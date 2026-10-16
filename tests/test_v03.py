"""v0.3: reference path leaks, judges in an empty cwd, interval and disagreement bounds on the decision,
artifacts bound by hash, provisional decisions until calibration passes."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from valid_evals import calibrate, cli, decide, jury, seal, validity  # noqa: E402
from tests.test_codex import cmd, item, manifest as codex_manifest, trace as codex_trace  # noqa: E402
from tests.test_core import FAKE_JUDGE, manifest, tool_use, trace  # noqa: E402


class TestReferencePaths(unittest.TestCase):
    def m(self, **over):
        return manifest(reference_paths=["reference/"], allowed_tools=["Read", "Grep", "Bash"], **over)

    def test_reading_the_reference_path_is_a_leak_even_without_the_canary(self):
        t = trace(events=[tool_use("Read", {"file_path": "/work/reference/solution.py"})])
        v = validity.check(t, self.m())
        self.assertEqual(v.cause, "reference_leak")
        self.assertIn({"path": "reference/"}, v.details["reference_leak"])

    def test_transformed_read_through_bash_is_a_leak(self):
        t = trace(events=[tool_use("Bash", {"command": "base64 reference/solution.py"})])
        self.assertEqual(validity.check(t, self.m()).cause, "reference_leak")

    def test_other_paths_are_fine(self):
        t = trace(events=[tool_use("Read", {"file_path": "/work/app.py"})])
        self.assertTrue(validity.check(t, self.m()).valid)

    def test_codex_command_and_file_change_paths(self):
        m = codex_manifest(reference_paths=["reference/"])
        self.assertEqual(validity.check(codex_trace(cmd("cat reference/solution.py", "x")), m).cause,
                         "reference_leak")
        fc = item("file_change", changes=[{"path": "reference/solution.py", "kind": "update"}], status="completed")
        self.assertEqual(validity.check(codex_trace(fc), m).cause, "reference_leak")

    def test_seal_rejects_bad_reference_paths(self):
        for bad in ("reference/", [""], [3]):
            with self.assertRaises(seal.SealError):
                seal.validate(manifest(reference_paths=bad))


class TestJudgeIsolation(unittest.TestCase):
    def test_judge_runs_in_an_empty_directory(self):
        probe = ("import json, os, sys; sys.stdin.read(); "
                 "print(json.dumps({'verdict': 'fail' if os.listdir('.') else 'pass'}))")
        judges = [{"name": "a", "vendor": "x", "cmd": [sys.executable, "-c", probe]},
                  {"name": "b", "vendor": "y", "cmd": [sys.executable, "-c", probe]}]
        self.assertEqual(jury.judge("case", judges).verdict, "PASS")


def sealed(d: Path, **over) -> Path:
    p = d / "manifest.json"
    p.write_text(json.dumps(manifest(**over)))
    seal.seal(p)
    return p


def rows(verdicts):
    return [{"case": f"c{i}", "valid": True, "verdict": v} for i, v in enumerate(verdicts)]


class TestDecisionUncertainty(unittest.TestCase):
    def test_wilson_interval(self):
        with tempfile.TemporaryDirectory() as d:
            dec = decide.decide(sealed(Path(d)), rows(["PASS"] * 8 + ["FAIL"] * 2))
        lo, hi = dec.interval
        self.assertAlmostEqual(lo, 0.4902, 3)
        self.assertAlmostEqual(hi, 0.9433, 3)

    def test_disagreements_give_bounds_not_a_changed_result(self):
        with tempfile.TemporaryDirectory() as d:
            dec = decide.decide(sealed(Path(d)), rows(["PASS"] * 4 + ["FAIL", "DISAGREE", "DISAGREE"]))
        self.assertEqual(dec.value, 0.8)
        self.assertEqual(dec.bounds, (4 / 7, 6 / 7))


class TestBoundArtifacts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.cases = self.d / "cases"
        for i in range(3):
            c = self.cases / f"c{i}"
            c.mkdir(parents=True)
            (c / "trace.jsonl").write_text(trace() + "\n")
            (c / "case.txt").write_text("case")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main([str(a) for a in args])
        return code, out.getvalue()

    def test_run_records_hashes_and_is_provisional_when_calibration_is_sealed(self):
        p = sealed(self.d, calibration={"min_kappa": 0.6, "min_labels": 2, "max_judge_error_rate": 0.5})
        code, out = self.run_cli("run", p, self.cases)
        rows = [json.loads(x) for x in (self.cases / "results.jsonl").read_text().splitlines()]
        self.assertTrue(all(len(r["trace_sha256"]) == 64 for r in rows))
        summary = json.loads(next(x for x in out.splitlines() if x.startswith("{")))
        self.assertEqual(len(summary["results_sha256"]), 64)
        self.assertEqual(summary["calibration"], "pending")
        self.assertIn("PROVISIONAL", out)

    def test_run_without_calibration_block_is_not_provisional(self):
        code, out = self.run_cli("run", sealed(self.d), self.cases)
        self.assertNotIn("PROVISIONAL", out)

    def test_calibrate_gives_the_final_decision_with_counts_and_hash(self):
        p = sealed(self.d, calibration={"min_kappa": 0.0, "min_labels": 2, "max_judge_error_rate": 0.5},
                   judges=[{"name": "a", "vendor": "anthropic", "cmd": [sys.executable, FAKE_JUDGE, "pass"]},
                           {"name": "b", "vendor": "openai", "cmd": [sys.executable, FAKE_JUDGE, "pass"]}])
        r = [{"case": f"c{i}", "valid": True, "verdict": v, "votes": {"a": a, "b": b}}
             for i, (v, a, b) in enumerate([("PASS", "pass", "pass"), ("FAIL", "fail", "fail"),
                                            ("PASS", "pass", "pass")])]
        rep = calibrate.calibrate(p, r, {"c0": "pass", "c1": "fail", "c2": "pass"})
        self.assertEqual(rep["pairs"]["a~b"]["counts"], {"pass_pass": 2, "pass_fail": 0, "fail_pass": 0, "fail_fail": 1})
        self.assertIn("decision", rep)
        self.assertFalse(rep["final"])  # pass rate 2/3 under the sealed 0.8 bar

    def test_cli_calibrate_exit_follows_the_final_decision(self):
        p = sealed(self.d, calibration={"min_kappa": 0.0, "min_labels": 2, "max_judge_error_rate": 0.5}, min_valid_cases=2)
        r = [{"case": f"c{i}", "valid": True, "verdict": v, "votes": {"a": a, "b": b}}
             for i, (v, a, b) in enumerate([("PASS", "pass", "pass"), ("FAIL", "fail", "fail")])]
        (self.cases / "results.jsonl").write_text("".join(json.dumps(x) + "\n" for x in r))
        labels = self.d / "labels.json"
        labels.write_text(json.dumps({"c0": "pass", "c1": "fail"}))
        code, out = self.run_cli("calibrate", p, self.cases, labels)
        self.assertEqual(code, 1)  # calibrated, but 0.5 is under the sealed 0.8 bar
        self.assertIn(json.loads(out.splitlines()[0])["results_sha256"], out)


if __name__ == "__main__":
    unittest.main()
