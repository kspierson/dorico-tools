"""Standard orchestral names resolve before fuzzy matching (needs a Dorico install; skipped otherwise)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f2d.dorico.install import ALIAS_INDEX, DoricoInstall, _clean_name  # noqa: E402

try:
    INSTALL = DoricoInstall()
except FileNotFoundError:
    INSTALL = None


class Keys(unittest.TestCase):
    def test_find_key(self):
        from f2d import keys
        self.assertEqual(keys.find_key("Trumpet in C"), "c")
        self.assertEqual(keys.find_key("B\u266d Clarinet 2"), "bflat")
        self.assertEqual(keys.find_key("Clarinets 1"), None)
        self.assertEqual(keys.strip_key("Trumpet in C 1"), "Trumpet 1")
        self.assertEqual(keys.family("Horns 1 3"), "horn")
        self.assertEqual(keys.family("English Horn"), None)


class Names(unittest.TestCase):
    def test_clean_name(self):
        self.assertEqual(_clean_name("Cello 1"), "cello")
        self.assertEqual(_clean_name("Horns 1 3"), "horns")
        self.assertEqual(_clean_name("Bass Tbn.\nTuba"), "bass tbn")
        self.assertEqual(ALIAS_INDEX["cfg"], "instrument.wind.contrabassoon")

    @unittest.skipIf(INSTALL is None, "no Dorico install")
    def test_standard_names(self):
        for name, eid in [("Cello 1", "instrument.strings.violoncello"), ("Bass", "instrument.strings.contrabass"),
                          ("Picc.", "instrument.wind.piccolo"), ("G.C.", "instrument.orchestral.unpitched.bass.drum")]:
            self.assertEqual(INSTALL.resolve(None, name, 1)[0], eid, name)
        for name, eid in [("Trumpet in C", "instrument.brass.trumpet.c"), ("C Tpt.", "instrument.brass.trumpet.c"),
                          ("Clarinets 1", "instrument.wind.clarinet.bflat"), ("Horns 1 3", "instrument.brass.horn.f"),
                          ("E\u266d Clarinet", "instrument.wind.clarinet.eflat"),
                          ("Bass Clarinet", "instrument.wind.clarinet.bass.bflat")]:
            self.assertEqual(INSTALL.resolve(None, name, 1, None)[0], eid, name)
        for eid in ALIAS_INDEX.values():
            self.assertIn(eid, INSTALL.instruments)


if __name__ == "__main__":
    unittest.main()
