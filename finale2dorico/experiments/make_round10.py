"""Generate the Round 10 review set (see experiments/round10/README.md).

    python3 experiments/make_round10.py [--no-pdf | --pdf-only] [names...]

Converts each source (`f2d convert --report`), writes the reviewer's findings next to it, then
has the running Dorico export the full score as PDF (research/tools/dorico_remote.ps1; needs
Dorico open with remote control allowed, and nobody working in it). PDFs are renamed after the
score: `<name>.pdf`.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from f2d.__main__ import main  # noqa: E402
from f2d.review import format_text, review, to_json  # noqa: E402

HP = Path("/mnt/c/Users/kspie/Documents/HPCaptures/finale/scores")
FILM = Path("/mnt/d/SCORES+BOOKS/Film Scores")
AV = FILM / "James Horner/Avatar/Finale (.mus) Files"
OUT = ROOT / "experiments" / "round10"
SOURCES = {f"{n}": HP / f"{n}.musx" for n in ("Willow", "Trex", "VV_Full", "Venus", "WW")}
SOURCES.update({
    "JW Raider's March": FILM / "John Williams/Indiana Jones and the Raiders of the Lost Ark/Concert Scores/John Williams - Raider's March.mus",
    "JW Superman": FILM / "John Williams/Superman/Concert Scores/John Williams - Superman.mus",
    "JW Asteroid Field": Path("/mnt/g/Scores/John Williams - Empire Strikes Back - The Asteroid Field.musx"),
    "JW E.T. Adventures On Earth": FILM / "John Williams/E.T. The Extra Terrestrial/Concert Scores/John Williams - E.T. - Adventures On Earth.mus",
    "Avatar 1m1R": AV / "1m1R_Avatar.score.mus",
    "Avatar 2m2r": AV / "2m2r_Avatar.score.mus",
    "Avatar 3m2": AV / "3m2_Avatar.score.mus",
    "Avatar 4m4-5R": AV / "4m4-5R_Avatar.score.mus",
    "The Thing 1m02": FILM / 'Marco Beltrami/The Thing/Complete Score (pdf"sib)/MB-TT-SIBMUS/THG_1m02_(B)_BR.mus',
})
PS = ROOT / "research/tools/dorico_remote.ps1"


def wpath(p: Path) -> str:
    return subprocess.run(["wslpath", "-w", str(p)], capture_output=True, text=True).stdout.strip()


def dorico_idle() -> bool:
    """Dorico answers quickly and has no project open. If a dialog is blocking it, commands sent
    now would queue up and run later all at once (that crashed Dorico once), so stop instead."""
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", wpath(PS),
                            "-Status", "-WaitForUser", "20"], capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired:
        return False
    return "hasScore=False" in r.stdout


def export_pdf(dorico: Path) -> str:
    if not dorico_idle():
        raise SystemExit("Dorico is busy, blocked by a dialog, or has a project open: stopping the PDF export")
    for old in OUT.glob("01 - Full score*.pdf"):
        old.unlink()
    r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", wpath(PS),
                        "-Export", wpath(dorico), "-WaitForUser", "60"],
                       capture_output=True, text=True, timeout=1800)
    import time
    for _ in range(60):  # Dorico finishes writing the PDF after it answers
        made = sorted(OUT.glob("01 - Full score*.pdf"))
        if made:
            time.sleep(3)
            break
        time.sleep(2)
    if not made:
        return "no PDF: " + (r.stdout + r.stderr).replace("\r", "").strip().splitlines()[-1]
    made[0].rename(dorico.with_suffix(".pdf"))
    return "pdf ok"


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    OUT.mkdir(parents=True, exist_ok=True)
    for name, src in SOURCES.items():
        if args and name not in args:
            continue
        if not src.exists():
            print(f"skip {name} (not found: {src})")
            continue
        out = OUT / f"{name}.dorico"
        print(f"== {name}", flush=True)
        if "--pdf-only" not in sys.argv:
            main(["convert", str(src), "-o", str(out), "--report"])
            findings = review(out)
            out.with_suffix(".review.json").write_text(to_json(findings, str(out)))
            out.with_suffix(".review.txt").write_text(format_text(findings, None))
        if "--no-pdf" not in sys.argv:
            print("  " + export_pdf(out), flush=True)
