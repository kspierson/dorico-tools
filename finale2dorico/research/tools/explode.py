"""Decode a .dorico file's score + scorelibrary to XML for study.

    python3 tools/explode.py Project.dorico outdir/
"""
import sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import f2d  # noqa: F401,E402  (makes doricokit importable)
from doricokit import format as dtn  # noqa: E402

src, dest = sys.argv[1], Path(sys.argv[2])
dest.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(src) as z:
    for info in z.infolist():
        if info.is_dir():
            continue
        data = z.read(info)
        name = info.filename
        if name.endswith(".dtn"):
            data = dtn.to_xml(dtn.decode(data)).encode()
            name = name[:-4] + ".xml"
        if "enginedata" in name:
            continue
        out = dest / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(f"{info.filename:60s} {info.file_size:>10d} {info.compress_type}")
