"""doricokit.harp, doricokit.midi (writer, bar maths) and doricokit.gliss (ad lib harp glissandi).

The last class checks the model against the user's crafted reference, trex-harp.mid
(PLANNED_WORK.md §4.9); it is skipped when the HPCaptures folder isn't reachable.
"""
import json
import tempfile
import unittest
from pathlib import Path

from doricokit import gliss, harp, midi, paths

TREX = Path(paths.corpus()["hp_captures"]) / "midi" / "trex-harp.mid"
PICKS = Path(__file__).resolve().parents[1] / "gliss"     # the user's preferred planned glissandi
WAVE1 = harp.Pedals.parse("Db C B | E F# G# A")       # trex m15-18
WAVE2 = harp.Pedals.parse("D# C# Bb | E F# G Ab")     # trex m26-28


class Harp(unittest.TestCase):
    def test_strings(self):
        s = harp.strings(harp.Pedals())
        self.assertEqual(len(s), 47)
        self.assertEqual((s[0].name, s[0].pitch), ("C1", 24))
        self.assertEqual((s[-1].name, s[-1].pitch), ("G7", 103))
        self.assertEqual(harp.strings(harp.Pedals.parse("Cb"))[0].pitch, 23)

    def test_parse_print_model(self):
        self.assertEqual(str(WAVE1), "D♭ C♮ B♮ | E♮ F♯ G♯ A♮")
        self.assertEqual(harp.Pedals.parse(str(WAVE1)), WAVE1)
        detail = {"aPedal": "kMiddle", "bPedal": "kMiddle", "cPedal": "kMiddle", "dPedal": "kTop",
                  "ePedal": "kMiddle", "fPedal": "kBottom", "gPedal": "kBottom"}
        self.assertEqual(harp.Pedals.from_model(detail), WAVE1)
        with self.assertRaises(ValueError):
            harp.Pedals.parse("H#")

    def test_infer(self):
        found = harp.Pedals.infer({60, 61, 64, 66, 68, 69, 71})
        self.assertEqual(found[0], WAVE1)                           # simplest spelling first
        self.assertEqual(str(found[1]), "D♭ C♭ B♯ | E♮ F♯ G♯ A♮")   # the B♯/C♭ swap also fits
        # G#/Ab sounding twice needs both strings on it
        dbl = harp.Pedals.infer({71, 72, 73, 76, 77, 80}, doubles={80})
        self.assertTrue(dbl and all(p.of("G") == 1 and p.of("A") == -1 for p in dbl))


