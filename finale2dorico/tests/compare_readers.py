"""Compare the bootstrap reader with the full (musxdom) reader on .musx files.

    python3 tests/compare_readers.py FILE.musx|DIR [...]

Prints, per file, every IR field where the two readers disagree (warnings excluded).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from f2d import ir  # noqa: E402
from f2d.finale.enigma import read_musx  # noqa: E402
from f2d.finale.facts import read_finale  # noqa: E402


def flat(x, prefix="", out=None):
    out = {} if out is None else out
    if isinstance(x, dict):
        for k, v in x.items():
            flat(v, f"{prefix}.{k}" if prefix else k, out)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            flat(v, f"{prefix}[{i}]", out)
    else:
        out[prefix] = x
    return out


def diff(path: Path, limit: int = 12) -> list[str]:
    a = json.loads(ir.to_json(read_musx(path)))
    b = json.loads(ir.to_json(read_finale(path)))
    for d in (a, b):
        d.pop("warnings", None)
        d.pop("source", None)
    fa, fb = flat(a), flat(b)
    keys = sorted(set(fa) | set(fb))
    lines = [f"  {k}: bootstrap={fa.get(k, '<none>')!r} musxdom={fb.get(k, '<none>')!r}"
             for k in keys if fa.get(k, "<none>") != fb.get(k, "<none>")]
    return lines[:limit] + ([f"  ... {len(lines) - limit} more"] if len(lines) > limit else [])


def main(argv: list[str]) -> int:
    files = []
    for arg in argv:
        p = Path(arg)
        files += sorted(p.glob("*.musx")) if p.is_dir() else [p]
    bad = 0
    for f in files:
        try:
            lines = diff(f)
        except Exception as e:
            lines = [f"  ERROR {type(e).__name__}: {e}"]
        bad += bool(lines)
        print(f"{f.name}: {'same' if not lines else 'DIFF'}")
        for line in lines:
            print(line)
    print(f"{bad} of {len(files)} file(s) differ")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
