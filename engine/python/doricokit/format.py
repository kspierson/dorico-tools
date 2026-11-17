"""Dorico's score tree: the binary DTN format (score.dtn, scorelibrary.dtn) and its XML text
form (score.xml), backed by the Rust codec in engine/crates/dorico-format.

Drop-in replacement for the old `dtn.py` copies (same `Node`, `Document`, `decode`, `encode`,
`to_xml`, `from_xml`). Import it under that name to keep code unchanged:

    from doricokit import format as dtn

`Node` and `Document` are plain Python objects that tools may edit in place. A node is a leaf
(`value` is a str, `children` is None) or an element (`children` is a list, `value` is None).
DTN rule: an element never has zero children; an empty array is a leaf with value "" and
`array=True`.

Format notes: dorigit/docs/RESEARCH.md (to be merged into engine/docs/FORMAT.md).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import _native

DTN_VERSION: int = _native.DTN_VERSION
MARKER_PI: str = _native.MARKER_PI

__all__ = ["DTN_VERSION", "MARKER_PI", "Document", "Node", "decode", "encode", "from_xml", "to_xml"]


@dataclass(slots=True)
class Node:
    tag: str
    value: str | None = None  # set for leaves
    array: bool = False
    children: list["Node"] | None = None  # set for elements

    # --- small helpers for walking the tree -------------------------------
    def child(self, tag: str) -> "Node | None":
        for c in self.children or ():
            if c.tag == tag:
                return c
        return None

    def text(self, tag: str, default: str = "") -> str:
        c = self.child(tag)
        return c.value if c is not None and c.value is not None else default

    def find(self, path: str) -> "Node | None":
        n: Node | None = self
        for part in path.split("/"):
            n = n.child(part) if n else None
        return n

    def items(self) -> list["Node"]:
        """Children of an array container (or [] if missing / empty)."""
        return list(self.children or ())


@dataclass(slots=True)
class Document:
    root: Node
    marker: int = 0  # per-file bits of every DTN node type byte; meaning unknown, preserved


def decode(data: bytes) -> Document:
    """score.dtn / scorelibrary.dtn bytes -> tree. Raises ValueError on malformed data."""
    return _native.dtn_decode(data, Node, Document)


def encode(doc: Document) -> bytes:
    """Tree -> DTN bytes (byte-identical to Dorico's for unchanged trees)."""
    return _native.dtn_encode(doc)


def to_xml(doc: Document, with_marker: bool = True) -> str:
    """Tree -> XML text in Dorico's score.xml layout. `with_marker` keeps the DTN marker in a
    processing instruction so `encode(from_xml(to_xml(d)))` is lossless."""
    return _native.xml_write(doc, with_marker)


def from_xml(text: bytes | str) -> Document:
    if isinstance(text, str):
        text = text.encode("utf-8")
    return _native.xml_read(text, Node, Document)
