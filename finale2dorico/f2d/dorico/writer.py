"""Write a Score IR as a Dorico project (.dorico).

Dorico's model, in brief (see docs/RESEARCH.md for the evidence):

  kScore
    scorePlayers[]        players, each with instruments (copied from the factory definition)
    flows[]
      flowPlayers[]       player -> player stream, stave streams, voice streams
      elementTables[]     shared definitions events point at (time sigs, keys, dynamics, slurs)
      blocks[]            events; one block per stream, placed by a blockInstance at 0
      eventStreams[]      kGlobalTimebaseStream | kPlayerStream | kInstrumentStaveStream | kVoiceStream
    layouts[]             full score + one part per player

Times are fractions of a crotchet; pitches are concert MIDI numbers with the concert
letter in kNoteSpelling. Rests are implicit: Dorico fills gaps itself. Tied notes are
one long note; the notated split is forced with kNoteSplitDurations.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from doricokit import container
from doricokit import format as dtn
from doricokit.format import Node

from .. import ir
from .install import DoricoInstall
from .tree import NO_LAYOUT, A, E, L, deep_copy, event_head, fstr, prop, ptable, svl
from . import layout as layout_mod

F = Fraction

# Dynamic intensity: {int: 0=forte|1=piano}, {}, {bool: mezzo}, {int: count}
_DYN = {"m": None}
for n in range(1, 7):
    _DYN["p" * n] = (1, False, n)
    _DYN["f" * n] = (0, False, n)
_DYN["mp"] = (1, True, None)
_DYN["mf"] = (0, True, None)
# intensities count the letters (f/ff = 1/2, p/pp = 1/2, mf/mp = 0): Round 9 mf-mp = kDown 0/0
COMBINED_DYNAMICS = {"fp": ("kDown", 1, 1), "ffp": ("kDown", 2, 1), "fpp": ("kDown", 1, 2),
                     "pf": ("kUp", 1, 1), "mfmp": ("kDown", 0, 0), "mfp": ("kDown", 0, 1),
                     "fmp": ("kDown", 1, 0), "mpmf": ("kUp", 0, 0), "mpf": ("kUp", 0, 1),
                     "pmf": ("kUp", 1, 0)}
# (type, intensityLevel[, has z]); the user's projects use Sfz at levels 1 and 2 (sffz).
# sf = Sfz with kDynamicRinforzandoAndSforzandoHaveZ false (ref-extras2); rf / sff / rff by analogy
FORCE_DYNAMICS = {"fz": ("kForceDynamicFz", 1), "mfz": ("kForceDynamicMfz", 1),
                  "rfz": ("kForceDynamicRfz", 1), "sfz": ("kForceDynamicSfz", 1),
                  "sffz": ("kForceDynamicSfz", 2), "ffz": ("kForceDynamicFz", 2),
                  "rffz": ("kForceDynamicRfz", 2),  # ffz / rffz: Round 9
                  "sf": ("kForceDynamicSfz", 1, False), "sff": ("kForceDynamicSfz", 2, False),
                  "rf": ("kForceDynamicRfz", 1, False), "rff": ("kForceDynamicRfz", 2, False)}

# barline kinds -> Dorico barlineChangeIfAny/type (Round 7 + enum names in Dorico5.exe)
BARLINE_TYPES = {"double": "kDouble", "final": "kFinal", "dashed": "kDashed", "thick": "kThick",
                 "tick": "kTick", "start_repeat": "kStartRepeat", "end_repeat": "kEndRepeat",
                 "end_start_repeat": "kEndAndStartRepeat"}

ARTICULATIONS = {
    # IR name -> (property, value)
    "staccato": ("kArticulationDuration", "kStaccato"),
    "staccatissimo": ("kArticulationDuration", "kStaccatissimo"),
    "tenuto": ("kArticulationDuration", "kTenuto"),
    "staccato-tenuto": ("kArticulationDuration", "kStaccatoTenuto"),
    "accent": ("kArticulationForce", "kAccent"),
    "marcato": ("kArticulationForce", "kMarcato"),
}

# order of events that share a position (as Dorico saves them)
_EVENT_RANK = {"BarDivisionEventDefinition": 0, "TonalityDivisionEventDefinition": 0,
               "ClefEventDefinition": 0, "TupletEventDefinition": 0,
               "GraceNoteEventDefinition": 1, "NoteEventDefinition": 1, "RestEventDefinition": 1,
               "SlurEventDefinition": 2}

ACCIDENTAL_IDS = {-2: "doubleflat", -1: "flat", 0: "natural", 1: "sharp", 2: "doublesharp"}
SHARP_ORDER = "FCGDAEB"
MAJOR_SHARP_TONICS = ["C", "G", "D", "A", "E", "B", "F", "C"]   # + accidental
MAJOR_FLAT_TONICS = ["C", "F", "B", "E", "A", "D", "G", "C"]
MINOR_SHARP_TONICS = ["A", "E", "B", "F", "C", "G", "D", "A"]
MINOR_FLAT_TONICS = ["A", "D", "G", "C", "F", "B", "E", "A"]
STEP_INDEX = {s: i for i, s in enumerate("CDEFGAB")}


FILE_VERSION = "1.1299"  # kScore/fileVersion of Dorico 5.1.60

GRADUAL_TEMPOS = {  # kind -> (preset, text, abbreviation, final tempo %) as in the user's projects
    "rit": ("tempopreset.ritardando", "ritardando", "rit.", 75.0),
    "rall": ("tempopreset.rall", "rallentando", "rall.", 75.0),
    "accel": ("tempopreset.accel", "accelerando", "accel.", 125.0)}
OTTAVA_ENTITIES = {"up8": "line.ottava.up.8", "down8": "line.ottava.down.8",
                   "up15": "line.ottava.up.15", "down15": "line.ottava.down.15"}
ARPEGGIO_TYPES = {"normal": "kUpArpeggio", "up": "kUpArpeggio", "down": "kDownArpeggio", "bracket": "kNoArpeggio"}

# technique kind (ir.Technique) -> Dorico playing-technique appearance (factory library);
# mute/open depend on the instrument family (see _technique_appearance)
def _line_style(ln: ir.Line) -> str:
    """Dorico factory line style for a line's look (Round 12). Dorico's hooks point inward
    (towards the staff); its hooked and arrowed dashed styles use short dashes."""
    if ln.body == "wavy":
        return "linestyle.wigglyLine"  # Finale's wavy custom lines use the same wiggleTrill glyph
    if ln.arrow_end:
        return "linestyle.dashedLineShortSolidArrowhead" if ln.body == "dashed" else "linestyle.solidLineSolidArrowhead"
    base = "linestyle.dashedLineShort" if ln.body == "dashed" else "linestyle.solidLine"
    if ln.hook_start and ln.hook_end:
        return base + "InwardHooks"
    if ln.hook_end:
        return base + "InwardHook"
    return base  # a start-only hook is added as a start cap (see _line_event)


def _esc(text: str) -> str:
    """Text inside a property's string value: one line, no straight double quotes."""
    return " ".join(text.split()).replace('"', "\u201d")


TECHNIQUE_APPEARANCES = {"pizz": "pta.pizzText", "arco": "pta.arcoText",
                         "up-bow": "pta.stringsUpBow", "down-bow": "pta.stringsDownBow",
                         "con-sord": "pta.conSordinoText", "senza-sord": "pta.senzaSordinoText",
                         "ord": "pta.ordinarioText", "sul-pont": "pta.sulPontText", "sul-tasto": "pta.sulTastoText"}


@dataclass
class Options:
    # how to force Finale's notated durations onto Dorico notes:
    #   "ties": only tie chains get kNoteSplitDurations (default)
    #   "all":  every note gets kNoteSplitDurations (Dorico won't renotate anything)
    #   "none": let Dorico notate everything
    force_durations: str = "ties"
    seed: str | None = None          # Dorico project to borrow library/options from
    # project library: "factory" = a new project's library built from the user's Dorico install
    # (default; Round 2: without a real library Dorico draws no noteheads), "seed" = copy a seed
    # project's library, "instruments" = instrument definitions only (Round 1: no noteheads)
    library: str = "factory"
    options_from_seed: bool = False  # copy scoreOptions / notationOptions / layoutOptions from seed
    playback_from_seed: bool = False # copy playModeData skeleton from seed
    write_dtn: bool = False          # score.dtn instead of score.xml
    parts: bool = True               # create one part layout per player
    group_dynamics: bool = True      # join chained dynamics/hairpins into Dorico dynamic groups
    # link identical dynamic groups at the same position across staves: "rhythm" (default; only
    # staves playing the same rhythm over the phrase, i.e. that would condense together),
    # "identical" (any identical group), "none"
    link_dynamics: str = "rhythm"
    harp_glissando_straight: bool = True  # user's preference: harp glissandi as straight lines
    dynamic_group_overlap: Fraction = Fraction(1, 2)  # a hairpin may overhang the next item by this much
    dynamic_group_gap: Fraction = Fraction(1)  # max gap (crotchets) between grouped items (user grouped mp + a cresc starting 1 beat later)


@dataclass
class _Ids:
    instrument: int = 0
    player: int = 0
    layout: int = 0
    flow: int = 0
    event: int = 0
    eventStream: int = 0
    blockInstance: int = 1000
    block: int = 0
    stave: int = 0
    eventGroup: int = 0

    def next(self, kind: str) -> int:
        v = getattr(self, kind)
        setattr(self, kind, v + 1)
        return v


@dataclass
class _Stream:
    sid: int
    stype: str
    events: list[Node] = field(default_factory=list)
    biid: int = -1   # its block instance (assigned at creation: glissandi reference it)


