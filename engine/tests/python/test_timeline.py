"""doricokit.timeline through the bridge, on the user's film reference (skipped when absent)."""
import unittest
from fractions import Fraction
from pathlib import Path

from doricokit import model, timeline

ROOT = Path(__file__).resolve().parents[3]
FILM = ROOT / "dorigit/research/refs/ref-film-v1.dorico"


@unittest.skipUnless(FILM.is_file(), f"{FILM} missing")
class FilmReference(unittest.TestCase):
    def setUp(self):
        self.t = timeline.read(FILM)
        self.score = model.read(FILM)

    def test_markers_land_on_dorico_times(self):
        flow = self.score["flows"][0]
        self.assertTrue(flow["markers"])
        for m in flow["markers"]:
            secs = self.t.seconds(0, m["pos"])
            self.assertAlmostEqual(self.t.clip_time(0, secs), m["time"], delta=0.003)

    def test_timecode_and_round_trip(self):
        info = self.t.info()["flows"][0]
        self.assertEqual(info["frame_rate"]["base"], 25)
        self.assertEqual(self.t.timecode(0, self.t.seconds(0, Fraction(31, 6))), "00:00:05:00")
        span, x = self.t.at_seconds(0, 5.0)
        self.assertAlmostEqual(self.t.notated_seconds(0, Fraction(x).limit_denominator(4800)), 5.0, places=4)
        events = self.t.tempo_events(0)
        self.assertEqual(events[0][0], 0)


if __name__ == "__main__":
    unittest.main()
