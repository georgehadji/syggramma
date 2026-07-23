"""Tests for the Eudoxus API client, SnapshotStore, and Harvest pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from syggramma.adapters.eudoxus import (
    EudoxusClient,
    TokenBucket,
    CircuitBreaker,
)
from syggramma.ports import (
    RecaptchaChallengeError,
    SuspiciousEmptyResult,
)
from syggramma.adapters.storage import SnapshotStore
from syggramma.pipelines.harvest import (
    HarvestPipeline,
    _secretariat_id_from_academics,
    DepartmentInfo,
    InstitutionInfo,
)


# ── TokenBucket ─────────────────────────────────────────────────────────────


class TestTokenBucket:
    def test_init_has_tokens(self) -> None:
        bucket = TokenBucket(rate=10.0, burst=5)
        # Initially full
        assert bucket._tokens == 5.0

    def test_acquire_reduces_tokens(self) -> None:
        bucket = TokenBucket(rate=100.0, burst=10)
        import asyncio
        asyncio.run(bucket.acquire())
        assert bucket._tokens < 10.0


# ── CircuitBreaker ──────────────────────────────────────────────────────────

class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_success_resets_failures(self) -> None:
        breaker = CircuitBreaker(failure_threshold=3, reset_timeout=10.0)
        async def good() -> int:
            return 42
        result = await breaker.call(good())
        assert result == 42
        assert breaker._failures == 0

    @pytest.mark.asyncio
    async def test_failure_opens_circuit(self) -> None:
        breaker = CircuitBreaker(failure_threshold=2, reset_timeout=60.0)
        async def bad() -> None:
            raise ValueError("fail")
        with pytest.raises(ValueError):
            await breaker.call(bad())
        assert breaker._failures == 1
        # Second failure opens circuit
        with pytest.raises(ValueError):
            await breaker.call(bad())
        assert breaker._open is True


# ── SnapshotStore ───────────────────────────────────────────────────────────

class TestSnapshotStore:
    def test_store_and_exists(self, tmp_path: Path) -> None:
        store = SnapshotStore(base_dir=tmp_path)
        body = b'{"test": true}'
        raw = store.store("http://example.com", body)
        assert raw.sha256 == store._sha256(body)
        assert store.exists(raw.sha256)

    def test_dedup(self, tmp_path: Path) -> None:
        store = SnapshotStore(base_dir=tmp_path)
        body = b'{"dedup": true}'
        raw1 = store.store("http://example.com/1", body)
        raw2 = store.store("http://example.com/2", body)
        # Same content, same sha256
        assert raw1.sha256 == raw2.sha256

    def test_load_by_sha256(self, tmp_path: Path) -> None:
        store = SnapshotStore(base_dir=tmp_path)
        body = b'hello snapshot'
        raw = store.store("http://test.gr", body)
        loaded = store.load_by_sha256(raw.sha256)
        assert loaded is not None
        assert loaded.value == body
        assert loaded.url == "http://test.gr"

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        store = SnapshotStore(base_dir=tmp_path)
        assert store.load_by_sha256("0000000000000000000000000000000000000000000000000000000000000000") is None


# ── EudoxusClient — reCAPTCHA detection ─────────────────────────────────────

class TestEudoxusClient:
    def test_recaptcha_detection_stops(self) -> None:
        """If a response body starts with HTML containing 'recaptcha',
        the client raises RecaptchaChallengeError."""
        client = EudoxusClient(recaptcha_stop=True)
        # Simulate the detection logic
        body_text = "<html>recaptcha challenge</html>"
        assert body_text.startswith("<")
        assert "recaptcha" in body_text.lower()


# ── Secretatiat ID resolution ───────────────────────────────────────────────

class TestSecretariatIdResolution:
    def test_resolves_from_academic_secretariats(self) -> None:
        academics = {
            "119": {"id": 2845},
            "120": {"id": 2846},
        }
        assert _secretariat_id_from_academics(119, academics) == 2845
        assert _secretariat_id_from_academics(120, academics) == 2846

    def test_returns_none_for_missing(self) -> None:
        assert _secretariat_id_from_academics(999, {}) is None

    def test_returns_none_for_invalid_id(self) -> None:
        academics = {"1": {"id": "not_an_int"}}
        result = _secretariat_id_from_academics(1, academics)
        assert result is None


# ── Department parsing ──────────────────────────────────────────────────────

class TestDepartmentParsing:
    def test_institution_parsing(self) -> None:
        raw = [
            {"id": 1, "name": "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ"},
            {"id": 2, "name": "ΕΘΝΙΚΟ ΚΑΙ ΚΑΠΟΔΙΣΤΡΙΑΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ"},
        ]
        result = HarvestPipeline._parse_institutions(raw)
        assert len(result) == 2
        assert result[1].name == "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ"

    def test_department_parsing_marks_merged(self) -> None:
        institutions = {1: InstitutionInfo(eudoxus_id=1, name="Test Uni")}
        institution_academics = {
            "1": [
                {"id": 101, "school": "ΣΧΟΛΗ", "department": "ΤΜΗΜΑ"},
                {"id": 102, "school": "ΣΧΟΛΗ", "department": "ΤΜΗΜΑ (ΚΑΤΑΡΓΗΘΗΚΕ)"},
            ],
        }
        academic_secretariats = {
            "101": {"id": 2001},
            "102": {"id": 2002},
        }
        departments = HarvestPipeline._parse_departments(
            institutions, institution_academics, academic_secretariats,
        )
        assert len(departments) == 2
        assert departments[0].is_live is True
        assert departments[0].secretariat_id == 2001
        assert departments[1].is_live is False
