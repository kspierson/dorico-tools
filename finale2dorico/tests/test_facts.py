"""Unit tests for f2d/finale/facts.py (facts JSON -> IR). No C++ extractor needed."""
from __future__ import annotations

import sys
import unittest
from fractions import Fraction as F
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from f2d.finale.facts import FactsReader  # noqa: E402


def ts(count="4", unit="1"):
    return {"components": [{"counts": [count], "units": [unit]}], "abbreviation": ""}


def measure(mid, pos, dur="4", spacer="0", fifths=0, time=None):
    t = time or ts()
    return {"id": mid, "pos": pos, "duration": dur, "time": t, "display_time": t,
            "display_duration": dur, "legacy_pickup_spacer": spacer,
            "key": {"fifths": fifths, "mode": 0, "linear": True, "keyless": False}}


def entry(n, meas, pos, dur="1", notes=(), **kw):
    e = {"n": n, "measure": meas, "layer": 1, "voice": 1, "pos": pos, "dur": dur, "notated": dur,
         "grace": False, "hidden": False, "rest": not notes, "notes": list(notes)}
    e.update(kw)
    return e


def note(midi, step, alter=0, **kw):
    d = {"midi": midi, "step": step, "alter": alter, "tie": False, "tie_end": False}
    d.update(kw)
    return d


def facts(measures, entries, kind="enigmaxml", instruments=None, clef_changes=(), tuplets=()):
    return {
        "format": "f2d-facts", "version": 1, "kind": kind, "source": "test",
        "info": {"title": "T"},
        "clefs": [{"index": 0, "type": "G", "octave": 0, "middle_c": -10, "char": 38},
                  {"index": 1, "type": "C", "octave": 0, "middle_c": -4, "char": 66}],
        "measures": measures,
        "instruments": instruments or [{"staves": [1], "name": "Flute", "uuid": "", "transposition_type": "none"}],
        "staves": [{"id": 1, "default_clef": 0,
                    "default_clef_info": {"index": 0, "type": "G", "octave": 0, "middle_c": -10},
                    "clef_changes": list(clef_changes), "entries": entries, "tuplets": list(tuplets)}],
        "expressions": [], "smart_shapes": [], "warnings": [],
    }


