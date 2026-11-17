"""Small helpers for building Dorico score trees (dtn.Node) by hand."""
from __future__ import annotations

from fractions import Fraction

from doricokit.format import Node


def fstr(x) -> str:
    """Dorico writes times as exact fractions: '0', '3/2', '17/2'."""
    if isinstance(x, Fraction):
        return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"
    if isinstance(x, bool):
        return "true" if x else "false"
    return str(x)


def L(tag: str, value="") -> Node:
    """Leaf."""
    return Node(tag, value=fstr(value))


def E(tag: str, *children: Node | None) -> Node:
    """Element with children (None children are dropped). No children -> empty leaf."""
    kids = [c for c in children if c is not None]
    if not kids:
        return Node(tag, value="")
    return Node(tag, children=kids)


def A(tag: str, items: list[Node]) -> Node:
    """Array element. An empty array is a leaf with the array flag."""
    if not items:
        return Node(tag, value="", array=True)
    return Node(tag, children=list(items), array=True)


def svl(*parts: str) -> str:
    """steamVariantList value: svl('{int: 1}', '{}') -> 'steamVariantList:list: {int: 1}, {}'."""
    return "steamVariantList:list: " + ", ".join(parts)


NO_LAYOUT = svl("{int: -1}", "{int: -1}", "{bool: false}")


def prop(ptype: str, value: str, context: bool = False, offset: str = "0:0:1:0") -> Node:
    kids = [L("propertyType", ptype), L("value", value)]
    if context:
        kids.append(E("context",
                      L("layoutIDWithFrameChainID", NO_LAYOUT),
                      L("blockInstanceID", -1),
                      L("propertyOffset", f'string: "{offset}"')))
    return E("entry", *kids)


def ptable(entries: list[Node], tag: str = "propertyTable") -> Node:
    return E(tag, A("entries", entries))


def event_head(tag: str, eid: int, pos, dur, props: list[Node] | None = None,
               secondary_pos="0") -> list[Node]:
    return [L("eventID", eid), L("position", pos), L("secondaryPosition", secondary_pos),
            L("duration", dur), L("secondaryEndOffset", 0), ptable(props or [])]


def deep_copy(n: Node) -> Node:
    if n.children is None:
        return Node(n.tag, value=n.value, array=n.array)
    return Node(n.tag, array=n.array, children=[deep_copy(c) for c in n.children])


def rename(n: Node, tag: str) -> Node:
    c = deep_copy(n)
    c.tag = tag
    return c
