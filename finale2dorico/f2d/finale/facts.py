"""Full reader: facts from the C++ extractor (musxdom / finale-mus-reader) -> Score IR.

The extractor (extract/src/main.cpp) does the Finale-specific work with musxdom: concert
pitches, entry positions and tuplet spans, ties (including Finale's workarounds), the
instrument list and names, and legacy .mus decoding. This module turns those facts into the
IR with the same interpretation tables as the bootstrap reader (glyphs, clefs, time
signatures), so the two readers can be compared file by file.

    from f2d.finale.facts import read_finale
    score = read_finale("Old.mus")      # or a .musx
"""
from __future__ import annotations

import itertools
import json
import re
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from .. import ir, keys
from .enigma import (ARTIC_GLYPHS, CLEF_GLYPH_TYPE, CLEF_MAP, DEFAULT_CLEFS, DYNAMIC_GLYPHS, EDU,
                     FLAT_ORDER, SHARP_ORDER, STEPS, _chromatic_to_semitones,
                     _diatonic_to_semitones, _time_sig)
from .extract import run_extractor

F = Fraction
_DATA = Path(__file__).resolve().parents[1] / "data"
UNKNOWN_UUID = "a925648a-abc9-4dc7-a619-a6ce355ad33c"  # Finale's "Unknown" instrument
# Maestro / SMuFL codepoints (openmusx smufl-mapping)
TREMOLO_GLYPHS = {33: 1, 64: 2, 190: 3, 0xE220: 1, 0xE221: 2, 0xE222: 3, 0xE223: 4, 0xE224: 5}
TRILL_LINE_GLYPHS = {126, 0xEAA4}                      # wiggleTrill
TRILL_TEXT_GLYPHS = {217, 0xE566}                      # ornamentTrill ("tr")
TRILL_ACCIDENTALS = {105: -1, 98: -1, 73: 1, 35: 1, 233: 0, 110: 0,
                     0xE260: -1, 0xE262: 1, 0xE261: 0}  # small/regular flat, sharp, natural


# --- markings by SMuFL glyph name (via smufl-mapping in f2d-extract; works for any music font)
GLYPH_ARTICULATIONS = {
    "articStaccato": "staccato", "articAccent": "accent", "articTenuto": "tenuto",
    "articMarcato": "marcato", "articStaccatissimo": "staccatissimo",
    "articStaccatissimoWedge": "staccatissimo", "articStaccatissimoStroke": "staccatissimo",
    "articTenutoStaccato": "staccato-tenuto", "articAccentStaccato": ("accent", "staccato"),
    "articTenutoAccent": ("accent", "tenuto"), "articMarcatoStaccato": ("marcato", "staccato"),
    "fermata": "fermata", "fermataShort": "fermata", "fermataLong": "fermata",
}
# Finale's built-in line shapes: (body, hook at start, hook at end)
LINE_SHAPES = {"solidLine": ("solid", False, False), "dashLine": ("dashed", False, False)}
for _b, _n in (("solid", "solidLine"), ("dashed", "dashLine")):
    for _d in ("Up", "Down"):
        LINE_SHAPES[_n + _d] = (_b, False, True)
        LINE_SHAPES[_n + _d + "2"] = (_b, True, True)
        LINE_SHAPES[_n + _d + "Left"] = (_b, True, False)
    for _ud in ("UpDown", "DownUp"):
        LINE_SHAPES[_n + _ud] = (_b, True, True)
# artificial harmonics: semitones from the stopped to the touched note -> Dorico partial
# (the touched note divides the string into that many parts)
ARTIFICIAL_PARTIALS = {12: 2, 7: 3, 5: 4, 4: 5, 3: 6}
# techniques Dorico can change gradually ("ord." -> "sul pont." with a transition line)
TRANSITION_TECHNIQUES = {"ord", "sul-pont", "sul-tasto"}
GLYPH_TECHNIQUES = {"stringsUpBow": "up-bow", "stringsDownBow": "down-bow"}
# breath marks / caesuras (Dorico appearances from Round 9 / ref-extras2)
GLYPH_PAUSES = {"breathMarkComma": ("breath", "kComma"), "breathMarkTick": ("breath", "kTick"),
                "breathMarkUpbow": ("breath", "kUpBow"), "breathMarkSalzedo": ("breath", "kSalzedo"),
                "caesura": ("caesura", "kNormal"), "caesuraThick": ("caesura", "kThick"),
                "caesuraShort": ("caesura", "kShort"), "caesuraCurved": ("caesura", "kCurved"),
                "caesuraSingleStroke": ("caesura", "kSingleStroke")}
# fermata glyph -> Dorico fermataDuration (ref-extras2); the curlew is its own pause type
GLYPH_FERMATAS = {"fermata": "kNormal", "fermataVeryShort": "kVeryShort", "fermataShort": "kShort",
                  "fermataLong": "kLong", "fermataVeryLong": "kVeryLong",
                  "fermataShortHenze": "kShortHenze", "fermataLongHenze": "kLongHenze", "curlew": "curlew"}
GLYPH_DYNAMICS = {
    "dynamicPPPPPP": "pppppp", "dynamicPPPPP": "ppppp", "dynamicPPPP": "pppp", "dynamicPPP": "ppp",
    "dynamicPP": "pp", "dynamicPiano": "p", "dynamicMP": "mp", "dynamicMF": "mf", "dynamicForte": "f",
    "dynamicFF": "ff", "dynamicFFF": "fff", "dynamicFFFF": "ffff", "dynamicFFFFF": "fffff",
    "dynamicFFFFFF": "ffffff", "dynamicSforzando": "sf", "dynamicSforzando1": "sf",
    "dynamicSforzato": "sfz", "dynamicSforzatoFF": "sffz", "dynamicForzando": "fz",
    "dynamicFortePiano": "fp", "dynamicSforzandoPiano": "sfp", "dynamicSforzandoPianissimo": "sfpp",
    "dynamicRinforzando": "rf", "dynamicRinforzando1": "rf", "dynamicRinforzando2": "rfz",
    "dynamicNiente": "niente", "dynamicNienteForHairpin": "niente",
}
_LEVELS = {"pppp", "ppp", "pp", "p", "mp", "mf", "f", "ff", "fff", "ffff"}
_COMBINED = {"fp", "ffp", "fpp", "pf", "mfmp", "mfp", "fmp", "mpmf", "mpf", "pmf"}
GLYPH_ARPEGGIOS = {"arpeggiato": "normal", "arpeggiatoUp": "up", "arpeggiatoDown": "down",
                   "arpeggioVerticalSegment": "normal"}
GLYPH_ORNAMENTS = {"ornamentTurn": "turn", "ornamentTurnInverted": "turnInverted",
                   "ornamentTurnSlash": "turnSlash", "ornamentTurnUp": "turnUp", "ornamentMordent": "mordent",
                   "ornamentShortTrill": "shortTrill", "ornamentTremblement": "tremblement",
                   "ornamentHaydn": "haydn", "ornamentSchleifer": "schleifer"}
# music-font glyphs that have a plain Unicode equivalent in text
GLYPH_TEXT = {"accidentalFlat": "\u266d", "accidentalSharp": "\u266f", "accidentalNatural": "\u266e",
              "accidentalFlatSmall": "\u266d", "accidentalSharpSmall": "\u266f",
              "accidentalNaturalSmall": "\u266e", "accidentalDoubleSharp": "\U0001D12A",
              "accidentalDoubleFlat": "\U0001D12B", "metNoteQuarterUp": "\u2669",
              "metNote8thUp": "\u266a", "metNoteHalfUp": "\U0001D15E", "metNoteWhole": "\U0001D15D",
              "metAugmentationDot": "."}
MET_NOTES = {"metNoteDoubleWhole": F(8), "metNoteWhole": F(4), "metNoteHalfUp": F(2), "metNoteHalfDown": F(2),
             "metNoteQuarterUp": F(1), "metNoteQuarterDown": F(1), "metNote8thUp": F(1, 2),
             "metNote8thDown": F(1, 2), "metNote16thUp": F(1, 4), "metNote16thDown": F(1, 4),
             # legacy fonts (Maestro "q", "h", "e") map to the plain note glyphs
             "noteWhole": F(4), "noteHalfUp": F(2), "noteHalfDown": F(2), "noteQuarterUp": F(1),
             "noteQuarterDown": F(1), "note8thUp": F(1, 2), "note8thDown": F(1, 2),
             "note16thUp": F(1, 4), "note16thDown": F(1, 4), "noteDoubleWhole": F(8)}
GRADUAL_WORDS = [(r"^(poco\s+)?(rit|ritard|ritardando)\b", "rit"), (r"^(poco\s+)?(rall|rallentando)\b", "rall"),
                 (r"^(poco\s+)?(accel|accelerando)\b", "accel")]


TEMPO_WORDS = re.compile(
    r"^(a tempo|tempo\b|tempo primo|tempo i\b|l'istesso|grave|largo|larghetto|lento|adagio|adagietto|andante|"
    r"andantino|moderato|allegretto|allegro|vivace|vivo|presto|prestissimo|maestoso|alla marcia|alla breve|"
    r"meno mosso|piu mosso|più mosso|poco meno|poco piu|poco più|slower|faster|slowly|briskly|moderately|"
    r"lively|in time|swing|rubato|freely|march|waltz|ballad)", re.I)


def _is_tempo_text(text: str) -> bool:
    return bool(TEMPO_WORDS.match(text.strip())) and len(text) <= 60


HARP_ORDER = "DCBEFGA"  # pedal diagram order (left foot D C B | right foot E F G A)
HARP_STATE = {"harpPedalRaised": -1, "harpPedalCentered": 0, "harpPedalLowered": 1}


def _harp_pedals(chunks: list[dict]):
    """('diagram', {letter: alter}) for a harp pedal diagram, ('changes', {...}) for stacked
    pedal-change letters (F♯ / C♭ / B♭), or None."""
    names = [g for c in chunks for g in (c.get("glyphs") or [])]
    states = [HARP_STATE[n] for n in names if n in HARP_STATE]
    if len(states) == 7:
        return "diagram", dict(zip(HARP_ORDER, states))
    if not any(c.get("music") for c in chunks):
        return None
    changes = {}
    for c in chunks:
        t, g = c.get("text", ""), c.get("glyphs") or []
        for k, ch in enumerate(t):
            name = g[k + 1] if k + 1 < len(g) else ""
            if ch.upper() in "ABCDEFG" and name in ("accidentalFlat", "accidentalSharp", "accidentalNatural"):
                changes[ch.upper()] = {"accidentalFlat": -1, "accidentalSharp": 1, "accidentalNatural": 0}[name]
    letters = re.sub(r"[\s\[\]]", "", "".join(c.get("text", "") for c in chunks))
    if changes and len(letters) == 2 * len(changes):  # nothing but letter+accidental pairs
        return "changes", changes
    return None


_COPYRIGHT = re.compile(r"(?i)copyright|©|\(c\)\s*\d|all rights reserved")


def _trill_step(words: str) -> int | None:
    """Semitones named in a trill's text: "1/2", "½", "H.T." -> 1; "WT", "W.T." -> 2."""
    t = re.sub(r"[\s.()]", "", words).upper()
    if t in ("1/2", "½", "HT", "HS"):
        return 1
    if t in ("WT", "WS"):
        return 2
    return None


def _gradual_kind(text: str) -> str | None:
    t = text.strip().lower()
    for pat, kind in GRADUAL_WORDS:
        if re.match(pat, t):
            return kind
    return None


def _chunks_text(chunks: list[dict]) -> tuple[str, bool]:
    """Plain text of an expression; music-font characters become Unicode where they have an
    equivalent (♭ ♯ ♮ ♩ ...). Returns (text, ok): ok is False if a music symbol couldn't be
    represented (harp pedal diagrams, brackets ...)."""
    out, ok = [], True
    for c in chunks:
        t = c.get("text", "")
        if not c.get("music"):
            out.append(t)
            continue
        names = c.get("glyphs") or []
        for k, ch in enumerate(t):
            name = names[k] if k < len(names) else ""
            if ch.isspace() or (ch.isascii() and (ch.isdigit() or ch in "=-–.,()[]/: ")) and name not in MET_NOTES:
                out.append(ch)
            elif name in GLYPH_TEXT:
                out.append(GLYPH_TEXT[name])
            else:
                ok = False
    return "".join(out), ok


