"""Score IR: the format-neutral model between a Finale reader and the Dorico writer.

The IR describes the music *as notated* in the source. Readers fill it faithfully;
the Dorico writer turns it into Dorico's own idioms (tie chains become one note
with forced split durations, rests become implicit, and so on).

Conventions
-----------
- Time is an exact Fraction in crotchets (quarter notes): 1 = crotchet, 1/2 = quaver.
  Positions are absolute from the start of the flow.
- Pitch is concert pitch: MIDI number plus the concert spelling (letter + alteration).
- Durations: `dur` is the sounding length (tuplet ratios applied); `notated` is the
  written value including dots, before tuplet scaling.

`to_json` / `from_json` give a stable, diff-friendly JSON form (fractions as "n/d").
"""
from __future__ import annotations

import dataclasses
import json
import typing
from dataclasses import dataclass, field
from fractions import Fraction

F = Fraction


@dataclass
class Pitch:
    midi: int                       # concert MIDI number (60 = middle C)
    step: str                       # concert letter, "C".."B"
    alter: int = 0                  # concert alteration in semitones (-2..2)
    tie: bool = False               # tied to the same pitch in the next chord of this voice
    accidental: str | None = None   # None = automatic; "show", "hide", "paren"
    staff: int | None = None        # cross-staff: drawn on this staff of the instrument (index)


@dataclass
class Lyric:
    text: str
    line: int = 0                   # 0-based line number within its kind
    kind: str = "verse"             # "verse" / "chorus"
    syllable: str = "whole"         # "whole" / "start" / "middle" / "end" (hyphens between)
    extension: bool = False         # word extension (melisma line) after this syllable


@dataclass
class Chord:
    """A note/chord or a rest (no pitches) in one voice."""
    pos: Fraction
    dur: Fraction
    notated: Fraction
    pitches: list[Pitch] = field(default_factory=list)
    grace: bool = False
    grace_slash: bool = False
    articulations: list[str] = field(default_factory=list)  # "staccato", "accent", ...
    stem: str | None = None         # "up" / "down" when forced
    hidden: bool = False
    tremolo: int = 0                # single-stem tremolo strokes
    # two-note tremolo: strokes on the first chord of the pair, pair_end on the second
    # (Round 12: Dorico kBeamStart/kBeamEnd on the two notes)
    tremolo_pair: int = 0
    tremolo_pair_end: bool = False
    fermata: bool = False
    arpeggio: str | None = None     # "normal" / "up" / "down" / "bracket"
    ornament: str | None = None     # Dorico ornament name: "turn", "mordent", "shortTrill" ...
    lyrics: list[Lyric] = field(default_factory=list)
    fermata_style: str | None = None  # Dorico fermataDuration ("kShort", "kLongHenze" ...) or "curlew"; None = normal
    # string harmonic: "natural" (circle) or "artificial" (stopped note + diamond at the touched
    # note); partial = Dorico's harmonic partial for artificial ones (Round 12: touched 4th = 4,
    # touched 5th = 3, touched major 3rd = 5, octave = 2)
    harmonic: str | None = None
    harmonic_partial: int | None = None

    @property
    def is_rest(self) -> bool:
        return not self.pitches


@dataclass
class Tuplet:
    pos: Fraction
    dur: Fraction                   # sounding span
    num: int                        # e.g. 3 (in the time of)
    den: int                        # e.g. 2
    unit: Fraction                  # notated unit of num/den, e.g. 1/2 for quaver triplets
    hidden: bool = False            # no number/bracket (staff-only time signatures: 12/8 over 4/4)


@dataclass
class Slur:
    pos: Fraction
    end: Fraction                   # position of the last note's start


@dataclass
class Trill:
    pos: Fraction
    end: Fraction
    interval: int | None = None     # semitones to the upper note; None = Dorico's default (diatonic)


