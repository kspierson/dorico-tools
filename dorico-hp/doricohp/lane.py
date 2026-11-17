"""Apply's shaping written into Dorico's Dynamics lane (Play mode).

The lane (`kDynamic` automation, tests I/I2 2026-11-01) holds **absolute** Dorico levels and,
inside a drawn span, replaces Dorico's own dynamics, humanise, beat stress and accent boosts.
So Apply draws it only where its shaping differs from the written dynamics (phrase swells,
espressivo, open-hairpin returns, section balance) and leaves the rest to Dorico. Inside a
span it adds the accent/marcato boost Dorico would have added.

Engine levels are steps (mf 0, mp -1, f +1, p -2 …); Dorico levels come from
`doricokit.dynlevels` (mf +0.5, mp -0.5, f +1, p -1 …). `step_to_level` interpolates between
the named points.
"""
from __future__ import annotations

from fractions import Fraction

from doricokit import dynlevels

from .engine import level_at, simplify
from .model import STEP

F = Fraction
_ANCHORS = sorted((float(STEP[k]), dynlevels.LEVELS[k]) for k in dynlevels.LEVELS)


def step_to_level(step: float) -> float:
    """Engine step (mf = 0) -> Dorico playback level (mf = 0.5)."""
    a = _ANCHORS
    if step <= a[0][0]:
        return a[0][1] + (step - a[0][0])
    if step >= a[-1][0]:
        return a[-1][1] + (step - a[-1][0])
    for (x0, y0), (x1, y1) in zip(a, a[1:]):
        if x0 <= step <= x1:
            return y0 + (y1 - y0) * (step - x0) / (x1 - x0)
    return a[-1][1]


def spans(pp, threshold: float = 0.1, join: Fraction = F(1)) -> list[tuple[Fraction, Fraction]]:
    """Stretches where the shaped curve differs from the written dynamics by >= threshold
    steps, widened to where the difference starts and ends, joined when closer than `join`."""
    off = pp.offset_curve()
    if not off:
        return []
    out: list[list[Fraction]] = []
    i = 0
    while i < len(off):
        if abs(off[i][1]) < threshold:
            i += 1
            continue
        j = i
        while j + 1 < len(off) and abs(off[j + 1][1]) >= threshold:
            j += 1
        a = off[i - 1][0] if i > 0 else off[i][0]
        b = off[j + 1][0] if j + 1 < len(off) else off[j][0]
        if out and a - out[-1][1] < join:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
        i = j + 1
    # a span that starts at (or just after) the end of a hairpin starts at the hairpin's start
    # instead, so the lane draws the whole hairpin and doesn't jump from Dorico's version of it
    for sp in out:
        for h0, h1, _ in pp.part.hairpins:
            if h0 < sp[0] <= h1 + F(1, 4):
                sp[0] = min(sp[0], h0)
    if not pp.part.notes:
        return []
    end = max(n.end for n in pp.part.notes)
    clipped = [(a, min(b, end)) for a, b in out]
    return [(a, b) for a, b in clipped if b > a]


def points(pp, a: Fraction, b: Fraction, accent_delta: float = 0.5, marcato_delta: float = 0.8,
           eps: Fraction = F(1, 480), lo: float = -6.0, hi: float = 6.0) -> list[tuple[Fraction, float]]:
    """Lane points (Dorico levels) for one span: the shaped curve plus accent boosts, kept
    inside Dorico's playback range lo..hi (`min/maxProfileLevelForPlayback`)."""
    bumps = []
    for n in pp.part.notes:
        if n.grace or not (a <= n.pos < b):
            continue
        d = marcato_delta if "marcato" in n.articulations else accent_delta if "accent" in n.articulations else 0.0
        if d:
            bumps.append((n.pos, min(n.end, b), d))
    xs = {a, b} | {p for p, _ in pp.shaped if a < p < b}
    for s, e, _ in bumps:
        xs |= {x for x in (s - eps, s, e - eps, e) if a <= x <= b}
    pts = []
    for x in sorted(xs):
        v = step_to_level(level_at(pp.shaped, x))
        v += sum(d for s, e, d in bumps if s <= x < e)
        pts.append((x, round(max(lo, min(hi, v)), 4)))
    return simplify(pts, 0.01)
