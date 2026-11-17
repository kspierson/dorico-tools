"""Dorico's playback dynamic levels: written dynamic -> level -> controller value.

    from doricokit import dynlevels
    dynlevels.level("mf")                  # 0.5   (Dorico level of a written dynamic)
    dynlevels.level("f", accent=True)      # 1.5   (+ accentDynamicDelta, default 0.5)
    dynlevels.curve(1.0)                   # 0.69  (position 0..1 in the map's range)
    dynlevels.to_range(1.0, 1, 127)        # 87    (CC11 on a map with range 1..127)

These are the numbers Dorico uses for playback and stores in Play mode's **Dynamics lane**
(`AutomationEventDefinition`, `controllerDefinition` = `kDynamic`, absolute; inside a drawn
span the lane replaces Dorico's own dynamics, humanise and beat stress).

Measured 2026-11-01 (dorico-hp session, tests I and I2: `HPCaptures\\dorico\\test-I2\\`,
Dorico 5.1, HP FLUTE project, map "SWAM - Flute" with CC11 range 1..127 and velocity range
40..127, Playback Options humanise 0, beat stress 0, `dynamicCurveParams` 0.5, 2.5, 2.5):
- written pppp…ffff land exactly on lane levels: p letters -> -n, f letters -> +n,
  mp -0.5, mf +0.5 (nothing is written at 0). ppppp/pppppp and fffff/ffffff (+-5, +-6) follow
  the same pattern but were not written in the test;
- an accent adds `dynamicsOptions.accentDynamicDelta` (0.5 here), a marcato
  `marcatoDynamicDelta` (0.8);
- controller and velocity follow one curve, scaled into each range (CC11 76 and velocity 92
  for mf). `CURVE` holds it for `dynamicCurveParams` 0.5, 2.5, 2.5 (the user's projects); other
  curve settings are not measured. Levels outside -6..6 are clamped by Dorico
  (`min/maxProfileLevelForPlayback`).
"""
from __future__ import annotations

from bisect import bisect_right

__all__ = ["LEVELS", "CURVE", "CURVE_PARAMS", "level", "curve", "to_range", "from_range"]

LEVELS: dict[str, float] = {
    "pppppp": -6.0, "ppppp": -5.0, "pppp": -4.0, "ppp": -3.0, "pp": -2.0, "p": -1.0,
    "mp": -0.5, "mf": 0.5,
    "f": 1.0, "ff": 2.0, "fff": 3.0, "ffff": 4.0, "fffff": 5.0, "ffffff": 6.0,
}

CURVE_PARAMS = (0.5, 2.5, 2.5)
# level -> position in the map's range (0..1), from CC11 on a 1..127 range: (cc - 1) / 126.
_MEASURED_CC = [(-6, 1), (-5, 2), (-4, 5), (-3, 12), (-2.5, 17), (-2, 24), (-1.5, 32), (-1, 41),
                (-0.5, 52), (0, 64), (0.5, 76), (1, 87), (1.5, 96), (2, 104), (2.5, 111),
                (3, 116), (4, 123), (5, 126), (6, 127)]
CURVE: list[tuple[float, float]] = [(float(lv), (cc - 1) / 126) for lv, cc in _MEASURED_CC]


def level(name: str, accent: bool = False, marcato: bool = False,
          accent_delta: float = 0.5, marcato_delta: float = 0.8) -> float:
    """Dorico level of a written immediate dynamic ("mf", "ff"…), plus articulation boosts.
    Raises KeyError for names it doesn't know (force/combined dynamics: not measured yet)."""
    v = LEVELS[name.strip()]
    if marcato:
        v += marcato_delta
    elif accent:
        v += accent_delta
    return v


def curve(lv: float) -> float:
    """Position (0..1) of a level in an expression map's range, by linear interpolation of the
    measured curve; clamped at -6 and 6."""
    xs = [x for x, _ in CURVE]
    if lv <= xs[0]:
        return CURVE[0][1]
    if lv >= xs[-1]:
        return CURVE[-1][1]
    i = bisect_right(xs, lv) - 1
    (x0, y0), (x1, y1) = CURVE[i], CURVE[i + 1]
    return y0 + (y1 - y0) * (lv - x0) / (x1 - x0)


def to_range(lv: float, lo: int, hi: int) -> int:
    """The controller value or velocity Dorico sends for a level on a map range lo..hi."""
    return int(round(lo + curve(lv) * (hi - lo)))


def from_range(value: float, lo: int, hi: int) -> float:
    """Inverse of `to_range` (level for a controller value), by interpolation."""
    y = (value - lo) / (hi - lo) if hi != lo else 0.0
    pts = CURVE
    if y <= pts[0][1]:
        return pts[0][0]
    if y >= pts[-1][1]:
        return pts[-1][0]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if y0 <= y <= y1 and y1 > y0:
            return x0 + (x1 - x0) * (y - y0) / (y1 - y0)
    return pts[-1][0]
