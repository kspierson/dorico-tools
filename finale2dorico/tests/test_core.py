"""Unit tests for core conversion logic (stdlib unittest; no Dorico install needed).

    python3 -m unittest discover -s tests -v
"""
import sys
import unittest
from fractions import Fraction as F
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f2d import ir  # noqa: E402  (importing f2d makes doricokit importable)
from doricokit import format as dtn  # noqa: E402
from f2d.dorico import writer  # noqa: E402
from f2d.finale import enigma  # noqa: E402


class KeyPitch(unittest.TestCase):
    def test_c_major(self):
        k = enigma.Key(0)
        self.assertEqual(k.pitch(0, 0), ("C", 4, 0, 60))
        self.assertEqual(k.pitch(-7, 0), ("C", 3, 0, 48))
        self.assertEqual(k.pitch(6, 1), ("B", 4, 1, 72))

    def test_g_major_harmlev_is_relative_to_tonic(self):
        k = enigma.Key(1)              # one sharp
        self.assertEqual(k.pitch(0, 0), ("G", 4, 0, 67))
        self.assertEqual(k.pitch(6, 0), ("F", 5, 1, 78))   # F# from the key
        self.assertEqual(k.pitch(6, -1), ("F", 5, 0, 77))  # natural

    def test_minor_and_flats(self):
        k = enigma.Key((1 << 8) | 0xFD)  # minor, 3 flats -> C minor
        self.assertTrue(k.minor)
        self.assertEqual(k.fifths, -3)
        self.assertEqual(k.pitch(0, 0)[:3], ("C", 4, 0))
        self.assertEqual(k.pitch(2, 0)[:3], ("E", 4, -1))


class Transposition(unittest.TestCase):
    def test_keysig_transpositions(self):
        self.assertEqual(enigma._diatonic_to_semitones(4, 1), 7)    # horn in F
        self.assertEqual(enigma._diatonic_to_semitones(1, 2), 2)    # B-flat clarinet
        self.assertEqual(enigma._diatonic_to_semitones(2, -3), 3)   # A clarinet
        self.assertEqual(enigma._diatonic_to_semitones(-7, 0), -12)  # octave down
        self.assertEqual(enigma._diatonic_to_semitones(8, 2), 14)   # bass clarinet

    def test_chromatic(self):
        self.assertEqual(enigma._chromatic_to_semitones(2, -1), 3)
        self.assertEqual(enigma._chromatic_to_semitones(-2, 1), -3)

    def test_interval_names(self):
        self.assertEqual(writer._interval(1, 2), (2, "kIntervalMajorOrPerfect"))
        self.assertEqual(writer._interval(2, 3), (3, "kIntervalMinor"))
        self.assertEqual(writer._interval(4, 7), (5, "kIntervalMajorOrPerfect"))


class TimeAndDurations(unittest.TestCase):
    def test_time_sig(self):
        self.assertEqual(enigma._time_sig(4, 1024), (4, 4))
        self.assertEqual(enigma._time_sig(2, 1536), (6, 8))
        self.assertEqual(enigma._time_sig(3, 512), (3, 8))
        self.assertEqual(enigma._time_sig(2, 2048), (2, 2))

    def test_duration_codes(self):
        self.assertEqual(writer._duration_code(F(1)), (8, 0))
        self.assertEqual(writer._duration_code(F(1, 2)), (7, 0))
        self.assertEqual(writer._duration_code(F(1, 4)), (6, 0))
        self.assertEqual(writer._duration_code(F(3, 2)), (8, 1))
        self.assertEqual(writer._duration_code(F(2)), (9, 0))


