"""Writer: dynamic grouping (Round 2, from the user's grouping of file 07) and linking across
staves (shared element, as in the user's own projects); factory library."""
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


def _score(staff_marks):
    """One flute player per entry; each entry = (dynamics, hairpins)."""
    players, staves = [], []
    for k, (dyns, pins) in enumerate(staff_marks, 1):
        inst = ir.Instrument(id=f"I{k}", name="Flute")
        players.append(ir.Player(id=f"P{k}", name="Flute", instruments=[inst]))
        chords = [ir.Chord(pos=F(i), dur=F(1), notated=F(1), pitches=[ir.Pitch(72, "C")]) for i in range(16)]
        staves.append(ir.Staff(instrument=f"I{k}", index=0, voices=[ir.Voice(index=0, chords=chords)],
                               dynamics=[ir.Dynamic(F(p), kind) for p, kind in dyns],
                               hairpins=[ir.Hairpin(F(a), F(b), d) for a, b, d in pins]))
    flow = ir.Flow(id="F1", title="T", length=F(16), staves=staves, bar_starts=[F(0), F(4), F(8), F(12)],
                   time_signatures=[ir.TimeSignature(F(0), 4, 4)], key_signatures=[ir.KeySignature(F(0), 0)])
    return ir.Score(players=players, flows=[flow])


def _groups(doc):
    """[(event position, stream index, element id, [(sub tag, relative position)])], elements."""
    elems = {}
    out = []

    def walk(n, stream):
        if n.tag == "block" and n.child("blockID") is not None:
            stream = n.child("blockID").value
        if n.tag == "DynamicGroupElementDefinition":
            elems[n.child("elementID").value] = (
                n.child("referencingEventIDs").value,
                [(s.tag, s.child("position").value) for s in n.child("subElements").children or []])
        if n.tag == "DynamicGroupEventDefinition":
            out.append((n.child("position").value, stream, n.child("dynamicGroupID").value))
        for c in n.children or []:
            walk(c, stream)

    walk(doc.root, None)
    return out, elems


class DynamicsTests(unittest.TestCase):
    def test_chain_with_small_gap_is_one_group(self):
        # mp at 0, cresc 1..4 (starts one beat later), f at 4, dim 4..6 -> one group
        s = _score([([(0, "mp"), (4, "f")], [(1, 4, "cresc"), (4, 6, "dim")])])
        events, elems = _groups(writer.DoricoWriter(s, _FakeInstall()).build())
        self.assertEqual(len(events), 1)
        subs = elems[events[0][2]][1]
        self.assertEqual([p for _, p in subs], ["0", "1", "4", "4"])

    def test_large_gap_with_rest_splits(self):
        s = _score([([(0, "p")], [(3, 5, "cresc")])])
        v = s.flows[0].staves[0].voices[0]
        v.chords = [c for c in v.chords if c.pos not in (F(1), F(2))]  # rests on beats 2-3
        events, _ = _groups(writer.DoricoWriter(s, _FakeInstall()).build())
        self.assertEqual(len(events), 2)

    def test_large_gap_while_playing_joins(self):
        # notes on every beat: the instrument keeps playing through the 3-beat gap (user's Willow edits)
        s = _score([([(0, "p")], [(3, 5, "cresc")])])
        events, _ = _groups(writer.DoricoWriter(s, _FakeInstall()).build())
        self.assertEqual(len(events), 1)

    def test_fp_is_a_combined_dynamic(self):
        s = _score([([(0, "fp")], [(0, 4, "cresc")])])
        doc = writer.DoricoWriter(s, _FakeInstall()).build()
        tags = []

        def walk(n):
            tags.append(n.tag)
            for c in n.children or []:
                walk(c)
        walk(doc.root)
        self.assertIn("CombinedDynamicDefinition", tags)

    def test_identical_groups_on_two_staves_are_linked(self):
        marks = ([(0, "p")], [(0, 4, "cresc")])
        s = _score([marks, marks, ([(0, "f")], [])])
        events, elems = _groups(writer.DoricoWriter(s, _FakeInstall()).build())
        self.assertEqual(len(events), 3)
        ids = [g for _, _, g in events]
        self.assertEqual(len(set(ids)), 2)  # staves 1+2 share, staff 3 its own
        shared = max(set(ids), key=ids.count)
        self.assertEqual(elems[shared][0].count(",") + 1, 2)

    def test_linking_can_be_disabled(self):
        marks = ([(0, "p")], [])
        s = _score([marks, marks])
        events, _ = _groups(writer.DoricoWriter(s, _FakeInstall(), writer.Options(link_dynamics="none")).build())
        self.assertEqual(len({g for _, _, g in events}), 2)


class StrictLinkingTests(unittest.TestCase):
    def test_different_rhythm_not_linked(self):
        marks = ([(0, "p")], [(0, 4, "cresc")])
        s = _score([marks, marks])
        # staff 2 plays minims instead of crotchets in the phrase
        s.flows[0].staves[1].voices[0].chords = [
            ir.Chord(pos=F(2 * i), dur=F(2), notated=F(2), pitches=[ir.Pitch(60, "C")]) for i in range(8)]
        events, _ = _groups(writer.DoricoWriter(s, _FakeInstall()).build())
        self.assertEqual(len({g for _, _, g in events}), 2)
        events, _ = _groups(writer.DoricoWriter(s, _FakeInstall(), writer.Options(link_dynamics="identical")).build())
        self.assertEqual(len({g for _, _, g in events}), 1)


class FactoryLibraryTests(unittest.TestCase):
    def test_new_project_set_from_install(self):
        from f2d.dorico.install import find_dorico_dir
        from f2d.dorico.library import FactoryLibrary
        try:
            d = find_dorico_dir()
        except Exception:
            d = None
        if d is None:
            self.skipTest("no Dorico install")
        lib = FactoryLibrary(d).build()
        heads = lib.child("noteheadSetDefinitions").child("entities").children or []
        self.assertIn("noteheadset.default", {h.child("entityID").value for h in heads})


if __name__ == "__main__":
    unittest.main()
