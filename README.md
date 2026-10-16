# valid-evals

**Your eval passed. Was the run even valid?**

Agent evals can pass for the wrong reasons. The run used another model. The agent read the answer key. Someone
typed a hint halfway through. The pass bar moved after the numbers came in. A single LLM judge sees none of this.

valid-evals is a small layer that sits after whatever runs your agent (`claude -p`, `codex exec`, promptfoo,
caliper, your own script). Before a score counts, it answers three questions:

1. **Was the rule fixed before we looked?** The decision rule (metric, threshold, the exact sentence for pass and
   for fail) is sealed with sha256 before any run. Edit it afterwards and the decision is refused.
2. **Was the run valid?** Each trace is checked, without any model call, for a crash, host hooks or MCP servers
   leaking in, a model other than the one you asked for, the answer key showing up (canary strings), a human turn,
   or a tool outside the allowlist. An invalid run gets exactly one cause and never counts.
3. **Do two judges from different vendors agree?** A case counts only when both say pass or both say fail. A split
   goes to a queue for a person. Output a judge cannot parse is counted as an error, never as a vote.

It is not a runner, a dashboard or a framework. Python standard library only.

## Try it (no API key)

```bash
git clone https://github.com/sdamianiw/valid-evals && cd valid-evals
python3 examples/demo/run_offline.py
```

Eight synthetic runs of a coding agent. Three of them cheat in ways a lone judge cannot see.

```
naive single judge pass rate: 0.875 (counts every run, trusts judge a alone)

01_clean       VALID    PASS
04_split       VALID    DISAGREE
06_wrong_model INVALID  model_mismatch
07_read_answer INVALID  reference_leak
08_human_hint  INVALID  human_turn
...
{"ok": false, "pass_rate": 0.75, "counted": 4, "excluded": {"invalid": 3, "disagree": 1, "judge_error": 0}, ...}
Do not ship: on valid runs the agent is under the sealed bar.

after editing the threshold to 0.7: exit 2 REFUSED: manifest changed after sealing; decision refused
```

The naive number says ship. The valid number says do not.

## Use it on your own runs

1. Write `manifest.json` (see `examples/demo/run_offline.py` for every field) and seal it:
   `python3 -m valid_evals seal manifest.json`. Commit `manifest.lock` before you run anything; git history is
   your timestamp.
2. Put a canary string inside every reference or answer file the agent must not read (the manifest needs at
   least one), and list the reference locations in `reference_paths`: a tool call that names one is a leak even
   when the agent transforms what it reads so the canary never shows.
3. Run your agent in bare mode and keep the trace:
   `claude --bare -p "$TASK" --model claude-sonnet-5-5 --allowedTools "Read,Grep,Edit" --output-format stream-json --verbose > cases/01/trace.jsonl`
   or `codex exec --json --ephemeral "$TASK" > cases/01/trace.jsonl`. The trace shape is detected; any other
   shape is a run error.
4. Put what the judges should grade in `cases/01/case.txt` (task, rubric, the agent's final output).
5. `python3 -m valid_evals run manifest.json cases/`

Exit code 0 means the sealed rule passed, 1 means it failed, 2 means the decision was refused.

### Judges

A judge is any command that reads the case on stdin and prints `{"verdict": "pass"}` or `{"verdict": "fail"}`.
The output of `claude -p --output-format json --json-schema` is also understood (it reads `structured_output`).

```json
{"name": "claude", "vendor": "anthropic",
 "cmd": ["claude", "--bare", "-p", "Grade this case against its rubric. Answer pass or fail.",
         "--output-format", "json",
         "--json-schema", "{\"type\":\"object\",\"properties\":{\"verdict\":{\"enum\":[\"pass\",\"fail\"]}},\"required\":[\"verdict\"]}"]}
```

The second judge must come from another vendor, for example an OpenAI model through the Codex CLI or a small
script that calls any other API. The seal step rejects two judges from the same vendor.

### Codex traces

`codex exec --json` does not say which model ran. A Codex run is therefore INVALID with `model_unverified`
unless the sealed manifest sets `"trust_runner_model": true`, which puts that trust on the record. Codex tools are
named by item type in `allowed_tools`: `command_execution`, `file_change`, `web_search`, `mcp:<server>/<tool>`.
An MCP call in a `require_bare` run is an isolation breach. A second `turn.started` means a prompt was added
during the run and counts as a human turn.

### Calibrate the judges

Add `"calibration": {"min_kappa": 0.6, "min_labels": 20, "max_judge_error_rate": 0.1}` to the manifest before
sealing. `run` then prints its decision as PROVISIONAL. Label a sample yourself as `{"case": "pass"|"fail"}`
without looking at the votes, and run `python3 -m valid_evals calibrate manifest.json cases/ labels.json`. It
prints n, the 2x2 counts, raw agreement and Cohen's kappa for judge vs judge and each judge vs you, each judge's
error rate, and the decision, from the votes `run` saved (with their sha256). Exit 0 only when the jury is
calibrated and the sealed rule passes, 1 when either does not, 2 when it refuses (no sealed calibration, too few
labels, a bad label). A kappa is undefined when every label is the same; that fails. Your labels never change
the decision: they only say whether the jury can be trusted.

Every decision also prints a Wilson 95% interval and the pass rate if every split case had been a fail, or a
pass. If that range crosses the bar, the split cases decide the outcome; read them.

## Live demo

`docs/LIVE_DEMO.md` is a runbook for your own Claude and Codex CLIs on five small public tasks, with a fresh
canary, a planted leak and a planted model switch. It reports cost, invalid runs caught and judge agreement.

## What it does not catch (yet)

- A canary that the agent sees in a transformed form (base64, paraphrase). Canaries catch copies, not understanding.
- Human turns outside bare mode, where Claude Code adds its own user messages. Use `require_bare`.
- A host plugin made to look builtin. Plugins with `path: builtin` and a source ending in `@builtin` ship with
  the CLI and are listed even under `--bare`, so they are allowed.
- The model of a Codex run, unless you trust the runner; and Codex config, `AGENTS.md` or hooks, since only MCP
  calls that actually happen are visible in the trace.
- A decision taken from `run` alone when no calibration block was sealed. With one, `run` is only provisional.
- Edits to `results.jsonl` between `run` and `calibrate` are not refused: both print its sha256, compare them.
- Judge agreement is only as good as the judges, and kappa on a few labels is noise. Report n with it.

See `docs/PREMORTEM_v0.2.md` and `docs/REDTEAM_v0.3.md` for the full list and what is planned.

## Status

v0.3. The offline demo and 99 tests pass. Trace parsing is pinned by redacted real traces from Claude Code
2.1.301 and Codex CLI 0.163.0 (`tests/fixtures`). The demo figures above come from synthetic traces; figures
from live runs will be added once measured with `docs/LIVE_DEMO.md`.

MIT license.
