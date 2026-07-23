"""Content-addressed snapshot store for raw HTTP responses (L0).

Snapshots are stored on disk keyed by sha256 of the response body.
Two-level sharding (first 2 / next 2 hex chars) keeps directory sizes flat.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from syggramma.config import settings
from syggramma.kernel import Raw, SnapshotId


class SnapshotStore:
    """File-system backed content-addressed store for L0 snapshots.

    Directory layout:
        <base>/
          ab/
            cd/
              abcdef...sha256  (body, raw bytes)
              abcdef...sha256.json  (metadata as JSON)
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or settings.snapshot_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    # ── Public API ─────────────────────────────────────────────────────

    def store(self, url: str, body: bytes, headers: dict[str, str] | None = None) -> Raw:
        """Store a response body content-addressed by sha256.

        If the body already exists, returns existing metadata (dedup).
        SnapshotId is derived from the sha256 (first 8 hex chars as int)
        for a stable reference without a database.
        """
        sha256 = self._sha256(body)
        body_path = self._body_path(sha256)

        if body_path.exists():
            meta = self._read_meta(sha256)
            return Raw(
                value=body,
                snapshot_id=SnapshotId(int(sha256[:8], 16)),
                url=url,
                fetched_at=datetime.fromisoformat(meta["fetched_at"]),
                sha256=sha256,
            )

        # Persist body
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_bytes(body)

        # Persist metadata
        now = datetime.now(UTC).isoformat()
        meta = {
            "sha256": sha256,
            "url": url,
            "headers": headers,
            "fetched_at": now,
        }
        meta_path = self._meta_path(sha256)
        meta_path.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

        return Raw(
            value=body,
            snapshot_id=SnapshotId(int(sha256[:8], 16)),
            url=url,
            fetched_at=datetime.fromisoformat(now),
            sha256=sha256,
        )

    def load_by_sha256(self, sha256: str) -> Raw | None:
        """Load a snapshot by its content hash."""
        body_path = self._body_path(sha256)
        if not body_path.exists():
            return None
        body = body_path.read_bytes()
        meta = self._read_meta(sha256)
        return Raw(
            value=body,
            snapshot_id=SnapshotId(int(sha256[:8], 16)),
            url=meta["url"],
            fetched_at=datetime.fromisoformat(meta["fetched_at"]),
            sha256=sha256,
        )

    def exists(self, sha256: str) -> bool:
        """Check if a snapshot with the given hash already exists."""
        return self._body_path(sha256).exists()

    # ── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _sha256(body: bytes) -> str:
        return hashlib.sha256(body).hexdigest()

    def _body_path(self, sha256: str) -> Path:
        return self._base_dir / sha256[:2] / sha256[2:4] / sha256

    def _meta_path(self, sha256: str) -> Path:
        return self._base_dir / sha256[:2] / sha256[2:4] / f"{sha256}.json"

    def _read_meta(self, sha256: str) -> dict[str, Any]:
        return json.loads(self._meta_path(sha256).read_text(encoding="utf-8"))  # type: ignore[no-any-return]
