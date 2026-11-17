"""Doublings: a staff that switches instrument by text becomes one player with two instruments."""
from __future__ import annotations

import sys
import unittest
from fractions import Fraction as F
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from f2d import ir  # noqa: E402
from f2d.doublings import _switch_target, apply_doublings, staff_instruments  # noqa: E402


def _score(name, switches):
    chords = [ir.Chord(pos=F(i), dur=F(1), notated=F(1), pitches=[ir.Pitch(72, "C")]) for i in range(16)]
    inst = ir.Instrument(id="I1", name=name)
    st = ir.Staff(instrument="I1", index=0, voices=[ir.Voice(index=0, chords=chords)],
                  dynamics=[ir.Dynamic(F(0), "p"), ir.Dynamic(F(9), "f")],
                  techniques=[ir.Technique(F(p), t, None) for p, t in switches])
    flow = ir.Flow(id="F1", title="T", length=F(16), staves=[st], bar_starts=[F(0), F(4), F(8), F(12)])
    return ir.Score(players=[ir.Player(id="P1", name=name, instruments=[inst])], flows=[flow])


class DoublingTests(unittest.TestCase):
    def test_names(self):
        self.assertEqual(staff_instruments("Piccolo\n(Flute 3)"), ["Piccolo", "Flute 3"])
        self.assertEqual(staff_instruments("Piano/Celeste"), ["Piano", "Celeste"])
        self.assertEqual(staff_instruments("Flute 1"), [])
        names = ["Oboe 2", "English Horn"]
        self.assertEqual(_switch_target("To Eng. Hn.", names), 1)
        self.assertEqual(_switch_target("(Eng. Hn.)\n  Solo", names), 1)
        self.assertEqual(_switch_target("To Oboe", names), 0)
        self.assertIsNone(_switch_target("espressivo", names))

    def test_split_by_switches(self):
        s = _score("Piccolo\n(Flute 3)", [(7.5, "To Flute"), (12, "Picc.")])
        report = apply_doublings(s)
        self.assertEqual(len(report), 1)
        p = s.players[0]
        self.assertEqual([i.name for i in p.instruments], ["Piccolo", "Flute 3"])
        by_inst = {st.instrument: st for st in s.flows[0].staves}
        picc, fl = by_inst[p.instruments[0].id], by_inst[p.instruments[1].id]
        self.assertEqual([c.pos for c in picc.voices[0].chords], [F(i) for i in list(range(8)) + list(range(12, 16))])
        self.assertEqual([c.pos for c in fl.voices[0].chords], [F(i) for i in range(8, 12)])
        self.assertEqual([d.kind for d in fl.dynamics], ["f"])          # follows the instrument playing
        self.assertFalse([t for st in s.flows[0].staves for t in st.techniques])  # switch texts consumed

    def test_no_switches_no_change(self):
        s = _score("Piano/Celeste", [])
        self.assertEqual(apply_doublings(s), [])
        self.assertEqual(len(s.players[0].instruments), 1)


if __name__ == "__main__":
    unittest.main()
