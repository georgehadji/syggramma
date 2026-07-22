"""Basic skeleton tests."""

from __future__ import annotations

from syggramma import __version__
from syggramma.kernel import TrustLevel, ok, err
from syggramma.domain import Semester, Period, Verdict


def test_version() -> None:
    """Package has a version string."""
    assert __version__ == "0.1.0"


def test_trust_level_enum() -> None:
    """Trust levels have correct ordering."""
    assert TrustLevel.RAW.value == 0
    assert TrustLevel.PARSED.value == 1
    assert TrustLevel.NORMALIZED.value == 2
    assert TrustLevel.INFERRED.value == 3
    assert TrustLevel.VERIFIED.value == 4


def test_result_ok() -> None:
    """Ok result wraps value correctly."""
    result = ok(42)
    assert result.value == 42


def test_result_err() -> None:
    """Err result carries message."""
    result = err("something went wrong")
    assert result.message == "something went wrong"


def test_domain_enums() -> None:
    """Domain enums exist and have correct values."""
    assert Semester.WINTER.value == 0
    assert Semester.SPRING.value == 1
    assert Period.WINTER.value == "Ximerino"
    assert Verdict.AUTHOR_SELF.value == "author_self"
    assert Verdict.NOT_AUTHOR.value == "not_author"