class _ElementTables:
    """Per-flow shared element definitions (one definition per referencing event here)."""

    ORDER = ["DynamicGroup", "BarDivision", "TonalityDivision", "Slur", "Lyric"]

    def __init__(self):
        self.tables: dict[str, list[Node]] = {k: [] for k in self.ORDER}
        self.linked: dict[tuple, tuple[Node, int, set]] = {}  # signature -> (element, id, stream ids)

    def link(self, kind: str, signature: tuple, stream_id: int, event_id: int) -> int | None:
        """Reuse an identical element from another stream (Dorico "linked" items: one element,
        several referencing events). Returns the element id, or None if there is none to share."""
        hit = self.linked.get((kind, signature))
        if hit is None or stream_id in hit[2]:
            return None
        elem, elem_id, streams = hit
        ref = elem.child("referencingEventIDs")
        ref.value = f"{ref.value},{event_id}"
        streams.add(stream_id)
        return elem_id

    def remember(self, kind: str, signature: tuple, stream_id: int, elem_id: int) -> None:
        self.linked.setdefault((kind, signature), (self.tables[kind][elem_id], elem_id, {stream_id}))

    def add(self, kind: str, event_id: int, *body: Node, sub_elements: list[Node] | None = None) -> int:
        elem_id = len(self.tables[kind])
        self.tables[kind].append(E(f"{kind}ElementDefinition",
                                   L("elementID", elem_id),
                                   L("referencingEventIDs", event_id),
                                   ptable([]),
                                   A("subElements", sub_elements or []),
                                   *body))
        return elem_id

    def node(self) -> Node:
        return E("elementTables", A("array", [
            E(f"{k}ElementTableDefinition", A("array", self.tables[k])) for k in self.ORDER]))