@dataclass
class Glissando:
    pos: Fraction                   # start note's position (same voice)
    end: Fraction                   # end note's position
    line: str = "wavy"              # "wavy" / "straight"
    end_staff: int | None = None    # end note on another staff of the instrument (index); None = same
    end_voice: int | None = None    # end note in another voice (index on that staff); None = same
    start_grace: bool = False       # starts / ends on the grace note before the note at that position
    end_grace: bool = False


@dataclass
class Voice:
    index: int                      # 0-based within the staff
    chords: list[Chord] = field(default_factory=list)
    tuplets: list[Tuplet] = field(default_factory=list)
    slurs: list[Slur] = field(default_factory=list)
    trills: list[Trill] = field(default_factory=list)
    glissandi: list[Glissando] = field(default_factory=list)
    layer: int | None = None        # source layer (Finale 1-4), when known


@dataclass
class Clef:
    pos: Fraction
    clef: str                       # Dorico clef entity, e.g. "clef.treble", "clef.bass"


@dataclass
class Dynamic:
    pos: Fraction
    kind: str                       # "pp", "mf", "sfz", "mfmp" ...
    subito: bool = False


@dataclass
class Hairpin:
    pos: Fraction
    end: Fraction
    direction: str                  # "cresc" / "dim"
    niente: bool = False            # from niente (cresc) / to niente (dim)


@dataclass
class Ottava:
    pos: Fraction
    end: Fraction
    kind: str = "up8"               # "up8" / "down8" / "up15" / "down15"


@dataclass
class Pedal:
    pos: Fraction
    end: Fraction


@dataclass
class HarpPedals:
    pos: Fraction
    settings: dict[str, int] = field(default_factory=dict)  # letter "C".."B" -> -1 flat / 0 natural / 1 sharp


@dataclass
class Technique:
    """Playing-technique / instruction text at a position on a staff.
    kind: "mute", "open", "pizz", "arco", "con-sord", "senza-sord", "ord", "sul-pont", "sul-tasto" (written as Dorico playing
    techniques); "a2", "solo1", "solo2" ... (player assignment on a shared staff, consumed when
    exploding staves into players); None = plain text, not converted yet."""
    pos: Fraction
    text: str
    kind: str | None = None
    boxed: bool = False             # plain text drawn in a box (Dorico text border)
    # gradual change to the next technique of the same group ("ord." -> "sul pont." with a
    # transition line; Round 12: a Dorico playing-technique group)
    group: int | None = None


@dataclass
class Line:
    """A horizontal line on a staff (Finale custom lines and line shapes): "Cue:" lines, words
    with a dashed continuation, brackets. Attached to rhythmic positions, not notes."""
    pos: Fraction
    end: Fraction
    body: str = "solid"             # "solid" / "dashed" / "wavy"
    hook_start: bool = False        # hook at either end (Dorico only draws inward hooks)
    hook_end: bool = False
    arrow_end: bool = False
    text: str = ""                  # words at the start of the line
    centre_text: str = ""           # words in the middle of the line


@dataclass
class Staff:
    instrument: str                 # Instrument.id
    index: int                      # 0-based stave within the instrument
    clefs: list[Clef] = field(default_factory=list)
    voices: list[Voice] = field(default_factory=list)
    dynamics: list[Dynamic] = field(default_factory=list)
    hairpins: list[Hairpin] = field(default_factory=list)
    techniques: list[Technique] = field(default_factory=list)
    ottavas: list[Ottava] = field(default_factory=list)
    pedals: list[Pedal] = field(default_factory=list)
    harp_pedals: list[HarpPedals] = field(default_factory=list)
    # staff-only time signatures (Finale "independent time signature"); a change back to the
    # score's signature is listed too. Bars keep the score's length: notes are scaled by
    # hidden tuplets (Dorico's own encoding, Round 7)
    time_signatures: list["TimeSignature"] = field(default_factory=list)
    # breath marks / caesuras on this staff only (Dorico: PauseEvent in the stave stream, Round 9);
    # marks on every playing staff go to Flow.breaths instead
    pauses: list["Breath"] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)


