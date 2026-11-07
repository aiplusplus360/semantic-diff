import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from semanticdiff.cli import main


def run(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(args)
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_diff_plain(self):
        before = self.write("a.txt", "Return JSON.")
        after = self.write("b.txt", "Return YAML.")
        code, out, _ = run(["diff", before, after])
        self.assertEqual(code, 0)
        self.assertIn("severity: high", out)

    def test_diff_json(self):
        before = self.write("a.txt", "Be concise.")
        after = self.write("b.txt", "Be concise. Never invent facts.")
        code, out, _ = run(["diff", before, after, "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["severity"], "medium")

    def test_fail_on_breaking(self):
        before = self.write("a.txt", "Never invent facts.")
        after = self.write("b.txt", "Be concise.")
        code, _, _ = run(["diff", before, after, "--fail-on-breaking"])
        self.assertEqual(code, 1)

    def test_no_failure_for_additive_change(self):
        before = self.write("a.txt", "Be concise.")
        after = self.write("b.txt", "Be concise. Return JSON.")
        code, _, _ = run(["diff", before, after, "--fail-on-breaking"])
        self.assertEqual(code, 0)

    def test_fail_on_change(self):
        before = self.write("a.txt", "Be concise.")
        after = self.write("b.txt", "Be concise. Return JSON.")
        code, _, _ = run(["diff", before, after, "--fail-on-change"])
        self.assertEqual(code, 1)

    def test_no_change(self):
        before = self.write("a.txt", "Be concise.")
        code, out, _ = run(["diff", before, before])
        self.assertEqual(code, 0)
        self.assertIn("no behavioural change", out)

    def test_classify(self):
        path = self.write("p.txt", "You are a reviewer. Return JSON.")
        code, out, _ = run(["classify", path, "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual([row["category"] for row in payload["clauses"]],
                         ["role", "format"])

    def test_classify_plain(self):
        path = self.write("p.txt", "Never invent facts.")
        code, out, _ = run(["classify", path])
        self.assertEqual(code, 0)
        self.assertIn("[constraint]", out)

    def test_missing_file(self):
        with self.assertRaises(SystemExit):
            run(["classify", str(self.root / "nope.txt")])


if __name__ == "__main__":
    unittest.main()
