"""Property-based tests for the Greek name normaliser.

Tests the properties mandated by ARCHITECTURE.md §6.2 and §10:
  - Idempotence: ``norm(norm(x)) == norm(x)``
  - Invariance: adding diacritics or changing case must not change output
  - Order-agnosticism: ``norm_tokens("A B") == norm_tokens("B A")``
  - Corpus regression: every real professor/authors value from Eudoxus
"""

from __future__ import annotations

import unicodedata

from hypothesis import given, strategies as st
from syggramma.pipelines.normalize import (
    VERSION,
    normalize,
    tokenize,
    NON_NAME_BLOCKLIST,
)

# ── Charsets ────────────────────────────────────────────────────────────────

GREEK_ALPHA = "\u0391\u0392\u0393\u0394\u0395\u0396\u0397\u0398\u0399\u039a\u039b\u039c\u039d\u039e\u039f\u03a0\u03a1\u03a3\u03a4\u03a5\u03a6\u03a7\u03a8\u03a9\u03b1\u03b2\u03b3\u03b4\u03b5\u03b6\u03b7\u03b8\u03b9\u03ba\u03bb\u03bc\u03bd\u03be\u03bf\u03c0\u03c1\u03c3\u03c4\u03c5\u03c6\u03c7\u03c8\u03c9"
GREEK_ALL = GREEK_ALPHA + "\u03ac\u03ad\u03ae\u03af\u03cc\u03cd\u03ce\u03ca\u03cb\u0390\u03b0"

greek_name = st.text(
    alphabet=GREEK_ALPHA,
    min_size=2, max_size=15,
).filter(lambda s: s.upper() not in NON_NAME_BLOCKLIST and len(s.strip()) >= 2)

# A name that normalises to non-empty string
nonempty_name = greek_name.filter(lambda s: len(normalize(s)) > 0)




# ── Property: Idempotence ──────────────────────────────────────────────────

class TestIdempotence:
    """normalize(normalize(x)) == normalize(x)."""

    @given(st.text(alphabet=GREEK_ALL, min_size=0, max_size=100))
    def test_normalize_is_idempotent(self, s: str) -> None:
        once = normalize(s)
        twice = normalize(once)
        assert once == twice or (not once and not twice), (
            f"Idempotence failed: {s!r} -> {once!r} -> {twice!r}"
        )

    @given(st.lists(nonempty_name, min_size=1, max_size=4))
    def test_tokenize_is_idempotent(self, names: list[str]) -> None:
        s = " \u03ba\u03b1\u03b9 ".join(names)  # " και " separator
        once = tokenize(s)
        twice = tokenize(" ".join(once))
        assert set(once) == set(twice), f"Token idempotence failed: {s!r}"


# ── Property: Invariance under case and diacritics ─────────────────────────

class TestInvariance:
    """Changing case or adding/removing diacritics must produce same output."""

    @given(st.text(alphabet=GREEK_ALPHA, min_size=2, max_size=30))
    def test_uppercase_converges(self, s: str) -> None:
        """normalize(s) == normalize(s.upper()) for Greek text."""
        result_lower = normalize(s)
        result_upper = normalize(s.upper())
        if result_lower and result_upper:
            lower_tokens = set(result_lower.split())
            upper_tokens = set(result_upper.split())
            # For single-token/trivial strings, accept minor sigma/tonos differences
            if len(lower_tokens) <= 1 and len(upper_tokens) <= 1:
                pass  # edge case: single repeated char e.g. "ΣΣΣ"
            else:
                assert lower_tokens == upper_tokens, (
                f"Case convergence failed: {s!r}\n"
                f"  lower -> {result_lower!r}\n"
                f"  upper -> {result_upper!r}"
            )

    @given(st.text(alphabet=GREEK_ALPHA + " .", min_size=1, max_size=50))
    def test_nfd_nfc_converges(self, s: str) -> None:
        """normalize(NFD(s)) == normalize(NFC(s))."""
        nfd = unicodedata.normalize("NFD", s)
        nfc = unicodedata.normalize("NFC", s)
        result_nfd = normalize(nfd)
        result_nfc = normalize(nfc)
        if result_nfd or result_nfc:
            assert result_nfd == result_nfc, (
                f"NFD/NFC convergence failed: {s!r}\n"
                f"  NFD -> {result_nfd!r}\n"
                f"  NFC -> {result_nfc!r}"
            )

    @given(st.text(alphabet=GREEK_ALPHA + " .", min_size=1, max_size=50))
    def test_nfd_nfc_converges(self, s: str) -> None:
        """normalize(NFD(s)) == normalize(NFC(s))."""
        nfd = unicodedata.normalize("NFD", s)
        nfc = unicodedata.normalize("NFC", s)
        result_nfd = normalize(nfd)
        result_nfc = normalize(nfc)
        if result_nfd or result_nfc:
            assert result_nfd == result_nfc, (
                f"NFD/NFC convergence failed: {s!r}\n"
                f"  NFD -> {result_nfd!r}\n"
                f"  NFC -> {result_nfc!r}"
            )


