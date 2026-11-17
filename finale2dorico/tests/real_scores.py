"""Note oracle on real scores: the user's Finale files that also have a Finale-exported MusicXML.

    python3 tests/real_scores.py [scores dir]      (default /mnt/g/Scores; skipped if absent)

Compares pitch, position, duration and ties of every note (per bar, 1/192-beat grid) between the
full reader and Finale's own MusicXML. Known, accepted differences: percussion staves (MusicXML
writes unpitched notes, not compared), ties into rests (Finale's export omits them), staves
with an independent time signature (E.T.: MusicXML writes them in longer bars).
"""
from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402
from f2d.finale.facts import read_finale  # noqa: E402

PAIRS = [
    ("John Williams - Raider's March.mus", "John Williams - Raider's March.mxl"),
    ("John Williams - Superman.mus", "John Williams - Superman.mxl"),
    ("John Williams - Empire Strikes Back - The Asteroid Field.musx",
     "John Williams - Empire Strikes Back - The Asteroid Field.mxl"),
    ("John Williams - E.T. - Adventures On Earth bak.musx", "John Williams - E.T. - Adventures On Earth bak.mxl"),
]


def main(argv: list[str]) -> int:
    root = Path(argv[0]) if argv else Path("/mnt/g/Scores")
    if not root.exists():
        print(f"{root} not found; skipped")
        return 0
    oracle.READ = read_finale
    with tempfile.TemporaryDirectory() as tmp:
        for src, mxl in PAIRS:
            if not (root / src).exists() or not (root / mxl).exists():
                continue
            z = zipfile.ZipFile(root / mxl)
            inner = next(n for n in z.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
            out = Path(tmp) / (Path(mxl).stem + ".musicxml")
            out.write_bytes(z.read(inner))
            ok, msg = oracle.compare(root / src, out)
            lines = msg.splitlines()
            print(lines[0])
            for line in lines[1:]:
                if line.startswith("  staff"):
                    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
