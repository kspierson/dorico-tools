"""The cleaner (f2d/clean.py): dedupe and link on small generated projects."""
from __future__ import annotations

import sys
import tempfile
import unittest
from fractions import Fraction as F
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from f2d import ir  # noqa: E402
from f2d.clean import clean  # noqa: E402
from f2d.dorico import writer  # noqa: E402
from f2d.dorico.read import read_project  # noqa: E402
from f2d.review import Reviewer  # noqa: E402
from test_core import _FakeInstall  # noqa: E402


def _project(path: Path, dyn_a, dyn_b, link="none", techniques=()) -> None:
    """Two flute players with the same notes; dyn_a / dyn_b: dynamics on each staff."""
    players, staves = [], []
    for k, dyns in enumerate((dyn_a, dyn_b)):
        inst = ir.Instrument(id=f"I{k}", name="Flute")
        players.append(ir.Player(id=f"P{k}", name=f"Flute {k + 1}", instruments=[inst]))
        chords = [ir.Chord(pos=F(i), dur=F(1), notated=F(1), pitches=[ir.Pitch(72, "C")]) for i in range(8)]
        st = ir.Staff(instrument=f"I{k}", index=0, voices=[ir.Voice(index=0, chords=chords)],
                      dynamics=[ir.Dynamic(pos=p, kind=d) for p, d in dyns])
        if k == 0:
            st.techniques = list(techniques)
        staves.append(st)
    flow = ir.Flow(id="F1", title="t", length=F(8), time_signatures=[ir.TimeSignature(pos=F(0), num=4, den=4)],
                   key_signatures=[ir.KeySignature(pos=F(0), fifths=0)], staves=staves,
                   bar_starts=[F(0), F(4)])
    opts = writer.Options(link_dynamics=link)
    writer.DoricoWriter(ir.Score(players=players, flows=[flow]), _FakeInstall(), opts).write(path)


def _left(path):
    return [f.check for f in Reviewer(read_project(path)).run() if f.check in ("could-link", "duplicate")]


class Clean(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_link_identical_section_dynamics(self):
        src, out = self.d / "a.dorico", self.d / "b.dorico"
        _project(src, [(F(0), "mf")], [(F(0), "mf")])
        self.assertEqual(_left(src), ["could-link"])
        changes = clean(src, out)
        self.assertEqual([c.check for c in changes], ["link"])
        self.assertEqual(_left(out), [])
        groups = [g for fl in read_project(out).flows for st in fl.staves for g in st.dynamics]
        self.assertEqual(len({g.element for g in groups}), 1)

    def test_dedupe(self):
        src, out = self.d / "a.dorico", self.d / "b.dorico"
        tech = [ir.Technique(pos=F(1), text="pizz.", kind="pizz"), ir.Technique(pos=F(1), text="pizz.", kind="pizz")]
        _project(src, [(F(0), "p"), (F(0), "p")], [(F(0), "f")], techniques=tech)
        changes = clean(src, out, rules=["dedupe"])
        self.assertEqual(sorted(c.message.split(" (")[0] for c in changes),
                         ["removed a second identical dynamics group", "removed a second identical technique pta.pizzText"])
        self.assertEqual(_left(out), [])

    def test_nothing_to_do_copies_the_file(self):
        src, out = self.d / "a.dorico", self.d / "b.dorico"
        _project(src, [(F(0), "mf")], [(F(0), "f")])
        self.assertEqual(clean(src, out), [])
        self.assertEqual(src.read_bytes(), out.read_bytes())

    def test_never_overwrites_the_input(self):
        src = self.d / "a.dorico"
        _project(src, [(F(0), "mf")], [(F(0), "mf")])
        with self.assertRaises(ValueError):
            clean(src, src)

    def test_dry_run_writes_nothing(self):
        src, out = self.d / "a.dorico", self.d / "b.dorico"
        _project(src, [(F(0), "mf")], [(F(0), "mf")])
        self.assertEqual(len(clean(src, out, dry_run=True)), 1)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
