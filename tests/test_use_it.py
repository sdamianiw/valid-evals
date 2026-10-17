"""README "Use it", step by step, as a stranger runs it: from another folder, through `python -m valid_evals`."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JUDGE = str(ROOT / "examples" / "demo" / "scripted_judge.py")
CANARY = "CANARY-use-it-1f2e"


def step(cwd, *args):
    # cp1252 is what a Windows console or pipe gives Python; it cannot show most non Latin text
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "cp1252"}
    p = subprocess.run([sys.executable, "-m", "valid_evals", *args], cwd=cwd, env=env, capture_output=True,
                       text=True, encoding="cp1252")
    return p.returncode, p.stdout + p.stderr


def trace(model="claude-sonnet-5-5", read="src/app.py"):
    ts = "2099-01-01T00:00:00.000Z"
    evs = [{"type": "system", "subtype": "init", "model": model, "tools": ["Read"], "mcp_servers": [], "plugins": []},
           {"type": "assistant", "timestamp": ts, "message": {"model": model, "content": [
               {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": read}}]}},
           {"type": "user", "timestamp": ts, "parent_tool_use_id": None, "message": {"role": "user", "content": [
               {"type": "tool_result", "tool_use_id": "t1", "content": "def add(a, b): return a + b"}]}},
           {"type": "result", "subtype": "success", "is_error": False}]
    return "".join(json.dumps(e) + "\n" for e in evs)


class TestUseIt(unittest.TestCase):
    def test_the_readme_steps_work_from_another_folder(self):
        work = Path(tempfile.mkdtemp(prefix="use it "))  # a space in the path, as in many home folders
        # 1. plant a canary in the files the agent must not read
        (work / "reference").mkdir()
        (work / "reference" / "solution.py").write_text(f"# {CANARY}\n", encoding="utf-8")
        # 2. manifest with canaries, reference_paths and a calibration block; seal it
        (work / "manifest.json").write_text(json.dumps({
            "metric": "pass_rate", "comparator": ">=", "threshold": 0.5, "min_valid_cases": 2,
            "max_excluded_fraction": 0.5,
            "outcome": {"pass": "Ship.", "fail": "Do not ship."},
            "allowed_models": ["claude-sonnet-5-5"], "allowed_tools": ["Read"], "canaries": [CANARY],
            "require_bare": True, "reference_paths": ["reference/"],
            "calibration": {"min_kappa": 0.5, "min_labels": 4, "max_judge_error_rate": 0.2},
            "judges": [{"name": "a", "vendor": "anthropic", "cmd": [sys.executable, JUDGE, "a"]},
                       {"name": "b", "vendor": "openai", "cmd": [sys.executable, JUDGE, "b"]}]}), encoding="utf-8")
        self.assertEqual(step(work, "seal", "manifest.json")[0], 0)
        # 3 and 4. one trace and one case.txt per run; text that is not ASCII must survive the judges
        runs = {"01": ("pass", "pass", trace()), "02": ("pass", "pass", trace()), "03": ("fail", "fail", trace()),
                "04_\u4f60\u597d": ("pass", "pass", trace()), "05": ("pass", "pass", trace(read="reference/solution.py"))}
        for name, (a, b, t) in runs.items():
            c = work / "cases" / name
            c.mkdir(parents=True)
            (c / "trace.jsonl").write_text(t, encoding="utf-8")
            (c / "case.txt").write_text(f"Tarea: corregir añadir() 你好 ✓\ndemo-votes: a={a} b={b}\n", encoding="utf-8")
        # 5. run: the leak is invalid, the rest are judged; provisional because calibration is sealed
        code, out = step(work, "run", "manifest.json", "cases")
        self.assertEqual(code, 1, out)
        printed = json.loads([x for x in out.splitlines() if x.startswith("{")][0])["results_sha256"]
        self.assertEqual(printed, hashlib.sha256((work / "cases" / "results.jsonl").read_bytes()).hexdigest())
        self.assertIn("05             INVALID  reference_leak", out)
        self.assertIn('"counted": 4', out)
        # 6. label blind, then calibrate gives the final decision
        (work / "labels.json").write_text(json.dumps({"01": "pass", "02": "pass", "03": "fail", "04_\u4f60\u597d": "pass"}),
                                          encoding="utf-8")
        code, out = step(work, "calibrate", "manifest.json", "cases", "labels.json")
        self.assertEqual(code, 0, out)
        # reproducible: the same inputs give byte identical results, run after run
        first = (work / "cases" / "results.jsonl").read_bytes()
        self.assertEqual(step(work, "run", "manifest.json", "cases")[0], 1)
        self.assertEqual((work / "cases" / "results.jsonl").read_bytes(), first)


class TestJudgeBytes(unittest.TestCase):
    def test_a_judge_that_prints_bytes_that_are_not_utf8_is_an_error_not_a_crash(self):
        sys.path.insert(0, str(ROOT))
        from valid_evals import jury
        bad = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff\\xfe{\"verdict\": \"pass\"}')"]
        good = [sys.executable, JUDGE, "a"]
        r = jury.judge("añadir\ndemo-votes: a=pass b=pass\n",
                       [{"name": "a", "vendor": "x", "cmd": good}, {"name": "b", "vendor": "y", "cmd": bad}])
        self.assertEqual(r.votes["b"], "error")


if __name__ == "__main__":
    unittest.main()
