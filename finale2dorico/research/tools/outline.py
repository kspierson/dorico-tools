"""Outline a Dorico XML tree: tags, sizes, array lengths (first item expanded).

    python3 tools/outline.py score.xml [path/inside] [maxdepth]
"""
import sys
import xml.etree.ElementTree as ET

def size(e):
    return sum(1 for _ in e.iter())

def show(e, depth, maxdepth, indent=""):
    kids = list(e)
    if not kids:
        v = (e.text or "").strip()
        print(f"{indent}{e.tag} = {v[:70]!r}")
        return
    arr = e.get("array") == "true"
    print(f"{indent}{e.tag}{'[]' if arr else ''}  ({len(kids)} children, {size(e)} nodes)")
    if depth >= maxdepth:
        return
    seen = {}
    for c in kids:
        seen[c.tag] = seen.get(c.tag, 0) + 1
        if seen[c.tag] == 1:
            show(c, depth + 1, maxdepth, indent + "  ")
    for tag, n in seen.items():
        if n > 1:
            print(f"{indent}  ... {tag} x{n}")

root = ET.parse(sys.argv[1]).getroot()
node = root
if len(sys.argv) > 2 and sys.argv[2] not in ("", "."):
    node = root.find(sys.argv[2])
show(node, 0, int(sys.argv[3]) if len(sys.argv) > 3 else 2)
