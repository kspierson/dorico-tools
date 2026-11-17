"""Edit an existing Dorico project: load -> change -> save, everything untouched kept as it was.

    from doricokit import edit
    proj = edit.Project.open("In.dorico")
    fe = proj.flows[0]                       # FlowEdit: events / dynamics elements by ID
    fe.remove_event("123")
    fe.link_dynamic_group("124", "17")       # make event 124 use element 17 (Dorico linking)
    proj.save("Out.dorico", protect="In.dorico")

- Only `score.dtn` / `score.xml` is re-encoded (in its own form); other zip entries are copied.
  A project with no changes is saved as the original bytes.
- Never writes over the source (`protect`); writes atomically; checks IDs before saving.
- `same(a, b)`: two items are the same marking only if they match apart from their IDs
  (and default-valued / empty property lists), so hand-made tweaks are never merged away.

Python prototype of the planned Rust `dorico-edit` crate (PLANNED_WORK.md §2, S5), written for
the cleaner (2026-10-31); dorico-hp's Apply plumbing and dorigit merge are meant to move onto
the same layer.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import container, ids
from .format import Document, Node

__all__ = ["Project", "FlowEdit", "canon", "same"]

# IDs and per-element numbering: not part of what an item *is*
ID_TAGS = {"eventID", "elementID", "referencingEventIDs", "dynamicGroupID", "scoreSubElementID"}
# property entries that only state Dorico's default (one copy has them, an identical one not)
DEFAULT_PROPS = {("kEventSecondaryPosition", 'string: "0"')}


def canon(n: Node, skip: frozenset = frozenset()) -> tuple:
    """A node's content without IDs (and without the child tags in `skip`), comparable."""
    if n.children is None:  # an empty array is written either way: <entries array="true"/> or with no items
        return (n.tag, ()) if n.tag == "entries" and not n.value else (n.tag, n.value)
    kids = [c for c in n.children if c.tag not in ID_TAGS and c.tag not in skip]
    if n.tag == "entries":
        kids = [c for c in kids if (c.text("propertyType"), c.text("value")) not in DEFAULT_PROPS]
    return (n.tag, tuple(canon(c) for c in kids))


def same(a: Node, b: Node) -> bool:
    return canon(a) == canon(b)


class FlowEdit:
    """One flow of the score tree, indexed for editing."""

    def __init__(self, flow: Node, project: "Project"):
        self.node = flow
        self._project = project
        self.events: dict[str, tuple[Node, Node]] = {}     # event ID -> (events array, event)
        for b in flow.find("blocks/array").children or []:
            arr = b.find("events")
            for e in (arr.children or []) if arr is not None else []:
                self.events[e.text("eventID")] = (arr, e)
        self.dynamic_elements: dict[str, tuple[Node, Node]] = {}   # element ID -> (array, element)
        for t in flow.find("elementTables/array").children or []:
            if t.tag == "DynamicGroupElementTableDefinition":
                arr = t.find("array")
                for el in arr.children or []:
                    self.dynamic_elements[el.text("elementID")] = (arr, el)

    # ------------------------------------------------------------------ read
    def event(self, event_id: str) -> Node | None:
        hit = self.events.get(event_id)
        return hit[1] if hit else None

    def event_content(self, event_id: str) -> tuple | None:
        e = self.event(event_id)
        return None if e is None else canon(e)

    def dynamic_group_content(self, event_id: str) -> tuple | None:
        """A dynamics-group event (without its position) with its element, without IDs: equal for
        two groups that would look and play the same."""
        e = self.event(event_id)
        if e is None or e.tag != "DynamicGroupEventDefinition":
            return None
        el = self.dynamic_elements.get(e.text("dynamicGroupID"))
        if el is None:
            return None
        return canon(e, frozenset({"position"})), canon(el[1])

    # ----------------------------------------------------------------- change
    @staticmethod
    def _refs(el: Node) -> list[str]:
        return [x for x in (el.text("referencingEventIDs") or "").split(",") if x]

    @staticmethod
    def _set_refs(el: Node, refs: list[str]) -> None:
        el.child("referencingEventIDs").value = ",".join(refs)

    def _unref(self, elem_id: str, event_id: str) -> None:
        """Take an event off an element; an element nothing refers to any more is removed
        (element IDs with gaps are normal in Dorico's own files)."""
        arr, el = self.dynamic_elements[elem_id]
        refs = [r for r in self._refs(el) if r != event_id]
        if refs:
            self._set_refs(el, refs)
        else:
            arr.children.remove(el)
            del self.dynamic_elements[elem_id]

    def remove_event(self, event_id: str) -> None:
        arr, e = self.events.pop(event_id)
        arr.children.remove(e)
        if e.tag == "DynamicGroupEventDefinition":
            self._unref(e.text("dynamicGroupID"), event_id)
        self._project.changed = True

    def link_dynamic_group(self, event_id: str, elem_id: str) -> None:
        """Make a dynamics-group event use another element: Dorico's linked dynamics (one
        element, `referencingEventIDs` listing every event)."""
        e = self.event(event_id)
        old = e.text("dynamicGroupID")
        if old == elem_id:
            return
        self._unref(old, event_id)
        e.child("dynamicGroupID").value = elem_id
        el = self.dynamic_elements[elem_id][1]
        self._set_refs(el, self._refs(el) + [event_id])
        self._project.changed = True


class Project:
    """An open project: zip entries + decoded score + per-flow edit indexes."""

    def __init__(self, data: bytes, path: str = ""):
        self.path = path
        self.data = data
        self.entries = container.read_bytes(data)
        self.doc: Document = container.score(self.entries)
        self.flows = [FlowEdit(f, self) for f in self.doc.root.find("flows/array").children or []]
        self.changed = False

    @classmethod
    def open(cls, path: str | os.PathLike) -> "Project":
        return cls(Path(path).read_bytes(), str(path))

    def to_bytes(self) -> bytes:
        """The project as bytes: the original, byte for byte, when nothing changed."""
        if not self.changed:
            return self.data
        problems = ids.check(self.doc)
        if problems:
            raise RuntimeError("edited score has ID problems: " + "; ".join(problems))
        container.set_score(self.entries, self.doc)
        return container.to_bytes(self.entries)

    def save(self, dest: str | os.PathLike, protect: str | os.PathLike | None = None) -> None:
        """Write to `dest` atomically; refuses to write over `protect` (pass the source)."""
        dest = Path(dest)
        if protect is not None and dest.resolve() == Path(protect).resolve():
            raise ValueError("refusing to overwrite the source project; write a new file")
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_bytes(self.to_bytes())
        os.replace(tmp, dest)
