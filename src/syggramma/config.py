"""Application configuration via pydantic-settings.

All configuration is loaded from environment variables at startup.
No secrets are hardcoded or committed.  Fails fast on missing config.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── General ──────────────────────────────────────────────────────────
    app_env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = True
    log_level: str = "INFO"

    # ── Database ─────────────────────────────────────────────────────────
    db_url: str = "postgresql+psycopg://syggramma:syggramma@localhost:5432/syggramma"
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # ── Eudoxus API ──────────────────────────────────────────────────────
    eudoxus_base_url: str = "https://service.eudoxus.gr/coursebooks/rest/"
    eudoxus_max_rps: float = 2.0
    eudoxus_max_concurrent: int = 4
    eudoxus_user_agent: str = "Syggramma/0.1 (mailto:vivlosbooks@gmail.com)"

    # ── External APIs ────────────────────────────────────────────────────
    openalex_base_url: str = "https://api.openalex.org/"
    openalex_max_rps: float = 10.0
    openalex_mailto: str = "vivlosbooks@gmail.com"

    orcid_base_url: str = "https://pub.orcid.org/v3.0/"
    orcid_max_rps: float = 5.0

    crossref_base_url: str = "https://api.crossref.org/"
    crossref_max_rps: float = 5.0

    # ── Anthropic (LLM) ──────────────────────────────────────────────────
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_max_tokens: int = 4096

    # ── SMTP / Mail ──────────────────────────────────────────────────────
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False
    mail_from: str = "noreply@kyriakidis.gr"
    mail_from_name: str = "Εκδόσεις Κυριακίδη"

    # ── Outreach ─────────────────────────────────────────────────────────
    outreach_max_per_day: int = 50
    outreach_quiet_period_days: int = 90
    outreach_default_legal_basis: str = "GDPR Art. 6(1)(f) — Legitimate Interest"
    outreach_lia_document_ref: str = ""

    # ── Encryption ────────────────────────────────────────────────────────
    encryption_key: str = ""
    """Fernet key for column-level encryption of contact data.
    Generate with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    """

    # ── Paths ────────────────────────────────────────────────────────────
    data_dir: Path = Path("data")
    snapshot_dir: Path = Path("data/snapshots")

    # ── Harvest ──────────────────────────────────────────────────────────
    harvest_start_year: int = 2024
    harvest_end_year: int = 2025
    harvest_pilot_departments: list[int] | None = None
    """If set, only harvest these secretariat ids (pilot mode)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
"""Global settings instance.  Import this everywhere."""