class _FakeInstall:
    """Just enough of DoricoInstall for the writer."""

    def __init__(self):
        flute = dtn.from_xml(b"""<InstrumentEntityDefinition><name>Flute</name>
            <entityID>instrument.wind.flute</entityID><parentEntityID/><nameID>instrumentname.wind.flute</nameID>
            <numStaves>1</numStaves><musicXMLSoundID>wind.flutes.flute</musicXMLSoundID>
            <staveDefinition><numStaveLines>5</numStaveLines></staveDefinition>
            <clefs><clefIDsForEachStave array="true"><staveClefIDs>
              <idForTransposingLayouts>clef.treble</idForTransposingLayouts></staveClefIDs></clefIDsForEachStave></clefs>
            <pitchedInstrumentData><standardRange>C4-A6</standardRange><advancedRange>B3-D7</advancedRange>
              <transposedChromaticTransposition>0</transposedChromaticTransposition>
              <transposedDiatonicTransposition>0</transposedDiatonicTransposition>
              <showTransposition>kNever</showTransposition></pitchedInstrumentData>
            </InstrumentEntityDefinition>""").root
        self.instruments = {"instrument.wind.flute": flute}
        self.instrument_names = {}
        self.dir = Path("/nowhere/Dorico5")

    def name_data(self, eid):
        return {"uiName": "Flute", "singularFullName": "Flute", "singularShortName": "Fl.",
                "pluralFullName": "Flutes", "pluralShortName": "Fl.", "gender": "kNeutral",
                "language": "kEnglish"}

    def resolve(self, *a, **k):
        return "instrument.wind.flute", "test"


def _score_with(chords, tuplets=()):
    inst = ir.Instrument(id="I1", name="Flute")
    st = ir.Staff(instrument="I1", index=0, voices=[ir.Voice(index=0, chords=chords, tuplets=list(tuplets))])
    flow = ir.Flow(id="F1", title="t", length=F(8),
                   time_signatures=[ir.TimeSignature(pos=F(0), num=4, den=4)],
                   key_signatures=[ir.KeySignature(pos=F(0), fifths=0)], staves=[st])
    return ir.Score(players=[ir.Player(id="P1", name="Flute", instruments=[inst])], flows=[flow])


def _notes(doc):
    out = []
    for b in doc.root.find("flows/array").children[0].find("blocks/array").children:
        for e in b.find("events").children or []:
            if e.tag == "NoteEventDefinition":
                props = {x.text("propertyType"): x.text("value")
                         for x in e.find("propertyTable/entries").children or []}
                out.append((e.text("position"), e.text("duration"), e.text("pitch"),
                            props.get("kNoteSplitDurations")))
    return out


