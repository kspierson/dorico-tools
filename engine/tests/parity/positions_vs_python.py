"""S3 safety check: doricokit.positions (Rust Ratio) vs the tools' Python `frac`/`frac_str`
(dorico-hp's `Fraction(s or "0")`, f2d's `fstr`) on every position/duration-like value in the
corpus; plus `ids.check` on every project (counters ahead of IDs in use).

    uv run python engine/tests/parity/positions_vs_python.py [--limit N]
"""
from __future__ import annotations

import sys
from fractions import Fraction

from doricokit import container, ids, paths, positions

TAGS = {"position", "duration", "secondaryPosition", "secondaryEndOffset", "rhythmicPosition"}


def py_frac(s):
    try:
        return Fraction(s or "0")
    except (ValueError, ZeroDivisionError):
        return Fraction(0)


def py_str(f):
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


def main() -> int:
    c = paths.corpus()
    files = sorted(c["projects"].glob("*.dorico")) + sorted(c["test_files"].glob("*.dorico"))
    if "--limit" in sys.argv:
        files = files[: int(sys.argv[sys.argv.index("--limit") + 1])]
    values: set[str] = set()
    id_problems = 0
    for f in files:
        doc = container.score(container.read(f))
        stack = [doc.root]
        while stack:
            n = stack.pop()
            if n.children:
                stack.extend(n.children)
            elif n.tag in TAGS:
                values.add(n.value)
        probs = ids.check(doc)
        if probs:
            id_problems += 1
            print(f"ids: {f.name}: {'; '.join(probs[:3])}")
    bad = 0
    for v in sorted(values):
        a, b = py_frac(v), positions.frac(v)
        if a != b or py_str(a) != positions.frac_str(b):
            bad += 1
            print(f"DIFF {v!r}: python {a} rust {b}")
    for t in range(-2000, 2000):
        f = Fraction(t, 977)
        if round(f * 480) != positions.to_ticks(f):
            bad += 1
            print(f"DIFF ticks {f}: {round(f * 480)} vs {positions.to_ticks(f)}")
    print(f"{len(values)} distinct position/duration strings from {len(files)} projects; {bad} differences; "
          f"{id_problems} projects with idGenerators problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
