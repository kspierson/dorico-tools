"""Round 12 encodings: harmonics, lines with words, metric modulation, boxed text, gradual
technique changes (Dorico file experiments/round12/ref-harmonics-lines.dorico)."""
from __future__ import annotations

import sys
import unittest
from fractions import Fraction as F
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from f2d import ir  # noqa: E402
from f2d.dorico import writer  # noqa: E402
from f2d.finale.facts import FactsReader, _metric_modulation  # noqa: E402
from test_core import _FakeInstall, _score_with  # noqa: E402
from test_facts import entry, facts, measure, note  # noqa: E402


def _events(doc, tag):
    out = []
    for b in doc.root.find("flows/array").children[0].find("blocks/array").children:
        for e in b.find("events").children or []:
            if e.tag == tag:
                props = {x.text("propertyType"): x.text("value")
                         for x in e.find("propertyTable/entries").children or []}
                out.append((e, props))
    return out


def _build(score):
    return writer.DoricoWriter(score, _FakeInstall()).build()


class WriterRound12(unittest.TestCase):
    def test_harmonics(self):
        nat = ir.Chord(pos=F(0), dur=F(1), notated=F(1), pitches=[ir.Pitch(67, "G")], harmonic="natural")
        art = ir.Chord(pos=F(1), dur=F(1), notated=F(1), pitches=[ir.Pitch(62, "D")],
                       harmonic="artificial", harmonic_partial=4)
        notes = _events(_build(_score_with([nat, art])), "NoteEventDefinition")
        self.assertEqual(notes[0][1]["kNoteHarmonicType"], 'string: "kNatural"')
        self.assertNotIn("kNoteHarmonic", notes[0][1])
        self.assertEqual(notes[1][1]["kNoteHarmonicType"], 'string: "kArtificial"')
        self.assertEqual(notes[1][1]["kNoteHarmonic"], "int: 4")

    def test_two_note_tremolo(self):
        a = ir.Chord(pos=F(0), dur=F(1), notated=F(1), pitches=[ir.Pitch(67, "G")], tremolo_pair=3)
        b = ir.Chord(pos=F(1), dur=F(1), notated=F(1), pitches=[ir.Pitch(69, "A")], tremolo_pair_end=True)
        notes = _events(_build(_score_with([a, b])), "NoteEventDefinition")
        self.assertEqual(notes[0][1]["kBeamStart"], "list: {int: 3}, {int: 0}")
        self.assertEqual(notes[1][1]["kBeamEnd"], "null: ")
        self.assertEqual([n[1]["kNoteSplitDurations"] for n in notes], ['list: {string: "1"}'] * 2)

    def test_line_with_start_text_and_hook(self):
        s = _score_with([])
        s.flows[0].staves[0].lines.append(ir.Line(pos=F(4), end=F(8), body="dashed", hook_end=True, text="Cue:"))
        (e, props), = _events(_build(s), "HorizontalLineEventDefinition")
        self.assertEqual(e.text("lineStyleEntityID"), "linestyle.dashedLineShortInwardHook")
        self.assertEqual((e.text("startAttachmentType"), e.text("endAttachmentType")),
                         ("kRhythmicPosition", "kRhythmicPosition"))
        self.assertEqual((e.text("position"), e.text("duration")), ("4", "4"))
        self.assertEqual(props["kHorizontalLineText"], 'string: "Cue:"')
        self.assertEqual(props["kHorizontalLineTextPlacement"], 'string: "kStart"')

    def test_line_styles(self):
        L = ir.Line
        cases = [(L(F(0), F(1)), "linestyle.solidLine"),
                 (L(F(0), F(1), body="dashed"), "linestyle.dashedLineShort"),
                 (L(F(0), F(1), hook_start=True, hook_end=True), "linestyle.solidLineInwardHooks"),
                 (L(F(0), F(1), hook_start=True), "linestyle.solidLine"),
                 (L(F(0), F(1), body="dashed", arrow_end=True), "linestyle.dashedLineShortSolidArrowhead"),
                 (L(F(0), F(1), body="wavy", arrow_end=True), "linestyle.wigglyLine")]
        for ln, style in cases:
            self.assertEqual(writer._line_style(ln), style)

    def test_metric_modulation(self):
        s = _score_with([])
        s.flows[0].tempos.append(ir.Tempo(pos=F(4), equation=(F(2), F(1)), show_metronome=False))
        (e, _), = _events(_build(s), "ImmediateTempoChangeEventDefinition")
        self.assertEqual(e.find("data").text("type"), "kEquation")
        self.assertEqual(e.find("data/tempoEquation").text("left"), "steamVariantList:list: {list: {int: 9}, {int: 0}}")
        self.assertEqual(e.find("data/tempoEquation").text("right"), "steamVariantList:list: {list: {int: 8}, {int: 0}}")

    def test_boxed_text_and_technique_change(self):
        s = _score_with([ir.Chord(pos=F(0), dur=F(4), notated=F(4), pitches=[ir.Pitch(67, "G")])])
        st = s.flows[0].staves[0]
        st.techniques += [ir.Technique(pos=F(0), text="Bright", boxed=True),
                          ir.Technique(pos=F(0), text="ord.", kind="ord", group=0),
                          ir.Technique(pos=F(3), text="sul pont.", kind="sul-pont", group=0)]
        doc = _build(s)
        (_, tprops), = _events(doc, "TextEventDefinition")
        self.assertEqual(tprops["kTextBorderStyle"], 'string: "kRectangle"')
        self.assertIn("kTextBorder", tprops)
        pts = _events(doc, "PlayingTechniqueEventDefinition")
        self.assertEqual([(e.text("appearanceEntityID"), e.text("duration"), p.get("kEventGroupId")) for e, p in pts],
                         [("pta.ordinarioText", "3", "int: 0"), ("pta.sulPontText", "0", "int: 0")])
        self.assertEqual(doc.root.find("idGenerators").text("eventGroup"), "1")