class WriterTies(unittest.TestCase):
    def test_tie_chain_becomes_one_note_with_split(self):
        c1 = ir.Chord(pos=F(3), dur=F(1), notated=F(1), pitches=[ir.Pitch(72, "C", tie=True)])
        c2 = ir.Chord(pos=F(4), dur=F(2), notated=F(2), pitches=[ir.Pitch(72, "C")])
        doc = writer.DoricoWriter(_score_with([c1, c2]), _FakeInstall()).build()
        self.assertEqual(_notes(doc), [("3", "3", "72", 'list: {string: "1"}, {string: "2"}')])

    def test_chord_partial_tie(self):
        c1 = ir.Chord(pos=F(0), dur=F(1), notated=F(1),
                      pitches=[ir.Pitch(60, "C", tie=True), ir.Pitch(64, "E")])
        c2 = ir.Chord(pos=F(1), dur=F(1), notated=F(1),
                      pitches=[ir.Pitch(60, "C"), ir.Pitch(67, "G")])
        doc = writer.DoricoWriter(_score_with([c1, c2]), _FakeInstall()).build()
        got = sorted((n[0], n[1], n[2]) for n in _notes(doc))
        self.assertEqual(got, [("0", "1", "64"), ("0", "2", "60"), ("1", "1", "67")])

    def test_tie_to_non_adjacent_is_dropped(self):
        c1 = ir.Chord(pos=F(0), dur=F(1), notated=F(1), pitches=[ir.Pitch(60, "C", tie=True)])
        c2 = ir.Chord(pos=F(2), dur=F(1), notated=F(1), pitches=[ir.Pitch(60, "C")])
        doc = writer.DoricoWriter(_score_with([c1, c2]), _FakeInstall()).build()
        self.assertEqual([(n[0], n[1]) for n in _notes(doc)], [("0", "1"), ("2", "1")])

    def test_tuplet_event(self):
        chords = [ir.Chord(pos=F(i, 3), dur=F(1, 3), notated=F(1, 2), pitches=[ir.Pitch(60, "C")])
                  for i in range(3)]
        doc = writer.DoricoWriter(_score_with(chords, [ir.Tuplet(F(0), F(1), 3, 2, F(1, 2))]),
                                  _FakeInstall()).build()
        xml = dtn.to_xml(doc)
        self.assertIn("{int: 3}, {int: 2}, {list: {int: 7}, {int: 0}}, {bool: true}", xml)
        # round-trips through the binary codec
        self.assertEqual(dtn.to_xml(dtn.decode(dtn.encode(doc))), xml)


    def test_staff_only_time_signature_and_hidden_tuplet(self):
        chords = [ir.Chord(pos=F(k, 3), dur=F(1, 3), notated=F(1, 2), pitches=[ir.Pitch(60, "C")])
                  for k in range(12)]
        score = _score_with(chords, [ir.Tuplet(F(0), F(4), 12, 8, F(1, 2), hidden=True)])
        st = score.flows[0].staves[0]
        st.time_signatures = [ir.TimeSignature(F(0), 12, 8), ir.TimeSignature(F(4), 4, 4)]
        doc = writer.DoricoWriter(score, _FakeInstall()).build()
        blocks = doc.root.find("flows/array").children[0].find("blocks/array").children
        stave = [b for b in blocks if b.text("parentEventStreamType") == "kInstrumentStaveStream"]
        bars = [e.text("position") for b in stave for e in b.find("events").children or []
                if e.tag == "BarDivisionEventDefinition"]
        self.assertEqual(bars, ["0", "4"])
        xml = dtn.to_xml(doc)
        self.assertIn("{int: 12}, {int: 8}, {list: {int: 7}, {int: 0}}, {bool: true}", xml)
        self.assertIn("kTupletBracketVisibility", xml)
        self.assertIn('string: "kNone"', xml)

class Layout(unittest.TestCase):
    def test_full_score_page_and_fit(self):
        from f2d.dorico import layout
        opts = layout.default_options("kFullScoreLayout")
        report = []
        layout.apply_full_score(opts, ir.Layout(612, 792, space=4.0, hide_empty="after_first", condense=True),
                                3, report)
        self.assertEqual(opts.text("defaultSpaceSize"), "4")
        self.assertEqual(opts.text("hideEmptyStavesPolicy"), "kAfterFirstSystem")
        self.assertEqual(opts.find("condensingLayoutOptions/enableCondensing").value, "true")
        self.assertEqual(report, [])
        # 45 staves on Letter: the page grows to 11x17 and the staff shrinks to fit
        opts = layout.default_options("kFullScoreLayout")
        layout.apply_full_score(opts, ir.Layout(612, 792, space=3.0), 45, report)
        self.assertEqual(opts.find("pageSizeAndMarginOptions/pageHeight").value, "1224")
        space = float(opts.text("defaultSpaceSize"))
        self.assertLessEqual(space, layout.fit_space(opts, 1224, 45) + 0.01)
        self.assertGreaterEqual(space, layout.MIN_SPACE)
        self.assertEqual(len(report), 2)

    def test_writer_writes_layout_options(self):
        score = _score_with([ir.Chord(pos=F(0), dur=F(1), notated=F(1), pitches=[ir.Pitch(60, "C")])])
        score.layout = ir.Layout(792, 1224, space=3.5, part_page_width=612, part_page_height=792, part_space=5)
        doc = writer.DoricoWriter(score, _FakeInstall()).build()
        lays = doc.root.find("layouts/array").children
        full = lays[0].find("layoutOptions")
        self.assertEqual(full.text("defaultSpaceSize"), "3.5")
        self.assertEqual(full.find("pageSizeAndMarginOptions/pageWidth").value, "792")
        part = lays[1].find("layoutOptions")
        self.assertEqual(part.text("defaultSpaceSize"), "5")
        self.assertEqual(part.find("customPlayerOrder").value, lays[1].find("layoutPlayers/array").children[0].text("playerID"))