_DIGIT_GLYPH = re.compile(r"^(?:tuplet|timeSig|fingering|metNoteNumber|figbass)(\d)$")


def _glyph_char(name: str, ch: str) -> str:
    """Music-font digits and '=' by glyph name (Maestro's metronome digits map to tuplet numerals)."""
    m = _DIGIT_GLYPH.match(name or "")
    if m:
        return m.group(1)
    if name in ("timeSigEquals", "metricModulationEquals"):
        return "="
    return ch


def _metric_modulation(chunks: list[dict]) -> tuple[Fraction, Fraction] | None:
    """(old unit, new unit) from a metric modulation like "(h = q)": two note values joined
    by "=" in a music font, with nothing else but brackets and spaces."""
    units, rest = [], ""
    for c in chunks:
        t, names = c.get("text", ""), c.get("glyphs") or []
        for k, ch in enumerate(t):
            name = names[k] if k < len(names) else ""
            if c.get("music") and name in MET_NOTES:
                units.append(MET_NOTES[name])
            elif units and c.get("music") and (name in ("metAugmentationDot", "augmentationDot") or ch == "."):
                units[-1] *= F(3, 2)
            else:
                rest += ch
    if len(units) != 2 or re.sub(r"[\s(){}\[\]]", "", rest) != "=" or units[0] == units[1]:
        return None
    return units[0], units[1]


def _metronome(chunks: list[dict]) -> tuple[Fraction, float, float | None, str] | None:
    """(beat unit, bpm, bpm_max or None, words) from a tempo mark like "Slower q = 84" or
    "q. = 60" or "q = 92-96" (note glyph in a music font)."""
    unit, words, rest = None, [], ""
    for c in chunks:
        t = c.get("text", "")
        names = c.get("glyphs") or []
        if not c.get("music"):
            if unit is None:
                words.append(t)
            else:
                rest += t
            continue
        for k, ch in enumerate(t):
            name = names[k] if k < len(names) else ""
            if name in MET_NOTES and unit is None:
                unit = MET_NOTES[name]
            elif unit is not None and (name == "metAugmentationDot" or (ch == "." and rest.strip() == "")):
                unit = unit * F(3, 2)
            elif unit is not None:
                rest += _glyph_char(name, ch)
            elif ch.isspace():
                words.append(ch)  # other music symbols before the note value are not words
    if unit is None:
        return None
    m = re.search(r"=\s*(\d+(?:\.\d+)?)\s*(?:[-–]\s*(\d+(?:\.\d+)?))?", rest)
    if not m:
        return None
    text = " ".join("".join(words).split()).rstrip(" ({[")  # "Con Brio (q = 144)": drop the bracket
    return unit, float(m.group(1)), float(m.group(2)) if m.group(2) else None, text


TEXT_OTTAVAS = {"ottavaAlta": "up8", "ottava": "up8", "ottavaBassa": "down8", "ottavaBassaVb": "down8",
                "ottavaBassaBa": "down8", "quindicesimaAlta": "up15", "quindicesima": "up15",
                "quindicesimaBassa": "down15", "quindicesimaBassaMb": "down15"}


def _text_ottava(x: dict, plain: str, chunks: list[dict]) -> str | None:
    """'up8' / 'down8' / ... for an 8va-style expression with transposing playback; 'loco' for
    the expression that ends it; None otherwise."""
    if x.get("playback") != "transpose":
        return None
    if re.fullmatch(r"\(?\s*loco\s*\)?\.?", plain, re.I):
        return "loco"
    names = [g for c in chunks for g in c.get("glyphs", []) if g]
    for n in names:
        if n in TEXT_OTTAVAS:
            return TEXT_OTTAVAS[n]
    if re.fullmatch(r"\(?\s*8(va|ve)?a?\.?\s*\)?", plain, re.I):
        return "up8" if (x.get("value") or 12) > 0 else "down8"
    return None


def _scale_note(key: dict, degree: int, alter: int) -> tuple[str, int]:
    """Letter and alteration of a scale degree (0 = tonic) in a key (fifths, major/minor)."""
    letters = "CDEFGAB"
    fifths = 0 if key.get("keyless") else int(key.get("fifths", 0))
    tonic = (fifths * 4) % 7 + (5 if key.get("linear", True) and key.get("mode") == 1 else 0)
    letter = letters[(tonic + int(degree)) % 7]
    sharps, flats = "FCGDAEB", "BEADGCF"
    base = 1 if fifths > 0 and letter in sharps[:fifths] else -1 if fifths < 0 and letter in flats[:-fifths] else 0
    return letter, base + int(alter)


_INTERVALS = ["maj13", "maj11", "maj9", "maj7", "13", "11", "9", "7", "69", "6", "5"]


def _parse_chord_suffix(elements: list[dict]) -> tuple[str, str | None, list[str], str]:
    """Finale chord suffix elements -> (quality, interval, alterations, text as written)."""
    parts = []
    for el in elements:
        pre = {1: "-", 2: "+", 3: "#", 4: "b"}.get(el.get("prefix") or 0, "")
        t = el.get("text", "")
        g = el.get("glyph") or ""
        if g.startswith("accidentalFlat") or t in ("\u266d", "\u00d1"):
            t = "b"
        elif g.startswith("accidentalSharp") or t == "\u266f":
            t = "#"
        elif g in ("csymDiminished",) or t in ("\u00b0", "o") and not parts:
            t = "dim"
        elif g in ("csymHalfDiminished",) or t == "\u00f8":
            t = "m7b5"
        elif g in ("csymMajorSeventh",) or t in ("\u0394", "\u2206"):
            t = "maj"
        parts.append(pre + t)
    text = "".join(parts)
    s = text.replace(" ", "").replace("(", "").replace(")", "").replace(",", "").replace("\u2013", "-")
    quality, interval, alts = "major", None, []
    low = s.lower()
    for word, q in (("m7b5", "half-diminished"), ("min", "minor"), ("mi", "minor"), ("dim", "diminished"),
                    ("aug", "augmented")):
        if low.startswith(word):
            quality, s, low = q, s[len(word):], low[len(word):]
            if q == "half-diminished":
                interval = "7"
            break
    else:
        if s.startswith(("m", "-")) and not low.startswith("maj"):
            quality, s, low = "minor", s[1:], low[1:]
        elif s.startswith("+") and not s[1:2].isdigit():
            quality, s, low = "augmented", s[1:], low[1:]
    if low.startswith(("maj", "ma")) or s.startswith("M"):
        cut = 3 if low.startswith("maj") else 2 if low.startswith("ma") else 1
        num = re.match(r"\d+", s[cut:])
        interval, s = "maj" + (num.group(0) if num else "7"), s[cut + (len(num.group(0)) if num else 0):]
    elif interval is None:
        m = re.match(r"(13|11|9|7|69|6/9|6|5)", s)
        if m:
            interval, s = m.group(1).replace("6/9", "69"), s[m.end():]
    for m in re.finditer(r"(sus[24]?|add\d+|omit\d+|no\d+|alt|[b#+-]\d+)", s.lower()):
        alts.append(m.group(1).replace("+", "#").replace("-", "b") if m.group(1)[0] in "+-" else m.group(1))
    return quality, interval, alts, text


def _repeat_marker(chunks: list[dict]) -> ir.RepeatMarker | None:
    """Segno / coda signs and D.C. / D.S. / To Coda / Fine text -> a repeat marker (or None)."""
    names = [g for c in chunks for g in c.get("glyphs", []) if g]
    text = " ".join("".join(c.get("text", "") for c in chunks if not c.get("music")).split())
    t = text.lower().replace(" ", "").rstrip(".")
    has_coda = any(n.startswith("coda") for n in names) or "coda" in t
    if names and not text:
        if any(n.startswith("segno") for n in names):
            return ir.RepeatMarker(pos=F(0), section="segno", text="segno")
        if any(n.startswith("coda") for n in names):
            return ir.RepeatMarker(pos=F(0), section="coda", text="coda")
        return None
    until = "fine" if "fine" in t and ("al" in t or t.startswith(("d.c", "d.s", "dc", "ds"))) else \
        "coda" if has_coda and "al" in t else "end"
    if t.startswith(("d.c", "dc", "dacapo")):
        return ir.RepeatMarker(pos=F(0), jump="dc", until=until, text=text)
    if t.startswith(("d.s", "ds", "dalsegno")):
        return ir.RepeatMarker(pos=F(0), jump="ds", until=until, text=text)
    if t.startswith(("tocoda", "to")) and has_coda:
        return ir.RepeatMarker(pos=F(0), jump="to_coda", until="end", text=text or "To Coda")
    if t == "fine":
        return ir.RepeatMarker(pos=F(0), section="fine", text=text)
    if t in ("coda", "segno"):
        return ir.RepeatMarker(pos=F(0), section=t, text=text)
    return None


OTTAVA_SHAPES = {"octaveUp": "up8", "octaveDown": "down8", "twoOctaveUp": "up15", "twoOctaveDown": "down15"}
TRILL_GLYPH_ACCIDENTAL = {"ornamentTrill": None, "ornamentTrillFlatAbove": -1,
                          "ornamentTrillSharpAbove": 1, "ornamentTrillNaturalAbove": 0}
ACCIDENTAL_GLYPHS = {"accidentalFlat": -1, "accidentalFlatSmall": -1, "accidentalSharp": 1,
                     "accidentalSharpSmall": 1, "accidentalNatural": 0, "accidentalNaturalSmall": 0}


def _base_glyph(name: str) -> str:
    return name[:-5] if name.endswith(("Above", "Below")) else name


# Finale's handwritten text fonts (Finale/Broadway Copyist Text, JazzText) draw a box around a
# word from pieces typed between its letters: "[B\r\i\g\ht]" is "Bright" in a box. '[' '{' and
# byte 0x85 are left sides, ']' '}' right sides, '\' '|' and bytes 0x86/0xB3 zero-width top-line
# pieces. The high bytes arrive as …/Ö/Ü/³/≥ depending on the saving machine's encoding.
_BOX_BYTES = {0x5B, 0x5C, 0x5D, 0x7B, 0x7C, 0x7D, 0x85, 0x86, 0xB3}


def _box_piece(ch: str) -> bool:
    for enc in ("latin-1", "cp1252", "mac_roman"):
        try:
            if ch.encode(enc)[0] in _BOX_BYTES:
                return True
        except UnicodeEncodeError:
            continue
    return False


def _unbox(text: str) -> str | None:
    """Words of a box-coded copyist-font text, or None if the text isn't box-coded."""
    t = text.strip(" \t\r\n")  # not str.strip(): it drops \x85, a box piece
    if not t or "\\" not in t or not _box_piece(t[0]) or t[0] in "\\|":
        return None
    return "".join(ch for ch in text if not _box_piece(ch))


def _raw_music_chunks(chunks: list[dict]) -> list[dict]:
    """Legacy .mus text arrives converted from the saving machine's encoding (Mac Roman /
    Windows-1252) to Unicode, but music fonts (Maestro, Petrucci) index glyphs by the raw byte:
    Maestro ff is byte 196, which Mac Roman turns into 'ƒ'. Map music-font text back to bytes
    (Finale 27's own conversion keeps the raw byte too). Box-coded copyist-font text becomes its
    words (marked "boxed")."""
    out = []
    for c in chunks:
        t = c.get("text", "")
        if c.get("music") and not c.get("smufl") and any(ord(ch) > 255 for ch in t):
            for enc in ("cp1252", "mac_roman"):
                try:
                    t = t.encode(enc).decode("latin-1")
                    break
                except UnicodeEncodeError:
                    continue
        elif not c.get("music"):
            words = _unbox(t)
            if words is not None:
                out.append(dict(c, text=words, boxed=True))
                continue
        out.append(dict(c, text=t))
    return out


