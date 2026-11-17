"""The engine's view of a score: one model for Dorico projects and Finale files.

Built from `doricohp.notation` (Dorico) or finale2dorico's `f2d ir` JSON (Finale .musx /
.mus), so the same rules run on both and Finale's Human Playback captures can be used to
check the engine (render with doricohp.render, compare with tools/analyze_capture.py).

Positions and durations are Fractions in crotchets from the flow start. Dynamic levels
are in steps with mf = 0 (mp = -1, f = +1, ff = +2 …).
"""
from __future__ import annotations

import json
import subprocess
import sys
from bisect import bisect_right
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

LEVELS = ["pppppp", "ppppp", "pppp", "ppp", "pp", "p", "mp", "mf", "f", "ff", "fff", "ffff", "fffff", "ffffff"]
STEP = {k: i - LEVELS.index("mf") for i, k in enumerate(LEVELS)}
FORCE = {"sfz", "sf", "sffz", "fz", "rfz", "rf", "sfp", "sfzp", "fp", "fpp", "pf"}

FAMILIES = [
    ("strings", ("violin", "viola", "cello", "violoncello", "contrabass", "double bass", "bass", "strings")),
    ("brass", ("horn", "trumpet", "trombone", "tuba", "euphonium", "cornet", "flugel", "brass")),
    ("woodwind", ("flute", "piccolo", "oboe", "english horn", "cor anglais", "clarinet", "bassoon",
                  "saxophone", "sax", "recorder", "reed", "wind")),
    ("keyboard", ("piano", "celesta", "celeste", "harpsichord", "organ", "keyboard", "synth")),
    ("harp", ("harp",)),
    ("pitched percussion", ("glockenspiel", "xylophone", "marimba", "vibraphone", "chimes", "tubular bells",
                            "crotales", "timpani")),
    ("percussion", ("drum", "cymbal", "triangle", "tam", "gong", "percussion", "shaker", "tambourine",
                    "wood block", "cowbell", "guiro", "taiko")),
    ("voice", ("soprano", "alto", "tenor", "bass voice", "baritone", "choir", "voice")),
    ("guitar", ("guitar",)),
]


def family_of(name: str, entity: str = "") -> str:
    s = f"{entity} {name}".lower()
    if "strings.contrabass" in s or "strings." in s:
        return "strings"
    if "unpitched" in s or "drumset" in s:
        return "percussion"
    if "pitchedpercussion" in s:
        return "pitched percussion"
    for fam, words in FAMILIES:
        if any(w in s for w in words):
            return fam
    return "other"


@dataclass
class Note:
    part: str
    pos: Fraction
    dur: Fraction
    pitch: int
    articulations: frozenset[str] = frozenset()
    grace: bool = False
    chord_size: int = 1
    voice: int = 0
    slur: str | None = None          # "start" | "in" | "end" | None
    tremolo: int = 0
    ref: object = None               # Dorico NoteRef / event id, for writing back

    @property
    def end(self) -> Fraction:
        return self.pos + self.dur


@dataclass
class Part:
    key: str
    name: str
    family: str
    entity: str = ""
    notes: list[Note] = field(default_factory=list)
    dynamics: list[tuple[Fraction, str]] = field(default_factory=list)          # (pos, kind)
    hairpins: list[tuple[Fraction, Fraction, str]] = field(default_factory=list)  # (pos, end, cresc|dim)
    slurs: list[tuple[Fraction, Fraction]] = field(default_factory=list)
    instrument_id: str = ""          # Dorico instrument id, for writing back
    passage: object = None           # passages.PassageMap (stacc./legato/leggiero… in force)

    def marked_level(self, pos: Fraction, default: float | None = None) -> float | None:
        """Level of the last immediate dynamic at or before pos (force dynamics ignored)."""
        lv = default
        for p, k in self.dynamics:
            if p > pos:
                break
            if k in STEP:
                lv = float(STEP[k])
            elif k in ("fp", "sfp", "fpp", "sfzp"):
                lv = float(STEP["p"] if k != "fpp" else STEP["pp"])
        return lv


