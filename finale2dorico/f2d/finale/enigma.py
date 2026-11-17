"""Bootstrap reader: Finale EnigmaXML (from .musx) -> Score IR.

This is a deliberately small reader for straightforward scores, written so the Dorico
writer can be tested end to end. It follows the data model documented by musxdom
(https://github.com/openmusx/musxdom, MIT): see docs/RESEARCH.md for the parts used.
The planned full reader is built on musxdom itself (handles .mus files, part voicing,
Finale's many notation workarounds, etc.).

Units: Finale EDUs, 1024 per crotchet. Positions in the IR are crotchets (Fraction).

Supported here: staves and grand-staff groups, measures, time signatures (simple and
compound), key signatures (built-in major/minor), clefs and mid-measure clef changes,
layers 1-4 and voice 2, notes/chords/rests, dots, ties, tuplets (incl. nested), grace
notes, hidden entries, articulations (by glyph), dynamics from expressions (by glyph),
slurs and hairpins (smart shapes), title/composer.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from .. import ir
from .musx import enigma_xml

F = Fraction
EDU = 1024  # per crotchet

# --- glyph tables (Maestro legacy codepoints and SMuFL codepoints) ----------------
# Codepoints from the Maestro -> SMuFL mapping in openmusx/smufl-mapping.
ARTIC_GLYPHS = {
    46: "staccato", 0xE4A2: "staccato", 0xE4A3: "staccato",
    62: "accent", 0xE4A0: "accent", 0xE4A1: "accent",
    45: "tenuto", 0xE4A4: "tenuto", 0xE4A5: "tenuto",
    94: "marcato", 118: "marcato", 0xE4AC: "marcato", 0xE4AD: "marcato",
    171: "staccatissimo", 216: "staccatissimo", 174: "staccatissimo", 39: "staccatissimo",
    0xE4A6: "staccatissimo", 0xE4A7: "staccatissimo", 0xE4A8: "staccatissimo", 0xE4A9: "staccatissimo",
    248: "staccato-tenuto", 60: "staccato-tenuto", 0xE4B2: "staccato-tenuto", 0xE4B3: "staccato-tenuto",
    249: ("accent", "staccato"), 223: ("accent", "staccato"),
    0xE4B0: ("accent", "staccato"), 0xE4B1: ("accent", "staccato"),
    138: ("accent", "tenuto"), 137: ("accent", "tenuto"), 0xE4B4: ("accent", "tenuto"), 0xE4B5: ("accent", "tenuto"),
    172: ("marcato", "staccato"), 232: ("marcato", "staccato"),
    85: "fermata", 117: "fermata", 0xE4C0: "fermata", 0xE4C1: "fermata",
}
DYNAMIC_GLYPHS = {
    175: "pppp", 184: "ppp", 185: "pp", 112: "p", 80: "mp", 70: "mf", 102: "f", 196: "ff",
    236: "fff", 235: "ffff", 83: "sfz", 115: "sf", 90: "fz", 142: "rf", 167: "sfz", 141: "sffz",
    234: "fp", 130: "sfp", 182: "sfpp",
    0xE529: "pppp", 0xE52A: "ppp", 0xE52B: "pp", 0xE520: "p", 0xE52C: "mp", 0xE52D: "mf",
    0xE522: "f", 0xE52F: "ff", 0xE530: "fff", 0xE531: "ffff", 0xE539: "sfz", 0xE536: "sfz",
    0xE524: "sf", 0xE535: "fz", 0xE523: "rf", 0xE534: "fp", 0xE537: "sfp",
}
CLEF_GLYPH_TYPE = {38: "G", 0xE050: "G", 86: "G8vb", 0xE052: "G8vb", 160: "G8va", 0xE053: "G8va",
                   66: "C", 0xE05C: "C", 63: "F", 0xE062: "F", 116: "F8vb", 0xE064: "F8vb",
                   230: "F8va", 0xE065: "F8va", 47: "perc", 139: "perc", 0xE069: "perc",
                   214: "perc2", 0xE06A: "perc2"}
# (glyph type, middle-C staff position relative to the top line) -> Dorico clef entity
CLEF_MAP = {
    ("G", -10): "clef.treble", ("G", -12): "clef.frenchviolin", ("G", -3): "clef.treble8ba",
    ("G", -17): "clef.treble8va", ("G8vb", -3): "clef.treble8ba", ("G8va", -17): "clef.treble8va",
    ("C", -8): "clef.soprano", ("C", -6): "clef.mezzo-soprano", ("C", -4): "clef.alto",
    ("C", -2): "clef.tenor", ("C", 0): "clef.baritone",
    ("F", 2): "clef.bass", ("F", 0): "clef.baritone-bass", ("F", 4): "clef.sub-bass",
    ("F", 9): "clef.bass8ba", ("F8vb", 9): "clef.bass8ba", ("F", -5): "clef.bass8va",
    ("F8va", -5): "clef.bass8va",
}
DEFAULT_CLEFS = {0: "clef.treble", 1: "clef.alto", 2: "clef.tenor", 3: "clef.bass", 4: "clef.percussion",
                 5: "clef.treble8ba", 6: "clef.bass8ba", 7: "clef.baritone-bass", 8: "clef.frenchviolin",
                 9: "clef.baritone", 10: "clef.mezzo-soprano", 11: "clef.soprano", 12: "clef.percussion2",
                 13: "clef.tab", 14: "clef.tab"}

STEPS = "CDEFGAB"
STEP_SEMI = [0, 2, 4, 5, 7, 9, 11]
SHARP_ORDER = [3, 0, 4, 1, 5, 2, 6]     # F C G D A E B as step indices
FLAT_ORDER = [6, 2, 5, 1, 4, 0, 3]      # B E A D G C F
MAJOR_CENTERS_SHARP = [0, 4, 1, 5, 2, 6, 3, 0]
MAJOR_CENTERS_FLAT = [0, 3, 6, 2, 5, 1, 4, 0]
MINOR_CENTERS_SHARP = [5, 2, 6, 3, 0, 4, 1, 5]
MINOR_CENTERS_FLAT = [5, 1, 4, 0, 3, 6, 2, 5]

_DATA = Path(__file__).resolve().parents[1] / "data"


def _int(e, tag, default=0) -> int:
    if e is None:
        return default
    t = e.findtext(tag)
    try:
        return int(t) if t not in (None, "") else default
    except ValueError:
        return default


def _flag(e, tag) -> bool:
    return e is not None and e.find(tag) is not None


class Key:
    """A built-in (or linear) Finale key: `key` value from a <keySig>."""

    def __init__(self, value: int = 0):
        self.value = value & 0xFFFF
        self.linear = (self.value & 0xC000) == 0
        self.mode = (self.value >> 8) if self.linear else self.value
        b = self.value & 0xFF
        self.fifths = (b - 256 if b > 127 else b) if self.linear else 0

    @property
    def minor(self) -> bool:
        return self.mode == 1

    def tonal_center(self) -> int:
        f = self.fifths
        if self.minor:
            arr = MINOR_CENTERS_SHARP if f >= 0 else MINOR_CENTERS_FLAT
        else:
            arr = MAJOR_CENTERS_SHARP if f >= 0 else MAJOR_CENTERS_FLAT
        return arr[abs(f) % 8]

    def key_alter(self, step: int) -> int:
        f = self.fifths
        order = SHARP_ORDER if f >= 0 else FLAT_ORDER
        amount = 1 if f >= 0 else -1
        return sum(amount for i in range(min(abs(f), 7)) if order[i] == step)

    def pitch(self, harm_lev: int, harm_alt: int) -> tuple[str, int, int, int]:
        """(step letter, octave, alteration, midi) for a note's harmLev/harmAlt."""
        lev = self.tonal_center() + harm_lev
        octave = lev // 7 + 4
        step = lev % 7
        alter = harm_alt + self.key_alter(step)
        midi = 12 * (octave + 1) + STEP_SEMI[step] + alter
        return STEPS[step], octave, alter, midi


