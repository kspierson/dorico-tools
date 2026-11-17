"""TEST ORACLE ONLY (Project S): the old pure-Python DTN codec, kept to check the Rust codec
(engine/tests/parity/codec_vs_python.py). Tools use `doricokit.format`. Do not import from tools.
Moved here from dorico-hp/doricohp/dtn.py on 2026-10-29 (S2); originally dorigit/prototype/dorigit/dtn.py.

Read and write Dorico's binary DTN format (score.dtn, scorelibrary.dtn).

DTN is a compact binary encoding of an XML-like tree. The same tree is what
Dorico writes as score.xml in some projects. Layout, all little-endian:

    u32 version (always 4)
    u32 unknown (always 1)
    u32 nKeys,   then nKeys   NUL-terminated UTF-8 strings  -- tag names
    u32 nValues, then nValues NUL-terminated UTF-8 strings  -- text values
    u32 nNodes,  then nNodes node records, stored in pre-order (node 0 = root)

Each node record is one type byte followed by LEB128 varints:

    type & 0b10 == 0   leaf:     key, value
    type & 0b10 != 0   element:  key, 0, nChildren, child node indices...
    type & 0b01        the node carries array="true"
    type >> 2          a per-file marker, identical for every node in a file.
                       Its meaning is unknown; we keep it so files rebuild
                       byte-for-byte.

String tables are in first-use order (pre-order walk), except that the empty
string is always value 0. Elements never have zero children: an empty array is
a leaf with value "" and the array flag set.
"""
from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

DTN_VERSION = 4


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
    marker: int = 0  # see module docstring


# --------------------------------------------------------------------------
# Binary <-> tree
# --------------------------------------------------------------------------

def decode(data: bytes) -> Document:
    p = 0

    def u32() -> int:
        nonlocal p
        (v,) = struct.unpack_from("<I", data, p)
        p += 4
        return v

    def varint() -> int:
        nonlocal p
        r = s = 0
        while True:
            b = data[p]
            p += 1
            r |= (b & 0x7F) << s
            s += 7
            if b < 0x80:
                return r

    def table() -> list[str]:
        nonlocal p
        out = []
        for _ in range(u32()):
            e = data.index(b"\0", p)
            out.append(data[p:e].decode("utf-8"))
            p = e + 1
        return out

    version = u32()
    if version != DTN_VERSION:
        raise ValueError(f"unsupported DTN version {version}")
    u32()
    keys, vals = table(), table()

    count = u32()
    types = bytearray(count)
    tags = [0] * count
    values: list[int | None] = [None] * count
    kids: list[list[int] | None] = [None] * count
    for i in range(count):
        t = data[p]
        p += 1
        types[i] = t
        tags[i] = varint()
        if t & 2:
            varint()  # always 0 in every file seen so far
            kids[i] = [varint() for _ in range(varint())]
        else:
            values[i] = varint()
    if p != len(data):
        raise ValueError(f"{len(data) - p} unexpected trailing bytes")

    nodes = [
        Node(keys[tags[i]], vals[values[i]] if kids[i] is None else None, bool(types[i] & 1))
        for i in range(count)
    ]
    seen = bytearray(count)
    for i, ks in enumerate(kids):
        if ks is not None:
            nodes[i].children = [nodes[k] for k in ks]
            for k in ks:
                seen[k] += 1
    if count and (seen[0] or any(s != 1 for s in seen[1:])):
        raise ValueError("DTN node graph is not a tree")
    markers = {t >> 2 for t in types}
    if len(markers) > 1:
        raise ValueError(f"mixed node markers {sorted(markers)}; format not understood")
    return Document(nodes[0], markers.pop() if markers else 0)


def encode(doc: Document) -> bytes:
    keys: list[str] = []
    kidx: dict[str, int] = {}
    vals: list[str] = [""]
    vidx: dict[str, int] = {"": 0}
    flat: list[tuple[Node, list[int] | None]] = []

    # iterative pre-order walk, assigning node indices as Dorico does
    def walk(root: Node) -> None:
        stack: list[tuple[Node, int | None]] = [(root, None)]
        while stack:
            n, parent_slot = stack.pop()
            if n.tag not in kidx:
                kidx[n.tag] = len(keys)
                keys.append(n.tag)
            if n.children is None and n.value not in vidx:
                vidx[n.value] = len(vals)
                vals.append(n.value)
            i = len(flat)
            flat.append((n, [] if n.children is not None else None))
            if parent_slot is not None:
                flat[parent_slot][1].append(i)
            for c in reversed(n.children or ()):
                stack.append((c, i))

    walk(doc.root)
    out = bytearray(struct.pack("<II", DTN_VERSION, 1))
    for tbl in (keys, vals):
        out += struct.pack("<I", len(tbl))
        for s in tbl:
            out += s.encode("utf-8") + b"\0"
    out += struct.pack("<I", len(flat))

    def varint(n: int) -> None:
        while True:
            b = n & 0x7F
            n >>= 7
            if n:
                out.append(b | 0x80)
            else:
                out.append(b)
                return

    m = doc.marker << 2
    for n, ks in flat:
        out.append(m | (1 if n.array else 0) | (2 if ks is not None else 0))
        varint(kidx[n.tag])
        if ks is None:
            varint(vidx[n.value])
        else:
            varint(0)
            varint(len(ks))
            for k in ks:
                varint(k)
    return bytes(out)


# --------------------------------------------------------------------------
# Tree <-> XML text (same layout Dorico uses for score.xml)
# --------------------------------------------------------------------------

MARKER_PI = "dorigit-dtn-marker"


def to_xml(doc: Document, with_marker: bool = True) -> str:
    out = ['<?xml version="1.0" encoding="utf-8"?>\n']
    if with_marker:
        out.append(f"<?{MARKER_PI} {doc.marker}?>\n")
    stack: list[tuple[Node, int, bool]] = [(doc.root, 0, False)]
    while stack:
        n, depth, closing = stack.pop()
        ind = "\t" * depth
        if closing:
            out.append(f"{ind}</{n.tag}>\n")
            continue
        attr = ' array="true"' if n.array else ""
        if n.children is None:
            if n.value:
                v = escape(n.value).replace("\r", "&#13;")
                out.append(f"{ind}<{n.tag}{attr}>{v}</{n.tag}>\n")
            else:
                out.append(f"{ind}<{n.tag}{attr}/>\n")
        else:
            out.append(f"{ind}<{n.tag}{attr}>\n")
            stack.append((n, depth, True))
            for c in reversed(n.children):
                stack.append((c, depth + 1, False))
    return "".join(out)


def from_xml(text: bytes | str) -> Document:
    if isinstance(text, str):
        text = text.encode("utf-8")
    marker = 0
    head = text[:200].decode("utf-8", "replace")
    tag = f"<?{MARKER_PI} "
    if tag in head:
        marker = int(head.split(tag, 1)[1].split("?>", 1)[0])

    def conv(e: ET.Element) -> Node:
        arr = e.get("array") == "true"
        if len(e):
            return Node(e.tag, None, arr, [conv(c) for c in e])
        return Node(e.tag, e.text or "", arr)

    return Document(conv(ET.fromstring(text)), marker)
