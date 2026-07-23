"""Greek person-name normaliser — pure functional, no I/O.

Implements the Greek-specific transformations required by ARCHITECTURE.md §6.2.
Every function is ``str -> str`` or ``str -> list[str]`` and carries a
``VERSION`` string so that L2 rows record which normaliser state produced them.
"""

from __future__ import annotations

import re
import unicodedata

# ── Version ─────────────────────────────────────────────────────────────────

VERSION = "normalize.person_name:v1"

# ── Constants ───────────────────────────────────────────────────────────────

# Honorifics and ranks to strip from the beginning of name strings.
# Listed in approximate order of frequency in the Eudoxus corpus.
HONORIFICS = [
    "Μητρ.", "Μητρ", "Μητροπολίτης",
    "Καθ.", "Καθ", "Καθηγητής", "Καθηγήτρια",
    "Αν. Καθ.", "Αν. Καθ", "Αναπληρωτής Καθηγητής", "Αναπληρώτρια Καθηγήτρια",
    "Επ. Καθ.", "Επ. Καθ", "Επίκουρος Καθηγητής", "Επίκουρη Καθηγήτρια",
    "Δρ.", "Δρ", "Dr.",
    "π.", "Π.",
    "Prof.", "Professor",
    "Ομότ. Καθ.", "Ομότιμος Καθηγητής",
    "Λέκτορας", "Λέκτ.",
    "ΕΔΙΠ",
    "ΤΟΜΕΑΣ",
]

# Non-name blocklist — values that appear in the professor/authors field
# that are NOT people.  Verified real values from the Eudoxus corpus.
NON_NAME_BLOCKLIST = {
    "ΑΝΑΘΕΣΗ",
    "ΔΙΔΑΣΚΩΝ",
    "ΕΠΙΤΡΟΠΗ",
    "ΤΟΜΕΑΣ",
}

# Greek lowercase vowel with tonos → bare vowel mapping
# Used during accent stripping (NFD + strip + NFC handles most, but
# this provides an explicit safety net).
GREEK_ACCENT_MAP = {
    "ά": "α", "ὰ": "α", "ἀ": "α", "ἁ": "α", "ἂ": "α", "ἃ": "α",
    "έ": "ε", "ὲ": "ε", "ἐ": "ε", "ἑ": "ε", "ἒ": "ε", "ἓ": "ε",
    "ή": "η", "ὴ": "η", "ἠ": "η", "ἡ": "η", "ἢ": "η", "ἣ": "η",
    "ί": "ι", "ὶ": "ι", "ἰ": "ι", "ἱ": "ι", "ἲ": "ι", "ἳ": "ι",
    "ό": "ο", "ὸ": "ο", "ὀ": "ο", "ὁ": "ο", "ὂ": "ο", "ὃ": "ο",
    "ύ": "υ", "ὺ": "υ", "ὐ": "υ", "ὑ": "υ", "ὒ": "υ", "ὓ": "υ",
    "ώ": "ω", "ὼ": "ω", "ὠ": "ω", "ὡ": "ω", "ὢ": "ω", "ὣ": "ω",
    "ϊ": "ι", "ϋ": "υ",
    "ΐ": "ι", "ΰ": "υ",
}


# ── Core normalisation pipeline ─────────────────────────────────────────────

def normalize(raw: str) -> str:
    """Normalise a single person-name string to its canonical form.

    The normalisation pipeline consists of:
      1. Strip whitespace
      2. Detect and reject non-name blocklisted values
      3. Strip honorifics/ranks
      4. Unicode NFD → strip combining marks → NFC
      5. Final sigma folding (ς → σ)
      6. Case folding (upper → lower, handling Greek accent loss)
      7. Collapse whitespace
      8. Sort tokens alphabetically (order-agnostic output)
    """
    s = raw.strip()

    if not s or s.upper() in NON_NAME_BLOCKLIST:
        return ""

    s = _strip_honorifics(s)
    s = _strip_combining_marks(s)
    s = _fold_case(s)
    s = _fold_final_sigma(s)
    s = s.rstrip(".")
    tokens = _tokenize(s)
    tokens = [t for t in tokens if t and len(t) >= 1]
    if not tokens:
        return ""
    tokens.sort()
    return " ".join(tokens)


def tokenize(raw: str) -> list[str]:
    """Split a name field into individual name tokens.

    Splits on commas, the conjunction `` και `` (with spaces), and whitespace.
    Then normalises each token.
    """
    s = raw.strip()
    if not s:
        return []

    # Split on comma, " και ", "Και", or whitespace
    parts = re.split(r"\s*,\s*|\s+και\s+|\s+Και\s+|\s+", s)

    tokens: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        normalised = normalize(part)
        if normalised:
            tokens.append(normalised)
    return tokens


def split_surname_given(tokens: list[str]) -> tuple[str | None, str | None]:
    """Best-effort split into (surname, given).

    Heuristic rules:
      - If exactly two tokens, first is surname (Greek convention).
      - If one token, it's surname-only.
      - If one token looks like an initial (single char or char+period),
        it's given-only (abbreviated).
      - If > 2 tokens, return (None, None) as ambiguous.

    Returns (None, None) when the split is ambiguous.
    """
    cleaned = [t for t in tokens if t]

    # Filter out pure initials
    initials: list[str] = []
    names: list[str] = []
    for t in cleaned:
        if _is_initial(t):
            initials.append(t)
        else:
            names.append(t)

    if len(names) == 2:
        return (names[0], names[1])
    if len(names) == 1:
        if initials:
            # "Γκίκας Α." → surname=Γκίκας, given=Α
            return (names[0], initials[0])
        return (names[0], None)
    if len(names) == 0 and len(initials) >= 1:
        return (None, initials[0])
    return (None, None)


# ── Internal transformation steps ───────────────────────────────────────────

def _strip_honorifics(s: str) -> str:
    """Remove leading honorifics and ranks."""
    for h in HONORIFICS:
        if s.startswith(h):
            s = s[len(h):].strip()
    return s


def _strip_combining_marks(s: str) -> str:
    """NFD → remove combining marks (accents, breathing marks) → NFC.

    This handles Greek tonos, dialytika, and other diacritics.
    """
    nfd = unicodedata.normalize("NFD", s)
    stripped = "".join(ch for ch in nfd if unicodedata.combining(ch) == 0)
    return unicodedata.normalize("NFC", stripped)


def _fold_final_sigma(s: str) -> str:
    """Replace final sigma (ς) with regular sigma (σ).

    This is needed because case folding may produce ς in middle of word
    (from uppercase Σ), and we want a single canonical form.
    """
    return s.replace("ς", "σ")


def _fold_case(s: str) -> str:
    """Fold to lowercase, handling Greek uppercase accent loss.

    Greek uppercase letters drop their accents (e.g., ΜΠΕΤΣΑΣ → μπετσασ).
    Standard str.lower() does this correctly for Greek, but we do an
    extra pass to map any remaining accented lowercase chars.
    """
    lowered = s.lower()
    # Extra safety pass for any accented chars that survived
    result: list[str] = []
    for ch in lowered:
        result.append(GREEK_ACCENT_MAP.get(ch, ch))
    return "".join(result)


def _tokenize(s: str) -> list[str]:
    """Split a normalised string into whitespace-separated tokens."""
    return s.split()


def _is_initial(t: str) -> bool:
    """Check if a token looks like an initial (single letter, possibly with period).

    Examples: ``Α``, ``Α.``, ``Γ``, ``Ά``, ``Μ.``
    """
    t = t.strip(".")
    return len(t) == 1 and t.isalpha()
