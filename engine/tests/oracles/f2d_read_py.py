"""TEST ORACLE ONLY: finale2dorico's old reviewer reader (f2d/dorico/read.py before Project S
S4), kept so engine/tests/parity/model_vs_python.py can compare the shared model against it.
f2d's reviewer now reads through doricokit.model. Do not use in tools.

Read a Dorico project into a plain model for checks (used by the reviewer).

Works on any .dorico (Dorico-saved `score.dtn` or a generated `score.xml`). Positions are
Fractions in crotchets from the flow start, as everywhere in finale2dorico.

Note: dorigit (`dorico-format` model, prototype `model.py`) and dorico-hp (`notation.py`) have
their own readers; this is the third. Logged in docs/SHARED_ENGINE.md for the shared engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from doricokit import container
from doricokit.format import Node

F = Fraction


def _t(n: Node | None, tag: str, default: str = "") -> str:
    c = n.child(tag) if n is not None else None
    return c.value if c is not None and c.value is not None else default


def _props(e: Node) -> dict[str, str]:
    pt = e.child("propertyTable")
    ents = pt.children[0] if pt is not None and pt.children else None
    return {_t(x, "propertyType"): _t(x, "value") for x in (ents.children or [])} if ents else {}


@dataclass
class Note:
    pos: Fraction
    dur: Fraction
    pitch: int
    grace: bool = False
    props: dict = field(default_factory=dict)


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

    def signature(self) -> tuple:
        return tuple((i.pos - self.pos, i.kind, i.level, (i.end - self.pos) if i.end else None)
                     for i in self.items)


@dataclass
class Staff:
    player: str
    instrument: str                # Dorico entity ID
    index: int
    voices: list[list[Note]] = field(default_factory=list)
    dynamics: list[DynGroup] = field(default_factory=list)
    techniques: list[tuple[Fraction, str]] = field(default_factory=list)
    trills: list[tuple[Fraction, Fraction]] = field(default_factory=list)
    slurs: list[tuple[Fraction, Fraction]] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.player + (f" (staff {self.index + 1})" if self.index else "")

    def notes(self) -> list[Note]:
        return [n for v in self.voices for n in v if not n.grace]


@dataclass
class Flow:
    name: str
    length: Fraction
    bars: list[tuple[Fraction, Fraction, int, int]]  # (start, length, numerator, denominator)
    staves: list[Staff] = field(default_factory=list)

    def bar_beat(self, pos: Fraction) -> tuple[int, Fraction]:
        """1-based bar number and beat (in the time signature's beat unit, 1-based)."""
        for i, (start, length, _num, den) in enumerate(self.bars):
            if start <= pos < start + length or i == len(self.bars) - 1:
                return i + 1, 1 + (pos - start) * den / 4
        return 1, F(1)

    def where(self, pos: Fraction) -> str:
        bar, beat = self.bar_beat(pos)
        b = f"{beat.numerator}" if beat.denominator == 1 else f"{float(beat):.3g}"
        return f"bar {bar} beat {b}"


@dataclass
class Project:
    path: str
    title: str
    flows: list[Flow]
    instruments: dict[str, Node]   # entity ID -> library definition


_INTENSITY = {}  # (loud, mezzo, count) -> name, filled below
for n in range(1, 7):
    _INTENSITY[("1", "false", str(n))] = "p" * n
    _INTENSITY[("0", "false", str(n))] = "f" * n
_INTENSITY[("1", "true", "")] = "mp"
_INTENSITY[("0", "true", "")] = "mf"


_COMBINED = {("kDown", "1", "1"): "fp", ("kDown", "2", "1"): "ffp", ("kDown", "1", "2"): "fpp",
             ("kUp", "1", "1"): "pf"}


def _level(intensity: str) -> str:
    # steamVariantList:list: {int: L}, {}, {bool: M}, {int: N}  (or {} for N)
    import re
    parts = re.findall(r"\{([^{}]*)\}", intensity.split(":", 1)[-1])
    vals = [p.split(":")[-1].strip() if p else "" for p in parts]
    while len(vals) < 4:
        vals.append("")
    return _INTENSITY.get((vals[0], vals[2], vals[3]), intensity[-30:])


def read_project(path: str | Path) -> Project:
    root = container.open_score(path).root
    insts = {}
    lib = root.child("library")
    for e in ((lib.child("instruments").child("entities").children or []) if lib and lib.child("instruments") else []):
        insts[_t(e, "entityID")] = e
    players, player_inst = {}, {}
    for p in root.child("scorePlayers").child("array").children or []:
        players[_t(p, "playerID")] = _t(p, "displayName")
        for i in p.child("instruments").children or []:
            player_inst[_t(i, "instrumentID")] = _t(i, "entityID") or _t(i, "instrumentEntityID")
    flows = []
    for fl in root.child("flows").child("array").children or []:
        flows.append(_read_flow(fl, players, player_inst))
    return Project(path=str(path), title=_t(root.child("info"), "title"), flows=flows, instruments=insts)


def _read_flow(fl: Node, players: dict, player_inst: dict) -> Flow:
    # element tables
    elements: dict[str, dict[str, Node]] = {}
    for tb in fl.child("elementTables").child("array").children or []:
        kind = tb.tag.replace("ElementTableDefinition", "")
        elements[kind] = {_t(e, "elementID"): e for e in tb.child("array").children or []}
    # streams -> owners
    owner: dict[str, tuple] = {}
    for fp in fl.child("flowPlayers").child("array").children or []:
        pname = players.get(_t(fp, "playerID"), "?")
        for fpi in fp.child("flowPlayerInstruments").children or []:
            iid = _t(fpi, "instrumentID")
            stave_of_id = {}
            for ssi in fpi.child("staveStreamInfos").children or []:
                k = int(_t(ssi, "nthStaveInInstrument", "0"))
                owner[_t(ssi, "staveStreamID")] = ("stave", pname, iid, k)
                stave_of_id[_t(ssi, "staveID")] = k
            for vsi in fpi.child("voiceStreamInfos").children or []:
                k = stave_of_id.get(_t(vsi, "defaultLogicalStaveID"), 0)
                owner[_t(vsi, "voiceStreamID")] = ("voice", pname, iid, k)
    block_stream = {_t(b, "blockID"): _t(b, "streamID") for b in fl.child("blockInstances").child("array").children or []}
    staves: dict[tuple, Staff] = {}

    def staff_for(pname, iid, k) -> Staff:
        key = (pname, iid, k)
        if key not in staves:
            staves[key] = Staff(player=pname, instrument=player_inst.get(iid, ""), index=k)
        return staves[key]

    bar_events = []
    for blk in fl.child("blocks").child("array").children or []:
        sid = block_stream.get(_t(blk, "blockID"))
        who = owner.get(sid)
        events = blk.child("events").children or []
        if who is None:  # global stream
            for e in events:
                if e.tag == "BarDivisionEventDefinition":
                    bar_events.append((F(_t(e, "position")), elements.get("BarDivision", {}).get(_t(e, "barDivisionElementID"))))
            continue
        kind, pname, iid, k = who
        st = staff_for(pname, iid, k)
        if kind == "voice":
            notes = []
            for e in events:
                if e.tag in ("NoteEventDefinition", "GraceNoteEventDefinition"):
                    notes.append(Note(F(_t(e, "position")), F(_t(e, "duration", "0")), int(_t(e, "pitch", "0")),
                                      grace=e.tag.startswith("Grace"), props=_props(e)))
                elif e.tag == "TrillEventDefinition":
                    p = F(_t(e, "position"))
                    st.trills.append((p, p + F(_t(e, "duration", "0"))))
                elif e.tag == "SlurEventDefinition":
                    p = F(_t(e, "position"))
                    st.slurs.append((p, p + F(_t(e, "duration", "0"))))
                elif e.tag == "PlayingTechniqueEventDefinition":
                    st.techniques.append((F(_t(e, "position")), _t(e, "appearanceEntityID")))
            st.voices.append(notes)
        else:
            for e in events:
                if e.tag == "DynamicGroupEventDefinition":
                    gid = _t(e, "dynamicGroupID")
                    el = elements.get("DynamicGroup", {}).get(gid)
                    st.dynamics.append(_dyn_group(F(_t(e, "position")), gid, el))
    length = max([F(_t(fl.child("minimumNotatedLength"), "length", "0"))] +
                 [n.pos + n.dur for s in staves.values() for v in s.voices for n in v] + [F(0)])
    return Flow(name=_t(fl, "flowName"), length=length, bars=_bars(bar_events, length),
                staves=list(staves.values()))


def _dyn_group(pos: Fraction, gid: str, el: Node | None) -> DynGroup:
    refs = _t(el, "referencingEventIDs") if el is not None else ""
    g = DynGroup(pos=pos, element=gid, linked=refs.count(",") + 1 if refs else 1)
    for s in (el.child("subElements").children or []) if el is not None else []:
        p = pos + F(_t(s, "position", "0"))
        if s.tag == "ImmediateChangeDynamicDefinition":
            g.items.append(DynItem(p, "dynamic", _level(_t(s, "intensity"))))
        elif s.tag == "GradualChangeDynamicDefinition":
            up = "Up" in _t(s, "direction")
            g.items.append(DynItem(p, "hairpin", "cresc" if up else "dim", p + F(_t(s, "duration", "0"))))
        elif s.tag == "CombinedDynamicDefinition":
            key = (_t(s, "direction"), _t(s, "startIntensity"), _t(s, "endIntensity"))
            g.items.append(DynItem(p, "combined", _COMBINED.get(key, "{}{}/{}".format(*key))))
        elif s.tag == "ForceDynamicDefinition":
            g.items.append(DynItem(p, "force", f"{_t(s, 'type').replace('kForceDynamic', '').lower()}{_t(s, 'intensityLevel')}"))
    return g


def _bars(events, length: Fraction) -> list[tuple[Fraction, Fraction, int, int]]:
    """Bar starts from BarDivision events (time signatures, pick-ups)."""
    changes = []
    for pos, el in sorted(events, key=lambda x: x[0]):
        if el is None:
            continue
        bd = el.child("barDivisionData")
        ts = None
        tsd = bd.child("timeSignature") if bd is not None else None
        arr = tsd.child("timeSignaturesAndDivisions") if tsd is not None else None
        if arr is not None and arr.children:
            t = arr.children[0].child("timeSignature")
            ts = (int(_t(t, "numerator", "4")), int(_t(t, "denominator", "4")))
        pick = _t(bd, "irregularBarLength") if bd is not None else ""
        changes.append((pos, ts, F(pick) if pick else None))
    bars = []
    num, den = 4, 4
    pos = F(0)
    i = 0
    while (pos < length or not bars) and len(bars) < 100000:
        pick = None
        while i < len(changes) and changes[i][0] <= pos:
            if changes[i][1]:
                num, den = changes[i][1]
            if changes[i][2]:
                pick = changes[i][2]
            i += 1
        blen = pick if pick else F(num * 4, den)
        bars.append((pos, blen, num, den))
        pos += blen
    return bars
