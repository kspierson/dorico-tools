"""Pedal harp: pedal settings, strings and the pitches they sound.

    from doricokit import harp
    p = harp.Pedals.parse("Db C B | E F# G# A")       # also "D♭ C♮ B♮ | E♮ F♯ G♯ A♮"
    p = harp.Pedals.from_model(mark["detail"])         # a "harp pedals" mark of doricokit.model
    harp.strings(p)            # the 47 strings low to high: String(index, letter, octave, pitch)
    harp.Pedals.infer({61, 63, 64, 66, 67, 68, 70})    # pedal settings that sound these pitches

Strings run C1–G7 (47 strings, as on a concert pedal harp). MIDI pitches use C4 = 60, so the
lowest string sounds 23 (C♭1) to 25 (C♯1). Two strings can sound the same pitch (enharmonic
doubles such as G♯ + A♭); a glissando plays both, which is how the harp sounds.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

__all__ = ["LETTERS", "PEDAL_ORDER", "Pedals", "String", "strings", "LOWEST", "HIGHEST"]

LETTERS = "CDEFGAB"
PEDAL_ORDER = "DCBEFGA"               # left foot D C B, right foot E F G A (diagram order)
_NATURAL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_SIGN = {-1: "♭", 0: "♮", 1: "♯"}
# Dorico's HarpPedal event: pedalSettings/<x>Pedal = kTop (flat), kMiddle (natural), kBottom (sharp)
_MODEL = {"kTop": -1, "kMiddle": 0, "kBottom": 1}
LOWEST = ("C", 1)
HIGHEST = ("G", 7)


@dataclass(frozen=True)
class Pedals:
    """Alteration per string letter: -1 flat, 0 natural, +1 sharp (C D E F G A B order)."""
    alter: tuple[int, int, int, int, int, int, int] = (0, 0, 0, 0, 0, 0, 0)

    def of(self, letter: str) -> int:
        return self.alter[LETTERS.index(letter)]

    @classmethod
    def from_dict(cls, d: dict[str, int]) -> "Pedals":
        return cls(tuple(int(d.get(x, 0)) for x in LETTERS))  # type: ignore[arg-type]

    @classmethod
    def parse(cls, text: str) -> "Pedals":
        """'Db C B | E F# G# A', 'D♭ C♮ B♮ | E♮ F♯ G♯ A♮' or 'Db,C,B,E,F#,G#,A'.
        Letters may come in any order; a letter not given is natural."""
        d: dict[str, int] = {}
        for tok in text.replace("|", " ").replace(",", " ").split():
            letter, rest = tok[0].upper(), tok[1:]
            if letter not in _NATURAL:
                raise ValueError(f"not a harp pedal: {tok!r}")
            if rest in ("", "n", "♮", "nat"):
                d[letter] = 0
            elif rest in ("b", "♭", "f", "flat"):
                d[letter] = -1
            elif rest in ("#", "♯", "s", "sharp"):
                d[letter] = 1
            else:
                raise ValueError(f"not a harp pedal: {tok!r}")
        return cls.from_dict(d)

    @classmethod
    def from_model(cls, detail: dict[str, str]) -> "Pedals":
        """From a `doricokit.model` "harp pedals" mark's `detail` ({"aPedal": "kTop", ...}).
        A pedal the mark leaves out is natural."""
        return cls.from_dict({x: _MODEL.get(detail.get(f"{x.lower()}Pedal", "kMiddle"), 0)
                              for x in LETTERS})

    @classmethod
    def infer(cls, pitches, doubles=()) -> list["Pedals"]:
        """Every pedal setting whose strings sound exactly the pitch classes of `pitches`
        (and sound each pitch class in `doubles` on two strings). Fewest sharps/flats first."""
        want = {p % 12 for p in pitches}
        dbl = {p % 12 for p in doubles}
        found = []
        for alter in itertools.product((-1, 0, 1), repeat=7):
            pcs = [(_NATURAL[x] + a) % 12 for x, a in zip(LETTERS, alter)]
            if set(pcs) != want:
                continue
            if any(pcs.count(pc) < 2 for pc in dbl):
                continue
            found.append(cls(alter))  # type: ignore[arg-type]
        return sorted(found, key=lambda p: (sum(a != 0 for a in p.alter), p.alter))

    @property
    def pitch_classes(self) -> set[int]:
        return {(_NATURAL[x] + a) % 12 for x, a in zip(LETTERS, self.alter)}

    def __str__(self) -> str:
        name = lambda x: x + _SIGN[self.of(x)]  # noqa: E731
        return " ".join(name(x) for x in PEDAL_ORDER[:3]) + " | " + " ".join(name(x) for x in PEDAL_ORDER[3:])


@dataclass(frozen=True)
class String:
    index: int      # 0 = C1 ... 46 = G7
    letter: str
    octave: int
    pitch: int      # sounding MIDI pitch with the pedals applied
    alter: int

    @property
    def name(self) -> str:
        return f"{self.letter}{_SIGN[self.alter] if self.alter else ''}{self.octave}"


def strings(pedals: Pedals) -> list[String]:
    """All 47 strings, low to high. Pitches follow string order, except where a B♯ string
    sounds above the C♭ string next to it (rare)."""
    out = []
    octave, li = LOWEST[1], LETTERS.index(LOWEST[0])
    while True:
        letter = LETTERS[li]
        a = pedals.of(letter)
        out.append(String(len(out), letter, octave, 12 * (octave + 1) + _NATURAL[letter] + a, a))
        if (letter, octave) == HIGHEST:
            return out
        li += 1
        if li == 7:
            li, octave = 0, octave + 1
