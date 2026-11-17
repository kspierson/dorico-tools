"""Where do hairpins added for playback sit in the music?

    python3 tools/swell_context.py SCORE PLAYBACK [--flow-a N --flow-b N]

Inputs as for compare_versions.py. A hairpin in the playback version counts as "added"
when the score version has no hairpin of the same direction starting within 1/2 crotchet.
Each added hairpin is classified by what the music does under it (per instrument):

  on held note   - lies within one sounding note (swell/fade on a sustained note)
  into arrival   - crescendo ending at a note onset on a beat, onto a longer or higher note
  to phrase end  - diminuendo ending at (or just before) a rest / the end of a slur
  arch           - a crescendo immediately followed by a diminuendo (< >)
  with contour   - crescendo while the line rises / diminuendo while it falls
  against contour- the opposite
  in slur        - starts and ends inside one slur

plus its length in crotchets, and whether it starts at a slur start or a note after a rest.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_versions import load, where  # noqa: E402

HALF = Fraction(1, 2)


def slurs_of(staff):
    return staff.get("slur_spans", [])


def classify(st, h, all_h):
    pos, end, d = h
    chords = st["chords"]
    out = set()
    sounding = [c for c in chords if c[0] <= pos + Fraction(1, 8) and c[0] + c[1] >= end - Fraction(1, 8)]
    if sounding and end - pos > 0:
        out.add("on held note")
    under = [c for c in chords if pos - Fraction(1, 8) <= c[0] < end]
    after = [c for c in chords if c[0] >= end - Fraction(1, 8)]
    nxt = after[0] if after else None
    if d == "cresc" and nxt is not None and abs(nxt[0] - end) <= Fraction(1, 4) and nxt[0].denominator == 1:
        prev_len = max((c[1] for c in under), default=0)
        if nxt[1] >= prev_len or (under and max(nxt[2]) > max(max(c[2]) for c in under)):
            out.add("into arrival")
    if d == "dim":
        last = under[-1] if under else None
        if nxt is None or (last is not None and last[0] + last[1] < nxt[0]) or (nxt and nxt[0] - end > HALF):
            out.add("to phrase end")
    for (p2, e2, d2) in all_h:
        if d == "cresc" and d2 == "dim" and abs(p2 - end) <= Fraction(1, 4):
            out.add("arch")
        if d == "dim" and d2 == "cresc" and abs(e2 - pos) <= Fraction(1, 4):
            out.add("arch")
    if len(under) >= 2:
        first, last = max(under[0][2]), max(under[-1][2])
        rising = last > first
        falling = last < first
        if (d == "cresc" and rising) or (d == "dim" and falling):
            out.add("with contour")
        elif (d == "cresc" and falling) or (d == "dim" and rising):
            out.add("against contour")
    for s, e in st.get("slur_spans", []):
        if s - Fraction(1, 8) <= pos and end <= e + Fraction(1, 4):
            out.add("in slur")
            break
    starts = []
    if any(abs(s - pos) <= Fraction(1, 4) for s, _ in st.get("slur_spans", [])):
        starts.append("at slur start")
    prevs = [c for c in chords if c[0] < pos - Fraction(1, 8)]
    if under and (not prevs or prevs[-1][0] + prevs[-1][1] < under[0][0]):
        starts.append("after rest")
    return out, starts


def attach_slurs(flows, path):
    """compare_versions.load keeps only slur counts; re-read spans here."""
    import json
    import subprocess
    p = Path(path)
    if p.suffix == ".dorico":
        from doricohp import notation
        data = json.loads(notation.to_json(notation.read(str(p))))
        for f, fl in zip(data["flows"], flows):
            for s in f["staves"]:
                if s["name"] in fl["staves"]:
                    fl["staves"][s["name"]]["slur_spans"] = [(Fraction(x["pos"]), Fraction(x["end"])) for x in s["slurs"]]
        return
    data = json.loads(Path(path).read_text()) if p.suffix == ".json" else None
    if data is None:
        return
    names = {}
    from collections import Counter as C
    count = C(i["name"] for pl in data["players"] for i in pl["instruments"])
    seen = C()
    for pl in data["players"]:
        for i in pl["instruments"]:
            seen[i["name"]] += 1
            names[i["id"]] = i["name"] + (f" {seen[i['name']]}" if count[i["name"]] > 1 else "")
    for f, fl in zip(data["flows"], flows):
        for s in f["staves"]:
            n = names.get(s["instrument"], s["instrument"])
            if n in fl["staves"]:
                fl["staves"][n].setdefault("slur_spans", [])
                for v in s["voices"]:
                    fl["staves"][n]["slur_spans"] += [(Fraction(x["pos"]), Fraction(x["end"])) for x in v.get("slurs", [])]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("score")
    ap.add_argument("playback")
    ap.add_argument("--flow-a", type=int, default=0)
    ap.add_argument("--flow-b", type=int, default=0)
    ap.add_argument("--list", action="store_true", help="print every added hairpin")
    args = ap.parse_args()
    A, B = load(args.score), load(args.playback)
    attach_slurs(B, args.playback)
    a, b = A[args.flow_a], B[args.flow_b]
    kinds, starts, lengths, n = Counter(), Counter(), Counter(), Counter()
    rows = []
    for name, st in b["staves"].items():
        if name not in a["staves"]:
            continue
        old = a["staves"][name]["hairpins"]
        for h in st["hairpins"]:
            if any(o[2] == h[2] and abs(o[0] - h[0]) <= HALF for o in old):
                continue
            n[h[2]] += 1
            k, s = classify(st, h, st["hairpins"])
            for x in k or {"(none)"}:
                kinds[(h[2], x)] += 1
            for x in s:
                starts[(h[2], x)] += 1
            L = h[1] - h[0]
            lengths[(h[2], "≤1" if L <= 1 else "≤2" if L <= 2 else "≤4" if L <= 4 else ">4")] += 1
            rows.append(f"{name}: {h[2]} {where(b['bar_starts'], h[0])}–{where(b['bar_starts'], h[1])} "
                        f"({float(L):.2g} crotchets) {', '.join(sorted(k)) or '-'}")
    print(f"# Added hairpins: {Path(args.score).name} → {Path(args.playback).name}\n")
    print(f"cresc {n['cresc']}, dim {n['dim']}\n")
    print("| context | cresc | dim |\n|---|---|---|")
    for x in ["on held note", "into arrival", "to phrase end", "arch", "with contour", "against contour", "in slur", "(none)"]:
        print(f"| {x} | {kinds[('cresc', x)]} | {kinds[('dim', x)]} |")
    print("\n| starts | cresc | dim |\n|---|---|---|")
    for x in ["at slur start", "after rest"]:
        print(f"| {x} | {starts[('cresc', x)]} | {starts[('dim', x)]} |")
    print("\n| length (crotchets) | cresc | dim |\n|---|---|---|")
    for x in ["≤1", "≤2", "≤4", ">4"]:
        print(f"| {x} | {lengths[('cresc', x)]} | {lengths[('dim', x)]} |")
    if args.list:
        print("\n" + "\n".join(f"- {r}" for r in rows))


if __name__ == "__main__":
    main()
