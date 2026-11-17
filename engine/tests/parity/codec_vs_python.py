"""S2 safety check: doricokit (Rust) codec vs the old pure-Python dtn.py, on every project in
the corpus (the user's Dorico Projects + test files A-H).

    uv run python engine/tests/parity/codec_vs_python.py [--limit N]

For each score.dtn / scorelibrary.dtn / score.xml: decode with both, compare the trees, compare
encode() bytes and to_xml() text, and check the Rust zip reader returns the same entries as
Python's zipfile. Exit 1 on any difference. The old dtn.py is loaded from dorico-hp's copy while
it still exists, else from engine/tests/oracles/dtn_py.py.
"""
from __future__ import annotations

import importlib.util
import sys
import time
import zipfile
from pathlib import Path

from doricokit import container, paths
from doricokit import format as dtn

ROOT = Path(__file__).resolve().parents[3]


def old_dtn():
    for p in (ROOT / "engine/tests/oracles/dtn_py.py", ROOT / "dorico-hp/doricohp/dtn.py"):
        if p.exists():
            spec = importlib.util.spec_from_file_location("old_dtn", p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    sys.exit("no pure-Python oracle found")


def same(a, b) -> bool:
    stack = [(a, b)]
    while stack:
        x, y = stack.pop()
        if (x.tag, x.value, x.array) != (y.tag, y.value, y.array):
            return False
        if (x.children is None) != (y.children is None):
            return False
        if x.children is not None:
            if len(x.children) != len(y.children):
                return False
            stack.extend(zip(x.children, y.children))
    return True


def main() -> int:
    old = old_dtn()
    c = paths.corpus()
    files = sorted(c["projects"].glob("*.dorico")) + sorted(c["test_files"].glob("*.dorico"))
    if "--limit" in sys.argv:
        files = files[: int(sys.argv[sys.argv.index("--limit") + 1])]
    bad = checked = 0
    t_old = t_new = 0.0
    for f in files:
        data = f.read_bytes()
        ents = container.read_bytes(data)
        with zipfile.ZipFile(f) as z:
            want = [(i.filename, z.read(i) if not i.is_dir() else b"", i.date_time,
                     i.compress_type != zipfile.ZIP_STORED) for i in z.infolist()]
        got = [(e.name, e.data, e.time, e.deflated) for e in ents]
        if want != got:
            print(f"DIFF zip entries: {f.name}")
            bad += 1
        for e in ents:
            if not (e.name.endswith(".dtn") or e.name in ("score.xml", "scorelibrary.xml")):
                continue
            t = time.time()
            a = old.decode(e.data) if e.name.endswith(".dtn") else old.from_xml(e.data)
            t_old += time.time() - t
            t = time.time()
            b = dtn.decode(e.data) if e.name.endswith(".dtn") else dtn.from_xml(e.data)
            t_new += time.time() - t
            problems = []
            if a.marker != b.marker or not same(a.root, b.root):
                problems.append("tree")
            if old.encode(a) != dtn.encode(b):
                problems.append("encode")
            if e.name.endswith(".dtn") and dtn.encode(b) != e.data:
                problems.append("round trip")
            for wm in (True, False):
                if old.to_xml(a, wm) != dtn.to_xml(b, wm):
                    problems.append(f"to_xml(with_marker={wm})")
            x = dtn.to_xml(b)
            if not same(old.from_xml(x).root, dtn.from_xml(x).root):
                problems.append("from_xml")
            checked += 1
            if problems:
                bad += 1
                print(f"DIFF {f.name} {e.name}: {', '.join(problems)}")
    print(f"{checked} trees from {len(files)} projects; {bad} differences; "
          f"decode time python {t_old:.1f}s vs rust {t_new:.1f}s")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
