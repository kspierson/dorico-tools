"""Generate the Round 8 Dorico test files (see experiments/round8/README.md).

    python3 experiments/make_round8.py

The five HPCaptures scores plus the four John Williams scores from G:\\Scores, through the full
pipeline (`f2d convert --report`), each followed by a review (`.review.txt` / `.review.json`).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from f2d.__main__ import main  # noqa: E402
from f2d.review import format_text, review, to_json  # noqa: E402

HP = Path("/mnt/c/Users/kspie/Documents/HPCaptures/finale/scores")
G = Path("/mnt/g/Scores")
OUT = ROOT / "experiments" / "round8"
SOURCES = [HP / f"{n}.musx" for n in ("Willow", "Trex", "VV_Full", "Venus", "WW")] + [
    G / "John Williams - Raider's March.mus",
    G / "John Williams - Superman.mus",
    G / "John Williams - Empire Strikes Back - The Asteroid Field.musx",
    G / "John Williams - E.T. - Adventures On Earth bak.musx",
]

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for src in SOURCES:
        if not src.exists():
            print(f"skip {src} (not found)")
            continue
        name = src.stem.replace("John Williams - ", "JW ").replace(" bak", "")
        out = OUT / f"{name}.dorico"
        print(f"== {name}")
        main(["convert", str(src), "-o", str(out), "--report"])
        findings = review(out)
        out.with_suffix(".review.json").write_text(to_json(findings, str(out)))
        out.with_suffix(".review.txt").write_text(format_text(findings, None))
