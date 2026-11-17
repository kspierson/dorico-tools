"""A checking view of a Dorico project: staves with their notes, dynamics groups (with element
and event IDs, so linked items are visible), techniques, trills and slurs; bars as Dorico numbers
them. Used by the reviewer, the cleaner and any tool's checks (doricokit.review / clean).

    from doricokit import view
    p = view.read_project("Score.dorico")     # or view.read_bytes(data)
    for fl in p.flows: for st in fl.staves: ...

Positions are Fractions in crotchets from the flow start. A thin layer over the shared read
model (`doricokit.model`, engine/crates/dorico-model). Moved here from finale2dorico's
f2d/dorico/read.py (2026-10-31); f2d re-exports it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from . import model

F = Fraction


@dataclass
class Note:
    pos: Fraction
    dur: Fraction
    pitch: int
    grace: bool = False
    props: dict = field(default_factory=dict)
    event: str = ""                # event ID


@dataclass
class DynItem:
    pos: Fraction                  # absolute
    kind: str                      # "dynamic" / "hairpin" / "combined" / "force"
    level: str = ""                # e.g. "mf", "fp", "sfz", "cresc"
    end: Fraction | None = None    # hairpins


@dataclass
class DynGroup:
    pos: Fraction
    element: str                   # element ID (shared = linked)
    linked: int                    # number of staves sharing the element
    items: list[DynItem] = field(default_factory=list)
    event: str = ""                # event ID (the cleaner edits by it)

    def signature(self) -> tuple:
        return tuple((i.pos - self.pos, i.kind, i.level, (i.end - self.pos) if i.end else None)
                     for i in self.items)


@dataclass
class Staff:
    player: str                    # readable player name ("Trumpet (B♭)": the model's label)
    instrument: str                # Dorico entity ID
    index: int
    voices: list[list[Note]] = field(default_factory=list)
    dynamics: list[DynGroup] = field(default_factory=list)
    techniques: list[tuple[Fraction, str]] = field(default_factory=list)
    trills: list[tuple[Fraction, Fraction]] = field(default_factory=list)
    slurs: list[tuple[Fraction, Fraction]] = field(default_factory=list)
    divisi: int | None = None      # divisi staves: 0-based divisi index (the main staff is None)
    # trills and techniques with their event IDs: (kind, pos, detail, event ID); for the cleaner
    marks: list[tuple[str, Fraction, object, str]] = field(default_factory=list)
    stave_id: str = ""             # Dorico stave ID

    @property
    def label(self) -> str:
        # Dorico gives every divisi staff index 0; the original staff counts as division 1
        return (self.player + (f" (staff {self.index + 1})" if self.index else "")
                + (f" (divisi staff {self.divisi + 2})" if self.divisi is not None else ""))

    def notes(self) -> list[Note]:
        return [n for v in self.voices for n in v if not n.grace]


@dataclass
class Flow:
    name: str
    length: Fraction
    bars: list[tuple[Fraction, Fraction, int, int]]  # (start, length, numerator, denominator)
    staves: list[Staff] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)  # bar numbers as Dorico shows them ("0", "35a")
    id: str = ""                                      # Dorico flow ID

    def bar_beat(self, pos: Fraction) -> tuple[int, Fraction]:
        """1-based bar index (into `bars`) and beat (in the time signature's beat unit, 1-based)."""
        for i, (start, length, _num, den) in enumerate(self.bars):
            if start <= pos < start + length or i == len(self.bars) - 1:
                return i + 1, 1 + (pos - start) * den / 4
        return 1, F(1)

    def bar_label(self, pos: Fraction) -> str:
        """The bar number Dorico shows at `pos` ("12", "35a", pick-up "0")."""
        bar, _ = self.bar_beat(pos)
        return self.labels[bar - 1] if bar <= len(self.labels) else str(bar)

    def where(self, pos: Fraction) -> str:
        """"bar 12 beat 3" with the bar number Dorico shows (pick-up = 0, bar-number changes)."""
        _, beat = self.bar_beat(pos)
        b = f"{beat.numerator}" if beat.denominator == 1 else f"{float(beat):.3g}"
        return f"bar {self.bar_label(pos)} beat {b}"


@dataclass
class Project:
    path: str
    title: str
    flows: list[Flow]
    # entity ID -> {"name", "standard_range", "advanced_range"} (concert pitch, e.g. "C4-C7")
    instruments: dict[str, dict]


def read_project(path: str | Path) -> Project:
    return from_model(model.read(path), str(path))


def read_bytes(data: bytes, path: str = "") -> Project:
    return from_model(model.read_bytes(data), path)


def from_model(score: dict, path: str = "") -> Project:
    return Project(path=path, title=score["title"], flows=[_flow(f) for f in score["flows"]],
                   instruments=score["instruments"])


def _flow(fl: dict) -> Flow:
    staves = []
    for p in fl["parts"]:
        by_id: dict[str, Staff] = {}
        by_index: dict[int, Staff] = {}
        for s in p["staves"]:
            st = Staff(player=p["player_label"], instrument=p["entity"], index=s["index"], divisi=s["divisi"],
                       stave_id=s["stave_id"])
            st.dynamics = [_dyn_group(g) for g in s["dynamics"]]
            by_id[s["stave_id"]] = st
            by_index.setdefault(st.index, st)
            staves.append(st)
        for v in p["voices"]:
            st = by_id.get(v["stave_id"]) or by_index.get(v["stave_index"])
            if st is None:
                continue
            st.voices.append([Note(n["pos"], n["dur"], n["pitch"], n["grace"], n["props"], n["event_id"])
                              for n in v["notes"]])
            for m in v["marks"]:
                end = m["end"] if m["end"] is not None else m["pos"]
                if m["kind"] == "trill":
                    st.trills.append((m["pos"], end))
                    st.marks.append(("trill", m["pos"], (m["pos"], end), m["event_id"]))
                elif m["kind"] == "slur":
                    st.slurs.append((m["pos"], end))
                elif m["kind"] == "technique":
                    st.techniques.append((m["pos"], m["detail"].get("appearance", "")))
                    st.marks.append(("technique", m["pos"], m["detail"].get("appearance", ""), m["event_id"]))
    bars = [(b["start"], b["length"], b["num"], b["den"]) for b in fl["bars"]]
    return Flow(name=fl["name"], length=fl["length"], bars=bars, staves=staves,
                labels=[b["label"] for b in fl["bars"]], id=fl["id"])


def _dyn_group(g: dict) -> DynGroup:
    # force dynamics carry their intensity separately ("sfz" + "2" -> "sfz2", as before)
    return DynGroup(pos=g["pos"], element=g["element_id"], linked=g["linked"], event=g["event_id"],
                    items=[DynItem(i["pos"], i["kind"], i["level"] + (i["extra"] if i["kind"] == "force" else ""),
                                   i["end"]) for i in g["items"]])
