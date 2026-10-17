"""v0.4: runs left out of the pass rate cannot inflate it past a sealed limit."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from valid_evals import cli, decide, seal  # noqa: E402
from tests.test_core import manifest, trace  # noqa: E402

FIX = ROOT / "tests" / "fixtures"

PASS, INVALID = {"valid": True, "verdict": "PASS"}, {"valid": False, "cause": "run_error"}


def sealed(**over):
    d = Path(tempfile.mkdtemp())
    p = d / "manifest.json"
    p.write_text(json.dumps(manifest(**over)))
    seal.seal(p)
    return p


class TestExclusionLimit(unittest.TestCase):
    def test_runs_that_hit_the_budget_cannot_lift_the_pass_rate(self):
        # Red team round 3: 3 PASS plus 7 runs that hit max turns read as 1.0 and shipped.
        p = sealed(max_excluded_fraction=0.25)
        with self.assertRaisesRegex(decide.DecisionError, "7 of 10 runs left out"):
            decide.decide(p, [PASS] * 3 + [INVALID] * 7)

    def test_disagreements_and_judge_errors_count_as_left_out(self):
        p = sealed(max_excluded_fraction=0.25)
        rows = [PASS] * 6 + [{"valid": True, "verdict": "DISAGREE"}, {"valid": True, "verdict": "JUDGE_ERROR"},
                             INVALID]
        with self.assertRaisesRegex(decide.DecisionError, "3 of 9 runs left out"):
            decide.decide(p, rows)

    def test_at_the_limit_the_decision_stands(self):
        p = sealed(max_excluded_fraction=0.25)
        self.assertTrue(decide.decide(p, [PASS] * 3 + [INVALID]).ok)

    def test_the_limit_is_required_and_bounded(self):
        m = manifest()
        del m["max_excluded_fraction"]
        with self.assertRaisesRegex(seal.SealError, "missing"):
            seal.validate(m)
        for bad in (-0.1, 1.1, "0.2", True, None):
            with self.assertRaisesRegex(seal.SealError, "max_excluded_fraction"):
                seal.validate(manifest(max_excluded_fraction=bad))

    def test_cli_refuses_when_most_runs_hit_max_turns(self):
        scripted = str(ROOT / "examples" / "demo" / "scripted_judge.py")
        judges = [{"name": "a", "vendor": "anthropic", "cmd": [sys.executable, scripted, "a"]},
                  {"name": "b", "vendor": "openai", "cmd": [sys.executable, scripted, "b"]}]
        max_turns = (FIX / "claude_2_1_301_max_turns.jsonl").read_text()
        for limit, code in ((0.25, 2), (1, 0)):
            p = sealed(max_excluded_fraction=limit, min_valid_cases=1, judges=judges)
            for i in range(4):
                c = p.parent / "cases" / f"c{i}"
                c.mkdir(parents=True)
                (c / "trace.jsonl").write_text(trace() + "\n" if i == 0 else max_turns)
                (c / "case.txt").write_text("demo-votes: a=pass b=pass\n")
            self.assertEqual(cli.main(["run", str(p), str(p.parent / "cases")]), code)


class TestDeniedTools(unittest.TestCase):
    """A run whose test command was denied could not check its own work. It stays valid (the allowlist is the
    author's setting), but the denial is reported instead of hidden."""

    def test_live_runs_with_denied_calls_say_so(self):
        from tests.test_live_results import LIVE, MANIFEST
        from valid_evals import validity
        seen = {p.stem: validity.check(p.read_text(), MANIFEST) for p in sorted(LIVE.glob("0*.jsonl"))}
        denied = {k: len(v.details.get("permission_denied", [])) for k, v in seen.items()}
        self.assertTrue(all(v.valid for v in seen.values()))
        self.assertEqual(denied, {"01_add_a": 3, "01_add_b": 3, "02_even_a": 3, "02_even_b": 3, "03_words_a": 3,
                                  "03_words_b": 2, "04_clamp_a": 0, "04_clamp_b": 0, "05_control_a": 0,
                                  "05_control_b": 0})
        self.assertIn("pytest", seen["01_add_a"].details["permission_denied"][0])

    def denied(self, denials):
        from valid_evals import validity
        lines = trace().splitlines()
        res = json.loads(lines[-1])
        res["permission_denials"] = denials
        return validity.check("\n".join(lines[:-1] + [json.dumps(res)]), manifest())

    def test_two_identical_denials_count_twice(self):
        d = {"tool_name": "Bash", "tool_input": {"command": "pytest"}}
        r = self.denied([{**d, "tool_use_id": "a"}, {**d, "tool_use_id": "b"}])
        self.assertEqual((r.valid, len(r.details["permission_denied"])), (True, 2))

    def test_a_malformed_denial_list_does_not_invalidate_the_run(self):
        for bad in (["x"], {}, "abc", 5):
            r = self.denied(bad)
            self.assertEqual((r.valid, r.details.get("permission_denied")), (True, None), bad)



def pass_chance(accuracy, labels=("pass",) * 3 + ("fail",) * 3, min_kappa=0.6):
    """Exact chance that a judge right with this probability on each case reaches min_kappa against the labels."""
    from itertools import product
    from valid_evals import calibrate
    total = 0.0
    for right in product((True, False), repeat=len(labels)):
        votes = [h if r else ("fail" if h == "pass" else "pass") for h, r in zip(labels, right)]
        k = calibrate.kappa(list(labels), votes)
        if k is not None and k >= min_kappa:
            total += accuracy ** sum(right) * (1 - accuracy) ** (len(labels) - sum(right))
    return total


class TestCalibrationPower(unittest.TestCase):
    def test_six_labels_cannot_tell_a_good_judge_from_a_weak_one(self):
        # README Limits: an 80% judge passes about two times in three
        self.assertEqual(round(pass_chance(0.8), 3), 0.655)
        self.assertEqual(round(pass_chance(0.9), 3), 0.886)
        self.assertEqual(round(pass_chance(0.6), 3), 0.233)


if __name__ == "__main__":
    unittest.main()
