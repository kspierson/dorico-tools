"""Compare a "score" version of a piece with a "playback" version.

    python3 tools/compare_versions.py SCORE PLAYBACK [--flow-a N --flow-b N] [--examples K]

Each argument is a .dorico project, a Finale .musx/.mus file (read with finale2dorico's
`f2d ir`, which must be at ../finale2dorico), or a JSON file already produced by
`f2d ir` / `python3 -m doricohp.notation`. Without --flow-*, flows are paired by title,
then by order.

Per instrument (matched by name) it reports what changed in the performance markings:
the dynamic level in force at each note (in steps: p→mp = 1), dynamics and hairpins
added/removed, articulation changes on the same notes, and notes added/removed (to tell
re-orchestration from playback tweaks). Output is Markdown.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

LEVELS = ["pppppp", "ppppp", "pppp", "ppp", "pp", "p", "mp", "mf", "f", "ff", "fff", "ffff", "fffff", "ffffff"]
STEP = {k: i - LEVELS.index("mf") for i, k in enumerate(LEVELS)}   # mf = 0, mp = -1, f = +1
F2D = HERE.parent / "finale2dorico"


def F(x) -> Fraction:
    return Fraction(x) if not isinstance(x, Fraction) else x


# ---------------------------------------------------------------------------
# loading into one shape: {flows: [{title, bar_starts, staves: {name: staff}}]}
# staff = {chords: [(pos, dur, pitches, arts)], dynamics: [(pos, kind)], hairpins: [(pos, end, dir)], slurs: n}
# ---------------------------------------------------------------------------

def load(path: str) -> list[dict]:
    p = Path(path)
    if p.suffix == ".dorico":
        from doricohp import notation
        data = json.loads(notation.to_json(notation.read(str(p))))
        return [_from_dorico(f) for f in data["flows"]]
    if p.suffix in (".musx", ".mus"):
        out = subprocess.run([sys.executable, "-m", "f2d", "ir", str(p.resolve())], cwd=F2D,
                             capture_output=True, text=True, check=True).stdout
        data = json.loads(out)
    else:
        data = json.loads(p.read_text())
    if data["flows"] and "staves" in data["flows"][0] and isinstance(data["flows"][0]["staves"], list) \
            and data["flows"][0]["staves"] and "voices" in data["flows"][0]["staves"][0]:
        return _from_f2d(data)
    return [_from_dorico(f) for f in data["flows"]]


def _from_dorico(f: dict) -> dict:
    staves = {}
    for s in f["staves"]:
        staves[s["name"]] = {
            "chords": [(F(c["pos"]), F(c["dur"]), tuple(sorted(c["pitches"])), frozenset(c["articulations"]))
                       for c in s["chords"] if not c["grace"]],
            "dynamics": [(F(d["pos"]), d["kind"]) for d in s["dynamics"]],
            "hairpins": [(F(h["pos"]), F(h["end"]), h["direction"]) for h in s["hairpins"]],
            "slurs": len(s["slurs"]),
        }
    return {"title": f["title"], "bar_starts": [F(b) for b in f["bar_starts"]], "staves": staves}


def _from_f2d(data: dict) -> list[dict]:
    names = {}
    count = Counter(i["name"] for p in data["players"] for i in p["instruments"])
    seen = Counter()
    for p in data["players"]:
        for i in p["instruments"]:
            seen[i["name"]] += 1
            names[i["id"]] = i["name"] + (f" {seen[i['name']]}" if count[i["name"]] > 1 else "")
    flows = []
    for f in data["flows"]:
        staves: dict[str, dict] = {}
        for s in f["staves"]:
            name = names.get(s["instrument"], s["instrument"])
            st = staves.setdefault(name, {"chords": [], "dynamics": [], "hairpins": [], "slurs": 0})
            for v in s["voices"]:
                for c in v["chords"]:
                    if c["pitches"] and not c["grace"]:
                        st["chords"].append((F(c["pos"]), F(c["dur"]), tuple(sorted(x["midi"] for x in c["pitches"])),
                                             frozenset(c["articulations"])))
                st["slurs"] += len(v.get("slurs", []))
            st["dynamics"] += [(F(d["pos"]), d["kind"]) for d in s.get("dynamics", [])]
            st["hairpins"] += [(F(h["pos"]), F(h["end"]), h["direction"]) for h in s.get("hairpins", [])]
        for st in staves.values():
            st["chords"].sort(key=lambda c: (c[0], c[2]))
            st["dynamics"].sort()
            st["hairpins"].sort()
        flows.append({"title": f.get("title", ""), "bar_starts": [F(b) for b in f["bar_starts"]], "staves": staves})
    return flows


# ---------------------------------------------------------------------------

def where(bar_starts, pos) -> str:
    bar = 0
    for i, s in enumerate(bar_starts):
        if s <= pos:
            bar = i
        else:
            break
    off = pos - bar_starts[bar] if bar_starts else pos
    whole, rest = int(off), off - int(off)
    return f"b{bar + 1}:{whole + 1}" + (f"+{rest}" if rest else "")


def level_at(dynamics, pos):
    lv = None
    for p, k in dynamics:
        if p > pos:
            break
        if k in STEP:
            lv = STEP[k]
    return lv


def compare_staff(a, b, bars, examples):
    out = {}
    ka = {(c[0], c[2]): c for c in a["chords"]}
    kb = {(c[0], c[2]): c for c in b["chords"]}
    matched = [k for k in ka if k in kb]
    out["notes"] = (len(ka), len(kb), len(matched))
    # dynamic level at each matched note
    shifts = []
    for k in matched:
        la, lb = level_at(a["dynamics"], k[0]), level_at(b["dynamics"], k[0])
        if la is not None and lb is not None:
            shifts.append(lb - la)
    out["shifts"] = shifts
    da, db = set(a["dynamics"]), set(b["dynamics"])
    out["dyn_added"] = sorted(db - da)
    out["dyn_removed"] = sorted(da - db)
    ha, hb = set(a["hairpins"]), set(b["hairpins"])
    out["hp_added"] = sorted(hb - ha)
    out["hp_removed"] = sorted(ha - hb)
    trans = Counter()
    for k in matched:
        x, y = ka[k][3], kb[k][3]
        if x != y:
            trans[("+".join(sorted(x)) or "–", "+".join(sorted(y)) or "–")] += 1
    out["arts"] = trans
    out["slurs"] = (a["slurs"], b["slurs"])
    return out


def report(A, B, la, lb, flow_pairs, examples) -> str:
    lines = [f"# {Path(la).name} → {Path(lb).name}", ""]
    total_trans = Counter()
    total_shift = []
    hp_total = [0, 0]
    for fa, fb in flow_pairs:
        a, b = A[fa], B[fb]
        bars = b["bar_starts"]
        lines.append(f"## Flow: {a['title']!r} → {b['title']!r}\n")
        common = [n for n in a["staves"] if n in b["staves"]]
        only_a = [n for n in a["staves"] if n not in b["staves"]]
        only_b = [n for n in b["staves"] if n not in a["staves"]]
        if only_a:
            lines.append(f"Only in score version: {', '.join(only_a)}  ")
        if only_b:
            lines.append(f"Only in playback version: {', '.join(only_b)}  ")
        lines.append("")
        lines.append("| instrument | notes a/b/same | level shift (mean, range) | notes louder/softer | dyn +/− | hairpins +/− | slurs a/b | top articulation changes |")
        lines.append("|---|---|---|---|---|---|---|---|")
        details = []
        for n in common:
            r = compare_staff(a["staves"][n], b["staves"][n], bars, examples)
            sh = r["shifts"]
            total_shift += sh
            hp_total[0] += len(r["hp_added"]); hp_total[1] += len(r["hp_removed"])
            total_trans.update(r["arts"])
            if not (r["dyn_added"] or r["dyn_removed"] or r["hp_added"] or r["hp_removed"] or r["arts"]
                    or r["notes"][0] != r["notes"][2] or r["notes"][1] != r["notes"][2]):
                continue
            ms = f"{mean(sh):+.2f} ({min(sh):+d}…{max(sh):+d})" if sh else "–"
            lo = f"{sum(1 for s in sh if s > 0)}/{sum(1 for s in sh if s < 0)} of {len(sh)}" if sh else "–"
            top = "; ".join(f"{x}→{y} ×{c}" for (x, y), c in r["arts"].most_common(3))
            lines.append(f"| {n} | {r['notes'][0]}/{r['notes'][1]}/{r['notes'][2]} | {ms} | {lo} | "
                         f"{len(r['dyn_added'])}/{len(r['dyn_removed'])} | {len(r['hp_added'])}/{len(r['hp_removed'])} | "
                         f"{r['slurs'][0]}/{r['slurs'][1]} | {top} |")
            ex = []
            for p, k in r["dyn_added"][:examples]:
                ex.append(f"+{k} {where(bars, p)}")
            for p, k in r["dyn_removed"][:examples]:
                ex.append(f"−{k} {where(bars, p)}")
            for p, e, d in r["hp_added"][:examples]:
                ex.append(f"+{d} {where(bars, p)}–{where(bars, e)}")
            if ex:
                details.append(f"- **{n}**: " + ", ".join(ex))
        if details:
            lines.append("\nExamples (playback version, bar:beat):\n")
            lines += details
        lines.append("")
    lines.append("## Totals over common instruments\n")
    if total_shift:
        c = Counter(total_shift)
        lines.append(f"Dynamic level at matched notes: mean {mean(total_shift):+.2f} steps; "
                     + ", ".join(f"{k:+d}: {c[k]}" for k in sorted(c)) + "  ")
    lines.append(f"Hairpins added {hp_total[0]}, removed {hp_total[1]}  ")
    lines.append("\nArticulation changes (score → playback):\n")
    for (x, y), c in total_trans.most_common(20):
        lines.append(f"- {x} → {y}: {c}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("score")
    ap.add_argument("playback")
    ap.add_argument("--flow-a", type=int, action="append")
    ap.add_argument("--flow-b", type=int, action="append")
    ap.add_argument("--examples", type=int, default=4)
    args = ap.parse_args()
    A, B = load(args.score), load(args.playback)
    if args.flow_a or args.flow_b:
        pairs = list(zip(args.flow_a or [0], args.flow_b or [0]))
    else:
        tb = {f["title"]: i for i, f in enumerate(B)}
        pairs = [(i, tb.get(f["title"], i)) for i, f in enumerate(A) if tb.get(f["title"], i) < len(B)]
    print(report(A, B, args.score, args.playback, pairs, args.examples))


if __name__ == "__main__":
    main()
