"""Findings of the v0.2 red team, each reproduced before its fix. P0 = fail open."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from valid_evals import calibrate, cli, jury, seal, validity  # noqa: E402
from tests.test_codex import CLEAN as CODEX_CLEAN, manifest as codex_manifest  # noqa: E402
from tests.test_core import FAKE_JUDGE, manifest, tool_use, trace  # noqa: E402


def lines(text):
    return [json.loads(x) for x in text.splitlines()]


def dump(evs):
    return "\n".join(json.dumps(e) for e in evs)


def without_result(text):
    return [e for e in lines(text) if e["type"] != "result"]


def judge(name, mode, vendor):
    return {"name": name, "vendor": vendor, "cmd": [sys.executable, FAKE_JUDGE, mode]}


class TestP0FailOpen(unittest.TestCase):
    def test_error_subtypes_are_run_errors_even_with_is_error_false(self):
        for sub in ("error_max_turns", "error_during_execution", "error_max_budget_usd"):
            evs = without_result(trace()) + [{"type": "result", "subtype": sub, "is_error": False}]
            self.assertEqual(validity.check(dump(evs), manifest()).cause, "run_error", sub)
        evs = without_result(trace()) + [{"type": "result", "subtype": "success"}]
        self.assertEqual(validity.check(dump(evs), manifest()).cause, "run_error")

    def test_duplicate_judge_names_are_refused(self):
        with self.assertRaises(seal.SealError):
            seal.validate(manifest(judges=[judge("j", "pass", "anthropic"), judge("j", "garbage", "openai")]))

    def test_vendors_differ_ignoring_case(self):
        with self.assertRaises(seal.SealError):
            seal.validate(manifest(judges=[judge("a", "pass", "anthropic"), judge("b", "pass", "Anthropic")]))

    def test_synthetic_only_run_has_no_verified_model(self):
        evs = lines(trace(model="<synthetic>", events=[tool_use("Read", {}, model="<synthetic>")]))
        self.assertFalse(validity.check(dump(evs), manifest()).valid)
        evs = [e for e in lines(trace(events=[tool_use("Read", {}, model="<synthetic>")]))
               if not (e["type"] == "assistant" and e["message"]["content"][0]["type"] == "text")]
        self.assertEqual(validity.check(dump(evs), manifest()).cause, "model_unverified")

    def test_escaped_canaries_still_match(self):
        for canary in ('CAN"ARY-1', "CAN\\ARY-2", "CAN\tARY-3", "CANÄRY-4"):
            for ascii_only in (True, False):
                result = {"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": f"# {canary}"}]}}
                evs = lines(trace(events=[tool_use("Read", {})]))
                evs.insert(-1, result)
                text = "\n".join(json.dumps(e, ensure_ascii=ascii_only) for e in evs)
                v = validity.check(text, manifest(canaries=[canary]))
                self.assertEqual(v.cause, "reference_leak", (canary, ascii_only))

    def test_canaries_must_be_a_non_empty_list_of_non_empty_strings(self):
        for bad in ([], [""], [123], "CANARY"):
            with self.assertRaises(seal.SealError):
                seal.validate(manifest(canaries=bad))

    def test_exactly_one_result_and_it_comes_last(self):
        evs = lines(trace())
        err = {"type": "result", "subtype": "error_during_execution", "is_error": True}
        self.assertEqual(validity.check(dump(evs[:-1] + [err, evs[-1]]), manifest()).cause, "run_error")
        late = evs + [tool_use("Read", {})]
        self.assertEqual(validity.check(dump(late), manifest()).cause, "run_error")

    def test_mixed_trace_shapes_are_a_run_error(self):
        evs = lines(trace(model="claude-opus-5-5")) + [{"type": "thread.started", "thread_id": "x"},
                                                       {"type": "turn.started"}, {"type": "turn.completed"}]
        v = validity.check(dump(evs), manifest(trust_runner_model=True, allowed_tools=["command_execution"]))
        self.assertEqual(v.cause, "run_error")

    def test_trust_flags_must_be_booleans(self):
        for key in ("trust_runner_model", "require_bare"):
            with self.assertRaises(seal.SealError):
                seal.validate(manifest(**{key: "false"}))

    def test_codex_tools_seen_in_any_item_event(self):
        base = lines(CODEX_CLEAN)
        for ev_type, it in (("item.started", {"id": "m1", "type": "mcp_tool_call", "server": "s", "tool": "t",
                                               "arguments": {}, "status": "in_progress"}),
                            ("item.updated", {"id": "w1", "type": "web_search", "query": "q"})):
            evs = base[:-1] + [{"type": ev_type, "item": it}, base[-1]]
            self.assertFalse(validity.check(dump(evs), codex_manifest()).valid, ev_type)

    def test_codex_reused_item_id_does_not_hide_a_tool(self):
        base = lines(CODEX_CLEAN)
        mcp = {"type": "item.completed", "item": {"id": "item_1", "type": "mcp_tool_call", "server": "s",
                                                  "tool": "t", "arguments": {}, "status": "completed"}}
        evs = base[:-1] + [mcp, base[-1]]
        self.assertFalse(validity.check(dump(evs), codex_manifest()).valid)


class TestP1(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def sealed(self, **over):
        p = self.d / "m.json"
        p.write_text(json.dumps(manifest(**over)))
        seal.seal(p)
        return p

    def test_calibrate_fails_on_too_many_judge_errors(self):
        p = self.sealed(threshold=0.0, min_valid_cases=1,
                        calibration={"min_kappa": 0.6, "min_labels": 2, "max_judge_error_rate": 0.1})
        rows = [{"case": f"c{i}", "valid": True, "verdict": v, "votes": {"a": a, "b": b}} for i, (v, a, b) in
                enumerate([("PASS", "pass", "pass"), ("FAIL", "fail", "fail")] + [("JUDGE_ERROR", "error", "error")] * 4)]
        rep = calibrate.calibrate(p, rows, {"c0": "pass", "c1": "fail"})
        self.assertFalse(rep["ok"])

    def test_calibration_values_that_switch_the_gate_off_are_refused(self):
        for cal in ({"min_kappa": -1, "min_labels": 2, "max_judge_error_rate": 0.1},
                    {"min_kappa": True, "min_labels": 2, "max_judge_error_rate": 0.1},
                    {"min_kappa": float("inf"), "min_labels": 2, "max_judge_error_rate": 0.1},
                    {"min_kappa": 0.6, "min_labels": True, "max_judge_error_rate": 0.1},
                    {"min_kappa": 0.6, "min_labels": 2},
                    {"min_kappa": 0.6, "min_labels": 2, "max_judge_error_rate": 2}):
            with self.assertRaises(seal.SealError, msg=cal):
                seal.validate(manifest(calibration=cal))

    def test_duplicate_keys_in_the_manifest_are_refused(self):
        p = self.d / "m.json"
        body = json.dumps(manifest())
        p.write_text(body[:-1] + ', "threshold": 0.1}')
        with self.assertRaises(seal.SealError):
            seal.seal(p)
        p.write_text(json.dumps(manifest()))
        seal.seal(p)
        p.write_text(body[:-1] + ', "threshold": 0.8}')
        with self.assertRaises(seal.SealError):
            seal.verify(p)

    def test_a_second_init_is_a_run_error(self):
        evs = lines(trace())
        second = dict(evs[0], model="claude-opus-5-5")
        self.assertEqual(validity.check(dump(evs[:2] + [second] + evs[2:]), manifest()).cause, "run_error")

    def test_main_thread_text_with_empty_parent_and_image_only_turns_are_human(self):
        a = tool_use("Read", {})
        for msg in ({"type": "user", "parent_tool_use_id": "", "message": {"role": "user", "content": "hint"}},
                    {"type": "user", "parent_tool_use_id": None,
                     "message": {"role": "user", "content": [{"type": "image", "source": {}}]}}):
            evs = lines(trace(events=[a, msg]))
            self.assertEqual(validity.check(dump(evs), manifest()).cause, "human_turn", msg)

    def test_judge_reads_only_its_final_output(self):
        code = "import sys; sys.stdin.read(); print('{\"verdict\": \"pass\"}'); print('on reflection: fail')"
        j = {"name": "a", "vendor": "x", "cmd": [sys.executable, "-c", code]}
        self.assertEqual(jury._vote(j, "case"), "error")

    def test_judge_output_may_be_one_pretty_printed_object(self):
        code = "import sys, json; sys.stdin.read(); print(json.dumps({'verdict': 'fail'}, indent=2))"
        j = {"name": "a", "vendor": "x", "cmd": [sys.executable, "-c", code]}
        self.assertEqual(jury._vote(j, "case"), "fail")


class TestP2(unittest.TestCase):
    def test_bad_input_is_refused_with_exit_2_not_1(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = d / "m.json"
            p.write_text(json.dumps(manifest()))
            seal.seal(p)
            bad = d / "t.jsonl"
            bad.write_bytes(b"\xff\xfe not utf8")
            self.assertEqual(cli.main(["check", str(p), str(bad)]), 2)
            weird = d / "w.jsonl"
            weird.write_text(dump([{"type": "system", "subtype": "init", "model": ["x"]},
                                   {"type": "assistant", "message": "str"}]))
            self.assertIn(cli.main(["check", str(p), str(weird)]), (1, 2))

    def test_rule_types_are_checked_at_seal(self):
        for over in ({"threshold": "0.8"}, {"threshold": True}, {"min_valid_cases": 0},
                     {"min_valid_cases": "3"}, {"allowed_models": "x"}, {"allowed_tools": "Read"}):
            with self.assertRaises(seal.SealError, msg=over):
                seal.validate(manifest(**over))

    def test_dated_ids_match_on_both_sides(self):
        t = trace(model="claude-sonnet-5-5", events=[tool_use("Read", {}, model="claude-sonnet-5-5-20260101")])
        self.assertTrue(validity.check(t, manifest(allowed_models=["claude-sonnet-5-5-20260101"])).valid)


if __name__ == "__main__":
    unittest.main()
