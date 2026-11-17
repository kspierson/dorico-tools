"""Passage markings ("stacc., brillante" …) and open hairpins.

    cd dorico-hp && python3 -m unittest discover -s tests
"""
from __future__ import annotations

import sys
import unittest
from fractions import Fraction as F
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from doricohp import engine, passages  # noqa: E402
from doricohp.model import Note, Part, Score, _slur_roles  # noqa: E402


class Words(unittest.TestCase):
    def check(self, text, flags):
        self.assertEqual(passages.words_to_flags(text), set(flags), text)

    def test_staccato_words(self):
        self.check("staccato", {"staccato"})
        self.check("stacc.", {"staccato"})
        self.check("staccatissimo", {"staccato", "short"})
        self.check("secco", {"staccato", "short"})

    def test_brillante(self):
        self.check("stacc., brillante", {"staccato", "light"})
        self.check("brill.", {"light"})
        # misspellings are not read (the user: a typo, to be flagged by a reviewer, not played)
        self.check("brilliante", set())

    def test_abbreviations_with_a_dot(self):
        # \b after the dot never matched before 2026-10-31
        self.check("marc.", {"marcato"})
        self.check("ten.", {"tenuto"})
        self.check("sost.", {"tenuto"})
        self.check("ord.", {"reset"})

    def test_negations(self):
        self.check("non stacc.", {"reset"})
        self.check("non legato", {"detache"})
        self.check("legato", {"legato"})

    def test_no_false_hits(self):
        self.check("tender", set())
        self.check("nation", set())


class TechniqueFlags(unittest.TestCase):
    def test_custom_appearance_on_builtin_technique_reads_words_too(self):
        self.assertEqual(passages.technique_flags("pt.staccato", "staccato"), {"staccato"})
        self.assertEqual(passages.technique_flags("pt.staccato", "stacc., brillante"), {"staccato", "light"})

    def test_custom_playback_technique_belongs_to_the_map(self):
        # ET score: "B Spiccato" switches a Berlin Strings patch
        self.assertEqual(passages.technique_flags("pt.user.b_spicc", "B Spiccato"), set())

    def test_unknown_builtin_falls_back_to_words(self):
        self.assertEqual(passages.technique_flags("pt.somethingElse", "leggiero"), {"light"})


def notes_with_slurs(spec, slurs):
    """spec: (pos, dur) in crotchets; slurs: (start, end)."""
    ns = [Note("Fl", F(p), F(d), 72 + i) for i, (p, d) in enumerate(spec)]
    _slur_roles(ns, [(F(a), F(b)) for a, b in slurs])
    return ns


class EffectiveArticulations(unittest.TestCase):
    def test_unslurred_notes_take_the_passage(self):
        n = notes_with_slurs([(0, F(1, 8))], [])[0]
        self.assertEqual(passages.effective_articulations(n, {"staccato"}), {"staccato"})
        self.assertEqual(passages.effective_articulations(n, {"staccato", "short"}), {"staccatissimo"})

    def test_slurred_notes_keep_their_length(self):
        a, b, c = notes_with_slurs([(0, F(1, 8)), (F(1, 8), F(1, 8)), (F(1, 4), F(1, 8))], [(0, F(1, 8))])
        self.assertEqual((a.slur, b.slur, c.slur), ("start", "end", None))
        self.assertEqual(passages.effective_articulations(a, {"staccato"}), frozenset())
        # slur end running into the next note: undotted in the user's playback copy
        self.assertEqual(passages.effective_articulations(b, {"staccato"}, rest_after=False), frozenset())
        # slur end before a rest: lifted
        self.assertEqual(passages.effective_articulations(b, {"staccato"}, rest_after=True), {"staccato"})

    def test_own_marks_win(self):
        n = Note("Fl", F(0), F(1, 4), 72, frozenset({"tenuto"}))
        self.assertEqual(passages.effective_articulations(n, {"staccato"}), {"tenuto"})


class OpenHairpins(unittest.TestCase):
    D = {"hairpin_default_steps": 2.0, "open_hairpin": "swell", "open_hairpin_return_bars": 1.0}

    def score(self, hairpins, dynamics, notes):
        part = Part("Fl", "Flute", "woodwind", notes=notes, dynamics=dynamics, hairpins=hairpins)
        return Score("t", [part], [F(4 * i) for i in range(8)]), part

    def test_returns_by_next_phrase(self):
        # crotchets 0..7, rest at 8, phrase restarts at 9; cresc 4->6 with no end dynamic
        notes = [Note("Fl", F(i), F(1), 72) for i in range(8)] + [Note("Fl", F(9), F(1), 72)]
        sc, part = self.score([(F(4), F(6), "cresc")], [(F(0), "mf"), (F(20), "p")], notes)
        contrib = []
        self.assertEqual(engine.open_hairpin_returns(sc, part, self.D, contrib), 1)
        c = contrib[0]
        self.assertEqual(engine.level_at(c, F(6)), 0.0)        # the peak note keeps the rise
        self.assertEqual(engine.level_at(c, F(9)), -2.0)       # back where it was by the next phrase
        self.assertEqual(engine.level_at(c, F(19)), -2.0)      # ... until the next dynamic
        self.assertEqual(engine.level_at(c, F(20)), 0.0)

    def test_target_dynamic_is_not_open(self):
        notes = [Note("Fl", F(i), F(1), 72) for i in range(8)]
        sc, part = self.score([(F(2), F(4), "cresc")], [(F(0), "mp"), (F(4), "f")], notes)
        self.assertEqual(engine.open_hairpin_returns(sc, part, self.D, []), 0)

    def test_stay_setting(self):
        notes = [Note("Fl", F(i), F(1), 72) for i in range(8)]
        sc, part = self.score([(F(2), F(4), "cresc")], [(F(0), "mp")], notes)
        self.assertEqual(engine.open_hairpin_returns(sc, part, {**self.D, "open_hairpin": "stay"}, []), 0)


if __name__ == "__main__":
    unittest.main()
