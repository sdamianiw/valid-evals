"""The live figures in the README, reproduced from the real traces they came from (Claude Code 2.1.301, Haiku,
run 2026 10 16 without --bare in a cloud container; see tests/fixtures/live_2026_10_16/README.md)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from valid_evals import validity  # noqa: E402

LIVE = ROOT / "tests" / "fixtures" / "live_2026_10_16"
MANIFEST = {"allowed_models": ["claude-haiku-5-5"], "allowed_tools": ["Read", "Edit", "Glob", "Grep", "Bash"],
            "canaries": ["CANARY-af94d2d7a9ea506c"], "reference_paths": ["reference/"], "require_bare": True}


def results():
    return {p.stem: validity.check(p.read_text(), MANIFEST) for p in sorted(LIVE.glob("*.jsonl"))}


class TestLiveFigures(unittest.TestCase):
    def test_no_false_alarm_on_the_ten_clean_runs(self):
        clean = {k: v for k, v in results().items() if not k.startswith("9")}
        self.assertEqual(len(clean), 10)
        self.assertEqual({k: v.cause for k, v in clean.items() if not v.valid}, {})

    def test_both_planted_runs_caught_with_the_right_cause(self):
        r = results()
        self.assertEqual(r["90_planted_leak"].cause, "reference_leak")
        self.assertEqual(r["91_planted_model"].cause, "model_mismatch")

    def test_agent_cost(self):
        costs = []
        for p in sorted(LIVE.glob("*.jsonl")):
            res = [json.loads(x) for x in p.read_text().splitlines() if '"type": "result"' in x]
            costs.append(res[-1]["total_cost_usd"])
        self.assertEqual(len(costs), 12)
        self.assertAlmostEqual(sum(costs), 0.0418, 4)
        self.assertAlmostEqual(max(costs), 0.024, 3)


if __name__ == "__main__":
    unittest.main()
