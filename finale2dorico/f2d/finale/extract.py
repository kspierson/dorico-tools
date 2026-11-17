"""Run the C++ extractor (extract/, built on musxdom + finale-mus-reader) and return its facts.

    facts = run_extractor("Old.mus")       # legacy Finale 1.0-2012
    facts = run_extractor("New.musx")      # unpacked to EnigmaXML here, then read by musxdom

The binary is looked for in this order: $F2D_EXTRACT, extract/build/f2d-extract(.exe) in
this repository, then `f2d-extract` on PATH. Build it with:

    cmake -S extract -B extract/build -G Ninja -DCMAKE_BUILD_TYPE=Release
    cmake --build extract/build
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .musx import enigma_xml

_ROOT = Path(__file__).resolve().parents[2]


class ExtractorMissing(RuntimeError):
    pass


def find_extractor() -> Path | None:
    env = os.environ.get("F2D_EXTRACT")
    if env:
        return Path(env)
    for name in ("f2d-extract", "f2d-extract.exe"):
        p = _ROOT / "extract" / "build" / name
        if p.exists():
            return p
    found = shutil.which("f2d-extract")
    return Path(found) if found else None


def run_extractor(path: str | Path) -> dict:
    exe = find_extractor()
    if exe is None:
        raise ExtractorMissing(
            "f2d-extract is not built. Build it with:\n"
            "  cmake -S extract -B extract/build -G Ninja -DCMAKE_BUILD_TYPE=Release\n"
            "  cmake --build extract/build\n"
            "(see docs/STATUS.md)")
    path = Path(path)
    with tempfile.TemporaryDirectory(prefix="f2d-") as tmp:
        target = path
        if path.suffix.lower() == ".musx":
            target = Path(tmp) / (path.stem + ".enigmaxml")
            target.write_text(enigma_xml(path), encoding="utf-8")
        proc = subprocess.run([str(exe), str(target)], capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"f2d-extract failed on {path}:\n{proc.stderr.strip()}")
    facts = json.loads(proc.stdout)
    facts["source"] = str(path)
    facts["log"] = [line for line in proc.stderr.splitlines() if line.strip()]
    return facts
