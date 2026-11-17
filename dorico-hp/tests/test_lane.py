"""Dynamics lane: engine steps -> Dorico levels, spans, accent boosts (doricohp/lane.py)."""
from __future__ import annotations

import sys
import unittest
from fractions import Fraction as F
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from doricohp import lane  # noqa: E402
from doricohp.engine import PartPerf  # noqa: E402
from doricohp.model import Note, Part  # noqa: E402


class StepToLevel(unittest.TestCase):
    def test_named_points(self):
        # engine steps (mf 0, mp -1, f 1, p -2, ff 2, pp -3) -> Dorico levels (test I2)
        for step, level in [(0, 0.5), (-1, -0.5), (1, 1.0), (-2, -1.0), (2, 2.0), (-3, -2.0), (5, 5.0)]:
            self.assertEqual(lane.step_to_level(step), level, step)

    def test_between(self):
        self.assertEqual(lane.step_to_level(0.5), 0.75)
        self.assertEqual(lane.step_to_level(-0.5), 0.0)


def perf(marked, shaped, notes=(), hairpins=()):
    part = Part("Fl", "Flute", "woodwind", notes=list(notes), hairpins=list(hairpins))
    return PartPerf(part, {}, marked=marked, shaped=shaped)


class Spans(unittest.TestCase):
    notes = [Note("Fl", F(i), F(1), 72) for i in range(16)]

    def test_only_where_shaping_differs(self):
        marked = [(F(0), 0.0), (F(16), 0.0)]
        shaped = [(F(0), 0.0), (F(4), 0.0), (F(5), 1.0), (F(6), 0.0), (F(16), 0.0)]
        self.assertEqual(lane.spans(perf(marked, shaped, self.notes)), [(F(4), F(6))])

    def test_nothing_to_draw(self):
        flat = [(F(0), 0.0), (F(16), 0.0)]
        self.assertEqual(lane.spans(perf(flat, flat, self.notes)), [])

    def test_span_after_a_hairpin_starts_with_it(self):
        marked = [(F(0), 0.0), (F(2), 0.0), (F(3), 2.0), (F(16), 2.0)]
        shaped = [(F(0), 0.0), (F(2), 0.0), (F(3), 2.0), (F(5), 0.0), (F(16), 0.0)]
        sp = lane.spans(perf(marked, shaped, self.notes, [(F(2), F(3), "cresc")]))
        self.assertEqual(sp[0][0], F(2))

    def test_part_without_notes(self):
        marked = [(F(0), 0.0), (F(16), 0.0)]
        self.assertEqual(lane.spans(perf(marked, [(F(0), -1.0), (F(16), -1.0)])), [])

    def test_clamped_to_doricos_range(self):
        loud = [(F(0), 9.0), (F(4), 9.0)]
        self.assertEqual({v for _, v in lane.points(perf(loud, loud), F(0), F(4))}, {6.0})

    def test_accent_boost(self):
        flat = [(F(0), 0.0), (F(16), 0.0)]
        notes = [Note("Fl", F(1), F(1), 72, frozenset({"accent"}))]
        pts = dict(lane.points(perf(flat, flat, notes), F(0), F(4), accent_delta=0.5))
        self.assertEqual(pts[F(0)], 0.5)
        self.assertEqual(pts[F(1)], 1.0)
        self.assertEqual(pts[F(2)], 0.5)


if __name__ == "__main__":
    unittest.main()
