"""Render a Performance to a Standard MIDI File (format 1, one track per part).

For auditioning rules outside Dorico and for checking the engine against Finale's Human
Playback captures (same analysis tools: tools/analyze_capture.py, tools/style_report.py).
It is *not* how results reach Dorico (that is doricohp.apply).

Rendering assumptions (stand-ins for what Dorico would do):
- note lengths: Dorico's default playback options (normal 95 %, staccato 50 %,
  staccatissimo 25 %, tenuto 98 %, slurred 105 %);
- dynamics: instruments that sustain get the shaped level on CC11
  (level → CC with HP's measured table, ppp 27 … fff 105) and the engine's attack velocity;
  keyboard, harp and percussion get velocity = HP's level velocities (ppp 23 … fff 114) plus
  the accent offset;
- vibrato curves as computed.

    python3 -m doricohp.render SCORE OUT.mid [--style NAME]
"""
from __future__ import annotations

import struct
import sys
from fractions import Fraction

from .engine import PartPerf, level_at
from .model import Score

PPQ = 480
VELOCITY_FAMILIES = {"keyboard", "harp", "pitched percussion", "percussion", "guitar"}
LENGTHS = {"staccato": 0.5, "staccatissimo": 0.25, "tenuto": 0.98, "staccato-tenuto": 0.75, "spiccato": 0.4}


def level_to_cc(lv: float) -> int:
    # HP 05-dynamics: ppp 27, pp 35, p 44, mp 54, mf 65, f 77, ff 91, fff 105 (mf = 0 steps)
    table = [(-4, 27), (-3, 35), (-2, 44), (-1, 54), (0, 65), (1, 77), (2, 91), (3, 105), (4, 118)]
    if lv <= table[0][0]:
        return max(1, int(table[0][1] + (lv - table[0][0]) * 8))
    for (a, va), (b, vb) in zip(table, table[1:]):
        if lv <= b:
            return int(round(va + (vb - va) * (lv - a) / (b - a)))
    return min(127, int(table[-1][1] + (lv - table[-1][0]) * 9))


def level_to_velocity(lv: float) -> int:
    # Finale's default dynamic key velocities: ppp 23 … fff 114, 13 per step, mf = 75
    return int(round(min(127, max(1, 75 + 13 * lv))))


def _vlq(n: int) -> bytes:
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def _track(events: list[tuple[int, int, bytes]]) -> bytes:
    events.sort(key=lambda e: (e[0], e[1]))
    data, last = bytearray(), 0
    for tick, _, msg in events:
        data += _vlq(max(0, tick - last)) + msg
        last = max(last, tick)
    data += b"\x00\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(data)) + bytes(data)


def to_ticks(score: Score, pos: Fraction, ms: float = 0.0) -> int:
    return int(round(float(pos) * PPQ + ms / score.ms_per_crotchet(pos) * PPQ))


def render(score: Score, perfs: list[PartPerf], path: str) -> None:
    tracks = []
    meta = []
    for pos, bpm in score.tempos:
        meta.append((to_ticks(score, pos), 0, b"\xff\x51\x03" + int(round(60e6 / bpm)).to_bytes(3, "big")))
    tracks.append(_track(meta))
    for ch_i, pp in enumerate(perfs):
        ch = ch_i % 16
        if ch == 9:
            ch = 10
        name = pp.part.name.encode("utf-8", "replace")[:120]
        ev: list[tuple[int, int, bytes]] = [(0, 0, b"\xff\x03" + _vlq(len(name)) + name)]
        by_velocity = pp.part.family in VELOCITY_FAMILIES
        for npf in pp.notes:
            n = npf.note
            if n.grace:
                dur = Fraction(1, 8)
                start_pos = n.pos - dur
            else:
                f = 1.05 if n.slur in ("start", "in") else 0.95
                for a in n.articulations:
                    f = min(f, LENGTHS.get(a, f)) if a != "tenuto" else max(f, LENGTHS[a])
                dur, start_pos = n.dur * Fraction(f).limit_denominator(100), n.pos
            t0 = to_ticks(score, start_pos, npf.start_ms)
            t1 = max(t0 + 1, to_ticks(score, start_pos + dur, npf.end_ms))
            if by_velocity:
                vel = level_to_velocity(level_at(pp.shaped, n.pos) + npf.vel_delta / 13)
                if "accent" in n.articulations:
                    vel += 13
                if "marcato" in n.articulations:
                    vel += 18
            else:
                vel = npf.velocity
            vel = max(1, min(127, vel))
            ev.append((t0, 2, bytes([0x90 | ch, n.pitch & 0x7F, vel])))
            ev.append((t1, 1, bytes([0x80 | ch, n.pitch & 0x7F, 0])))
        if not by_velocity:
            last = None
            pts = pp.shaped
            end = max((npf.note.end for npf in pp.notes), default=Fraction(0))
            grid = sorted({p for p, _ in pts} | {Fraction(i, 8) for i in range(int(end * 8) + 1)})
            for p in grid:
                v = level_to_cc(level_at(pts, p))
                if v != last:
                    ev.append((to_ticks(score, p), 0, bytes([0xB0 | ch, 11, v])))
                    last = v
        for cc, pts in pp.ccs.items():
            last = None
            end = pts[-1][0] if pts else Fraction(0)
            grid = sorted({p for p, _ in pts} | {Fraction(i, 16) for i in range(int(end * 16) + 1)})
            for p in grid:
                v = int(round(min(127, max(0, level_at(pts, p)))))
                if v != last:
                    ev.append((to_ticks(score, p), 0, bytes([0xB0 | ch, cc & 0x7F, v])))
                    last = v
        tracks.append(_track(ev))
    with open(path, "wb") as f:
        f.write(b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), PPQ))
        for t in tracks:
            f.write(t)


def main(argv: list[str]) -> None:
    from . import engine, model
    from .profiles import Profiles
    style = "Standard"
    if "--style" in argv:
        i = argv.index("--style")
        style = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    src, out = argv
    score = model.load(src)
    perfs = engine.perform(score, Profiles(style))
    render(score, perfs, out)
    for pp in perfs:
        print(pp.part.name, "; ".join(pp.notes_for_log))


if __name__ == "__main__":
    main(sys.argv[1:])
