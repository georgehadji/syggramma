"""SMTP mail adapter implementing ``ports.MailerPort``.

Uses aiosmtplib for async delivery.  Supports STARTTLS and
authentication.  Designed for use with the transactional outbox.
"""

from __future__ import annotations

import contextlib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import aiosmtplib

from syggramma.config import Settings
from syggramma.domain import Contact
from syggramma.kernel import CampaignId, MessageId, Result, err, ok


class SmtpMailer:
    """Delivers emails via SMTP, respecting the MailerPort contract."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._client: aiosmtplib.SMTP | None = None

    async def send(
        self,
        to: Contact,
        subject: str,
        body: str,
        campaign_id: CampaignId,
        message_id: MessageId,
    ) -> Result[None]:
        """Send a single message via SMTP.

        Returns Ok(None) on success, Error on failure.
        """
        try:
            client = await self._get_client()
            msg = self._build_mime(to, subject, body, campaign_id, message_id)
            await client.send_message(msg)
        except (aiosmtplib.SMTPException, OSError) as exc:
            return err(f"SMTP delivery failed: {exc}")
        except Exception:
            return err("Unexpected SMTP error")
        return ok(None)

    async def close(self) -> None:
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.close()
            self._client = None

    # ── Internal helpers ─────────────────────────────────────────────────

    async def _get_client(self) -> aiosmtplib.SMTP:
        if self._client is not None and self._client.is_connected:
            return self._client

        self._client = aiosmtplib.SMTP(
            hostname=self._settings.smtp_host,
            port=self._settings.smtp_port,
            use_tls=self._settings.smtp_use_tls,
        )
        await self._client.connect()

        # STARTTLS if not already TLS
        if not self._settings.smtp_use_tls:
            try:
                await self._client.starttls()
            except (aiosmtplib.SMTPException, OSError):
                pass  # server may not support STARTTLS

        # Authenticate if credentials are provided
        if self._settings.smtp_username and self._settings.smtp_password:
            await self._client.login(
                self._settings.smtp_username,
                self._settings.smtp_password,
            )

        return self._client

    def _build_mime(
        self,
        to: Contact,
        subject: str,
        body: str,
        campaign_id: CampaignId,
        message_id: MessageId,
    ) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["From"] = formataddr(
            (self._settings.mail_from_name, self._settings.mail_from),
        )
        msg["To"] = to.value_encrypted  # decrypted by caller in production
        msg["Subject"] = subject
        msg["X-Campaign-Id"] = str(campaign_id)
        msg["X-Message-Id"] = str(message_id)
        msg.attach(MIMEText(body, "plain", "utf-8"))
        return msg
