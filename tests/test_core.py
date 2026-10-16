"""Tests for seal, validity, jury and decide. Traces are synthetic, built in the shape documented for
`claude -p --output-format stream-json --verbose` (code.claude.com/docs/en/headless, read 2026 10 16)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from valid_evals import decide, jury, seal, validity  # noqa: E402

FAKE_JUDGE = str(ROOT / "tests" / "fake_judge.py")


def manifest(**over):
    m = {
        "metric": "pass_rate", "comparator": ">=", "threshold": 0.8, "min_valid_cases": 3,
        "outcome": {"pass": "Ship it: pass rate met the sealed bar.", "fail": "Do not ship: pass rate under the sealed bar."},
        "allowed_models": ["claude-sonnet-5-5"], "allowed_tools": ["Read", "Grep"],
        "canaries": ["CANARY-7f3a"], "require_bare": True,
        "judges": [{"name": "a", "vendor": "anthropic", "cmd": [sys.executable, FAKE_JUDGE, "pass"]},
                   {"name": "b", "vendor": "openai", "cmd": [sys.executable, FAKE_JUDGE, "pass", "b"]}],
    }
    m.update(over)
    return m


def trace(model="claude-sonnet-5-5", events=(), mcp=(), plugins=(), result=True, is_error=False):
    out = [{"type": "system", "subtype": "init", "model": model, "tools": ["Read", "Grep"],
            "mcp_servers": list(mcp), "plugins": list(plugins), "session_id": "s1"},
           {"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": "Solve task 1."}},
           {"type": "assistant", "parent_tool_use_id": None,
            "message": {"model": model, "content": [{"type": "text", "text": "Looking at the task."}]}}]
    out += list(events)
    if result:
        out.append({"type": "result", "subtype": "error_during_execution" if is_error else "success",
                    "is_error": is_error, "total_cost_usd": 0.0123, "session_id": "s1"})
    return "\n".join(json.dumps(e) for e in out)


def tool_use(name, inp, model="claude-sonnet-5-5", parent=None):
    return {"type": "assistant", "parent_tool_use_id": parent,
            "message": {"model": model, "content": [{"type": "tool_use", "id": "t1", "name": name, "input": inp}]}}


def tool_result(text, parent=None):
    return {"type": "user", "parent_tool_use_id": parent,
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": text}]}}


class TestSeal(unittest.TestCase):
    def test_hash_is_stable_across_key_order(self):
        a = manifest()
        b = dict(reversed(list(a.items())))
        self.assertEqual(seal.digest(a), seal.digest(b))

    def test_any_edit_changes_the_hash(self):
        self.assertNotEqual(seal.digest(manifest()), seal.digest(manifest(threshold=0.7)))

    def test_verify_fails_closed_after_edit(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "manifest.json"
            p.write_text(json.dumps(manifest()))
            seal.seal(p)
            p.write_text(json.dumps(manifest(threshold=0.5)))
            with self.assertRaises(seal.SealError):
                seal.verify(p)

    def test_judges_must_be_two_different_vendors(self):
        same = manifest(judges=[{"name": "a", "vendor": "anthropic", "cmd": ["x"]},
                                {"name": "b", "vendor": "anthropic", "cmd": ["y"]}])
        with self.assertRaises(seal.SealError):
            seal.validate(same)


class TestValidity(unittest.TestCase):
    def check(self, text, m=None):
        return validity.check(text, m or manifest())

    def test_clean_run_is_valid(self):
        r = self.check(trace(events=[tool_use("Read", {"file_path": "task.md"}), tool_result("task text")]))
        self.assertEqual((r.valid, r.cause), (True, None))

    def test_missing_result_is_run_error(self):
        self.assertEqual(self.check(trace(result=False)).cause, "run_error")

    def test_error_result_is_run_error(self):
        self.assertEqual(self.check(trace(is_error=True)).cause, "run_error")

    def test_mcp_server_in_bare_run_is_isolation_breach(self):
        r = self.check(trace(mcp=[{"name": "x", "status": "connected"}]))
        self.assertEqual(r.cause, "isolation_breach")

    def test_init_model_mismatch(self):
        self.assertEqual(self.check(trace(model="claude-haiku-5-5")).cause, "model_mismatch")

    def test_per_message_model_mismatch(self):
        r = self.check(trace(events=[tool_use("Read", {"file_path": "a"}, model="other-model")]))
        self.assertEqual(r.cause, "model_mismatch")

    def test_dated_model_id_matches_its_alias(self):
        r = self.check(trace(model="claude-sonnet-5-5-20260901"))
        self.assertTrue(r.valid, r)

    def test_canary_in_tool_result_is_reference_leak(self):
        r = self.check(trace(events=[tool_use("Read", {"file_path": "ref/answer.md"}), tool_result("x CANARY-7f3a y")]))
        self.assertEqual(r.cause, "reference_leak")

    def test_human_text_turn_in_main_thread(self):
        human = {"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": "try the other file"}}
        self.assertEqual(self.check(trace(events=[human])).cause, "human_turn")

    def test_subagent_prompt_is_not_a_human_turn(self):
        sub = {"type": "user", "parent_tool_use_id": "agent1", "message": {"role": "user", "content": "subtask"}}
        self.assertTrue(self.check(trace(events=[sub])).valid)

    def test_tool_outside_allowlist(self):
        self.assertEqual(self.check(trace(events=[tool_use("Bash", {"command": "ls"})])).cause, "tool_not_allowed")

    def test_priority_reports_one_cause_and_keeps_all(self):
        r = self.check(trace(model="other", events=[tool_use("Bash", {"command": "cat CANARY-7f3a"})]))
        self.assertEqual(r.cause, "model_mismatch")
        self.assertEqual(set(r.details), {"model_mismatch", "reference_leak", "tool_not_allowed"})

    def test_synthetic_model_marker_is_not_a_mismatch(self):
        r = self.check(trace(events=[tool_use("Read", {"file_path": "a"}, model="<synthetic>")]))
        self.assertTrue(r.valid, r)

    def test_unknown_events_are_tolerated_but_unreadable_lines_are_not(self):
        # v0.3: a line we cannot read could hide a model switch or a human turn, so it fails closed
        self.assertTrue(self.check(trace() + '\n{"type": "stream_event", "event": {}}\n').valid)
        self.assertEqual(self.check(trace() + "\nnot json\n").cause, "run_error")


class TestJury(unittest.TestCase):
    def judges(self, a, b):
        return [{"name": "a", "vendor": "anthropic", "cmd": [sys.executable, FAKE_JUDGE, a]},
                {"name": "b", "vendor": "openai", "cmd": [sys.executable, FAKE_JUDGE, b]}]

    def test_both_pass(self):
        self.assertEqual(jury.judge("case", self.judges("pass", "pass")).verdict, "PASS")

    def test_both_fail(self):
        self.assertEqual(jury.judge("case", self.judges("fail", "fail")).verdict, "FAIL")

    def test_split_is_disagree(self):
        self.assertEqual(jury.judge("case", self.judges("pass", "fail")).verdict, "DISAGREE")

    def test_garbage_is_judge_error(self):
        self.assertEqual(jury.judge("case", self.judges("pass", "garbage")).verdict, "JUDGE_ERROR")

    def test_claude_json_structured_output_is_read(self):
        js = [{"name": "a", "vendor": "anthropic", "cmd": [sys.executable, FAKE_JUDGE, "structured_pass"]},
              {"name": "b", "vendor": "openai", "cmd": [sys.executable, FAKE_JUDGE, "pass", "b"]}]
        self.assertEqual(jury.judge("case", js).verdict, "PASS")

    def test_crash_is_judge_error(self):
        self.assertEqual(jury.judge("case", self.judges("pass", "crash")).verdict, "JUDGE_ERROR")


class TestDecide(unittest.TestCase):
    def run_decide(self, rows, m=None):
        with tempfile.TemporaryDirectory() as d:
            mp = Path(d) / "manifest.json"
            mp.write_text(json.dumps(m or manifest()))
            seal.seal(mp)
            return decide.decide(mp, rows)

    def rows(self, verdicts, valid=True):
        return [{"case": str(i), "valid": valid, "verdict": v} for i, v in enumerate(verdicts)]

    def test_pass_prints_sealed_sentence(self):
        d = self.run_decide(self.rows(["PASS"] * 4 + ["FAIL"]))
        self.assertEqual((d.ok, d.sentence), (True, manifest()["outcome"]["pass"]))

    def test_fail_under_bar(self):
        d = self.run_decide(self.rows(["PASS", "FAIL", "FAIL", "PASS"]))
        self.assertEqual((d.ok, d.sentence), (False, manifest()["outcome"]["fail"]))

    def test_invalid_and_disagree_do_not_count(self):
        rows = self.rows(["PASS"] * 3) + self.rows(["FAIL"] * 5, valid=False) + self.rows(["DISAGREE", "JUDGE_ERROR"])
        d = self.run_decide(rows)
        self.assertEqual((d.counted, d.excluded["invalid"], d.excluded["disagree"], d.excluded["judge_error"]), (3, 5, 1, 1))
        self.assertTrue(d.ok)

    def test_too_few_valid_cases_fails_closed(self):
        with self.assertRaises(decide.DecisionError):
            self.run_decide(self.rows(["PASS", "PASS"]))


if __name__ == "__main__":
    unittest.main()
