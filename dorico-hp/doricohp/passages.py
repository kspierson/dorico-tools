"""Passage-level articulation and character from playing techniques and text.

Scores often mark a whole passage once ("stacc., brillante", "sempre legato", "leggiero")
instead of marking every note. HP and Dorico both ignore such words for playback unless
they are playing techniques the expression map knows. Here they become a passage state
that Apply uses for every note until it is cancelled.

Sources, in order of preference (research/score-vs-playback.md, flute solo):
- Dorico playing techniques, by their playback technique id (pt.staccato, pt.spiccato,
  pt.legato, pt.natural …) – built in, or the user's own technique linked to one;
- text items, by word (stacc., leggiero, brillante, sempre …).

A state lasts until a cancelling word (ord., nat., legato vs stacc. …), another word of
the same kind, or a rest of at least `reset_rest_crotchets` (default 8 = two 4/4 bars).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction

# flags: staccato (unslurred unmarked notes play staccato), short (shorter still),
# light (light/brilliant character: shorter caps, lighter attacks), legato, detache,
# marcato (stronger attacks), tenuto (full length), reset (back to normal)
TECHNIQUE_FLAGS = {
    "pt.staccato": {"staccato"},
    "pt.staccatissimo": {"staccato", "short"},
    "pt.spiccato": {"staccato", "light"},
    "pt.sautille": {"staccato", "light"},
    "pt.martele": {"marcato"},
    "pt.martellato": {"marcato"},
    "pt.marcato": {"marcato"},
    "pt.legato": {"legato"},
    "pt.nonLegato": {"detache"},
    "pt.detache": {"detache"},
    "pt.detacheLance": {"detache"},
    "pt.portatoloure": {"tenuto"},
    "pt.tenuto": {"tenuto"},
    "pt.natural": {"reset"},
}

# each pattern ends in (?!\w), not \b: \b fails after an abbreviation's dot ("marc.")
WORDS = [
    (r"\bstacc(\.|ato)?\b", {"staccato"}),
    (r"\bsecco(?!\w)|\bstaccatiss(\.|imo)(?!\w)", {"staccato", "short"}),
    (r"\bspicc(\.|ato)?\b", {"staccato", "light"}),
    (r"\b(leggi?ero|leggiermente|leggier\.?)(?!\w)", {"light"}),
    (r"\b(brillante|brill\.|scherzando|scherz\.|giocoso|capriccioso)(?!\w)", {"light"}),
    (r"\bmarc(\.|ato)(?!\w)|\bmartel", {"marcato"}),
    (r"\bpesante(?!\w)", {"marcato", "tenuto"}),
    (r"\b(non legato|non leg\.|d[ée]tach[ée])(?!\w)", {"detache"}),
    (r"(?<!non )\blegato(?!\w)|(?<!non )\bleg\.", {"legato"}),
    (r"\b(ten(\.|uto)|sostenuto|sost\.)(?!\w)", {"tenuto"}),
    (r"\b(ord(\.|inario)?|nat(\.|urale)?|normale|modo ordinario)(?!\w)", {"reset"}),
]

# what a new flag cancels
CANCELS = {
    "staccato": {"legato", "tenuto", "detache"},
    "legato": {"staccato", "short", "detache"},
    "detache": {"staccato", "short", "legato"},
    "tenuto": {"staccato", "short"},
}


def words_to_flags(text: str) -> set[str]:
    t = text.lower()
    out: set[str] = set()
    # negations first: "non stacc." / "non legato" must not also count as the plain word
    if re.search(r"\bnon stacc", t):
        out.add("reset")
        t = re.sub(r"\bnon stacc\w*\.?", " ", t)
    for pat, flags in WORDS:
        if re.search(pat, t):
            out |= flags
    if "sempre" in t:
        out.add("sempre")
    return out


def technique_flags(technique: str, text: str) -> set[str]:
    """Passage flags of a playing technique: its playback technique plus its own words.

    A custom technique linked to a built-in playback technique is notation: "stacc., brillante"
    linked to pt.staccato is staccato + light (the user's HP flute print copy). A technique
    linked to a custom *playback* technique (pt.user.*) only exists to switch an expression
    map's patch ("B Spiccato" in the ET score): the map owns it and its words are ignored,
    else Apply would shorten notes the sampled patch already plays short."""
    if technique.startswith("pt.user."):
        return set()
    return TECHNIQUE_FLAGS.get(technique, set()) | words_to_flags(text)


@dataclass
class PassageMap:
    changes: list[tuple[Fraction, set[str]]] = field(default_factory=list)   # (pos, active flags after)

    def at(self, pos: Fraction) -> set[str]:
        cur: set[str] = set()
        for p, flags in self.changes:
            if p > pos:
                break
            cur = flags
        return cur


def build(marks: list[tuple[Fraction, set[str]]], notes, reset_rest: Fraction = Fraction(8)) -> PassageMap:
    """marks: (pos, flags) from techniques/texts; notes: the part's notes (for rest resets)."""
    events: list[tuple[Fraction, str, set[str]]] = [(p, "mark", f) for p, f in marks if f]
    onsets = sorted({n.pos for n in notes if not n.grace})
    ends = {}
    for n in notes:
        ends[n.pos] = max(ends.get(n.pos, n.pos), n.end)
    last_end = None
    for p in onsets:
        if last_end is not None and p - last_end >= reset_rest:
            events.append((p, "rest", set()))
        last_end = max(last_end or p, ends[p])
    events.sort(key=lambda e: (e[0], e[1] != "rest"))
    pm = PassageMap()
    cur: set[str] = set()
    for pos, kind, flags in events:
        if kind == "rest":
            cur = set()
        elif "reset" in flags:
            cur = set(flags - {"reset", "sempre"})
        else:
            new = set(cur)
            for f in flags - {"sempre"}:
                new -= CANCELS.get(f, set())
                new.add(f)
            cur = new
        pm.changes.append((pos, set(cur)))
    return pm


def effective_articulations(note, state: set[str], rest_after: bool = False) -> frozenset[str]:
    """The note's articulations with the passage state applied (for playback lengths).

    Slurred notes keep their own length. A slur's last note does too, unless a rest follows
    it: then it is lifted like the unslurred notes. From the user's flute playback copy (HP
    FLUTE, 2026-10-31): under "stacc." 13 slur ends running into the next note stayed
    undotted, the one slur end before a rest was dotted."""
    arts = set(note.articulations)
    duration_marks = {"staccato", "staccatissimo", "tenuto", "staccato-tenuto", "spiccato"}
    if arts & duration_marks or note.slur in ("start", "in") or (note.slur == "end" and not rest_after):
        return frozenset(arts)
    if "staccato" in state:
        arts.add("staccatissimo" if "short" in state else "staccato")
    elif "tenuto" in state:
        arts.add("tenuto")
    return frozenset(arts)
