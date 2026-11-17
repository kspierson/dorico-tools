"""Build a project library from the user's Dorico install.

Round 2 showed Dorico needs a real library in the project: with only instrument definitions,
notes have no noteheads and double-clicking one crashes Dorico. A brand-new Dorico project
carries a fixed set of library entities (noteheads, rests, flags, glyphs, composites, fonts,
paragraph styles, playing techniques ...). Their IDs are in f2d/data/new_project_library.json;
the definitions are copied from the factory XML files in the user's Dorico folder (glyphs.xml,
composites.xml, scorelibrary.xml, ...). Nothing from Steinberg ships with this tool.

On top of that set, the writer adds what the score uses (instruments, names, clefs ...), and
every entity those definitions refer to (a clef -> its composite -> its glyphs), so the
library is closed.

    lib = FactoryLibrary(install_dir)
    node = lib.build(extra={"instruments": [...nodes...]}, want=["clef.tenor"])
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from doricokit import format as dtn
from doricokit.format import Node
from .tree import A, E, L, deep_copy

_DATA = Path(__file__).resolve().parents[1] / "data" / "new_project_library.json"
# never pulled in just because something mentions them (score orders list every instrument)
_NO_CLOSURE = {"instruments", "instrumentNames", "ensembles", "instrumentScoreOrders", "instrumentFamilies"}


def _conv(e: ET.Element) -> Node:
    arr = e.get("array") == "true"
    if len(e):
        return Node(e.tag, None, arr, [_conv(c) for c in e])
    return Node(e.tag, e.text or "", arr)


class FactoryLibrary:
    def __init__(self, install_dir: str | Path):
        self.dir = Path(install_dir)
        spec = json.loads(_DATA.read_text())
        self.spec = spec
        self.collection_of: dict[str, str] = {}   # entityID -> collection tag
        self._raw: dict[str, ET.Element] = {}     # entityID -> factory element
        self._index()

    # ----------------------------------------------------------------- factory
    def _index(self) -> None:
        tags = {c["tag"] for c in self.spec["collections"]}
        for f in sorted(self.dir.glob("*.xml")):
            try:
                root = ET.parse(f).getroot()
            except ET.ParseError:
                continue
            if root.tag != "kScoreLibrary":
                continue
            for coll in root:
                if coll.tag not in tags:
                    continue
                ents = coll.find("entities")
                for e in (ents if ents is not None else []):
                    eid = e.findtext("entityID")
                    if eid and eid not in self._raw:
                        self._raw[eid] = e
                        self.collection_of[eid] = coll.tag

    def has(self, eid: str) -> bool:
        return eid in self._raw

    def node(self, eid: str) -> Node:
        return _conv(self._raw[eid])

    # ------------------------------------------------------------------- build
    def references(self, n: Node) -> set[str]:
        """Entity IDs mentioned anywhere in a definition's leaf values."""
        found = set()

        def visit(x: Node) -> None:
            if x.children is None:
                v = (x.value or "").strip()
                if not v:
                    return
                for piece in {v, *re.split(r'\s*,\s*|"', v)}:
                    piece = piece.strip()
                    if piece in self._raw:
                        found.add(piece)
                return
            for c in x.children:
                visit(c)

        visit(n)
        if n.child("entityID") is not None:
            found.discard(n.child("entityID").value)
        return found

    def build(self, extra: dict[str, list[Node]] | None = None, want: list[str] = ()) -> Node:
        """Library node: new-project set + `want` IDs + `extra` ready-made nodes (e.g. the
        instruments the writer resolved), closed over references."""
        extra = extra or {}
        chosen: dict[str, Node] = {}       # entityID -> node
        order: dict[str, list[str]] = {}   # collection -> ids in insertion order

        def add_node(coll: str, n: Node) -> None:
            eid = n.child("entityID").value
            if eid in chosen:
                return
            chosen[eid] = n
            order.setdefault(coll, []).append(eid)

        # 1. the new-project set, as Dorico itself writes it (already self-contained)
        for c in self.spec["collections"]:
            for eid in c["ids"]:
                if eid in self._raw:
                    add_node(c["tag"], self.node(eid))
        # 2. what the score adds, plus whatever those definitions refer to
        for coll, nodes in extra.items():
            for n in nodes:
                add_node(coll, n)
        queue = list(want) + [r for nodes in extra.values() for n in nodes for r in self.references(n)]
        while queue:
            eid = queue.pop(0)
            if eid in chosen or eid not in self._raw or self.collection_of[eid] in _NO_CLOSURE:
                continue
            n = self.node(eid)
            add_node(self.collection_of[eid], n)
            queue.extend(self.references(n))

        colls = [L("fileVersion", self.spec["fileVersion"])]
        for c in self.spec["collections"]:
            ents = [chosen[eid] for eid in order.get(c["tag"], [])]
            colls.append(E(c["tag"], A("entities", ents), *[L(k, v) for k, v in c["extra"].items()]))
        return E("library", *colls)

    def scorelibrary_dtn(self, library: Node) -> bytes:
        """The same library as a standalone scorelibrary.dtn (root kScoreLibrary)."""
        root = Node("kScoreLibrary", None, False, [deep_copy(c) for c in library.children])
        return dtn.encode(dtn.Document(root=root, marker=self.spec.get("marker", 0)))
