"""Exploding shared staves (Finale layers) into Dorico players (Round 5, user's Willow edit)."""
from __future__ import annotations

import sys
import unittest
from fractions import Fraction as F
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from f2d import ir  # noqa: E402
from f2d.explode import _base_and_numbers, explode  # noqa: E402


def _note(pos, midi=60):
    return ir.Chord(pos=F(pos), dur=F(1), notated=F(1), pitches=[ir.Pitch(midi, "C")])


def _horns(two_staves=True, marks=()):
    """Bar 1: both layers; bar 2: layer 1 only; bar 3: layer 1 only; bar 4: layer 2 only."""
    players, staves = [], []
    for n in ((1, 2) if two_staves else (1,)):
        inst = ir.Instrument(id=f"I{n}", name=f"Horn in F {n}", sound_id="brass.french-horn")
        players.append(ir.Player(id=f"P{n}", name=inst.name, instruments=[inst]))
        l1 = ir.Voice(index=0, layer=1, chords=[_note(0, 72), _note(4, 72), _note(8, 72)])
        l2 = ir.Voice(index=1, layer=2, chords=[_note(0, 60), _note(12, 60)])
        staves.append(ir.Staff(instrument=inst.id, index=0, voices=[l1, l2],
                               dynamics=[ir.Dynamic(F(0), "mf")],
                               techniques=[ir.Technique(F(p), t, k) for p, t, k in marks]))
    flow = ir.Flow(id="F1", title="T", length=F(16), staves=staves,
                   bar_starts=[F(0), F(4), F(8), F(12)])
    return ir.Score(players=players, flows=[flow])


def _music(score, name):
    p = next(p for p in score.players if p.name == name)
    st = next(s for s in score.flows[0].staves if s.instrument == p.instruments[0].id)
    return sorted((c.pos, c.pitches[0].midi) for v in st.voices for c in v.chords)


class ExplodeTests(unittest.TestCase):
    def test_numbers_from_names(self):
        self.assertEqual(_base_and_numbers("Horn in F 1"), ("Horn in F", [1]))
        self.assertEqual(_base_and_numbers("Horns 1-2"), ("Horns", [1, 2]))
        self.assertEqual(_base_and_numbers("Trumpet 1/3"), ("Trumpet", [1, 3]))
        self.assertEqual(_base_and_numbers("Oboe"), ("Oboe", []))

    def test_two_staves_pair_1_3_and_2_4_in_order(self):
        s = _horns(marks=[(4, "a2", "a2"), (8, "1.", "solo1"), (12, "2.", "solo2")])
        explode(s)
        self.assertEqual([p.name for p in s.players],
                         ["Horn in F 1", "Horn in F 3", "Horn in F 2", "Horn in F 4"])

    def test_markings_decide_single_lines(self):
        s = _horns(two_staves=False, marks=[(4, "a2", "a2"), (8, "1.", "solo1"), (12, "2.", "solo2")])
        explode(s)
        # bar 1 split by layer; bar 2 a2 -> both; bar 3 "1." -> player 1 only; bar 4 "2." -> player 2
        self.assertEqual(_music(s, "Horn in F 1"), [(F(0), 72), (F(4), 72), (F(8), 72)])
        self.assertEqual(_music(s, "Horn in F 2"), [(F(0), 60), (F(4), 72), (F(12), 60)])

    def test_staff_items_copied_and_markings_consumed(self):
        s = _horns(two_staves=False, marks=[(4, "a2", "a2")])
        explode(s)
        for st in s.flows[0].staves:
            self.assertEqual([d.kind for d in st.dynamics], ["mf"])
            self.assertFalse([t for t in st.techniques if t.kind == "a2"])

    def test_chords_in_one_layer_are_divided(self):
        s = _horns(two_staves=False, marks=[(4, "a2", "a2")])
        l1 = s.flows[0].staves[0].voices[0]
        l1.chords[1].pitches = [ir.Pitch(72, "C"), ir.Pitch(64, "E")]  # bar 2: a chord, one layer
        explode(s)
        self.assertIn((F(4), 72), _music(s, "Horn in F 1"))
        self.assertIn((F(4), 64), _music(s, "Horn in F 2"))
        self.assertNotIn((F(4), 64), _music(s, "Horn in F 1"))

    def test_single_layer_staves_untouched(self):
        s = _horns(two_staves=False)
        s.flows[0].staves[0].voices.pop()  # no layer 2
        explode(s)
        self.assertEqual(len(s.players), 1)


if __name__ == "__main__":
    unittest.main()