def upper_neighbour_semitones(step: str, midi: int, dia: int, chrom: int, acc: int) -> int:
    """Concert note (letter + MIDI) and written transposition (diatonic, chromatic) -> semitones
    up to the next written letter with alteration `acc` (-1 flat, 0 natural, 1 sharp)."""
    semis = [0, 2, 4, 5, 7, 9, 11]
    w_step = ("CDEFGAB".index(step) + dia) % 7
    w_midi = midi + chrom
    nat = semis[w_step]
    alter = ((w_midi - nat) % 12 + 6) % 12 - 6
    up_step = (w_step + 1) % 7
    up_nat = semis[up_step] + (12 if up_step == 0 else 0)
    return (up_nat + acc) - (nat + alter)


def _technique_kind(text: str) -> str | None:
    """Instruction text -> technique kind (see ir.Technique)."""
    t = text.strip().lower().rstrip(".").replace("\u00ba", "")
    t = re.sub(r"\s+", " ", t)
    if t in ("a2", "a 2", "a3", "a 3", "a4", "a 4", "unis", "unison"):
        return "a" + (re.findall(r"\d", t) or ["2"])[0]
    m = re.fullmatch(r"(\d)(st|nd|rd|th)?( only| solo)?", t)
    if m:
        return f"solo{m.group(1)}"
    return {"mute": "mute", "mutes": "mute", "con sord": "con-sord", "con sordino": "con-sord",
            "open": "open", "senza sord": "senza-sord", "senza sordino": "senza-sord",
            "pizz": "pizz", "pizzicato": "pizz", "arco": "arco",
            "ord": "ord", "ordinario": "ord",
            "sul pont": "sul-pont", "sul ponticello": "sul-pont", "sul tasto": "sul-tasto"}.get(t)
_DYNAMIC_WORDS = {"pppp", "ppp", "pp", "p", "mp", "mf", "f", "ff", "fff", "ffff",
                  "sfz", "sf", "fz", "rfz", "fp", "sfp", "ffz", "rffz", "sffz", "mfz", "niente",
                  "sff", "rf", "rff",
                  "mf-mp", "mp-mf"}
_SUBITO = re.compile(r"^(?:(?:subito|sub\.?)\s+(?P<a>.+)|(?P<b>.+?)\s+(?:subito|sub\.?))$", re.I)


def read_finale(path: str | Path) -> ir.Score:
    """Read a .mus or .musx file through the C++ extractor."""
    return FactsReader(run_extractor(path)).read()


