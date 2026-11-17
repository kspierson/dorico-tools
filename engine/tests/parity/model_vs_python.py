"""S4 safety check: the Rust read model (doricokit.model) vs the two Python readers it replaces,
finale2dorico's old reviewer reader and dorico-hp's old notation.py, on every project in the
corpus. Both tools now read through the model; their old readers are kept as test oracles in
engine/tests/oracles/ (f2d_read_py.py, hp_notation_py.py).

    PYTHONDONTWRITEBYTECODE=1 uv run python engine/tests/parity/model_vs_python.py [--limit N] [-v]

Each old reader's output is reduced to comparable facts (bars, notes, dynamics, techniques,
slurs, trills, tempos, chords) and compared with the same facts from the new model. Differences
are counted per category with a few examples, so each one can be explained (old-reader bug,
new-model bug, or a deliberate difference).
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from doricokit import model, paths  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "finale2dorico"))
sys.path.insert(0, str(ROOT / "dorico-hp"))
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("f2d_read_py", ROOT / "engine/tests/oracles/f2d_read_py.py")
f2d_read = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(f2d_read)
_spec = importlib.util.spec_from_file_location("hp_notation_py", ROOT / "engine/tests/oracles/hp_notation_py.py")
hp_notation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hp_notation)

DIFFS: Counter = Counter()
EXAMPLES: dict[str, list[str]] = defaultdict(list)
VERBOSE = "-v" in sys.argv


ALL: dict[str, list[str]] = defaultdict(list)


def diff(cat: str, where: str, a, b) -> None:
    DIFFS[cat] += 1
    ALL[cat].append(where)
    if len(EXAMPLES[cat]) < (20 if VERBOSE else 3):
        sa, sb = str(a), str(b)
        EXAMPLES[cat].append(f"{where}: old={sa[:300]} new={sb[:300]}")


def compare_sets(cat: str, where: str, old: list, new: list) -> None:
    so, sn = Counter(old), Counter(new)
    if so != sn:
        only_old = list((so - sn).elements())[:4]
        only_new = list((sn - so).elements())[:4]
        diff(cat, f"{where} ({sum((so - sn).values())} only old, {sum((sn - so).values())} only new)",
             sorted(only_old, key=str), sorted(only_new, key=str))


def end_or_pos(m) -> Fraction:
    return m["end"] if m["end"] is not None else m["pos"]


# --- vs f2d read.py --------------------------------------------------------------------

def vs_f2d(path: Path, new: dict) -> None:
    old = f2d_read.read_project(path)
    for fi, (of, nf) in enumerate(zip(old.flows, new["flows"])):
        w = f"{path.name} flow {fi + 1}"
        ob = [(s, l, n, d) for s, l, n, d in of.bars]
        nb = [(b["start"], b["length"], b["num"], b["den"]) for b in nf["bars"]]
        if ob != nb:
            k = next((i for i, (x, y) in enumerate(zip(ob, nb)) if x != y), min(len(ob), len(nb)))
            diff("f2d/bars", w, f"{len(ob)} bars, first diff #{k + 1}: {ob[k:k + 2]}",
                 f"{len(nb)} bars: {nb[k:k + 2]}")
        # staves keyed by (player name, entity, stave index, occurrence). read.py merges staves
        # that share an index (divisi staves are all index 0), so merge them here too.
        new_staves = {}
        seen = Counter()
        for p in nf["parts"]:
            pk = (p["player_name"], p["entity"])
            seen[pk] += 1
            for st in p["staves"]:
                key = pk + (st["index"], seen[pk])
                if key in new_staves:
                    new_staves[key][1]["dynamics"] = new_staves[key][1]["dynamics"] + st["dynamics"]
                else:
                    new_staves[key] = (p, dict(st))
        seen = Counter()
        for s in of.staves:
            key = (s.player, s.instrument, s.index)
            seen[key] += 1
            hit = new_staves.get(key + (seen[key],))
            sw = f"{w} {s.label}"
            if hit is None:
                diff("f2d/staff missing", sw, key, "-")
                continue
            p, st = hit
            voices = [v for v in p["voices"] if v["stave_index"] == st["index"]]
            compare_sets("f2d/notes", sw, [(n.pos, n.dur, n.pitch, n.grace) for v in s.voices for n in v],
                         [(n["pos"], n["dur"], n["pitch"], n["grace"]) for v in voices for n in v["notes"]])
            compare_sets("f2d/dynamics", sw,
                         [(g.pos, g.element, g.linked, tuple((i.pos, i.kind, _combined(i.level), i.end) for i in g.items))
                          for g in s.dynamics],
                         [(g["pos"], g["element_id"], g["linked"],
                           tuple((i["pos"], i["kind"], i["level"] + (i["extra"] if i["kind"] == "force" else ""),
                                  i["end"]) for i in g["items"]))
                          for g in st["dynamics"]])
            marks = [m for v in voices for m in v["marks"]]
            compare_sets("f2d/techniques", sw, s.techniques,
                         [(m["pos"], m["detail"].get("appearance", "")) for m in marks if m["kind"] == "technique"])
            compare_sets("f2d/trills", sw, s.trills, [(m["pos"], end_or_pos(m)) for m in marks if m["kind"] == "trill"])
            compare_sets("f2d/slurs", sw, s.slurs, [(m["pos"], end_or_pos(m)) for m in marks if m["kind"] == "slur"])


def _combined(level: str) -> str:
    """The old reader named only fp/ffp/fpp/pf and left other combined dynamics raw
    ("kDown2/0"); since 2026-10-31 the model names them all through dorico-format::dynamics
    ("ff-mp", 0 letters = mezzo). Translate the raw form so only other differences remain."""
    m = re.fullmatch(r"k(Down|Up)(\d+)/(\d+)", level)
    if not m:
        return level
    def part(n, loud):
        n = int(n)
        return ("mf" if loud else "mp") if n == 0 else ("f" if loud else "p") * n
    a, b = (part(m[2], True), part(m[3], False)) if m[1] == "Down" else (part(m[2], False), part(m[3], True))
    return f"{a}-{b}" if a.startswith("m") or b.startswith("m") else a + b


# --- vs dorico-hp notation.py ----------------------------------------------------------

def vs_hp(path: Path, new: dict) -> None:
    old = hp_notation.read(str(path))
    for fi, (of, nf) in enumerate(zip(old, new["flows"])):
        w = f"{path.name} flow {fi + 1}"
        ob, nb = of.bar_starts, [b["start"] for b in nf["bars"]]
        common = min(len(ob), len(nb))
        if ob[:common] != nb[:common]:
            k = next(i for i in range(common) if ob[i] != nb[i])
            diff("hp/bar starts", w, f"#{k + 1}: {ob[k:k + 3]}", nb[k:k + 3])
        elif len(ob) != len(nb):
            diff("hp/bar count (end of flow)", w, len(ob), len(nb))
        compare_sets("hp/tempos", w,
                     [(t["pos"], t.get("bpm"), t.get("gradual", False), t.get("end"), t.get("text") or "")
                      for t in of.tempos],
                     [(t["pos"], t["bpm"], t["gradual"], t["end"], t["text"]) for t in nf["tempos"]])
        parts = []
        for p in nf["parts"]:
            name = p["player_name"] + (f" #{p['number']}" if p["of"] > 1 else "")
            parts.append((name, p))
        for os_, (name, p) in zip(of.staves, parts):
            sw = f"{w} {os_.name}"
            if os_.name != name or os_.instrument != p["instrument_id"]:
                diff("hp/part order", sw, (os_.name, os_.instrument), (name, p["instrument_id"]))
                continue
            new_chords = []
            for v in p["voices"]:
                groups = defaultdict(list)
                for n in v["notes"]:
                    groups[(n["pos"], n["grace"])].append(n)
                for (pos, grace), ns in groups.items():
                    arts = []
                    for n in ns:
                        for a in n["articulations"]:
                            if a not in arts:
                                arts.append(a)
                    new_chords.append((pos, ns[0]["dur"], tuple(sorted(n["pitch"] for n in ns)), tuple(sorted(arts)),
                                       grace, int(any(n["tremolo"] for n in ns))))
            compare_sets("hp/chords", sw,
                         [(c.pos, c.dur, tuple(sorted(c.pitches)), tuple(sorted(c.articulations)), c.grace, c.tremolo)
                          for c in os_.chords], new_chords)
            dyn_new, hp_new = [], []
            for st in p["staves"]:
                for g in st["dynamics"]:
                    for i in g["items"]:
                        if i["kind"] in ("dynamic", "force"):
                            dyn_new.append((i["pos"], i["level"]))
                        elif i["kind"] == "hairpin":
                            hp_new.append((i["pos"], i["end"], i["level"]))
            compare_sets("hp/dynamics", sw, [(d["pos"], d["kind"]) for d in os_.dynamics], dyn_new)
            compare_sets("hp/hairpins", sw, [(h["pos"], h["end"], h["direction"]) for h in os_.hairpins], hp_new)
            vmarks = [m for v in p["voices"] for m in v["marks"]]
            smarks = [m for st in p["staves"] for m in st["marks"]]
            compare_sets("hp/slurs", sw, [(s["pos"], s["end"]) for s in os_.slurs],
                         [(m["pos"], end_or_pos(m)) for m in vmarks if m["kind"] == "slur"])
            compare_sets("hp/techniques", sw, [(t["pos"], t["id"], t["text"], t["technique"]) for t in os_.techniques],
                         [(m["pos"], m["detail"].get("appearance", ""), m["detail"].get("text", ""),
                           m["detail"].get("technique", "")) for m in vmarks + smarks if m["kind"] == "technique"])
            compare_sets("hp/texts (best effort)", sw, [(t["pos"], t["text"]) for t in os_.texts],
                         [(m["pos"], m["detail"]["text"]) for m in vmarks + smarks if m["detail"].get("text")
                          and m["kind"] != "technique"])


# Differences that were investigated and are deliberate (category, file, reason). See
# engine/docs/STATUS.md "S4 parity findings". Anything not listed here fails the check.
EXPLAINED = [
    ("f2d/bars", "all i want 2.dorico", "read.py doesn't start a new bar at a mid-bar time signature; Dorico does"),
    ("hp/bar starts", "brass test.dorico", "notation.py ignores the pick-up bar (irregularBarLength)"),
    ("hp/bar count (end of flow)", "", "notation.py stops at the last event; Dorico keeps minimumNotatedLength"),
    ("f2d/dynamics", "ET The Flying Theme", "read.py decodes only 1-6 p/f; 7-8 (e.g. {int: 7}) and the undecoded value fall back to raw text"),
    ("hp/dynamics", "", "intensity {int: 0}, {int: 1}, {bool: false}, {} is undecoded: old '?', new keeps raw value"),
    ("hp/texts (best effort)", "", "notation.py misses rich-text `content` fragments of Text events"),
]


def explained(cat: str, example: str) -> bool:
    return any(cat == c and f in example for c, f, _ in EXPLAINED)


def main() -> int:
    c = paths.corpus()
    files = sorted(c["projects"].glob("*.dorico")) + sorted(c["test_files"].glob("*.dorico"))
    if "--limit" in sys.argv:
        files = files[: int(sys.argv[sys.argv.index("--limit") + 1])]
    for f in files:
        new = model.read(f)
        for fn in (vs_f2d, vs_hp):
            try:
                fn(f, new)
            except Exception as e:  # noqa: BLE001 - an old reader crashing is a finding too
                diff(f"{fn.__name__} crashed", f.name, repr(e)[:200], "-")
    print(f"compared {len(files)} projects")
    bad = 0
    for cat in sorted(DIFFS):
        ok = all(explained(cat, e) for e in ALL[cat])
        bad += 0 if ok else 1
        why = next((r for c, f, r in EXPLAINED if c == cat), "") if ok else "UNEXPLAINED"
        print(f"\n{cat}: {DIFFS[cat]} differences ({why})")
        for e in EXAMPLES[cat]:
            print("   ", e)
    print("\nno unexplained differences" if not bad else f"\n{bad} categories with unexplained differences")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
