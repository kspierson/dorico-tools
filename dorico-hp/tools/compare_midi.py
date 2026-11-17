"""Compare two MIDI renderings of the same piece, track by track.

    python3 tools/compare_midi.py A.mid B.mid [--tol TICKS]

Tracks are paired by name; notes by pitch and the nearest start within --tol ticks
(default 128 = 1/8 crotchet at 1024 ppq), since HP moves onsets by a few ticks. Prints per
track: notes, matched, velocity change (B − A), length ratio, and the dynamics controller
range in each file (CC1/7/11, whichever the track uses most).
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from doricohp import smf  # noqa: E402


def dyn_cc(m, track):
    c = Counter(x.number for x in m.ctrls if x.kind == "cc" and x.track == track and x.number in (1, 7, 11))
    if not c:
        return "–"
    num = c.most_common(1)[0][0]
    vals = [x.value for x in m.ctrls if x.kind == "cc" and x.track == track and x.number == num]
    return f"CC{num} {min(vals)}–{max(vals)} (mean {st.mean(vals):.0f})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--tol", type=int, default=128)
    args = ap.parse_args()
    a, b = smf.read(args.a), smf.read(args.b)
    na = {v: k for k, v in a.track_names.items()}
    nb = {v: k for k, v in b.track_names.items()}
    print(f"# {Path(args.a).name} → {Path(args.b).name}\n")
    print(f"Only in A: {', '.join(n for n in na if n not in nb) or '–'}  ")
    print(f"Only in B: {', '.join(n for n in nb if n not in na) or '–'}\n")
    print("| track | notes A/B/matched | velocity A→B (mean change, sd) | length B/A | dynamics CC A | dynamics CC B |")
    print("|---|---|---|---|---|---|")
    for name, ta in na.items():
        if name not in nb:
            continue
        A = [n for n in a.notes if n.track == ta]
        pool = defaultdict(list)
        for n in b.notes:
            if n.track == nb[name]:
                pool[n.pitch].append(n)
        pairs = []
        for x in A:
            y = min(pool[x.pitch], key=lambda y: abs(y.start - x.start), default=None)
            if y is not None and abs(y.start - x.start) <= args.tol:
                pairs.append((x, y))
        if not A:
            continue
        dv = [y.velocity - x.velocity for x, y in pairs]
        dl = [(y.end - y.start) / (x.end - x.start) for x, y in pairs if x.end > x.start]
        vel = (f"{st.mean(x.velocity for x, _ in pairs):.0f}→{st.mean(y.velocity for _, y in pairs):.0f} "
               f"({st.mean(dv):+.1f}, sd {st.pstdev(dv):.1f})") if pairs else "–"
        print(f"| {name} | {len(A)}/{sum(len(v) for v in pool.values())}/{len(pairs)} | {vel} | "
              f"{st.mean(dl):.2f} | {dyn_cc(a, ta)} | {dyn_cc(b, nb[name])} |" if dl else
              f"| {name} | {len(A)}/{sum(len(v) for v in pool.values())}/{len(pairs)} | {vel} | – | {dyn_cc(a, ta)} | {dyn_cc(b, nb[name])} |")


if __name__ == "__main__":
    main()
