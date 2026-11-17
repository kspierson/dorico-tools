"""Findings format v2: additive over v1, IDs filled by the reviewer and the cleaner."""
import json
import tempfile
import unittest
from pathlib import Path

from doricokit import clean, findings, model, review
from doricokit.findings import Finding

SAMPLE = Path(__file__).resolve().parents[1] / "dorico-files" / "ET The Flying Theme mASTER A-rebuilt.dorico"


class FindingsV2(unittest.TestCase):
    def test_v1_reports_still_read(self):
        v1 = {"project": "x.dorico", "checks": {}, "findings": [
            {"check": "range", "severity": "info", "flow": "Flow 1", "player": "Flute", "pos": "7/2",
             "where": "bar 1 beat 4.5", "message": "MIDI 99 outside the standard range"}]}
        head, items = findings.from_json(json.dumps(v1))
        self.assertEqual(head["findings_version"], 1)
        self.assertEqual(items[0].where, "bar 1 beat 4.5")
        self.assertEqual((items[0].events, items[0].change, items[0].bar), ([], None, ""))

    def test_positional_v1_construction_and_round_trip(self):
        f = Finding("not-converted", "info", "", "", "0", "", "text")
        head, items = findings.from_json(findings.to_json([f], "p.dorico"))
        self.assertEqual(head["findings_version"], findings.FINDINGS_VERSION)
        self.assertEqual(items[0].tool, "doricokit")  # filled on output
        self.assertNotIn("change", json.loads(findings.to_json([f], "p"))["findings"][0])

    @unittest.skipUnless(SAMPLE.exists(), "test file A not present")
    def test_review_findings_carry_ids(self):
        found = review.review(SAMPLE)
        self.assertTrue(found)
        score = model.read(SAMPLE)
        flow_ids = {f["id"] for f in score["flows"]}
        events = {n["event_id"] for fl in score["flows"] for p in fl["parts"] for v in p["voices"] for n in v["notes"]}
        events |= {g["event_id"] for fl in score["flows"] for p in fl["parts"] for s in p["staves"] for g in s["dynamics"]}
        events |= {m["event_id"] for fl in score["flows"] for p in fl["parts"] for x in p["voices"] + p["staves"]
                   for m in x["marks"]}
        for f in found:
            self.assertIn(f.flow_id, flow_ids)
            self.assertTrue(f.events, f)
            self.assertTrue(set(f.events) <= events, f)
            self.assertTrue(f.staves, f)
            self.assertIn(f"bar {f.bar} beat", f.where)

    @unittest.skipUnless(SAMPLE.exists(), "test file A not present")
    def test_cleaner_changes_say_before_and_after(self):
        with tempfile.TemporaryDirectory() as d:
            changes = [c for c in clean.clean(SAMPLE, Path(d) / "out.dorico") if c.severity == "change"]
        self.assertTrue(changes)
        for c in changes:
            self.assertTrue(c.events and c.change and c.change["before"] != c.change["after"], c)


if __name__ == "__main__":
    unittest.main()
