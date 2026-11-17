"""The one read model of a Dorico score (engine/crates/dorico-model), for Python tools.

    score = model.read("Cue.dorico")          # plain dicts/lists, positions as Fractions
    for flow in score["flows"]:
        for bar in flow["bars"]: ...           # index, start, length, num, den, irregular
        for part in flow["parts"]:             # one per instrument of a player
            for v in part["voices"]: v["notes"], v["marks"]
            for s in part["staves"]: s["dynamics"], s["marks"]

Shapes are documented on the Rust types in engine/crates/dorico-model/src/lib.rs. This is a
plain-data view during the transition; typed Python classes can follow when tools move onto it.
"""
from __future__ import annotations

import json
import os
from fractions import Fraction
from pathlib import Path

from . import _native

__all__ = ["read", "read_bytes"]

# keys whose values are positions/durations ("81/4") -> Fraction
_RATIO_KEYS = {"pos", "dur", "end", "start", "length", "pickup", "unit"}


def _convert(x, key=None):
    if isinstance(x, dict):
        return {k: _convert(v, k) for k, v in x.items()}
    if isinstance(x, list):
        if key in ("key_changes", "rehearsal_marks", "segments", "equation"):
            return [Fraction(v) for v in x]
        return [_convert(v) for v in x]
    if key in _RATIO_KEYS and isinstance(x, str):
        return Fraction(x)
    return x


def read_bytes(data: bytes) -> dict:
    return _convert(json.loads(_native.model_json(data)))


def read(path: str | os.PathLike) -> dict:
    return read_bytes(Path(path).read_bytes())
