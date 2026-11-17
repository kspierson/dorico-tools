"""Read a .dorico project, change its playback data, write a new .dorico.

What we write (all of it shows up in Dorico's Play mode and can be edited there):

  note velocity        NoteEventDefinition property  kNoteVelocity = "int: 0..127"
  played start / end   NoteEventDefinition properties kEventPlayStartOffset /
                       kEventPlayEndOffset = "int: <ticks>" (Play mode "Played durations" edits;
                       480 ticks per crotchet, confirmed by test H). The kEventRecorded*
                       variants hold MIDI-recorded timing and are not what Play mode edits.
  controller curves    AutomationEventDefinition events in a kAutomationStream, one stream
                       per instrument, registered in the flow's automationStreamTable as
                       "kIRV:<instrumentID>:-1". Points that belong to one drawn line share
                       a kEventGroupId.

New IDs come from the score's idGenerators counters, which hold the next free value.
Positions are exact Fractions in crotchets from the start of the flow.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Iterator

from doricokit import container
from doricokit import format as dtn
from doricokit.format import Node

VELOCITY = "kNoteVelocity"
PLAY_START = "kEventPlayStartOffset"
PLAY_END = "kEventPlayEndOffset"
RECORDED_START = "kEventRecordedPlayStartOffset"
RECORDED_END = "kEventRecordedPlayEndOffset"
GROUP = "kEventGroupId"
# Positions are exact Fractions; parsing/formatting and the tick unit (480 per crotchet, the unit
# of the play offsets) come from the shared engine (Project S, S3).
from doricokit.positions import TICKS_PER_CROTCHET, frac, frac_str  # noqa: E402,F401


# ---------------------------------------------------------------------------
# Tree helpers that respect DTN's rules (an element never has zero children:
# an empty array is a leaf with value "" and the array flag).
# ---------------------------------------------------------------------------

def leaf(tag: str, value: str) -> Node:
    return Node(tag, value)


def elem(tag: str, *children: Node, array: bool = False) -> Node:
    return Node(tag, None, array, list(children))


def items(n: Node | None) -> list[Node]:
    return list(n.children or ()) if n is not None else []


def append_child(parent: Node, child: Node) -> None:
    if parent.children is None:
        parent.value = None
        parent.children = []
    parent.children.append(child)


def remove_children(parent: Node, pred) -> int:
    if not parent.children:
        return 0
    keep = [c for c in parent.children if not pred(c)]
    removed = len(parent.children) - len(keep)
    if keep:
        parent.children = keep
    else:
        parent.children = None
        parent.value = ""
    return removed


def array_of(n: Node | None) -> list[Node]:
    """Children of an `x/array` container or of an array node itself."""
    if n is None:
        return []
    a = n.child("array")
    return items(a if a is not None else n)


# ---------------------------------------------------------------------------
# Properties on events
# ---------------------------------------------------------------------------

def _entries(ev: Node, create: bool) -> Node | None:
    pt = ev.child("propertyTable")
    if pt is None:
        if not create:
            return None
        pt = elem("propertyTable", leaf("entries", ""))
        pt.children[0].array = True
        # propertyTable sits after secondaryEndOffset in every event we've seen
        idx = next((i + 1 for i, c in enumerate(ev.children) if c.tag == "secondaryEndOffset"),
                   len(ev.children))
        ev.children.insert(idx, pt)
    return pt.child("entries")


def get_prop(ev: Node, ptype: str) -> str | None:
    for e in items(_entries(ev, False)):
        if e.text("propertyType") == ptype and e.child("context") is None:
            return e.text("value")
    return None


def get_int_prop(ev: Node, ptype: str) -> int | None:
    v = get_prop(ev, ptype)
    if v and v.startswith("int: "):
        return int(v[5:])
    return None


def set_prop(ev: Node, ptype: str, value: str | None) -> None:
    """Set (or with None, remove) an unscoped property."""
    entries = _entries(ev, value is not None)
    if entries is None:
        return
    remove_children(entries, lambda e: e.text("propertyType") == ptype and e.child("context") is None)
    if value is not None:
        append_child(entries, elem("entry", leaf("propertyType", ptype), leaf("value", value)))


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

@dataclass
class NoteRef:
    node: Node
    position: Fraction      # absolute, crotchets from flow start
    duration: Fraction
    pitch: int
    voice_stream: str
    grace: bool = False

    @property
    def event_id(self) -> str:
        return self.node.text("eventID")

    @property
    def end(self) -> Fraction:
        return self.position + self.duration


@dataclass
class InstrumentRef:
    instrument_id: str
    player_id: str
    player_name: str
    voice_streams: list[str]
    stave_streams: list[str]


class Project:
    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.entries = container.read(self.path)  # every zip entry, kept for save()
        self.doc = container.score(self.entries)  # score.dtn (or score.xml)
        self.root = self.doc.root

    def entry(self, name: str) -> bytes | None:
        """Raw bytes of another file in the project (e.g. "scorelibrary.dtn")."""
        return next((e.data for e in self.entries if e.name == name), None)

    # -- saving ----------------------------------------------------------
    def save(self, dest: str | os.PathLike) -> None:
        container.set_score(self.entries, self.doc)
        container.write(dest, self.entries, protect=self.path)

    # -- ids ---------------------------------------------------------------
    def new_id(self, kind: str) -> int:
        """kind: event, eventStream, block, blockInstance, eventGroup, ..."""
        n = self.root.find(f"idGenerators/{kind}")
        if n is None:
            raise KeyError(f"no idGenerators/{kind}")
        v = int(n.value)
        n.value = str(v + 1)
        return v

    # -- structure -----------------------------------------------------------
    def flows(self) -> list[Node]:
        return array_of(self.root.child("flows"))

    def player_names(self) -> dict[str, str]:
        out = {}
        for p in array_of(self.root.child("scorePlayers")):
            out[p.text("playerID")] = p.text("displayName") or p.text("baseName") or f"player {p.text('playerID')}"
        return out

    def instruments(self, flow: Node) -> list[InstrumentRef]:
        names = self.player_names()
        out = []
        for fp in array_of(flow.child("flowPlayers")):
            pid = fp.text("playerID")
            for inst in items(fp.child("flowPlayerInstruments")):
                out.append(InstrumentRef(
                    inst.text("instrumentID"), pid, names.get(pid, pid),
                    [v.text("voiceStreamID") for v in items(inst.child("voiceStreamInfos"))],
                    [s.text("staveStreamID") for s in items(inst.child("staveStreamInfos"))]))
        return out

    def _streams(self, flow: Node) -> dict[str, Node]:
        return {s.text("streamID"): s for s in array_of(flow.child("eventStreams"))}

    def _blocks(self, flow: Node) -> dict[str, Node]:
        return {b.text("blockID"): b for b in array_of(flow.child("blocks"))}

    def _instances(self, flow: Node) -> dict[str, Node]:
        return {b.text("blockInstanceID"): b for b in array_of(flow.child("blockInstances"))}

    def stream_events(self, flow: Node, stream_id: str) -> Iterator[tuple[Fraction, Node]]:
        """(absolute position, event node) for every event placed on a stream."""
        stream = self._streams(flow).get(stream_id)
        if stream is None:
            return
        blocks, inst = self._blocks(flow), self._instances(flow)
        bi_ids = stream.child("blockInstanceIDs")
        ids = [c.value for c in bi_ids.children] if bi_ids.children else (bi_ids.value or "").split()
        for bid in ids:
            bi = inst.get(bid)
            if bi is None:
                continue
            base = frac(bi.text("position"))
            block = blocks.get(bi.text("blockID"))
            for ev in items(block.child("events")) if block is not None else ():
                yield base + frac(ev.text("position")), ev

    def notes(self, flow: Node, inst: InstrumentRef) -> list[NoteRef]:
        out = []
        for vs in inst.voice_streams:
            for pos, ev in self.stream_events(flow, vs):
                if ev.tag in ("NoteEventDefinition", "GraceNoteEventDefinition"):
                    out.append(NoteRef(ev, pos, frac(ev.text("duration")), int(ev.text("pitch") or 0), vs,
                                       ev.tag.startswith("Grace")))
        out.sort(key=lambda n: (n.position, n.pitch))
        return out

    # -- automation ----------------------------------------------------------
    def automation_block(self, flow: Node, instrument_id: str, create: bool = True) -> Node | None:
        """The events container of an instrument's automation stream (made if missing)."""
        target = f"kIRV:{instrument_id}:-1"
        table = flow.child("automationStreamTable")
        if table is None:
            if not create:
                return None
            table = elem("automationStreamTable", leaf("entries", ""))
            table.children[0].array = True
            flow.children.append(table)
        entries = table.child("entries")
        sid = next((e.text("streamID") for e in items(entries) if e.text("automationTarget") == target), None)
        if sid is not None:
            bi = self._streams(flow)[sid].text("blockInstanceIDs")
            block = self._blocks(flow)[self._instances(flow)[bi].text("blockID")]
            ev = block.child("events")
            if ev is None:
                ev = leaf("events", "")
                ev.array = True
                block.children.append(ev)
            return ev
        if not create:
            return None
        sid = str(self.new_id("eventStream"))
        block_id = str(self.new_id("block"))
        bi_id = str(self.new_id("blockInstance"))
        events = leaf("events", "")
        events.array = True
        flow.find("blocks/array").children.append(
            elem("block", leaf("blockID", block_id), leaf("parentEventStreamType", "kAutomationStream"), events))
        flow.find("blockInstances/array").children.append(
            elem("blockInstance", leaf("blockInstanceID", bi_id), leaf("blockID", block_id),
                 leaf("streamID", sid), leaf("position", "0")))
        flow.find("eventStreams/array").children.append(
            elem("eventStream", leaf("streamID", sid), leaf("blockInstanceIDs", bi_id),
                 leaf("eventStreamType", "kAutomationStream")))
        append_child(entries, elem("entry", leaf("automationTarget", target), leaf("streamID", sid)))
        return events

    def automation_points(self, flow: Node, instrument_id: str) -> list[tuple[Fraction, str, float, str, int | None]]:
        """(position, controller, value, interpolation, group) for an instrument."""
        ev = self.automation_block(flow, instrument_id, create=False)
        out = []
        for e in items(ev):
            if e.tag != "AutomationEventDefinition":
                continue
            d = e.child("data")
            out.append((frac(e.text("position")), d.text("controllerDefinition"), float(d.text("value") or 0),
                        d.text("type"), get_int_prop(e, GROUP)))
        return out

    def add_curve(self, flow: Node, instrument_id: str, controller: str,
                  points: list[tuple[Fraction, float]], hold_last: bool = True) -> int:
        """Add one drawn line of controller points; returns its event group id.

        controller: "kMIDICC:1" style, or "kDynamic" for the Dynamics lane (test I, 2026-11-01:
        same stream, values are absolute Dorico dynamic levels, may be negative; inside a
        drawn span they replace Dorico's own dynamics, humanise and beat stress included).
        The last point is a step ('kConstant') when hold_last is set, which is how Dorico
        ends the lines it draws.
        """
        lo, hi = (-12.0, 12.0) if controller == "kDynamic" else (0.0, 127.0)
        events = self.automation_block(flow, instrument_id)
        group = self.new_id("eventGroup")
        for i, (pos, value) in enumerate(points):
            kind = "kConstant" if hold_last and i == len(points) - 1 else "kLinear"
            ev = elem("AutomationEventDefinition",
                      leaf("eventID", str(self.new_id("event"))),
                      leaf("position", frac_str(pos)), leaf("secondaryPosition", "0"),
                      leaf("duration", "0"), leaf("secondaryEndOffset", "0"),
                      elem("propertyTable", elem("entries", elem("entry", leaf("propertyType", GROUP),
                                                                 leaf("value", f"int: {group}")), array=True)),
                      elem("data", leaf("controllerDefinition", controller),
                           leaf("value", f"{max(lo, min(hi, value)):.6f}"), leaf("type", kind)))
            append_child(events, ev)
        if events.children:
            events.children.sort(key=lambda e: frac(e.text("position")))
        return group

    def remove_curves(self, flow: Node, instrument_id: str, groups: set[int]) -> int:
        events = self.automation_block(flow, instrument_id, create=False)
        if events is None:
            return 0
        return remove_children(events, lambda e: get_int_prop(e, GROUP) in groups)
