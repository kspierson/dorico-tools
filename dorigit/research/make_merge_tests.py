"""Make merge-preview test files from the user's divisi reference file.

    uv run python dorigit/research/make_merge_tests.py

From research/refs/ref-dynamics-divisi.dorico (Violin; divisi into 2 in bars 5-6):
  merge-A-IA.dorico     section 1 (IA, voice 1) bar 5 beat 1 up a tone
  merge-B-IB.dorico     section 2 (IB, divisi stave voice) bar 5 beat 1 down a tone
  merge-C-IA-other.dorico  the same IA note as A, but up a fourth (conflicts with A)
  merge-D-dynamic.dorico   bar 1 beat 1 note up an octave (unrelated to A/B/C)
Expected preview (base = the reference file): A+B review (other divisi section, same bar),
A+C conflict, A+D automatic. Only the edited notes' pitch and spelled letter change.
"""
import zipfile
from pathlib import Path

from doricokit import format as dtn
from doricokit import listing

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "dorigit/research/refs/ref-dynamics-divisi.dorico"
OUT = ROOT / "dorigit/research/refs/merge"


def walk(n):
    stack = [n]
    while stack:
        x = stack.pop()
        yield x
        stack.extend(x.children or ())


def find_note(where: str, lane: str) -> str:
    score = listing.read(SRC)
    for f in score["flows"]:
        for e in f["events"]:
            if e["kind"] == "note" and e["lane"] == lane and e["where"] == where:
                return e["event_id"]
    raise SystemExit(f"no note at {where} in {lane}")


LETTERS = "CDEFGAB"
STEPS = {2: 1, -2: -1, 5: 3, 12: 0}  # semitones -> letter steps for the edits below


def respell(node, semis: int) -> None:
    """Move Dorico's spelled letter with the pitch (G +2 semitones -> A, not G##)."""
    table = node.child("propertyTable")
    for e in (table.child("entries").children if table and table.child("entries") else []):
        if e.text("propertyType") == "kNoteSpelling":
            v = e.child("value")
            letter = v.value.split('"')[1]
            new = LETTERS[(LETTERS.index(letter) + STEPS[semis]) % 7]
            v.value = f'string: "{new}"'


def write(name: str, edits: dict[str, int]) -> None:
    with zipfile.ZipFile(SRC) as z:
        doc = dtn.decode(z.read("score.dtn"))
    done = set()
    for node in walk(doc.root):
        if node.tag == "NoteEventDefinition" and node.text("eventID") in edits:
            p = node.child("pitch")
            p.value = str(int(p.value) + edits[node.text("eventID")])
            respell(node, edits[node.text("eventID")])
            done.add(node.text("eventID"))
    assert done == set(edits), (name, edits, done)
    with zipfile.ZipFile(SRC) as zin, zipfile.ZipFile(OUT / name, "w") as zout:
        for info in zin.infolist():
            data = dtn.encode(doc) if info.filename == "score.dtn" else zin.read(info)
            new = zipfile.ZipInfo(info.filename, info.date_time)
            new.compress_type = info.compress_type
            zout.writestr(new, data)
    print("wrote", OUT / name)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ia = find_note("bar 5 beat 1", "voice 1")
    ib = find_note("bar 5 beat 1", "voice 2")
    b1 = find_note("bar 1 beat 1", "voice 1")
    write("merge-A-IA.dorico", {ia: +2})
    write("merge-B-IB.dorico", {ib: -2})
    write("merge-C-IA-other.dorico", {ia: +5})
    write("merge-D-dynamic.dorico", {b1: +12})


if __name__ == "__main__":
    main()
