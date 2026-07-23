"""CLI entry point for Syggramma using Typer."""

from __future__ import annotations

import asyncio

import typer

from syggramma.adapters.eudoxus import EudoxusClient
from syggramma.adapters.storage import SnapshotStore
from syggramma.config import settings
from syggramma.pipelines.harvest import HarvestPipeline

app = typer.Typer(
    name="syggramma",
    help="Market-intelligence and author-outreach system for Εκδόσεις Κυριακίδη",
)


@app.command()
def harvest(
    years: str = typer.Option(
        "2024,2025",
        "--years", "-y",
        help="Comma-separated list of academic years to harvest",
    ),
    pilot_ids: str | None = typer.Option(
        None,
        "--pilot-ids", "-p",
        help="Comma-separated list of secretariat IDs for pilot mode",
    ),
    max_concurrent: int = typer.Option(
        4,
        "--max-concurrent", "-c",
        help="Maximum concurrent department-year harvests",
    ),
) -> None:
    """Run the Eudoxus harvest pipeline for one or more years."""
    year_list = [int(y.strip()) for y in years.split(",")]
    pilot_list: list[int] | None = None
    if pilot_ids:
        pilot_list = [int(p.strip()) for p in pilot_ids.split(",")]

    async def _run() -> None:
        client = EudoxusClient(
            base_url=settings.eudoxus_base_url,
            max_rps=settings.eudoxus_max_rps,
            max_concurrent=settings.eudoxus_max_concurrent,
            user_agent=settings.eudoxus_user_agent,
        )
        store = SnapshotStore()
        pipeline = HarvestPipeline(
            eudoxus=client,
            snapshot_store=store,
            max_concurrent_units=max_concurrent,
        )
        results = await pipeline.run(
            years=year_list,
            pilot_secretariat_ids=pilot_list,
        )
        for run in results:
            status = "✓" if run.status == "completed" else "✗"
            typer.echo(f"{status} Year {run.year}: {len(run.units)} units, "
                       f"{run.total_courses} courses, {run.total_books} books")
            for unit in run.units:
                if unit.error:
                    typer.echo(
                        f"  warning  secretariat {unit.secretariat_id}"
                        f" [{unit.status}]: {unit.error}",
                    )
        await client.close()

    asyncio.run(_run())


@app.command()
def version() -> None:
    """Show the installed version."""
    from syggramma import __version__
    typer.echo(f"Syggramma v{__version__}")


@app.command()
def scheduler(
    action: str = typer.Option(
        "start",
        "--action", "-a",
        help="start | stop | status",
    ),
) -> None:
    """Manage the background scheduler (APScheduler).

    The scheduler runs periodic harvest and analysis jobs.
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    sched = AsyncIOScheduler()

    @sched.scheduled_job(IntervalTrigger(hours=24))  # type: ignore[untyped-decorator]
    async def harvest_job() -> None:
        """Daily harvest of the current academic year."""
        client = EudoxusClient(
            base_url=settings.eudoxus_base_url,
            max_rps=settings.eudoxus_max_rps,
            max_concurrent=settings.eudoxus_max_concurrent,
            user_agent=settings.eudoxus_user_agent,
        )
        try:
            store = SnapshotStore()
            pipeline = HarvestPipeline(
                eudoxus=client,
                snapshot_store=store,
                max_concurrent_units=2,
            )
            results = await pipeline.run(
                years=[2025],
                pilot_secretariat_ids=None,
            )
            typer.echo(f"Harvest completed: {len(results)} year-runs")
        finally:
            await client.close()

    @sched.scheduled_job(IntervalTrigger(hours=6))  # type: ignore[untyped-decorator]
    async def outbox_flush_job() -> None:
        """Flush the outreach outbox every 6 hours."""
        import asyncio as _asyncio

        from syggramma.adapters.mail import SmtpMailer
        from syggramma.pipelines.outreach import EventStore, Outbox

        store = EventStore()
        outbox = Outbox(store)
        if outbox.has_pending():
            from syggramma.domain import Message as _Msg
            from syggramma.kernel import Result as _Res
            mailer = SmtpMailer()
            try:
                def sync_mailer(msg: _Msg) -> _Res[None]:
                    return _asyncio.run(mailer.send(
                        msg.person_id,  # type: ignore[arg-type]
                        msg.subject,
                        msg.body,
                        msg.campaign_id,  # type: ignore[arg-type]
                        msg.id,  # type: ignore[arg-type]
                    ))
                outbox.dispatch(sync_mailer)
            finally:
                await mailer.close()
            typer.echo("Outbox flushed")

    if action == "start":
        sched.start()
        typer.echo("Scheduler started (harvest: 24h, outbox: 6h)")
        import asyncio
        try:
            asyncio.get_event_loop().run_forever()
        except (KeyboardInterrupt, SystemExit):
            sched.shutdown()
    elif action == "stop":
        sched.shutdown()
        typer.echo("Scheduler stopped")
    else:
        typer.echo(f"Scheduler status: {'running' if sched.running else 'stopped'}")


def main() -> None:
    app()