def _line_facts(line_type="smartLine", **custom):
    f = facts([measure(1, "0"), measure(2, "4")],
              [entry(1, 1, "0", "4", [note(67, "G")]), entry(2, 2, "4", "4", [note(69, "A")])])
    cl = {"id": 7, "style": "dashed", "cap_start": "none", "cap_end": "none", "hook_start": 0, "hook_end": 0,
          "arrow_start": 0, "arrow_end": 0}
    cl.update(custom)
    f["custom_lines"] = [cl]
    f["smart_shapes"] = [{"id": 1, "type": line_type, "entry_based": False, "hidden": False, "line_style": 7,
                          "start": {"staff": 1, "measure": 1, "entry": 0, "valid": True, "pos": "0"},
                          "end": {"staff": 1, "measure": 2, "entry": 0, "valid": True, "pos": "8"}}]
    return f


def _words(text):
    return [{"text": text, "music": False}]


class FactsRound12(unittest.TestCase):
    def test_cue_line(self):
        f = _line_facts(cap_end="hook", hook_end=-1843, start_text=_words("Cue (don't play):"))
        st = FactsReader(f).read().flows[0].staves[0]
        self.assertEqual(st.lines, [ir.Line(pos=F(0), end=F(8), body="dashed", hook_end=True,
                                            text="Cue (don't play):")])

    def test_centre_word_line(self):
        f = _line_facts(start_text=_words("\n"), center_text=_words("possibile"))
        ln, = FactsReader(f).read().flows[0].staves[0].lines
        self.assertEqual((ln.text, ln.centre_text), ("", "possibile"))

    def test_technique_change(self):
        f = _line_facts(cap_end="arrow", arrow_end=3, start_text=_words("ord."),
                        center_text=_words("move bow towards..."), end_text=_words("sul pont."))
        st = FactsReader(f).read().flows[0].staves[0]
        self.assertEqual(st.lines, [])
        self.assertEqual([(t.pos, t.text, t.kind, t.group) for t in st.techniques],
                         [(F(0), "ord.", "ord", 0), (F(4), "move bow towards...", None, None),
                          (F(8), "sul pont.", "sul-pont", 0)])

    def test_plain_line_left_out(self):
        r = FactsReader(_line_facts("solidLine"))
        st = r.read().flows[0].staves[0]
        self.assertEqual(st.lines, [])
        self.assertTrue(any("plain line" in w for w in r.warnings))

    def test_artificial_harmonic_chord(self):
        f = facts([measure(1, "0")], [entry(1, 1, "0", "4", [note(62, "D"),
                                                            note(67, "G", notehead="noteheadDiamondHalfWide")])])
        c, = FactsReader(f).read().flows[0].staves[0].voices[0].chords
        self.assertEqual(([p.midi for p in c.pitches], c.harmonic, c.harmonic_partial), ([62], "artificial", 4))

    def test_finale_tremolo_tuplet(self):
        f = facts([measure(1, "0")], [entry(1, 1, "0", "1", [note(67, "G")], notated="1/8"),
                                      entry(2, 1, "1", "1", [note(69, "A")], notated="1/8")],
                  tuplets=[{"layer": 1, "voice": 1, "pos": "0", "end": "2", "display_num": 2,
                            "display_dur": "1/8", "ref_num": 1, "ref_dur": "2", "hidden": True,
                            "tremolo": True, "beams": 3}])
        v = FactsReader(f).read().flows[0].staves[0].voices[0]
        self.assertEqual(v.tuplets, [])
        self.assertEqual([(c.notated, c.tremolo_pair, c.tremolo_pair_end) for c in v.chords],
                         [(F(1), 3, False), (F(1), 0, True)])

    def test_metric_modulation_text(self):
        mus = lambda t, g: {"text": t, "music": True, "glyphs": g}  # noqa: E731
        chunks = [mus("{", ["timeSigParensLeft"]), mus("h", ["noteHalfUp"]), mus(" = ", ["", "", ""]),
                  mus("q", ["noteQuarterUp"]), mus("}", ["timeSigParensRight"])]
        self.assertEqual(_metric_modulation(chunks), (F(2), F(1)))
        self.assertIsNone(_metric_modulation([mus("q", ["noteQuarterUp"]), mus(" = 60", ["", "", "", "", ""])]))


if __name__ == "__main__":
    unittest.main()
