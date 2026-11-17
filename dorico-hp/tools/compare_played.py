"""Compare how two .dorico copies of a piece *play*, note by note, in milliseconds.

    python3 tools/compare_played.py A.dorico B.dorico [--part "Flute 1"] [--notes] [--flow N]

Typical use: A = the printed-notation copy after Apply, B = the user's hand-made playback
copy (extra dots, accents, dynamics) played by Dorico as it is.

For every note matched in both copies (same part name, position and pitch) it works out the
start shift and the played length:
- a note with Play-mode offsets (kEventPlayStart/EndOffset) plays exactly those;
- otherwise Dorico's own length rule applies (playback options, the expression map's
  overrides, the note's articulations and slur), as `doricohp.apply.played_length`.
Dorico's timing humanise and the map's technique length factors are not modelled.

Output is Markdown: per part a table by what B does to the note (B's articulations) with
A's and B's median lengths, a per-bar table of median lengths, and with --notes every note.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from doricohp import model  # noqa: E402
from doricohp.apply import played_length  # noqa: E402
from doricohp.playback import PlaybackSetup  # noqa: E402
from doricohp.project import PLAY_END, PLAY_START, TICKS_PER_CROTCHET, VELOCITY, get_int_prop  # noqa: E402

NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def pitch_name(p: int) -> str:
    return f"{NAMES[p % 12]}{p // 12 - 1}"


def played(path: str, flow_index: int) -> tuple[object, dict]:
    """{(part, pos, pitch): info} for one flow of a project."""
    sc = model.from_dorico_all(path)[flow_index]
    setup = PlaybackSetup(sc.project)
    out = {}
    for part in sc.parts:
        for n in part.notes:
            if n.grace:
                continue
            mpc = sc.ms_per_crotchet(n.pos)
            node = n.ref.node if n.ref is not None else None
            t0 = get_int_prop(node, PLAY_START) if node is not None else None
            t1 = get_int_prop(node, PLAY_END) if node is not None else None
            vel = get_int_prop(node, VELOCITY) if node is not None else None
            if t1 is not None or t0 is not None:
                start = Fraction(t0 or 0, TICKS_PER_CROTCHET)
                length = n.dur + Fraction(t1 or 0, TICKS_PER_CROTCHET) - start
                how = "offsets"
            else:
                start = Fraction(0)
                length = played_length(n, setup, part.instrument_id)
                how = "dorico"
            out[(part.name, n.pos, n.pitch)] = {
                "note": n, "start_ms": float(start) * mpc, "len_ms": float(length) * mpc,
                "written_ms": float(n.dur) * mpc, "vel": vel, "how": how,
                "bar": sc.bar_of(n.pos), "beat": n.pos - sc.bar_starts[sc.bar_of(n.pos)],
                "passage": sorted(part.passage.at(n.pos)) if part.passage else [],
            }
    return sc, out


def marks(n) -> str:
    a = sorted(n.articulations)
    if n.slur in ("start", "in"):
        a.append("slur")
    return "+".join(a) or "–"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--part", action="append", help="part name (repeatable); default all")
    ap.add_argument("--flow", type=int, default=0)
    ap.add_argument("--notes", action="store_true", help="list every note")
    args = ap.parse_args()
    sa, A = played(args.a, args.flow)
    sb, B = played(args.b, args.flow)
    keys = sorted(set(A) & set(B), key=lambda k: (k[0], k[1], k[2]))
    parts = args.part or sorted({k[0] for k in keys}, key=lambda p: [k[0] for k in keys].index(p))
    print(f"# Played lengths: A = {Path(args.a).name}, B = {Path(args.b).name}\n")
    print(f"Matched notes: {len(keys)} (only in A: {len(set(A) - set(B))}, only in B: {len(set(B) - set(A))}). "
          "Lengths in ms; 'dorico' = Dorico's own length rule, 'offsets' = Play-mode offsets.\n")
    for part in parts:
        ks = [k for k in keys if k[0] == part]
        if not ks:
            continue
        hows = defaultdict(set)
        for k in ks:
            hows["A"].add(A[k]["how"])
            hows["B"].add(B[k]["how"])
        print(f"## {part} ({len(ks)} notes; A: {'/'.join(sorted(hows['A']))}, B: {'/'.join(sorted(hows['B']))})\n")
        # by B's marking (what the playback copy asks for)
        groups = defaultdict(list)
        for k in ks:
            groups[(marks(A[k]["note"]), marks(B[k]["note"]), round(A[k]["written_ms"]))].append(k)
        print("| A marks | B marks | written ms | notes | A median ms | B median ms | A/B |")
        print("|---|---|---|---|---|---|---|")
        for (ma, mb, w), g in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            la = median(A[k]["len_ms"] for k in g)
            lb = median(B[k]["len_ms"] for k in g)
            print(f"| {ma} | {mb} | {w} | {len(g)} | {la:.0f} | {lb:.0f} | {la / lb:.2f} |")
        print()
        bars = defaultdict(list)
        for k in ks:
            bars[A[k]["bar"]].append(k)
        print("| bar | notes | A median ms | B median ms | A start shift ms (min…max) | A velocity (min…max) |")
        print("|---|---|---|---|---|---|")
        for bar in sorted(bars):
            g = bars[bar]
            sh = [A[k]["start_ms"] for k in g]
            vs = [A[k]["vel"] for k in g if A[k]["vel"] is not None]
            label = sa.bar_labels[bar] if getattr(sa, "bar_labels", None) else bar + 1
            print(f"| {label} | {len(g)} | {median(A[k]['len_ms'] for k in g):.0f} | "
                  f"{median(B[k]['len_ms'] for k in g):.0f} | {min(sh):+.0f}…{max(sh):+.0f} | "
                  + (f"{min(vs)}…{max(vs)}" if vs else "–") + " |")
        print()
        if args.notes:
            print("| bar | beat | pitch | written | A marks | A passage | A ms | B marks | B ms | A vel |")
            print("|---|---|---|---|---|---|---|---|---|---|")
            for k in ks:
                a, b = A[k], B[k]
                print(f"| {a['bar'] + 1} | {a['beat']} | {pitch_name(k[2])} | {a['written_ms']:.0f} | "
                      f"{marks(a['note'])} | {'+'.join(a['passage']) or '–'} | {a['len_ms']:.0f} | "
                      f"{marks(b['note'])} | {b['len_ms']:.0f} | {a['vel'] if a['vel'] is not None else '–'} |")
            print()


if __name__ == "__main__":
    main()