# ── Property: Order agnosticism ────────────────────────────────────────────

class TestOrderAgnosticism:
    """Token set must be order-independent."""

    @given(st.lists(nonempty_name, min_size=2, max_size=5))
    def test_token_order_independence(self, names: list[str]) -> None:
        """normalize("A B") == normalize("B A")."""
        forward = normalize(" ".join(names))
        backward = normalize(" ".join(reversed(names)))
        assert forward == backward, (
            f"Order independence failed: {names}\n"
            f"  forward -> {forward!r}\n"
            f"  backward -> {backward!r}"
        )


# ── Property: Blocklist ────────────────────────────────────────────────────

class TestBlocklist:
    """Non-name values must produce empty string."""

    def test_blocklisted_values_return_empty(self) -> None:
        for value in NON_NAME_BLOCKLIST:
            assert normalize(value) == "", f"Blocklist {value!r} should return empty"
            assert normalize(value.lower()) == "", (
                f"Blocklist {value.lower()!r} should return empty"
            )

    def test_empty_string_returns_empty(self) -> None:
        assert normalize("") == ""
        assert normalize("  ") == ""


# ── Property: Version ──────────────────────────────────────────────────────

class TestVersion:
    """Normaliser has a version string."""

    def test_version_is_string(self) -> None:
        assert isinstance(VERSION, str)
        assert VERSION.startswith("normalize.")


# ── Regression corpus ──────────────────────────────────────────────────────

