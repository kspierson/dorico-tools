"""The `.dorico` container (a zip), backed by the Rust code in engine/crates/dorico-format.

    entries = container.read(path)            # list[Entry], in zip order
    doc = container.score(entries)            # score.dtn or score.xml -> format.Document
    doc = container.open_score(path)          # the same in one step (read-only use)
    container.write(dest, entries)            # atomic; refuses to overwrite `protect`

Entries keep their name, timestamp and stored/deflated choice, so rewriting a project changes
only the entries you replace.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import _native
from . import format as dtn

__all__ = ["Entry", "open_score", "read", "read_bytes", "score", "set_score", "to_bytes", "write"]


@dataclass(slots=True)
class Entry:
    name: str
    data: bytes
    is_dir: bool = False
    time: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0)
    deflated: bool = True


def read_bytes(data: bytes) -> list[Entry]:
    return [Entry(*t) for t in _native.zip_read(data)]


def read(path: str | os.PathLike) -> list[Entry]:
    return read_bytes(Path(path).read_bytes())


def to_bytes(entries: list[Entry]) -> bytes:
    return _native.zip_write([(e.name, e.data, e.is_dir, tuple(e.time), e.deflated) for e in entries])


def write(dest: str | os.PathLike, entries: list[Entry], protect: str | os.PathLike | None = None) -> None:
    """Write a .dorico atomically (temp file + rename). Refuses to write over `protect`
    (pass the source project: tools never overwrite the user's file)."""
    dest = Path(dest)
    if protect is not None and dest.resolve() == Path(protect).resolve():
        raise ValueError("refusing to overwrite the source project; write a new file")
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(to_bytes(entries))
    os.replace(tmp, dest)


def _find(entries: list[Entry], name: str) -> Entry | None:
    return next((e for e in entries if e.name == name), None)


def score(entries: list[Entry], part: str = "score") -> dtn.Document:
    """Decode `score` (or `scorelibrary`), stored as .dtn or .xml."""
    e = _find(entries, f"{part}.dtn")
    if e is not None:
        return dtn.decode(e.data)
    e = _find(entries, f"{part}.xml")
    if e is not None:
        return dtn.from_xml(e.data)
    raise KeyError(f"project has no {part}.dtn or {part}.xml")


def open_score(path: str | os.PathLike, part: str = "score") -> dtn.Document:
    """Shortcut: read a .dorico file and decode its score (or `scorelibrary`)."""
    return score(read(path), part)


def set_score(entries: list[Entry], doc: dtn.Document, part: str = "score") -> None:
    """Re-encode `doc` into the entry it came from, in the same form (.dtn or .xml).
    XML entries are written without the marker instruction, as Dorico writes them."""
    e = _find(entries, f"{part}.dtn")
    if e is not None:
        e.data = dtn.encode(doc)
        return
    e = _find(entries, f"{part}.xml")
    if e is None:
        raise KeyError(f"project has no {part}.dtn or {part}.xml")
    e.data = dtn.to_xml(doc, with_marker=False).encode("utf-8")
