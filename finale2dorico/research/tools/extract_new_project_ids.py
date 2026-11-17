"""Build f2d/data/new_project_library.json from a brand-new Dorico project.

    python3 research/tools/extract_new_project_ids.py NEW.dorico

Records, per library collection, the entity IDs a new Dorico project carries (names only, no
definitions) plus the collection skeleton (order and non-entity fields). The converter then
copies those definitions from the user's own Dorico install (f2d/dorico/library.py).
Instruments and instrument names are left out: the writer adds the ones a score uses.
Source used: experiments/round2-results/ref-pickup.dorico (File > New in Dorico 5.1.60).
"""
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import f2d  # noqa: F401,E402  (makes doricokit importable)
from doricokit import format as dtn  # noqa: E402

SKIP = {"instruments", "instrumentNames"}

src = Path(sys.argv[1])
doc = dtn.decode(zipfile.ZipFile(src).read("scorelibrary.dtn"))
out = {"_source": f"entity IDs from a new Dorico project ({src.name}); definitions are read "
                  "from the user's Dorico install at run time",
       "fileVersion": doc.root.child("fileVersion").value,
       "marker": doc.marker, "collections": []}
for coll in doc.root.children:
    if coll.tag == "fileVersion":
        continue
    ents = coll.child("entities")
    extra = {c.tag: c.value for c in coll.children or [] if c.tag != "entities" and c.children is None}
    ids = [] if coll.tag in SKIP or ents is None else [e.child("entityID").value for e in ents.children or []]
    out["collections"].append({"tag": coll.tag, "extra": extra, "ids": ids})
dest = Path(__file__).resolve().parents[2] / "f2d/data/new_project_library.json"
dest.write_text(json.dumps(out, indent=1))
print(dest, sum(len(c["ids"]) for c in out["collections"]), "ids")
