"""Count propertyType names (with an example value) per event kind across .dorico files."""
import sys, zipfile, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import f2d  # noqa: F401,E402  (makes doricokit importable)
from doricokit import format as dtn  # noqa: E402

def load(p):
    with zipfile.ZipFile(p) as z:
        n = set(z.namelist())
        return dtn.decode(z.read("score.dtn")).root if "score.dtn" in n else dtn.from_xml(z.read("score.xml")).root

cnt = collections.Counter(); ex = {}
def walk(n, owner):
    if n.children is None: return
    if n.tag == "entry" and n.child("propertyType") is not None:
        k = (owner, n.text("propertyType")); cnt[k] += 1; ex.setdefault(k, n.text("value")[:60])
        return
    tag = n.tag if n.tag.endswith("Definition") else owner
    for c in n.children: walk(c, tag)
for p in sys.argv[1:]:
    r = load(p)
    walk(r.find("flows"), "flows")
for (o, k), v in sorted(cnt.items()): print(f"{v:7d} {o:40s} {k:45s} {ex[(o,k)]}")
