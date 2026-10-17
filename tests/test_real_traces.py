"""Validity against real Claude Code stream-json traces (see tests/fixtures/README.md)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from valid_evals import validity  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
BARE_AUTH_ERROR = (FIX / "claude_2_1_301_bare_auth_error.jsonl").read_text()
READ_CANARY = (FIX / "claude_2_1_301_read_canary.jsonl").read_text()


def manifest(**over):
    m = {"allowed_models": ["claude-haiku-5-5", "claude-opus-5-5"], "allowed_tools": ["Read"],
         "canaries": [], "require_bare": True}
    m.update(over)
    return m


def human_after_first_assistant(text: str, says: str = "hint: it is the minus sign") -> str:
    lines = text.splitlines()
    i = next(n for n, line in enumerate(lines) if json.loads(line).get("type") == "assistant")
    turn = {"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": says}}
    return "\n".join(lines[:i + 1] + [json.dumps(turn)] + lines[i + 1:])


class TestRealClaudeTraces(unittest.TestCase):
    def test_clean_real_run_is_valid(self):
        v = validity.check(READ_CANARY, manifest())
        self.assertTrue(v.valid, v.details)

    def test_builtin_plugins_are_not_an_isolation_breach(self):
        v = validity.check(READ_CANARY, manifest())
        self.assertNotIn("isolation_breach", v.details)

    def test_host_plugin_next_to_builtins_is_isolation_breach(self):
        host = {"name": "lint", "path": "/home/u/.claude/plugins/lint", "source": "lint@market"}
        fake = {"name": "x", "path": "builtin", "source": "x@market"}
        for plugin in (host, fake):
            lines = [json.loads(line) for line in READ_CANARY.splitlines()]
            for e in lines:
                if e.get("subtype") == "init":
                    e["plugins"].append(plugin)
            v = validity.check("\n".join(json.dumps(e) for e in lines), manifest())
            self.assertEqual(v.cause, "isolation_breach", plugin)

    def test_real_canary_read_is_reference_leak(self):
        v = validity.check(READ_CANARY, manifest(canaries=["CANARY-7f3a"]))
        self.assertEqual(v.cause, "reference_leak")
        self.assertEqual(set(v.details), {"reference_leak"})

    def test_human_turn_is_caught_when_the_prompt_is_not_echoed(self):
        v = validity.check(human_after_first_assistant(READ_CANARY), manifest())
        self.assertEqual(v.cause, "human_turn")

    def test_api_error_with_success_subtype_is_run_error_named_by_reason(self):
        v = validity.check(BARE_AUTH_ERROR, manifest())
        self.assertEqual(v.cause, "run_error")
        self.assertEqual(v.details["run_error"], ["api_error"])

    def test_real_max_turns_stop_is_run_error(self):
        text = (FIX / "claude_2_1_301_max_turns.jsonl").read_text()
        v = validity.check(text, manifest(allowed_tools=["Read", "Edit"]))
        self.assertEqual(v.cause, "run_error")
        self.assertIn("max_turns", v.details["run_error"])

    def test_real_subagent_run_is_valid_and_its_prompt_is_not_human(self):
        text = (FIX / "claude_2_1_301_subagent.jsonl").read_text()
        v = validity.check(text, manifest(allowed_models=["claude-haiku-5-5"], allowed_tools=["Agent", "Read"]))
        self.assertTrue(v.valid, v.details)

    def test_real_subagent_tool_is_named_agent_not_task(self):
        text = (FIX / "claude_2_1_301_subagent.jsonl").read_text()
        v = validity.check(text, manifest(allowed_models=["claude-haiku-5-5"], allowed_tools=["Task", "Read"]))
        self.assertEqual(v.details.get("tool_not_allowed"), ["Agent"])

    def test_real_restricted_run_is_valid_under_require_bare(self):
        text = (FIX / "claude_2_1_301_restricted.jsonl").read_text()
        v = validity.check(text, manifest(allowed_models=["claude-haiku-5-5"], allowed_tools=[]))
        self.assertTrue(v.valid, v.details)

    def test_real_claude_judge_output_is_read(self):
        from valid_evals import jury
        out = FIX / "claude_2_1_301_judge_json_schema.json"
        judge = {"name": "claude", "vendor": "anthropic",
                 "cmd": [sys.executable, "-c", f"import sys; sys.stdin.read(); print(open({str(out)!r}).read())"]}
        self.assertEqual(jury._vote(judge, "case"), "pass")

    def test_synthetic_error_message_is_not_a_model_mismatch(self):
        v = validity.check(BARE_AUTH_ERROR, manifest(allowed_models=["claude-opus-5-5"]))
        self.assertNotIn("model_mismatch", v.details)

    def test_wrong_model_in_real_trace(self):
        v = validity.check(READ_CANARY, manifest(allowed_models=["claude-sonnet-5-5"]))
        self.assertEqual(v.cause, "model_mismatch")


if __name__ == "__main__":
    unittest.main()
