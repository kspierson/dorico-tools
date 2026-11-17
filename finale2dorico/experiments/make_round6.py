"""Generate the Round 6 Dorico test files (see experiments/round6/README.md).

    python3 experiments/make_round6.py

The five real scores through the full pipeline (`f2d convert` defaults: musxdom reader,
shared staves exploded into players, install-built library, grouped/linked dynamics,
trills, glissandi, tremolos, playing techniques).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from f2d.__main__ import main  # noqa: E402

SCORES = Path("/mnt/c/Users/kspie/Documents/HPCaptures/finale/scores")
OUT = ROOT / "experiments" / "round6"

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("Willow", "Trex", "VV_Full", "Venus", "WW"):
        print(f"== {name}")
        main(["convert", str(SCORES / f"{name}.musx"), "-o", str(OUT / f"{name}.dorico"), "--report"])
