"""CLI entry point for Syggramma using Typer."""

from __future__ import annotations

import asyncio
from typing import Optional

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
                    typer.echo(f"  ⚠  secretariat {unit.secretariat_id} [{unit.status}]: {unit.error}")
        await client.close()

    asyncio.run(_run())


@app.command()
def version() -> None:
    """Show the installed version."""
    from syggramma import __version__
    typer.echo(f"Syggramma v{__version__}")


def main() -> None:
    app()