class Explode(unittest.TestCase):
    def _score(self, name, chords):
        score = _score_with(chords)
        score.players[0].instruments[0].name = score.players[0].name = name
        score.flows[0].bar_starts = [F(0), F(4)]
        return score

    def test_chord_written_pair_split_top_down(self):
        from f2d.explode import explode
        chords = [ir.Chord(pos=F(0), dur=F(2), notated=F(2), pitches=[ir.Pitch(67, "G"), ir.Pitch(72, "C")]),
                  ir.Chord(pos=F(2), dur=F(2), notated=F(2), pitches=[ir.Pitch(70, "B", -1)])]
        score = self._score("Horns 1 3", chords)
        explode(score)
        self.assertEqual([p.name for p in score.players], ["Horn 1", "Horn 3"])
        got = [[[q.midi for q in c.pitches] for c in st.voices[0].chords] for st in score.flows[0].staves]
        self.assertEqual(got, [[[72], [70]], [[67], [70]]])  # unison B-flat: a2, both play
        self.assertTrue(score.layout.condense)
        doc = writer.DoricoWriter(score, _FakeInstall()).build()
        full = doc.root.find("layouts/array").children[0].find("layoutOptions")
        self.assertEqual(full.find("condensingLayoutOptions/userDefinedCondensableGroups").value, "0,0:1,1")

    def test_ungrouped_neighbours_excluded_from_condensing(self):
        # Avatar: once condensing is on, Dorico would also merge Oboe 1 / Oboe 2 (separate Finale
        # staves); they go in groupsToExcludeFromCondensing as player IDs
        import copy
        from f2d.explode import explode
        chords = [ir.Chord(pos=F(0), dur=F(4), notated=F(4), pitches=[ir.Pitch(67, "G"), ir.Pitch(72, "C")])]
        score = self._score("Horns 1 3", chords)
        explode(score)
        for n in (1, 2):
            p = copy.deepcopy(score.players[0])
            p.id, p.name, p.condense_group = f"PO{n}", f"Oboe {n}", None
            p.instruments[0].id = f"IO{n}"
            score.players.append(p)
            st = copy.deepcopy(score.flows[0].staves[0])
            st.instrument = f"IO{n}"
            score.flows[0].staves.append(st)
        doc = writer.DoricoWriter(score, _FakeInstall()).build()
        full = doc.root.find("layouts/array").children[0].find("layoutOptions")
        self.assertEqual(full.find("condensingLayoutOptions/groupsToExcludeFromCondensing").value, "2,3")

    def test_two_instrument_staff(self):
        from f2d.explode import explode
        chords = [ir.Chord(pos=F(0), dur=F(4), notated=F(4), pitches=[ir.Pitch(36, "C"), ir.Pitch(48, "C")])]
        score = self._score("Bass Tbn. / Tuba", chords)
        explode(score)
        self.assertEqual([p.name for p in score.players], ["Bass Tbn.", "Tuba"])
        self.assertEqual([st.voices[0].chords[0].pitches[0].midi for st in score.flows[0].staves], [48, 36])


class IRJson(unittest.TestCase):
    def test_round_trip(self):
        s = _score_with([ir.Chord(pos=F(1, 3), dur=F(1, 3), notated=F(1, 2), pitches=[ir.Pitch(61, "D", -1)])])
        s2 = ir.from_json(ir.to_json(s))
        self.assertEqual(s, s2)


if __name__ == "__main__":
    unittest.main()
