"""Validity over `codex exec --json` traces. Event shapes from the Codex TypeScript SDK types (see
tests/fixtures/README.md); one real failed run pins the format."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from valid_evals import validity  # noqa: E402

AUTH_ERROR = (ROOT / "tests" / "fixtures" / "codex_0_163_0_auth_error.jsonl").read_text()
USAGE = {"input_tokens": 2400, "cached_input_tokens": 0, "cache_write_input_tokens": 0, "output_tokens": 80,
         "reasoning_output_tokens": 0}


def manifest(**over):
    m = {"allowed_models": ["gpt-5.5"], "allowed_tools": ["command_execution", "file_change"],
         "canaries": ["CANARY-7f3a"], "require_bare": True, "trust_runner_model": True}
    m.update(over)
    return m


def item(kind, **fields):
    return {"type": "item.completed", "item": {"id": "item_1", "type": kind, **fields}}


def cmd(command, output):
    return item("command_execution", command=command, aggregated_output=output, exit_code=0, status="completed")


def trace(*items, turns=1, end="turn.completed"):
    evs = [{"type": "thread.started", "thread_id": "t1"}]
    for n in range(turns):
        evs.append({"type": "turn.started"})
        if n == turns - 1:
            evs += list(items)
        evs.append({"type": end, "usage": USAGE} if end == "turn.completed"
                   else {"type": end, "error": {"message": "boom"}})
    return "\n".join(json.dumps(e) for e in evs)


CLEAN = trace(cmd("bash -lc 'cat app.py'", "def add(a, b): return a - b"),
              item("file_change", changes=[{"path": "app.py", "kind": "update"}], status="completed"),
              item("agent_message", text="Fixed the sign in add."))


class TestCodexTraces(unittest.TestCase):
    def test_clean_run_is_valid(self):
        v = validity.check(CLEAN, manifest())
        self.assertTrue(v.valid, v.details)

    def test_real_auth_failure_is_run_error(self):
        v = validity.check(AUTH_ERROR, manifest())
        self.assertEqual(v.cause, "run_error")

    def test_turn_failed_is_run_error(self):
        self.assertEqual(validity.check(trace(end="turn.failed"), manifest()).cause, "run_error")

    def test_unfinished_turn_is_run_error(self):
        text = "\n".join(CLEAN.splitlines()[:-1])
        self.assertEqual(validity.check(text, manifest()).cause, "run_error")

    def test_model_is_unverified_unless_the_sealed_rule_trusts_the_runner(self):
        v = validity.check(CLEAN, manifest(trust_runner_model=False))
        self.assertEqual(v.cause, "model_unverified")
        v = validity.check(CLEAN, {k: val for k, val in manifest().items() if k != "trust_runner_model"})
        self.assertEqual(v.cause, "model_unverified")

    def test_mcp_call_in_bare_run_is_isolation_breach(self):
        t = trace(item("mcp_tool_call", server="docs", tool="search", arguments={}, status="completed"))
        self.assertEqual(validity.check(t, manifest()).cause, "isolation_breach")

    def test_canary_in_command_output_is_reference_leak(self):
        t = trace(cmd("bash -lc 'cat ref/solution.py'", "# CANARY-7f3a\ndef add(a, b): return a + b"))
        self.assertEqual(validity.check(t, manifest()).cause, "reference_leak")

    def test_second_turn_is_human_turn(self):
        self.assertEqual(validity.check(trace(turns=2), manifest()).cause, "human_turn")

    def test_item_type_outside_allowlist(self):
        t = trace(item("web_search", query="add function bug"))
        v = validity.check(t, manifest())
        self.assertEqual(v.cause, "tool_not_allowed")
        self.assertEqual(v.details["tool_not_allowed"], ["web_search"])

    def test_messages_reasoning_plans_and_error_items_are_not_tools(self):
        t = trace(item("reasoning", text="look at add"), item("todo_list", items=[]),
                  item("error", message="non fatal"), item("agent_message", text="done"))
        self.assertTrue(validity.check(t, manifest(allowed_tools=[])).valid)

    def test_unknown_trace_shape_fails_closed(self):
        v = validity.check(json.dumps({"type": "something_else"}), manifest())
        self.assertEqual(v.cause, "run_error")


if __name__ == "__main__":
    unittest.main()
