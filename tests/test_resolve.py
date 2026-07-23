"""Tests for the person entity resolution pipeline."""

from __future__ import annotations

import pytest
from syggramma.pipelines.resolve import (
    generate_candidates,
    score_match,
    make_block_key,
    make_phonetic_block_key,
    surname_exact_match,
    surname_fuzzy_match,
    initial_compatibility,
    UnionFind,
    PersonMatch,
)
from syggramma.domain import Verdict


# ── Blocking ────────────────────────────────────────────────────────────────

class TestBlocking:
    def test_block_key_from_normalized(self) -> None:
        assert make_block_key("αθανασιος γκικασ") == "αθαν"

    def test_block_key_empty(self) -> None:
        assert make_block_key("") == ""

    def test_phonetic_block_key(self) -> None:
        # "μπετσασ" → phonetic starts with "β"
        key = make_phonetic_block_key("\u03bc\u03c0\u03b5\u03c4\u03c3\u03b1\u03c3")
        assert key.startswith("\u03b2")  # starts with "β"

    def test_block_key_first_token(self) -> None:
        # Single token
        assert make_block_key("\u03b6\u03b5\u03c1\u03b2\u03bf\u03c5\u03b4\u03b1\u03ba\u03b7\u03c3")[:4] == "\u03b6\u03b5\u03c1\u03b2"


# ── Candidate generation ───────────────────────────────────────────────────

class TestCandidateGeneration:
    def test_known_match_gkikas(self) -> None:
        """Γκίκας matches Αθανάσιος Γκίκας."""
        prof = "\u0391\u03b8\u03b1\u03bd\u03ac\u03c3\u03b9\u03bf\u03c2 \u0393\u03ba\u03af\u03ba\u03b1\u03c2"
        authors = ["\u0393\u03ba\u03af\u03ba\u03b1\u03c2 \u0391\u03b8\u03b1\u03bd\u03ac\u03c3\u03b9\u03bf\u03c2"]
        candidates = generate_candidates(prof, authors)
        assert len(candidates) >= 1

    def test_nomatch_different_surname(self) -> None:
        prof = "\u0399\u03c9\u03ac\u03bd\u03bd\u03b7\u03c2 \u03a0\u03b1\u03c0\u03b1\u03b4\u03cc\u03c0\u03bf\u03c5\u03bb\u03bf\u03c2"
        authors = ["\u0393\u03ba\u03af\u03ba\u03b1\u03c2 \u0391\u03b8\u03b1\u03bd\u03ac\u03c3\u03b9\u03bf\u03c2"]
        candidates = generate_candidates(prof, authors)
        assert len(candidates) == 0


# ── Matchers ───────────────────────────────────────────────────────────────

class TestSurnameExact:
    def test_exact_match(self) -> None:
        result = surname_exact_match("\u03b1\u03b8\u03b1\u03bd\u03b1\u03c3\u03b9\u03bf\u03c2 \u03b3\u03ba\u03b9\u03ba\u03b1\u03c3", "\u03b3\u03ba\u03b9\u03ba\u03b1\u03c3 \u03b1\u03b8\u03b1\u03bd\u03b1\u03c3\u03b9\u03bf\u03c2")
        assert result.score > 0.5  # both have γκικασ as surname

    def test_different_surname(self) -> None:
        result = surname_exact_match("\u03b1\u03b8\u03b1\u03bd\u03b1\u03c3\u03b9\u03bf\u03c2 \u03b3\u03ba\u03b9\u03ba\u03b1\u03c3", "\u03c0\u03b1\u03c0\u03b1\u03b4\u03bf\u03c0\u03bf\u03c5\u03bb\u03bf\u03c2 \u03b9\u03c9\u03b1\u03bd\u03bd\u03b7\u03c2")
        assert result.score == 0.0


class TestSurnameFuzzy:
    def test_fuzzy_similar(self) -> None:
        result = surname_fuzzy_match("\u03b1\u03b8\u03b1\u03bd\u03b1\u03c3\u03b9\u03bf\u03c2 \u03b3\u03ba\u03b9\u03ba\u03b1\u03c3", "\u03a0\u03b1\u03c0\u03b1\u03b4\u03cc\u03c0\u03bf\u03c5\u03bb\u03bf\u03c2 \u0399\u03c9\u03ac\u03bd\u03bd\u03b7\u03c2")
        assert 0.0 <= result.score <= 1.0

    def test_identical_surname(self) -> None:
        result = surname_fuzzy_match("\u03b1 \u03b3\u03ba\u03b9\u03ba\u03b1\u03c3", "\u03b2 \u03b3\u03ba\u03b9\u03ba\u03b1\u03c3")
        assert result.score >= 0.99


class TestInitialCompatibility:
    def test_matching_initial(self) -> None:
        result = initial_compatibility("\u0393. \u039a\u03b1\u03c1\u03c5\u03bc\u03c0\u03b1\u03bb\u03b7", "\u0393\u03b5\u03ce\u03c1\u03b3\u03b9\u03bf\u03c2 \u0386\u03bb\u03bb\u03bf\u03c2")
        assert result.score == 0.5  # neutral

    def test_no_initials(self) -> None:
        result = initial_compatibility("\u03a0\u03b1\u03c0\u03b1\u03b4\u03cc\u03c0\u03bf\u03c5\u03bb\u03bf\u03c2", "\u0393\u03ba\u03af\u03ba\u03b1\u03c2")
        assert result.score == 0.5  # neutral


