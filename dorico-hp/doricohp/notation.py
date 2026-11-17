"""Read the performance-relevant notation of a Dorico project.

Gives, per flow and instrument: notes/chords with articulations, dynamics (immediate and
force), hairpins (gradual dynamics), slurs, playing techniques, tempo marks and bar
positions. The shape matches finale2dorico's `f2d ir` JSON closely enough that the same
comparison code works on Finale and Dorico versions of a piece (see
tools/compare_versions.py). Positions are Fractions in crotchets from the flow start.

    python3 -m doricohp.notation Project.dorico > notation.json

Since Project S (S4) this is a view over the shared read model (`doricokit.model`,
engine/crates/dorico-model), which finale2dorico's reviewer and dorigit use too. The old
reader is kept as a test oracle (engine/tests/oracles/hp_notation_py.py). Differences from it
(all corrections, see engine/docs/STATUS.md "S4 parity findings"): bars follow Dorico (pick-up
bars, a time signature mid-bar starts a bar, the flow runs to `minimumNotatedLength`), rich-text
Text items are read, and dynamics the old decoder showed as "?" keep Dorico's value ("f
possibile", or the raw encoding when unknown).
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from fractions import Fraction

from doricokit import model

from .project import Project


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
    instrument: str      # Dorico instrument ID within the project (instrumentID)
    chords: list[Chord] = field(default_factory=list)
    dynamics: list[dict] = field(default_factory=list)    # {pos, kind}
    hairpins: list[dict] = field(default_factory=list)    # {pos, end, direction}
    slurs: list[dict] = field(default_factory=list)       # {pos, end}
    techniques: list[dict] = field(default_factory=list)  # {pos, id, text, technique}
    texts: list[dict] = field(default_factory=list)       # {pos, text}


@dataclass
class FlowNotation:
    id: str
    title: str
    bar_starts: list[Fraction]
    tempos: list[dict]
    staves: list[Staff]
    bar_labels: list[str] = field(default_factory=list)  # bar numbers as Dorico shows them ("0", "35a")

    def where(self, pos: Fraction) -> str:
        """'bar 12 beat 2+1/2' (beats are crotchets; bar numbers as Dorico shows them)."""
        bar = 0
        for i, s in enumerate(self.bar_starts):
            if s <= pos:
                bar = i
            else:
                break
        off = pos - (self.bar_starts[bar] if self.bar_starts else 0)
        whole, rest = int(off), off - int(off)
        label = self.bar_labels[bar] if bar < len(self.bar_labels) else str(bar + 1)
        return f"bar {label} beat {whole + 1}" + (f"+{rest}" if rest else "")


def read(path: str) -> list[FlowNotation]:
    return _from_model(model.read(path))


def read_project(p: Project) -> list[FlowNotation]:
    """The notation of an opened project (read from its file; the shared model reads it in Rust)."""
    return read(str(p.path))


def _end(m: dict) -> Fraction:
    return m["end"] if m["end"] is not None else m["pos"]


def _from_model(score: dict) -> list[FlowNotation]:
    out = []
    for fl in score["flows"]:
        tempos = []
        for t in fl["tempos"]:
            if t["gradual"]:
                tempos.append({"pos": t["pos"], "gradual": True, "end": t["end"], "text": t["text"]})
            else:
                tempos.append({"pos": t["pos"], "bpm": t["bpm"], "text": t["text"]})
        staves = []
        for p in fl["parts"]:
            name = p["player_name"] + (f" #{p['number']}" if p["of"] > 1 else "")
            st = Staff(name, p["instrument_id"])
            for v in p["voices"]:
                chords: dict[tuple[Fraction, bool], Chord] = {}
                for n in v["notes"]:
                    c = chords.get((n["pos"], n["grace"]))
                    if c is None:
                        c = chords[(n["pos"], n["grace"])] = Chord(n["pos"], n["dur"], [], [], grace=n["grace"])
                    c.pitches.append(n["pitch"])
                    for a in n["articulations"]:
                        if a not in c.articulations:
                            c.articulations.append(a)
                    if n["tremolo"]:
                        c.tremolo = 1
                st.chords += chords.values()
            st.chords.sort(key=lambda c: (c.pos, c.grace))
            # slurs live in voices; techniques and texts on voices and staves (as before)
            for m in [m for v in p["voices"] for m in v["marks"]] + [m for s in p["staves"] for m in s["marks"]]:
                d = m["detail"]
                if m["kind"] == "slur":
                    st.slurs.append({"pos": m["pos"], "end": _end(m)})
                elif m["kind"] == "technique":
                    st.techniques.append({"pos": m["pos"], "id": d.get("appearance", ""), "text": d.get("text", ""),
                                          "technique": d.get("technique", "")})
                elif d.get("text"):
                    st.texts.append({"pos": m["pos"], "text": d["text"]})
            for s in p["staves"]:
                for g in s["dynamics"]:
                    for i in g["items"]:
                        # combined dynamics (fp, ...) are not used by the rules yet (as before)
                        if i["kind"] in ("dynamic", "force"):
                            st.dynamics.append({"pos": i["pos"], "kind": i["level"]})
                        elif i["kind"] == "hairpin":
                            st.hairpins.append({"pos": i["pos"], "end": i["end"], "direction": i["level"]})
            for lst in (st.dynamics, st.hairpins, st.slurs, st.techniques, st.texts):
                lst.sort(key=lambda d: d["pos"])
            staves.append(st)
        out.append(FlowNotation(fl["id"], fl["name"], [b["start"] for b in fl["bars"]],
                                sorted(tempos, key=lambda t: t["pos"]), staves,
                                bar_labels=[b["label"] for b in fl["bars"]]))
    return out


def to_json(flows: list[FlowNotation]) -> str:
    def conv(x):
        if isinstance(x, Fraction):
            return str(x)
        raise TypeError(type(x))
    return json.dumps({"flows": [asdict(f) for f in flows]}, default=conv, indent=1)


if __name__ == "__main__":
    print(to_json(read(sys.argv[1])))
