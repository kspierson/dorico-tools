"""Build f2d/data/finale_instruments.json from musxdom + denigma sources (MIT, Robert G. Patterson).

Reads (as text, nothing is compiled or run):
  musxdom/src/musx/dom/InstrumentUuids.h                 uuid constant -> UUID string + display name
  denigma/src/formats/musicxml/musicxml_instruments.cpp  uuid constant -> MusicXML SoundID (camelCase)

    python3 research/tools/extract_finale_instruments.py <musxdom dir> <denigma dir>
"""
import json, re, sys
from pathlib import Path

musxdom, denigma = Path(sys.argv[1]), Path(sys.argv[2])
uu = {}
for m in re.finditer(r'inline constexpr std::string_view (\w+) = "([0-9a-f-]+)";\s*///<\s*(.*)',
                     (musxdom / "src/musx/dom/InstrumentUuids.h").read_text()):
    uu[m.group(1)] = (m.group(2), m.group(3).strip())
snd = {}
src = (denigma / "src/formats/musicxml/musicxml_instruments.cpp").read_text()
for m in re.finditer(r'^\s*\{\s*uuid::(\w+),\s*SoundID::(\w+)\s*\}', src, re.M):
    snd.setdefault(m.group(1), m.group(2))
out = {}
for const, (uuid, name) in uu.items():
    out[uuid] = {"const": const, "name": name, "sound": snd.get(const)}
dest = Path(__file__).resolve().parents[2] / "f2d/data/finale_instruments.json"
dest.write_text(json.dumps({
    "_source": "Extracted from musxdom InstrumentUuids.h and denigma musicxml_instruments.cpp "
               "(MIT licence, Copyright (c) 2025 Robert G. Patterson). 'sound' is a MusicXML sound ID in mx camelCase.",
    "instruments": out}, indent=1, sort_keys=True))
print(len(out), "instruments,", sum(1 for v in out.values() if v["sound"]), "with sound IDs ->", dest)
