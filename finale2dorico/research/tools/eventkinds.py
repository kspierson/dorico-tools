"""Count event element types (block events + element tables) across .dorico files."""
import sys, zipfile, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import f2d  # noqa: F401,E402  (makes doricokit importable)
from doricokit import format as dtn  # noqa: E402

def load(p):
    with zipfile.ZipFile(p) as z:
        n = set(z.namelist())
        if "score.dtn" in n: return dtn.decode(z.read("score.dtn")).root
        return dtn.from_xml(z.read("score.xml")).root

ev = collections.Counter(); tab = collections.Counter(); where = {}
for p in sys.argv[1:]:
    try: root = load(p)
    except Exception as e:
        print("skip", p, e); continue
    for flow in (root.find("flows/array").children or []):
        for b in (flow.find("blocks/array").children or []) if flow.find("blocks/array") and flow.find("blocks/array").children else []:
            evs = b.find("events")
            for e in (evs.children or []) if evs is not None else []:
                ev[e.tag] += 1; where.setdefault(e.tag, Path(p).name)
        et = flow.find("elementTables/array")
        for t in (et.children or []) if et is not None else []:
            tab[t.tag] += 1
for k, v in ev.most_common(): print(f"{v:8d} {k:45s} {where[k]}")
print("--- element tables")
for k, v in tab.most_common(): print(f"{v:8d} {k}")
