"""IDs in a score (backed by engine/crates/dorico-format/src/ids.rs).

`idGenerators/<kind>` holds the next free ID of each kind. `check(doc)` lists counters that are
not ahead of the IDs in use (new items would collide); an empty list means fine.
"""
from __future__ import annotations

from . import _native
from .format import Document

__all__ = ["check"]


def check(doc: Document) -> list[str]:
    return _native.ids_check(doc)
