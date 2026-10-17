"""Red team round 4: agent side gaps, a refusal that still paid for judge calls, a limit that could switch off."""

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


class TestAgentSide(unittest.TestCase):
    def test_reference_paths_that_never_match_are_refused_at_seal(self):
        for bad in ("/work/reference/", "./reference", "reference ", " reference"):
            with self.assertRaisesRegex(seal.SealError, "reference_paths"):
                seal.validate(manifest(reference_paths=[bad]))

    def test_a_denied_call_is_not_a_tool_the_agent_used(self):
        lines = trace(events=[tool_use("Bash", {"command": "pytest"})]).splitlines()
        res = json.loads(lines[-1])
        res["permission_denials"] = [{"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {"command": "pytest"}}]
        v = validity.check("\n".join(lines[:-1] + [json.dumps(res)]), manifest())
        self.assertEqual((v.valid, v.cause), (True, None))

    def test_search_queries_and_todo_labels_are_prose(self):
        m = manifest(reference_paths=["reference/"], allowed_tools=["WebSearch", "TodoWrite"])
        for name, inp in (("WebSearch", {"query": "python reference counting"}),
                          ("TodoWrite", {"todos": [{"content": "x", "activeForm": "Reading reference docs",
                                                    "status": "pending"}]})):
            self.assertTrue(validity.check(trace(events=[tool_use(name, inp)]), m).valid, name)


class TestRefuseEarly(unittest.TestCase):
    def test_no_limit_of_one(self):
        with self.assertRaisesRegex(seal.SealError, "max_excluded_fraction"):
            seal.validate(manifest(max_excluded_fraction=1))

    def test_invalid_share_alone_refuses_before_any_judge_call(self):
        d = Path(tempfile.mkdtemp())
        log = d / "calls.txt"
        judge = [sys.executable, "-c", f"open({str(log)!r}, 'a').write('x'); print('{{\"verdict\": \"pass\"}}')"]
        p = d / "manifest.json"
        p.write_text(json.dumps(manifest(max_excluded_fraction=0.25, min_valid_cases=1, judges=[
            {"name": "a", "vendor": "anthropic", "cmd": judge}, {"name": "b", "vendor": "openai", "cmd": judge + ["b"]}])))
        seal.seal(p)
        for i, t in enumerate([trace(), trace(model="other"), trace(model="other")]):
            (d / "cases" / f"c{i}").mkdir(parents=True)
            (d / "cases" / f"c{i}" / "trace.jsonl").write_text(t + "\n")
            (d / "cases" / f"c{i}" / "case.txt").write_text("x\n")
        self.assertEqual(cli.main(["run", str(p), str(d / "cases")]), 2)
        self.assertFalse(log.exists())


if __name__ == "__main__":
    unittest.main()
