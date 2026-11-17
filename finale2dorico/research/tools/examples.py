"""Print the first example of each event type (and element-table def) in a .dorico/score.xml.

    python3 tools/examples.py file.dorico|score.xml [EventTag ...]
"""
import sys, zipfile, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import f2d  # noqa: F401,E402  (makes doricokit importable)
from doricokit import format as dtn  # noqa: E402

def load(p):
    if p.endswith(".xml"): return dtn.from_xml(open(p, "rb").read())
    with zipfile.ZipFile(p) as z:
        n = set(z.namelist())
        return dtn.decode(z.read("score.dtn")) if "score.dtn" in n else dtn.from_xml(z.read("score.xml"))

doc = load(sys.argv[1]); want = set(sys.argv[2:])
def xml(n):
    s = dtn.to_xml(dtn.Document(n, marker=0) if hasattr(dtn, "Document") else n)
    return s
seen = set()
def emit(n, ctx):
    if n.tag in seen or (want and n.tag not in want): return
    seen.add(n.tag)
    sub = dtn.Document.__new__(dtn.Document)
    print(f"===== {n.tag}  (in {ctx})")
    print(re.sub(r"\n\s*\n", "\n", dtn.to_xml(dtn.Document(root=n, marker=doc.marker), with_marker=False).split("?>",1)[-1])[:4000])
for flow in doc.root.find("flows/array").children or []:
    for b in flow.find("blocks/array").children or []:
        for e in b.find("events").children or []:
            emit(e, b.text("parentEventStreamType"))
    for t in flow.find("elementTables/array").children or []:
        for e in (t.find("array").children or []):
            emit(e, t.tag)
