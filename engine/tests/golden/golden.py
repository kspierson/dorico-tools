"""Golden outputs for Project S: record what the tools produce today, then check that
moving code into the engine changes nothing.

    python3 engine/tests/golden/golden.py record [--only PREFIX] [--fast]
    python3 engine/tests/golden/golden.py check  [--only PREFIX] [--fast]

`record` writes engine/tests/golden/manifest.json (hashes, committed) and the full outputs
under engine/tests/golden/out/ (git-ignored; useful for diffing when a check fails).
`check` re-runs every case into a temporary folder and compares hashes.

Hashes:
- text and binary outputs: sha256 of the bytes.
- .dorico outputs: sha256 of the whole file *and* of every zip entry (name, contents,
  timestamp, stored/deflated). A different zip writer may compress differently, so the
  check passes when every entry matches even if the raw zip bytes differ (it says so).

Cases need the user's corpora (engine/tests/corpus.toml). Cases whose inputs are missing
are skipped, not failed. f2d changes daily, so its cases are re-recorded right before each move
that touches it (`record --only f2d/`, PLANNED_WORK.md §2.12). f2d writes the current time into
its scores, so its .dorico outputs are compared as decoded trees with the dates masked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "manifest.json"
OUT = HERE / "out"


def corpus() -> dict[str, Path]:
    """Corpus paths from corpus.toml, with DORICO_<NAME> env overrides."""
    data = tomllib.loads((ROOT / "engine/tests/corpus.toml").read_text())
    out = {}
    for k, v in data["corpus"].items():
        if isinstance(v, str):
            v = os.environ.get(f"DORICO_{k.upper()}", v)
            p = Path(v)
            out[k] = p if p.is_absolute() else ROOT / p
    for k, v in data["corpus"].get("projects_used", {}).items():
        out[k] = out["projects"] / v
    return out


def test_files_dir(c: dict[str, Path]) -> Path:
    """The shared Dorico test files A–H (engine/tests/dorico-files)."""
    return c["test_files"]


def dorigit_bin() -> Path | None:
    for p in (os.environ.get("DORIGIT_BIN"), ROOT / "target/release/dorigit",
              ROOT / "dorigit/target/release/dorigit"):
        if p and Path(p).is_file():
            return Path(p)
    return None


@dataclass
class Case:
    name: str
    cmd: list[str]
    cwd: Path
    outputs: list[str]          # file names inside the case's output dir; "stdout" = captured stdout
    inputs: list[Path] = field(default_factory=list)
    slow: bool = False
    env: dict[str, str] = field(default_factory=dict)
    tree: bool = False          # compare .dorico outputs as decoded trees, dates masked


def cases() -> list[Case]:
    c = corpus()
    out: list[Case] = []
    hp = ROOT / "dorico-hp"
    py = sys.executable

    # --- dorigit: musical listing of every project (exercises codec + model) -------------
    exe = dorigit_bin()
    files = sorted(c["projects"].glob("*.dorico")) if c["projects"].is_dir() else []
    files += sorted(test_files_dir(c).glob("*.dorico"))
    for f in files:
        out.append(Case(f"dorigit/show/{f.stem}", [str(exe or "dorigit"), "show", str(f)], ROOT,
                        ["stdout"], [f] + ([exe] if exe else [Path("/nonexistent/dorigit")])))

    # --- dorico-hp: Apply (edit layer), playback inspector, MIDI render ------------------
    main = c["hp_main"]
    out.append(Case("dorico-hp/apply/romantic",
                    [py, "-m", "doricohp.apply", str(main), "{out}/out.dorico", "--style", "Romantic"],
                    hp, ["stdout", "out.dorico", "out.dorico.hp-apply.json"], [main], slow=True))
    # re-apply on top of our own output must undo and redo cleanly (idempotent)
    out.append(Case("dorico-hp/apply/reapply",
                    ["sh", "-c", f'"{py}" -m doricohp.apply "{main}" "{{out}}/a.dorico" --style Romantic >/dev/null'
                     f' && "{py}" -m doricohp.apply "{{out}}/a.dorico" "{{out}}/b.dorico" --style Romantic'],
                    hp, ["stdout", "b.dorico"], [main], slow=True))
    for only in ("velocity", "timing", "vibrato"):
        out.append(Case(f"dorico-hp/apply/only-{only}",
                        [py, "-m", "doricohp.apply", str(main), "{out}/out.dorico", "--only", only, "--style",
                         "Standard"], hp, ["stdout", "out.dorico"], [main], slow=True))
    tf = test_files_dir(c)
    for f in sorted(tf.glob("*A-rebuilt.dorico")):
        out.append(Case("dorico-hp/apply/test-file-A",
                        [py, "-m", "doricohp.apply", str(f), "{out}/out.dorico", "--style", "Standard"],
                        hp, ["stdout", "out.dorico", "out.dorico.hp-apply.json"], [f]))
    out.append(Case("dorico-hp/playback/main", [py, "-m", "doricohp.playback", str(main)], hp, ["stdout"], [main]))
    out.append(Case("dorico-hp/render/main",
                    [py, "-m", "doricohp.render", str(main), "{out}/out.mid", "--style", "Standard"],
                    hp, ["stdout", "out.mid"], [main], slow=True))
    for f in sorted(tf.glob("*.dorico")):
        out.append(Case(f"dorico-hp/render/{f.stem}",
                        [py, "-m", "doricohp.render", str(f), "{out}/out.mid", "--style", "Standard"],
                        hp, ["out.mid"], [f]))

    # --- finale2dorico: convert, review, dump, ir ----------------------------------------
    # f2d writes the current time into the score and iterates some sets, so its cases fix
    # the hash seed and compare decoded scores with the dates masked (tree=True).
    f2d = ROOT / "finale2dorico"
    fenv = {"PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}
    hpf = c["hp_captures"] / "finale/scores"
    film = Path("/mnt/d/SCORES+BOOKS/Film Scores/John Williams")
    sources = {n: hpf / f"{n}.musx" for n in ("Willow", "Trex", "VV_Full", "Venus", "WW")}
    slow_sources = {
        "JW Raiders March": film / "Indiana Jones and the Raiders of the Lost Ark/Concert Scores/"
                                   "John Williams - Raider's March.mus",
        "JW ET Adventures On Earth": film / "E.T. The Extra Terrestrial/Concert Scores/"
                                            "John Williams - E.T. - Adventures On Earth.mus",
        "JW Asteroid Field": c["finale_scores"] / "John Williams - Empire Strikes Back - The Asteroid Field.musx",
    }
    for n, src in [*sources.items(), *slow_sources.items()]:
        # convert, then review our own output (the reviewer's main use)
        out.append(Case(f"f2d/convert/{n}",
                        ["sh", "-c", f'"{py}" -m f2d convert "{src}" -o "{{out}}/out.dorico" --report'
                         f' && "{py}" -m f2d review "{{out}}/out.dorico" --all --json "{{out}}/review.json"'],
                        f2d, ["stdout", "out.dorico", "out.f2d-report.json", "review.json"], [src],
                        slow=n in slow_sources, env=fenv, tree=True))
    willow = sources["Willow"]
    out.append(Case("f2d/convert-dtn/Willow",
                    [py, "-m", "f2d", "convert", str(willow), "-o", "{out}/out.dorico", "--dtn"],
                    f2d, ["stdout", "out.dorico"], [willow], env=fenv, tree=True))
    out.append(Case("f2d/convert-bootstrap/Willow",
                    [py, "-m", "f2d", "convert", str(willow), "-o", "{out}/out.dorico", "--reader", "bootstrap"],
                    f2d, ["stdout", "out.dorico"], [willow], env=fenv, tree=True))
    out.append(Case("f2d/ir/Willow", [py, "-m", "f2d", "ir", str(willow)], f2d, ["stdout"], [willow], env=fenv))
    for i, f in enumerate(files):
        out.append(Case(f"f2d/review/{f.stem}",
                        [py, "-m", "f2d", "review", str(f), "--all", "--json", "{out}/review.json"],
                        f2d, ["stdout", "review.json"], [f], slow=i % 4 != 0, env=fenv))
    for f in [c["hp_main"], *sorted(tf.glob("*A-rebuilt.dorico")), *sorted(tf.glob("*B-xml-inside.dorico"))]:
        out.append(Case(f"f2d/dump/{f.stem}", [py, "-m", "f2d", "dump", str(f)], f2d, ["stdout"], [f], env=fenv))
    return out


_ORACLE = None


def oracle():
    """The old pure-Python DTN codec (engine/tests/oracles/dtn_py.py), independent of the code
    under test, used to compare score trees rather than bytes."""
    global _ORACLE
    if _ORACLE is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("dtn_oracle", ROOT / "engine/tests/oracles/dtn_py.py")
        _ORACLE = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_ORACLE)
    return _ORACLE


def tree_text(name: str, data: bytes) -> bytes:
    """A score entry as XML with createdDate/lastSavedDate masked."""
    import re
    o = oracle()
    if name.endswith(".dtn"):
        text = o.to_xml(o.decode(data), with_marker=False)
    elif name.endswith(".xml") and b"<kScore" in data[:400] and name != "supplementary_data/scoreinfo/scoreinfo.xml":
        text = o.to_xml(o.from_xml(data), with_marker=False)
    else:
        return data
    return re.sub(r"<(createdDate|lastSavedDate)>\d*</", r"<\1>MASKED</", text).encode("utf-8")


def entry_hashes(path: Path, tree: bool = False) -> dict[str, str]:
    """Per-entry hashes. tree=True: score entries are hashed as decoded XML with dates masked,
    and zip timestamps are left out (for tools that write the current time)."""
    out = {}
    with zipfile.ZipFile(path) as z:
        for i, info in enumerate(z.infolist()):
            data = z.read(info) if not info.is_dir() else b""
            if tree:
                data = tree_text(info.filename, data)
            h = hashlib.sha256(data).hexdigest()
            kind = "stored" if info.compress_type == zipfile.ZIP_STORED else "deflated"
            date = "" if tree else " " + "-".join(map(str, info.date_time))
            out[f"{i:03d} {info.filename}"] = f"{h} {kind}{date}"
    return out


def run(case: Case, od: Path) -> dict:
    od.mkdir(parents=True, exist_ok=True)
    cmd = [a.replace("{out}", str(od)) for a in case.cmd]
    t = time.time()
    p = subprocess.run(cmd, cwd=case.cwd, capture_output=True, env={**os.environ, **case.env})
    res: dict = {"exit": p.returncode, "seconds": round(time.time() - t, 1), "files": {}}
    (od / "stdout").write_bytes(p.stdout)
    if p.stderr:
        (od / "stderr").write_bytes(p.stderr)
    # Text outputs mention their input and output folders; those move during Project S,
    # so they are replaced by placeholders before hashing.
    subst = [(str(od), "{out}")] + [(str(i.parent), "{in}") for i in case.inputs]
    for name in case.outputs:
        f = od / name
        if not f.exists():
            res["files"][name] = None
            continue
        data = f.read_bytes()
        if name == "stdout" or name.endswith((".json", ".txt")):
            text = data.decode("utf-8", "replace")
            for a, b in subst:
                text = text.replace(a, b)
            data = text.encode("utf-8")
            f.write_bytes(data)
        entry = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        if name.endswith(".dorico"):
            entry["entries"] = entry_hashes(f, case.tree)
        res["files"][name] = entry
    return res


def compare(want: dict, got: dict) -> list[str]:
    problems = []
    if want["exit"] != got["exit"]:
        problems.append(f"exit {want['exit']} -> {got['exit']}")
    for name, w in want["files"].items():
        g = got["files"].get(name)
        if w is None or g is None:
            if w != g:
                problems.append(f"{name}: {'missing' if g is None else 'appeared'}")
            continue
        if w["sha256"] == g["sha256"]:
            continue
        if "entries" in w:
            if w["entries"] == g["entries"]:
                problems.append(f"(note) {name}: zip bytes differ but every entry is identical")
                continue
            diff = sorted(k for k in set(w["entries"]) | set(g["entries"])
                          if w["entries"].get(k) != g["entries"].get(k))
            problems.append(f"{name}: entries differ: {', '.join(diff[:5])}")
        else:
            problems.append(f"{name}: content differs")
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("mode", choices=["record", "check", "list"])
    ap.add_argument("--only", help="run cases whose name starts with this")
    ap.add_argument("--fast", action="store_true", help="skip slow cases")
    a = ap.parse_args(argv)

    todo = [c for c in cases() if (not a.only or c.name.startswith(a.only)) and not (a.fast and c.slow)]
    if a.mode == "list":
        for c in todo:
            print(c.name, "(slow)" if c.slow else "")
        return 0
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"cases": {}}
    failed = skipped = 0
    tmp = Path(tempfile.mkdtemp(prefix="golden-"))
    try:
        for c in todo:
            missing = [str(i) for i in c.inputs if not i.exists()]
            if missing:
                print(f"skip  {c.name}: missing {missing[0]}")
                skipped += 1
                continue
            if a.mode == "record":
                od = OUT / c.name
                shutil.rmtree(od, ignore_errors=True)
                manifest["cases"][c.name] = run(c, od)
                r = manifest["cases"][c.name]
                print(f"rec   {c.name} (exit {r['exit']}, {r['seconds']}s)")
            else:
                want = manifest["cases"].get(c.name)
                if want is None:
                    print(f"new   {c.name}: not in manifest (run record)")
                    continue
                got = run(c, tmp / c.name)
                probs = compare(want, got)
                bad = [p for p in probs if not p.startswith("(note)")]
                print(f"{'FAIL' if bad else 'ok  '}  {c.name}" + "".join(f"\n      {p}" for p in probs))
                if bad:
                    failed += 1
                    keep = HERE / "out-failed" / c.name
                    shutil.rmtree(keep, ignore_errors=True)
                    shutil.copytree(tmp / c.name, keep)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if a.mode == "record":
        manifest["recorded"] = time.strftime("%Y-%m-%d %H:%M")
        manifest["cases"] = dict(sorted(manifest["cases"].items()))
        MANIFEST.write_text(json.dumps(manifest, indent=1) + "\n")
        print(f"recorded {len(todo) - skipped} cases ({skipped} skipped) -> {MANIFEST.relative_to(ROOT)}")
        return 0
    print(f"{len(todo) - failed - skipped} ok, {failed} failed, {skipped} skipped"
          + (" (failed outputs kept in engine/tests/golden/out-failed/)" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
