"""Time in a Dorico project (engine/crates/timeline): tempo map, performed order (repeats,
endings, D.C./D.S., Fine, Coda), seconds, timecode at any frame rate, MIDI tempo events.

    from doricokit import timeline
    t = timeline.read("Cue.dorico")
    t.seconds(0, Fraction(81, 4))         # first time crotchet 81/4 of flow 0 sounds (s)
    t.occurrences(0, pos)                 # every time it sounds: [(pass, secs, performed pos)]
    t.notated_seconds(0, pos)             # ignoring repeats
    t.at_seconds(0, 12.5)                 # -> (span, notated position as float)
    t.timecode(0, secs)                   # "01:00:06:00" (video: clip timecode), any rate
    t.tempo_events(0)                     # [(tick, crotchets/min)] as Dorico's MIDI export
    info = t.info()                       # tempo segments, spans, flow starts, caveats

Positions are Fractions in crotchets from the flow start, as in `doricokit.model`. Read
`info()["flows"][i]["caveats"]` for anything the numbers rely on that is not yet confirmed
against Dorico (engine/docs/TIMELINE.md).
"""

from __future__ import annotations

import json
import os
from fractions import Fraction
from pathlib import Path

from . import _native
from .positions import frac, frac_str

__all__ = ["Timeline", "read", "read_bytes"]


class Timeline:
    def __init__(self, native):
        self._t = native

    def info(self) -> dict:
        """Tempo segments, performed spans, durations, flow starts and caveats (plain data)."""
        return json.loads(self._t.to_json())

    def seconds(self, flow: int, pos: Fraction) -> float | None:
        return self._t.seconds(flow, frac_str(pos))

    def notated_seconds(self, flow: int, pos: Fraction) -> float:
        return self._t.notated_seconds(flow, frac_str(pos))

    def occurrences(self, flow: int, pos: Fraction) -> list[tuple[int, float, Fraction]]:
        return [(p, s, frac(c)) for p, s, c in self._t.occurrences(flow, frac_str(pos))]

    def at_seconds(self, flow: int, secs: float) -> tuple[int, float] | None:
        return self._t.at_seconds(flow, secs)

    def bpm_at(self, flow: int, pos: Fraction) -> float:
        """Crotchets per minute at `pos`."""
        return self._t.bpm_at(flow, frac_str(pos))

    def clip_time(self, flow: int, secs: float) -> float | None:
        return self._t.clip_time(flow, secs)

    def timecode(self, flow: int, secs: float) -> str | None:
        return self._t.timecode(flow, secs)

    def tempo_events(self, flow: int) -> list[tuple[int, float]]:
        """[(tick, crotchets/min)] in performed order, as Dorico's MIDI export writes them."""
        return self._t.tempo_events(flow)


def read_bytes(data: bytes) -> Timeline:
    return Timeline(_native.Timeline.from_bytes(data))


def read(path: str | os.PathLike) -> Timeline:
    return read_bytes(Path(path).read_bytes())