class EnigmaReader:
    def __init__(self, xml_text: str, source: str = ""):
        xml_text = re.sub(r' xmlns="[^"]+"', "", xml_text, count=1)
        self.root = ET.fromstring(xml_text)
        self.source = source
        self.warnings: list[str] = []
        self.others = defaultdict(list)
        for e in self.root.find("others"):
            self.others[e.tag].append(e)
        self.details = defaultdict(list)
        for e in self.root.find("details"):
            self.details[e.tag].append(e)
        self.entries = {int(e.get("entnum")): e for e in self.root.find("entries")}
        self.texts = defaultdict(dict)
        for e in self.root.find("texts"):
            key = e.get("number") or e.get("type")
            self.texts[e.tag][key] = e.text or ""
        self.finale_instruments = json.loads((_DATA / "finale_instruments.json").read_text())["instruments"]

    # ---------------------------------------------------------------- helpers
    def score_records(self, tag: str):
        """Records that belong to the score (not a linked part's override)."""
        return [e for e in self.others[tag] if e.get("part") in (None, "0")]

    def by_cmper(self, tag: str) -> dict[int, ET.Element]:
        return {int(e.get("cmper")): e for e in self.score_records(tag)}

    def detail_map(self, tag: str, *keys: str) -> dict:
        out = {}
        for e in self.details[tag]:
            if e.get("part") not in (None, "0"):
                continue
            out[tuple(int(e.get(k, 0)) for k in keys)] = e
        return out

    def text_of_block(self, text_id_key: int) -> str:
        tb = self.by_cmper("textBlock").get(text_id_key)
        if tb is None:
            return ""
        tid = tb.findtext("textID")
        tag = "expression" if tb.findtext("textTag") in (None, "expression") else "blockText"
        return self.texts[tag].get(tid, "") or self.texts["expression"].get(tid, "")

    @staticmethod
    def strip_enigma(text: str) -> tuple[str, bool]:
        """Remove ^font(...) etc. commands. Returns (plain text, uses a music font)."""
        music = "^fontMus" in text
        text = (text.replace("^flat()", "\u266d").replace("^sharp()", "\u266f")
                .replace("^natural()", "\u266e"))
        plain = re.sub(r"\^[a-zA-Z]+\([^)]*\)", "", text)
        plain = re.sub(r"\^\^", "^", plain)
        return plain, music

    # ------------------------------------------------------------------ main
    def read(self) -> ir.Score:
        score = ir.Score(source=self.source)
        self._info(score)
        measures = sorted(self.by_cmper("measSpec").items())
        if not measures:
            raise ValueError("no measures found")
        staves = self._staff_order()
        self._players(score, staves)
        flow = self._flow(score, measures, staves)
        score.flows.append(flow)
        score.warnings[:0] = self.warnings
        return score

    def _info(self, score: ir.Score) -> None:
        fi = self.texts["fileInfo"]
        score.info.title = fi.get("title", "") or ""
        score.info.composer = fi.get("composer", "") or ""
        score.info.copyright = fi.get("copyright", "") or ""
        score.info.subtitle = fi.get("subtitle", "") or ""
        score.info.arranger = fi.get("arranger", "") or ""
        score.info.lyricist = fi.get("lyricist", "") or ""

    def _staff_order(self) -> list[int]:
        used = [e for e in self.score_records("instUsed") if e.get("cmper") == "0"]
        used.sort(key=lambda e: int(e.get("inci", 0)))
        return [_int(e, "inst") for e in used if e.findtext("trackType") in (None, "staff")]

    def _staff_name(self, spec: ET.Element) -> str:
        nid = _int(spec, "fullName")
        if nid:
            txt = self.text_of_block(nid)
            plain, _ = self.strip_enigma(txt)
            plain = plain.replace("\r", " ").replace("\n", " ").strip()
            if plain:
                return plain
        return ""

    def _group_name(self, first: int, last: int) -> str:
        """Name of a score staff group (bracket) spanning exactly first..last, if any."""
        for g in self.details["staffGroup"]:
            if g.get("part") not in (None, "0") or g.get("cmper1") not in (None, "0"):
                continue
            if _int(g, "startInst") == first and _int(g, "endInst") == last and _int(g, "fullID"):
                plain, _ = self.strip_enigma(self.text_of_block(_int(g, "fullID")))
                plain = plain.replace("\r", " ").replace("\n", " ").strip()
                if plain:
                    return plain
        return ""

    def _players(self, score: ir.Score, staves: list[int]) -> None:
        specs = self.by_cmper("staffSpec")
        groups: dict[int, list[int]] = {}
        for g in self.score_records("multiStaffInstGroup"):
            members = [_int(g, f"staffNum{i}") for i in range(1, 4)]
            groups[int(g.get("cmper"))] = [m for m in members if m]
        staff_group = {}
        for gid, members in groups.items():
            for m in members:
                staff_group[m] = gid
        self.staff_to_inst: dict[int, tuple[str, int]] = {}
        done = set()
        for s in staves:
            if s in done:
                continue
            members = groups.get(staff_group.get(s), [s])
            members = [m for m in members if m in staves] or [s]
            spec = specs.get(members[0])
            uuid = spec.findtext("instUuid") if spec is not None else None
            info = self.finale_instruments.get(uuid or "", {})
            name = self._staff_name(spec) if spec is not None else ""
            if not name and len(members) > 1:
                name = self._group_name(members[0], members[-1])
            if not name:
                name = re.sub(r"NoName$", "", info.get("name") or "") or f"Staff {s}"
            trans = self._transposition(spec)
            no_key = spec is not None and spec.find("transposition/chromatic") is not None and trans != (0, 0)
            pid, iid = f"P{len(score.players) + 1}", f"I{len(score.players) + 1}"
            inst = ir.Instrument(id=iid, name=name, finale_uuid=uuid, sound_id=info.get("sound"),
                                 num_staves=len(members), transposition=trans, no_key_signature=no_key)
            score.players.append(ir.Player(id=pid, name=name, instruments=[inst]))
            for k, m in enumerate(members):
                self.staff_to_inst[m] = (iid, k)
                done.add(m)

    def _transposition(self, spec: ET.Element | None) -> tuple[int, int]:
        """Finale staff transposition -> (diatonic, chromatic), written = concert + this."""
        if spec is None:
            return (0, 0)
        t = spec.find("transposition")
        if t is None:
            return (0, 0)
        ks = t.find("keysig")
        if ks is not None:
            interval = _int(ks, "interval")
            adjust = _int(ks, "adjust")
            return (interval, _diatonic_to_semitones(interval, adjust))
        ch = t.find("chromatic")
        if ch is not None:
            d, a = _int(ch, "diatonic"), _int(ch, "alteration")
            return (d, _chromatic_to_semitones(d, a))
        return (0, 0)

    # ------------------------------------------------------------------ flow
    def _flow(self, score: ir.Score, measures, staves: list[int]) -> ir.Flow:
        flow = ir.Flow(id="F1", title=score.info.title, length=F(0))
        meas_start: dict[int, Fraction] = {}
        meas_len: dict[int, Fraction] = {}
        meas_key: dict[int, Key] = {}
        pos = F(0)
        last_sig = None
        last_key = None
        for cmper, m in measures:
            beats, divbeat = _int(m, "beats", 4), _int(m, "divbeat", EDU)
            if beats <= 0 or divbeat <= 0 or _flag(m, "altNumTsig") or _flag(m, "altDenTsig"):
                self.warnings.append(f"measure {cmper}: composite time signature not supported; using 4/4")
                beats, divbeat = 4, EDU
            length = F(beats * divbeat, EDU)
            dbeats, ddiv = beats, divbeat
            if _flag(m, "useDisplayTimesig"):  # Finale ignores dispBeats/dispDivbeat otherwise
                dbeats, ddiv = _int(m, "dispBeats", beats), _int(m, "dispDivbeat", divbeat)
            sig = _time_sig(dbeats, ddiv) if (dbeats and ddiv) else _time_sig(beats, divbeat)
            if cmper == measures[0][0] and F(dbeats * ddiv, EDU) != length and dbeats and ddiv:
                flow.pickup = length
            if sig != last_sig:
                flow.time_signatures.append(ir.TimeSignature(pos=pos, num=sig[0], den=sig[1],
                                                             symbol=None))
                last_sig = sig
            ks = m.find("keySig")
            key = Key(_int(ks, "key")) if ks is not None else (last_key or Key(0))
            if ks is not None and _flag(ks, "keyless"):
                key = Key(0)
            if last_key is None or key.value != last_key.value:
                flow.key_signatures.append(ir.KeySignature(pos=pos, fifths=key.fifths,
                                                           mode="minor" if key.minor else "major"))
                if not key.linear or key.mode > 1:
                    self.warnings.append(f"measure {cmper}: non-standard key mode {key.mode} treated as major")
                last_key = key
            meas_start[cmper], meas_len[cmper], meas_key[cmper] = pos, length, key
            flow.bar_starts.append(pos)
            pos += length
        flow.length = pos
        self.meas_start, self.meas_len, self.meas_key = meas_start, meas_len, meas_key

        gfholds = self.detail_map("gfhold", "cmper1", "cmper2")
        frames = defaultdict(dict)
        for e in self.score_records("frameSpec"):
            frames[int(e.get("cmper"))][int(e.get("inci", 0))] = e
        tuplets = defaultdict(list)
        for e in self.details["tupletDef"]:
            if e.get("part") in (None, "0"):
                tuplets[int(e.get("entnum"))].append(e)
        artics = defaultdict(list)
        for e in self.details["articAssign"]:
            if e.get("part") in (None, "0"):
                artics[int(e.get("entnum"))].append(_int(e, "articDef"))
        artic_defs = self.by_cmper("articDef")
        clef_defs = self._clef_defs()
        specs = self.by_cmper("staffSpec")
        clef_lists = defaultdict(list)
        for e in self.score_records("clefList"):
            clef_lists[int(e.get("cmper"))].append(e)

        self.entry_pos: dict[int, tuple[int, Fraction]] = {}  # entnum -> (staff, position)
        staff_objs: dict[int, ir.Staff] = {}
        for s in staves:
            iid, k = self.staff_to_inst[s]
            st = ir.Staff(instrument=iid, index=k)
            staff_objs[s] = st
            flow.staves.append(st)
            voices: dict[tuple[int, int], ir.Voice] = {}
            spec = specs.get(s)
            last_clef = None
            default_clef_idx = _int(spec, "defaultClef", 0) if spec is not None else 0
            for cmper, _m in measures:
                hold = gfholds.get((s, cmper))
                mstart = meas_start[cmper]
                # clefs
                if hold is not None and _int(hold, "clefListID"):
                    for ce in sorted(clef_lists[_int(hold, "clefListID")], key=lambda e: _int(e, "xEduPos")):
                        clef = clef_defs.get(_int(ce, "clefIndex"), "clef.treble")
                        if clef != last_clef:
                            st.clefs.append(ir.Clef(pos=mstart + F(_int(ce, "xEduPos"), EDU), clef=clef))
                            last_clef = clef
                else:
                    idx = _int(hold, "clefID", default_clef_idx) if hold is not None else (
                        default_clef_idx if last_clef is None else None)
                    if idx is not None:
                        clef = clef_defs.get(idx, "clef.treble")
                        if clef != last_clef:
                            st.clefs.append(ir.Clef(pos=mstart, clef=clef))
                            last_clef = clef
                if hold is None:
                    continue
                for layer in range(1, 5):
                    fr = _int(hold, f"frame{layer}")
                    if not fr:
                        continue
                    spec_f = frames[fr].get(0)
                    if spec_f is None:
                        continue
                    self._read_frame(spec_f, layer, mstart, meas_key[cmper], voices, tuplets, artics,
                                     artic_defs, s, cmper)
            for (layer, _v), voice in voices.items():
                voice.layer = layer
            st.voices = [voices[k] for k in sorted(voices)]
            for i, v in enumerate(st.voices):
                v.index = i
        self._expressions(staff_objs)
        self._smart_shapes(staff_objs)
        return flow

    def _clef_defs(self) -> dict[int, str]:
        out = {}
        co = self.root.find("options/clefOptions")
        for d in (co.findall("clefDef") if co is not None else []):
            idx = int(d.get("index", 0))
            char = _int(d, "clefChar")
            middle_c = _int(d, "adjust")
            gtype = CLEF_GLYPH_TYPE.get(char)
            if gtype in ("perc", "perc2"):
                out[idx] = "clef.percussion" if gtype == "perc" else "clef.percussion2"
            elif gtype and (gtype, middle_c) in CLEF_MAP:
                out[idx] = CLEF_MAP[(gtype, middle_c)]
            else:
                out[idx] = DEFAULT_CLEFS.get(idx, "clef.treble")
        for k, v in DEFAULT_CLEFS.items():
            out.setdefault(k, v)
        return out

    # ----------------------------------------------------------------- entries
    def _read_frame(self, fspec, layer, mstart, key: Key, voices, tuplets, artics, artic_defs,
                    staff, meas) -> None:
        start, end = _int(fspec, "startEntry"), _int(fspec, "endEntry")
        chain = []
        e = start
        guard = 0
        while e and guard < 10000:
            chain.append(e)
            if e == end:
                break
            e = int(self.entries[e].get("next", 0)) if e in self.entries else 0
            guard += 1
        offset = F(_int(fspec, "startTime"), EDU)
        # voice 1 and voice 2 within the layer
        t1 = mstart + offset
        t2 = None
        tup_stack: dict[int, list[dict]] = {1: [], 2: []}
        for entnum in chain:
            ent = self.entries.get(entnum)
            if ent is None:
                continue
            v = 2 if _flag(ent, "v2") else 1
            if v == 2 and t2 is None:
                t2 = t1
            if v == 1 and t2 is not None:
                t2 = None
            voice = voices.setdefault((layer, v), ir.Voice(index=0))
            cur = t1 if v == 1 else t2
            dura = _int(ent, "dura", EDU)
            notated = F(dura, EDU)
            grace = _flag(ent, "graceNote")
            # tuplets starting here
            if _flag(ent, "tupletStart") and not grace:
                for td in tuplets.get(entnum, []):
                    sym_n, sym_d = _int(td, "symbolicNum", 3), _int(td, "symbolicDur", 512)
                    ref_n, ref_d = _int(td, "refNum", 2), _int(td, "refDur", 512)
                    if not (sym_n and sym_d and ref_n and ref_d):
                        continue
                    ratio = F(ref_n * ref_d, sym_n * sym_d)
                    outer = _cum_ratio(tup_stack[v])
                    total_symbolic = F(sym_n * sym_d, EDU)
                    tup = {"start": cur, "ratio": ratio, "remaining": total_symbolic,
                           "num": sym_n, "den": F(ref_n * ref_d, sym_d), "unit": F(sym_d, EDU),
                           "outer": outer}
                    tup_stack[v].append(tup)
            ratio = _cum_ratio(tup_stack[v])
            actual = F(0) if grace else notated * ratio
            chord = ir.Chord(pos=cur, dur=actual if not grace else F(0), notated=notated, grace=grace,
                             grace_slash=_flag(ent, "slashGrace"), hidden=_flag(ent, "ignore"))
            if _flag(ent, "isNote"):
                for n in ent.findall("note"):
                    step, octave, alter, midi = key.pitch(_int(n, "harmLev"), _int(n, "harmAlt"))
                    acc = None
                    if _flag(n, "freezeAcci"):
                        acc = "show" if _flag(n, "showAcci") else "hide"
                    if _flag(n, "parenAcci"):
                        acc = "paren"
                    chord.pitches.append(ir.Pitch(midi=midi, step=step, alter=alter,
                                                  tie=_flag(n, "tieStart"), accidental=acc))
            if _flag(ent, "freezeStem"):
                chord.stem = "up" if _flag(ent, "upStem") else "down"
            for adef in artics.get(entnum, []):
                d = artic_defs.get(adef)
                g = ARTIC_GLYPHS.get(_int(d, "charMain")) if d is not None else None
                if g is None:
                    if d is not None:
                        self.warnings.append(f"staff {staff} meas {meas}: articulation glyph "
                                             f"{_int(d, 'charMain')} not recognised")
                    continue
                for a in (g if isinstance(g, tuple) else (g,)):
                    if a == "fermata":
                        chord.fermata = True
                    elif a not in chord.articulations:
                        chord.articulations.append(a)
            if not (chord.hidden and chord.is_rest):
                voice.chords.append(chord)
            self.entry_pos[entnum] = (staff, cur, layer, v, actual)
            if not grace:
                cur = cur + actual
                # close finished tuplets (innermost first)
                stack = tup_stack[v]
                consumed = notated * _cum_ratio(stack)
                for k in range(len(stack) - 1, -1, -1):
                    t = stack[k]
                    inner = _cum_ratio(stack[k + 1:])
                    t["remaining"] -= notated * inner
                while stack and stack[-1]["remaining"] <= 0:
                    t = stack.pop()
                    voice.tuplets.append(ir.Tuplet(pos=t["start"], dur=cur - t["start"], num=t["num"],
                                                   den=int(t["den"]) if t["den"].denominator == 1 else t["num"],
                                                   unit=t["unit"]))
            if v == 1:
                t1 = cur
            else:
                t2 = cur

    # ------------------------------------------------------------ expressions
    def _expressions(self, staff_objs: dict[int, ir.Staff]) -> None:
        defs = self.by_cmper("textExprDef")
        cats = self.by_cmper("markingsCategory")
        for a in self.score_records("measExprAssign"):
            meas = int(a.get("cmper"))
            if meas not in self.meas_start or _flag(a, "hidden"):  # hidden: invisible in Finale
                continue
            staff = _int(a, "staffAssign")
            d = defs.get(_int(a, "textExprID"))
            if d is None or staff not in staff_objs:
                continue
            text = self.text_of_block(_int(d, "textIDKey"))
            plain, music = self.strip_enigma(text)
            pos = self.meas_start[meas] + F(_int(a, "horzEduOff"), EDU)  # xml name of eduPosition
            kind = None
            if music and len(plain) == 1:
                kind = DYNAMIC_GLYPHS.get(ord(plain))
            elif plain.strip() in {"pppp", "ppp", "pp", "p", "mp", "mf", "f", "ff", "fff", "ffff",
                                   "sfz", "sf", "fz", "rfz", "fp", "sfp"}:
                kind = plain.strip()
            cat = cats.get(_int(d, "categoryID"))
            if kind:
                staff_objs[staff].dynamics.append(ir.Dynamic(pos=pos, kind=kind))
            elif cat is not None and cat.findtext("categoryType") == "dynamics":
                self.warnings.append(f"measure {meas}: dynamic expression {plain!r} not recognised")
            elif cat is not None and cat.findtext("categoryType") == "tempoMarks":
                pass  # tempo handled later
            elif plain.strip():
                self.warnings.append(f"measure {meas}: text expression {plain.strip()!r} not converted yet")

    def _smart_shapes(self, staff_objs: dict[int, ir.Staff]) -> None:
        for sh in self.score_records("smartShape"):
            st = sh.findtext("shapeType")
            s_end, e_end = sh.find("startTermSeg/endPt"), sh.find("endTermSeg/endPt")
            if s_end is None or e_end is None:
                continue
            staff = _int(s_end, "inst")
            if staff not in staff_objs:
                continue
            if st and st.startswith("slur"):
                a, b = _int(s_end, "entryNum"), _int(e_end, "entryNum")
                if a in self.entry_pos and b in self.entry_pos:
                    sa, pa, layer, v, _ = self.entry_pos[a]
                    sb, pb, *_ = self.entry_pos[b]
                    voice = self._voice_at(staff_objs[sa], pa)
                    if voice is not None:
                        voice.slurs.append(ir.Slur(pos=pa, end=pb))
                else:
                    self.warnings.append(f"slur {sh.get('cmper')}: endpoints not found")
            elif st in ("cresc", "decresc"):
                p0 = self._shape_pos(s_end)
                p1 = self._shape_pos(e_end)
                if p0 is not None and p1 is not None and p1 > p0:
                    staff_objs[staff].hairpins.append(ir.Hairpin(
                        pos=p0, end=p1, direction="cresc" if st == "cresc" else "dim"))
            elif st:
                self.warnings.append(f"smart shape '{st}' not converted yet")

    def _shape_pos(self, endpt) -> Fraction | None:
        en = _int(endpt, "entryNum")
        if en and en in self.entry_pos:
            return self.entry_pos[en][1]
        meas = _int(endpt, "meas")
        if meas not in self.meas_start:
            return None
        return self.meas_start[meas] + F(_int(endpt, "edu"), EDU)

    @staticmethod
    def _voice_at(staff: ir.Staff, pos: Fraction) -> ir.Voice | None:
        for v in staff.voices:
            if any(c.pos == pos and not c.is_rest for c in v.chords):
                return v
        return staff.voices[0] if staff.voices else None