class DoricoWriter:
    def __init__(self, score: ir.Score, install: DoricoInstall, options: Options | None = None):
        self.score = score
        self.install = install
        self.opt = options or Options()
        self.ids = _Ids()
        self.report: list[str] = []
        self.seed: Node | None = None
        if self.opt.seed:
            self.seed = _load_score(self.opt.seed)
        # resolved per instrument
        self.player_ids: dict[str, int] = {}
        self.instrument_ids: dict[str, int] = {}
        self.entities: dict[str, str] = {}
        self.stave_ids: dict[tuple[str, int], int] = {}
        self.custom_names: dict[str, str] = {}

    # ------------------------------------------------------------------ public
    def build(self) -> dtn.Document:
        self._resolve_instruments()
        players = self._score_players()
        flows = [self._flow(f) for f in self.score.flows]
        layouts = self._layouts()
        root = E("kScore",
                 L("fileVersion", self._file_version()),
                 None,  # idGenerators placeholder (filled below)
                 self._info(),
                 self._score_options(),
                 self._library(),
                 players,
                 self._player_groups(),
                 E("flows", A("array", flows)),
                 E("textFlows", A("array", [])),
                 layouts,
                 self._play_mode_data(),
                 L("printingModeData", ""))
        root.children.insert(1, self._id_generators())
        root.children = [c for c in root.children if c is not None]
        return dtn.Document(root=root, marker=0)

    def write(self, path: str | Path) -> None:
        doc = self.build()
        path = Path(path)
        if self.opt.write_dtn:
            score_name, score_bytes = "score.dtn", dtn.encode(doc)
        else:
            score_name, score_bytes = "score.xml", dtn.to_xml(doc, with_marker=False).encode("utf-8")
        container_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
                     '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                     '\t<rootfiles>\n'
                     f'\t\t<rootfile full-path="{score_name}" media-type="application/vnd.steinberg.dorico-project"/>\n'
                     '\t</rootfiles>\n</container>\n')
        scoreinfo = ('<?xml version="1.0" encoding="utf-8"?>\n<kScore>\n'
                     f'\t<kTitle>{_xml_escape(self.score.info.title)}</kTitle>\n'
                     f'\t<kComposer>{_xml_escape(self.score.info.composer)}</kComposer>\n</kScore>\n')
        stamp = time.localtime()[:6]
        files = [("META-INF/container.xml", container_xml.encode()),
                 (score_name, score_bytes),
                 ("supplementary_data/scoreinfo/scoreinfo.xml", scoreinfo.encode())]
        if self.opt.library == "factory" and getattr(self, "_library_node", None) is not None:
            files.append(("scorelibrary.dtn", self._factory.scorelibrary_dtn(self._library_node)))
        if self.opt.library == "seed" and self.opt.seed:
            seed = {e.name: e.data for e in container.read(self.opt.seed)}
            files += [(n, seed[n]) for n in ("scorelibrary.dtn", "scorelibrary.xml") if n in seed]
        container.write(path, [container.Entry(n, d, time=stamp) for n, d in files], protect=self.opt.seed)

    # ------------------------------------------------------------- top level
    def _file_version(self) -> str:
        # Dorico 5.1.60 writes 1.1299 (checked in the user's projects; 4.0.5 wrote 1.1096).
        # An older value makes Dorico treat the file as Dorico 3 and run its upgrade path.
        return FILE_VERSION

    def _id_generators(self) -> Node:
        i = self.ids
        return E("idGenerators",
                 L("instrument", i.instrument), L("player", i.player), L("playerGroups", 0),
                 L("layout", i.layout), L("flow", i.flow), L("event", i.event),
                 L("eventStream", i.eventStream), L("blockInstance", i.blockInstance),
                 L("block", i.block), L("stave", i.stave), L("frameChain", 0), L("page", 0),
                 L("textFlow", 0), L("eventGroup", i.eventGroup), L("doodle", -1), L("doodleGroup", -1))

    def _info(self) -> Node:
        inf = self.score.info
        now = str(int(time.time()))
        return E("info",
                 L("title", inf.title), L("subtitle", inf.subtitle), L("dedication"),
                 L("composer", inf.composer), L("arranger", inf.arranger), L("lyricist", inf.lyricist),
                 L("artist"), L("copyist"), L("publisher"), L("editor"), L("copyright", inf.copyright),
                 L("workNumber"), L("composerDates"), L("compositionYear"), L("otherInfo"),
                 L("createdDate", now), L("lastSavedDate", now),
                 L("createdVersion", "5.1.60"), L("lastSavedVersion", "5.1.60"),
                 L("originalSourcePath", self.score.source), L("filePath"),
                 L("generatePreviews", "true"), L("resolveMarkdown", "false"),
                 L("originator", "kDorico"))

    def _score_options(self) -> Node | None:
        if self.opt.options_from_seed and self.seed is not None:
            return deep_copy(self.seed.find("scoreOptions"))
        return None

    def _library(self) -> Node | None:
        lib = self._library_inner()
        # instruments that carry chord symbols in the source show them (Dorico shows chord symbols
        # only for instruments whose definition has showChordSymbols, e.g. piano, guitar)
        want = {self.entities.get(cs.instrument) for f in self.score.flows for cs in f.chord_symbols} - {None}
        ents = lib.find("instruments/entities") if lib is not None else None
        for e in (ents.children or []) if ents is not None else []:
            if e.text("entityID") in want and e.child("showChordSymbols") is not None:
                e.child("showChordSymbols").value = "true"
        return lib

    def _library_inner(self) -> Node | None:
        if self.opt.library == "none":
            return None
        if self.opt.library == "seed" and self.seed is not None:
            lib = deep_copy(self.seed.find("library"))
            # make sure every instrument we use is defined in the project library
            ents = lib.find("instruments/entities")
            have = {e.text("entityID") for e in (ents.children or [])} if ents else set()
            extra = [deep_copy(self.install.instruments[e]) for e in sorted(set(self.entities.values()))
                     if e not in have]
            if extra:
                if ents.children is None:
                    ents.children, ents.value = [], None
                ents.children.extend(extra)
            return lib
        used = sorted(set(self.entities.values()))
        if self.opt.library == "factory":
            # a new project's library, from the user's Dorico install, plus what we use
            from .library import FactoryLibrary
            names = []
            for e in used:
                nid = self.install.instruments[e].text("nameID")
                if nid in self.install.instrument_names:
                    names.append(deep_copy(self.install.instrument_names[nid]))
            want = sorted({c.clef for f in self.score.flows for st in f.staves for c in st.clefs})
            want += sorted({a for f in self.score.flows for st in f.staves for t in st.techniques
                            for a in [self._technique_appearance(t.kind, st.instrument)] if a})
            want += sorted({OTTAVA_ENTITIES[o.kind] for f in self.score.flows for st in f.staves for o in st.ottavas})
            want += sorted({_line_style(ln) for f in self.score.flows for st in f.staves for ln in st.lines})
            if any(ln.hook_start and not ln.hook_end for f in self.score.flows for st in f.staves for ln in st.lines):
                want.append("lineannotation.inwardHookAxisAligned")
            want += sorted({f"ornament.{c.ornament}" for f in self.score.flows for st in f.staves
                            for v in st.voices for c in v.chords if c.ornament})
            want += sorted({f"tempopreset.{p}" for p in ("ritardando", "rall", "accel")}
                           if any(f.gradual_tempos for f in self.score.flows) else [])
            self._factory = FactoryLibrary(self.install.dir)
            self._library_node = self._factory.build(
                extra={"instruments": [deep_copy(self.install.instruments[e]) for e in used],
                       "instrumentNames": names},
                want=want)
            return self._library_node
        # "instruments": only the instrument + name definitions we use
        insts = [deep_copy(self.install.instruments[e]) for e in used]
        names = []
        for e in used:
            nid = self.install.instruments[e].text("nameID")
            if nid in self.install.instrument_names:
                names.append(deep_copy(self.install.instrument_names[nid]))
        return E("library",
                 L("fileVersion", self._file_version()),
                 E("instruments", A("entities", insts)),
                 E("instrumentNames", A("entities", names), L("language", "kEnglish")))

    def _play_mode_data(self) -> Node | None:
        if self.opt.playback_from_seed and self.seed is not None:
            pm = deep_copy(self.seed.find("playModeData"))
            # keep the engine/template choice, drop per-instrument routing (it names seed instruments)
            for path in ("instrumentPlaybackData/entries", "mixerChannelData/entries"):
                n = pm.find(path)
                if n is not None:
                    n.children, n.value = None, ""
            return pm
        return None

    # --------------------------------------------------------------- players
    def _resolve_instruments(self) -> None:
        for p in self.score.players:
            self.player_ids[p.id] = self.ids.next("player")
            for inst in p.instruments:
                if inst.dorico_id and inst.dorico_id in self.install.instruments:
                    eid, how = inst.dorico_id, "given"
                else:
                    eid, how = self.install.resolve(inst.sound_id, inst.name, inst.num_staves,
                                                    tuple(inst.transposition) if inst.transposition is not None else None,
                                                    inst.no_key_signature,
                                                    self._first_clef(inst.id), inst.key)
                n_def = int(self.install.instruments[eid].text("numStaves") or 1)
                if n_def != inst.num_staves:
                    self.report.append(f"instrument '{inst.name}': source has {inst.num_staves} staves, "
                                       f"Dorico '{eid}' has {n_def}")
                self.entities[inst.id] = eid
                if eid.startswith("instrument.generic.") or how.startswith("fallback"):
                    self.custom_names[inst.id] = inst.name
                self.instrument_ids[inst.id] = self.ids.next("instrument")
                for s in range(max(inst.num_staves, n_def)):
                    self.stave_ids[(inst.id, s)] = self.ids.next("stave")
                self.report.append(f"instrument '{inst.name}' -> {eid} ({how})")

    def _first_clef(self, iid: str) -> str | None:
        for f in self.score.flows:
            for st in f.staves:
                if st.instrument == iid and st.index == 0 and st.clefs:
                    return st.clefs[0].clef
        return None

    def _instrument_node(self, inst: ir.Instrument, suffix: int | None) -> Node:
        eid = self.entities[inst.id]
        ent = self.install.instruments[eid]
        nd = dict(self.install.name_data(eid))
        if inst.id in self.custom_names:
            nm = self.custom_names[inst.id]
            short = inst.short_name or nm
            nd.update(uiName=nm, singularFullName=nm, pluralFullName=nm,
                      singularShortName=short, pluralShortName=short)
        pid = ent.find("pitchedInstrumentData")
        d = int(pid.text("transposedDiatonicTransposition") or 0) if pid else 0
        c = int(pid.text("transposedChromaticTransposition") or 0) if pid else 0
        show = pid.text("showTransposition") if pid else "kNever"

        def fname(key: str, text: str) -> Node:
            return E(key, A("paragraphs", [E("paragraph",
                                             L("paragraphStyleID", "paragraph.stafflabels"),
                                             L("content"),
                                             A("fragments", [E("fragment", L("content", text),
                                                               E("textFragmentStyle", L("libraryStyle")))]))]))

        formatted = [fname(k, nd[k]) for k in
                     ("singularFullName", "singularShortName", "pluralFullName", "pluralShortName")]
        clefs = []
        cl = ent.find("clefs/clefIDsForEachStave")
        for sc in (cl.children or []) if cl else []:
            clefs.append(E("clef", *[deep_copy(x) for x in sc.children or []]))
        trans = None
        if d or c:
            num, quality = _interval(d, c)
            trans = E("transposition", L("intervalForTransposingScores",
                                         svl(f"{{int: {num}}}", f'{{string: "{quality}"}}')))
        else:
            trans = L("transposition")
        return E("instrument",
                 L("entityID", eid), L("baseInstrumentEntityID", eid),
                 L("frettedInstrumentDataEntityID", ent.text("frettedInstrumentDataID")),
                 L("instrumentID", self.instrument_ids[inst.id]),
                 L("numStaves", ent.text("numStaves") or 1),
                 L("transpositionVisibility", show or "kFollowOptions"),
                 L("instrumentColour", _colour(self.instrument_ids[inst.id])),
                 L("suffix", suffix) if suffix else None,
                 L("variantString"), L("suffixType", "kArabic"),
                 L("standardRange", pid.text("standardRange")) if pid else None,
                 L("advancedRange", pid.text("advancedRange")) if pid else None,
                 E("nameData", L("uiName", nd["uiName"]), L("customVariantString"),
                   L("singularFullName", nd["singularFullName"]),
                   L("singularShortName", nd["singularShortName"]),
                   L("pluralFullName", nd["pluralFullName"]),
                   L("pluralShortName", nd["pluralShortName"]),
                   L("gender", nd["gender"]), L("language", nd["language"])),
                 E("formattedNameData", L("uiName", nd["uiName"]), L("gender", nd["gender"]),
                   L("language", nd["language"]), *formatted),
                 trans,
                 deep_copy(ent.find("staveDefinition")),
                 A("clefs", clefs))

    def _score_players(self) -> Node:
        # number players that share an instrument type: Flute 1, Flute 2 ...
        # (players with a custom name, e.g. generic "Staff 1"/"Staff 2", only when names collide)
        def name_key(inst):
            return (self.entities[inst.id], self.custom_names.get(inst.id))

        counts: dict[tuple, int] = {}
        for p in self.score.players:
            for i in p.instruments[:1]:
                counts[name_key(i)] = counts.get(name_key(i), 0) + 1
        # use the source's own numbers ("Horn in F 3") when every player of the type has a
        # distinct one; otherwise number in score order
        source_num: dict[tuple, dict[str, int]] = {}
        for p in self.score.players:
            i = p.instruments[0]
            m = re.search(r"\s(\d+)$", i.name or "")
            source_num.setdefault(name_key(i), {})[p.id] = int(m.group(1)) if m else None
        seen: dict[tuple, int] = {}
        out = []
        for p in self.score.players:
            insts = []
            for k, inst in enumerate(p.instruments):
                nk = name_key(inst)
                suffix = None
                if k == 0 and counts.get(nk, 0) > 1:
                    nums = source_num.get(nk, {})
                    if None not in nums.values() and len(set(nums.values())) == len(nums):
                        suffix = nums[p.id]
                    else:
                        seen[nk] = seen.get(nk, 0) + 1
                        suffix = seen[nk]
                insts.append(self._instrument_node(inst, suffix))
            first = dict(self.install.name_data(self.entities[p.instruments[0].id]))
            if p.instruments[0].id in self.custom_names:
                first["singularFullName"] = first["singularShortName"] = self.custom_names[p.instruments[0].id]
            base = first["singularFullName"]
            sfx = insts[0].text("suffix")
            display = f"{base} {sfx}" if sfx else base
            if len(p.instruments) > 1:  # doubling player: "Piccolo & Flute" (as Dorico names them)
                names = []
                for inst in p.instruments:
                    nd = dict(self.install.name_data(self.entities[inst.id]))
                    n = self.custom_names.get(inst.id, nd["singularFullName"])
                    m = re.search(r"\s(\d+)$", inst.name or "")
                    names.append(f"{n} {m.group(1)}" if m else n)
                display = " & ".join(names)
            out.append(E("scorePlayer",
                         L("playerID", self.player_ids[p.id]),
                         L("soloPlayer", "false" if p.section else "true"),
                         L("baseName", base), L("automaticBaseName", "true"),
                         L("displayName", display),
                         L("chordSymbolPlayerInstrumentVisibility", "kShowIfPlayerHasRhythmSectionInstrument"),
                         L("capoChordSymbolPlayerInstrumentVisibility", "kShowIfPlayerHasRhythmSectionInstrument"),
                         L("chordSymbolPlayerLayoutVisibility", "kShowInFullScoreAndParts"),
                         L("chordDiagramFrettedInstrumentDataID"),
                         L("baseShortName", first["singularShortName"]),
                         L("displayShortName", first["singularShortName"] + (f" {sfx}" if sfx else "")),
                         L("isSoloist", "false"),
                         A("instruments", insts)))
        return E("scorePlayers", A("array", out))

    def _player_groups(self) -> Node:
        ids = ",".join(str(self.player_ids[p.id]) for p in self.score.players)
        return E("scorePlayerGroups", A("array", [E("scorePlayerGroup",
                                                    L("name"), L("shortName"), L("groupID", -1),
                                                    L("playerIDs", ids), L("insertionIndex", 0))]))

    # ----------------------------------------------------------------- flows
    def _flow(self, flow: ir.Flow) -> Node:
        fid = self.ids.next("flow")
        tables = _ElementTables()
        self._note_index: dict = {}
        self._grace_index: dict = {}
        self._pending_gliss: list = []
        streams: list[_Stream] = []

        def new_stream(stype: str) -> _Stream:
            s = _Stream(self.ids.next("eventStream"), stype)
            s.biid = self.ids.next("blockInstance")
            streams.append(s)
            return s

        glob = new_stream("kGlobalTimebaseStream")
        self._global_events(flow, glob, tables)

        flow_players = []
        staves_by_inst: dict[str, list[ir.Staff]] = {}
        for st in flow.staves:
            staves_by_inst.setdefault(st.instrument, []).append(st)
        for p in self.score.players:
            pstream = new_stream("kPlayerStream")
            fpis = []
            for inst in p.instruments:
                iid = self.instrument_ids[inst.id]
                ent = self.install.instruments[self.entities[inst.id]]
                n_staves = int(ent.text("numStaves") or 1)
                ir_staves = {s.index: s for s in staves_by_inst.get(inst.id, [])}
                stave_infos, voice_infos = [], []
                stave_streams = {}
                for k in range(n_staves):
                    ss = new_stream("kInstrumentStaveStream")
                    stave_streams[k] = ss
                    stave_infos.append(E("staveStreamInfo",
                                         L("staveStreamID", ss.sid), L("instrumentID", iid),
                                         L("nthStaveInInstrument", k),
                                         L("staveID", self.stave_ids[(inst.id, k)]),
                                         L("ossia", "kNone"),
                                         E("divisiIndex", L("index", -1)),
                                         E("extraStaveIndex", L("position", "kAbove"), L("index", -1))))
                voices_made = 0
                for k in sorted(ir_staves):
                    st = ir_staves[k]
                    target = min(k, n_staves - 1)
                    if k >= n_staves:
                        self.score.warnings.append(
                            f"{inst.name}: source staff {k + 1} folded onto Dorico stave {n_staves}")
                    self._stave_events(st, stave_streams[target], tables, ent, target, flow)
                    for v_i, voice in enumerate(st.voices):
                        vs = new_stream("kVoiceStream")
                        direction = "kPreferStemsUp" if v_i % 2 == 0 else "kPreferStemsDown"
                        voice_infos.append(E("voiceStreamInfo",
                                             L("voiceStreamID", vs.sid), L("instrumentID", iid),
                                             L("defaultLogicalStaveID", self.stave_ids[(inst.id, target)]),
                                             L("ossia", "kNone"), L("voiceDirection", direction),
                                             L("slashType", "kWithoutSlashes")))
                        self._voice_key = (inst.id, k, v_i)
                        self._voice_events(voice, vs, tables)
                        if v_i == 0:
                            self._technique_events(st, vs, inst.id)
                        voices_made += 1
                if voices_made == 0:
                    vs = new_stream("kVoiceStream")
                    voice_infos.append(E("voiceStreamInfo",
                                         L("voiceStreamID", vs.sid), L("instrumentID", iid),
                                         L("defaultLogicalStaveID", self.stave_ids[(inst.id, 0)]),
                                         L("ossia", "kNone"), L("voiceDirection", "kPreferStemsUp"),
                                         L("slashType", "kWithoutSlashes")))
                fpis.append(E("flowPlayerInstrument", L("instrumentID", iid),
                              A("staveStreamInfos", stave_infos), A("voiceStreamInfos", voice_infos)))
            flow_players.append(E("flowPlayer", L("playerID", self.player_ids[p.id]),
                                  L("eventStreamID", pstream.sid),
                                  A("flowPlayerInstruments", fpis),
                                  A("staveSizeOverrides", [])))

        self._resolve_glissandi()
        blocks, instances, estreams = [], [], []
        for s in streams:
            bid = self.ids.next("block")
            biid = s.biid
            s.events.sort(key=lambda e: (F(e.text("position")), F(e.text("secondaryPosition") or "0"),
                                         _EVENT_RANK.get(e.tag, 3)))
            blocks.append(E("block", L("blockID", bid), L("parentEventStreamType", s.stype),
                            A("events", s.events)))
            instances.append(E("blockInstance", L("blockInstanceID", biid), L("blockID", bid),
                               L("streamID", s.sid), L("position", 0)))
            estreams.append(E("eventStream", L("streamID", s.sid), L("blockInstanceIDs", biid),
                              L("eventStreamType", s.stype)))

        notation = None
        if self.opt.options_from_seed and self.seed is not None:
            seed_flow = self.seed.find("flows/array").children[0]
            notation = deep_copy(seed_flow.find("notationOptions"))
        return E("flow",
                 L("flowID", fid), L("flowName", flow.title or f"Flow {fid + 1}"),
                 L("playerAcquisitionPolicy", "1,1"),
                 E("minimumNotatedLength", L("length", flow.length), L("behaviour", "kNotateBeyondLength")),
                 E("flowPlayers", A("array", flow_players)),
                 tables.node(),
                 notation,
                 E("blocks", A("array", blocks)),
                 E("blockInstances", A("array", instances)),
                 E("eventStreams", A("array", estreams)),
                 E("flowInfo", L("title", flow.title), L("subtitle"), L("dedication"), L("composer"),
                   L("arranger"), L("lyricist"), L("artist"), L("copyist"), L("publisher"), L("editor"),
                   L("copyright"), L("workNumber"), L("composerDates"), L("compositionYear"),
                   L("otherInfo")),
                 E("flowVideoData", L("hasVideoAttached", "false"), L("videoFilename"),
                   L("videoAttachmentPosition", 0), E("properties", A("entries", []))),
                 E("automationStreamTable", A("entries", [])),
                 E("condensedStreams", A("condensedStreams", [])),
                 E("editingLocks", A("entries", [])))

    # ---------------------------------------------------------- global stream
    def _global_events(self, flow: ir.Flow, glob: _Stream, tables: _ElementTables) -> None:
        barlines = {b.pos: b.kind for b in flow.barlines}
        for ts in flow.time_signatures:
            eid = self.ids.next("event")
            pickup = ts.pos == 0 and flow.pickup > 0
            elem = self._bar_division(ts, eid, tables, flow.pickup if pickup else "", barlines.pop(ts.pos, ""))
            ev = E("BarDivisionEventDefinition", *event_head("x", eid, ts.pos, 0),
                   L("barDivisionElementID", elem))
            glob.events.append(ev)
            if pickup:
                self.score.warnings.append(f"pick-up bar of {flow.pickup} crotchets written with an "
                                           "unconfirmed encoding (irregularBarLength)")
        # barline changes without a time signature change: the current signature, hidden, plus the
        # barline (Round 7: BarDivision element with kTimeSignatureHide and barlineChangeIfAny)
        for pos, kind in sorted(barlines.items()):
            cur = next((t for t in reversed(flow.time_signatures) if t.pos <= pos), None) or \
                ir.TimeSignature(F(0), 4, 4)
            hidden = ir.TimeSignature(pos, cur.num, cur.den, list(cur.groups), cur.symbol, hidden=True)
            eid = self.ids.next("event")
            elem = self._bar_division(hidden, eid, tables, "", kind)
            glob.events.append(E("BarDivisionEventDefinition", *event_head("x", eid, pos, 0),
                                 L("barDivisionElementID", elem)))
        self._repeat_events(flow, glob)
        self._chord_symbol_events(flow, glob)
        self._global_key_and_more(flow, glob, tables)

    _ACCIDENTALS = {-2: "kDoubleFlat", -1: "kFlat", 0: "kNatural", 1: "kSharp", 2: "kDoubleSharp"}
    _QUALITIES = {"major": "kMajor", "minor": "kMinor", "diminished": "kDiminished", "augmented": "kAugmented",
                  "half-diminished": "kMinor"}
    _INTERVALS = {None: "kNone", "6": "k6", "7": "k7", "9": "k9", "11": "k11", "13": "k13", "69": "k6",
                  "maj7": "kMaj7", "maj9": "kMaj9", "maj11": "kMaj11", "maj13": "kMaj13"}
    _ADJUST = {"b": "kFlat", "#": "kSharp", "": "kUnaltered"}

    def _chord_alterations(self, cs: ir.ChordSymbol) -> list[Node]:
        """Round 11: alteration = type (kAltered / kAdd / kSuspended / kOmit) + degree + adjustment.
        m7b5 = minor 7 + altered flat 5; sus4 = quality kNoThird + suspended 4; 6/9 = 6 + add 9;
        alt = altered b5, #5, b9, #9 (as Dorico stores C7alt)."""
        out = []

        def alt(kind: str, degree: int, adjust: str = "") -> None:
            out.append(E("alteration", L("type", kind),
                         E("degreeAndAdjustment", L("degree", degree), L("adjustment", self._ADJUST[adjust]))))
        if cs.quality == "half-diminished":
            alt("kAltered", 5, "b")
        for a in cs.alterations:
            m = re.fullmatch(r"([b#]?)(\d+)", a)
            if m:
                alt("kAltered", int(m.group(2)), m.group(1))
            elif a.startswith("add"):
                alt("kAdd", int(a[3:] or 9))
            elif a.startswith("sus"):
                alt("kSuspended", int(a[3:] or 4))
            elif a.startswith(("omit", "no")):
                alt("kOmit", int(re.sub(r"\D", "", a) or 3))
            elif a == "alt":
                for d, adj in ((5, "b"), (5, "#"), (9, "b"), (9, "#")):
                    alt("kAltered", d, adj)
        if cs.interval == "69":
            alt("kAdd", 9)
        return out

    def _chord_symbol_events(self, flow: ir.Flow, glob: _Stream) -> None:
        """Chord symbols (global; Rounds 7 + 11): quality, interval, alterations, root, slash bass
        (alteredBass); N.C. = chordSymbolData without a primary chord."""
        for cs in flow.chord_symbols:
            eid = self.ids.next("event")
            if cs.no_chord:
                data = E("chordSymbolData", A("playedPrimaryPitches", []), A("playedSecondaryPitches", []))
            else:
                quality = "kNoThird" if any(a.startswith("sus") for a in cs.alterations) and cs.quality == "major" \
                    else self._QUALITIES.get(cs.quality, "kMajor")
                data = E("chordSymbolData",
                         E("primaryChord",
                           E("definition", L("quality", quality),
                             L("interval", self._INTERVALS.get(cs.interval, "kNone")),
                             A("alterations", self._chord_alterations(cs))),
                           E("root", L("noteName", cs.root),
                             L("accidentalType", self._ACCIDENTALS.get(cs.root_alter, "kNatural"))),
                           E("alteredBass", L("noteName", cs.bass),
                             L("accidentalType", self._ACCIDENTALS.get(cs.bass_alter, "kNatural"))) if cs.bass else None),
                         A("playedPrimaryPitches", []), A("playedSecondaryPitches", []))
            glob.events.append(E(
                "ChordSymbolEventDefinition", *event_head("x", eid, cs.pos, 0), data,
                E("chordDiagramData", E("chordDiagramDefinitionPerTuningMap",
                                        A("chordDiagramPerTuningDefinitions", [])))))
            if cs.interval not in self._INTERVALS:
                self.report.append(f"chord symbol {cs.root}{cs.text}: interval {cs.interval!r} not known, written without it")

    def _repeat_events(self, flow: ir.Flow, glob: _Stream) -> None:
        """Endings and repeat markers (Round 7 encodings)."""
        groups: list[list[ir.Ending]] = []
        for e in sorted(flow.endings, key=lambda e: e.pos):
            if groups and groups[-1][-1].end == e.pos:
                groups[-1].append(e)  # 1st, 2nd ... endings: one line with a segment each
            else:
                groups.append([e])
        for g in groups:
            props = [prop("kRepeatEndingLineNumSegments", f"int: {len(g)}")]
            props += [prop("kRepeatEndingLineSegmentDuration", f'string: "{fstr(e.end - e.pos)}"',
                           context=True, offset=f"2:{k}:0:0") for k, e in enumerate(g)]
            if [n for e in g for n in e.numbers] not in ([], list(range(1, 1 + sum(len(e.numbers) for e in g)))):
                self.report.append("ending numbers " + ", ".join(e.text or str(e.numbers) for e in g) +
                                   " written as Dorico's default numbering (1., 2. ...)")
            eid = self.ids.next("event")
            glob.events.append(E("RepeatEndingLineEventDefinition",
                                 *event_head("x", eid, g[0].pos, g[-1].end - g[0].pos, props)))
        sections = {"segno": "kSegno", "coda": "kCoda", "fine": "kFine"}
        jumps = {"dc": "kDaCapo", "ds": "kDalSegno", "to_coda": "kToCoda"}
        until = {"end": "kEndOfFlow", "fine": "kAlFine", "coda": "kAlCoda"}
        for m in sorted(flow.repeat_markers, key=lambda m: m.pos):
            eid = self.ids.next("event")
            if m.section:
                body = L("sectionType", sections[m.section])
            else:
                body = E("jumpTypeAndQualification", L("jumpType", jumps[m.jump]),
                         L("jumpQualification", until.get(m.until or "end", "kEndOfFlow")))
            glob.events.append(E("RepeatMarkerEventDefinition", *event_head("x", eid, m.pos, 0), body))

    def _bar_division(self, ts: ir.TimeSignature, eid: int, tables: _ElementTables, irregular="",
                      barline: str = "") -> int:
        """BarDivision element for a time signature (global stream, or a stave stream for a
        staff-only signature: same element, Round 7)."""
        unit = {1: "kSemibreve", 2: "kMinim", 4: "kCrotchet", 8: "kQuaver",
                16: "kSemiquaver", 32: "kDemisemiquaver"}.get(ts.den, "kCrotchet")
        groups = ts.groups or _default_groups(ts.num, ts.den)
        props = [prop("kTimeSignatureHide", 'string: "true"')] if ts.hidden else []
        # irregularBarLength: empty in Dorico 5 saves; guessed to hold a pick-up length (untested)
        elem = tables.add("BarDivision", eid, E(
            "barDivisionData",
            L("irregularBarLength", irregular),
            L("suppressInitialBarline", "false"),
            L("forceEndOfInterchangeableRange", "false"),
            L("timeSignatureCommon", "true" if ts.symbol in ("common", "cut") else "false"),
            L("timeSignatureDrawClosingParenthesis", "false"),
            L("initialIndexForAggregateTimeSignature", 0),
            E("timeSignature", A("timeSignaturesAndDivisions", [E(
                "timeSignatureAndDivision",
                L("behaviour", "kNewBar"),
                E("timeSignature",
                  L("numerator", ts.num), L("denominator", ts.den),
                  E("beatGroupingAndOptions", E("beatGrouping",
                                                L("beatUnit", unit),
                                                L("beatLengthsInUnits",
                                                  svl(*[f"{{int: {g}}}" for g in groups]))))))])),
            E("interchangeableTimeSignatures", A("timeSignatures", [])),
            E("barlineChangeIfAny", L("type", BARLINE_TYPES[barline])) if barline in BARLINE_TYPES else None))
        if props:
            tables.tables["BarDivision"][-1].find("propertyTable").children[0] = A("entries", props)
        return elem

    def _global_key_and_more(self, flow: ir.Flow, glob: _Stream, tables: _ElementTables) -> None:
        for ks in flow.key_signatures:
            eid = self.ids.next("event")
            elem = tables.add("TonalityDivision", eid, E(
                "tonalityDivisionData",
                L("temperamentDefinitionID", "temperament definition.12-edo"),
                L("accidentalSystemID", "accidental system.12et.western"),
                L("tonalitySystemID", "tonalitysystem.equaltemperament"),
                _key_signature(ks),
                E("spellingRule", L("mode", "kUseGlobalAlgorithm"))))
            glob.events.append(E("TonalityDivisionEventDefinition", *event_head("x", eid, ks.pos, 0),
                                 L("tonalityDivisionElementID", elem)))
        for t in flow.tempos:
            if t.equation:  # metric modulation (Round 12): "old = new" note values
                eid = self.ids.next("event")
                l, r = (_duration_code(u) for u in t.equation)
                glob.events.append(E("ImmediateTempoChangeEventDefinition", *event_head("x", eid, t.pos, 0),
                                     E("data", L("type", "kEquation"), L("presetID"), L("text", t.text),
                                       L("flags", 1), L("modifierFlags", 0),
                                       E("tempoEquation",
                                         L("left", svl(f"{{list: {{int: {l[0]}}}, {{int: {l[1]}}}}}")),
                                         L("right", svl(f"{{list: {{int: {r[0]}}}, {{int: {r[1]}}}}}"))))))
                continue
            if t.bpm is None and not t.text:
                continue
            eid = self.ids.next("event")
            bpm = t.bpm or 120.0
            # tempoValue = 60e6 / bpm in the stated beat unit (Round 7: dotted crotchet = 60 -> 1000000)
            tempo_value = round(60_000_000 / bpm)
            code = _duration_code(t.unit)

            # flags (user's projects): 1 = show text, 2 = show metronome mark
            flags = (1 if t.text else 0) | (2 if t.show_metronome and t.bpm else 0)
            glob.events.append(E("ImmediateTempoChangeEventDefinition", *event_head("x", eid, t.pos, 0),
                                 E("data", L("type", "kAbsolute"), L("presetID"),
                                   L("text", t.text), L("flags", flags),
                                   L("modifierFlags", 0),
                                   # metronome range (Round 7): upper value, same units
                                   L("tempoValueRange", round(60_000_000 / t.bpm_max)) if t.bpm_max else None,
                                   E("absoluteTempo", L("tempoValue", tempo_value),
                                     L("beatUnits", svl(f"{{list: {{int: {code[0]}}}, {{int: {code[1]}}}}}")))))
                                 )

        for g in flow.gradual_tempos:
            preset, word, abbr, pct = GRADUAL_TEMPOS[g.kind]
            eid = self.ids.next("event")
            glob.events.append(E("GradualTempoChangeEventDefinition", *event_head("x", eid, g.pos, g.end - g.pos),
                                 E("data", L("finalTempoPercent", f"{pct:.6f}"), L("presetID", preset),
                                   L("muted", "false"), L("text", word), L("abbreviatedText", abbr),
                                   L("modifierFlags", 4), L("automationDataPoint", "false"))))
        for pos in flow.rehearsal_marks:
            eid = self.ids.next("event")
            glob.events.append(E("RehearsalMarkEventDefinition", *event_head("x", eid, pos, 0), L("data", "")))
        for pos in flow.pauses:
            eid = self.ids.next("event")
            glob.events.append(E("PauseEventDefinition", *event_head("x", eid, pos, 0),
                                 E("pauseData", L("pauseType", "kFermata"), L("fermataDuration", "kNormal"))))
        for b in flow.breaths:
            glob.events.append(_pause_event(self.ids.next("event"), b))

    # ----------------------------------------------------------- stave stream
    def _stave_events(self, st: ir.Staff, stream: _Stream, tables: _ElementTables, ent: Node,
                      nth: int, flow: ir.Flow) -> None:
        default_clef = None
        cl = ent.find("clefs/clefIDsForEachStave")
        if cl and cl.children and nth < len(cl.children):
            default_clef = cl.children[nth].text("idForTransposingLayouts")
        for c in st.clefs:
            if c.pos == 0 and c.clef == default_clef:
                continue
            eid = self.ids.next("event")
            stream.events.append(E("ClefEventDefinition", *event_head("x", eid, c.pos, 0),
                                   L("forceAfterGraceNotes", "false"),
                                   E("entityIDs", L("idForTransposingLayouts", c.clef))))
        for ts in st.time_signatures:  # staff-only time signatures (Round 7)
            eid = self.ids.next("event")
            elem = self._bar_division(ts, eid, tables)
            stream.events.append(E("BarDivisionEventDefinition", *event_head("x", eid, ts.pos, 0),
                                   L("barDivisionElementID", elem)))
        self._dynamic_groups(st, stream, tables, flow)
        for b in st.pauses:  # breath marks / caesuras on this staff only (ref-extras2)
            stream.events.append(_pause_event(self.ids.next("event"), b))
        for o in st.ottavas:
            eid = self.ids.next("event")
            stream.events.append(E("OttavaLineEventDefinition", *event_head("x", eid, o.pos, o.end - o.pos),
                                   L("entityID", OTTAVA_ENTITIES[o.kind]), L("logicalStaveIDOverride", -1)))
        for hp in st.harp_pedals:
            eid = self.ids.next("event")
            pos_name = {-1: "kTop", 0: "kMiddle", 1: "kBottom"}  # flat / natural / sharp
            stream.events.append(E("HarpPedalEventDefinition", *event_head("x", eid, hp.pos, 0),
                                   E("pedalSettings", *[L(f"{l.lower()}Pedal", pos_name[hp.settings.get(l, 0)])
                                                        for l in "CDEFGAB"])))
        for pd in st.pedals:
            eid = self.ids.next("event")
            stream.events.append(E("PedalLineEventDefinition", *event_head("x", eid, pd.pos, pd.end - pd.pos),
                                   L("pedalLineType", "kSustainPedal")))
        for ln in st.lines:
            stream.events.append(self._line_event(ln))

    def _line_event(self, ln: ir.Line) -> Node:
        """A horizontal line between rhythmic positions (Round 12: HorizontalLineEventDefinition
        in the stave stream, kRhythmicPosition at both ends; the style comes from the library)."""
        style = _line_style(ln)
        props = []
        if ln.hook_start and not ln.hook_end and ln.body != "wavy":
            # no factory style hooks only the start: override the start cap (checked in Dorico)
            props.append(prop("kHorizontalLineLineStartCapID", 'string: "lineannotation.inwardHookAxisAligned"'))
        if ln.text:
            props += [prop("kHorizontalLineText", f'string: "{_esc(ln.text)}"'),
                      prop("kHorizontalLineTextPlacement", 'string: "kStart"')]
        elif ln.centre_text:  # no placement: Dorico centres line text by default
            props.append(prop("kHorizontalLineText", f'string: "{_esc(ln.centre_text)}"'))
        eid = self.ids.next("event")
        return E("HorizontalLineEventDefinition", *event_head("x", eid, ln.pos, ln.end - ln.pos, props),
                 L("fromNoteEventAndBlockInstanceIDs", svl("{int: -1}", "{int: -1}")),
                 L("toNoteEventAndBlockInstanceIDs", svl("{int: -1}", "{int: -1}")),
                 L("startAttachmentType", "kRhythmicPosition"), L("endAttachmentType", "kRhythmicPosition"),
                 L("lineStyleEntityID", style), L("systemLine", "false"))

    @staticmethod
    def _bar_length_at(flow: ir.Flow, pos: Fraction) -> Fraction:
        starts = flow.bar_starts + [flow.length]
        for a, b in zip(starts, starts[1:]):
            if a <= pos < b:
                return b - a
        return Fraction(4)

    @staticmethod
    def _bar_end_after(flow: ir.Flow, pos: Fraction) -> Fraction:
        """End of the bar containing pos (at least one full bar of phrase for linking)."""
        for b in flow.bar_starts:
            if b > pos:
                return b
        return flow.length

    def _dynamic_groups(self, st: ir.Staff, stream: _Stream, tables: _ElementTables,
                        flow: ir.Flow) -> None:
        """Dynamics and hairpins, grouped the way Dorico groups them: a chain where each item
        starts where the previous one ends, or up to `dynamic_group_gap` later, (dynamic -> hairpin from it -> dynamic at its end,
        or hairpin -> hairpin) becomes one dynamic group; anything else stands alone.
        Encoding (from a Dorico-saved file): one DynamicGroup event at the chain's start; its
        element lists every dynamic/hairpin with positions relative to that start.
        Linking (seen in the user's projects): identical groups on several staves share one
        element whose referencingEventIDs lists every staff's event ("a,b,c")."""
        items = []  # (pos, end, order, kind, payload)
        for d in st.dynamics:
            if _dynamic_sub(d.kind, 0) is None:
                self.score.warnings.append(f"dynamic '{d.kind}' at {d.pos} not supported yet")
                continue
            items.append((d.pos, d.pos, 0, "dyn", d))
        for h in st.hairpins:
            items.append((h.pos, h.end, 1, "hairpin", h))
        items.sort(key=lambda x: (x[0], x[2]))
        chains: list[list[tuple]] = []
        for it in items:
            cur = chains[-1] if chains else None
            gap = it[0] - cur[-1][1] if cur is not None else None
            close = gap is not None and (
                -self.opt.dynamic_group_overlap <= gap <= self.opt.dynamic_group_gap or
                # longer gaps (up to a bar) while the instrument keeps playing (user's Willow edits)
                (0 < gap <= self._bar_length_at(flow, cur[-1][1]) and _sounds_through(st, cur[-1][1], it[0])))
            if cur is not None and self.opt.group_dynamics and close and \
                    not (it[3] == "dyn" and cur[-1][3] == "dyn") and it[0] >= cur[-1][0]:
                if gap < 0:  # hairpin hanging a little past the next item: end it there
                    p0, _, o, k, x = cur[-1]
                    cur[-1] = (p0, it[0], o, k, x)
                cur.append(it)
            else:
                chains.append([it])
        for chain in chains:
            start = chain[0][0]
            subs = []
            for k, (pos, end, _, kind, x) in enumerate(chain):
                if kind == "dyn":
                    sub = _dynamic_sub(x.kind, k, x.subito)
                    sub.child("position").value = fstr(pos - start)
                else:
                    sub = E("GradualChangeDynamicDefinition",
                            L("scoreSubElementID", k), L("position", pos - start),
                            ptable([prop("kDynamicGradualChangeDynamicAppearance", 'string: "kHairpin"')]),
                            L("type", "kCrescOrDim"),
                            L("direction", "kGradualDynamicUp" if x.direction == "cresc" else "kGradualDynamicDown"),
                            L("duration", end - pos), L("hasNiente", "true" if x.niente else "false"),
                            L("showsPocoAPoco", "false"), L("hasFlaredEnd", "false"),
                            E("commonDef", L("subito", "false")))
                subs.append(sub)
            eid = self.ids.next("event")
            # identical group at the same position on another staff -> link (share the element)
            sig = (start, tuple(_node_signature(x) for x in subs))
            mode = {True: "rhythm", False: "none"}.get(self.opt.link_dynamics, self.opt.link_dynamics)
            if mode == "rhythm":
                # only staves that would condense together: same rhythm over the phrase
                end = max(e for _, e, *_ in chain)
                rhythm = _rhythm(st, start, max(end, self._bar_end_after(flow, start)))
                sig = (sig, rhythm) if rhythm else None
            gid = tables.link("DynamicGroup", sig, stream.sid, eid) if (mode != "none" and sig) else None
            if gid is None:
                gid = tables.add("DynamicGroup", eid, sub_elements=subs)
                if sig:
                    tables.remember("DynamicGroup", sig, stream.sid, gid)
            stream.events.append(E("DynamicGroupEventDefinition", *event_head("x", eid, start, 0),
                                   L("dynamicGroupID", gid)))

    # ----------------------------------------------------------- voice stream
    _SYLLABLES = {"whole": "kWholeWord", "start": "kStart", "middle": "kMiddle", "end": "kEnd"}

    def _lyric_events(self, chords: list[ir.Chord], stream: _Stream, tables: _ElementTables) -> None:
        """Lyrics (Rounds 7 + 11): a LyricEventDefinition at the note -> LyricElementDefinition
        (text, syllableType kWholeWord/kStart/kMiddle/kEnd, lineType kVerse/kChorus, lineNumber).
        A word extension is the event's duration: to the end of the last note sung on it."""
        notes = [c for c in chords if not c.grace and c.pitches]
        for i, c in enumerate(notes):
            for ly in c.lyrics:
                dur = F(0)
                if ly.extension:  # held until the next note with a lyric on this line (or a rest)
                    end = c.pos + c.dur
                    for nxt in notes[i + 1:]:
                        if nxt.pos > end or any((l2.kind, l2.line) == (ly.kind, ly.line) for l2 in nxt.lyrics):
                            break
                        end = nxt.pos + nxt.dur
                    dur = end - c.pos
                eid = self.ids.next("event")
                elem = tables.add("Lyric", eid,
                                  L("text", ly.text), L("syllableType", self._SYLLABLES.get(ly.syllable, "kWholeWord")),
                                  L("lineLocation", "kBelow"),
                                  L("lineType", "kChorus" if ly.kind == "chorus" else "kVerse"),
                                  L("lineNumber", ly.line),
                                  E("richText", A("paragraphs", [E(
                                      "paragraph", L("paragraphStyleID", "paragraph.lyrics"), L("content"),
                                      A("fragments", [E("fragment", L("content", ly.text),
                                                        E("textFragmentStyle", L("libraryStyle")))]))])))
                stream.events.append(E("LyricEventDefinition", *event_head("x", eid, c.pos, dur),
                                       L("lyricElementID", elem)))

    def _voice_events(self, voice: ir.Voice, stream: _Stream, tables: _ElementTables) -> None:
        chords = sorted(voice.chords, key=lambda c: (c.pos, not c.grace))
        # graces: index them so each knows its offset before the main note
        pending_graces: list[ir.Chord] = []
        open_ties: dict[int, dict] = {}   # midi -> note record still accepting tied continuation
        grace_ids: dict[Fraction, int] = {}  # main-note position -> first grace event before it
        notes: list[dict] = []

        def flush_graces(main_pos: Fraction) -> None:
            offset = F(0)
            for g in reversed(pending_graces):
                offset -= g.notated
                for p in g.pitches:
                    eid = self.ids.next("event")
                    grace_ids.setdefault(main_pos, eid)
                    stream.events.append(E("GraceNoteEventDefinition",
                                           *event_head("x", eid, main_pos, 0, [_spelling(p)],
                                                       secondary_pos=offset),
                                           L("logicalStaveIDOverride", -1), L("pitch", p.midi),
                                           L("notatedDuration", g.notated),
                                           L("slashed", "true" if g.grace_slash else "false")))
            pending_graces.clear()

        for c in chords:
            if c.grace:
                if pending_graces and pending_graces[-1].pos != c.pos:
                    flush_graces(pending_graces[-1].pos)  # graces before a rest: keep their place
                pending_graces.append(c)
                continue
            if pending_graces:
                # a grace's position is its main note's; graces followed by a rest stay put
                flush_graces(pending_graces[-1].pos)
            if c.is_rest:
                for m in list(open_ties):
                    open_ties.pop(m)
                if c.hidden or self.opt.force_durations == "all":
                    eid = self.ids.next("event")
                    props = [prop("kRestForcePositionAndDuration", "null: ")]
                    stream.events.append(E("RestEventDefinition",
                                           *event_head("x", eid, c.pos, c.dur, props),
                                           L("logicalStaveIDOverride", -1)))
                continue
            # ties opened by earlier chords must continue into this one, or they are dropped
            expiring = {m for m, r in open_ties.items() if r["end"] <= c.pos}
            for p in c.pitches:
                rec = open_ties.get(p.midi)
                if rec is not None and rec["end"] == c.pos:
                    rec["segments"].append(c.dur)
                    rec["end"] = c.pos + c.dur
                    expiring.discard(p.midi)
                    if not p.tie:
                        open_ties.pop(p.midi)
                    continue
                rec = {"pos": c.pos, "end": c.pos + c.dur, "segments": [c.dur], "pitch": p, "chord": c}
                notes.append(rec)
                expiring.discard(p.midi)
                if p.tie:
                    open_ties[p.midi] = rec
                else:
                    open_ties.pop(p.midi, None)
            for m in expiring:
                open_ties.pop(m, None)
        if pending_graces:  # trailing graces (e.g. a harp gliss up to a final grace): before the rest
            flush_graces(pending_graces[-1].pos)

        note_ids: dict[Fraction, int] = {}  # position -> first note event there (glissandi)
        for rec in notes:
            p: ir.Pitch = rec["pitch"]
            c: ir.Chord = rec["chord"]
            props = [_spelling(p)]
            for a in c.articulations:
                if a in ARTICULATIONS:
                    k, v = ARTICULATIONS[a]
                    props.append(prop(k, f'string: "{v}"'))
            segs = rec["segments"]
            if (self.opt.force_durations == "all" or
                    (self.opt.force_durations == "ties" and len(segs) > 1)):
                props.append(prop("kNoteSplitDurations",
                                  "list: " + ", ".join(f'{{string: "{fstr(s)}"}}' for s in segs)))
            if c.stem in ("up", "down"):
                props.append(prop("kNoteForcedVoiceDirection",
                                  'string: "kForceStemsUp"' if c.stem == "up" else 'string: "kForceStemsDown"'))
            if p.accidental in ("show", "paren"):
                # native files always carry both (the _v3 one is current)
                props.append(prop("kNoteAccidentalVisibility_v3", 'string: "kShow"'))
                props.append(prop("kNoteAccidentalVisibility", 'string: "kShow"'))
            if c.tremolo:
                props.append(prop("kNoteSingleStemTremolo", f'string: "list: {{int: {c.tremolo}}}, {{bool: false}}"'))
            if c.tremolo_pair or c.tremolo_pair_end:  # two-note tremolo (Round 12)
                if not any(x.text("propertyType") == "kNoteSplitDurations" for x in props):
                    props.append(prop("kNoteSplitDurations", f'list: {{string: "{fstr(c.dur)}"}}'))
                props.append(prop("kBeamStart", f"list: {{int: {c.tremolo_pair}}}, {{int: 0}}")
                             if c.tremolo_pair else prop("kBeamEnd", "null: "))
            if c.harmonic == "natural":  # Round 12
                props.append(prop("kNoteHarmonicType", 'string: "kNatural"'))
            elif c.harmonic == "artificial":
                props.append(prop("kNoteHarmonicType", 'string: "kArtificial"'))
                props.append(prop("kNoteHarmonic", f"int: {c.harmonic_partial or 4}"))
            eid = self.ids.next("event")
            q = rec["pos"]
            for seg in rec["segments"]:  # every position in a tie chain maps to its one note
                note_ids.setdefault(q, eid)
                q += seg
            override = -1
            if p.staff is not None and getattr(self, "_voice_key", None):
                override = self.stave_ids.get((self._voice_key[0], p.staff), -1)
            stream.events.append(E("NoteEventDefinition",
                                   *event_head("x", eid, rec["pos"], rec["end"] - rec["pos"], props),
                                   L("logicalStaveIDOverride", override), L("pitch", p.midi)))

        self._lyric_events(chords, stream, tables)

        for t in voice.tuplets:
            eid = self.ids.next("event")
            code = _duration_code(t.unit)
            props = []
            if t.hidden:  # as Dorico writes the tuplet under a staff-only 12/8 (Round 7)
                ctx = lambda *extra: E("context", L("layoutIDWithFrameChainID",
                                                    "steamVariantList:list: {int: 0}, {int: -1}, {bool: false}"),
                                       L("blockInstanceID", -1), L("propertyOffset"), *extra)
                props = [E("entry", L("propertyType", "kTupletTextContent"), L("value", 'string: "kNone"'), ctx()),
                         E("entry", L("propertyType", "kTupletBracketVisibility"), L("value", 'string: "kHidden"'),
                           ctx(L("assignedStaveType", "kNormal")))]
            stream.events.append(E("TupletEventDefinition", *event_head("x", eid, t.pos, t.dur, props),
                                   L("tupletDefinition",
                                     svl(f"{{int: {t.num}}}", f"{{int: {t.den}}}",
                                         f"{{list: {{int: {code[0]}}}, {{int: {code[1]}}}}}",
                                         "{bool: true}"))))
        for s in voice.slurs:
            eid = self.ids.next("event")
            elem = tables.add("Slur", eid)
            stream.events.append(E("SlurEventDefinition", *event_head("x", eid, s.pos, s.end - s.pos),
                                   L("slurElementID", elem)))
        for c in chords:
            if c.arpeggio and c.pitches:
                eid = self.ids.next("event")
                stream.events.append(E("ArpeggioEventDefinition", *event_head("x", eid, c.pos, 0),
                                       L("startVoiceID", stream.sid), L("endVoiceID", stream.sid),
                                       L("arpeggioType", ARPEGGIO_TYPES.get(c.arpeggio, "kUpArpeggio"))))
            if c.ornament and c.pitches:
                eid = self.ids.next("event")
                stream.events.append(E("OrnamentEventDefinition", *event_head("x", eid, c.pos, 0),
                                       L("entityID", f"ornament.{c.ornament}")))
        for t in voice.trills:
            # (user's Dorico edit of Willow) kTrillInterval = (interval as a fraction of an
            # octave in 12-EDO, diatonic steps); none = Dorico's diatonic default
            props = []
            if t.interval:
                props.append(prop("kTrillInterval", f'list: {{string: "{fstr(Fraction(t.interval, 12))}"}}, {{int: 1}}'))
            eid = self.ids.next("event")
            stream.events.append(E("TrillEventDefinition", *event_head("x", eid, t.pos, t.end - t.pos, props)))
        key = getattr(self, "_voice_key", None)
        self._note_index[key] = (note_ids, stream.biid)
        self._grace_index[key] = grace_ids
        for g in voice.glissandi:
            self._pending_gliss.append((stream, key, g))

    def _resolve_glissandi(self) -> None:
        """Glissandi reference note events by (event ID, block instance), possibly in another
        voice or staff (harp hand to hand), so they are written once all voices exist."""
        for stream, key, g in self._pending_gliss:
            inst, staff, voice = key
            end_key = (inst, staff if g.end_staff is None else g.end_staff,
                       voice if g.end_voice is None else g.end_voice)
            a = (self._grace_index.get(key, {}) if g.start_grace else
                 self._note_index.get(key, ({}, -1))[0]).get(g.pos)
            b_ids, b_biid = self._note_index.get(end_key, ({}, -1))
            b = (self._grace_index.get(end_key, {}) if g.end_grace else b_ids).get(g.end)
            if a is None or b is None:
                self.score.warnings.append(f"glissando at {g.pos}: notes not found")
                continue
            harp = "harp" in self.entities.get(inst, "")
            straight = g.line == "straight" or (harp and self.opt.harp_glissando_straight)
            props = [prop("kGlissandoLineType", 'string: "kFlatLine"')] if straight else []
            eid = self.ids.next("event")
            stream.events.append(E("GlissandoLineEventDefinition",
                                   *event_head("x", eid, g.pos, g.end - g.pos, props),
                                   L("fromNoteEventAndBlockInstanceIDs", svl(f"{{int: {a}}}", f"{{int: {stream.biid}}}")),
                                   L("toNoteEventAndBlockInstanceIDs", svl(f"{{int: {b}}}", f"{{int: {b_biid}}}"))))
        self._pending_gliss.clear()

    def _technique_events(self, st: ir.Staff, stream: _Stream, inst_id: str) -> None:
        """Playing techniques (from Finale technique text) as Dorico playing-technique events
        in the staff's first voice, as in the user's Dorico edit of Willow."""
        # gradual changes: each group's first technique lasts until the next one in its group,
        # and all share one project-wide event group ID (Round 12: "ord." -> "sul pont.")
        groups: dict[int, list[ir.Technique]] = {}
        for t in st.techniques:
            if t.group is not None:
                groups.setdefault(t.group, []).append(t)
        group_ids = {g: self.ids.next("eventGroup") for g, ts in groups.items() if len(ts) > 1}
        for t in st.techniques:
            if t.kind is None and t.text:  # plain staff text
                eid = self.ids.next("event")
                props = []
                if t.boxed:  # Round 12: border on, rectangle (Dorico writes both)
                    props = [E("entry", L("propertyType", "kTextBorder"), L("value", "null: "),
                               E("context", L("layoutIDWithFrameChainID", NO_LAYOUT), L("blockInstanceID", -1),
                                 L("propertyOffset"), L("assignedStaveType", "kNormal"))),
                             E("entry", L("propertyType", "kTextBorderStyle"), L("value", 'string: "kRectangle"'),
                               E("context", L("layoutIDWithFrameChainID", NO_LAYOUT), L("blockInstanceID", -1),
                                 L("propertyOffset")))]
                stream.events.append(E("TextEventDefinition", *event_head("x", eid, t.pos, 0, props),
                                       L("aboveOrBelow", "kAbove"), L("isSystemText", "false"),
                                       L("alignWithSystemStart", "false"),
                                       E("content", A("paragraphs", [E("paragraph",
                                           L("paragraphStyleID", "paragraph.defaulttext"), L("content", ""),
                                           A("fragments", [E("fragment", L("content", t.text),
                                                             E("textFragmentStyle", L("libraryStyle", ""),
                                                               L("localStyle", "")))]))]))))
                continue
            pta = self._technique_appearance(t.kind, inst_id)
            if pta is None:
                continue
            eid = self.ids.next("event")
            dur, props = 0, []
            if t.group in group_ids:
                ts = groups[t.group]
                i = next(i for i, x in enumerate(ts) if x is t)
                if i + 1 < len(ts):
                    dur = ts[i + 1].pos - t.pos
                props = [prop("kEventGroupId", f"int: {group_ids[t.group]}")]
            stream.events.append(E("PlayingTechniqueEventDefinition", *event_head("x", eid, t.pos, dur, props),
                                   L("appearanceEntityID", pta), L("appearanceType", "kGlyph"),
                                   L("data", "")))

    def _technique_appearance(self, kind: str | None, inst_id: str) -> str | None:
        family = self.entities.get(inst_id, "").split(".")[1:2]
        family = family[0] if family else ""
        if kind == "mute":
            return {"brass": "pta.straightMuteText", "strings": "pta.conSordinoText"}.get(family, "pta.muteText")
        if kind == "open":
            return "pta.openRemoveMuteText" if family == "brass" else "pta.openText"
        return TECHNIQUE_APPEARANCES.get(kind)

    # --------------------------------------------------------------- layouts
    def _system_staves(self) -> int:
        """Staves in one full-score system: one instrument per player shows at a time (doublings);
        with condensing, about as many as the source printed."""
        n = sum(max((i.num_staves for i in p.instruments), default=1) for p in self.score.players)
        lay = self.score.layout
        if lay and lay.condense and lay.staves_per_system:
            n = min(n, lay.staves_per_system)
        return n

    def _condensing_groups(self) -> str:
        """Players split from one Finale staff condense back together (and only those): Dorico's
        userDefinedCondensableGroups, 'player,instrument:player,instrument|...' (user's HP BRASS
        TEST project)."""
        groups: dict = {}
        for p in self.score.players:
            if p.condense_group and p.instruments:
                groups.setdefault(p.condense_group, []).append(
                    f"{self.player_ids[p.id]},{self.instrument_ids[p.instruments[0].id]}")
        return "|".join(":".join(m) for m in groups.values() if len(m) >= 2)

    def _condensing_exclusions(self) -> str:
        """Neighbouring players of the same instrument that were separate staves in Finale (Avatar
        Viola 1 / Viola 2): Dorico would condense them on its own once condensing is on, so they
        go in groupsToExcludeFromCondensing (same format as the user-defined groups)."""
        runs, cur, last = [], [], None
        for p in self.score.players:
            eid = self.entities.get(p.instruments[0].id) if p.instruments and len(p.instruments) == 1 else None
            key = None if p.condense_group or eid is None else eid
            if key is not None and key == last:
                cur.append(p)
            else:
                if len(cur) >= 2:
                    runs.append(cur)
                cur = [p] if key is not None else []
            last = key
        if len(cur) >= 2:
            runs.append(cur)
        return "|".join(",".join(str(self.player_ids[p.id]) for p in run) for run in runs)

    def _layouts(self) -> Node:
        layouts = []
        all_players = [self.player_ids[p.id] for p in self.score.players]
        flow_ids = ",".join(str(i) for i in range(self.ids.flow))
        seed_layouts = []
        if self.opt.options_from_seed and self.seed is not None:
            seed_layouts = self.seed.find("layouts/array").children or []

        def layout(ltype: str, name: str, number: int, players: list[int]) -> Node:
            lid = self.ids.next("layout")
            opts = None
            for sl in seed_layouts:
                if sl.text("layoutType") == ltype:
                    opts = deep_copy(sl.find("layoutOptions"))
                    break
            if opts is None:  # the user's new-project layout options
                opts = layout_mod.default_options(ltype)
            if opts is not None:
                n = opts.find("customPlayerOrder")
                if n is not None:
                    n.value = ",".join(str(p) for p in players)
                if ltype == "kFullScoreLayout":
                    layout_mod.apply_full_score(opts, self.score.layout, self._system_staves(), self.report)
                    groups = self._condensing_groups()
                    g = opts.find("condensingLayoutOptions/userDefinedCondensableGroups")
                    if groups and g is not None:
                        g.value = groups
                        x = opts.find("condensingLayoutOptions/groupsToExcludeFromCondensing")
                        excl = self._condensing_exclusions()
                        if excl and x is not None:
                            x.value = excl
                else:
                    layout_mod.apply_part(opts, self.score.layout)
            return E("layout",
                     L("layoutID", lid), L("layoutType", ltype), L("layoutName", name),
                     L("useCustomLayoutName", "false"), L("layoutNameIndex", -1),
                     L("layoutNumber", number), L("useCustomPlayerOrder", "false"),
                     L("flowIDs", flow_ids),
                     opts,
                     E("layoutPlayers", A("array", [E("LayoutPlayerDefinition", L("playerID", p))
                                                    for p in players])),
                     E("pageSequenceOverrides",
                       E("frameChainDefinitions", A("musicFrameChains", []), A("textFrameChains", []),
                         A("graphicFrameChains", []), A("chordsUsedFrameChains", []),
                         A("graphicSliceFrameChains", [])),
                       A("pageDefinitionOverrides", []), A("pageNumberChanges", []),
                       A("masterPageChanges", []), A("flowHeadingChanges", []),
                       A("graphicSliceFrameDefinitionsAndPages", [])),
                     E("clefAndTranspositionOverrides", A("overrides", [])),
                     E("doodles", A("doodles", []), A("groups", [])),
                     A("spacingAdjustments", []), A("lyricLineUserYOffsets", []),
                     A("layoutInstrumentVisibilityPresetDefinitions", []))

        layouts.append(layout("kFullScoreLayout", "Full score", 1, all_players))
        if self.opt.parts:
            for p in self.score.players:
                layouts.append(layout("kPartLayout", p.name, 1, [self.player_ids[p.id]]))
        return E("layouts", A("array", layouts))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _load_score(path: str) -> Node:
    return container.open_score(path).root


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _spelling(p: ir.Pitch) -> Node:
    return prop("kNoteSpelling", f'string: "{p.step}"', context=True)