class Midi(unittest.TestCase):
    def test_write_read_and_bars(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "t.mid"
            midi.write(f, [midi.Track("Harp", [(0, 60, 100, 240), (240, 62, 90, 240)], program=46)],
                       ppq=480, tempos=[(0, 600000), (1920, 500000)], time_sigs=[(0, 6, 8), (1440, 12, 8)])
            m = midi.read(f)
        self.assertEqual([(n.pitch, n.velocity, n.start, n.end) for n in m.notes],
                         [(60, 100, 0, 240), (62, 90, 240, 480)])
        self.assertEqual(m.track_names[1], "Harp")
        self.assertEqual((m.bar_start(1), m.bar_start(2), m.bar_start(3), m.bar_start(4)), (0, 1440, 4320, 7200))
        self.assertEqual(m.tick_at(3, 1.5), 4320 + 720)
        for t in (0, 100, 1919, 1920, 5000):
            self.assertEqual(m.tick(m.seconds(t)), t)


class Render(unittest.TestCase):
    def test_even_steps_with_hang(self):
        s0 = gliss.string_near(WAVE1, 60)
        g = gliss.AdLibGliss(WAVE1, [gliss.Sweep(1.0, 1.0 + 0.03 * 3 + 0.06, s0, s0 + 4, 90, hang=2.0)])
        n = g.notes()
        self.assertEqual([x.pitch for x in n], [60, 61, 64, 66, 68])   # C D♭ E F♯ G♯
        self.assertEqual([round(x.time, 4) for x in n], [1.0, 1.03, 1.06, 1.09, 1.15])
        self.assertEqual(n[-1].length, g.release)

    def test_skip_and_enharmonic_double(self):
        p = harp.Pedals.parse("C D E F G# Ab B")
        a = gliss.string_near(p, 76)                                  # E
        g = gliss.AdLibGliss(p, [gliss.Sweep(0, 1, a, a + 4)])        # E F G♯ A♭ B
        self.assertEqual([x.pitch for x in g.notes()], [76, 77, 80, 80, 83])
        g.sweeps[0].skip = [a + 1]
        self.assertEqual([x.pitch for x in g.notes()], [76, 80, 80, 83])

    def test_dynamics_and_json(self):
        g = gliss.AdLibGliss(WAVE1, [gliss.Sweep(0, 1, 20, 30)], dynamics=[(0, 40), (1, 120)])
        v = [x.velocity for x in g.notes()]
        self.assertEqual((v[0], v[-1]), (40, 120))
        self.assertEqual(v, sorted(v))
        self.assertEqual(gliss.AdLibGliss.from_dict(g.to_dict()), g)


class FitAndPlan(unittest.TestCase):
    def test_fit_reproduces_rendered_notes(self):
        g = gliss.plan(10.0, 13.0, WAVE1, low=56, high=84, first=84, last=56, seed=3)
        notes = [(x.time, x.pitch, x.velocity, x.layer) for x in g.notes()]
        r = gliss.fit(notes)
        self.assertEqual(r.gliss.pedals, WAVE1)
        self.assertEqual(len(r.gliss.sweeps), len(g.sweeps))
        c = gliss.compare(notes, r.gliss.notes())
        self.assertEqual((c["matched"], c["missing"], c["extra"]), (len(notes), [], []))
        self.assertLess(c["max_ms"], 0.5)

    def test_plan_shape(self):
        g = gliss.plan(0.0, 3.0, WAVE1, low=56, high=84, first=84, last=56, sweep=0.6)
        self.assertEqual("".join("U" if s.direction > 0 else "D" for s in g.sweeps), "DUDUD")
        self.assertAlmostEqual(g.sweeps[0].start, 0.0)
        self.assertAlmostEqual(g.sweeps[-1].end, 3.0)
        strs = harp.strings(WAVE1)
        self.assertEqual(strs[g.sweeps[0].from_string].pitch, 84)
        self.assertEqual(strs[g.sweeps[-1].to_string].pitch, 56)
        for a, b in zip(g.sweeps, g.sweeps[1:]):     # a turn moves on to the neighbouring string
            self.assertEqual(b.from_string, a.to_string - a.direction)
            step = (b.end - b.start) / (abs(b.to_string - b.from_string) - 1 + b.hang)
            self.assertAlmostEqual(b.start - a.end, step)          # ... one regular step later
            self.assertEqual(a.layer, b.layer)                     # one hand plays the wave
        self.assertEqual(gliss.physical_checks(g), [])
        rp = gliss.plan(0.0, 3.0, WAVE1, low=56, high=84, first=84, last=56, sweep=0.6, repluck=True)
        self.assertEqual(rp.sweeps[1].from_string, rp.sweeps[0].to_string)
        self.assertTrue(any("sounds twice" in w for w in gliss.physical_checks(rp)))
        pitches = {x.pitch % 12 for x in g.notes()}
        self.assertEqual(pitches, WAVE1.pitch_classes)
        self.assertEqual(gliss.plan(0.0, 3.0, WAVE1, low=56, high=84, seed=7).to_dict(),
                         gliss.plan(0.0, 3.0, WAVE1, low=56, high=84, seed=7).to_dict())

    def test_plan_sawtooth_overlaps(self):
        g = gliss.plan(0.0, 2.0, WAVE2, low=55, high=82, pattern="UUUD", overlap=0.3)
        s = g.sweeps
        self.assertLess(s[1].start, s[0].end)                           # overlapping rises
        self.assertNotEqual(s[0].layer, s[1].layer)
        self.assertLess(s[1].from_string, s[0].to_string)               # each rise restarts low
        self.assertAlmostEqual(s[-1].end, 2.0)
        self.assertEqual([x.layer for x in s], [0, 1, 0, 0])              # hand over hand, then turn
        self.assertEqual(gliss.physical_checks(g), [])

    def test_physical_checks(self):
        s = gliss.Sweep
        three = gliss.AdLibGliss(WAVE1, [s(0, 1, 20, 30, layer=0), s(0.2, 1, 22, 32, layer=1),
                                         s(0.4, 1, 21, 31, layer=0)])
        w = gliss.physical_checks(three)
        self.assertTrue(any("3 sweeps at once" in x for x in w))
        self.assertTrue(any("hand 1 starts before finishing" in x for x in w))


class Picks(unittest.TestCase):
    """The user's preferred planned versions (2026-11-01): gliss 1 seed 1, gliss 2 seed 2.
    If a planner change alters them on purpose, re-record with
    `python -m doricokit.gliss fit … --json OUT --replan …` (writes OUT-replan.json)."""

    def test_picks_are_reproduced_and_playable(self):
        for f in sorted(PICKS.glob("*-pick.json")):
            d = json.loads(f.read_text())
            args = dict(d["plan"], pedals=harp.Pedals.parse(d["plan"]["pedals"]))
            g = gliss.plan(**args)
            self.assertEqual(g.to_dict(), d["spec"], f.name)
            self.assertEqual(gliss.physical_checks(g), [], f.name)


@unittest.skipUnless(TREX.is_file(), f"{TREX} missing")
class TrexReference(unittest.TestCase):
    """The user's crafted ad lib glissandi (lead-ins in m14 and m25 are separate notation)."""

    def setUp(self):
        self.m = midi.read(TREX)

    def run_fit(self, start, end):
        notes = gliss.select(self.m, self.m.tick_at(*start), self.m.tick_at(*end))
        r = gliss.fit(notes)
        return notes, r, gliss.compare(notes, r.gliss.notes())

    def test_gliss1_m15_to_m18(self):
        notes, r, c = self.run_fit((15, 0), (18, 0))
        self.assertEqual(r.gliss.pedals, WAVE1)
        self.assertEqual(len(notes), 88)
        self.assertEqual("".join(s["dir"][0] for s in r.sweeps), "dudud")
        self.assertEqual(c["matched"], 88)
        self.assertEqual(sum("sounds twice" in w for w in r.warnings), 4)   # crafted turns re-pluck
        self.assertLess(c["max_ms"], 0.1)

    def test_gliss2_m26_to_m28_beat4(self):
        notes, r, c = self.run_fit((26, 0), (28, 4.5))
        self.assertEqual(r.gliss.pedals, WAVE2)
        self.assertEqual(len(notes), 202)
        self.assertEqual(c["matched"], 201)                             # the F6 outside the pedals
        self.assertEqual([p for _, p in c["missing"]], [89])
        self.assertTrue(any("[89]" in w for w in r.warnings))
