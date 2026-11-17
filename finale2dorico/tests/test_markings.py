"""Writer: tempo marks and changes, rehearsal marks, fermatas, ottavas, pedals, arpeggios,
ornaments, text, cross-staff notes (encodings mined from the user's projects)."""
from __future__ import annotations

import sys
import unittest
from fractions import Fraction as F
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from f2d import ir  # noqa: E402
from f2d.dorico import writer  # noqa: E402
from test_core import _FakeInstall  # noqa: E402


def _score():
    chords = [ir.Chord(pos=F(i), dur=F(1), notated=F(1), pitches=[ir.Pitch(72, "C"), ir.Pitch(76, "E")])
              for i in range(8)]
    chords[0].arpeggio, chords[1].ornament, chords[2].fermata = "normal", "turn", True
    chords[3].pitches[1].staff = 0
    st = ir.Staff(instrument="I1", index=0, voices=[ir.Voice(index=0, chords=chords)],
                  ottavas=[ir.Ottava(F(4), F(6), "up8")], pedals=[ir.Pedal(F(0), F(2))],
                  techniques=[ir.Technique(F(1), "cantabile", None)])
    flow = ir.Flow(id="F1", title="T", length=F(8), staves=[st], bar_starts=[F(0), F(4)],
                   time_signatures=[ir.TimeSignature(F(0), 4, 4)], key_signatures=[ir.KeySignature(F(0), 0)],
                   tempos=[ir.Tempo(F(0), 92, text="Allegro"), ir.Tempo(F(4), None, text="Meno mosso", show_metronome=False),
                           ir.Tempo(F(6), 60)],
                   gradual_tempos=[ir.GradualTempo(F(2), F(4), "rit", "rit.")],
                   rehearsal_marks=[F(4)], pauses=[F(2)])
    inst = ir.Instrument(id="I1", name="Flute")
    return ir.Score(players=[ir.Player(id="P1", name="Flute", instruments=[inst])], flows=[flow])


def _events(doc):
    out = {}

    def walk(n):
        if n.tag.endswith("EventDefinition"):
            out.setdefault(n.tag, []).append(n)
        for c in n.children or []:
            walk(c)
    walk(doc.root)
    return out


