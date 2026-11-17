"""Make the starter files for dorigit's reference rounds (see research/refs/README.md).

    uv run python dorigit/research/make_ref_starters.py

Copies finale2dorico's 8-bar violin start file (converter-written for Dorico 5.1.60, score
stored as plain XML, which Dorico opens) and changes only the project
title and flow name, so each starter is easy to recognise in Dorico and in listings.
"""
import zipfile
from pathlib import Path

from doricokit import format as dtn

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "finale2dorico/experiments/round12/ref-start.dorico"
OUT = ROOT / "dorigit/research/refs"

STARTERS = {
    "start-dynamics-divisi.dorico": "dorigit ref 1: dynamics + divisi",
    "start-film.dorico": "dorigit ref 2: film",
}


def retitled(score_raw: bytes, title: str, xml: bool) -> bytes:
    doc = dtn.from_xml(score_raw.decode()) if xml else dtn.decode(score_raw)
    doc.root.find("info/title").value = title
    for flow in doc.root.find("flows/array").children:
        flow.find("flowName").value = title
        flow.find("flowInfo/title").value = title
    return dtn.to_xml(doc, with_marker=False).encode() if xml else dtn.encode(doc)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, title in STARTERS.items():
        with zipfile.ZipFile(SRC) as zin, zipfile.ZipFile(OUT / name, "w") as zout:
            for info in zin.infolist():
                data = zin.read(info)
                if info.filename == "supplementary_data/scoreinfo/scoreinfo.xml":
                    data = data.replace(b"Round 12 reference", title.encode())
                if info.filename in ("score.dtn", "score.xml"):
                    data = retitled(data, title, xml=info.filename.endswith(".xml"))
                new = zipfile.ZipInfo(info.filename, info.date_time)
                new.compress_type = info.compress_type
                zout.writestr(new, data)
        print("wrote", OUT / name)


if __name__ == "__main__":
    main()
