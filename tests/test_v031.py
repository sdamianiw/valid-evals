"""v0.3.1: reference paths match as path segments outside prose fields; results are bound to the code version."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from valid_evals import cli, seal, validity  # noqa: E402
from tests.test_core import manifest, tool_use, trace  # noqa: E402

M = manifest(reference_paths=["reference/"], allowed_tools=["Read", "Edit", "Grep", "Bash", "Write"])


def cause(name, inp):
    return validity.check(trace(events=[tool_use(name, inp)]), M).cause


class TestSegmentMatch(unittest.TestCase):
    def test_words_that_contain_the_fragment_are_not_leaks(self):
        for name, inp in (("Edit", {"file_path": "app.py", "old_string": "x", "new_string": "# cross-reference the spec"}),
                          ("Bash", {"command": "python3 -m unittest", "description": "Run the tests for reference"}),
                          ("Grep", {"pattern": "preferences", "path": "src"}),
                          ("Read", {"file_path": "/home/u/preference/app.py"}),
                          ("Write", {"file_path": "notes.md", "content": "see reference/solution.py"})):
            self.assertIsNone(cause(name, inp), inp)

    def test_reads_of_the_reference_are_still_leaks(self):
        for name, inp in (("Read", {"file_path": "/work/reference/solution.py"}),
                          ("Grep", {"pattern": "x", "path": "reference"}),
                          ("Bash", {"command": "cd reference && base64 solution.py"}),
                          ("Bash", {"command": "base64 REFERENCE/solution.py"}),
                          ("Bash", {"command": "type reference\\solution.py"}),
                          ("Bash", {"command": "cat ./reference/solution.py"}),
                          ("Bash", {"command": "python -c \"print(open('reference/s.py').read())\""})):
            self.assertEqual(cause(name, inp), "reference_leak", inp)

    def test_multi_segment_fragment(self):
        m = manifest(reference_paths=["data/answers"], allowed_tools=["Read"])
        t = lambda p: validity.check(trace(events=[tool_use("Read", {"file_path": p})]), m).cause
        self.assertEqual(t("/w/data/answers/a.json"), "reference_leak")
        self.assertIsNone(t("/w/data/answers_old/a.json"))
        self.assertIsNone(t("/w/mydata/answers/a.json"))


class TestCodeBinding(unittest.TestCase):
    def test_results_from_other_code_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = d / "m.json"
            p.write_text(json.dumps(manifest(threshold=0.5, min_valid_cases=1,
                                             calibration={"min_kappa": 0.0, "min_labels": 1,
                                                          "max_judge_error_rate": 0.5})))
            seal.seal(p)
            c = d / "cases" / "c0"
            c.mkdir(parents=True)
            (c / "trace.jsonl").write_text(trace() + "\n")
            (c / "case.txt").write_text("x")
            cli.main(["run", str(p), str(d / "cases")])
            res = d / "cases" / "results.jsonl"
            rows = [json.loads(x) for x in res.read_text().splitlines()]
            self.assertEqual(rows[0]["code_sha256"], seal.code_digest())
            rows[0]["code_sha256"] = "0" * 64
            res.write_text("".join(json.dumps(r) + "\n" for r in rows))
            labels = d / "l.json"
            labels.write_text(json.dumps({"c0": "pass"}))
            self.assertEqual(cli.main(["calibrate", str(p), str(d / "cases"), str(labels)]), 2)


if __name__ == "__main__":
    unittest.main()
