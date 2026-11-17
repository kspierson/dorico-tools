"""TEST ORACLE ONLY: dorico-hp's old notation reader (doricohp/notation.py before Project S
S4), kept so engine/tests/parity/model_vs_python.py can compare the shared model against it.
dorico-hp now reads notation through doricokit.model. Do not use in tools.

Read the performance-relevant notation of a Dorico project.

Gives, per flow and instrument: notes/chords with articulations, dynamics (immediate and
force), hairpins (gradual dynamics), slurs, playing techniques, tempo marks and bar
positions. The shape matches finale2dorico's `f2d ir` JSON closely enough that the same
comparison code works on Finale and Dorico versions of a piece (see
tools/compare_versions.py). Positions are Fractions in crotchets from the flow start.

    python3 -m doricohp.notation Project.dorico > notation.json

Dynamic intensity encoding and the element-table layout come from dorigit's research
(dorigit/docs/RESEARCH.md), confirmed against Dorico there.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from fractions import Fraction

from doricohp.project import Project, array_of, frac, items

ARTICULATIONS = {
    "kStaccato": "staccato", "kStaccatissimo": "staccatissimo", "kTenuto": "tenuto",
    "kStaccatoTenuto": "staccato-tenuto", "kSpiccato": "spiccato",
    "kAccent": "accent", "kMarcato": "marcato", "kStress": "stress", "kUnstress": "unstress",
}


def decode_intensity(v: str) -> str:
    """{int: 0=forte|1=piano}, {}, {bool: mezzo}, {int: count} -> 'pp', 'mf', ..."""
    nums = re.findall(r"\{(int|bool): (\w+)\}|\{\}", v or "")
    try:
        loud = nums[0][1] == "0"
        if nums[2][1] == "true":
            return "mf" if loud else "mp"
        return ("f" if loud else "p") * int(nums[3][1])
    except (IndexError, ValueError):
        return "?"


@dataclass
class Chord:
    pos: Fraction
    dur: Fraction
    pitches: list[int]
    articulations: list[str]
    grace: bool = False
    tremolo: int = 0


@dataclass
class Staff:
    name: str            # player name (+ instrument number when a player doubles)
    instrument: str      # Dorico instrument type id when known
    chords: list[Chord] = field(default_factory=list)
    dynamics: list[dict] = field(default_factory=list)    # {pos, kind}
    hairpins: list[dict] = field(default_factory=list)    # {pos, end, direction}
    slurs: list[dict] = field(default_factory=list)       # {pos, end}
    techniques: list[dict] = field(default_factory=list)  # {pos, id, text, technique}
    texts: list[dict] = field(default_factory=list)       # {pos, text} (text items, best effort)


@dataclass
class FlowNotation:
    id: str
    title: str
    bar_starts: list[Fraction]
    tempos: list[dict]
    staves: list[Staff]

    def where(self, pos: Fraction) -> str:
        """'bar 12 beat 2+1/2' (beats are crotchets)."""
        bar = 0
        for i, s in enumerate(self.bar_starts):
            if s <= pos:
                bar = i
            else:
                break
        off = pos - (self.bar_starts[bar] if self.bar_starts else 0)
        whole, rest = int(off), off - int(off)
        return f"bar {bar + 1} beat {whole + 1}" + (f"+{rest}" if rest else "")


def _props(ev) -> dict[str, str]:
    out = {}
    pt = ev.child("propertyTable")
    for e in items(pt.child("entries") if pt is not None else None):
        if e.child("context") is None:
            out[e.text("propertyType")] = e.text("value")
    return out


def _clean(v: str) -> str:
    m = re.match(r'string: "(.*)"$', v or "")
    return m.group(1) if m else (v or "")


def _bar_starts(p: Project, flow, tables) -> list[Fraction]:
    """Bar start positions from the global time-signature/barline events."""
    divisions = tables.get("BarDivision", {})
    events = []
    for s in array_of(flow.child("eventStreams")):
        if s.text("eventStreamType") == "kGlobalTimebaseStream":
            events += [(pos, ev) for pos, ev in p.stream_events(flow, s.text("streamID"))
                       if ev.tag == "BarDivisionEventDefinition"]
    events.sort(key=lambda x: x[0])
    # flow length = end of the last note/rest in any stream
    end = Fraction(0)
    for b in array_of(flow.child("blocks")):
        for ev in items(b.child("events")):
            end = max(end, frac(ev.text("position")) + frac(ev.text("duration")))
    end = max(end, max((pos for pos, _ in events), default=Fraction(0)))
    for bi in array_of(flow.child("blockInstances")):
        end = max(end, frac(bi.text("position")))
    starts: list[Fraction] = []
    bar_len, at = Fraction(4), Fraction(0)
    pending = list(events)
    while at < end + bar_len or pending:
        if pending and pending[0][0] <= at:
            pos, ev = pending.pop(0)
            el = divisions.get(ev.text("barDivisionElementID"))
            ts = el.find("barDivisionData/timeSignature/timeSignaturesAndDivisions") if el is not None else None
            sig = items(ts)[0].child("timeSignature") if ts is not None and items(ts) else None
            if sig is not None:
                bar_len = Fraction(4 * int(sig.text("numerator") or 4), int(sig.text("denominator") or 4))
            if pos < at and starts:      # a barline/time signature mid-bar starts a new bar
                at = pos
            continue
        if at >= end:
            break
        starts.append(at)
        nxt = at + bar_len
        if pending and pending[0][0] < nxt:
            nxt = pending[0][0]
        at = nxt
    return starts or [Fraction(0)]


def _tables(flow) -> dict[str, dict[str, object]]:
    out = {}
    for t in array_of(flow.child("elementTables")):
        kind = t.tag.removesuffix("ElementTableDefinition")
        out[kind] = {e.text("elementID"): e for e in items(t.child("array"))}
    return out


def read(path: str) -> list[FlowNotation]:
    return read_project(Project(path))


def technique_table(p: Project) -> dict[str, tuple[str, str]]:
    """Playing-technique appearance id → (written text, playback technique id)."""
    out = {}
    lib = p.root.find("library/playingTechniqueAppearanceCollectionDefinition/entities")
    for d in items(lib):
        out[d.text("entityID")] = (d.text("text") or d.text("name"), d.text("playingTechniqueEntityID"))
    return out


def _texts_in(ev) -> list[str]:
    """Any text carried by an event (leaves named text/string/plainText), best effort."""
    found = []

    def walk(n):
        for c in n.children or ():
            if c.children:
                walk(c)
            elif c.tag in ("text", "plainText", "string", "displayText") and c.value:
                v = re.sub(r"<[^>]+>", "", c.value)
                v = re.sub(r'^string: "(.*)"$', r"\1", v)
                if v.strip():
                    found.append(v.strip())
    walk(ev)
    return found


def read_project(p: Project) -> list[FlowNotation]:
    techs = technique_table(p)
    out = []
    for flow in p.flows():
        tables = _tables(flow)
        dyn_table = tables.get("DynamicGroup", {})
        staves = []
        tempos = []
        for s in array_of(flow.child("eventStreams")):
            if s.text("eventStreamType") != "kGlobalTimebaseStream":
                continue
            for pos, ev in p.stream_events(flow, s.text("streamID")):
                if ev.tag == "ImmediateTempoChangeEventDefinition":
                    tv = ev.find("data/absoluteTempo/tempoValue")
                    bpm = round(60e6 / int(tv.value), 2) if tv is not None and tv.value not in (None, "", "0") else None
                    tempos.append({"pos": pos, "bpm": bpm, "text": ev.find("data/text").value if ev.find("data/text") is not None else ""})
                elif ev.tag.startswith("GradualTempoChange"):
                    tempos.append({"pos": pos, "gradual": True, "end": pos + frac(ev.text("duration")),
                                   "text": ev.find("data/text").value if ev.find("data/text") is not None else ""})
        insts = p.instruments(flow)
        per_player = defaultdict(int)
        for inst in insts:
            per_player[inst.player_id] += 1
        seen = defaultdict(int)
        for inst in insts:
            seen[inst.player_id] += 1
            name = inst.player_name + (f" #{seen[inst.player_id]}" if per_player[inst.player_id] > 1 else "")
            st = Staff(name, inst.instrument_id)
            chords: dict[tuple[str, Fraction], Chord] = {}
            for vs in inst.voice_streams:
                for pos, ev in p.stream_events(flow, vs):
                    tag = ev.tag
                    if tag in ("NoteEventDefinition", "GraceNoteEventDefinition"):
                        pr = _props(ev)
                        key = (vs, pos, tag)
                        c = chords.get(key)
                        if c is None:
                            c = chords[key] = Chord(pos, frac(ev.text("duration")), [], [],
                                                   grace=tag.startswith("Grace"))
                        c.pitches.append(int(ev.text("pitch") or 0))
                        for k in ("kArticulationDuration", "kArticulationForce", "kArticulationStress"):
                            if k in pr:
                                a = ARTICULATIONS.get(_clean(pr[k]), _clean(pr[k]))
                                if a not in c.articulations:
                                    c.articulations.append(a)
                        if "kNoteSingleStemTremolo" in pr:
                            c.tremolo = 1
                    elif tag == "SlurEventDefinition":
                        st.slurs.append({"pos": pos, "end": pos + frac(ev.text("duration"))})
                    elif tag == "PlayingTechniqueEventDefinition":
                        aid = ev.text("appearanceEntityID")
                        txt, pt = techs.get(aid, ("", ""))
                        st.techniques.append({"pos": pos, "id": aid, "text": txt, "technique": pt})
                    elif "Text" in tag and tag != "TextEventDefinition_unused":
                        for t in _texts_in(ev):
                            st.texts.append({"pos": pos, "text": t})
            st.chords = sorted(chords.values(), key=lambda c: (c.pos, c.grace))
            for stave in inst.stave_streams:
                for pos, ev in p.stream_events(flow, stave):
                    if ev.tag == "DynamicGroupEventDefinition":
                        el = dyn_table.get(ev.text("dynamicGroupID"))
                        for sub in items(el.child("subElements")) if el is not None else ():
                            at = pos + frac(sub.text("position"))
                            if sub.tag == "ImmediateChangeDynamicDefinition":
                                st.dynamics.append({"pos": at, "kind": decode_intensity(sub.text("intensity"))})
                            elif sub.tag == "GradualChangeDynamicDefinition":
                                d = sub.text("direction")
                                st.hairpins.append({"pos": at, "end": at + frac(sub.text("duration")),
                                                    "direction": "cresc" if d.endswith("Up") else "dim" if d.endswith("Down") else d})
                            elif sub.tag == "ForceDynamicDefinition":
                                st.dynamics.append({"pos": at, "kind": sub.text("type").removeprefix("kForceDynamic").lower()})
                    elif ev.tag == "PlayingTechniqueEventDefinition":
                        aid = ev.text("appearanceEntityID")
                        txt, pt = techs.get(aid, ("", ""))
                        st.techniques.append({"pos": pos, "id": aid, "text": txt, "technique": pt})
                    elif "Text" in ev.tag:
                        for t in _texts_in(ev):
                            st.texts.append({"pos": pos, "text": t})
            for lst in (st.dynamics, st.hairpins, st.slurs, st.techniques, st.texts):
                lst.sort(key=lambda d: d["pos"])
            staves.append(st)
        out.append(FlowNotation(flow.text("flowID"), flow.text("flowName"), _bar_starts(p, flow, tables),
                                sorted(tempos, key=lambda t: t["pos"]), staves))
    return out


def to_json(flows: list[FlowNotation]) -> str:
    def conv(x):
        if isinstance(x, Fraction):
            return str(x)
        raise TypeError(type(x))
    return json.dumps({"flows": [asdict(f) for f in flows]}, default=conv, indent=1)


if __name__ == "__main__":
    print(to_json(read(sys.argv[1])))