@dataclass
class TimeSignature:
    pos: Fraction
    num: int
    den: int
    groups: list[int] = field(default_factory=list)  # beat grouping in `den` units; empty = default
    symbol: str | None = None       # "common", "cut"
    hidden: bool = False


@dataclass
class KeySignature:
    pos: Fraction
    fifths: int                     # concert: -7..7
    mode: str = "major"             # "major" / "minor"


@dataclass
class Tempo:
    pos: Fraction
    bpm: float | None = None
    unit: Fraction = F(1)           # beat unit in crotchets
    text: str = ""
    bpm_max: float | None = None    # metronome range ("92-96")
    show_metronome: bool = True     # False: text only (bpm still used for playback)
    # metric modulation "old = new" as (old unit, new unit) in crotchets, e.g. (2, 1) for
    # minim = crotchet (Round 12: Dorico tempo equation)
    equation: tuple[Fraction, Fraction] | None = None


@dataclass
class GradualTempo:
    pos: Fraction
    end: Fraction
    kind: str                       # "rit" / "rall" / "accel"
    text: str = ""


@dataclass
class Instrument:
    id: str
    name: str                       # source's full name
    short_name: str = ""
    finale_uuid: str | None = None
    sound_id: str | None = None     # MusicXML sound ID (any spelling)
    dorico_id: str | None = None    # Dorico instrument entity, once resolved
    num_staves: int = 1
    transposition: tuple[int, int] | None = (0, 0)  # (diatonic, chromatic) written = concert + this; None = unknown
    no_key_signature: bool = False  # transposed part shows no key signature (accidentals only)
    key: str | None = None          # instrument pitch stated in the source ("c", "bflat", "a" ...; f2d/keys.py)


@dataclass
class Player:
    id: str
    name: str
    instruments: list[Instrument] = field(default_factory=list)
    section: bool = False
    condense_group: str | None = None  # players split from one source staff: Dorico condenses them back together


@dataclass
class Flow:
    id: str
    title: str
    length: Fraction                # total length in crotchets
    pickup: Fraction = F(0)         # length of an anacrusis, 0 if none
    time_signatures: list[TimeSignature] = field(default_factory=list)
    key_signatures: list[KeySignature] = field(default_factory=list)
    tempos: list[Tempo] = field(default_factory=list)
    staves: list[Staff] = field(default_factory=list)
    bar_starts: list[Fraction] = field(default_factory=list)  # position of every barline (bar 1 first)
    gradual_tempos: list[GradualTempo] = field(default_factory=list)
    rehearsal_marks: list[Fraction] = field(default_factory=list)
    pauses: list[Fraction] = field(default_factory=list)      # fermatas (Dorico: global)
    breaths: list["Breath"] = field(default_factory=list)     # breath marks, caesuras, styled fermatas (global)
    barlines: list["Barline"] = field(default_factory=list)   # barline changes and repeat barlines
    endings: list["Ending"] = field(default_factory=list)     # 1st/2nd-time bars (one per ending)
    repeat_markers: list["RepeatMarker"] = field(default_factory=list)  # segno, coda, D.C., D.S., To Coda, Fine
    chord_symbols: list["ChordSymbol"] = field(default_factory=list)  # global in Dorico


@dataclass
class Barline:
    pos: Fraction                   # the barline's position (start of the bar after it)
    kind: str                       # "double" / "final" / "dashed" / "thick" / "tick" /
                                    # "start_repeat" / "end_repeat" / "end_start_repeat"


@dataclass
class Ending:
    pos: Fraction
    end: Fraction
    numbers: list[int] = field(default_factory=list)  # passes, e.g. [1] or [1, 2]
    text: str = ""                  # the source's text ("1.", "1.-3.")
    open: bool = False              # no closing stroke at the right


@dataclass
class RepeatMarker:
    pos: Fraction                   # sections: start of the bar; jumps: the bar's last beat (Dorico, Round 7)
    section: str | None = None      # "segno" / "coda" / "fine"
    jump: str | None = None         # "dc" / "ds" / "to_coda"
    until: str | None = None        # "end" / "fine" / "coda" (D.S. al Coda = jump "ds", until "coda")
    text: str = ""                  # the source's text