class FactsTests(unittest.TestCase):
    def test_legacy_pickup_spacer_shortens_bar_one(self):
        f = facts([measure(1, "0", spacer="7/2"), measure(2, "4")],
                  [entry(1, 1, "7/2", "1/2", [note(71, "B")]), entry(2, 2, "4", "4", [note(72, "C")])])
        s = FactsReader(f).read()
        flow = s.flows[0]
        self.assertEqual(flow.pickup, F(1, 2))
        self.assertEqual(flow.bar_starts, [F(0), F(1, 2)])
        self.assertEqual(flow.length, F(9, 2))
        chords = flow.staves[0].voices[0].chords
        self.assertEqual([c.pos for c in chords], [F(0), F(1, 2)])

    def test_compound_time_signature(self):
        f = facts([measure(1, "0", dur="3", time=ts("2", "3/2"))], [])
        sig = FactsReader(f).read().flows[0].time_signatures[0]
        self.assertEqual((sig.num, sig.den), (6, 8))

    def test_mid_bar_clef_snaps_to_next_entry(self):
        f = facts([measure(1, "0")],
                  [entry(1, 1, "0", "1/2", [note(65, "F")]), entry(2, 1, "1/2", "1/2", [note(67, "G")])],
                  clef_changes=[{"pos": "119/512", "index": 1, "type": "C", "octave": 0, "middle_c": -4}])
        clefs = FactsReader(f).read().flows[0].staves[0].clefs
        self.assertEqual([(c.pos, c.clef) for c in clefs], [(F(0), "clef.treble"), (F(1, 2), "clef.alto")])

    def test_legacy_courtesy_accidental_frozen_only_when_not_needed(self):
        # C4 with "show accidental" in C major: a courtesy natural -> forced.
        # C#4 then C4 (natural needed to cancel) -> left automatic.
        f = facts([measure(1, "0")],
                  [entry(1, 1, "0", "1", [note(60, "C", show_acci=True)]),
                   entry(2, 1, "1", "1", [note(61, "C", 1, show_acci=True)]),
                   entry(3, 1, "2", "1", [note(60, "C", show_acci=True)])], kind="mus")
        chords = FactsReader(f).read().flows[0].staves[0].voices[0].chords
        self.assertEqual([c.pitches[0].accidental for c in chords], ["show", None, None])

    def test_courtesy_rule_only_for_legacy_files(self):
        f = facts([measure(1, "0")], [entry(1, 1, "0", "1", [note(60, "C", show_acci=True)])])
        chords = FactsReader(f).read().flows[0].staves[0].voices[0].chords
        self.assertIsNone(chords[0].pitches[0].accidental)

    def test_zero_length_and_tremolo_tuplets_skipped(self):
        tup = {"layer": 1, "voice": 1, "display_num": 3, "display_dur": "1/2", "ref_num": 2, "ref_dur": "1/2",
               "hidden": False, "tremolo": False}
        f = facts([measure(1, "0")], [entry(1, 1, "0", "1/3", [note(60, "C")])],
                  tuplets=[dict(tup, pos="0", end="1"), dict(tup, pos="2", end="2"),
                           dict(tup, pos="3", end="4", tremolo=True)])
        r = FactsReader(f)
        tuplets = r.read().flows[0].staves[0].voices[0].tuplets
        self.assertEqual([(t.pos, t.dur, t.num, t.den, t.unit) for t in tuplets], [(F(0), F(1), 3, 2, F(1, 2))])
        self.assertTrue(any("tremolo" in w for w in r.warnings))

    def test_staff_only_time_signature(self):
        # E.T.: one staff in 12/8 (four dotted crotchets) for bar 2 while the score is 4/4.
        # musxdom positions are global (quavers last 1/3), so bar 2 gets a hidden 12:8 tuplet
        # and the staff returns to 4/4 at bar 3.
        quavers = [entry(10 + k, 2, str(4 + F(k, 3)), "1/3", [note(60, "C")], notated="1/2") for k in range(12)]
        f = facts([measure(1, "0"), measure(2, "4"), measure(3, "8")],
                  [entry(1, 1, "0", "4", [note(60, "C")])] + quavers + [entry(30, 3, "8", "4", [note(60, "C")])])
        f["staves"][0]["time_changes"] = [{"measure": 2, "pos": "4", "time": ts("4", "3/2"),
                                           "display_time": ts("4", "3/2"), "display_duration": "6"}]
        flow = FactsReader(f).read().flows[0]
        st = flow.staves[0]
        self.assertEqual([(t.pos, t.num, t.den) for t in st.time_signatures], [(F(4), 12, 8), (F(8), 4, 4)])
        self.assertEqual([(t.num, t.den) for t in flow.time_signatures], [(4, 4)])
        tuplets = st.voices[0].tuplets
        self.assertEqual([(t.pos, t.dur, t.num, t.den, t.unit, t.hidden) for t in tuplets],
                         [(F(4), F(4), 12, 8, F(1, 2), True)])

    def test_unnamed_untyped_staves(self):
        f = facts([measure(1, "0")], [], instruments=[
            {"staves": [1], "name": "Unknown Instrument", "uuid": "a925648a-abc9-4dc7-a619-a6ce355ad33c",
             "transposition_type": "none"}])
        self.assertEqual(FactsReader(f).read().players[0].name, "Staff 1")

    def test_zero_length_trill_line_by_glyph_name(self):
        # Trex: custom line (wiggleTrill) whose start text is EngraverFontExtras "tr-flat"
        # (ornamentTrillFlatAbove), both ends at the same spot -> half-step trill on the note
        f = facts([measure(1, "0")], [entry(1, 1, "0", "2", [note(74, "D")]), entry(2, 1, "2", "2", [note(77, "F")])])
        f["custom_lines"] = [{"id": 18, "style": "char", "char": 60, "glyph": "wiggleTrill",
                              "start_text": [{"text": "<", "music": True, "smufl": False,
                                              "glyphs": ["ornamentTrillFlatAbove"]}]}]
        ep = {"staff": 1, "measure": 1, "entry": 0, "valid": True, "pos": "0"}
        f["smart_shapes"] = [{"id": 1, "type": "smartLine", "line_style": 18, "hidden": False,
                              "start": ep, "end": dict(ep)}]
        trills = FactsReader(f).read().flows[0].staves[0].voices[0].trills
        self.assertEqual([(t.pos, t.end, t.interval) for t in trills], [(F(0), F(2), 1)])  # D -> E flat

    def test_glyph_named_articulations_and_dynamics(self):
        e = entry(1, 1, "0", "1", [note(72, "C")])
        e["artics"] = [{"char": 999, "glyph": "articAccentAbove"}, {"char": 998, "glyph": "tremolo2"}]
        f = facts([measure(1, "0")], [e])
        f["expressions"] = [{"measure": 1, "staff": 1, "pos": "0", "layer": 1, "hidden": False, "kind": "text",
                             "chunks": [{"text": "x", "music": True, "smufl": False, "glyphs": ["dynamicSforzatoFF"]}],
                             "category": "dynamics"}]
        st = FactsReader(f).read().flows[0].staves[0]
        c = st.voices[0].chords[0]
        self.assertEqual((c.articulations, c.tremolo), (["accent"], 2))
        self.assertEqual([d.kind for d in st.dynamics], ["sffz"])

    def test_tempo_marks_parsed_and_merged(self):
        f = facts([measure(1, "0"), measure(2, "4")], [entry(1, 1, "0", "1", [note(72, "C")])])
        chunk = lambda t, music=False, glyphs=None: {"text": t, "music": music, "smufl": False,
                                                     **({"glyphs": glyphs} if glyphs else {})}
        f["expressions"] = [
            {"measure": 1, "staff": 1, "pos": "0", "hidden": False, "kind": "text", "category": "tempoMarks",
             "chunks": [chunk("SCENE I")]},
            {"measure": 1, "staff": 1, "pos": "0", "hidden": False, "kind": "text", "category": "tempoMarks",
             "chunks": [chunk("q = 92-96", True, ["metNoteQuarterUp"] + [""] * 8)]},
            {"measure": 2, "staff": 1, "pos": "4", "hidden": False, "kind": "text", "category": "misc",
             "chunks": [chunk("Meno mosso")], "playback": "time", "value": 72},
            {"measure": 2, "staff": 1, "pos": "6", "hidden": False, "kind": "text", "category": "tempoAlts",
             "chunks": [chunk("rit.")]},
            {"measure": 2, "staff": 1, "pos": "4", "hidden": False, "kind": "text", "category": "misc",
             "enclosure": True, "chunks": [chunk("21")]},
        ]
        fl = FactsReader(f).read().flows[0]
        self.assertEqual([(t.pos, t.bpm, t.bpm_max, t.text, t.show_metronome) for t in fl.tempos],
                         [(F(0), 92.0, 96.0, "SCENE I", True), (F(4), 72.0, None, "Meno mosso", False)])
        self.assertEqual([(g.pos, g.end, g.kind) for g in fl.gradual_tempos], [(F(6), F(8), "rit")])
        self.assertEqual(fl.rehearsal_marks, [F(4)])

    def test_notes_under_8va_are_sounding_pitch(self):
        f = facts([measure(1, "0")], [entry(1, 1, "0", "1", [note(72, "C")]), entry(2, 1, "1", "1", [note(74, "D")])])
        ep = lambda p: {"staff": 1, "measure": 1, "entry": 0, "valid": True, "pos": p}
        f["smart_shapes"] = [{"id": 1, "type": "octaveUp", "hidden": False, "start": ep("1"), "end": ep("2")}]
        st = FactsReader(f).read().flows[0].staves[0]
        self.assertEqual([c.pitches[0].midi for c in st.voices[0].chords], [72, 86])  # D raised an octave
        self.assertEqual([(o.pos, o.kind) for o in st.ottavas], [(F(1), "up8")])

    def test_fermata_pedal_cross_staff(self):
        e1 = entry(1, 1, "0", "1", [note(72, "C")])
        e1["artics"] = [{"char": 0, "glyph": "fermataAbove"}, {"char": 0, "glyph": "keyboardPedalPed"}]
        e2 = entry(2, 1, "2", "1", [note(74, "D", staff=2, cross_staff=True)])
        e2["artics"] = [{"char": 0, "glyph": "keyboardPedalUp"}]
        f = facts([measure(1, "0")], [e1, e2], instruments=[{"staves": [1, 2], "name": "Piano", "uuid": "",
                                                              "transposition_type": "none"}])
        f["staves"].append({"id": 2, "default_clef": 3, "clef_changes": [], "entries": [], "tuplets": []})
        fl = FactsReader(f).read().flows[0]
        self.assertEqual(fl.pauses, [F(0)])
        self.assertEqual([(p.pos, p.end) for p in fl.staves[0].pedals], [(F(0), F(2))])
        self.assertEqual(fl.staves[0].voices[0].chords[1].pitches[0].staff, 1)

    def test_round9_breaths_subito_combined_niente(self):
        # Round 9: breath marks / caesura after the note; subito, mf-mp, niente hairpins
        e1 = entry(1, 1, "0", "1", [note(72, "C")])
        e1["artics"] = [{"char": 0, "glyph": "breathMarkTick"}]
        e2 = entry(2, 1, "1", "3", [note(74, "D")])
        e2["artics"] = [{"char": 0, "glyph": "caesura"}]
        f = facts([measure(1, "0"), measure(2, "4")], [e1, e2, entry(3, 2, "4", "4", [note(72, "C")])])

        def x(pos, chunks):
            return {"measure": 1, "staff": 1, "pos": pos, "layer": 1, "hidden": False, "kind": "text",
                    "chunks": chunks, "category": "dynamics"}
        f["expressions"] = [
            x("0", [{"text": "sub. ", "music": False, "smufl": False, "glyphs": []},
                    {"text": "p", "music": True, "smufl": False, "glyphs": ["dynamicPiano"]}]),
            x("1", [{"text": "xy", "music": True, "smufl": False, "glyphs": ["dynamicMF", "dynamicMP"]}]),
            x("4", [{"text": "n", "music": True, "smufl": False, "glyphs": ["dynamicNiente"]}])]
        ep = lambda pos: {"staff": 1, "measure": 2, "entry": 0, "valid": True, "pos": pos}
        f["smart_shapes"] = [{"id": 1, "type": "cresc", "hidden": False, "start": ep("4"), "end": ep("6")}]
        fl = FactsReader(f).read().flows[0]
        self.assertEqual([(b.pos, b.kind, b.appearance) for b in fl.breaths],
                         [(F(1), "breath", "kTick"), (F(4), "caesura", "kNormal")])
        st = fl.staves[0]
        self.assertEqual([(d.kind, d.subito) for d in st.dynamics], [("p", True), ("mfmp", False)])
        self.assertEqual([h.niente for h in st.hairpins], [True])

    def test_staff_only_breath_and_fermata_styles(self):
        # ref-extras2: a mark on only some playing staves goes on those staves; fermata styles
        e1 = entry(1, 1, "0", "1", [note(72, "C")])
        e1["artics"] = [{"char": 0, "glyph": "breathMarkComma"}, {"char": 0, "glyph": "fermataShortHenzeAbove"}]
        e2 = entry(2, 1, "1", "1", [note(74, "D")])
        e2["artics"] = [{"char": 0, "glyph": "caesuraCurved"}]
        e3 = entry(3, 1, "2", "1", [note(76, "E")])
        e3["artics"] = [{"char": 0, "glyph": "curlew"}]
        f = facts([measure(1, "0")], [e1, e2, e3],
                  instruments=[{"staves": [1], "name": "Flute", "uuid": "", "transposition_type": "none"},
                               {"staves": [2], "name": "Oboe", "uuid": "", "transposition_type": "none"}])
        o1 = entry(4, 1, "0", "2", [note(69, "A")])
        o1["artics"] = [{"char": 0, "glyph": "fermataShortHenzeAbove"}, {"char": 0, "glyph": "caesuraCurved"}]
        o2 = entry(5, 1, "2", "1", [note(69, "A")])
        f["staves"].append({"id": 2, "default_clef": 0, "clef_changes": [], "tuplets": [],
                            "entries": [o1, o2]})
        fl = FactsReader(f).read().flows[0]
        flute = next(s for s in fl.staves if s.voices[0].chords[0].pitches[0].midi == 72)
        # the comma after beat 1 is on the flute only (oboe still sounding) -> flute staff
        self.assertEqual([(b.pos, b.kind, b.appearance) for b in flute.pauses], [(F(1), "breath", "kComma")])
        # caesura at 2: flute and oboe both have it -> global; fermatas: Henze + curlew
        self.assertEqual(sorted((b.pos, b.kind, b.appearance) for b in fl.breaths),
                         [(F(0), "fermata", "kShortHenze"), (F(2), "caesura", "kCurved"),
                          (F(2), "curlew", "")])
        self.assertEqual(fl.pauses, [])

    def test_page_layout(self):
        f = facts([measure(1, "0"), measure(2, "4")], [entry(1, 1, "0", "4", [note(72, "C")])])
        sys_ = lambda sid, staves: {"id": sid, "page": 1, "start": sid, "end": sid + 1, "scaling": 0.5,
                                    "staves": [{"id": s, "top": 0, "scaling": 1} for s in staves]}
        f["layout"] = {"page_format": {"width": 3168, "height": 4896, "scaling": 0.5},
                       "part_page_format": {"width": 2448, "height": 3168, "scaling": 0.85},
                       "pages": [{"id": 1, "width": 3168, "height": 4896}],
                       "systems": [sys_(1, [1, 2]), sys_(2, [1])]}
        lay = FactsReader(f).read().layout
        self.assertEqual((lay.page_width, lay.page_height, lay.space), (792, 1224, 3.0))
        self.assertEqual((lay.part_page_width, lay.part_page_height, lay.part_space), (612, 792, 5.1))
        self.assertEqual((lay.hide_empty, lay.staves_per_system), ("after_first", 2))

    def test_numbered_and_doubling_staff_names(self):
        # Avatar: "1)" / "1 -" take the bracket group's name; "2 - Picc." is player 2 on piccolo
        insts = [{"staves": [1], "name": "1)", "group_name": "Bassoons", "uuid": "", "transposition_type": "none"},
                 {"staves": [2], "name": "2 - Cfg.", "group_name": "Bassoons", "uuid": "", "transposition_type": "none"}]
        f = facts([measure(1, "0")], [entry(1, 1, "0", "4", [note(48, "C")])], instruments=insts)
        f["staves"].append({"id": 2, "default_clef": 0, "clef_changes": [], "tuplets": [], "entries": []})
        names = [p.name for p in FactsReader(f).read().players]
        self.assertEqual(names, ["Bassoon 1", "Cfg."])

    def test_untyped_staves_get_unknown_transposition_and_shared_key(self):
        insts = [{"staves": [1], "name": "Trumpet 1 in C", "uuid": "", "transposition_type": "none"},
                 {"staves": [2], "name": "Trumpet 2", "uuid": "", "transposition_type": "none"},
                 {"staves": [3], "name": "Clarinet", "uuid": "", "transposition_type": "none"}]
        f = facts([measure(1, "0")], [entry(1, 1, "0", "4", [note(72, "C")])], instruments=insts)
        for sid in (2, 3):
            f["staves"].append({"id": sid, "default_clef": 0, "clef_changes": [], "tuplets": [], "entries": []})
        insts = [i for p in FactsReader(f).read().players for i in p.instruments]
        self.assertEqual([i.transposition for i in insts], [None, None, None])
        self.assertEqual([i.key for i in insts], ["c", "c", None])

    def test_legacy_font_tempo_sff_and_text_ottava(self):
        # E.T. (.mus): Maestro tempo "Con Brio (q=144)" in Miscellaneous, "S"+"f" = sff,
        # "8va" text with transposing playback ... "loco"
        f = facts([measure(1, "0"), measure(2, "4")],
                  [entry(1, 1, "0", "4", [note(72, "C")]), entry(2, 2, "4", "4", [note(72, "C")])])
        mus = lambda t, g: {"text": t, "music": True, "smufl": False, "glyphs": g}
        txt = lambda t: {"text": t, "music": False, "smufl": False}
        x = lambda pos, chunks, **kw: dict({"measure": 1, "staff": 1, "pos": pos, "layer": 0, "hidden": False,
                                            "kind": "text", "chunks": chunks, "category": "misc"}, **kw)
        f["expressions"] = [
            x("0", [txt("Con Brio ("), mus("q=144", ["noteQuarterUp", "timeSigEquals", "tuplet1", "tuplet4", "tuplet4"]), txt(")")]),
            x("0", [mus("Sf", ["dynamicSforzando1", "dynamicForte"])]),
            x("0", [mus("\u00c3", ["ottavaAlta"])], playback="transpose", value=12),
            x("4", [txt("loco")], playback="transpose", value=0)]
        fl = FactsReader(f).read().flows[0]
        self.assertEqual([(t.text, t.bpm, t.unit) for t in fl.tempos], [("Con Brio", 144.0, F(1))])
        st = fl.staves[0]
        self.assertEqual([d.kind for d in st.dynamics], ["sff"])
        self.assertEqual([(o.pos, o.end, o.kind) for o in st.ottavas], [(F(0), F(4), "up8")])
        self.assertEqual([c.pitches[0].midi for c in st.voices[0].chords], [84, 72])  # sounding octave up

    def test_copyist_font_box_codes(self):
        # Finale's jazz library: "[B\r\i\g\ht]" in Finale Copyist Text is "Bright" in a box
        # (Avalon lead sheet); the high box pieces arrive as Ü/≥ (Mac) or \x86/³ (Windows).
        f = facts([measure(1, "0")], [entry(1, 1, "0", "4", [note(72, "C")])])
        txt = lambda t: {"text": t, "music": False, "smufl": False, "font": "Finale Copyist Text"}
        x = lambda chunks, cat: {"measure": 1, "staff": 1, "pos": "0", "layer": 0, "hidden": False,
                                 "kind": "text", "chunks": chunks, "category": cat}
        f["expressions"] = [x([txt("[B\\r\\i\\g\\ht]")], "tempoMarks"),
                            x([txt("[h\\a\\r\\m\\o\\n\\ \\w\u2265/st\\em]")], "techniqueText"),
                            x([txt("[s\\t\\r\\\u00dc\\a\\i\\g\\ht]")], "techniqueText")]
        fl = FactsReader(f).read().flows[0]
        self.assertEqual([t.text for t in fl.tempos], ["Bright"])
        texts = [t.text for t in fl.staves[0].techniques] + [t.text for t in getattr(fl.staves[0], "texts", [])]
        self.assertIn("harmon w/stem", texts)
        self.assertIn("straight", texts)

    def test_score_info_as_printed(self):
        # Für Elise: template Score Info "Title Insert", real title typed as page text;
        # Avatar: "composer" holds the cue number for the header, composer typed on page 1
        f = facts([measure(1, "0")], [entry(1, 1, "0", "4", [note(72, "C")])])
        f["info"] = {"title": "Title Insert", "composer": "2m2r", "copyright": "x"}
        pt = lambda text, h, v, size, page=1, multi=False, ins=(): {
            "start_page": page, "end_page": page, "multi": multi, "hidden": False, "h_align": h,
            "v_align": v, "size": size, "inserts": list(ins), "chunks": [{"text": text, "music": False}]}
        f["page_texts"] = [pt("Für Elise\n", "center", "top", 24), pt("Bagatelle", "center", "top", 15),
                           pt("James Horner (ASCAP)\nOrch. Jon Kull", "right", "top", 12),
                           pt("Name ________", "left", "top", 12),
                           pt("2m2r", "right", "top", 40, page=2, multi=True, ins=["composer"])]
        info = FactsReader(f).read().info
        self.assertEqual((info.title, info.subtitle, info.composer, info.arranger, info.copyright),
                         ("Für Elise", "Bagatelle", "James Horner (ASCAP)", "Orch. Jon Kull", ""))

    def test_et_page_one_fixes(self):
        # E.T.: stacked "1"/"2" staff labels in bar 1, "maestoso" on a lower staff only (text,
        # not a tempo), one divisi staff hidden in some systems (show all), ^title + typed subtitle
        f = facts([measure(1, "0"), measure(2, "4")], [])
        names = ["Flute", "Oboe", "Horn", "Trumpet", "Violin"]
        f["instruments"] = [{"staves": [i + 1], "name": n, "uuid": "", "transposition_type": "none"}
                            for i, n in enumerate(names)]
        f["staves"] = [dict(f["staves"][0], id=i + 1, entries=[entry(10 * i + 1, 1, "0", "4", [note(72, "C")])])
                       for i in range(5)]
        txt = lambda t: {"text": t, "music": False, "smufl": False}
        x = lambda staff, t, m=1, pos="0": {"measure": m, "staff": staff, "pos": pos, "layer": 0, "hidden": False,
                                            "kind": "text", "chunks": [txt(t)], "category": "misc"}
        f["expressions"] = [x(3, "1\n2"), x(4, "maestoso", 2, "4"), x(1, "Allegro")]
        sy = lambda ids: {"staves": [{"id": i, "top": 0, "scaling": 1} for i in ids]}
        f["layout"] = {"page_format": {"width": 2448, "height": 3168, "scaling": 1},
                       "systems": [sy([1, 2, 3, 4]), sy([1, 2, 3, 4, 5])]}
        f["info"] = {"title": "ADVENTURES ON EARTH"}
        f["page_texts"] = [{"start_page": 1, "end_page": 1, "multi": False, "hidden": False, "h_align": "center",
                            "v_align": "top", "size": 24, "inserts": ["title"],
                            "chunks": [txt("ADVENTURES ON EARTH\nFrom the Universal Picture")]}]
        s = FactsReader(f).read()
        fl = s.flows[0]
        self.assertEqual([t.text for t in fl.tempos], ["Allegro"])
        texts = [t.text for st in fl.staves for t in st.techniques]
        self.assertEqual(texts.count("maestoso"), 1)
        self.assertNotIn("1 2", texts)
        self.assertEqual(s.layout.hide_empty, "never")
        self.assertEqual(s.info.subtitle, "From the Universal Picture")

    def test_trill_half_and_whole_step_text(self):
        from f2d.finale.facts import _trill_step
        self.assertEqual([_trill_step(t) for t in ("1/2", " ½", "H.T.", "WT", "W.T.", "1", "b")],
                         [1, 1, 1, 2, 2, None, None])

    def test_repeats_endings_text_repeats(self):
        ms = [measure(i, str(4 * (i - 1))) for i in range(1, 5)]
        ms[1]["forward_repeat"] = True                       # |: at bar 2
        ms[2]["backward_repeat"] = True                      # :| after bar 3
        ms[3]["barline"] = "final"                           # closing final barline: automatic
        ms[0]["barline"] = "double"
        f = facts(ms, [entry(1, 1, "0", "4", [note(72, "C")])])
        f["endings"] = [{"measure": 3, "length": 1, "text": "1.", "passes": [1], "open": False, "hidden": False},
                        {"measure": 4, "length": 1, "text": "2.", "passes": [2], "open": True, "hidden": False}]
        seg = {"text": "%", "music": True, "smufl": False, "glyphs": ["segno"]}
        f["text_repeats"] = [{"measure": 2, "chunks": [seg], "hidden": False, "action": "none"},
                             {"measure": 4, "chunks": [{"text": "D.S. al Fine", "music": False}], "hidden": False,
                              "action": "absolute"}]
        fl = FactsReader(f).read().flows[0]
        # bar 1's double barline coincides with bar 2's start repeat: the repeat wins; the closing
        # final barline is automatic
        self.assertEqual([(b.pos, b.kind) for b in fl.barlines], [(F(4), "start_repeat"), (F(12), "end_repeat")])
        self.assertEqual([(e.pos, e.end, e.numbers) for e in fl.endings], [(F(8), F(12), [1]), (F(12), F(16), [2])])
        self.assertEqual([(m.pos, m.section, m.jump, m.until) for m in fl.repeat_markers],
                         [(F(4), "segno", None, None), (F(15), None, "ds", "fine")])

    def test_workaround_extra_entries_dropped(self):
        f = facts([measure(1, "0")], [entry(1, 1, "0", "1", [note(60, "C")]),
                                      entry(2, 1, "0", "1", [note(60, "C")], workaround_extra=True)])
        self.assertEqual(len(FactsReader(f).read().flows[0].staves[0].voices[0].chords), 1)


if __name__ == "__main__":
    unittest.main()
