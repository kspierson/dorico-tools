"""Instrument pitch ("key") written in names and staff text: "Trumpet in C", "C Tpt.", "Cl. in A",
"E♭ Clarinet", "to B♭ Cl.". Used when the source has no transposition (untyped staves in concert
scores): the standard instrument is chosen unless a key is stated.

Keys are Dorico entity-ID suffixes: "c", "bflat", "a", "eflat", "f", "d", "g", "aflat", ...
"""
from __future__ import annotations

import re

# transposing families whose pitch is a choice; standard key first
FAMILIES = {
    "clarinet": ("bflat", re.compile(r"\b(clarinets?|clar|cls?)\b", re.I)),
    "trumpet": ("bflat", re.compile(r"\b(trumpets?|tpts?|trp|tromba)\b", re.I)),
    "horn": ("f", re.compile(r"\b(?<!english )(horns?|hns?|corno|corni)\b", re.I)),
    "cornet": ("bflat", re.compile(r"\b(cornets?|cnt)\b", re.I)),
}

_ACC = r"(b|♭|flat|#|♯|sharp)?"
_IN_KEY = re.compile(r"\b(?:in|to)\s+([A-G])\s*" + _ACC + r"(?![\w])", re.I)
_LEADING = re.compile(r"^\s*(?:to\s+)?([A-G])\s*" + _ACC + r"\s+(?=[A-Za-z])", re.I)


def _key(letter: str, acc: str | None) -> str:
    acc = (acc or "").lower()
    suffix = "flat" if acc in ("b", "♭", "flat") else "sharp" if acc in ("#", "♯", "sharp") else ""
    return letter.lower() + suffix


def find_key(text: str) -> str | None:
    """'Trumpet in C' -> 'c'; 'E♭ Clarinet' -> 'eflat'; 'Clarinets 1' -> None."""
    m = _IN_KEY.search(text) or _LEADING.match(text)
    return _key(m.group(1), m.group(2)) if m else None


def strip_key(text: str) -> str:
    """Name without its key: 'Trumpet in C 1' -> 'Trumpet 1', 'C Tpt.' -> 'Tpt.'."""
    t = _IN_KEY.sub("", text)
    t = _LEADING.sub("", t)
    return " ".join(t.split())


def family(name: str) -> str | None:
    for fam, (_, rx) in FAMILIES.items():
        if rx.search(name):
            return fam
    return None


def standard_key(fam: str) -> str:
    return FAMILIES[fam][0]