@dataclass
class ChordSymbol:
    pos: Fraction
    root: str                       # letter "C".."B"
    root_alter: int = 0
    quality: str = "major"          # "major" / "minor" / "diminished" / "augmented" / "half-diminished" / "sus"
    interval: str | None = None     # None / "6" / "7" / "maj7" / "9" / "maj9" / "11" / "13" ...
    alterations: list[str] = field(default_factory=list)  # "b9", "#11", "add9", "sus4", "b5" ...
    bass: str | None = None         # slash chord bass letter
    bass_alter: int = 0
    text: str = ""                  # the source's suffix as written ("min7(b5)")
    instrument: str | None = None   # Instrument.id whose staff carried it in the source
    no_chord: bool = False          # "N.C."


@dataclass
class Breath:
    pos: Fraction                   # after the note it follows (Dorico: global PauseEvent)
    kind: str                       # "breath" / "caesura" / "fermata" / "curlew"
    appearance: str = "kComma"      # Dorico breathMarkAppearance / caesuraAppearance / fermataDuration


@dataclass
class Layout:
    """Page setup taken from the source (points: 1/72 inch). The Dorico writer starts from the
    user's new-project layout options and applies these, shrinking the staff size when a
    system would not fit the page."""
    page_width: float = 612.0
    page_height: float = 792.0
    space: float | None = None      # staff space (1/4 of a 5-line staff) in the score; None = default
    part_page_width: float | None = None
    part_page_height: float | None = None
    part_space: float | None = None
    hide_empty: str = "never"       # "never" / "after_first" / "all": source systems omit empty staves
    staves_per_system: int = 0      # most staves the source prints in one system
    condense: bool = False          # shared staves were split into players (Dorico condensing restores them)
    concert_pitch: bool | None = None  # full score in C (True) / transposed (False); None = user's default


@dataclass
class Info:
    title: str = ""
    subtitle: str = ""
    composer: str = ""
    arranger: str = ""
    lyricist: str = ""
    copyright: str = ""


@dataclass
class Score:
    info: Info = field(default_factory=Info)
    players: list[Player] = field(default_factory=list)
    flows: list[Flow] = field(default_factory=list)
    source: str = ""
    warnings: list[str] = field(default_factory=list)
    layout: Layout | None = None

    def instrument(self, iid: str) -> Instrument:
        for p in self.players:
            for i in p.instruments:
                if i.id == iid:
                    return i
        raise KeyError(iid)

    def player_of(self, iid: str) -> Player:
        for p in self.players:
            if any(i.id == iid for i in p.instruments):
                return p
        raise KeyError(iid)


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def _enc(x):
    if isinstance(x, Fraction):
        return str(x)
    if dataclasses.is_dataclass(x):
        return {f.name: _enc(getattr(x, f.name)) for f in dataclasses.fields(x)}
    if isinstance(x, (list, tuple)):
        return [_enc(v) for v in x]
    return x


def to_json(score: Score) -> str:
    return json.dumps(_enc(score), indent=1, ensure_ascii=False)


def _dec(tp, v):
    origin = typing.get_origin(tp)
    if v is None:
        return None
    if tp is Fraction:
        return Fraction(v)
    if dataclasses.is_dataclass(tp):
        hints = typing.get_type_hints(tp)
        return tp(**{k: _dec(hints[k], val) for k, val in v.items() if k in hints})
    if origin is list:
        (arg,) = typing.get_args(tp)
        return [_dec(arg, x) for x in v]
    if origin is tuple:
        return tuple(_dec(a, x) for a, x in zip(typing.get_args(tp), v))
    if origin in (typing.Union, getattr(__import__("types"), "UnionType", None)):
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        return _dec(args[0], v) if len(args) == 1 else v
    return v


def from_json(text: str) -> Score:
    return _dec(Score, json.loads(text))