class FactsReader:
    def __init__(self, facts: dict):
        if facts.get("format") != "f2d-facts":
            raise ValueError("not an f2d-extract facts document")
        self.f = facts
        self.warnings: list[str] = list(facts.get("warnings", []))
        self.finale_instruments = json.loads(
            (_DATA / "finale_instruments.json").read_text())["instruments"]
        self.shift = F(0)  # legacy pick-up spacer removed from the start of the flow
        self.raw_note: dict[int, dict] = {}  # id(ir.Pitch) -> extractor note facts
        self.note_trills: list = []      # (staff id, chord, accidental) from "tr" articulations
        self.note_techniques: list = []  # (staff id, pos, kind) from bowing articulations
        self.pedal_marks: list = []      # (staff id, pos, is_down) from Ped./* articulations
        self.pause_marks: list = []
        self.text_ottavas: list = []      # (staff, pos, 'up8'/'down8'/.../'loco')      # (staff id, pos, kind, appearance): breath marks, caesuras
        self.gradual_pending: list = []  # (pos, kind, text, end or None)
        self.ottava_raw_start: dict = {}  # id(ir.Ottava) -> Finale's unsnapped start
        self.harp_pending: list = []  # (staff, pos, ("diagram"|"changes", {letter: alter}))

    # ------------------------------------------------------------------ main
    def read(self) -> ir.Score:
        score = ir.Score(source=self.f.get("source", ""))
        for k in ("title", "subtitle", "composer", "arranger", "lyricist", "copyright"):
            setattr(score.info, k, (self.f["info"].get(k) or "").strip())
        self._printed_info(score.info)
        if not self.f["measures"]:
            raise ValueError("no measures found")
        self.clef_names = self._clefs()
        self.custom_lines = {c["id"]: c for c in self.f.get("custom_lines", [])}
        self.lines_plain = 0                    # plain line shapes left out (Finale drawings)
        self.technique_groups = itertools.count()  # gradual technique changes
        self.score = score
        flow = self.flow = self._flow(score)
        self._players(score)
        self._staves(flow)
        self._note_marks()
        self._expressions(flow)
        self._smart_shapes(flow)
        self._finish_global(flow)
        self._drawn_lines(flow)
        self._repeats(flow)
        self._chord_symbols(flow)
        self._reconcile_keys(score)
        score.layout = self._layout()
        score.flows.append(flow)
        score.warnings[:0] = self.warnings
        return score

    _BARLINES = {"double": "double", "final": "final", "dashed": "dashed", "solid": "thick", "tick": "tick"}

    def _repeats(self, flow: ir.Flow) -> None:
        """Barline types, repeat barlines, endings and text repeats (Round 7 encodings)."""
        at: dict = {}  # barline position -> set of kinds
        ids = [m["id"] for m in self.f["measures"]]
        for i, m in enumerate(self.f["measures"]):
            start = self.meas_start[m["id"]]
            end = start + self.meas_dur[m["id"]]
            if m.get("forward_repeat"):
                at.setdefault(start, set()).add("start_repeat")
            if m.get("backward_repeat"):
                at.setdefault(end, set()).add("end_repeat")
            kind = self._BARLINES.get(m.get("barline", "normal"))
            if kind and not (kind == "final" and i == len(ids) - 1):  # the closing final barline is automatic
                at.setdefault(end, set()).add(kind)
            left = self._BARLINES.get(m.get("left_barline", "default"))
            if left in ("double", "thick", "dashed") and start > 0:
                at.setdefault(start, set()).add(left)
        for pos in sorted(at):
            kinds = at[pos]
            if {"start_repeat", "end_repeat"} <= kinds:
                kind = "end_start_repeat"
            elif "start_repeat" in kinds or "end_repeat" in kinds:
                kind = "start_repeat" if "start_repeat" in kinds else "end_repeat"
            else:
                kind = next(k for k in ("final", "double", "thick", "dashed", "tick") if k in kinds)
            if pos < flow.length or kind == "end_repeat":
                flow.barlines.append(ir.Barline(pos=pos, kind=kind))
        for e in self.f.get("endings", []):
            if e.get("hidden") or e["measure"] not in self.meas_start:
                continue
            start = self.meas_start[e["measure"]]
            k = ids.index(e["measure"])
            last = ids[min(k + max(e.get("length") or 1, 1) - 1, len(ids) - 1)]
            end = self.meas_start[last] + self.meas_dur[last]
            numbers = [int(n) for n in e.get("passes") or []] or [int(x) for x in re.findall(r"\d+", e.get("text", ""))]
            flow.endings.append(ir.Ending(pos=start, end=end, numbers=numbers, text=e.get("text", ""),
                                          open=bool(e.get("open"))))
        skipped = []
        for t in self.f.get("text_repeats", []):
            if t.get("hidden") or t["measure"] not in self.meas_start:
                continue
            marker = _repeat_marker(t.get("chunks", []))
            if marker is None:
                skipped.append("".join(c.get("text", "") for c in t.get("chunks", [])))
                continue
            start = self.meas_start[t["measure"]]
            self._place_marker(flow, marker, start, start + self.meas_dur[t["measure"]])
        if skipped:
            self.warnings.append(f"{len(skipped)} text repeat(s) not converted: {', '.join(sorted(set(skipped)))[:120]}")

    def _chord_symbols(self, flow: ir.Flow) -> None:
        """Finale chord symbols (staff-attached; Dorico's are global): root/bass from scale degree +
        key, suffix parsed into quality / interval / alterations."""
        keys = {m["id"]: m["key"] for m in self.f["measures"]}
        seen = set()
        for c in self.f.get("chords", []):
            if c["measure"] not in self.meas_start:
                continue
            if not c.get("show_root", True) and not re.search(r"n\.?\s*c", "".join(x.get("text", "") for x in c.get("suffix") or []).lower()):
                continue
            pos = self.pos(c["pos"])
            if pos in seen:  # the same chord on several staves
                continue
            seen.add(pos)
            k = keys.get(c["measure"], {"fifths": 0, "mode": 0, "linear": True})
            root, ralt = _scale_note(k, c.get("root_degree", 0), c.get("root_alter", 0))
            quality, interval, alts, text = _parse_chord_suffix(c.get("suffix") or [])
            if re.fullmatch(r"n\.?\s*c\.?", text.strip().lower()):  # "N.C." written as a chord suffix
                flow.chord_symbols.append(ir.ChordSymbol(pos=pos, root="C", no_chord=True, text=text))
                continue
            if c.get("root_lower") and quality == "major":
                quality = "minor"
            cs = ir.ChordSymbol(pos=pos, root=root, root_alter=ralt, quality=quality, interval=interval,
                                alterations=alts, text=text,
                                instrument=(self.staff_to_inst.get(c["staff"]) or (None,))[0])
            if c.get("show_bass"):
                cs.bass, cs.bass_alter = _scale_note(k, c.get("bass_degree", 0), c.get("bass_alter", 0))
            flow.chord_symbols.append(cs)
        flow.chord_symbols.sort(key=lambda c: c.pos)

    def _place_marker(self, flow: ir.Flow, marker: ir.RepeatMarker, start: Fraction, end: Fraction) -> None:
        """Sections at the bar start; jumps (and Fine) at the bar's last beat, as Dorico stores them."""
        beat = F(1)
        for ts in flow.time_signatures:
            if ts.pos <= start:
                beat = F(4, ts.den) * (3 if ts.den >= 8 and ts.num % 3 == 0 and ts.num > 3 else 1)
        marker.pos = start if marker.section in ("segno", "coda") else max(start, end - beat)
        if not any(m.pos == marker.pos and (m.section, m.jump) == (marker.section, marker.jump)
                   for m in flow.repeat_markers):
            flow.repeat_markers.append(marker)

    def _reconcile_keys(self, score: ir.Score) -> None:
        """Instrument pitch for staves without a transposition (concert scores): a key stated in
        the name or in staff text near the start ("in C", "C Tpt.") is used; staves of the same
        family without one follow it when the family agrees. Otherwise the standard instrument
        (B-flat clarinet/trumpet, F horn) is chosen by the Dorico writer."""
        staves_of: dict = {}
        for st in self.staff_objs.values():
            staves_of.setdefault(st.instrument, []).append(st)
        by_family: dict = {}
        for p in score.players:
            for inst in p.instruments:
                fam = keys.family(inst.name)
                if not fam or inst.transposition is not None:
                    continue
                k = keys.find_key(inst.name)
                if not k:
                    for st in staves_of.get(inst.id, []):
                        texts = [t.text for t in st.techniques if t.pos <= self.flow.bar_starts[min(1, len(self.flow.bar_starts) - 1)]]
                        found = [keys.find_key(t) for t in texts if keys.family(t) or re.match(r"\s*(in|to)\s", t, re.I)]
                        if any(found):
                            k = next(x for x in found if x)
                            self.warnings.append(f"instrument '{inst.name}': in {k} (staff text)")
                inst.key = k
                by_family.setdefault(fam, []).append(inst)
        for fam, insts in by_family.items():
            stated = {i.key for i in insts if i.key}
            if len(stated) == 1:
                k = stated.pop()
                for i in insts:
                    if not i.key and k != keys.standard_key(fam):
                        i.key = k
                        self.warnings.append(f"instrument '{i.name}': in {k} like the other {fam} staves")

    def _layout(self) -> ir.Layout | None:
        """Page size, staff size and empty-staff hiding from Finale's score page layout.
        Evpu: 288 per inch = 4 per point; a staff space is 24 Evpu at 100%."""
        lay = self.f.get("layout") or {}
        pf, systems = lay.get("page_format"), lay.get("systems") or []
        if not pf:
            return None
        pages = [p for p in lay.get("pages") or [] if p.get("width")]
        w, h = (pages[0]["width"], pages[0]["height"]) if pages else (pf["width"], pf["height"])
        scales = sorted(s["scaling"] for s in systems if s.get("scaling")) or [pf.get("scaling") or 1]
        out = ir.Layout(page_width=w / 4, page_height=h / 4, space=round(6 * scales[len(scales) // 2], 2))
        ppf = lay.get("part_page_format")
        if ppf and ppf.get("width"):
            out.part_page_width, out.part_page_height = ppf["width"] / 4, ppf["height"] / 4
            out.part_space = round(6 * (ppf.get("scaling") or 1), 2)
        sets = [{x["id"] for x in s["staves"]} for s in systems if s.get("staves")]
        if sets:
            every = set().union(*sets)
            out.staves_per_system = max(len(s) for s in sets)
            optional = {x for x in every if any(x not in s for s in sets)}
            if optional and len(optional) * 4 < len(every):
                # a few staves come and go (E.T.: a "Vc. II" divisi staff), the rest always show:
                # hiding every empty staff would look far less like Finale than showing all
                self.warnings.append(f"layout: Finale hides {len(optional)} of {len(every)} staves in "
                                     "some systems; all staves are shown")
            elif len(sets[0]) < len(every):
                out.hide_empty = "all"
            elif any(len(s) < len(every) for s in sets[1:]):
                out.hide_empty = "after_first"
        if "concert_pitch" in lay:
            # Finale's "Display in Concert Pitch"; a score with no transposing staff (Avatar's
            # untyped concert score) shows concert pitch either way, so it is a score in C
            transposes = any((i.get("transposition") or [0])[0] % 7 for i in self.f.get("instruments", []))
            out.concert_pitch = bool(lay["concert_pitch"]) or not transposes
        return out

    def pos(self, text: str) -> Fraction:
        """Absolute position from the facts, with any legacy pick-up spacer removed."""
        p = F(text) - self.shift
        return p if p > 0 else F(0)

    # ----------------------------------------------------------------- clefs
    def _clefs(self) -> dict[int, str]:
        """Clef index -> Dorico clef, from the document's clef table (no staff context)."""
        self.clef_chars = {c["index"]: c.get("char", 0) for c in self.f.get("clefs", [])}
        out = {c["index"]: self._clef_name(c) for c in self.f.get("clefs", [])}
        for k, v in DEFAULT_CLEFS.items():
            out.setdefault(k, v)
        return out

    def _clef_name(self, c: dict) -> str:
        """Dorico clef for musxdom clef info {type, octave, middle_c[, index]}."""
        t, octave, mid = c.get("type"), c.get("octave", 0), c.get("middle_c", 0)
        if t is None:
            return self.clef_names.get(c.get("index", 0), "clef.treble")
        # musxdom types a clef by its staff position; a percussion glyph on a normal staff
        # still draws a percussion clef in Finale (e.g. Maestro 139 for finger cymbals).
        glyph = CLEF_GLYPH_TYPE.get(self.clef_chars.get(c.get("index", -1), 0))
        if glyph in ("perc", "perc2") and t in ("G", "C", "F"):
            t = "perc1" if glyph == "perc" else "perc2"
        if t == "perc1":
            return "clef.percussion"
        if t == "perc2":
            return "clef.percussion2"
        if t == "tab":
            return "clef.tab"
        suffix = {-1: "8vb", 1: "8va"}.get(octave, "")
        name = CLEF_MAP.get((t + suffix, mid)) or CLEF_MAP.get((t, mid))
        return name or DEFAULT_CLEFS.get(c.get("index", 0), "clef.treble")

    # ------------------------------------------------------------------ flow
    def _flow(self, score: ir.Score) -> ir.Flow:
        measures = self.f["measures"]
        first = measures[0]
        spacer = F(first.get("legacy_pickup_spacer") or "0")
        if 0 < spacer < F(first["duration"]):
            self.shift = spacer
        flow = ir.Flow(id="F1", title=score.info.title, length=F(0))
        self.meas_start: dict[int, Fraction] = {}
        self.meas_dur: dict[int, Fraction] = {}
        last_sig = last_key = None
        for i, m in enumerate(measures):
            start = self.pos(m["pos"])
            dur = F(m["duration"]) - (self.shift if i == 0 else 0)
            self.meas_start[m["id"]] = start
            self.meas_dur[m["id"]] = dur
            flow.bar_starts.append(start)
            sig = self._time_sig(m["display_time"] or m["time"], m["id"])
            if i == 0:
                if self.shift:
                    flow.pickup = dur
                elif F(m["display_duration"]) != F(m["duration"]):
                    flow.pickup = F(m["duration"])
            if sig != last_sig:
                num, den, groups, symbol = sig
                flow.time_signatures.append(ir.TimeSignature(pos=start, num=num, den=den,
                                                             groups=list(groups), symbol=symbol))
                last_sig = sig
            k = m["key"]
            fifths = 0 if k["keyless"] else k["fifths"]
            mode = "minor" if (k["linear"] and k["mode"] == 1) else "major"
            key = (fifths, mode)
            if key != last_key:
                flow.key_signatures.append(ir.KeySignature(pos=start, fifths=fifths, mode=mode))
                if not k["linear"] or k["mode"] > 1:
                    self.warnings.append(f"measure {m['id']}: non-standard key mode {k['mode']} treated as major")
                last_key = key
            flow.length = start + dur
        return flow

    def _time_sig(self, ts: dict, meas: int):
        """(num, den, groups, symbol) from a musxdom time signature."""
        comps = ts.get("components") or []
        symbol = ts.get("abbreviation") or None
        units = {u for c in comps for u in c["units"]}
        if len(units) == 1:
            unit = F(units.pop())
            counts = [F(x) for c in comps for x in c["counts"]]
            total = sum(counts, F(0))
            if total.denominator == 1 and (unit * EDU).denominator == 1:
                num, den = _time_sig(int(total), int(unit * EDU))
                groups = ()
                if len(counts) > 1 and all(x.denominator == 1 for x in counts) and num == int(total):
                    groups = tuple(int(x) for x in counts)
                return num, den, groups, symbol
        # Composite (e.g. 3/4+2/8, or Finale's mixed units): keep the bar length exact and
        # write it over the smallest unit used. Within a group, counts add and units add.
        total = sum((sum((F(x) for x in c["counts"]), F(0)) * sum((F(u) for u in c["units"]), F(0))
                     for c in comps), F(0))  # crotchets
        smallest = min((F(u) for c in comps for u in c["units"]), default=F(1))
        den = 4 * smallest.denominator // max(smallest.numerator, 1)
        while (total * den / 4).denominator != 1:
            den *= 2
        self.warnings.append(f"measure {meas}: composite time signature written as {int(total * den / 4)}/{den}")
        return int(total * den / 4), den, (), None

    # --------------------------------------------------------------- players
    def _players(self, score: ir.Score) -> None:
        self.staff_to_inst: dict[int, tuple[str, int]] = {}
        for inst_f in self.f["instruments"]:
            staves = inst_f["staves"]
            uuid = inst_f.get("uuid") or None
            info = self.finale_instruments.get(uuid or "", {})
            raw = (inst_f.get("name") or inst_f.get("staff_name") or "").replace("\r", "\n")
            lines = [_clean(x) for x in raw.split("\n") if x.strip()]
            if len(lines) == 2 and not any(re.fullmatch(r"[\d\s&,./+()\-]+", x) for x in lines) \
                    and not lines[1].startswith("("):
                name = " / ".join(lines)  # "Bass Tbn." over "Tuba": two instruments share the staff
            else:
                name = _clean(raw)
            dbl = re.fullmatch(r"(\d[\d\s,&]*)\s*[-\u2013:]\s*(\D.*)", name or "")
            if dbl:  # "2 - Picc." (player 2 on piccolo): the instrument is the second part
                name = dbl.group(2).strip()
            elif re.fullmatch(r"[\d\s&,./+()\-\u2013]+", name or ""):  # "1 2", "1)", "1 -": name is elsewhere
                base = _clean(inst_f.get("group_name") or "") or re.sub(r"NoName$", "", info.get("name") or "")
                nums = " ".join(re.findall(r"\d+", name))
                if base:
                    from ..explode import _singular
                    name = f"{_singular(base) if nums else base} {nums}".strip()  # bracket group, else type
            if name == "Unknown Instrument":  # musxdom's label for an untyped, unnamed staff
                name = ""
            if not name and uuid != UNKNOWN_UUID:
                name = re.sub(r"NoName$", "", info.get("name") or "")
            if not name:  # untyped and unnamed (common in legacy .mus files)
                name = "Grand Staff" if len(staves) == 2 else f"Staff {staves[0]}"
            trans = self._transposition(inst_f)
            if trans == (0, 0) and (uuid in (None, UNKNOWN_UUID) or not info) and \
                    inst_f.get("transposition_type", "none") == "none":
                trans = None  # untyped staff, nothing set: concert pitch; Dorico picks the standard instrument
            no_key = inst_f.get("transposition_type") == "chromatic" and trans not in (None, (0, 0))
            n = len(score.players) + 1
            inst = ir.Instrument(id=f"I{n}", name=name, short_name=_clean(inst_f.get("short_name") or ""),
                                 finale_uuid=uuid, sound_id=info.get("sound"), num_staves=len(staves),
                                 transposition=trans, no_key_signature=no_key)
            score.players.append(ir.Player(id=f"P{n}", name=name, instruments=[inst]))
            for k, s in enumerate(staves):
                self.staff_to_inst[s] = (inst.id, k)

    @staticmethod
    def _transposition(inst_f: dict) -> tuple[int, int]:
        ks = inst_f.get("keysig")
        if inst_f.get("transposition_type") == "keysig" and ks:
            return (ks["interval"], _diatonic_to_semitones(ks["interval"], ks["adjust"]))
        ch = inst_f.get("chromatic")
        if inst_f.get("transposition_type") == "chromatic" and ch:
            return (ch["diatonic"], _chromatic_to_semitones(ch["diatonic"], ch["alteration"]))
        return (0, 0)

    # ---------------------------------------------------------------- staves
    def _staves(self, flow: ir.Flow) -> None:
        self.staff_objs: dict[int, ir.Staff] = {}
        self.entry_at: dict[int, tuple[int, Fraction, ir.Voice]] = {}
        self.entry_grace: dict[int, bool] = {}
        self.entry_rest: set[int] = set()
        order = [s for inst in self.f["instruments"] for s in inst["staves"]]
        by_id = {s["id"]: s for s in self.f["staves"]}
        for sid in order:
            sf = by_id.get(sid)
            if sf is None or sid not in self.staff_to_inst:
                continue
            iid, k = self.staff_to_inst[sid]
            st = ir.Staff(instrument=iid, index=k)
            self.staff_objs[sid] = st
            flow.staves.append(st)
            self._staff_clefs(st, sf)
            voices: dict[tuple[int, int], ir.Voice] = {}
            for e in sf["entries"]:
                if e.get("workaround_extra"):
                    continue
                voice = voices.setdefault((e["layer"], e["voice"]), ir.Voice(index=0))
                chord = self._chord(e, sid)
                self.entry_at[e["n"]] = (sid, chord.pos, voice)
                self.entry_grace[e["n"]] = chord.grace
                if chord.is_rest:
                    self.entry_rest.add(e["n"])
                if chord.hidden and chord.is_rest:
                    continue
                voice.chords.append(chord)
            for t in sf.get("tuplets", []):
                if t.get("tremolo"):
                    self._tremolo_pair(t, voices, sid)
                    continue
                pos, end = self.pos(t["pos"]), self.pos(t["end"])
                if end <= pos:
                    continue  # zero-length tuplet: Finale's singleton-beam workaround
                voice = voices.setdefault((t["layer"], t["voice"]), ir.Voice(index=0))
                unit = F(t["display_dur"])
                den = F(t["ref_num"]) * F(t["ref_dur"]) / unit
                voice.tuplets.append(ir.Tuplet(pos=pos, dur=end - pos, num=t["display_num"],
                                               den=int(den) if den.denominator == 1 else t["display_num"],
                                               unit=unit))
            for (layer, _v), voice in voices.items():
                voice.layer = layer
            st.voices = [voices[key] for key in sorted(voices)]
            self._staff_time_signatures(st, sf)
            self._snap_clefs(st, flow)
            if self.f.get("kind") == "mus":
                self._legacy_courtesy_accidentals(st, flow)
            for i, v in enumerate(st.voices):
                v.index = i
                v.tuplets.sort(key=lambda t: (t.pos, -t.dur))

    def _staff_time_signatures(self, st: ir.Staff, sf: dict) -> None:
        """Finale independent time signatures -> staff-only signatures. The bar keeps the
        score's length (musxdom positions are global: E.T.'s 12/8 quavers last 1/3), so a bar
        whose staff signature is longer or shorter gets a hidden tuplet in each voice, as Dorico
        does (Round 7: 12/8 over 4/4 = hidden 12:8 quaver tuplet over the bar)."""
        changes = {t["measure"]: t for t in sf.get("time_changes") or []}
        if not changes:
            return
        cur = None  # staff signature in effect; None = following the score
        for m in self.f["measures"]:
            start, gdur = self.meas_start[m["id"]], self.meas_dur[m["id"]]
            t = changes.get(m["id"])
            if t is None:
                if cur is not None:
                    num, den, groups, symbol = self._time_sig(m["display_time"] or m["time"], m["id"])
                    st.time_signatures.append(ir.TimeSignature(pos=start, num=num, den=den,
                                                               groups=list(groups), symbol=symbol))
                    cur = None
                continue
            sig = self._time_sig(t["display_time"] or t["time"], m["id"])
            if sig != cur:
                num, den, groups, symbol = sig
                st.time_signatures.append(ir.TimeSignature(pos=start, num=num, den=den,
                                                           groups=list(groups), symbol=symbol))
                cur = sig
            sdur = F(t.get("display_duration") or 0)
            if not sdur or sdur == gdur or gdur <= 0:
                continue
            unit = F(4, sig[1])
            tn, td = sdur / unit, gdur / unit
            if tn.denominator != 1 or td.denominator != 1:
                self.warnings.append(f"staff {st.instrument}: bar {m['id']} staff time signature "
                                     f"{sig[0]}/{sig[1]} against {gdur} crotchets not scaled")
                continue
            for v in st.voices:
                if any(start <= c.pos < start + gdur for c in v.chords):
                    v.tuplets.append(ir.Tuplet(pos=start, dur=gdur, num=int(tn), den=int(td),
                                               unit=unit, hidden=True))

    def _breaths(self, flow: ir.Flow) -> None:
        """Breath marks and caesuras. A mark on every staff that plays there goes to the global
        stream (Dorico's "all staves"); otherwise it is written on just the staves that have it
        (a PauseEvent in the stave stream; ref-extras2)."""
        by_pos: dict = {}
        for staff, pos, kind, look in self.pause_marks:
            by_pos.setdefault((pos, kind), {})[staff] = look
        for (pos, kind), staves in sorted(by_pos.items(), key=lambda x: x[0][0]):
            playing = {sid for sid, st in self.staff_objs.items()
                       if any(c.pitches and c.pos < pos <= c.pos + c.dur for v in st.voices for c in v.chords)}
            if playing and not playing <= set(staves):
                for sid, look in staves.items():
                    if sid in self.staff_objs:
                        self.staff_objs[sid].pauses.append(ir.Breath(pos=pos, kind=kind, appearance=look))
                continue
            look = max(set(staves.values()), key=list(staves.values()).count)
            flow.breaths.append(ir.Breath(pos=pos, kind=kind, appearance=look))

    def _identical_staves(self) -> None:
        """Flag staves whose notes are identical to another staff's (E.T. prints two copies of
        several staves); both are kept, the cleaner/reviewer can decide."""
        seen: dict = {}
        for sid, st in self.staff_objs.items():
            sig = tuple(sorted((c.pos, c.dur, tuple(p.midi for p in c.pitches))
                               for v in st.voices for c in v.chords if c.pitches))
            if len(sig) < 8:
                continue
            if sig in seen:
                self.warnings.append(f"staff {sid} has the same notes as staff {seen[sig]} "
                                     "(both kept; Finale prints both)")
            else:
                seen[sig] = sid

    def _niente(self) -> None:
        """A niente mark at the start of a crescendo / end of a diminuendo -> niente hairpin;
        any other niente is written as text."""
        near = F(1, 2)
        for st in self.staff_objs.values():
            keep = []
            for d in st.dynamics:
                if d.kind != "niente":
                    keep.append(d)
                    continue
                h = next((h for h in st.hairpins if (h.direction == "cresc" and abs(h.pos - d.pos) <= near)
                          or (h.direction == "dim" and abs(h.end - d.pos) <= near)), None)
                if h is not None:
                    h.niente = True
                else:
                    st.techniques.append(ir.Technique(pos=d.pos, text="niente", kind=None))
            st.dynamics = keep

    def _legacy_courtesy_accidentals(self, st: ir.Staff, flow: ir.Flow) -> None:
        """Legacy .mus files store "show accidental" without Finale 2014's freeze flag; Finale
        decided at run time. Finale 27's upgrade freezes it only where the accidental would not
        appear anyway (a courtesy accidental), so do the same: walk each bar in time order,
        track accidentals by staff line, and force-show a shown accidental that isn't needed.
        Uses concert spelling, which matches the written one for key-signature transposition."""
        bars = flow.bar_starts + [flow.length]
        keys = flow.key_signatures
        chords = sorted((c for v in st.voices for c in v.chords if c.pitches),
                        key=lambda c: (c.pos, not c.grace))
        bar = -1
        state: dict[tuple[str, int], int] = {}
        key_alter: dict[str, int] = {}
        for c in chords:
            while bar + 1 < len(bars) and bars[bar + 1] <= c.pos:
                bar += 1
                state = {}
                fifths = next((k.fifths for k in reversed(keys) if k.pos <= bars[bar]), 0)
                order = SHARP_ORDER if fifths >= 0 else FLAT_ORDER
                key_alter = {STEPS[order[i]]: (1 if fifths >= 0 else -1) for i in range(min(abs(fifths), 7))}
            for p in c.pitches:
                raw = self.raw_note.get(id(p), {})
                octave = (p.midi - p.alter) // 12 - 1
                current = state.get((p.step, octave), key_alter.get(p.step, 0))
                needed = p.alter != current
                if raw.get("show_acci") and p.accidental is None and not needed and not raw.get("tie_end"):
                    p.accidental = "show"
                state[(p.step, octave)] = p.alter

    @staticmethod
    def _snap_clefs(st: ir.Staff, flow: ir.Flow) -> None:
        """A Finale mid-bar clef applies from the first entry at or after its stored position
        (which is often a little before that entry); move it onto that entry."""
        bars = flow.bar_starts + [flow.length]
        starts = sorted({c.pos for v in st.voices for c in v.chords})
        for clef in st.clefs:
            if clef.pos in bars:
                continue
            bar_end = next((b for b in bars if b > clef.pos), flow.length)
            later = [p for p in starts if clef.pos <= p < bar_end]
            if later:
                clef.pos = later[0]

    def _staff_clefs(self, st: ir.Staff, sf: dict) -> None:
        last = None
        changes = sorted(sf.get("clef_changes", []), key=lambda c: F(c["pos"]))
        if not changes or F(changes[0]["pos"]) > 0:
            info = sf.get("default_clef_info") or {"index": sf.get("default_clef", 0)}
            last = self._clef_name(info)
            st.clefs.append(ir.Clef(pos=F(0), clef=last))
        for c in changes:
            name = self._clef_name(c)
            if name != last:
                st.clefs.append(ir.Clef(pos=self.pos(c["pos"]), clef=name))
                last = name

    def _chord(self, e: dict, staff: int) -> ir.Chord:
        grace = e["grace"]
        chord = ir.Chord(pos=self.pos(e["pos"]), dur=F(0) if grace else F(e["dur"]),
                         notated=F(e["notated"]), grace=grace,
                         grace_slash=bool(e.get("grace_slash")), hidden=e["hidden"],
                         stem=e.get("stem"))
        if not e["rest"]:
            for n in e["notes"]:
                p = ir.Pitch(midi=n["midi"], step=n["step"], alter=n["alter"],
                             tie=n["tie"], accidental=n.get("acc"))
                target = n.get("staff")
                if target and target != staff:  # cross-staff: drawn on another staff of the instrument
                    home, other = self.staff_to_inst.get(staff), self.staff_to_inst.get(target)
                    if home and other and home[0] == other[0]:
                        p.staff = other[1]
                chord.pitches.append(p)
                self.raw_note[id(p)] = n
            self._artificial_harmonic(chord, e["notes"])
        for a in e.get("artics", []):
            if a.get("hidden"):
                continue
            glyph = a.get("glyph") or ""
            m = re.fullmatch(r"tremolo([1-5])", glyph)
            strokes = int(m.group(1)) if m else (None if glyph else TREMOLO_GLYPHS.get(a["char"]))
            if strokes:  # single-stem tremolo drawn as an articulation
                chord.tremolo = max(chord.tremolo, strokes)
                continue
            if glyph in TRILL_GLYPH_ACCIDENTAL:  # "tr" on one note: a trill over that note
                self.note_trills.append((staff, chord, TRILL_GLYPH_ACCIDENTAL[glyph]))
                continue
            if glyph in GLYPH_TECHNIQUES:
                self.note_techniques.append((staff, chord.pos, GLYPH_TECHNIQUES[glyph]))
                continue
            if _base_glyph(glyph) == "stringsHarmonic":  # circle: natural harmonic (Round 12)
                chord.harmonic = chord.harmonic or "natural"
                continue
            if glyph in GLYPH_ARPEGGIOS:
                chord.arpeggio = GLYPH_ARPEGGIOS[glyph]
                continue
            if _base_glyph(glyph) in GLYPH_ORNAMENTS:
                chord.ornament = GLYPH_ORNAMENTS[_base_glyph(glyph)]
                continue
            if _base_glyph(glyph) in GLYPH_FERMATAS:
                chord.fermata = True
                style = GLYPH_FERMATAS[_base_glyph(glyph)]
                chord.fermata_style = None if style == "kNormal" else style
                continue
            if _base_glyph(glyph) in GLYPH_PAUSES:  # after the note
                kind, look = GLYPH_PAUSES[_base_glyph(glyph)]
                if not chord.grace:
                    self.pause_marks.append((staff, chord.pos + chord.dur, kind, look))
                continue
            if glyph in ("keyboardPedalPed", "keyboardPedalUp"):  # Finale pedal marks as articulations
                self.pedal_marks.append((staff, chord.pos, glyph == "keyboardPedalPed"))
                continue
            g = GLYPH_ARTICULATIONS.get(_base_glyph(glyph)) if glyph else None
            if g is None:
                g = ARTIC_GLYPHS.get(a["char"])
            if g is None:
                self.warnings.append(f"staff {staff} meas {e['measure']}: articulation "
                                     f"{glyph or a['char']} not converted yet")
                continue
            for name in (g if isinstance(g, tuple) else (g,)):
                if name == "fermata":
                    chord.fermata = True
                elif name not in chord.articulations:
                    chord.articulations.append(name)
        for ly in e.get("lyrics") or []:
            text = re.sub(r"^\s*\d+\.\s*", "", ly.get("text", "").replace("\xa0", " ")).strip()  # "1. Si" (verse number)
            if not text:
                continue
            before, after = ly.get("hyphen_before"), ly.get("hyphen_after")
            syl = "middle" if before and after else "start" if after else "end" if before else "whole"
            chord.lyrics.append(ir.Lyric(text=text, line=max(int(ly.get("number") or 1) - 1, 0),
                                         kind="chorus" if ly.get("type") == "chorus" else "verse",
                                         syllable=syl, extension=bool(ly.get("extension"))))
        return chord

    # ----------------------------------------------------------- page text
    INFO_INSERTS = {"title": "title", "subtitle": "subtitle", "composer": "composer",
                    "arranger": "arranger", "lyricist": "lyricist", "copyright": "copyright"}

    def _printed_info(self, info: ir.Info) -> None:
        """Score Info as Finale prints it. A field is kept if page text shows it (^title() ...);
        otherwise the text typed on page 1 where that field usually goes replaces it (Für Elise:
        Score Info "Title Insert" from the template, printed title typed as page text; Avatar:
        "composer" holds the cue number for the running header, the composer is typed on page 1).
        Files without page text keep Score Info as it is."""
        texts = [t for t in self.f.get("page_texts", []) if not t.get("hidden")]
        if not texts:
            return
        used = {i for t in texts for i in t.get("inserts", [])}
        on_page1 = {i for t in texts if t.get("start_page", 0) <= 1 for i in t.get("inserts", [])}

        def plain(t):
            return "".join(c["text"] for c in t.get("chunks", []) if not c.get("music")).strip()

        page1 = [t for t in texts if t.get("start_page") == 1 and not t.get("multi")
                 and not t.get("inserts") and plain(t) and not re.search(r"_{4,}", plain(t))]  # not "Name ____"
        legal = [t for t in page1 if _COPYRIGHT.search(plain(t))]
        words = [t for t in page1 if t not in legal]
        centre_top = sorted((t for t in words if t["h_align"] == "center" and t["v_align"] == "top"),
                            key=lambda t: -t.get("size", 0))
        slots = {
            "title": centre_top[0] if centre_top else None,
            "subtitle": centre_top[1] if len(centre_top) > 1 else None,
            "composer": next((t for t in words if t["h_align"] == "right" and t["v_align"] == "top"), None),
            "copyright": legal[0] if legal else None,
        }
        for t in texts:  # "^title()" + a typed line under it (E.T.: "From the Universal Picture ...")
            if "title" in t.get("inserts", []) and t.get("start_page", 0) <= 1 and info.title:
                rest = plain(t).replace(info.title, "", 1).strip()
                if rest and "subtitle" not in on_page1:
                    lines = [ln.strip() for ln in rest.splitlines() if ln.strip()]
                    if info.subtitle != " ".join(lines):
                        self.warnings.append(f"score info: subtitle {info.subtitle!r} is not printed in "
                                             f"Finale; using the line under the title {' '.join(lines)!r}")
                    info.subtitle = " ".join(lines)
                    on_page1 = on_page1 | {"subtitle"}
        if "title" in on_page1 and slots["title"] is not None:  # the printed title is the insert:
            slots["subtitle"], slots["title"] = slots["title"], None  # the largest typed text is next
        from_page: set[str] = set()
        for field, ins in self.INFO_INSERTS.items():
            if ins in on_page1 or field in from_page:
                continue
            old = getattr(info, field)
            slot = slots.get(field)
            if slot is not None:
                new = plain(slot)
                lines = [ln.strip() for ln in new.splitlines() if ln.strip()]
                if field == "composer" and len(lines) > 1:  # "James Horner (ASCAP)\nOrch. Jon Kull"
                    new = lines[0]
                    if "arranger" not in on_page1 and not (info.arranger and "arranger" in used):
                        info.arranger = " ".join(lines[1:])
                        from_page.add("arranger")
                else:
                    new = " ".join(lines)
                if new != old:
                    setattr(info, field, new)
                    self.warnings.append(f"score info: {field} {old!r} is not printed in Finale; "
                                         f"using the page text {new!r}")
            elif old and ins not in used and field in ("composer", "lyricist", "copyright"):
                # fields Dorico's default page templates print; the title is kept (it names the
                # project); subtitle/arranger stay as metadata (Dorico doesn't print them)
                setattr(info, field, "")
                self.warnings.append(f"score info: {field} {old!r} is not printed in Finale; left empty")

    # ----------------------------------------------------------- expressions
    def _staff_for(self, staff: int) -> ir.Staff | None:
        if staff == -1 and self.staff_objs:
            return next(iter(self.staff_objs.values()))
        if staff == -2 and self.staff_objs:
            return list(self.staff_objs.values())[-1]
        return self.staff_objs.get(staff)

    def _expressions(self, flow: ir.Flow) -> None:
        hidden = labels = 0
        exprs = self.f.get("expressions", [])
        text_of = lambda x: "".join(c.get("text", "") for c in x.get("chunks", [])).strip()
        # tempo words count as a tempo where they are on the top staff Finale shows, score-wide,
        # or on at least half the staves; E.T. "maestoso" next to the brass dynamics (4 of 28
        # staves) is expressive text on those staves
        systems = [sy for sy in (self.f.get("layout") or {}).get("systems") or [] if sy.get("staves")]
        shown = [x["id"] for x in systems[0]["staves"]] if systems else list(self.staff_objs)
        top = shown[0] if shown else None
        where: dict = defaultdict(set)
        for x in exprs:
            where[(x["measure"], x["pos"], text_of(x))].add(x.get("staff"))
        on_top = {k for k, sts in where.items()
                  if top in sts or any(s < 0 for s in sts if s is not None) or 2 * len(sts) >= len(shown)}
        first_bar = min((m["id"] for m in self.f["measures"]), default=1)
        for x in exprs:
            st = self._staff_for(x["staff"])
            if st is None or x.get("kind") != "text":
                continue
            if x.get("hidden"):  # invisible in Finale (usually playback-only): not notation
                hidden += 1
                continue
            raw = text_of(x)
            if x["measure"] == first_bar and F(x["pos"]) == 0 and re.fullmatch(r"\d+(?:\s*\n\s*\d+)+", raw):
                labels += 1  # stacked player numbers ("1" over "2") placed as a staff label
                continue
            chunks = _raw_music_chunks(x.get("chunks", []))
            plain = "".join(c["text"] for c in chunks)
            plain = plain.replace("\r", " ").replace("\n", " ").strip()
            cat = x.get("category")
            if cat != "rehearsalMarks" and x.get("enclosure") and re.fullmatch(r"[A-Za-z]{1,2}|\d{1,4}", plain):
                cat = "rehearsalMarks"  # older files: rehearsal marks are boxed text in "misc"
            if cat == "rehearsalMarks":
                p = self._snap(st, self.pos(x["pos"]))
                if p not in flow.rehearsal_marks:
                    flow.rehearsal_marks.append(p)
                continue
            rm = _repeat_marker(chunks) if plain and cat not in ("dynamics", "tempoMarks") else None
            if rm:  # D.S. al Coda / To Coda / segno / coda written as an expression
                pos = self.pos(x["pos"])
                starts = [b for b in flow.bar_starts if b <= pos] or [F(0)]
                later = [b for b in flow.bar_starts if b > starts[-1]]
                self._place_marker(flow, rm, starts[-1], later[0] if later else flow.length)
                continue
            ott = _text_ottava(x, plain, chunks)
            if ott:
                self.text_ottavas.append((x["staff"], self._snap(st, self.pos(x["pos"])), ott))
                continue
            harp = _harp_pedals(chunks)
            if harp is not None:  # pedal diagram or pedal-change letters (music-font text)
                self.harp_pending.append((x["staff"], self._snap(st, self.pos(x["pos"])), harp))
                continue
            if cat != "tempoMarks" and cat not in ("dynamics",) and (
                    (_is_tempo_text(plain) and (x["measure"], x["pos"], text_of(x)) in on_top) or _metronome(chunks)
                    or _metric_modulation(chunks)):
                cat = "tempoMarks"  # older files have no tempo category: tempo words or a metronome mark
            if cat in ("tempoMarks", "tempoAlts") or (cat in ("misc", "expressiveText", "techniqueText")
                                                     and _gradual_kind(plain)):
                if self._tempo_expression(x, chunks, plain, st, flow, cat):
                    continue
            music = bool(chunks) and all(c["music"] for c in chunks if c["text"].strip())
            pos = self._snap(st, self.pos(x["pos"]))
            kind = None
            names = [g for c in chunks for g in c.get("glyphs", []) if g]
            words = " ".join(c["text"] for c in chunks if not c["music"]).strip().lower()
            subito = words.rstrip(".") in ("sub", "subito")
            sm = _SUBITO.match(plain.strip())
            joined = "".join(GLYPH_DYNAMICS.get(n, "?") for n in names)
            if music and len(names) == 1 and names[0] in GLYPH_DYNAMICS:
                kind = GLYPH_DYNAMICS[names[0]]
            elif music and len(names) >= 2 and joined in ("sff", "sfff", "rff", "sffz", "fff", "ffff", "ppp", "pppp"):
                kind = joined  # "S" + "f" in Maestro = sf + f = sff (often in "Miscellaneous")
            elif (music or subito) and len(names) == 2 and \
                    GLYPH_DYNAMICS.get(names[0], "") + GLYPH_DYNAMICS.get(names[1], "") in _COMBINED and \
                    GLYPH_DYNAMICS.get(names[0]) in _LEVELS and GLYPH_DYNAMICS.get(names[1]) in _LEVELS:
                kind = GLYPH_DYNAMICS[names[0]] + GLYPH_DYNAMICS[names[1]]  # "mf" + "mp" -> mf-mp
            elif subito and len(names) == 1 and names[0] in GLYPH_DYNAMICS:
                kind = GLYPH_DYNAMICS[names[0]]
            elif music and len(plain) == 1:
                kind = DYNAMIC_GLYPHS.get(ord(plain))
            elif plain in _DYNAMIC_WORDS:
                kind = plain
            elif sm and (sm.group("a") or sm.group("b")).strip() in _DYNAMIC_WORDS:
                kind, subito = (sm.group("a") or sm.group("b")).strip(), True
            if kind:
                st.dynamics.append(ir.Dynamic(pos=pos, kind=kind.replace("-", ""), subito=subito))
            elif cat == "dynamics":
                self.warnings.append(f"measure {x['measure']}: dynamic expression {plain!r} not recognised")
            elif plain and _technique_kind(plain):
                st.techniques.append(ir.Technique(pos=pos, text=plain, kind=_technique_kind(plain)))
            elif plain:
                text, ok = _chunks_text(chunks)
                text = " ".join(text.split())
                if ok and any(ch.isalnum() for ch in text):
                    boxed = bool(x.get("enclosure")) or any(c.get("boxed") for c in chunks)
                    st.techniques.append(ir.Technique(pos=pos, text=text, kind=None, boxed=boxed))  # written as text
                elif not any(ch.isalnum() for ch in plain):
                    pass  # bracket shapes around harp pedal changes etc.: decoration only
                else:
                    self.warnings.append(f"measure {x['measure']}: music-symbol text {plain!r} not converted yet")
        if hidden:
            self.warnings.append(f"{hidden} hidden expression(s) skipped (invisible in Finale)")
        if labels:
            self.warnings.append(f"{labels} stacked player number(s) in bar 1 skipped (staff labels; "
                                 "the players are numbered in Dorico)")
        self._text_ottava_lines(flow)
        for st in self.staff_objs.values():  # identical instruction twice at one spot (Finale copies)
            seen, keep = set(), []
            for t in sorted(st.techniques, key=lambda t: t.pos):
                if (t.pos, t.kind, t.text) not in seen:
                    seen.add((t.pos, t.kind, t.text))
                    keep.append(t)
            st.techniques = keep

    def _text_ottava_lines(self, flow: ir.Flow) -> None:
        """'8va' text (repeated at each system) ... 'loco' -> one ottava line; notes are stored at
        written pitch like under an ottava shape (the shift is applied in _finish_global)."""
        by_staff: dict = {}
        for sid, pos, kind in sorted(self.text_ottavas, key=lambda t: (t[0], t[1])):
            by_staff.setdefault(sid, []).append((pos, kind))
        unclosed = 0
        for sid, events in by_staff.items():
            st = self._staff_for(sid)
            cur = None  # (start, kind)
            for pos, kind in events + [(flow.length, None)]:
                if kind == "loco" or kind is None or (cur and kind != cur[1]):
                    if cur and pos > cur[0]:
                        st.ottavas.append(ir.Ottava(pos=cur[0], end=pos, kind=cur[1]))
                        unclosed += kind is None
                    cur = None
                if kind not in (None, "loco") and cur is None:
                    cur = (pos, kind)
        if unclosed:
            self.warnings.append(f"{unclosed} text 8va/8vb without 'loco': runs to the end of the flow")

    def _tempo_expression(self, x: dict, chunks: list, plain: str, st: ir.Staff, flow: ir.Flow,
                          cat: str | None = None) -> bool:
        """Tempo marks (global in Dorico; Finale often repeats them on several staves)."""
        pos = self._snap(st, self.pos(x["pos"]))
        kind = _gradual_kind(plain)
        if kind:
            if not any(g[0] == pos for g in self.gradual_pending):
                self.gradual_pending.append((pos, kind, plain, None))
            return True
        if (cat or x.get("category")) != "tempoMarks":
            return False
        eq = _metric_modulation(chunks)
        if eq:  # Round 12: a Dorico tempo equation (Finale often repeats it on several staves)
            if not any(t.pos == pos and t.equation == eq for t in flow.tempos):
                flow.tempos.append(ir.Tempo(pos=pos, equation=eq, show_metronome=False))
            return True
        met = _metronome(chunks)
        if not met and any(t.text == " ".join(plain.split()) and abs(t.pos - pos) <= 1 for t in flow.tempos):
            return True  # the same tempo words copied on another staff, a little apart
        same = next((t for t in flow.tempos if t.pos == pos), None)
        if same is not None:  # Finale often stacks text and metronome mark as two expressions
            if met and not same.show_metronome:
                unit, bpm, bpm_max, words = met
                same.bpm, same.unit, same.bpm_max, same.show_metronome = bpm, unit, bpm_max, True
                same.text = " ".join(x for x in (same.text, words) if x)
            return True
        if met:
            unit, bpm, bpm_max, words = met
            flow.tempos.append(ir.Tempo(pos=pos, bpm=bpm, unit=unit, text=words, bpm_max=bpm_max))
        else:
            text, ok = _chunks_text(chunks)
            text = " ".join(text.split())
            if not text:
                return True
            bpm = float(x["value"]) if x.get("playback") == "time" and x.get("value") else None
            flow.tempos.append(ir.Tempo(pos=pos, bpm=bpm, text=text, show_metronome=False))
        return True

    def _finish_global(self, flow: ir.Flow) -> None:
        """Fermatas, gradual tempo spans, pedal lines: things that need all staves read."""
        # Finale stores notes under an ottava line at the written pitch (playback adds the
        # octave); the IR is concert/sounding, so move them (Asteroid Field / Raider's March
        # against Finale's own MusicXML: every 12-semitone mismatch was under an 8va)
        shift = {"up8": 12, "down8": -12, "up15": 24, "down15": -24}
        for st in self.staff_objs.values():
            for o in st.ottavas:
                start = self.ottava_raw_start.get(id(o), o.pos)
                for v in st.voices:
                    for c in v.chords:
                        if start <= c.pos < o.end:
                            for p in c.pitches:
                                p.midi += shift[o.kind]
        fermatas: dict = {}  # pos -> styles of the fermatas there (Dorico: one global pause)
        for st in self.staff_objs.values():
            for v in st.voices:
                for c in v.chords:
                    if c.fermata:
                        fermatas.setdefault(c.pos, []).append(c.fermata_style or "kNormal")
        for pos, styles in sorted(fermatas.items()):
            style = max(set(styles), key=styles.count)
            if style == "kNormal":
                flow.pauses.append(pos)
            elif style == "curlew":
                flow.breaths.append(ir.Breath(pos=pos, kind="curlew", appearance=""))
            else:
                flow.breaths.append(ir.Breath(pos=pos, kind="fermata", appearance=style))
        self._breaths(flow)
        self._niente()
        self._identical_staves()
        flow.pauses.sort()
        flow.rehearsal_marks.sort()
        flow.tempos.sort(key=lambda t: t.pos)
        starts = sorted({t.pos for t in flow.tempos} | {g[0] for g in self.gradual_pending})
        for pos, kind, text, end in sorted(self.gradual_pending, key=lambda g: g[0]):
            if end is None:  # a word without a line: until the next tempo mark, at most two bars
                later = [p for p in starts if p > pos]
                two_bars = self._bar_after(flow, self._bar_after(flow, pos))
                end = min([two_bars] + later)
            if end > pos:
                flow.gradual_tempos.append(ir.GradualTempo(pos=pos, end=end, kind=kind, text=text))
        # harp pedals: diagrams set all seven; letter changes apply to the previous setting
        state: dict[int, dict[str, int]] = {}
        for sid, pos, (kind, values) in sorted(self.harp_pending, key=lambda h: h[1]):
            st = self._staff_for(sid)
            if st is None:
                continue
            key = st.instrument
            cur = dict(state.get(key, {k: 0 for k in "CDEFGAB"}))
            cur.update(values)
            state[key] = cur
            st.harp_pedals.append(ir.HarpPedals(pos=pos, settings=cur))
        by_staff = defaultdict(list)
        for sid, pos, down in sorted(self.pedal_marks, key=lambda m: m[1]):
            by_staff[sid].append((pos, down))
        for sid, marks in by_staff.items():
            st = self.staff_objs.get(sid)
            if st is None:
                continue
            start = None
            for pos, down in marks:
                if down:
                    if start is not None and pos > start:  # re-pedal without a release mark
                        st.pedals.append(ir.Pedal(start, pos))
                    start = pos
                elif start is not None and pos > start:
                    st.pedals.append(ir.Pedal(start, pos))
                    start = None
            if start is not None:
                st.pedals.append(ir.Pedal(start, self._bar_after(flow, start)))

    @staticmethod
    def _bar_after(flow: ir.Flow, pos: Fraction) -> Fraction:
        return next((b for b in flow.bar_starts if b > pos), flow.length)

    def _smart_shapes(self, flow: ir.Flow) -> None:
        for sh in self.f.get("smart_shapes", []):
            t = sh["type"]
            a, b = sh.get("start"), sh.get("end")
            if not a or not b or not (a.get("valid") and b.get("valid")):
                continue
            if t.startswith("slur") or t.startswith("dashSlur") or t.startswith("dashCurve"):
                ea, eb = self.entry_at.get(a["entry"]), self.entry_at.get(b["entry"])
                if ea and eb:
                    _, pa, voice = ea
                    pb = eb[1]
                    if pb >= pa:
                        voice.slurs.append(ir.Slur(pos=pa, end=pb))
                else:
                    self.warnings.append(f"slur {sh['id']}: endpoints not found")
            elif t in ("cresc", "decresc"):
                st = self.staff_objs.get(a["staff"])
                p0, p1 = self._shape_pos(a, st), self._shape_pos(b, st, end=True)
                if st is not None and p0 is not None and p1 is not None and p1 > p0:
                    st.hairpins.append(ir.Hairpin(pos=p0, end=p1,
                                                  direction="cresc" if t == "cresc" else "dim"))
            elif t in ("trill", "trillExt") or (t == "smartLine" and self._is_trill_line(sh)):
                self._trill(sh, a, b)
            elif t in OTTAVA_SHAPES:
                st = self.staff_objs.get(a["staff"])
                p0, p1 = self._shape_pos(a, st), self._shape_pos(b, st, end=True)
                if st is not None and p0 is not None and p1 is not None and p1 > p0:
                    o = ir.Ottava(pos=p0, end=p1, kind=OTTAVA_SHAPES[t])
                    st.ottavas.append(o)
                    # which notes Finale stores at written pitch: those from the raw start on
                    raw = self.pos(a["pos"]) if (not a.get("entry") and "pos" in a) else p0
                    self.ottava_raw_start[id(o)] = raw
            elif t == "smartLine" and self._gradual_line(sh):
                st = self.staff_objs.get(a["staff"])
                p0, p1 = self._shape_pos(a, st), self._shape_pos(b, st, end=True)
                kind, text = self._gradual_line(sh)
                if p0 is not None and p1 is not None and p1 > p0 and not any(g[0] == p0 for g in self.gradual_pending):
                    self.gradual_pending.append((p0, kind, text, p1))
            elif t == "glissando":
                ea, eb = self.entry_at.get(a["entry"]), self.entry_at.get(b["entry"])
                if ea and eb and (a["entry"] in self.entry_rest or b["entry"] in self.entry_rest):
                    self.warnings.append(f"glissando {sh['id']}: starts or ends on a rest (Finale leftover), skipped")
                    continue
                if ea and eb and (eb[1] > ea[1] or (eb[1] == ea[1] and self.entry_grace.get(a["entry"]))):
                    line = self.custom_lines.get(sh.get("line_style"), {}).get("style")
                    g = ir.Glissando(pos=ea[1], end=eb[1], line="straight" if line == "solid" else "wavy",
                                     start_grace=self.entry_grace.get(a["entry"], False),
                                     end_grace=self.entry_grace.get(b["entry"], False))
                    if eb[2] is not ea[2]:  # ends on another staff/voice (harp: hand to hand)
                        sa, sb = self.staff_objs[ea[0]], self.staff_objs[eb[0]]
                        if sa.instrument != sb.instrument:
                            self.warnings.append(f"glissando {sh['id']}: ends on another instrument")
                            continue
                        g.end_staff = sb.index if sb is not sa else None
                        g.end_voice = sb.voices.index(eb[2])
                    ea[2].glissandi.append(g)
                else:
                    self.warnings.append(f"glissando {sh['id']}: endpoints not found")
            elif t in LINE_SHAPES or t == "smartLine":
                self._line(sh, a, b)
            else:
                self.warnings.append(f"smart shape '{t}' not converted yet")
        if self.lines_plain:
            self.warnings.append(f"{self.lines_plain} plain line(s) with no text or hooks left out "
                                 "(Finale drawings: short strokes, zero-length or vertical lines)")
        self._dedupe_hairpins()

    def _tremolo_pair(self, t: dict, voices: dict, sid: int) -> None:
        """Finale's two-note tremolo: two short notes (their beams are the strokes) in a hidden
        tuplet that stretches them to the real length. Dorico: the two notes at their real length,
        joined by tremolo strokes (Round 12)."""
        pos, end = self.pos(t["pos"]), self.pos(t["end"])
        voice = voices.get((t["layer"], t["voice"]))
        pair = [c for c in (voice.chords if voice else []) if pos <= c.pos < end and not c.grace]
        if len(pair) != 2 or not all(c.pitches for c in pair) or not t.get("beams"):
            self.warnings.append(f"staff {sid}: tremolo at {t['pos']} not converted yet")
            return
        own = 0 if pair[0].dur >= 1 else 1 if pair[0].dur >= F(1, 2) else 2  # the notes' own beams
        for c in pair:
            c.notated = c.dur
        pair[0].tremolo_pair = max(1, t["beams"] - own)
        pair[1].tremolo_pair_end = True

    def _drawn_lines(self, flow: ir.Flow) -> None:
        """Lines with no words that only extend another mark: a dashed line after an "8va" typed
        as text is that ottava's line (E.T.: 35); a solid line after "Ped." text is a pedal
        line (E.T. vibraphone). The ottava / pedal line already says it, in Dorico's own way."""
        ott = ped = 0
        for st in self.staff_objs.values():
            keep = []
            for ln in st.lines:
                if not (ln.text or ln.centre_text):
                    if ln.body == "dashed" and any(o.pos - 1 <= ln.pos <= o.end for o in st.ottavas):
                        ott += 1
                        continue
                    mark = next((t for t in st.techniques if t.kind is None and abs(t.pos - ln.pos) <= 1
                                 and re.fullmatch(r"ped\.?", t.text.strip(), re.I)), None)
                    if ln.body == "solid" and mark is not None:
                        st.techniques.remove(mark)
                        st.pedals.append(ir.Pedal(pos=mark.pos, end=ln.end))
                        ped += 1
                        continue
                keep.append(ln)
            st.lines = keep
        if ott:
            self.warnings.append(f"{ott} dashed line(s) drawn after 8va text: part of that ottava line")
        if ped:
            self.warnings.append(f"{ped} \"Ped.\" text(s) with a drawn line: pedal line(s)")

    @staticmethod
    def _artificial_harmonic(chord: ir.Chord, notes: list[dict]) -> None:
        """A stopped note with a diamond above it (the touched note) is one artificial harmonic:
        Dorico draws the diamond itself from the harmonic partial (Round 12)."""
        if len(notes) != 2 or len(chord.pitches) != 2:
            return
        lo, hi = sorted(range(2), key=lambda i: notes[i]["midi"])
        if notes[lo].get("notehead") or not (notes[hi].get("notehead") or "").startswith("noteheadDiamond"):
            return
        partial = ARTIFICIAL_PARTIALS.get(notes[hi]["midi"] - notes[lo]["midi"])
        if partial is None:
            return
        chord.harmonic, chord.harmonic_partial = "artificial", partial
        del chord.pitches[hi]

    def _line(self, sh: dict, a: dict, b: dict) -> None:
        """A line shape (Round 12): a Dorico line with its words, or a gradual technique change
        ("ord. -- move bow towards... --> sul pont."). Plain lines with no words or hooks are
        Finale drawings in the film scores (Avatar: seven short strokes per cue) and are left out."""
        st = self.staff_objs.get(a["staff"])
        if st is None:
            return
        p0, p1 = self._shape_pos(a, st), self._shape_pos(b, st, end=True)
        t = sh["type"]
        start = centre = end = ""
        arrow = False
        if t in LINE_SHAPES:
            body, hs, he = LINE_SHAPES[t]
        else:
            cl = self.custom_lines.get(sh.get("line_style"))
            if not cl:
                self.warnings.append(f"line {sh['id']}: its custom line style is missing")
                return
            body = {"solid": "solid", "dashed": "dashed"}.get(cl.get("style"))
            if cl.get("style") == "char" and cl.get("glyph") == "wiggleTrill":
                body = "wavy"
            hs = cl.get("cap_start") == "hook" and cl.get("hook_start", 0) != 0
            he = cl.get("cap_end") == "hook" and cl.get("hook_end", 0) != 0
            arrow = cl.get("cap_end") == "arrow" and cl.get("arrow_end", 0) != 0
            parts = {}
            for key in ("start_text", "center_text", "end_text"):
                chunks = _raw_music_chunks(cl.get(key, []))
                if any(c.get("music") and c["text"].strip() for c in chunks):
                    body = None  # music-font symbols on the line: not known yet
                parts[key] = " ".join("".join(c["text"] for c in chunks if not c.get("music")).split())
            start, centre, end = parts["start_text"], parts["center_text"], parts["end_text"]
            if body is None:
                self.warnings.append(f"line {sh['id']}: custom line with music symbols not converted yet")
                return
        if p0 is None or p1 is None or p1 <= p0 or not (start or centre or end or hs or he or arrow or body == "wavy"):
            self.lines_plain += 1
            return
        mid = self._snap(st, p0 + (p1 - p0) / 2)
        k0, k1 = _technique_kind(start), _technique_kind(end)
        if k0 in TRANSITION_TECHNIQUES and k1 in TRANSITION_TECHNIQUES and k0 != k1:
            g = next(self.technique_groups)
            st.techniques.append(ir.Technique(pos=p0, text=start, kind=k0, group=g))
            if centre:  # "move bow towards...": Dorico's transition line has no words
                st.techniques.append(ir.Technique(pos=mid, text=centre))
            st.techniques.append(ir.Technique(pos=p1, text=end, kind=k1, group=g))
            return
        st.lines.append(ir.Line(pos=p0, end=p1, body=body, hook_start=hs, hook_end=he, arrow_end=arrow,
                                text=start, centre_text="" if start else centre))
        if start and centre:  # Dorico lines carry one text
            st.techniques.append(ir.Technique(pos=mid, text=centre))
        if end:
            st.techniques.append(ir.Technique(pos=p1, text=end, kind=k1))

    def _note_marks(self) -> None:
        """Marks drawn as articulations that Dorico models differently: a "tr" on one note
        becomes a trill over that note (and its tie chain); bowings become playing techniques."""
        for sid, chord, acc in self.note_trills:
            st = self.staff_objs.get(sid)
            voice = next((v for v in st.voices if any(c is chord for c in v.chords)), None) if st else None
            if voice is None or not chord.pitches:
                continue
            end, cur = chord.pos + chord.dur, chord
            for c in sorted(voice.chords, key=lambda c: c.pos):
                if c.pos == end and c.pitches and any(q.tie for q in cur.pitches):
                    cur, end = c, c.pos + c.dur
            interval = None
            if acc is not None:
                interval = self._upper_neighbour_semitones(st, chord.pitches[-1], acc)
                interval = interval if 1 <= interval <= 3 else None
            if not any(t.pos == chord.pos for t in voice.trills):
                voice.trills.append(ir.Trill(pos=chord.pos, end=end, interval=interval))
        for sid, pos, kind in self.note_techniques:
            st = self.staff_objs.get(sid)
            if st is not None:
                st.techniques.append(ir.Technique(pos=pos, text=kind, kind=kind))

    def _gradual_line(self, sh: dict):
        """A custom line starting with "rit." / "accel." (WW: dashed "rit." lines)."""
        cl = self.custom_lines.get(sh.get("line_style"))
        if not cl:
            return None
        text = "".join(c["text"] for c in cl.get("start_text", []) if not c.get("music")).strip()
        kind = _gradual_kind(text)
        return (kind, text) if kind else None

    # ---------------------------------------------------------------- trills
    def _is_trill_line(self, sh: dict) -> bool:
        """A custom line drawn with the wavy trill glyph and/or starting with "tr"."""
        cl = self.custom_lines.get(sh.get("line_style"))
        if not cl:
            return False
        names = [g for c in cl.get("start_text", []) for g in c.get("glyphs", []) if g]
        if any(n in TRILL_GLYPH_ACCIDENTAL for n in names):
            return True
        start = "".join(c["text"] for c in _raw_music_chunks(cl.get("start_text", []))).strip()
        if names and cl.get("glyph") == "wiggleTrill":
            return False  # wavy line with some other symbol: not a trill (unknown)
        if any(ord(ch) in TRILL_TEXT_GLYPHS for ch in start) or start.lower().startswith("tr"):
            return True
        # a bare wavy line is a trill extension; a wavy line with other text (Trex: a
        # tenuto-staccato glyph) is something else (shake? vibrato?) -> not guessed
        return cl.get("char") in TRILL_LINE_GLYPHS and not start

    def _trill(self, sh: dict, a: dict, b: dict) -> None:
        st = self.staff_objs.get(a["staff"])
        if st is None:
            return
        p0, p1 = self._shape_pos(a, st), self._shape_pos(b, st, end=True)
        if p0 is None or p1 is None or p1 < p0:
            return
        # a zero-length trill line (Trex: just the "tr♭" symbol, both ends at the same spot)
        # is a trill on the note there; the tie-chain rule below extends it over that note
        voice = next((v for v in st.voices if any(c.pos == p0 and c.pitches for c in v.chords)),
                     st.voices[0] if st.voices else None)
        if voice is None:
            return
        # accidental shown with the "tr" (custom line start text) -> interval to the upper note
        acc = None
        cl = self.custom_lines.get(sh.get("line_style"))
        names = [g for c in (cl or {}).get("start_text", []) for g in c.get("glyphs", []) if g]
        for n in names:
            if TRILL_GLYPH_ACCIDENTAL.get(n) is not None:
                acc = TRILL_GLYPH_ACCIDENTAL[n]
            elif n in ACCIDENTAL_GLYPHS:
                acc = ACCIDENTAL_GLYPHS[n]
        if not names:
            for ch in "".join(c["text"] for c in _raw_music_chunks((cl or {}).get("start_text", []))):
                if ord(ch) in TRILL_ACCIDENTALS:
                    acc = TRILL_ACCIDENTALS[ord(ch)]
        interval = None
        note = next((c for c in voice.chords if c.pos == p0 and c.pitches), None)
        if acc is not None and note is not None:
            interval = self._upper_neighbour_semitones(st, note.pitches[-1], acc)
            if not 1 <= interval <= 3:  # the "tr<accidental>" belongs to a line style used on
                interval = None         # notes it doesn't fit (Willow Cl 2: tr-flat on written E)
        if interval is None:  # "tr 1/2" / "tr WT" (Avatar): half- or whole-step trill
            words = "".join(c["text"] for c in (cl or {}).get("start_text", []) if not c.get("music"))
            interval = _trill_step(words)
        if note is not None:  # a trill covers its note (and the notes tied to it)
            chain_end = note.pos + note.dur
            for c in sorted(voice.chords, key=lambda c: c.pos):
                if c.pos == chain_end and c.pitches and any(q.tie for q in note.pitches):
                    note, chain_end = c, c.pos + c.dur
            if p0 <= p1 <= chain_end or abs(chain_end - p1) <= 2 * self.SNAP_TOLERANCE:
                p1 = chain_end  # line ends inside (or just past) the trilled note's tie chain
        if p1 <= p0:
            return
        if any(t.pos == p0 for t in voice.trills):  # duplicate (Finale copies)
            for t in voice.trills:
                if t.pos == p0:
                    t.end = max(t.end, p1)
                    t.interval = t.interval if t.interval is not None else interval
            return
        voice.trills.append(ir.Trill(pos=p0, end=p1, interval=interval))

    def _upper_neighbour_semitones(self, st: ir.Staff, p: ir.Pitch, acc: int) -> int:
        """Semitones from p up to the next letter carrying alteration `acc`, worked out in
        written pitch (the accidental is what the player reads)."""
        inst = next((i for pl in self.score.players for i in pl.instruments if i.id == st.instrument), None)
        dia, chrom = (inst.transposition if inst else None) or (0, 0)
        return upper_neighbour_semitones(p.step, p.midi, dia, chrom, acc)

    def _dedupe_hairpins(self) -> None:
        """Finale scores often carry duplicate hairpins (copied twice, or a second one
        overlapping the first in the same direction). Keep one per overlapping set: the
        longest (Willow: Horn 1 had two identical crescendos at beat 169 plus an overlapping
        third; Violins 1/2 had theirs twice at 179)."""
        removed = 0
        for st in self.staff_objs.values():
            keep: list[ir.Hairpin] = []
            for h in sorted(st.hairpins, key=lambda h: (h.pos, -(h.end - h.pos))):
                if any(k.direction == h.direction and h.pos < k.end and k.pos < h.end for k in keep):
                    removed += 1
                    continue
                keep.append(h)
            st.hairpins = keep
        if removed:
            self.warnings.append(f"{removed} duplicate/overlapping hairpin(s) removed")

    def _shape_pos(self, ep: dict, st: ir.Staff | None = None, end: bool = False) -> Fraction | None:
        if ep.get("entry") and ep["entry"] in self.entry_at:
            return self.entry_at[ep["entry"]][1]
        if "pos" in ep:
            p = self.pos(ep["pos"])
            if st is None:
                return p
            return self._snap_end(st, p) if end else self._snap(st, p)
        return None

    END_ON_ONSET = F(1, 32)  # crotchets: an end this close to a note start ends there

    def _snap_end(self, st: ir.Staff, p: Fraction) -> Fraction:
        """A hairpin end inside a note covers that note: move it forward to the next note start
        or barline (Willow bar 1: Flute 1 ends at 3.88, Oboe 1 at 3.90, both inside the last
        quintuplet note -> both end at the barline). An end right at a note start stays there."""
        self._snap(st, p)  # fills the onset cache
        key = ("end", id(st))
        if key not in self._onsets:
            self._onsets[key] = sorted(set(self._onsets[id(st)]) |
                                       {c.pos + c.dur for v in st.voices for c in v.chords if c.pitches})
        cands = self._onsets[key]
        near = min(cands, key=lambda c: abs(c - p), default=None)
        if near is not None and abs(near - p) <= self.END_ON_ONSET:
            return near
        later = [c for c in cands if c >= p]
        if later and later[0] - p <= 2 * self.SNAP_TOLERANCE:
            return later[0]
        return self._snap(st, p)

    SNAP_TOLERANCE = F(1, 2)   # crotchets
    SNAP_GRID = F(1, 4)

    def _snap(self, st: ir.Staff, p: Fraction) -> Fraction:
        """Measure-attached markings carry the raw position Finale got from where they were
        clicked (e.g. beat 1 + 595/1024), drawn next to the note they belong to. Snap to the
        nearest note onset or barline on the staff within SNAP_TOLERANCE, else to the
        nearest semiquaver."""
        if not hasattr(self, "_onsets"):
            self._onsets = {}
        key = id(st)
        if key not in self._onsets:
            self._onsets[key] = sorted({c.pos for v in st.voices for c in v.chords}
                                       | set(self.flow.bar_starts) | {self.flow.length})
        cands = self._onsets[key]
        best = min(cands, key=lambda c: abs(c - p), default=None)
        if best is not None and abs(best - p) <= self.SNAP_TOLERANCE:
            return best
        return round(p / self.SNAP_GRID) * self.SNAP_GRID


def _clean(name: str) -> str:
    return " ".join(name.replace("\r", " ").replace("\n", " ").split())
