"""The live demo helper prepares and packages runs; it never runs an agent or a judge."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from valid_evals import seal  # noqa: E402

LIVE = str(ROOT / "examples" / "live" / "live.py")
TRACE = (ROOT / "tests" / "fixtures" / "claude_2_1_301_read_canary.jsonl").read_text()


def live(*args):
    return subprocess.run([sys.executable, LIVE, *map(str, args)], capture_output=True, text=True)


class TestLiveHelper(unittest.TestCase):
    def test_prepare_then_cases(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / "w"
            r = live("prepare", work, "--model", "claude-sonnet-5-5", "--other-model", "claude-haiku-5-5")
            self.assertEqual(r.returncode, 0, r.stderr)
            m = json.loads((work / "manifest.json").read_text())
            seal.validate(m)
            canary = m["canaries"][0]
            runs = sorted(p.name for p in (work / "runs").iterdir())
            self.assertEqual(len(runs), 12)
            leak = work / "runs" / "90_planted_leak" / "ws" / "reference" / "solution.py"
            self.assertIn(canary, leak.read_text())
            self.assertFalse(any(canary in p.read_text() for p in (work / "runs" / "01_add_a" / "ws").rglob("*.py")))
            self.assertIn("claude-haiku-5-5", (work / "runs" / "91_planted_model" / "cmd.sh").read_text())
            for run in runs:
                self.assertNotIn("control", (work / "runs" / run / "prompt.txt").read_text().lower())
            rubric = (ROOT / "examples" / "live" / "tasks" / "05_control" / "rubric.txt").read_text().lower()
            self.assertNotIn("control", rubric)
            self.assertNotIn("should fail", rubric)
            self.assertEqual(live("prepare", work, "--model", "x", "--other-model", "y").returncode, 1)
            for run in runs:
                (work / "runs" / run / "trace.jsonl").write_text(TRACE)
            r = live("cases", work)
            self.assertEqual(r.returncode, 0, r.stderr)
            case = (work / "cases" / "01_add_a" / "case.txt").read_text()
            self.assertIn("RUBRIC", case)
            self.assertIn("test_app.py changed by the agent: no", case)
            self.assertIn("TEST OUTPUT (exit 1)", case)
            self.assertEqual(json.loads(live("cost", work).stdout)["runs_with_cost"], 12)
            t = work / "runs" / "01_add_a" / "trace.jsonl"
            t.write_text(TRACE + TRACE)  # two result events: the run cost is unknown, not summed
            c = json.loads(live("cost", work).stdout)
            self.assertEqual((c["runs_with_cost"], c["runs_without_cost"]), (11, ["01_add_a"]))


class TestIsolationModes(unittest.TestCase):
    def manifest_and_cmd(self, *extra):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / "w"
            r = live("prepare", work, "--model", "claude-haiku-5-5", "--other-model", "claude-sonnet-5-5", *extra)
            self.assertEqual(r.returncode, 0, r.stderr)
            return (json.loads((work / "manifest.json").read_text()),
                    (work / "runs" / "01_add_a" / "cmd.sh").read_text())

    def test_default_is_restricted_for_a_subscription_login(self):
        m, cmd = self.manifest_and_cmd()
        self.assertIn("claude --restricted --strict-mcp-config -p", cmd)
        self.assertNotIn("--bare", cmd)
        claude = m["judges"][0]["cmd"]
        self.assertEqual(claude[:3], ["claude", "--restricted", "--strict-mcp-config"])

    def test_bare_for_an_api_key(self):
        m, cmd = self.manifest_and_cmd("--isolation", "bare")
        self.assertIn("claude --bare -p", cmd)
        self.assertEqual(m["judges"][0]["cmd"][:2], ["claude", "--bare"])

    def test_codex_judge_model_is_pinned_when_given(self):
        m, _ = self.manifest_and_cmd("--codex-model", "some-model")
        codex = m["judges"][1]["cmd"]
        self.assertEqual(codex[codex.index("-m") + 1], "some-model")
        m, _ = self.manifest_and_cmd()
        self.assertNotIn("-m", m["judges"][1]["cmd"])


if __name__ == "__main__":
    unittest.main()
