"""Open Finale .musx files (Finale 2014 and later) as EnigmaXML text.

Vendored from dorico-hp/doricohp/musx.py (same author/repo; dorico-hp owns the original).

A .musx is a zip; `score.dat` inside is EnigmaXML that has been gzip-compressed and
then scrambled with a simple XOR keystream (a linear congruential generator that
restarts every 128 KiB). Unscrambling and gunzipping gives plain XML.

Units in EnigmaXML: durations and positions in EDUs, 1024 per crotchet.
"""
from __future__ import annotations

import gzip
import zipfile
from pathlib import Path

_INITIAL_STATE = 0x28006D45
_RESET_EVERY = 0x20000


def unscramble(data: bytes) -> bytes:
    out = bytearray(data)
    state = _INITIAL_STATE
    for i in range(len(out)):
        if i % _RESET_EVERY == 0:
            state = _INITIAL_STATE
        state = (state * 0x41C64E6D + 0x3039) & 0xFFFFFFFF
        upper = state >> 16
        out[i] ^= (upper + upper // 255) & 0xFF
    return bytes(out)


def enigma_xml(path: str | Path) -> str:
    """EnigmaXML text of a .musx file (or pass through an .enigmaxml file)."""
    path = Path(path)
    if path.suffix.lower() in (".enigmaxml", ".xml"):
        return path.read_text(encoding="utf-8")
    with zipfile.ZipFile(path) as z:
        raw = z.read("score.dat")
    return gzip.decompress(unscramble(raw)).decode("utf-8")
