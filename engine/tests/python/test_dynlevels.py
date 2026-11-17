"""doricokit.dynlevels against the dorico-hp test I2 export (2026-11-01).

The MIDI check is skipped when the HPCaptures folder isn't reachable.
"""
import unittest
from pathlib import Path

from doricokit import dynlevels, midi, paths

I2 = Path(paths.corpus()["hp_captures"]) / "dorico" / "test-I2"


class Levels(unittest.TestCase):
    def test_written(self):
        self.assertEqual(dynlevels.level("mf"), 0.5)
        self.assertEqual(dynlevels.level("mp"), -0.5)
        self.assertEqual(dynlevels.level("pppp"), -4)
        self.assertEqual(dynlevels.level("ffff"), 4)
        self.assertEqual(dynlevels.level("f", accent=True), 1.5)
        self.assertAlmostEqual(dynlevels.level("mf", marcato=True), 1.3)
        with self.assertRaises(KeyError):
            dynlevels.level("sfz")

    def test_ranges(self):
        self.assertEqual(dynlevels.to_range(0.5, 1, 127), 76)     # mf, CC11
        self.assertEqual(dynlevels.to_range(0.5, 40, 127), 92)    # mf, velocity
        # mf + marcato: Dorico sent 93; straight lines between the measured points give 92
        self.assertAlmostEqual(dynlevels.to_range(1.3, 1, 127), 93, delta=1)
        self.assertEqual(dynlevels.to_range(-9, 1, 127), 1)
        self.assertAlmostEqual(dynlevels.from_range(76, 1, 127), 0.5)


@unittest.skipUnless(I2.is_dir(), "HPCaptures not reachable")
class AgainstExport(unittest.TestCase):
    def test_written_dynamics_match_the_export(self):
        mid = next(I2.glob("*.mid"))
        m = midi.read(str(mid))
        names = ["pppp", "ppp", "pp", "p", "mp", "mf", "f", "ff", "fff", "ffff"]
        cc = [c for c in m.ctrls if c.track == 2 and c.kind == "cc" and c.number == 11]
        for bar, name in enumerate(names):
            got = [c.value for c in cc if c.tick == bar * 960]
            self.assertEqual(got, [dynlevels.to_range(dynlevels.level(name), 1, 127)], name)
            vel = [n.velocity for n in m.notes if n.track == 2 and n.start == bar * 960]
            self.assertEqual(vel, [dynlevels.to_range(dynlevels.level(name), 40, 127)], name)


if __name__ == "__main__":
    unittest.main()