@dataclass
class Score:
    title: str
    parts: list[Part]
    bar_starts: list[Fraction]
    tempos: list[tuple[Fraction, float]] = field(default_factory=lambda: [(Fraction(0), 100.0)])
    gradual_tempos: list[tuple[Fraction, Fraction, str]] = field(default_factory=list)
    source: str = ""

    # --- metre -------------------------------------------------------------
    def bar_of(self, pos: Fraction) -> int:
        return max(0, bisect_right(self.bar_starts, pos) - 1)

    def bar_length(self, bar: int) -> Fraction:
        if bar + 1 < len(self.bar_starts):
            return self.bar_starts[bar + 1] - self.bar_starts[bar]
        return self.bar_starts[bar] - self.bar_starts[bar - 1] if bar > 0 else Fraction(4)

    def beat_info(self, pos: Fraction) -> tuple[int, Fraction, Fraction]:
        """(bar index, offset in bar, bar length) in crotchets."""
        b = self.bar_of(pos)
        return b, pos - self.bar_starts[b], self.bar_length(b)

    # --- time ----------------------------------------------------------------
    def bpm_at(self, pos: Fraction) -> float:
        bpm = self.tempos[0][1] if self.tempos else 100.0
        for p, v in self.tempos:
            if p > pos:
                break
            bpm = v
        return bpm

    def ms_per_crotchet(self, pos: Fraction) -> float:
        return 60000.0 / self.bpm_at(pos)

    def seconds(self, pos: Fraction) -> float:
        t, last_p, last_bpm = 0.0, Fraction(0), self.tempos[0][1] if self.tempos else 100.0
        for p, v in self.tempos:
            if p >= pos:
                break
            t += float(p - last_p) * 60.0 / last_bpm
            last_p, last_bpm = p, v
        return t + float(pos - last_p) * 60.0 / last_bpm


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------

def _slur_roles(notes: list[Note], slurs: list[tuple[Fraction, Fraction]]) -> None:
    """Mark each note's place in a slur: start / in / end (first slur that covers it)."""
    for s, e in slurs:
        inside = [n for n in notes if s <= n.pos <= e and not n.grace and n.slur is None]
        if len(inside) < 2:
            continue
        onsets = sorted({n.pos for n in inside})
        for n in inside:
            n.slur = "start" if n.pos == onsets[0] else "end" if n.pos == onsets[-1] else "in"


def from_dorico_all(path: str) -> list[Score]:
    """Every flow of a Dorico project (reads the file once)."""
    from . import notation
    from .project import Project
    p = Project(path)
    flows = notation.read_project(p)
    out = []
    for f, pflow in zip(flows, p.flows()):
        refs = {}
        insts = p.instruments(pflow)
        for inst in insts:
            for nr in p.notes(pflow, inst):
                refs[(inst.instrument_id, nr.position, nr.pitch, nr.grace)] = nr
        parts = []
        for st, inst in zip(f.staves, insts):
            part = Part(st.name, st.name, family_of(st.name, st.instrument), st.instrument,
                        instrument_id=inst.instrument_id)
            for c in st.chords:
                for pitch in c.pitches:
                    part.notes.append(Note(st.name, c.pos, c.dur, pitch, frozenset(c.articulations), c.grace,
                                           len(c.pitches), tremolo=c.tremolo,
                                           ref=refs.get((inst.instrument_id, c.pos, pitch, c.grace))))
            part.dynamics = [(d["pos"], d["kind"]) for d in st.dynamics]
            part.hairpins = [(h["pos"], h["end"], h["direction"]) for h in st.hairpins]
            part.slurs = [(sl["pos"], sl["end"]) for sl in st.slurs]
            part.notes.sort(key=lambda n: (n.pos, n.pitch))
            _slur_roles(part.notes, part.slurs)
            from . import passages
            marks = []
            for t in st.techniques:
                marks.append((t["pos"], passages.technique_flags(t.get("technique", ""), t.get("text", ""))))
            for t in st.texts:
                marks.append((t["pos"], passages.words_to_flags(t["text"])))
            part.passage = passages.build(marks, part.notes)
            parts.append(part)
        tempos = [(t["pos"], t["bpm"]) for t in f.tempos if t.get("bpm")]
        grad = [(t["pos"], t["end"], t.get("text", "")) for t in f.tempos if t.get("gradual")]
        sc = Score(f.title, parts, f.bar_starts, tempos or [(Fraction(0), 100.0)], grad, source=path)
        sc.flow_node = pflow
        sc.project = p
        out.append(sc)
    return out


