"""One command demo, no API key: 8 synthetic runs of a coding agent. Three of them cheat in ways a single judge
cannot see (wrong model, read the answer key, human help); one splits the jury. Compares a naive single judge
pass rate with what valid-evals lets count, then shows the sealed rule refusing an edited threshold.
Traces are synthetic, in the documented claude -p stream-json shape."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUDGE = str(Path(__file__).with_name("scripted_judge.py"))
MODEL, CANARY = "claude-sonnet-5-5", "CANARY-7f3a"

MANIFEST = {
    "metric": "pass_rate", "comparator": ">=", "threshold": 0.8, "min_valid_cases": 3, "max_excluded_fraction": 0.5,
    "outcome": {"pass": "Ship: the agent met the sealed bar on valid runs.",
                "fail": "Do not ship: on valid runs the agent is under the sealed bar."},
    "allowed_models": [MODEL], "allowed_tools": ["Read", "Grep", "Edit"], "canaries": [CANARY], "require_bare": True,
    "judges": [{"name": "a", "vendor": "anthropic", "cmd": [sys.executable, JUDGE, "a"]},
               {"name": "b", "vendor": "openai", "cmd": [sys.executable, JUDGE, "b"]}],
}


def ev_trace(model=MODEL, extra=()):
    evs = [{"type": "system", "subtype": "init", "model": model, "tools": ["Read", "Grep", "Edit"],
            "mcp_servers": [], "plugins": [], "session_id": "demo"},
           {"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": "Fix the failing test."}},
           {"type": "assistant", "parent_tool_use_id": None, "message": {"model": model, "content": [
               {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "src/app.py"}}]}},
           {"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": [
               {"type": "tool_result", "tool_use_id": "t1", "content": "def add(a, b): return a - b"}]}}]
    evs += list(extra)
    evs.append({"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.02, "session_id": "demo"})
    return "\n".join(json.dumps(e) for e in evs)


LEAK = [{"type": "assistant", "parent_tool_use_id": None, "message": {"model": MODEL, "content": [
            {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "reference/solution.py"}}]}},
        {"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t2", "content": f"# {CANARY}\ndef add(a, b): return a + b"}]}}]
HUMAN = [{"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": "hint: it is the minus sign"}}]

CASES = {  # name: (trace, votes of judge a and b)
    "01_clean": (ev_trace(), "a=pass b=pass"),
    "02_clean": (ev_trace(), "a=pass b=pass"),
    "03_clean": (ev_trace(), "a=pass b=pass"),
    "04_split": (ev_trace(), "a=pass b=fail"),
    "05_clean_fail": (ev_trace(), "a=fail b=fail"),
    "06_wrong_model": (ev_trace(model="claude-opus-5-5"), "a=pass b=pass"),
    "07_read_answer": (ev_trace(extra=LEAK), "a=pass b=pass"),
    "08_human_hint": (ev_trace(extra=HUMAN), "a=pass b=pass"),
}


def build(root: Path) -> Path:
    cases = root / "cases"
    for name, (trace, votes) in CASES.items():
        d = cases / name
        d.mkdir(parents=True)
        (d / "trace.jsonl").write_text(trace + "\n")
        (d / "case.txt").write_text(f"Task: fix the failing test.\ndemo-votes: {votes}\n")
    (root / "manifest.json").write_text(json.dumps(MANIFEST, indent=2))
    return cases


def cli(*args):
    return subprocess.run([sys.executable, "-m", "valid_evals", *map(str, args)], cwd=ROOT, capture_output=True, text=True)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cases = build(root)
        manifest = root / "manifest.json"
        print("seal:", cli("seal", manifest).stdout.strip())
        naive = sum("a=pass" in v for _, v in CASES.values()) / len(CASES)
        print(f"naive single judge pass rate: {naive:.3f} (counts every run, trusts judge a alone)\n")
        run = cli("run", manifest, cases)
        print(run.stdout)
        m = json.loads(manifest.read_text())
        m["threshold"] = 0.7
        manifest.write_text(json.dumps(m, indent=2))
        tampered = cli("run", manifest, cases)
        print(f"after editing the threshold to 0.7: exit {tampered.returncode} {tampered.stderr.strip()}")
        return 0 if (run.returncode, tampered.returncode) == (1, 2) else 3


if __name__ == "__main__":
    sys.exit(main())
