"""Build test projects that answer questions only Dorico itself can answer.

    uv run python dorigit/research/make_test_files.py SOURCE.dorico OUT_DIR

Made the shared test files A-D in engine/tests/dorico-files/ from "ET The Flying Theme mASTER"
(E-H were made by dorico-hp). Moved from the retired Python prototype on 2026-10-30 and switched
to the shared engine (`doricokit`); output is byte-identical to the prototype's.

A-rebuilt.dorico   decoded to XML and re-encoded (should be byte-identical
                   inside; proves the round trip is safe)
B-xml-inside.dorico  score/scorelibrary stored as plain XML, like some of
                   Steinberg's own example projects. Does Dorico open it?
C-title-edit.dorico  title changed via our encoder. Does Dorico accept files
                   we write?
D-note-edit.dorico   title changed and one note moved up an octave. Does
                   Dorico accept musical edits we make (the basis for merge)?
"""
import sys
import zipfile
from pathlib import Path

from doricokit import format as dtn
from doricokit import listing


def write(src: Path, dest: Path, replace: dict[str, bytes], rename: dict[str, str] | None = None) -> None:
    rename = rename or {}
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest, "w") as zout:
        for info in zin.infolist():
            data = replace.get(info.filename, zin.read(info))
            new = zipfile.ZipInfo(rename.get(info.filename, info.filename), info.date_time)
            new.compress_type = info.compress_type
            zout.writestr(new, data)


def main(src: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as z:
        score_raw = z.read("score.dtn")
        lib_raw = z.read("scorelibrary.dtn")
        container = z.read("META-INF/container.xml")
    stem = src.stem

    # A: straight round trip
    write(src, out / f"{stem} A-rebuilt.dorico", {
        "score.dtn": dtn.encode(dtn.from_xml(dtn.to_xml(dtn.decode(score_raw)))),
        "scorelibrary.dtn": dtn.encode(dtn.from_xml(dtn.to_xml(dtn.decode(lib_raw)))),
    })

    # B: XML inside
    write(src, out / f"{stem} B-xml-inside.dorico", {
        "score.dtn": dtn.to_xml(dtn.decode(score_raw), with_marker=False).encode(),
        "scorelibrary.dtn": dtn.to_xml(dtn.decode(lib_raw), with_marker=False).encode(),
        "META-INF/container.xml": container.replace(b'"score.dtn"', b'"score.xml"'),
    }, rename={"score.dtn": "score.xml", "scorelibrary.dtn": "scorelibrary.xml"})

    # C: title edit
    doc = dtn.decode(score_raw)
    title = doc.root.find("info/title")
    old_title = title.value
    title.value = f"{old_title} [dorigit C: title edit]"
    write(src, out / f"{stem} C-title-edit.dorico", {"score.dtn": dtn.encode(doc)})

    # D: title + first note of the first flow up an octave
    doc = dtn.decode(score_raw)
    doc.root.find("info/title").value = f"{old_title} [dorigit D: note edit]"
    score = listing.read(src)
    notes = [e for f in score["flows"] for e in f["events"]
             if e["kind"] == "note" and "crotchets" not in e["text"] and e["owner"] != "(global)"]
    target = min(notes, key=lambda e: e["position"])
    for node in _walk(doc.root):
        if node.tag == "NoteEventDefinition" and node.text("eventID") == target["event_id"]:
            pitch = node.child("pitch")
            pitch.value = str(int(pitch.value) + 12)
            break
    write(src, out / f"{stem} D-note-edit.dorico", {"score.dtn": dtn.encode(doc)})
    print(f"D moved this note up an octave: {target['flow']} / {target['owner']} {target['lane']} "
          f"{target['where']}: {target['text']}")
    print(f"wrote test files to {out}")


def _walk(n):
    stack = [n]
    while stack:
        x = stack.pop()
        yield x
        stack.extend(x.children or ())


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