def _cum_ratio(stack) -> Fraction:
    r = F(1)
    for t in stack:
        r *= t["ratio"]
    return r


def _time_sig(beats: int, divbeat: int) -> tuple[int, int]:
    """Finale beats x EDU-per-beat -> (numerator, denominator)."""
    unit = F(divbeat, EDU * 4)  # fraction of a whole note
    if unit.numerator == 3:      # dotted beat -> compound
        unit = unit / 3
        beats *= 3
    if unit.numerator != 1:
        n = F(beats) * unit
        return n.numerator, n.denominator
    return beats, unit.denominator


def _diatonic_to_semitones(interval: int, key_adjust: int) -> int:
    """Finale key-signature transposition (diatonic steps + change in sharps) -> semitones.

    Transposing C major up `interval` diatonic steps naturally adds NATURAL_FIFTHS sharps
    (up a 5th: +1). Any other key change shifts the interval by fifths (7 semitones each).
    Horn in F: interval 4, adjust 1 -> 7. Clarinet in A: interval 2, adjust -3 -> 3.
    """
    sign = -1 if interval < 0 else 1
    d = abs(interval)
    base = STEP_SEMI[d % 7] + 12 * (d // 7)
    natural = [0, 2, 4, -1, 1, 3, 5][d % 7]
    extra = key_adjust * sign - natural
    delta = (7 * extra) % 12
    if delta > 6:
        delta -= 12
    return sign * (base + delta)


def _chromatic_to_semitones(interval: int, alteration: int) -> int:
    """musxdom Transposer convention: alteration 0 = major/perfect; {2,-1} = minor third up."""
    sign = -1 if interval < 0 else 1
    d = abs(interval)
    return sign * (STEP_SEMI[d % 7] + 12 * (d // 7)) + alteration


def read_musx(path: str | Path) -> ir.Score:
    path = Path(path)
    text = enigma_xml(path)
    return EnigmaReader(text, source=str(path)).read()
