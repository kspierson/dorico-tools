"""Positions and durations: Dorico stores exact fractions of a crotchet as text ("81/4").
Python code holds them as `fractions.Fraction`; parsing and formatting are done by the Rust
`Ratio` (engine/crates/dorico-format/src/ratio.rs) so every tool reads them the same way.

    frac("81/4") -> Fraction(81, 4)      invalid or empty text -> 0 (lenient, as tools expect)
    frac_str(Fraction(3, 2)) -> "3/2"    frac_str(2) -> "2"
    to_ticks(Fraction(1, 7)) -> 69       480 ticks per crotchet, halves to even like round()
"""
from __future__ import annotations

from fractions import Fraction

from . import _native

TICKS_PER_CROTCHET: int = _native.TICKS_PER_CROTCHET

__all__ = ["TICKS_PER_CROTCHET", "frac", "frac_str", "from_ticks", "to_ticks"]


def frac(s: str | None) -> Fraction:
    n, d = _native.ratio_parse(s or "")
    return Fraction(n, d)


def frac_str(f: Fraction | int) -> str:
    f = Fraction(f)
    return _native.ratio_format(f.numerator, f.denominator)


def to_ticks(f: Fraction | int) -> int:
    f = Fraction(f)
    return _native.ratio_to_ticks(f.numerator, f.denominator)


def from_ticks(t: int) -> Fraction:
    return Fraction(t, TICKS_PER_CROTCHET)