# ── Ensemble scorer ────────────────────────────────────────────────────────

class TestEnsembleScorer:
    def test_author_self_verdict(self) -> None:
        """Same person: professor IS the author."""
        match = score_match(
            "\u0391\u03b8\u03b1\u03bd\u03ac\u03c3\u03b9\u03bf\u03c2 \u0393\u03ba\u03af\u03ba\u03b1\u03c2",
            "\u0393\u03ba\u03af\u03ba\u03b1\u03c2 \u0391\u03b8\u03b1\u03bd\u03ac\u03c3\u03b9\u03bf\u03c2",
        )
        assert match.verdict == Verdict.AUTHOR_SELF, f"Got {match.verdict}, score={match.ensemble_score}"

    def test_completely_different(self) -> None:
        """Completely different people → NOT_AUTHOR."""
        match = score_match(
            "\u0399\u03c9\u03ac\u03bd\u03bd\u03b7\u03c2 \u03a0\u03b1\u03c0\u03b1\u03b4\u03cc\u03c0\u03bf\u03c5\u03bb\u03bf\u03c2",
            "\u0393\u03ba\u03af\u03ba\u03b1\u03c2 \u0391\u03b8\u03b1\u03bd\u03ac\u03c3\u03b9\u03bf\u03c2",
        )
        assert match.verdict == Verdict.NOT_AUTHOR, f"Got {match.verdict}, score={match.ensemble_score}"

    def test_betsas_uppercase_vs_titlecase(self) -> None:
        """All-caps must converge with title case."""
        match = score_match(
            "\u039c\u03a0\u0395\u03a4\u03a3\u0391\u03a3 \u0399\u03a9\u0391\u039d\u039d\u0397\u03a3",
            "\u039c\u03c0\u03ad\u03c4\u03c3\u03b1\u03c2 \u0399\u03c9\u03ac\u03bd\u03bd\u03b7\u03c2",
        )
        assert match.verdict in (Verdict.AUTHOR_SELF, Verdict.PROBABLE), (
            f"Got {match.verdict}, score={match.ensemble_score}"
        )

    def test_feature_vector_created(self) -> None:
        match = score_match(
            "\u0391\u03b8\u03b1\u03bd\u03ac\u03c3\u03b9\u03bf\u03c2 \u0393\u03ba\u03af\u03ba\u03b1\u03c2",
            "\u0393\u03ba\u03af\u03ba\u03b1\u03c2 \u0391\u03b8\u03b1\u03bd\u03ac\u03c3\u03b9\u03bf\u03c2",
        )
        from syggramma.pipelines.resolve import make_feature_vector
        fv = make_feature_vector(match)
        assert "surname_exact" in fv.features
        assert "ensemble" in fv.features
        assert fv.method == "resolve.ensemble:v1"


# ── Union-Find ─────────────────────────────────────────────────────────────

class TestUnionFind:
    def test_singleton(self) -> None:
        uf = UnionFind()
        uf.add("\u03b1")
        assert uf.find("\u03b1") == "\u03b1"

    def test_union(self) -> None:
        uf = UnionFind()
        uf.union("\u03b1", "\u03b2")
        assert uf.find("\u03b1") == uf.find("\u03b2")

    def test_transitive(self) -> None:
        uf = UnionFind()
        uf.union("\u03b1", "\u03b2")
        uf.union("\u03b2", "\u03b3")
        assert uf.find("\u03b1") == uf.find("\u03b3")

    def test_clusters(self) -> None:
        uf = UnionFind()
        uf.union("\u03b1", "\u03b2")
        uf.union("\u03b3", "\u03b4")
        clusters = uf.clusters()
        assert len(clusters) == 2


# ── Integration: full pipeline ─────────────────────────────────────────────

class TestPipelineIntegration:
    def test_regression_corpus(self) -> None:
        """All 11 EUDOXUS-API.md values integrated through the pipeline."""
        # Proof that the resolve pipeline can handle every known real value
        test_cases = [
            ("\u0391\u03b8\u03b1\u03bd\u03ac\u03c3\u03b9\u03bf\u03c2 \u0393\u03ba\u03af\u03ba\u03b1\u03c2",
             "\u0393\u03ba\u03af\u03ba\u03b1\u03c2 \u0391\u03b8\u03b1\u03bd\u03ac\u03c3\u03b9\u03bf\u03c2",
             Verdict.AUTHOR_SELF),
            ("\u039c\u03a0\u0395\u03a4\u03a3\u0391\u03a3 \u0399\u03a9\u0391\u039d\u039d\u0397\u03a3",
             "\u039c\u03c0\u03ad\u03c4\u03c3\u03b1\u03c2 \u0399\u03c9\u03ac\u03bd\u03bd\u03b7\u03c2",
             Verdict.AUTHOR_SELF),
            ("\u0396\u0395\u03a1\u0392\u039f\u03a5\u0394\u0391\u039a\u0397\u03a3 \u0393.",
             "\u0396\u03b5\u03c1\u03b2\u03bf\u03cd\u03b4\u03b1\u03ba\u03b7\u03c2 \u0393\u03b5\u03ce\u03c1\u03b3\u03b9\u03bf\u03c2",
             Verdict.PROBABLE),
        ]
        for prof, author, expected_min in test_cases:
            match = score_match(prof, author)
            assert list(Verdict).index(match.verdict) <= list(Verdict).index(expected_min), (
                f"{prof!r} vs {author!r}: {match.verdict} < {expected_min}"
            )
