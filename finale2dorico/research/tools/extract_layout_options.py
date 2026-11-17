"""Build f2d/data/new_project_layout_options.xml from a brand-new Dorico project.

    python3 research/tools/extract_layout_options.py NEW.dorico

Keeps the full-score and part `layoutOptions` of a new project (the user's defaults). The writer
starts every layout from these and then sets page size, staff size, condensing and empty-stave
hiding from the Finale file (f2d/dorico/layout.py). Source used:
experiments/round2-results/ref-pickup.dorico (File > New in Dorico 5.1.60).
"""
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import f2d  # noqa: F401,E402  (makes doricokit importable)
from doricokit import format as dtn  # noqa: E402
from doricokit.format import Node  # noqa: E402

src = Path(sys.argv[1])
z = zipfile.ZipFile(src)
root = (dtn.decode(z.read("score.dtn")) if "score.dtn" in z.namelist() else dtn.from_xml(z.read("score.xml"))).root
kept = {}
for lay in root.child("layouts").child("array").children:
    kept.setdefault(lay.child("layoutType").value, lay.child("layoutOptions"))
out = Node("newProjectLayoutOptions", children=[Node(t, children=[lo]) for t, lo in kept.items()])
dest = Path(__file__).resolve().parents[2] / "f2d/data/new_project_layout_options.xml"
dest.write_text(dtn.to_xml(dtn.Document(out), with_marker=False))
print(dest, list(kept))
