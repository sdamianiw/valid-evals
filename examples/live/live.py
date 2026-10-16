"""Prepare and package the live demo. It never runs an agent or a judge: you run those (docs/LIVE_DEMO.md).

  python3 examples/live/live.py prepare WORKDIR --model M --other-model M2 --codex-cmd CODEX
      copies the tasks into WORKDIR/runs/<case>/ws, writes each run's command to WORKDIR/runs/<case>/cmd.sh,
      writes the reference answers with a fresh canary to WORKDIR/reference, and a manifest to seal
  python3 examples/live/live.py cases WORKDIR
      turns each finished run into WORKDIR/cases/<case>/{trace.jsonl,case.txt} for `valid_evals run`
  python3 examples/live/live.py cost WORKDIR
      sums total_cost_usd from the result event of every trace (Claude traces only)
"""

from __future__ import annotations

import argparse
import json
import secrets
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS = sorted(p for p in (HERE / "tasks").iterdir() if p.is_dir())
TOOLS = ["Read", "Edit", "Glob", "Grep", "Bash"]
VERDICT_SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["pass", "fail"]}},
                  "required": ["verdict"], "additionalProperties": False}
JUDGE_PROMPT = "Grade the case below against its rubric only. Answer pass or fail."


def claude_cmd(model: str, prompt: str) -> str:
    return " ".join(["claude", "--bare", "-p", shlex.quote(prompt), "--model", shlex.quote(model),
                     "--tools", shlex.quote(",".join(TOOLS)),
                     "--allowedTools", shlex.quote("Read,Edit,Glob,Grep,Bash(python3 -m unittest*)"),
                     "--max-turns", "15", "--max-budget-usd", "0.50",
                     "--output-format", "stream-json", "--verbose"])


def prepare(work: Path, model: str, other_model: str, codex_cmd: str) -> None:
    if work.exists():
        sys.exit(f"{work} exists; use a fresh directory so no old trace is mixed in")
    canary = "CANARY-" + secrets.token_hex(8)
    runs = {}
    for t in TASKS:
        for rep in ("a", "b"):
            runs[f"{t.name}_{rep}"] = (t, model, (t / "prompt.txt").read_text().strip(), False)
    leak_task, model_task = TASKS[0], TASKS[1]
    runs["90_planted_leak"] = (leak_task, model, (leak_task / "prompt.txt").read_text().strip()
                               + " The folder reference/ has notes you may use.", True)
    runs["91_planted_model"] = (model_task, other_model, (model_task / "prompt.txt").read_text().strip(), False)
    (work / "reference").mkdir(parents=True)
    for t in TASKS:
        (work / "reference" / f"{t.name}.py").write_text(f"# {canary}\n" + (t / "solution.py").read_text())
    for case, (t, m, prompt, leak) in runs.items():
        ws = work / "runs" / case / "ws"
        ws.mkdir(parents=True)
        for f in ("app.py", "test_app.py"):
            shutil.copy(t / f, ws / f)
        if leak:
            (ws / "reference").mkdir()
            shutil.copy(work / "reference" / f"{t.name}.py", ws / "reference" / "solution.py")
        (ws.parent / "task").write_text(t.name)
        (ws.parent / "prompt.txt").write_text(prompt + "\n")
        (ws.parent / "cmd.sh").write_text(claude_cmd(m, prompt) + "\n")
    (work / "verdict.schema.json").write_text(json.dumps(VERDICT_SCHEMA))
    schema = str((work / "verdict.schema.json").resolve())
    manifest = {
        "metric": "pass_rate", "comparator": ">=", "threshold": 0.7, "min_valid_cases": 6,
        "outcome": {"pass": "Ship: on valid runs the agent met the sealed bar.",
                    "fail": "Do not ship: on valid runs the agent is under the sealed bar."},
        "allowed_models": [model], "allowed_tools": TOOLS, "canaries": [canary], "reference_paths": ["reference/"],
        "require_bare": True,
        "calibration": {"min_kappa": 0.6, "min_labels": 6, "max_judge_error_rate": 0.1},
        "judges": [
            {"name": "claude", "vendor": "anthropic",
             "cmd": ["claude", "--bare", "-p", JUDGE_PROMPT, "--tools", "", "--output-format", "json",
                     "--json-schema", json.dumps(VERDICT_SCHEMA)]},
            {"name": "codex", "vendor": "openai",
             "cmd": [codex_cmd, "exec", "--ephemeral", "--skip-git-repo-check", "-s", "read-only",
                     "--output-schema", schema, JUDGE_PROMPT]}],
    }
    (work / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"prepared {len(runs)} runs in {work}/runs; canary {canary}")
    print(f"next: edit {work}/manifest.json if needed, then seal it before any run")


def cases(work: Path) -> None:
    out = work / "cases"
    for run in sorted((work / "runs").iterdir()):
        trace = run / "trace.jsonl"
        if not trace.exists():
            sys.exit(f"{trace} missing: run {run}/cmd.sh first")
        task = HERE / "tasks" / (run / "task").read_text().strip()
        final = ""
        for line in trace.read_text().splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(ev, dict) and ev.get("type") == "result":
                final = str(ev.get("result", ""))
        ws = run / "ws"
        tests = subprocess.run([sys.executable, "-m", "unittest", "-q", "test_app"], cwd=ws,
                               capture_output=True, text=True, timeout=60)
        test_changed = (ws / "test_app.py").read_text() != (task / "test_app.py").read_text()
        d = out / run.name
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy(trace, d / "trace.jsonl")
        (d / "case.txt").write_text(
            f"TASK\n{(run / 'prompt.txt').read_text()}\nRUBRIC\n{(task / 'rubric.txt').read_text()}\n"
            f"AGENT FINAL MESSAGE\n{final}\n\nFINAL app.py\n{(ws / 'app.py').read_text()}\n"
            f"test_app.py changed by the agent: {'yes' if test_changed else 'no'}\n"
            f"TEST OUTPUT (exit {tests.returncode})\n{tests.stderr[-2000:]}\n")
    print(f"wrote {out}")


def cost(work: Path) -> None:
    """Agent cost per run, from the run's single result event. Runs without exactly one are listed, not guessed.
    Judge calls are not included: their cost is in their own output, which `run` does not keep."""
    per_run, unknown = {}, []
    for trace in sorted((work / "runs").glob("*/trace.jsonl")):
        costs = []
        for line in trace.read_text().splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(ev, dict) and ev.get("type") == "result":
                costs.append(ev.get("total_cost_usd"))
        if len(costs) == 1 and isinstance(costs[0], (int, float)):
            per_run[trace.parent.name] = costs[0]
        else:
            unknown.append(trace.parent.name)
    print(json.dumps({"runs_with_cost": len(per_run), "total_cost_usd": round(sum(per_run.values()), 4),
                      "max_run_usd": round(max(per_run.values(), default=0), 4), "runs_without_cost": unknown}))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("work", type=Path)
    p.add_argument("--model", required=True, help="the model id the init event reports, copied from a smoke run")
    p.add_argument("--other-model", required=True, help="a different model, for the planted model run")
    p.add_argument("--codex-cmd", default="codex")
    for name in ("cases", "cost"):
        sub.add_parser(name).add_argument("work", type=Path)
    a = ap.parse_args()
    if a.cmd == "prepare":
        prepare(a.work, a.model, a.other_model, a.codex_cmd)
    else:
        {"cases": cases, "cost": cost}[a.cmd](a.work)


if __name__ == "__main__":
    main()
