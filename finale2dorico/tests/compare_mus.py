"""Check .mus reading against Finale 27's own conversion of the same file.

finale-mus-reader's test fixtures (tests/evidence/<release>/) pair many legacy X.mus files
with -finale27/X.musx, the same document opened and saved by Finale 27. Reading both through
the full reader should give the same IR, apart from what Finale's upgrade normalises.

    python3 tests/compare_mus.py [evidence dir] [-v]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_readers import flat  # noqa: E402
from f2d import ir  # noqa: E402
from f2d.finale.facts import read_finale  # noqa: E402

DEFAULT = Path(__file__).resolve().parents[1] / "extract/build/_deps/finale_mus_reader-src/tests/evidence"


def notes(d: dict) -> int:
    return sum(len(v["chords"]) for f in d["flows"] for s in f["staves"] for v in s["voices"])


def main(argv: list[str]) -> int:
    verbose = "-v" in argv
    args = [a for a in argv if a != "-v"]
    root = Path(args[0]) if args else DEFAULT
    pairs = sorted((m, m.parent / "-finale27" / (m.stem + ".musx"))
                   for m in root.glob("*/*.mus") if (m.parent / "-finale27" / (m.stem + ".musx")).exists())
    kinds, bad, errors, total_chords = Counter(), 0, 0, 0
    for mus, musx in pairs:
        try:
            a = json.loads(ir.to_json(read_finale(mus)))
            b = json.loads(ir.to_json(read_finale(musx)))
        except Exception as e:
            errors += 1
            print(f"{mus.parent.name}/{mus.name}: ERROR {type(e).__name__}: {str(e)[:200]}")
            continue
        for d in (a, b):
            d.pop("warnings", None)
            d.pop("source", None)
            d.pop("layout", None)  # Finale 27 re-lays-out the file when it upgrades it
        total_chords += notes(a)
        fa, fb = flat(a), flat(b)
        diffs = [k for k in sorted(set(fa) | set(fb)) if fa.get(k) != fb.get(k)]
        if diffs:
            bad += 1
            import re
            for k in {re.sub(r"\[\d+\]", "[]", k) for k in diffs}:
                kinds[k] += 1
            if verbose:
                print(f"{mus.parent.name}/{mus.name}: {len(diffs)} differences")
                for k in diffs[:6]:
                    print(f"  {k}: mus={fa.get(k, '<none>')!r} finale27={fb.get(k, '<none>')!r}")
    print(f"{len(pairs)} pairs, {total_chords} chords/rests read from .mus; "
          f"{bad} pairs differ, {errors} errors")
    for k, n in kinds.most_common(40):
        print(f"  {n:4d}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