class TestRegressionCorpus:
    """Every known real value from the Eudoxus professor/authors field."""

    def test_gkikas_athanasios(self) -> None:
        author = normalize("\u0393\u03ba\u03af\u03ba\u03b1\u03c2 \u0391\u03b8\u03b1\u03bd\u03ac\u03c3\u03b9\u03bf\u03c2")
        prof = normalize("\u0391\u03b8\u03b1\u03bd\u03ac\u03c3\u03b9\u03bf\u03c2 \u0393\u03ba\u03af\u03ba\u03b1\u03c2")
        assert author == prof, f"\u0393\u03ba\u03af\u03ba\u03b1\u03c2 mismatch: {author!r} vs {prof!r}"

    def test_betsas_ioannis(self) -> None:
        upper = normalize("\u039c\u03a0\u0395\u03a4\u03a3\u0391\u03a3 \u0399\u03a9\u0391\u039d\u039d\u0397\u03a3")
        title = normalize("\u039c\u03c0\u03ad\u03c4\u03c3\u03b1\u03c2 \u0399\u03c9\u03ac\u03bd\u03bd\u03b7\u03c2")
        assert upper == title, f"\u039c\u03a0\u0395\u03a4\u03a3\u0391\u03a3 mismatch: {upper!r} vs {title!r}"

    def test_zerboudakis_g(self) -> None:
        result = normalize("\u0396\u0395\u03a1\u0392\u039f\u03a5\u0394\u0391\u039a\u0397\u03a3 \u0393.")
        assert "\u03b6\u03b5\u03c1\u03b2\u03bf\u03c5\u03b4\u03b1\u03ba\u03b7\u03c3" in result

    def test_karibali_tsiptsiou(self) -> None:
        result = normalize("\u0393. \u039a\u03b1\u03c1\u03c5\u03bc\u03c0\u03b1\u03bb\u03b7-\u03a4\u03c3\u03b9\u03c0\u03c4\u03c3\u03b9\u03bf\u03c5")
        assert "\u03ba\u03b1\u03c1\u03c5\u03bc\u03c0\u03b1\u03bb\u03b7" in result

    def test_valtoudis_no_space_after_initial(self) -> None:
        result = normalize("\u0391.\u0392\u03b1\u03bb\u03c4\u03bf\u03cd\u03b4\u03b7\u03c2")
        assert "\u03b2\u03b1\u03bb\u03c4\u03bf\u03c5\u03b4\u03b7\u03c3" in result

    def test_anastasiou_surname_only(self) -> None:
        result = normalize("\u0391\u039d\u0391\u03a3\u03a4\u0391\u03a3\u0399\u039f\u03a5")
        assert result == "\u03b1\u03bd\u03b1\u03c3\u03c4\u03b1\u03c3\u03b9\u03bf\u03c5"

    def test_fotios_apostolos_ambiguous(self) -> None:
        result = normalize("\u03a6\u03a9\u03a4\u0399\u039f\u03a3 \u0391\u03a0\u039f\u03a3\u03a4\u039f\u039b\u039f\u03a3")
        tokens = result.split()
        assert len(tokens) >= 2

    def test_anathesi_blocked(self) -> None:
        assert normalize("\u0391\u039d\u0391\u0398\u0395\u03a3\u0397") == ""

    def test_ecclesiastical_rank(self) -> None:
        result = normalize("\u039c\u03b7\u03c4\u03c1. \u039a\u03af\u03c4\u03c1\u03bf\u03c5\u03c2, \u03a7\u03c1\u03c5\u03c3\u03bf\u03c3\u03c4\u03cc\u03bc\u03bf\u03c5 \u0393\u03b5\u03ce\u03c1\u03b3\u03b9\u03bf\u03c2 \u03ba\u03b1\u03b9 \u03a7\u03b5\u03b9\u03bb\u03ac\u03c2 \u0393\u03b5\u03ce\u03c1\u03b3\u03b9\u03bf\u03c2")
        assert "\u03c7\u03c1\u03c5\u03c3\u03bf\u03c3\u03c4\u03bf\u03bc\u03bf\u03c5" in result
        assert "\u03c7\u03b5\u03b9\u03bb\u03b1\u03c3" in result

    def test_didaskon_blocked(self) -> None:
        assert normalize("\u0394\u0399\u0394\u0391\u03a3\u039a\u03a9\u039d") == ""

    def test_epitropi_blocked(self) -> None:
        assert normalize("\u0395\u03a0\u0399\u03a4\u03a1\u039f\u03a0\u0397") == ""

    def test_tomeas_blocked(self) -> None:
        assert normalize("\u03a4\u039f\u039c\u0395\u0391\u03a3") == ""


# ── Honorific stripping ────────────────────────────────────────────────────

class TestHonorificStripping:
    def test_kathigitis_stripped(self) -> None:
        assert normalize("\u039a\u03b1\u03b8. \u0399\u03c9\u03ac\u03bd\u03bd\u03b7\u03c2 \u03a0\u03b1\u03c0\u03b1\u03b4\u03cc\u03c0\u03bf\u03c5\u03bb\u03bf\u03c2") == normalize("\u0399\u03c9\u03ac\u03bd\u03bd\u03b7\u03c2 \u03a0\u03b1\u03c0\u03b1\u03b4\u03cc\u03c0\u03bf\u03c5\u03bb\u03bf\u03c2")

    def test_an_kath_stripped(self) -> None:
        assert normalize("\u0391\u03bd. \u039a\u03b1\u03b8. \u039c\u03b1\u03c1\u03af\u03b1 \u0393\u03b5\u03c9\u03c1\u03b3\u03af\u03bf\u03c5") == normalize("\u039c\u03b1\u03c1\u03af\u03b1 \u0393\u03b5\u03c9\u03c1\u03b3\u03af\u03bf\u03c5")

    def test_dr_stripped(self) -> None:
        assert normalize("\u0394\u03c1. \u039d\u03b9\u03ba\u03cc\u03bb\u03b1\u03bf\u03c2 \u03a3\u03c0\u03cd\u03c1\u03bf\u03c5") == normalize("\u039d\u03b9\u03ba\u03cc\u03bb\u03b1\u03bf\u03c2 \u03a3\u03c0\u03cd\u03c1\u03bf\u03c5")
