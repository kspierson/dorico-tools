"""doricokit.edit / findings / review / clean on a real Dorico-saved project."""
import tempfile
import unittest
from pathlib import Path

from doricokit import clean, container, edit, findings, ids, review

SAMPLE = Path(__file__).resolve().parents[1] / "dorico-files" / "ET The Flying Theme mASTER A-rebuilt.dorico"


class Edit(unittest.TestCase):
    def test_no_change_is_byte_identical(self):
        data = SAMPLE.read_bytes()
        self.assertEqual(edit.Project(data).to_bytes(), data)

    def test_save_never_overwrites_the_source(self):
        p = edit.Project.open(SAMPLE)
        with self.assertRaises(ValueError):
            p.save(SAMPLE, protect=SAMPLE)

    def test_remove_event_and_canon(self):
        p = edit.Project.open(SAMPLE)
        fe = p.flows[0]
        eid = next(k for k, (_, e) in fe.events.items() if e.tag == "DynamicGroupEventDefinition")
        fe.remove_event(eid)
        self.assertTrue(p.changed)
        self.assertEqual(ids.check(p.doc), [])
        a = edit.canon(fe.node.find("blocks/array").children[0])
        self.assertEqual(a, edit.canon(fe.node.find("blocks/array").children[0]))


class Clean(unittest.TestCase):
    def test_default_rules_fix_what_the_reviewer_reports(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.dorico"
            changes = clean.clean(SAMPLE, out)
            self.assertTrue(any(c.check == "link" and c.severity == "change" for c in changes))
            left_alone = [c for c in changes if c.severity == "info"]
            self.assertEqual(len(clean.after_check(out)), len(left_alone))  # only those left on purpose
            before, after = container.read(SAMPLE), container.read(out)
            self.assertEqual([e.name for e in before if e.data != next(x for x in after if x.name == e.name).data],
                             ["score.dtn"])
            self.assertEqual(ids.check(container.open_score(out)), [])

    def test_another_tool_can_add_a_rule_and_a_check(self):
        seen = []

        def count_flows(ctx, fl, fe):
            seen.append(fl.name)
            ctx.change("test-count", fl, "", fl.bars[0][0], "looked at this flow")

        def flow_check(ctx, fl):
            ctx.add("test-check", "info", fl, "", fl.bars[0][0], "checked")

        findings.register_rule("test-count", "test only", count_flows, default=False, owner="test")
        findings.register_check("test-check", "test only", flow_check, scope="flow", owner="test")
        try:
            self.assertNotIn("test-count", clean.default_rules())
            changes = clean.clean(SAMPLE, None, ["test-count"], dry_run=True)
            self.assertEqual([c.check for c in changes], ["test-count"])
            self.assertEqual(len(seen), 1)
            found = review.review(SAMPLE, only=["test-check"])
            self.assertEqual([f.check for f in found], ["test-check"])
        finally:
            findings._RULES.pop("test-count", None)
            findings._CHECKS.pop("test-check", None)


if __name__ == "__main__":
    unittest.main()