def _duration_code(unit: Fraction) -> tuple[int, int]:
    """Dorico note-value code: 8 = crotchet, 7 = quaver, 9 = minim ...; plus dots."""
    for dots in range(0, 4):
        base = unit / (2 - F(1, 2 ** dots))
        n, d = base.numerator, base.denominator
        if n & (n - 1) == 0 and d & (d - 1) == 0:
            log2 = (n.bit_length() - 1) - (d.bit_length() - 1)
            return 8 + log2, dots
    return 8, 0


def _default_groups(num: int, den: int) -> list[int]:
    if den >= 8 and num % 3 == 0 and num > 3:
        return [3] * (num // 3)
    return [1] * num if den <= 4 else [1] * num


def _interval(diatonic: int, chromatic: int) -> tuple[int, str]:
    d = abs(diatonic)
    c = abs(chromatic)
    major = [0, 2, 4, 5, 7, 9, 11]
    expect = major[d % 7] + 12 * (d // 7)
    perfect = d % 7 in (0, 3, 4)
    if c == expect:
        q = "kIntervalMajorOrPerfect"
    elif c == expect - 1 and not perfect:
        q = "kIntervalMinor"
    elif c < expect:
        q = "kIntervalDiminished"
    else:
        q = "kIntervalAugmented"
    return d + 1, q


def _colour(i: int) -> str:
    palette = ["#39a8ec", "#23d897", "#e82dbc", "#f2a531", "#7765f2", "#20cccd", "#ec5a39", "#5c7eee"]
    return palette[i % len(palette)]


def _key_signature(ks: ir.KeySignature) -> Node:
    f = max(-7, min(7, ks.fifths))
    minor = ks.mode == "minor"
    if f >= 0:
        tonic = (MINOR_SHARP_TONICS if minor else MAJOR_SHARP_TONICS)[f]
        sharped = set(SHARP_ORDER[:f])
        tonic_acc = 1 if tonic in sharped else 0
        accs = [(s, 1) for s in SHARP_ORDER[:f]]
    else:
        flats = SHARP_ORDER[::-1][:-f]
        tonic = (MINOR_FLAT_TONICS if minor else MAJOR_FLAT_TONICS)[-f]
        tonic_acc = -1 if tonic in flats else 0
        accs = [(s, -1) for s in flats]

    def acc_id(a: int) -> str:
        return f"accidental.12et.western.{ACCIDENTAL_IDS[a]}"

    return E("keySignature",
             L("showCautionaryNaturals", "false"),
             E("root", L("tonalityType", "kKeySigMinor" if minor else "kKeySigMajor"),
               E("root", L("noteName", tonic), L("accidentalID", acc_id(tonic_acc)))),
             A("accidentals", [E("accidental",
                                 E("noteNameAndAccidental", L("noteName", s), L("accidentalID", acc_id(a))),
                                 A("clefPositions", [])) for s, a in accs]))


def _sounds_through(st: ir.Staff, a: Fraction, b: Fraction) -> bool:
    """True if some note sounds at every moment of [a, b) on this staff (no rest in between)."""
    cur = a
    for x, y in sorted((c.pos, c.pos + c.dur) for v in st.voices for c in v.chords
                       if c.pitches and not c.grace):
        if y <= cur:
            continue
        if x > cur:
            return False
        cur = y
        if cur >= b:
            return True
    return cur >= b


def _rhythm(st: ir.Staff, start: Fraction, end: Fraction) -> tuple:
    """Note onsets and lengths (all voices, no pitches) in [start, end): the phrase rhythm."""
    return tuple(sorted({(c.pos, c.dur) for v in st.voices for c in v.chords
                         if c.pitches and not c.grace and start <= c.pos < end}))


def _node_signature(n: Node) -> tuple:
    return (n.tag, n.value, tuple(_node_signature(c) for c in n.children or ()))


_PAUSE_TYPES = {"breath": ("kBreathMark", "breathMarkAppearance"),
                "caesura": ("kCaesura", "caesuraAppearance"),
                "fermata": ("kFermata", "fermataDuration"), "curlew": ("kCurlew", None)}


def _pause_event(eid: int, b: ir.Breath) -> Node:
    """Breath mark / caesura / styled fermata / curlew (Round 9, ref-extras2). The same element
    goes in the global stream (all staves) or a stave stream (that staff only)."""
    ptype, field_ = _PAUSE_TYPES[b.kind]
    return E("PauseEventDefinition", *event_head("x", eid, b.pos, 0),
             E("pauseData", L("pauseType", ptype), L(field_, b.appearance) if field_ else None))


def _dynamic_sub(kind: str, sub_id: int, subito: bool = False) -> Node | None:
    kind = kind.strip().lower().replace("-", "").replace(" ", "")
    common = E("commonDef", L("subito", "true" if subito else "false"))
    if kind in _DYN and _DYN[kind]:
        loud, mezzo, count = _DYN[kind]
        intensity = svl(f"{{int: {loud}}}", "{}", f"{{bool: {'true' if mezzo else 'false'}}}",
                        f"{{int: {count}}}" if count else "{}")
        return E("ImmediateChangeDynamicDefinition",
                 L("scoreSubElementID", sub_id), L("position", 0),
                 ptable([prop("kEventSecondaryPosition", 'string: "0"')]),
                 L("intensity", intensity),
                 L("intensityModifier", svl("{}", "{}")),
                 common)
    if kind in COMBINED_DYNAMICS:
        # (user's Dorico edit of Willow: fp = kDown, startIntensity 1 (f), endIntensity 1 (p))
        direction, start, end = COMBINED_DYNAMICS[kind]
        return E("CombinedDynamicDefinition",
                 L("scoreSubElementID", sub_id), L("position", 0),
                 ptable([prop("kEventSecondaryPosition", 'string: "0"')]),
                 L("direction", direction), L("startIntensity", start), L("endIntensity", end),
                 common)
    if kind in FORCE_DYNAMICS:
        ftype, level, *z = FORCE_DYNAMICS[kind]
        props = [prop("kDynamicRinforzandoAndSforzandoHaveZ", 'string: "false"'),
                 prop("kEventSecondaryPosition", 'string: "0"')] if z and not z[0] else []
        return E("ForceDynamicDefinition",
                 L("scoreSubElementID", sub_id), L("position", 0), ptable(props),
                 L("type", ftype), L("intensityLevel", level), common)
    return None


def write_project(score: ir.Score, path: str | Path, install: DoricoInstall | None = None,
                  options: Options | None = None) -> list[str]:
    w = DoricoWriter(score, install or DoricoInstall(), options)
    w.write(path)
    return w.report
