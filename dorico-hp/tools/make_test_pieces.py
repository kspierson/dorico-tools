"""Generate the MusicXML test pieces used to measure Finale's Human Playback.

    python3 tools/make_test_pieces.py OUT_DIR

Each piece isolates one musical feature (articulations, slurs, hairpins, ...).
The same files are imported into Finale (to capture what Human Playback does)
and into Dorico (to see how Dorico stores the same notation), so the two can
be compared note for note.

Notation mini-language used below (one string per note, space separated):

    A4:q          A4 crotchet            r:h      minim rest
    C#5:e.        dotted quaver          C4+E4+G4:h  chord
    G4:e3         quaver triplet         A4:w~    tied to the next note
    marks after '/' : A4:q/stacc,acc   (see MARKS)
    '(' before a note starts a slur, ')' after a note ends it:  (C5:e D5:e)
    'grace:D5' before a note adds an acciaccatura, 'app:D5' an appoggiatura

Directions are separate tokens:  !p  !mf  !sfz  <  >  |   (| ends a hairpin)
                                 "rit."  "a tempo"  @100 (metronome)
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

DIV = 480  # divisions per crotchet
TYPES = {"w": ("whole", 4), "h": ("half", 2), "q": ("quarter", 1), "e": ("eighth", 0.5),
         "s": ("16th", 0.25), "t": ("32nd", 0.125)}
STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
DYNAMIC_VELOCITY = {"pppp": 10, "ppp": 23, "pp": 36, "p": 49, "mp": 62, "mf": 75, "f": 88, "ff": 101,
                    "fff": 114, "ffff": 127}
MARKS = {  # name -> (group, xml)
    "stacc": ("articulations", "<staccato/>"),
    "staccis": ("articulations", "<staccatissimo/>"),
    "ten": ("articulations", "<tenuto/>"),
    "acc": ("articulations", "<accent/>"),
    "marc": ("articulations", '<strong-accent type="up"/>'),
    "port": ("articulations", "<detached-legato/>"),
    "breath": ("articulations", "<breath-mark/>"),
    "caesura": ("articulations", "<caesura/>"),
    "ferm": ("", '<fermata type="upright"/>'),
    "tr": ("ornaments", "<trill-mark/>"),
    "mord": ("ornaments", "<mordent/>"),
    "invmord": ("ornaments", "<inverted-mordent/>"),
    "turn": ("ornaments", "<turn/>"),
    "trem3": ("ornaments", '<tremolo type="single">3</tremolo>'),
    "upbow": ("technical", "<up-bow/>"),
    "harm": ("technical", "<harmonic/>"),
    "stopped": ("technical", "<stopped/>"),
    "snap": ("technical", "<snap-pizzicato/>"),
    "fall": ("articulations", "<falloff/>"),
    "doit": ("articulations", "<doit/>"),
    "scoop": ("articulations", "<scoop/>"),
    "plop": ("articulations", "<plop/>"),
    "shake": ("ornaments", "<shake/>"),
    # handled specially in note_xml (need a partner note or every chord note):
    "gliss": ("", ""), "slide": ("", ""), "arp": ("", ""),
    "downbow": ("technical", "<down-bow/>"),
}
INSTRUMENTS = {  # name -> (abbrev, GM program 1-based, instrument-sound, clef, transpose)
    "Violin": ("Vln.", 41, "strings.violin", ("G", 2), None),
    "Viola": ("Vla.", 42, "strings.viola", ("C", 3), None),
    "Cello": ("Vc.", 43, "strings.cello", ("F", 4), None),
    "Flute": ("Fl.", 74, "wind.flutes.flute", ("G", 2), None),
    "Oboe": ("Ob.", 69, "wind.reed.oboe", ("G", 2), None),
    "Trumpet in C": ("Tpt.", 57, "brass.trumpet", ("G", 2), None),
    "Horn in F": ("Hn.", 61, "brass.french-horn", ("G", 2), (-4, -7)),
    "Piano": ("Pno.", 1, "keyboard.piano", None, None),
    "Harp": ("Hp.", 47, "pluck.harp", None, None),
    "Harpsichord": ("Hpd.", 7, "keyboard.harpsichord", None, None),
    "Guitar": ("Gtr.", 25, "pluck.guitar.acoustic", ("G", 2), None),
    "Alto Sax": ("A. Sax.", 66, "wind.reed.saxophone.alto", ("G", 2), (-5, -9)),
    "Trombone": ("Tbn.", 58, "brass.trombone", ("F", 4), None),
    "Timpani": ("Timp.", 48, "drum.timpani", ("F", 4), None),
}


@dataclass
class Part:
    instrument: str
    staves: list[list[str]]  # one list of bar strings per stave (piano has 2)


@dataclass
class Piece:
    name: str
    title: str
    parts: list[Part]
    time: tuple[int, int] = (4, 4)
    key: int = 0  # fifths
    tempo: int = 100
    notes: str = ""


# ---------------------------------------------------------------------------
# Token parsing
# ---------------------------------------------------------------------------

def pitch_xml(p: str, transpose_chromatic: int = 0) -> str:
    step = p[0]
    rest = p[1:]
    alter = 0
    while rest and rest[0] in "#b":
        alter += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    octave = int(rest)
    # written pitch for transposing instruments (horn: written a 5th above)
    if transpose_chromatic:
        midi = 12 * (octave + 1) + STEPS[step] + alter + transpose_chromatic
        # respell simply with sharps/flats preserved where possible
        names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
        n = names[midi % 12]
        step, alter = n[0], (1 if "#" in n else -1 if "b" in n else 0)
        octave = midi // 12 - 1
    a = f"<alter>{alter}</alter>" if alter else ""
    return f"<pitch><step>{step}</step>{a}<octave>{octave}</octave></pitch>"


@dataclass
class Note:
    pitches: list[str] | None  # None = rest
    type: str
    dots: int
    tuplet: int  # 0 or 3
    marks: list[str]
    tie_start: bool = False
    tie_stop: bool = False
    gliss_stop: str = ""
    slur_start: bool = False
    slur_stop: bool = False
    grace: list[tuple[str, bool]] = field(default_factory=list)  # (pitch, slashed)
    directions: list[str] = field(default_factory=list)
    end_directions: list[str] = field(default_factory=list)

    @property
    def length(self) -> int:
        base = TYPES[self.type][1] * DIV
        total = base
        add = base
        for _ in range(self.dots):
            add /= 2
            total += add
        if self.tuplet:
            total = total * 2 / 3
        return int(round(total))


def parse_bar(text: str) -> list[Note]:
    notes: list[Note] = []
    pending_dirs: list[str] = []
    pending_grace: list[tuple[str, bool]] = []
    slur_next = False
    tokens = tokenize(text)
    for tok in tokens:
        if (tok.startswith("!") or tok in ("<", ">", "|", "Ped", "*") or tok.startswith('"') or tok.startswith("@")
                or tok.startswith("harp:")):
            pending_dirs.append(tok)
            continue
        if tok.startswith("grace:") or tok.startswith("app:"):
            kind, p = tok.split(":", 1)
            pending_grace.append((p, kind == "grace"))
            continue
        if tok == "(":
            slur_next = True
            continue
        slur_stop = tok.endswith(")")
        tok = tok.rstrip(")")
        if tok.startswith("("):
            slur_next = True
            tok = tok[1:]
        body, _, marks = tok.partition("/")
        p, _, dur = body.partition(":")
        tie = dur.endswith("~")
        dur = dur.rstrip("~")
        tuplet = 3 if dur.endswith("3") else 0
        dur = dur.rstrip("3")
        dots = len(dur) - len(dur.rstrip("."))
        dur = dur.rstrip(".")
        n = Note(None if p == "r" else p.split("+"), dur, dots, tuplet,
                 [m for m in marks.split(",") if m], tie_start=tie,
                 slur_start=slur_next, slur_stop=slur_stop, grace=pending_grace,
                 directions=pending_dirs)
        slur_next = False
        pending_dirs, pending_grace = [], []
        notes.append(n)
    if pending_dirs and notes:
        notes[-1].end_directions = pending_dirs
    return notes


def tokenize(text: str) -> list[str]:
    out, cur, quoted = [], "", False
    for ch in text:
        if ch == '"':
            cur += ch
            if quoted:
                out.append(cur)
                cur = ""
            quoted = not quoted
        elif ch.isspace() and not quoted:
            if cur:
                out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


# ---------------------------------------------------------------------------
# MusicXML writing
# ---------------------------------------------------------------------------

def direction_xml(tok: str, staff: int, tempo_hint: int | None = None) -> str:
    st = f"<staff>{staff}</staff>"
    if tok.startswith("!"):
        d = tok[1:]
        # Finale's default dynamic velocities. Human Playback takes the dynamic level from
        # the expression's playback value, which Finale's MusicXML import sets from
        # <sound dynamics> (a percentage of velocity 90). Without it HP ignores the level.
        vel = DYNAMIC_VELOCITY.get(d)
        sound = f'<sound dynamics="{vel / 90 * 100:.2f}"/>' if vel else ""
        return (f'<direction placement="below"><direction-type><dynamics><{d}/></dynamics>'
                f"</direction-type>{st}{sound}</direction>")
    if tok == "<":
        return f'<direction placement="below"><direction-type><wedge type="crescendo"/></direction-type>{st}</direction>'
    if tok == ">":
        return f'<direction placement="below"><direction-type><wedge type="diminuendo"/></direction-type>{st}</direction>'
    if tok == "|":
        return f'<direction placement="below"><direction-type><wedge type="stop"/></direction-type>{st}</direction>'
    if tok.startswith("@"):
        bpm = int(tok[1:])
        return (f'<direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit>'
                f"<per-minute>{bpm}</per-minute></metronome></direction-type>{st}"
                f'<sound tempo="{bpm}"/></direction>')
    if tok == "Ped":
        return f'<direction placement="below"><direction-type><pedal type="start" line="no"/></direction-type>{st}</direction>'
    if tok == "*":
        return f'<direction placement="below"><direction-type><pedal type="stop" line="no"/></direction-type>{st}</direction>'
    if tok.startswith("harp:"):
        tunings = []
        for p in tok[5:].split(","):
            alter = p.count("#") - p.count("b")
            tunings.append(f"<pedal-tuning><pedal-step>{p[0]}</pedal-step><pedal-alter>{alter}</pedal-alter></pedal-tuning>")
        return (f'<direction placement="below"><direction-type><harp-pedals>{"".join(tunings)}</harp-pedals>'
                f"</direction-type>{st}</direction>")
    if tok.startswith('"'):
        words = escape(tok.strip('"'))
        return (f'<direction placement="above"><direction-type><words font-style="italic">{words}</words>'
                f"</direction-type>{st}</direction>")
    raise ValueError(tok)


def note_xml(n: Note, voice: int, staff: int, transpose: int, open_tuplet: list[int]) -> str:
    out = []
    for gp, slashed in n.grace:
        g = '<grace slash="yes"/>' if slashed else "<grace/>"
        typ = "eighth" if slashed else "quarter"
        out.append(f"<note>{g}{pitch_xml(gp, transpose)}<voice>{voice}</voice><type>{typ}</type>"
                   f"<staff>{staff}</staff></note>")
    pitches = n.pitches or [None]
    for i, p in enumerate(pitches):
        x = ["<note>"]
        if i > 0:
            x.append("<chord/>")
        x.append("<rest/>" if p is None else pitch_xml(p, transpose))
        x.append(f"<duration>{n.length}</duration>")
        if n.tie_stop:
            x.append('<tie type="stop"/>')
        if n.tie_start:
            x.append('<tie type="start"/>')
        x.append(f"<voice>{voice}</voice><type>{TYPES[n.type][0]}</type>")
        x.append("<dot/>" * n.dots)
        if n.tuplet:
            x.append("<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes>"
                     "</time-modification>")
        x.append(f"<staff>{staff}</staff>")
        nots: list[str] = []
        if n.tie_stop:
            nots.append('<tied type="stop"/>')
        if n.tie_start:
            nots.append('<tied type="start"/>')
        if "arp" in n.marks and n.pitches:
            nots.append("<arpeggiate/>")
        if i == 0:
            if "gliss" in n.marks:
                nots.append('<glissando type="start" line-type="wavy"/>')
            if "slide" in n.marks:
                nots.append('<slide type="start" line-type="solid"/>')
            if n.gliss_stop == "gliss":
                nots.append('<glissando type="stop" line-type="wavy"/>')
            if n.gliss_stop == "slide":
                nots.append('<slide type="stop" line-type="solid"/>')
            if n.slur_start:
                nots.append('<slur type="start" number="1"/>')
            if n.slur_stop:
                nots.append('<slur type="stop" number="1"/>')
            if n.tuplet:
                if open_tuplet[0] == 0:
                    nots.append('<tuplet type="start" bracket="no"/>')
                open_tuplet[0] += 1
                if open_tuplet[0] == 3:
                    nots.append('<tuplet type="stop"/>')
                    open_tuplet[0] = 0
            groups: dict[str, list[str]] = {}
            for m in n.marks:
                grp, xml = MARKS[m]
                if not xml:
                    continue
                groups.setdefault(grp, []).append(xml)
            for grp, xs in groups.items():
                nots.append("".join(xs) if grp == "" else f"<{grp}>{''.join(xs)}</{grp}>")
        if nots:
            x.append(f"<notations>{''.join(nots)}</notations>")
        x.append("</note>")
        out.append("".join(x))
    return "".join(out)


def piece_xml(piece: Piece) -> str:
    beats, beat_type = piece.time
    bar_len = int(beats * 4 / beat_type * DIV)
    part_list, parts_xml = [], []
    for pi, part in enumerate(piece.parts, 1):
        abbr, prog, sound, clef, transp = INSTRUMENTS[part.instrument]
        pid = f"P{pi}"
        part_list.append(
            f'<score-part id="{pid}"><part-name>{escape(part.instrument)}</part-name>'
            f"<part-abbreviation>{escape(abbr)}</part-abbreviation>"
            f'<score-instrument id="{pid}-I1"><instrument-name>{escape(part.instrument)}</instrument-name>'
            f"<instrument-sound>{sound}</instrument-sound></score-instrument>"
            f'<midi-instrument id="{pid}-I1"><midi-channel>{pi}</midi-channel>'
            f"<midi-program>{prog}</midi-program></midi-instrument></score-part>")
        transpose = -transp[1] if transp else 0  # written = sounding - chromatic transposition
        bars_per_staff = [[parse_bar(b) for b in st] for st in part.staves]
        nbars = len(bars_per_staff[0])
        assert all(len(s) == nbars for s in bars_per_staff), piece.name
        # carry ties across bars
        for st in bars_per_staff:
            prev = None
            for bar in st:
                for n in bar:
                    if prev is not None and prev.tie_start:
                        n.tie_stop = True
                    if prev is not None and ("gliss" in prev.marks or "slide" in prev.marks):
                        n.gliss_stop = "gliss" if "gliss" in prev.marks else "slide"
                    prev = n
        measures = []
        for bi in range(nbars):
            m = [f'<measure number="{bi + 1}">']
            if bi == 0:
                nst = len(part.staves)
                fifths = piece.key
                if transp:  # written key = concert key moved by the transposition
                    fifths = (piece.key + (-transp[1] * 7) % 12 + 6) % 12 - 6
                attrs = [f"<divisions>{DIV}</divisions><key><fifths>{fifths}</fifths></key>"
                         f"<time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>"]
                if nst > 1:
                    attrs.append(f"<staves>{nst}</staves>")
                if clef is None:
                    attrs.append('<clef number="1"><sign>G</sign><line>2</line></clef>'
                                 '<clef number="2"><sign>F</sign><line>4</line></clef>')
                else:
                    attrs.append(f"<clef><sign>{clef[0]}</sign><line>{clef[1]}</line></clef>")
                if transp:
                    attrs.append(f"<transpose><diatonic>{transp[0]}</diatonic>"
                                 f"<chromatic>{transp[1]}</chromatic></transpose>")
                m.append(f"<attributes>{''.join(attrs)}</attributes>")
                if pi == 1:
                    m.append(direction_xml(f"@{piece.tempo}", 1))
            for si, st in enumerate(bars_per_staff):
                if si > 0:
                    m.append(f"<backup><duration>{bar_len}</duration></backup>")
                total = 0
                open_tuplet = [0]
                for n in st[bi]:
                    for d in n.directions:
                        m.append(direction_xml(d, si + 1))
                    m.append(note_xml(n, si + 1 if si else 1, si + 1, transpose, open_tuplet))
                    for d in n.end_directions:
                        m.append(direction_xml(d, si + 1))
                    total += n.length
                if total != bar_len:
                    raise ValueError(f"{piece.name} {part.instrument} stave {si + 1} bar {bi + 1}: "
                                     f"{total / DIV} crotchets, expected {bar_len / DIV}")
            if bi == nbars - 1:
                m.append('<barline location="right"><bar-style>light-heavy</bar-style></barline>')
            m.append("</measure>")
            measures.append("".join(m))
        parts_xml.append(f'<part id="{pid}">{"".join(measures)}</part>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
            '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" '
            '"http://www.musicxml.org/dtds/partwise.dtd">\n'
            '<score-partwise version="3.1">'
            f"<work><work-title>{escape(piece.title)}</work-title></work>"
            "<identification><encoding><software>dorico-hp make_test_pieces.py</software></encoding></identification>"
            f"<part-list>{''.join(part_list)}</part-list>{''.join(parts_xml)}</score-partwise>\n")


# ---------------------------------------------------------------------------
# The test pieces
# ---------------------------------------------------------------------------

def rep(bar: str, n: int) -> list[str]:
    return [bar] * n


def mono(name, title, instrument, bars, **kw) -> Piece:
    return Piece(name, title, [Part(instrument, [bars])], **kw)


def pieces() -> list[Piece]:
    P: list[Piece] = []
    Q4 = "A4:q A4:q A4:q A4:q"
    E8 = " ".join(["A4:e"] * 8)

    # 01 Baseline: unmarked repeated notes. Shows metric accents, timing feel, randomness.
    base = ["!mf " + Q4] + rep(Q4, 7) + rep(E8, 4) + ["A4:w"]
    for inst, note in (("Violin", "A4"), ("Flute", "A5"), ("Trumpet in C", "A4"), ("Piano", "A4")):
        bars = [b.replace("A4", note) for b in base]
        if inst == "Piano":
            P.append(Piece(f"01-baseline-{slug(inst)}", f"01 Baseline ({inst})",
                           [Part(inst, [bars, rep("r:w", len(bars))])]))
        else:
            P.append(mono(f"01-baseline-{slug(inst)}", f"01 Baseline ({inst})", inst, bars))

    # 02 Note lengths on one pitch.
    P.append(mono("02-lengths-violin", "02 Note lengths", "Violin", [
        "!mf A4:w", "A4:h A4:h", Q4, E8, " ".join(["A4:s"] * 16), "A4:h. A4:q",
        "A4:q. A4:e A4:q. A4:e", "A4:w~", "A4:w", "A4:h r:h", "A4:w"]))

    # 03 Articulations: one articulation per bar, crotchets then quavers.
    arts = ["", "stacc", "staccis", "ten", "acc", "marc", "port", "acc,stacc", "ten,acc"]
    for inst, note in (("Violin", "A4"), ("Trumpet in C", "G4"), ("Flute", "A5")):
        bars = []
        for i, a in enumerate(arts):
            mark = f"/{a}" if a else ""
            bars.append(("!mf " if i == 0 else "") + " ".join([f"{note}:q{mark}"] * 4))
        for a in ("", "stacc", "acc", "ten"):
            mark = f"/{a}" if a else ""
            bars.append(" ".join([f"{note}:e{mark}"] * 8))
        bars.append(f"{note}:w")
        P.append(mono(f"03-articulations-{slug(inst)}", f"03 Articulations ({inst})", inst, bars,
                      notes="bars 1-9: none, stacc, staccatissimo, tenuto, accent, marcato, "
                            "portato, accent+stacc, tenuto+accent; bars 10-13 quavers: none, stacc, accent, tenuto"))

    # 04 Slurs on a scale.
    up = ["C5", "D5", "E5", "F5", "G5", "A5", "B5", "C6"]
    dn = list(reversed(up))
    def scale(ps, d="e"):
        return [f"{p}:{d}" for p in ps]
    def slurred(ns, size):
        out = []
        for i, n in enumerate(ns):
            s = ("(" if i % size == 0 else "") + n + (")" if i % size == size - 1 else "")
            out.append(s)
        return " ".join(out)
    for inst, shift in (("Violin", 0), ("Flute", 0), ("Cello", -24)):
        def sh(ps):
            return [transpose_name(p, shift) for p in ps]
        bars = [
            "!mf " + " ".join(scale(sh(up))), " ".join(scale(sh(dn))),
            slurred(scale(sh(up)), 2), slurred(scale(sh(dn)), 2),
            slurred(scale(sh(up)), 4), slurred(scale(sh(dn)), 4),
            slurred(scale(sh(up)), 8), slurred(scale(sh(dn)), 8),
            " ".join(scale(sh(up[:4]), "q")), " ".join(scale(sh(dn[:4]), "q")),
            slurred(scale(sh(up[:4]), "q"), 4), slurred(scale(sh(dn[:4]), "q"), 4),
            f"({sh(['C5'])[0]}:h {sh(['G5'])[0]}:h", f"{sh(['E5'])[0]}:h {sh(['C5'])[0]}:h)",
            f"{sh(['C5'])[0]}:w",
        ]
        P.append(mono(f"04-slurs-{slug(inst)}", f"04 Slurs ({inst})", inst, bars,
                      notes="pairs of bars: unslurred, 2-note, 4-note, 8-note slurs; crotchets unslurred/slurred; long slur"))

    # 05 Dynamics ladder.
    levels = ["ppp", "pp", "p", "mp", "mf", "f", "ff", "fff"]
    for inst, note in (("Violin", "A4"), ("Piano", "A4"), ("Trumpet in C", "G4")):
        bars = [f"!{lv} {note}:h {note}:q {note}:q" for lv in levels]
        bars += [f"!mf {note}:q !sfz {note}:q !mf {note}:q {note}:q", f"!fp {note}:w", f"!sfp {note}:w", f"!mf {note}:w"]
        staves = [bars] if inst != "Piano" else [bars, rep("r:w", len(bars))]
        P.append(Piece(f"05-dynamics-{slug(inst)}", f"05 Dynamics ({inst})", [Part(inst, staves)]))

    # 06 Hairpins.
    for inst, note in (("Violin", "A4"), ("Flute", "A5"), ("Piano", "A4"), ("Horn in F", "F4")):
        n = note
        bars = [
            f"!p < {n}:q {n}:q {n}:q {n}:q", f"{n}:q {n}:q {n}:q {n}:q", f"| !f {n}:q {n}:q {n}:q {n}:q",
            f"> {n}:q {n}:q {n}:q {n}:q", f"{n}:q {n}:q {n}:q {n}:q", f"| !p {n}:w",
            # single long note swell (messa di voce) over tied whole notes
            f"!p < {n}:w~", f"| > {n}:w~", f"{n}:w", f"| r:w",
            # one-bar crescendo with no target dynamic, then nothing
            f"!mp < {n}:q {n}:q {n}:q {n}:q |", f"{n}:q {n}:q {n}:q {n}:q",
            # long hairpin over minims
            f"!pp < {n}:h {n}:h", f"{n}:h {n}:h", f"{n}:h {n}:h", f"{n}:h {n}:h", f"| !ff {n}:w",
            # short hairpin on one note
            f"!mf {n}:q < {n}:h {n}:q |", f"!mf > {n}:h | {n}:h", f"{n}:w",
        ]
        staves = [bars] if inst != "Piano" else [bars, rep("r:w", len(bars))]
        P.append(Piece(f"06-hairpins-{slug(inst)}", f"06 Hairpins ({inst})", [Part(inst, staves)]))

    # 07 Tempo: rit., a tempo, accel., fermatas, breaths, final bar.
    P.append(mono("07-tempo-violin", "07 Tempo changes", "Violin", [
        "!mf " + Q4, Q4, '"rit." ' + Q4, Q4, '"a tempo" ' + Q4, Q4, '"accel." ' + Q4, Q4,
        '"a tempo" ' + Q4, "A4:q A4:q A4:h/ferm", Q4, "A4:q A4:q r:h/ferm", Q4,
        "A4:q A4:q A4:q/breath A4:q", "A4:q A4:q A4:q/caesura A4:q", '"poco rit." ' + Q4, Q4,
        '"a tempo" ' + Q4, '"rall." ' + Q4, "A4:w/ferm"]))

    # 08 Ornaments.
    for inst in ("Violin", "Flute"):
        P.append(mono(f"08-ornaments-{slug(inst)}", f"08 Ornaments ({inst})", inst, [
            "!mf A4:w/tr", "A4:h/tr A4:h", "E5:w/tr", "B4:h/tr C5:h", "A4:q/mord A4:q A4:q/mord A4:q",
            "A4:q/invmord A4:q A4:q/invmord A4:q", "A4:h/turn A4:h", "grace:B4 A4:q A4:q grace:B4 A4:q A4:q",
            "app:B4 A4:h app:B4 A4:h", "grace:G4 grace:B4 A4:q A4:q A4:h", "A4:w/trem3", "A4:h/trem3 A4:h",
            "D5:q C5:q B4:q A4:q", "A4:w"]))

    # 09 Rhythms: dotted, triplets, syncopation, off-beats.
    P.append(mono("09-rhythms-violin", "09 Rhythms", "Violin", [
        "!mf A4:e. A4:s A4:e. A4:s A4:e. A4:s A4:e. A4:s", "A4:e. A4:s A4:e. A4:s A4:e. A4:s A4:e. A4:s",
        "A4:e3 A4:e3 A4:e3 A4:e3 A4:e3 A4:e3 A4:e3 A4:e3 A4:e3 A4:e3 A4:e3 A4:e3",
        "A4:q3 A4:q3 A4:q3 A4:q3 A4:q3 A4:q3",
        "A4:e A4:q A4:q A4:q A4:e", "A4:e A4:q A4:q A4:q A4:e",
        "r:e A4:e r:e A4:e r:e A4:e r:e A4:e", "r:e A4:e r:e A4:e r:e A4:e r:e A4:e",
        "A4:q. A4:e A4:q. A4:e", "A4:s A4:s A4:e A4:s A4:s A4:e A4:q A4:q", E8, E8, "A4:w"]))

    # 10 Triple and compound metre.
    waltz_lh = "D3:q D4+F#4+A4:q D4+F#4+A4:q"
    waltz_rh = ["!mf F#5:h. ", "A5:h G5:q", "F#5:h E5:q", "D5:h.", "E5:h F#5:q", "G5:h E5:q", "D5:h C#5:q", "D5:h."]
    P.append(Piece("10-waltz-piano", "10 Waltz (piano)", [Part("Piano", [
        waltz_rh, ["!mf " + waltz_lh] + rep(waltz_lh, 3) + ["A2:q C#4+E4+G4:q C#4+E4+G4:q"] * 3 + [waltz_lh]])],
        time=(3, 4), key=2, tempo=150))
    P.append(mono("10-triple-violin", "10 Triple metre", "Violin",
                  ["!mf A4:q A4:q A4:q"] + rep("A4:q A4:q A4:q", 7) + rep("A4:e A4:e A4:e A4:e A4:e A4:e", 4) + ["A4:h."],
                  time=(3, 4)))
    P.append(mono("10-compound-violin", "10 Compound metre", "Violin",
                  ["!mf A4:e A4:e A4:e A4:e A4:e A4:e"] + rep("A4:e A4:e A4:e A4:e A4:e A4:e", 5)
                  + rep("A4:q A4:e A4:q A4:e", 3) + ["A4:h."], time=(6, 8)))

    # 11 Real melodies (public domain): phrase shape, cadences, final bars.
    ode = ["!mf F#5:q F#5:q G5:q A5:q", "A5:q G5:q F#5:q E5:q", "D5:q D5:q E5:q F#5:q", "F#5:q. E5:e E5:h",
           "F#5:q F#5:q G5:q A5:q", "A5:q G5:q F#5:q E5:q", "D5:q D5:q E5:q F#5:q", "E5:q. D5:e D5:h",
           "E5:q E5:q F#5:q D5:q", "E5:q (F#5:e G5:e) F#5:q D5:q", "E5:q (F#5:e G5:e) F#5:q E5:q", "D5:q E5:q A4:h",
           "F#5:q F#5:q G5:q A5:q", "A5:q G5:q F#5:q E5:q", "D5:q D5:q E5:q F#5:q", "E5:q. D5:e D5:h"]
    grace = ["!p C5:q", "(F5:h A5:e F5:e)", "A5:h G5:q", "F5:h D5:q", "C5:h C5:q", "(F5:h A5:e F5:e)", "A5:h G5:q",
             "C6:h.~", "C6:h A5:q", "(C6:q. A5:e C6:e A5:e)", "F5:h C5:q", "D5:q. F5:e F5:e D5:e", "C5:h C5:q",
             "(F5:h A5:e F5:e)", "A5:h G5:q", "F5:h.~", "F5:h r:q"]
    for inst, shift in (("Violin", 0), ("Flute", 0), ("Trumpet in C", -12), ("Cello", -24), ("Oboe", 0)):
        P.append(mono(f"11-ode-{slug(inst)}", f"11 Ode to Joy ({inst})", inst,
                      [transpose_bar(b, shift) for b in ode], key=2, tempo=100))
    for inst, shift in (("Violin", 0), ("Cello", -24), ("Flute", 0)):
        P.append(Piece(f"11-amazing-grace-{slug(inst)}", f"11 Amazing Grace ({inst})",
                       [Part(inst, [[transpose_bar(b, shift) for b in pickup_free(grace)]])],
                       time=(3, 4), key=-1, tempo=72))

    # 12 Piano textures: Alberti bass, chords, bass octaves.
    alberti = "C4:e G4:e E4:e G4:e C4:e G4:e E4:e G4:e"
    P.append(Piece("12-piano-textures", "12 Piano textures", [Part("Piano", [
        ["!mf C5:h E5:q G5:q", "B4:q. C5:s D5:s C5:h", "A5:h G5:q C6:q", "G5:q F5:e E5:e F5:h",
         "!mf E5+G5+C6:q D5+F5+B5:q C5+E5+A5:q B4+D5+G5:q", "C5+E5+A5:h B4+D5+G5:h", "A4+C5+F5:q G4+B4+E5:q F4+A4+D5:q G4+B4+D5:q",
         "E4+G4+C5:w"],
        ["!mf " + alberti, "D4:e G4:e F4:e G4:e C4:e G4:e E4:e G4:e", "C4:e A4:e F4:e A4:e C4:e G4:e E4:e G4:e",
         "B3:e G4:e D4:e G4:e C4:e G4:e E4:e G4:e",
         "C3+C4:q G2+G3:q A2+A3:q E2+E3:q", "F2+F3:h G2+G3:h", "D2+D3:q E2+E3:q F2+F3:q G2+G3:q", "C2+C3:w"]])]))

    # 13 Solo against accompaniment.
    acc_v = ["!p A4:h A4:h", "A4:h A4:h", "B4:h B4:h", "A4:h A4:h"] * 2
    acc_va = ["!p F#4:h F#4:h", "E4:h E4:h", "D4:h D4:h", "C#4:h C#4:h"] * 2
    acc_vc = ["!p D3:h D3:h", "C#3:h C#3:h", "B2:h B2:h", "A2:h A2:h"] * 2
    P.append(Piece("13-solo-accompaniment", "13 Solo with accompaniment", [
        Part("Flute", [[b.replace("!mf", "!mf") for b in ode[:8]]]),
        Part("Violin", [acc_v]), Part("Viola", [acc_va]), Part("Cello", [acc_vc])], key=2))

    # 14 Long notes (for vibrato and long-note expression).
    for inst, n in (("Violin", "D5"), ("Cello", "D3"), ("Flute", "D5"), ("Oboe", "D5")):
        P.append(mono(f"14-long-notes-{slug(inst)}", f"14 Long notes ({inst})", inst, [
            f"!p {n}:w", f"{n}:h {n}:h", f"{n}:h. {n}:q", f"{n}:w~", f"{n}:w", f"!mf {n}:w", f"{n}:h {n}:h",
            f"{n}:w~", f"{n}:w", f"!f {n}:w", f"{n}:h {n}:h", f"!mf ({n}:h {transpose_name(n, 2)}:h",
            f"{transpose_name(n, 4)}:h {transpose_name(n, 2)}:h)", f"{n}:q {n}:q {n}:h", f"!p {n}:w~", f"{n}:w"]))

    # 15 Techniques and glissando text.
    P.append(mono("15-techniques-violin", "15 Techniques", "Violin", [
        "!mf " + Q4, '"pizz." ' + Q4, Q4, '"arco" ' + Q4, '"con sord." ' + Q4, Q4, '"senza sord." ' + Q4,
        '"sul pont." A4:w', '"ord." A4:w', '"trem." A4:w/trem3', "A4:w"]))

    # ---- batch 2 -----------------------------------------------------------
    rests = lambda n: rep("r:w", n)

    # 16 Glissandi: harp (with pedal settings), strings, trombone, piano.
    harp_rh = [
        "harp:D,C,B,E,F,G,A !mf C4:h/gliss C6:h", "C6:h/gliss C4:h",
        "harp:D,C,Bb,Eb,F,G,Ab Eb4:h/gliss Eb6:h", "Eb6:h/gliss Eb4:h",
        "harp:D,C#,B,E,F#,G,A D4:q/gliss D5:q D5:q/gliss D4:q", "D4:w/gliss", "D6:w",
        "harp:D,C#,Bb,E,F#,G#,A# !p C4:h/gliss C6:h", "!f C6:h/gliss C4:h", "C4:w"]
    P.append(Piece("16-gliss-harp", "16 Glissandi (harp)", [Part("Harp", [harp_rh, rests(len(harp_rh))])]))
    P.append(mono("16-gliss-violin", "16 Glissandi (violin)", "Violin", [
        "!mf A4:h/gliss E5:h", "E5:h/slide A4:h", "D4:q/gliss D5:q r:h", "A5:h/gliss A4:h",
        "(E5:q/gliss A5:q) A5:h", "A4:w/gliss", "A5:w", "A4:w"]))
    P.append(mono("16-gliss-trombone", "16 Glissandi (trombone)", "Trombone", [
        "!mf Bb2:h/gliss F3:h", "F3:h/gliss Bb2:h", "D3:q/slide F3:q r:h", "Bb2:w/gliss", "F3:w", "Bb2:w"]))
    P.append(Piece("16-gliss-piano", "16 Glissandi (piano)", [Part("Piano", [
        ["!mf C4:h/gliss C6:h", "C6:h/gliss C4:h", "C4:w/gliss", "C7:w", "C5:w"], rests(5)])]))

    # 17 Chords: strummed / arpeggiated.
    rh_ch = ["!mf C4+E4+G4+C5:q C4+E4+G4+C5:q F4+A4+C5+F5:h", "G4+B4+D5+G5:h C4+E4+G4+C5:h",
             "C4+E4+G4+C5:h/arp F4+A4+C5+F5:h/arp", "G4+B4+D5+G5:q/arp G4+B4+D5+G5:q C4+E4+G4+C5:h", "C4+E4+G4+C5:w"]
    lh_ch = ["!mf C3+G3:q C3+G3:q F2+C3:h", "G2+D3:h C3+G3:h", "C3+G3:h/arp F2+C3:h/arp",
             "G2+D3:q/arp G2+D3:q C3+G3:h", "C3+G3:w"]
    for inst in ("Harp", "Harpsichord", "Piano"):
        P.append(Piece(f"17-chords-{slug(inst)}", f"17 Chords ({inst})", [Part(inst, [rh_ch, lh_ch])]))
    P.append(mono("17-chords-guitar", "17 Chords (guitar)", "Guitar", [
        "!mf E4+G4+C5:q E4+G4+C5:q F4+A4+C5:h", "D4+G4+B4:h E4+G4+C5:h", "E4+G4+C5:h/arp F4+A4+C5:h/arp",
        "D4+G4+B4:q/arp D4+G4+B4:q E4+G4+C5:h", "E4+G4+C5:w"]))

    # 18 Piano pedalling: marked, then the same music unmarked (automatic pedalling).
    rh_ped = ["!p E5:q G5:q C6:q G5:q", "F5:q A5:q C6:q A5:q", "D5:q G5:q B5:q G5:q", "E5:h C5:h"]
    lh_ped = ["C3:w", "F2:w", "G2:w", "C3:w"]
    P.append(Piece("18-pedal-piano", "18 Pedalling (piano)", [Part("Piano", [
        rh_ped + rh_ped + ["C5:w"],
        ["Ped " + b + " *" for b in lh_ped] + lh_ped + ["C2:w"]])]))

    # 19 Jazz: swing, syncopation, falls, doits, scoops, shakes.
    jazz = ['"Swing" !mf F4:e G4:e A4:e Bb4:e C5:e D5:e C5:e A4:e', "Bb4:q/acc r:e F4:e A4:e/acc G4:e r:q",
            "F4:e G4:e A4:e C5:e/acc r:e Bb4:e r:q", "Bb4:h/fall r:h", "r:e D5:e/acc r:e C5:e r:e Bb4:e/acc r:q",
            "Bb4:h/doit r:h", "F5:h/shake F5:q/stacc r:q", "r:q D5:q/scoop C5:q Bb4:q",
            "D5:e/acc D5:e D5:e C5:e/stacc r:e Bb4:q.", "Bb4:w"]
    for inst in ("Alto Sax", "Trumpet in C"):
        P.append(mono(f"19-jazz-{slug(inst)}", f"19 Jazz ({inst})", inst, jazz, key=-2, tempo=140))

    # 20 Timpani: rolls, single strokes, roll with crescendo, fp roll.
    P.append(mono("20-timpani", "20 Timpani", "Timpani", [
        "!p A2:w/trem3", "< A2:w/trem3", "| !f A2:q D3:q A2:q D3:q", "A2:h/trem3 D3:h/trem3",
        "!mf A2:e A2:e D3:e D3:e A2:q D3:q", "!fp A2:w/trem3", "!p > A2:w/trem3", "| A2:w"]))

    # 21 Harmonics: violin and harp.
    P.append(mono("21-harmonics-violin", "21 Harmonics (violin)", "Violin", [
        "!mf A5:h/harm A5:h", "E6:q/harm E6:q/harm A5:h", "A5:w/harm", "A4:w"]))
    P.append(Piece("21-harmonics-harp", "21 Harmonics (harp)", [Part("Harp", [
        ["!mf C5:q/harm G5:q/harm C5:h", "E5:h/harm C5:h", "C5:w"], rests(3)])]))

    # 22 Chorale in four string parts: half cadence (bar 4), perfect cadence (bar 8).
    sop = ["!mf E5:q E5:q F5:q G5:q", "G5:q F5:q E5:q D5:q", "C5:q C5:q D5:q E5:q", "E5:q. D5:e D5:h/ferm"]
    alt = ["!mf C5:q C5:q C5:q B4:q", "B4:q C5:q C5:q B4:q", "G4:q G4:q B4:q C5:q", "C5:q. B4:e B4:h/ferm"]
    ten = ["!mf G4:q G4:q A4:q D4:q", "D4:q A4:q G4:q G4:q", "E4:q E4:q G4:q G4:q", "G4:q. G4:e G4:h/ferm"]
    bas = ["!mf C3:q C3:q F3:q G3:q", "G3:q F3:q C3:q G3:q", "C3:q C3:q G2:q C3:q", "C3:q. G2:e G2:h/ferm"]
    P.append(Piece("22-chorale-strings", "22 Chorale (strings)", [
        Part("Violin", [sop + [b.replace("!mf ", "") for b in sop[:3]] + ["D5:q. C5:e C5:h/ferm"]]),
        Part("Violin", [alt + [b.replace("!mf ", "") for b in alt[:3]] + ["B4:q. G4:e G4:h/ferm"]]),
        Part("Viola", [ten + [b.replace("!mf ", "") for b in ten[:3]] + ["G4:q. E4:e E4:h/ferm"]]),
        Part("Cello", [bas + [b.replace("!mf ", "") for b in bas[:3]] + ["G2:q. C3:e C3:h/ferm"]])]))

    # 23 Brass techniques and HP control words.
    Q4G = "G4:q G4:q G4:q G4:q"
    P.append(mono("23-techniques-trumpet", "23 Techniques (trumpet)", "Trumpet in C", [
        "!mf " + Q4G, '"con sord." ' + Q4G, '"open" ' + Q4G, '"cup mute" ' + Q4G, '"harmon mute" ' + Q4G,
        '"open" ' + Q4G, '"flz." G4:w', '"ord." G4:w', '"solo" ' + Q4G, '"tutti" ' + Q4G,
        '"hpoff" ' + Q4G, '"hpon" ' + Q4G, "G4:w"]))
    P.append(mono("23-techniques-horn", "23 Techniques (horn)", "Horn in F", [
        "!mf F4:q F4:q F4:q F4:q", "F4:q/stopped F4:q/stopped F4:q F4:q", '"stopped" F4:w', '"open" F4:w',
        '"con sord." F4:q F4:q F4:q F4:q', '"senza sord." F4:w', "F4:w"]))
    P.append(mono("23-techniques-strings", "23 Techniques (violin)", "Violin", [
        "!mf " + Q4, '"col legno" ' + Q4, '"ord." ' + Q4, "A4:q/snap A4:q/snap A4:h", '"sul tasto" A4:w',
        '"ord." A4:w', '"spicc." ' + E8, '"ord." ' + E8, "A4:w"]))

    # 24 Dynamics written as words, and sudden changes.
    P.append(mono("24-dynamic-words-violin", "24 Dynamic words", "Violin", [
        '!p "cresc." ' + Q4, Q4, "!f " + Q4, '"dim." ' + Q4, Q4, "!p " + Q4,
        '"poco a poco cresc." ' + Q4, Q4, Q4, Q4, "!ff A4:w", '"subito p" ' + Q4, '"molto dim." ' + Q4, Q4,
        "!pp A4:w", "!mf A4:q !sfz A4:q !p A4:h", "!fp A4:w", "A4:w"]))
    return P


def slug(s: str) -> str:
    return s.lower().replace(" in ", "-").replace(" ", "-")


NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def midi_of(p: str) -> int:
    step, rest, alter = p[0], p[1:], 0
    while rest and rest[0] in "#b":
        alter += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    return 12 * (int(rest) + 1) + STEPS[step] + alter


def transpose_name(p: str, semis: int) -> str:
    if not semis:
        return p
    if semis % 12 == 0:  # octave shifts keep the spelling
        step, rest = p[0], p[1:]
        acc = "".join(c for c in rest if c in "#b")
        octave = int(rest.lstrip("#b"))
        return f"{step}{acc}{octave + semis // 12}"
    m = midi_of(p) + semis
    return f"{NAMES[m % 12]}{m // 12 - 1}"


def transpose_bar(bar: str, semis: int) -> str:
    out = []
    for tok in tokenize(bar):
        if tok[0] in "(ABCDEFG" and ":" in tok:
            pre = "(" if tok.startswith("(") else ""
            body = tok[len(pre):]
            p, _, rest = body.partition(":")
            out.append(pre + "+".join(transpose_name(x, semis) for x in p.split("+")) + ":" + rest)
        else:
            out.append(tok)
    return " ".join(out)


def pickup_free(bars: list[str]) -> list[str]:
    """Amazing Grace is written here without its pickup: the first bar is padded with rests."""
    first = bars[0].replace("C5:q", "r:h C5:q")
    return [first] + bars[1:]


def expected_notes(piece: Piece) -> list[dict]:
    """The written notes, one entry per sounding note (tied chains merged), per part/stave.

    Positions and durations are in crotchets from the start; pitch is sounding MIDI.
    Each note carries its marks, slur state, the dynamic and hairpin in force, and
    any text direction seen since the previous note.
    """
    beats, beat_type = piece.time
    bar_len = beats * 4 / beat_type
    out = []
    for pi, part in enumerate(piece.parts):
        for si, st in enumerate(part.staves):
            pos, notes, chain = 0.0, [], {}
            dyn, wedge, in_slur, words = None, None, False, []
            for bi, bar_text in enumerate(st):
                bar_start = bi * bar_len
                pos = bar_start
                bar = parse_bar(bar_text)
                for n in bar:
                    for d in n.directions:
                        if d.startswith("!"):
                            dyn = d[1:]
                        elif d in ("<", ">"):
                            wedge = "cresc" if d == "<" else "dim"
                        elif d == "|":
                            wedge = None
                        elif d.startswith('"'):
                            words.append(d.strip('"'))
                        elif d in ("Ped", "*") or d.startswith("harp:"):
                            words.append(d)
                    for gi, (gp, slashed) in enumerate(n.grace):
                        notes.append(dict(part=pi, stave=si, instrument=part.instrument, bar=bi + 1,
                                          beat=round(pos - bar_start, 6), pos=round(pos, 6), dur=0.0,
                                          pitch=midi_of(gp), grace="acciaccatura" if slashed else "appoggiatura",
                                          marks=[], dyn=dyn, wedge=wedge, slur=False, words=[]))
                    length = n.length / DIV
                    slur_state = "start" if n.slur_start else "end" if n.slur_stop else ("in" if in_slur else "")
                    if n.slur_start:
                        in_slur = True
                    for p in n.pitches or []:
                        midi = midi_of(p)
                        if midi in chain:  # continues a tie from the previous note
                            chain[midi]["dur"] = round(chain[midi]["dur"] + length, 6)
                            if not n.tie_start:
                                chain.pop(midi)
                            continue
                        e = dict(part=pi, stave=si, instrument=part.instrument, bar=bi + 1,
                                 beat=round(pos - bar_start, 6), pos=round(pos, 6), dur=round(length, 6),
                                 pitch=midi, grace="", marks=list(n.marks), dyn=dyn, wedge=wedge,
                                 slur=slur_state, words=list(words), chord=len(n.pitches) > 1,
                                 tuplet=bool(n.tuplet))
                        notes.append(e)
                        if n.tie_start:
                            chain[midi] = e
                    if n.pitches:
                        words = []
                    if n.slur_stop:
                        in_slur = False
                    for d in n.end_directions:
                        if d == "|":
                            wedge = None
                        elif d in ("<", ">"):
                            wedge = "cresc" if d == "<" else "dim"
                    pos += length
            out.extend(notes)
    return out


def main(out: Path) -> None:
    import json
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for p in pieces():
        (out / f"{p.name}.musicxml").write_text(piece_xml(p), encoding="utf-8")
        meta = dict(name=p.name, title=p.title, time=p.time, tempo=p.tempo, key=p.key,
                    parts=[pt.instrument for pt in p.parts], notes=expected_notes(p))
        (out / f"{p.name}.expected.json").write_text(json.dumps(meta, indent=0), encoding="utf-8")
        index.append(f"{p.name}\t{p.title}\t{p.notes}")
    (out / "INDEX.tsv").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"wrote {len(index)} pieces to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "test-pieces"))
