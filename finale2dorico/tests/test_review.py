"""Reviewer: write a small project with known problems, read it back, check the findings."""
from __future__ import annotations

import sys
import tempfile
import unittest
from fractions import Fraction as F
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from f2d import ir  # noqa: E402
from f2d.dorico import writer  # noqa: E402
from f2d.review import review  # noqa: E402
from test_core import _FakeInstall  # noqa: E402


def _project(staff_marks, rests=()):
    players, staves = [], []
    for k, (dyns, pins) in enumerate(staff_marks, 1):
        inst = ir.Instrument(id=f"I{k}", name="Flute")
        players.append(ir.Player(id=f"P{k}", name="Flute", instruments=[inst]))
        chords = [ir.Chord(pos=F(i), dur=F(1), notated=F(1), pitches=[ir.Pitch(72, "C")])
                  for i in range(16) if i not in rests]
        staves.append(ir.Staff(instrument=f"I{k}", index=0, voices=[ir.Voice(index=0, chords=chords)],
                               dynamics=[ir.Dynamic(F(p), kind) for p, kind in dyns],
                               hairpins=[ir.Hairpin(F(a), F(b), d) for a, b, d in pins]))
    flow = ir.Flow(id="F1", title="T", length=F(16), staves=staves, bar_starts=[F(0), F(4), F(8), F(12)],
                   time_signatures=[ir.TimeSignature(F(0), 4, 4)], key_signatures=[ir.KeySignature(F(0), 0)])
    return ir.Score(players=players, flows=[flow])


def _checks(score, **opts):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "t.dorico"
        writer.DoricoWriter(score, _FakeInstall(), writer.Options(library="instruments", **opts)).write(path)
        return review(path)


class ReviewTests(unittest.TestCase):
    def test_clash_silence_and_repeat(self):
        s = _project([([(0, "p"), (4, "mf"), (6, "mf"), (9, "f"), (12, "p")], [])], rests=(9,))
        s.flows[0].staves[0].dynamics.append(ir.Dynamic(F(12), "ff"))  # clash with p at 12
        found = {(f.check, f.where) for f in _checks(s, group_dynamics=False)}
        self.assertIn(("dynamic-clash", "bar 4 beat 1"), found)
        self.assertIn(("repeated-dynamic", "bar 2 beat 3"), found)
        self.assertIn(("dynamic-in-silence", "bar 3 beat 2"), found)

    def test_could_link_when_not_linked(self):
        marks = ([(0, "p")], [(0, 4, "cresc")])
        s = _project([marks, marks])
        found = [f for f in _checks(s, link_dynamics="none") if f.check == "could-link"]
        self.assertEqual(len(found), 1)
        found = [f for f in _checks(s) if f.check == "could-link"]  # linked by the writer: quiet
        self.assertEqual(found, [])

    def test_bar_beat_with_pickup(self):
        from f2d.dorico.read import read_project
        ref = Path(__file__).resolve().parents[1] / "experiments/round2-results/ref-pickup.dorico"
        if not ref.exists():
            self.skipTest("reference file not present")
        fl = read_project(ref).flows[0]
        # 1-beat pick-up in 3/4. Bar numbers as Dorico shows them (shared model, 2026-10-29):
        # the pick-up is bar 0, the first full bar is bar 1.
        self.assertEqual(fl.where(F(0)), "bar 0 beat 1")
        self.assertEqual(fl.where(F(1)), "bar 1 beat 1")


if __name__ == "__main__":
    unittest.main()