def from_dorico(path: str, flow_index: int = 0) -> Score:
    return from_dorico_all(path)[flow_index]


def from_f2d(data: dict | str, flow_index: int = 0, default_bpm: float = 100.0) -> Score:
    """From finale2dorico's `f2d ir` JSON (a dict, a JSON file path, or a .musx/.mus path)."""
    if isinstance(data, str):
        p = Path(data)
        if p.suffix in (".musx", ".mus"):
            f2d = Path(__file__).resolve().parents[2] / "finale2dorico"
            out = subprocess.run([sys.executable, "-m", "f2d", "ir", str(p.resolve())], cwd=f2d,
                                 capture_output=True, text=True, check=True).stdout
            data = json.loads(out)
        else:
            data = json.loads(p.read_text())
    names, entity = {}, {}
    from collections import Counter
    count = Counter(i["name"] for pl in data["players"] for i in pl["instruments"])
    seen = Counter()
    for pl in data["players"]:
        for i in pl["instruments"]:
            seen[i["name"]] += 1
            names[i["id"]] = i["name"] + (f" {seen[i['name']]}" if count[i["name"]] > 1 else "")
            entity[i["id"]] = i.get("sound_id") or ""
    f = data["flows"][flow_index]
    parts: dict[str, Part] = {}
    ties: dict[tuple[int, int], Note] = {}
    for s in f["staves"]:
        key = names.get(s["instrument"], s["instrument"])
        part = parts.get(key) or parts.setdefault(key, Part(key, key, family_of(key, entity.get(s["instrument"], "")),
                                                            entity.get(s["instrument"], "")))
        for vi, v in enumerate(s["voices"]):
            for c in v["chords"]:
                if not c["pitches"]:
                    continue
                for x in c["pitches"]:
                    pos, dur, voice = Fraction(c["pos"]), Fraction(c["dur"]), s["index"] * 8 + vi
                    prev = ties.pop((voice, x["midi"]), None)
                    if prev is not None and prev.end == pos:
                        prev.dur += dur                     # tied continuation
                        note = prev
                    else:
                        note = Note(key, pos, dur, x["midi"], frozenset(c["articulations"]), c["grace"],
                                    len(c["pitches"]), voice=voice, tremolo=c.get("tremolo", 0))
                        part.notes.append(note)
                    if x.get("tie"):
                        ties[(voice, x["midi"])] = note
            part.slurs += [(Fraction(x["pos"]), Fraction(x["end"])) for x in v.get("slurs", [])]
        part.dynamics += [(Fraction(d["pos"]), d["kind"]) for d in s.get("dynamics", [])]
        part.hairpins += [(Fraction(h["pos"]), Fraction(h["end"]), h["direction"]) for h in s.get("hairpins", [])]
    for part in parts.values():
        part.notes.sort(key=lambda n: (n.pos, n.pitch))
        part.dynamics.sort()
        part.hairpins.sort()
        part.slurs.sort()
        _slur_roles(part.notes, part.slurs)
    tempos = [(Fraction(t["pos"]), float(t["bpm"])) for t in f.get("tempos", []) if t.get("bpm")]
    return Score(f.get("title", ""), list(parts.values()), [Fraction(b) for b in f["bar_starts"]],
                 tempos or [(Fraction(0), default_bpm)], source=str(data.get("source", "")))


def load(path: str, flow_index: int = 0) -> Score:
    if path.endswith(".dorico"):
        return from_dorico(path, flow_index)
    return from_f2d(path, flow_index)
