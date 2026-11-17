"""Unit tests for the doricokit Python bridge (no corpus needed)."""
import tempfile
import unittest
from pathlib import Path

from doricokit import container, paths
from doricokit import format as dtn
from doricokit.format import Document, Node


def sample() -> Document:
    empty = Node("events", "", True)
    return Document(Node("score", None, False, [
        Node("title", "Fl\u00fbte & <Oboe>\r"),
        Node("flows", None, True, [Node("flow", None, False, [Node("flowID", "0"), empty])]),
        Node("blank", ""),
    ]), marker=3)


class Format(unittest.TestCase):
    def test_round_trip(self):
        d = sample()
        b = dtn.encode(d)
        again = dtn.decode(b)
        self.assertEqual(again, d)
        self.assertEqual(dtn.encode(again), b)
        self.assertEqual(again.marker, 3)

    def test_xml(self):
        d = sample()
        x = dtn.to_xml(d)
        self.assertIn("<?dorigit-dtn-marker 3?>", x)
        self.assertIn("Fl\u00fbte &amp; &lt;Oboe&gt;&#13;", x)
        self.assertIn('<events array="true"/>', x)
        self.assertEqual(dtn.from_xml(x), d)
        self.assertEqual(dtn.from_xml(x.encode()), d)
        self.assertNotIn("dorigit-dtn-marker", dtn.to_xml(d, with_marker=False))

    def test_shared_strings_and_editing(self):
        d = dtn.decode(dtn.encode(sample()))
        flow = d.root.find("flows/flow")
        self.assertEqual(flow.text("flowID"), "0")
        flow.children.append(Node("extra", "1"))      # tools edit trees in place
        flow.child("flowID").value = "7"
        self.assertEqual(dtn.decode(dtn.encode(d)).root.find("flows/flow/flowID").value, "7")

    def test_errors(self):
        with self.assertRaises(ValueError):
            dtn.decode(b"\x05\x00\x00\x00")
        with self.assertRaises(ValueError):
            dtn.encode(Document(Node("x")))           # neither value nor children
        with self.assertRaises(TypeError):
            dtn.encode(Document(Node("x", 5)))         # value must be str


class Container(unittest.TestCase):
    def test_round_trip_keeps_entries(self):
        ents = [
            container.Entry("mimetype", b"application/x-dorico", False, (2021, 11, 28, 18, 35, 2), False),
            container.Entry("META-INF/", b"", True, (2021, 11, 28, 17, 55, 52), True),
            container.Entry("score.dtn", dtn.encode(sample()), False, (2021, 11, 28, 18, 35, 2), True),
        ]
        again = container.read_bytes(container.to_bytes(ents))
        self.assertEqual(again, ents)
        self.assertEqual(container.score(again), sample())

    def test_write_refuses_source(self):
        with tempfile.TemporaryDirectory() as t:
            src = Path(t) / "a.dorico"
            ents = [container.Entry("score.xml", dtn.to_xml(sample(), False).encode())]
            container.write(src, ents)
            with self.assertRaises(ValueError):
                container.write(src, ents, protect=src)
            doc = container.score(container.read(src))
            doc.root.child("blank").value = "x"
            container.set_score(ents, doc)
            self.assertIn(b"<blank>x</blank>", ents[0].data)


class Paths(unittest.TestCase):
    def test_conversion(self):
        self.assertEqual(paths.windows_to_wsl(r"C:\Users\x"), "/mnt/c/Users/x")
        self.assertEqual(paths.wsl_to_windows("/home/k/a", "U"), r"\\wsl.localhost\U\home\k\a")

    def test_corpus_has_entries(self):
        c = paths.corpus()
        self.assertIn("projects", c)
        self.assertTrue(c["test_files"].is_absolute())


if __name__ == "__main__":
    unittest.main()
