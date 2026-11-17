"""dorigit's listing model (engine/crates/dorico-format/src/model.rs), for Python research tools.

    score = listing.read("Cue.dorico")
    score["players"]                 # {playerID: name}, in score order
    score["options"], ["layouts"]    # flattened settings {path: value}
    for flow in score["flows"]:      # flow_id, name, meters, events
        for e in flow["events"]:     # flow, owner, lane, kind, position (Fraction), where,
            ...                      # bar, text, props, event_id

This is the model behind `dorigit show`/`diff` (one row per event, located by bar and beat),
not the read model in `doricokit.model`. Used by dorigit/research/merge_probe.py.
"""
from __future__ import annotations

import json
import os
from fractions import Fraction
from pathlib import Path

from . import _native

__all__ = ["read", "read_bytes"]


def _flow(f: dict) -> dict:
    for e in f["events"]:
        e["position"] = Fraction(e["position"])
    for m in f["meters"]:
        for k in ("start", "length", "beat"):
            m[k] = Fraction(m[k])
    return f


def read_bytes(data: bytes) -> dict:
    s = json.loads(_native.listing_json(data))
    return {
        "info": dict(s["info"]["entries"]),
        "players": dict(s["players"]),
        "flows": [_flow(f) for f in s["flows"]],
        "options": dict(s["options"]["entries"]),
        "layouts": dict(s["layouts"]["entries"]),
    }


def read(path: str | os.PathLike) -> dict:
    return read_bytes(Path(path).read_bytes())
