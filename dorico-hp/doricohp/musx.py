"""Read Finale .musx files (Finale 2014 and later).

A .musx is a zip; `score.dat` inside is EnigmaXML that has been gzip-compressed and
then scrambled with a simple XOR keystream (a linear congruential generator that
restarts every 128 KiB). Unscrambling and gunzipping gives plain XML:

    python3 -m doricohp.musx Score.musx > Score.enigmaxml
    python3 -m doricohp.musx --hp Score.musx      # just the Human Playback settings

Units in EnigmaXML: durations and positions in EDUs, 1024 per crotchet.
"""
from __future__ import annotations

import gzip
import re
import sys
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
    with zipfile.ZipFile(path) as z:
        raw = z.read("score.dat")
    return gzip.decompress(unscramble(raw)).decode("utf-8")


def hp_options(xml: str) -> dict[str, str]:
    """The document's Human Playback style settings (<hpOptions>), as name -> value.

    Switches that are on appear as empty elements (value "1"); missing ones are off.
    """
    m = re.search(r"<hpOptions[^>]*>(.*?)</hpOptions>", xml, re.S)
    if not m:
        return {}
    out = {}
    for tag, val in re.findall(r"<(\w+)(?:/>|>([^<]*)</\1>)", m.group(1)):
        out[tag] = val if val else "1"
    return out


def main(argv: list[str]) -> None:
    if argv and argv[0] == "--hp":
        for p in argv[1:]:
            print(Path(p).name, hp_options(enigma_xml(p)))
        return
    sys.stdout.write(enigma_xml(argv[0]))


if __name__ == "__main__":
    main(sys.argv[1:])