class MarkingTests(unittest.TestCase):
    def setUp(self):
        self.ev = _events(writer.DoricoWriter(_score(), _FakeInstall()).build())

    def test_round9_pauses_and_dynamics(self):
        score = _score()
        fl, st = score.flows[0], score.flows[0].staves[0]
        fl.breaths = [ir.Breath(F(3), "breath", "kSalzedo"), ir.Breath(F(7), "caesura", "kNormal")]
        st.dynamics = [ir.Dynamic(F(0), "mfmp", subito=True), ir.Dynamic(F(4), "ffz")]
        st.hairpins = [ir.Hairpin(F(5), F(7), "dim", niente=True)]
        doc = writer.DoricoWriter(score, _FakeInstall()).build()
        ev = _events(doc)
        pauses = [(e.child("position").value, [(c.tag, c.value) for c in e.child("pauseData").children])
                  for e in ev["PauseEventDefinition"]]
        self.assertIn(("3", [("pauseType", "kBreathMark"), ("breathMarkAppearance", "kSalzedo")]), pauses)
        self.assertIn(("7", [("pauseType", "kCaesura"), ("caesuraAppearance", "kNormal")]), pauses)
        from doricokit import format as dtn
        xml = dtn.to_xml(doc)
        self.assertRegex(xml, r"<direction>kDown</direction>\s*<startIntensity>0</startIntensity>\s*"
                              r"<endIntensity>0</endIntensity>\s*<commonDef>\s*<subito>true</subito>")
        self.assertRegex(xml, r"kForceDynamicFz</type>\s*<intensityLevel>2<")
        self.assertIn("<hasNiente>true</hasNiente>", xml)

    def test_sf_staff_pauses_fermata_styles(self):
        # ref-extras2: sf = Sfz without z; staff-only pause in the stave stream; fermata styles
        score = _score()
        fl, st = score.flows[0], score.flows[0].staves[0]
        st.dynamics = [ir.Dynamic(F(0), "sf")]
        st.pauses = [ir.Breath(F(3), "breath", "kComma")]
        fl.breaths = [ir.Breath(F(4), "fermata", "kLongHenze"), ir.Breath(F(5), "curlew", "")]
        doc = writer.DoricoWriter(score, _FakeInstall()).build()
        from doricokit import format as dtn
        xml = dtn.to_xml(doc)
        self.assertRegex(xml, r"kDynamicRinforzandoAndSforzandoHaveZ</propertyType>\s*"
                              r"<value>string: &quot;false&quot;</value>|kDynamicRinforzandoAndSforzandoHaveZ")
        self.assertRegex(xml, r"kForceDynamicSfz</type>\s*<intensityLevel>1<")
        blocks = doc.root.find("flows/array").children[0].find("blocks/array").children
        where = {}
        for b in blocks:
            for e in b.find("events").children or []:
                if e.tag == "PauseEventDefinition":
                    data = tuple((c.tag, c.value) for c in e.child("pauseData").children)
                    where[data] = (b.text("parentEventStreamType"), e.child("position").value)
        self.assertEqual(where[(("pauseType", "kBreathMark"), ("breathMarkAppearance", "kComma"))],
                         ("kInstrumentStaveStream", "3"))
        self.assertEqual(where[(("pauseType", "kFermata"), ("fermataDuration", "kLongHenze"))],
                         ("kGlobalTimebaseStream", "4"))
        self.assertEqual(where[(("pauseType", "kCurlew"),)], ("kGlobalTimebaseStream", "5"))

    def test_repeat_barlines_endings_markers(self):
        score = _score()
        fl = score.flows[0]
        fl.barlines = [ir.Barline(F(4), "start_repeat"), ir.Barline(F(6), "double")]
        fl.endings = [ir.Ending(F(4), F(6), [1]), ir.Ending(F(6), F(8), [2])]
        fl.repeat_markers = [ir.RepeatMarker(F(0), section="segno"), ir.RepeatMarker(F(7), jump="ds", until="coda")]
        doc = writer.DoricoWriter(score, _FakeInstall()).build()
        from doricokit import format as dtn
        xml = dtn.to_xml(doc)
        self.assertIn("<type>kStartRepeat</type>", xml)
        self.assertIn("<type>kDouble</type>", xml)
        self.assertRegex(xml, r"kRepeatEndingLineNumSegments</propertyType>\s*<value>int: 2</value>")
        self.assertIn('string: &quot;2:1:0:0&quot;', xml.replace('"', "&quot;"))
        self.assertIn("<sectionType>kSegno</sectionType>", xml)
        self.assertRegex(xml, r"<jumpType>kDalSegno</jumpType>\s*<jumpQualification>kAlCoda</jumpQualification>")

    def test_round11_chords_and_lyric_syllables(self):
        score = _score()
        fl, st = score.flows[0], score.flows[0].staves[0]
        fl.chord_symbols = [
            ir.ChordSymbol(F(0), "C", quality="half-diminished", interval="7"),
            ir.ChordSymbol(F(1), "C", interval="7", alterations=["sus4"]),
            ir.ChordSymbol(F(2), "C", bass="E"),
            ir.ChordSymbol(F(3), "C", no_chord=True),
            ir.ChordSymbol(F(4), "C", interval="69")]
        v = st.voices[0]
        v.chords[0].lyrics = [ir.Lyric("hal", syllable="start")]
        v.chords[1].lyrics = [ir.Lyric("le", syllable="middle")]
        v.chords[2].lyrics = [ir.Lyric("jah", syllable="end", extension=True)]
        doc = writer.DoricoWriter(score, _FakeInstall()).build()
        from doricokit import format as dtn
        xml = dtn.to_xml(doc)
        self.assertRegex(xml, r"<quality>kMinor</quality>\s*<interval>k7</interval>\s*<alterations array=\"true\">\s*"
                              r"<alteration>\s*<type>kAltered</type>\s*<degreeAndAdjustment>\s*<degree>5</degree>\s*"
                              r"<adjustment>kFlat</adjustment>")
        self.assertRegex(xml, r"<quality>kNoThird</quality>\s*<interval>k7</interval>[\s\S]*?<type>kSuspended</type>\s*"
                              r"<degreeAndAdjustment>\s*<degree>4</degree>")
        self.assertRegex(xml, r"<alteredBass>\s*<noteName>E</noteName>")
        self.assertRegex(xml, r"<interval>k6</interval>[\s\S]*?<type>kAdd</type>\s*<degreeAndAdjustment>\s*<degree>9</degree>")
        self.assertRegex(xml, r"<chordSymbolData>\s*<playedPrimaryPitches")  # N.C.: no primary chord
        for syl in ("kStart", "kMiddle", "kEnd"):
            self.assertIn(f"<syllableType>{syl}</syllableType>", xml)
        lyr = [e for e in _events(doc)["LyricEventDefinition"]]
        self.assertTrue(any(e.child("duration").value != "0" for e in lyr))  # extension = duration

    def test_tempo_flags(self):
        flags = [e.child("data").child("flags").value for e in self.ev["ImmediateTempoChangeEventDefinition"]]
        self.assertEqual(flags, ["3", "1", "2"])  # text+metronome, text only, metronome only

    def test_global_markings(self):
        self.assertEqual(len(self.ev["GradualTempoChangeEventDefinition"]), 1)
        self.assertEqual(self.ev["RehearsalMarkEventDefinition"][0].child("position").value, "4")
        pause = self.ev["PauseEventDefinition"][0]
        self.assertEqual(pause.child("pauseData").child("pauseType").value, "kFermata")

    def test_stave_and_voice_markings(self):
        self.assertEqual(self.ev["OttavaLineEventDefinition"][0].child("entityID").value, "line.ottava.up.8")
        self.assertEqual(self.ev["PedalLineEventDefinition"][0].child("duration").value, "2")
        self.assertEqual(self.ev["ArpeggioEventDefinition"][0].child("arpeggioType").value, "kUpArpeggio")
        self.assertEqual(self.ev["OrnamentEventDefinition"][0].child("entityID").value, "ornament.turn")
        text = self.ev["TextEventDefinition"][0]
        self.assertIn("cantabile", repr(text))

    def test_cross_staff_override(self):
        overrides = [e.child("logicalStaveIDOverride").value for e in self.ev["NoteEventDefinition"]]
        self.assertEqual(sum(1 for o in overrides if o != "-1"), 1)


if __name__ == "__main__":
    unittest.main()
