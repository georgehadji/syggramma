"""Person entity resolution pipeline — blocking, matching, ensemble scoring.

Implements the architecture described in ARCHITECTURE.md §6.3:
  - Blocking (canopy clustering via trigram similarity)
  - Individual matchers (surname exact, surname fuzzy, initial)
  - Weighted ensemble → four-tier verdicts
  - Union-Find for canonical person merging
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

from syggramma.domain import Verdict
from syggramma.kernel import FeatureVector
from syggramma.pipelines.normalize import (
    normalize,
    split_surname_given,
    _strip_combining_marks,
    _fold_case,
    _fold_final_sigma,
)


# ── Scoring types ──────────────────────────────────────────────────────────

@dataclass
class MatchSignal:
    """Output of a single matcher."""

    name: str  # e.g. "surname_exact"
    score: float  # 0.0 to 1.0
    weight: float  # contribution to ensemble
    details: str = ""


@dataclass
class PersonMatch:
    """A candidate match between a professor name and an author name."""

    professor_normalized: str
    author_normalized: str
    signals: list[MatchSignal] = field(default_factory=list)
    ensemble_score: float = 0.0
    verdict: Verdict = Verdict.UNCERTAIN


# ── Feature vector builder ─────────────────────────────────────────────────

def make_feature_vector(match: PersonMatch) -> FeatureVector:
    """Build an explainable feature vector from match signals."""
    features: dict[str, float] = {}
    for s in match.signals:
        features[s.name] = s.score
    features["ensemble"] = match.ensemble_score
    return FeatureVector(
        features=features,
        method=f"resolve.ensemble:v1",
    )


# ── Blocking (candidate generation) ────────────────────────────────────────

def make_block_key(normalized: str) -> str:
    """Generate a blocking key for canopy clustering.

    Uses the first 4 characters of the normalized surname.
    """
    if not normalized:
        return ""
    tokens = normalized.split()
    if not tokens:
        return ""
    # Take the first token (likely surname in normalized form)
    key = tokens[0][:4]
    return key


def make_phonetic_block_key(normalized: str) -> str:
    """Simple phonetic key for Greek names.

    Handles first-character variation like Μπ→Β, Γκ→Γ, etc.
    A full Soundex would be better; this is a lightweight fallback.
    """
    if not normalized:
        return ""
    tokens = normalized.split()
    if not tokens:
        return ""
    first = tokens[0].lower()[:4]
    # Handle common Greek consonant clusters
    replacements = {
        "μπ": "β", "ντ": "δ", "γκ": "γ", "γγ": "γ",
        "τζ": "ζ", "τσ": "σ",
    }
    for old, new in replacements.items():
        if first.startswith(old):
            first = new + first[len(old):]
            break
    return first


def generate_candidates(
    professor_name: str,
    author_names: list[str],
    threshold: float = 0.4,
) -> list[tuple[str, str, float]]:
    """Generate candidate (professor, author) pairs using blocking + trigram.

    First applies blocking, then filters by fuzzy similarity above threshold.
    Returns list of (professor, author, similarity_score).
    """
    prof_norm = normalize(professor_name)
    if not prof_norm:
        return []

    prof_key = make_block_key(prof_norm)

    candidates: list[tuple[str, str, float]] = []
    for author_raw in author_names:
        auth_norm = normalize(author_raw)
        if not auth_norm:
            continue

        # Check blocking key match
        auth_key = make_block_key(auth_norm)
        if prof_key != auth_key:
            # Try phonetic fallback
            prof_phon = make_phonetic_block_key(prof_norm)
            auth_phon = make_phonetic_block_key(auth_norm)
            if prof_phon != auth_phon:
                continue

        # Fuzzy similarity check
        sim = fuzz.token_sort_ratio(prof_norm, auth_norm) / 100.0
        if sim >= threshold:
            candidates.append((prof_norm, auth_norm, sim))

    return candidates


# ── Individual matchers ────────────────────────────────────────────────────

def surname_exact_match(prof_raw: str, author_raw: str) -> MatchSignal:
    """Surname exact match after normalisation."""
    prof_normalized = normalize(prof_raw)
    author_normalized = normalize(author_raw)
    prof_parts = prof_normalized.split()
    auth_parts = author_normalized.split()

    if not prof_parts or not auth_parts:
        return MatchSignal("surname_exact", 0.0, 0.35)

    # Last token in normalized form is likely the surname (sorted order puts surname last)
    prof_surname = prof_parts[-1] if len(prof_parts) >= 1 else prof_parts[0]
    auth_surname = auth_parts[-1] if len(auth_parts) >= 1 else auth_parts[0]

    score = 1.0 if prof_surname == auth_surname else 0.0
    return MatchSignal(
        "surname_exact", score, 0.35,
        details=f"{prof_surname} vs {auth_surname}",
    )


def surname_fuzzy_match(prof_raw: str, author_raw: str) -> MatchSignal:
    """Fuzzy surname similarity using partial ratio."""
    prof_normalized = normalize(prof_raw)
    author_normalized = normalize(author_raw)
    prof_parts = prof_normalized.split()
    auth_parts = author_normalized.split()

    if not prof_parts or not auth_parts:
        return MatchSignal("surname_fuzzy", 0.0, 0.25)

    prof_surname = prof_parts[-1]
    auth_surname = auth_parts[-1]

    score = fuzz.partial_ratio(prof_surname, auth_surname) / 100.0
    return MatchSignal(
        "surname_fuzzy", score, 0.25,
        details=f"{prof_surname} ~ {auth_surname}: {score:.2f}",
    )


def initial_compatibility(prof_raw: str, author_raw: str) -> MatchSignal:
    """Check if given-name initials are compatible.

    Handles cases like 'Α. Βαλτούδης' and 'Αθανάσιος Γκίκας'.
    """
    prof_initials = _extract_initials(prof_raw)
    auth_initials = _extract_initials(author_raw)

    if not prof_initials or not auth_initials:
        return MatchSignal("initial_compat", 0.5, 0.15)  # neutral

    # Check if any initial matches
    for pi in prof_initials:
        for ai in auth_initials:
            if pi == ai:
                return MatchSignal("initial_compat", 1.0, 0.15)

    return MatchSignal("initial_compat", 0.0, 0.15)


def _extract_initials(raw: str) -> list[str]:
    """Extract single-letter initials from a name string.

    Examples:
      'Γ. Καρυμπαλη-Τσιπτσιου' → ['γ']
      'Αθανάσιος Γκίκας' → ['α']
      'ΜΠΕΤΣΑΣ ΙΩΑΝΝΗΣ' → ['ι']
      'ΖΕΡΒΟΥΔΑΚΗΣ Γ.' → ['γ']
    """
    s = _strip_combining_marks(raw)
    s = _fold_case(s)
    s = _fold_final_sigma(s)

    initials: list[str] = []
    for token in s.split():
        t = token.strip(".")
        if len(t) == 1 and t.isalpha():
            initials.append(t)
    return initials


# ── Ensemble scorer ────────────────────────────────────────────────────────

def score_match(prof_raw: str, author_raw: str) -> PersonMatch:
    """Run all matchers and produce an ensemble score with verdict."""
    prof_norm = normalize(prof_raw)
    auth_norm = normalize(author_raw)

    match = PersonMatch(
        professor_normalized=prof_norm,
        author_normalized=auth_norm,
    )

    if not prof_norm or not auth_norm:
        match.verdict = Verdict.NOT_AUTHOR
        return match

    # Run all matchers
    match.signals.append(surname_exact_match(prof_norm, auth_norm))
    match.signals.append(surname_fuzzy_match(prof_norm, auth_norm))
    match.signals.append(initial_compatibility(prof_raw, author_raw))

    # Weighted ensemble
    total_weight = sum(s.weight for s in match.signals)
    weighted_sum = sum(s.score * s.weight for s in match.signals)
    match.ensemble_score = weighted_sum / total_weight if total_weight > 0 else 0.0

    # Four-tier verdict
    match.verdict = _determine_verdict(match)
    return match


def _determine_verdict(match: PersonMatch) -> Verdict:
    """Convert ensemble score to four-tier verdict.

    Thresholds (configurable):
      - AUTHOR_SELF: score >= 0.85 AND surname exact
      - PROBABLE:    score >= 0.70
      - UNCERTAIN:   score >= 0.40
      - NOT_AUTHOR:  score < 0.40 or no signals
    """
    score = match.ensemble_score

    # Check for AUTHOR_SELF: surname exact AND good ensemble
    surname_signal = next(
        (s for s in match.signals if s.name == "surname_exact"), None
    )
    if surname_signal and surname_signal.score >= 0.99 and score >= 0.80:
        return Verdict.AUTHOR_SELF

    if score >= 0.70:
        return Verdict.PROBABLE
    if score >= 0.40:
        return Verdict.UNCERTAIN
    return Verdict.NOT_AUTHOR


# ── Union-Find (disjoint set) for canonical person merging ──────────────────

class UnionFind:
    """Union-Find data structure for merging alias clusters into persons.

    Near-linear time; the natural structure for transitive identity.
    """

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = {}
        self._size: dict[str, int] = {}

    def find(self, x: str) -> str:
        """Find with path compression."""
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0
            self._size[x] = 1
            return x
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, a: str, b: str) -> None:
        """Union by rank. Returns True if merged, False if already same."""
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        self._size[ra] += self._size.get(rb, 0)
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1

    def clusters(self) -> dict[str, set[str]]:
        """Return all clusters as {root: {members}}."""
        result: dict[str, set[str]] = {}
        for item in self._parent:
            root = self.find(item)
            if root not in result:
                result[root] = set()
            result[root].add(item)
        return result

    def add(self, x: str) -> None:
        """Ensure an element exists in the structure."""
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0
            self._size[x] = 1
