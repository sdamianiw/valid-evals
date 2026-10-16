"""Round 2 red team findings on v0.3, each reproduced before its fix."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from valid_evals import cli, jury, seal, validity  # noqa: E402
from tests.test_codex import CLEAN as CODEX_CLEAN, manifest as codex_manifest  # noqa: E402
from tests.test_core import FAKE_JUDGE, manifest, tool_result, tool_use, trace  # noqa: E402
from tests.test_redteam import dump, lines  # noqa: E402

CAL = {"min_kappa": 0.0, "min_labels": 1, "max_judge_error_rate": 0.5}


def leak_trace(content: str) -> str:
    evs = lines(trace(events=[tool_use("Read", {"file_path": "x"}), tool_result("placeholder")]))
    for e in evs:
        if e["type"] == "user" and isinstance(e["message"]["content"], list):
            e["message"]["content"][0]["content"] = content
    return dump(evs)


class TestA_CalibrateRechecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.cases = self.d / "cases"
        for i in range(2):
            c = self.cases / f"c{i}"
            c.mkdir(parents=True)
            (c / "trace.jsonl").write_text(trace(model="claude-other") + "\n")
            (c / "case.txt").write_text("case")
        self.labels = self.d / "labels.json"
        self.labels.write_text(json.dumps({"c0": "pass", "c1": "pass"}))

    def tearDown(self):
        self.tmp.cleanup()

    def manifest_file(self, name, **over):
        p = self.d / name
        p.write_text(json.dumps(manifest(**{"threshold": 0.5, "min_valid_cases": 1, "calibration": CAL, **over})))
        seal.seal(p)
        return p

    def test_results_from_another_manifest_are_refused(self):
        lenient = self.manifest_file("lenient.json", allowed_models=["claude-other"])
        strict = self.manifest_file("strict.json")
        cli.main(["run", str(lenient), str(self.cases)])
        self.assertEqual(cli.main(["calibrate", str(strict), str(self.cases), str(self.labels)]), 2)

    def test_edited_validity_or_verdict_is_refused(self):
        strict = self.manifest_file("strict.json")
        cli.main(["run", str(strict), str(self.cases)])
        res = self.cases / "results.jsonl"
        rows = [json.loads(x) for x in res.read_text().splitlines()]
        for r in rows:
            r.update(valid=True, cause=None, verdict="PASS", votes={"a": "pass", "b": "pass"})
        res.write_text("".join(json.dumps(r) + "\n" for r in rows))
        self.assertEqual(cli.main(["calibrate", str(strict), str(self.cases), str(self.labels)]), 2)

    def test_verdict_must_follow_from_votes(self):
        good = self.manifest_file("good.json", allowed_models=["claude-other"])
        cli.main(["run", str(good), str(self.cases)])
        res = self.cases / "results.jsonl"
        rows = [json.loads(x) for x in res.read_text().splitlines()]
        rows[0]["votes"] = {"a": "pass", "b": "fail"}  # verdict still PASS
        res.write_text("".join(json.dumps(r) + "\n" for r in rows))
        self.assertEqual(cli.main(["calibrate", str(good), str(self.cases), str(self.labels)]), 2)

    def test_uncalibrated_jury_is_no_decision_exit_2(self):
        good = self.manifest_file("good.json", allowed_models=["claude-other"],
                                  calibration={"min_kappa": 0.9, "min_labels": 1, "max_judge_error_rate": 0.5})
        cli.main(["run", str(good), str(self.cases)])
        self.labels.write_text(json.dumps({"c0": "fail", "c1": "pass"}))
        self.assertEqual(cli.main(["calibrate", str(good), str(self.cases), str(self.labels)]), 2)


class TestB_Matching(unittest.TestCase):
    def test_dated_allowed_id_matches_only_that_snapshot(self):
        t = trace(model="claude-x-20241022", events=[tool_use("Read", {}, model="claude-x-20241022")])
        self.assertEqual(validity.check(t, manifest(allowed_models=["claude-x-20240620"])).cause, "model_mismatch")
        self.assertTrue(validity.check(t, manifest(allowed_models=["claude-x"])).valid)

    def test_canary_in_any_json_escape_form(self):
        for canary, stored in (("<CANARY-7f3a>", "\\u003cCANARY-7f3a\\u003e"), ("CANARY/7f3a", "CANARY\\/7f3a"),
                               ("café-CANARY", "caf\\u00E9-CANARY"), ("k\U0001f511-CANARY", "k\\ud83d\\udd11-CANARY"),
                               ("CANARY-7f3a", "\\u0043ANARY-7f3a")):
            text = leak_trace("PLACE").replace("PLACE", stored)
            self.assertEqual(validity.check(text, manifest(canaries=[canary])).cause, "reference_leak", stored)

    def test_reference_paths_normalized(self):
        m = manifest(reference_paths=["reference/"], allowed_tools=["Read", "Grep", "Bash"])
        for name, inp in (("Grep", {"pattern": "x", "path": "reference"}),
                          ("Bash", {"command": "cd reference && base64 solution.py"}),
                          ("Bash", {"command": "base64 REFERENCE/solution.py"}),
                          ("Bash", {"command": "type reference\\solution.py"})):
            self.assertEqual(validity.check(trace(events=[tool_use(name, inp)]), m).cause, "reference_leak", inp)
        q = manifest(reference_paths=['ref"s/'], allowed_tools=["Read"])
        self.assertEqual(validity.check(trace(events=[tool_use("Read", {"file_path": 'ref"s/a'})]), q).cause,
                         "reference_leak")


class TestC_TraceShape(unittest.TestCase):
    def test_claude_events_inside_a_codex_trace(self):
        base = lines(CODEX_CLEAN)
        m = codex_manifest()
        for extra in ({"type": "result", "subtype": "error_max_turns", "is_error": True},
                      tool_use("Read", {}, model="claude-other"),
                      {"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": "hint"}}):
            self.assertEqual(validity.check(dump(base + [extra]), m).cause, "run_error", extra)

    def test_codex_needs_one_started_turn_before_completion(self):
        evs = [{"type": "thread.started", "thread_id": "t"}, {"type": "turn.completed", "usage": {}}]
        self.assertEqual(validity.check(dump(evs), codex_manifest()).cause, "run_error")

    def test_unparsable_line_is_a_run_error(self):
        evs = trace().splitlines()
        evs.insert(3, '{"type": "assistant", "message": {"model": "claude-other"')
        self.assertEqual(validity.check("\n".join(evs), manifest()).cause, "run_error")
        codex = CODEX_CLEAN.splitlines()
        codex.insert(2, '{"type": "item.completed", "item": {"type": "mcp_tool_call"')
        self.assertEqual(validity.check("\n".join(codex), codex_manifest()).cause, "run_error")

    def test_init_after_agent_events(self):
        evs = lines(trace())
        init = evs.pop(0)
        evs.insert(2, init)
        self.assertEqual(validity.check(dump(evs), manifest()).cause, "run_error")


class TestD_Seal(unittest.TestCase):
    def test_threshold_outside_0_1(self):
        for t in (-0.5, 1.5):
            with self.assertRaises(seal.SealError):
                seal.validate(manifest(threshold=t))

    def test_same_cmd_twice_is_one_judge(self):
        j = [sys.executable, FAKE_JUDGE, "pass"]
        with self.assertRaises(seal.SealError):
            seal.validate(manifest(judges=[{"name": "a", "vendor": "x", "cmd": j}, {"name": "b", "vendor": "y", "cmd": j}]))

    def test_unknown_keys_are_refused(self):
        with self.assertRaises(seal.SealError):
            seal.validate(manifest(reference_path=["reference/"]))
        with self.assertRaises(seal.SealError):
            seal.validate(manifest(calibration={**CAL, "min_kapa": 0.9}))

    def test_judge_output_with_duplicate_keys_is_an_error(self):
        code = "import sys; sys.stdin.read(); print('{\"verdict\":\"fail\",\"verdict\":\"pass\"}')"
        self.assertEqual(jury._vote({"name": "a", "vendor": "x", "cmd": [sys.executable, "-c", code]}, "c"), "error")


class TestF_LiveHelper(unittest.TestCase):
    def test_agent_files_cannot_fake_the_test_run(self):
        import subprocess
        live = str(ROOT / "examples" / "live" / "live.py")
        fixture = (ROOT / "tests" / "fixtures" / "claude_2_1_301_read_canary.jsonl").read_text()
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / "w"
            subprocess.run([sys.executable, live, "prepare", work, "--model", "m", "--other-model", "n"], check=True,
                           capture_output=True)
            for run in (work / "runs").iterdir():
                (run / "trace.jsonl").write_text(fixture)
            ws = work / "runs" / "01_add_a" / "ws"
            (ws / "unittest.py").write_text("import sys\nsys.exit(0)\n")
            subprocess.run([sys.executable, live, "cases", work], check=True, capture_output=True)
            case = (work / "cases" / "01_add_a" / "case.txt").read_text()
            self.assertIn("TEST OUTPUT (exit 1)", case)
            self.assertIn("unittest.py", case)


if __name__ == "__main__":
    unittest.main()
