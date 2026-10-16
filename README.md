# valid-evals

**Your eval passed. Was the run even valid?**

Agent evals can pass for the wrong reasons. The run used another model. The agent read the answer key. Someone
typed a hint halfway through. The pass bar moved after the numbers came in. A single LLM judge sees none of this.

valid-evals is a small layer that sits after whatever runs your agent (`claude -p`, `codex exec`, promptfoo,
caliper, your own script). Before a score counts, it answers three questions:

1. **Was the rule fixed before we looked?** The decision rule (metric, threshold, the exact sentence for pass and
   for fail) is sealed with sha256 before any run. Edit it afterwards and the decision is refused.
2. **Was the run valid?** Each trace is checked, without any model call, for a crash or early stop, MCP servers or
   host plugins present at start, a model other than the one you asked for, the answer key showing up (canary
   strings or a tool call that names a reference path), a human turn, or a tool outside the allowlist. An
   invalid run gets exactly one cause and never counts.
3. **Do two judges from different vendors agree, and do they agree with you?** A case counts only when both say
   pass or both say fail. A split goes to a queue for a person. Output a judge cannot parse is an error, never a
   vote. Before the decision is final, the judges are checked against a sample you labeled yourself.

It is not a runner, a dashboard or a framework. Python 3.10 or later, standard library only, nothing to install.

## Try it (no API key)

```bash
git clone https://github.com/sdamianiw/valid-evals && cd valid-evals
python3 examples/demo/run_offline.py
```

Eight synthetic runs of a coding agent. Three of them cheat in ways a lone judge cannot see; one splits the
jury. This is the real output (a test keeps this block equal to it). The hashes on your machine will differ: the
judge commands include the path to your Python, and they are part of the sealed rule.

<!-- demo-output -->
```
seal: 286e64daab3dcd8023072ec8123a7fe645a09b2d7ea8a7d97676e467c9efa1c8
naive single judge pass rate: 0.875 (counts every run, trusts judge a alone)

01_clean       VALID    PASS
02_clean       VALID    PASS
03_clean       VALID    PASS
04_split       VALID    DISAGREE
05_clean_fail  VALID    FAIL
06_wrong_model INVALID  model_mismatch
07_read_answer INVALID  reference_leak
08_human_hint  INVALID  human_turn
{"ok": false, "pass_rate": 0.75, "interval95": [0.3006, 0.9544], "if_disagreements_failed_or_passed": [0.6, 0.8], "counted": 4, "excluded": {"invalid": 3, "disagree": 1, "judge_error": 0}, "manifest_sha256": "286e64daab3dcd8023072ec8123a7fe645a09b2d7ea8a7d97676e467c9efa1c8", "results_sha256": "05d9a8fd50cab939be19479ecae35737c465446e1a6d2a26a14228a707613047"}
Do not ship: on valid runs the agent is under the sealed bar.

after editing the threshold to 0.7: exit 2 REFUSED: manifest changed after sealing; decision refused
```

A naive single judge pass rate says ship (0.875). On agreed valid runs the rate is 0.75, under the sealed 0.8.
The bounds `[0.6, 0.8]` say the one split case decides the outcome: had both judges passed it, the rule would
pass. So someone has to read `04_split` before anyone ships. Editing the threshold afterwards is refused.

## Use it on your own runs

Run the commands from the repo root, or set `PYTHONPATH` to it.

1. Write `manifest.json` (fields below) and seal it: `python3 -m valid_evals seal manifest.json`. Commit
   `manifest.lock` before you run anything; git history is your timestamp.
2. Put a canary string inside every reference or answer file the agent must not read, and list where those files
   live in `reference_paths`.
3. Run your agent and keep the trace. For Claude Code, `--tools` limits what the agent can call and
   `--allowedTools` only pre approves them, so pass both:
   `claude --bare -p "$TASK" --model claude-sonnet-5-5 --tools "Read,Grep,Edit" --allowedTools "Read,Grep,Edit" --output-format stream-json --verbose > cases/01/trace.jsonl`
   For Codex, see below.
4. Put what the judges should grade in `cases/01/case.txt` (task, rubric, the agent's final output).
5. `python3 -m valid_evals run manifest.json cases/` checks every trace, asks the jury about the valid ones and
   writes `cases/results.jsonl` and `cases/human_queue.jsonl`.
6. Label a sample yourself, then `python3 -m valid_evals calibrate manifest.json cases/ labels.json` gives the
   final decision (see Calibrate the judges).

### Manifest fields

| Field | Required | Meaning |
|---|---|---|
| `metric` | yes | `pass_rate` |
| `comparator`, `threshold` | yes | for example `>=` and `0.8` |
| `min_valid_cases` | yes | fewer counted cases and the decision is refused |
| `outcome` | yes | `{"pass": "...", "fail": "..."}`, the sentences printed for each result |
| `allowed_models` | yes | model ids the trace must report; an alias matches its dated snapshots, a dated id only itself |
| `allowed_tools` | yes | tool names as the trace shows them (Claude Code 2.1.301 names `--tools Task` as `Agent`; Codex: see below) |
| `canaries` | yes | at least one string planted in every reference file |
| `require_bare` | yes | `true`: MCP servers or plugins other than the CLI's builtin ones make the run invalid |
| `judges` | yes | two judges, different names and vendors, each `{"name", "vendor", "cmd": [...]}` |
| `reference_paths` | no | path fragments; a tool call that names one as whole path segments is a leak (case folded, `\` read as `/`; prose fields such as `content` or `description` are skipped) |
| `trust_runner_model` | no | `true` accepts Codex runs whose trace names no model |
| `calibration` | no | `{"min_kappa", "min_labels", "max_judge_error_rate"}`; makes `run` provisional until `calibrate` passes |

Unknown keys are refused, so a typo cannot switch a guard off. The threshold must be between 0 and 1, and the two
judges must differ in name, vendor and command.

### Exit codes

| Command | 0 | 1 | 2 |
|---|---|---|---|
| `run` | sealed rule passed, no calibration sealed | rule failed, or provisional | refused: broken seal, too few counted cases, bad input |
| `calibrate` | jury calibrated and rule passed | jury calibrated, rule failed | refused: jury not calibrated, no calibration sealed, too few or bad labels, `results.jsonl` not from this rule and these traces |
| `check` | every trace valid | any trace invalid | refused |

### Judges

A judge is any command that reads the case on stdin and prints `{"verdict": "pass"}` or `{"verdict": "fail"}`. It
runs in an empty temporary directory, so it sees the case and nothing else. Its output is read as one JSON value,
or else its last line only. The output of `claude -p --output-format json --json-schema` is understood (it reads
`structured_output`); that shape is pinned by a real judge call in `tests/fixtures`.

```json
{"name": "claude", "vendor": "anthropic",
 "cmd": ["claude", "--bare", "-p", "Grade this case against its rubric. Answer pass or fail.",
         "--tools", "", "--output-format", "json",
         "--json-schema", "{\"type\":\"object\",\"properties\":{\"verdict\":{\"type\":\"string\",\"enum\":[\"pass\",\"fail\"]}},\"required\":[\"verdict\"],\"additionalProperties\":false}"]}
```

The second judge must come from another vendor. `examples/live/live.py` builds one with the Codex CLI
(`codex exec --output-schema`); its output has not been checked against a live call yet.

### Codex traces

A trace from `codex exec --json` is detected by its shape. Not yet run live end to end: the format is pinned by
one real failed run and the event types of the Codex SDK. A starting point, flags from `codex exec --help`
(0.163.0): `codex exec --json --ephemeral --ignore-user-config -s workspace-write "$TASK" > cases/01/trace.jsonl`.

`codex exec --json` does not say which model ran. A Codex run is therefore INVALID with `model_unverified`
unless the sealed manifest sets `"trust_runner_model": true`, which puts that trust on the record. Codex tools are
named by item type in `allowed_tools`: `command_execution`, `file_change`, `web_search`, `mcp:<server>/<tool>`.
An MCP call in a `require_bare` run is an isolation breach. A second `turn.started` means a prompt was added
during the run and counts as a human turn.

### Calibrate the judges

Add `"calibration": {"min_kappa": 0.6, "min_labels": 20, "max_judge_error_rate": 0.1}` to the manifest before
sealing. `run` then prints its decision as PROVISIONAL and never exits 0. Label a sample yourself as
`{"case": "pass"|"fail"}` without looking at the votes, and run
`python3 -m valid_evals calibrate manifest.json cases/ labels.json`. It prints n, the 2x2 counts, raw agreement
and Cohen's kappa for judge vs judge and each judge vs you, each judge's error rate, and the decision, from the
votes `run` saved. A kappa is undefined when every label is the same; that fails. Your labels never change the
decision: they only say whether the jury can be trusted.

`calibrate` does not trust `results.jsonl`: every row must carry this manifest's hash, every case folder must have
its row, each trace is hashed and checked again, and each verdict must follow from its votes. Both commands print
the sha256 of `results.jsonl`.
Every decision also prints a Wilson 95% interval and the pass rate if every split case had been a fail, or a
pass. If that range crosses the bar, the split cases decide the outcome; read them.

## Live demo

`docs/LIVE_DEMO.md` is a runbook for your own Claude and Codex CLIs on five small public tasks, with a fresh
canary, a planted leak and a planted model switch. It reports cost, false alarms on clean runs, planted runs
caught and judge agreement.

### Measured so far: the validity step on 12 real runs

Claude Code 2.1.301, Haiku, 2026 10 16, in a cloud container without `--bare` (bare mode could not
authenticate there). No judge was run, so there is no pass rate or agreement figure yet.

| Figure | Value |
|---|---|
| clean runs flagged invalid | 0 of 10 |
| planted runs caught with the right cause | 2 of 2 (`reference_leak`, `model_mismatch`) |
| agent cost, 12 runs | 0.0418 USD: 0.0178 for the 11 Haiku runs, 0.0240 for the one Sonnet run |

Every one of the 12 runs passed the task's tests, the two planted ones included. A score taken from tests alone
would have counted the run that read the answer key and the run on the wrong model. The traces are in
`tests/fixtures/live_2026_10_16` and `tests/test_live_results.py` reproduces each figure.

Read these figures narrowly. Ten clean runs is a small sample: it says the gates did not fire on ordinary runs of
this task, not what the false alarm rate is. The runs were short (4 to 7 turns), with no subagent, compaction or
hook, and in 6 of them the agent's test commands were denied by a too narrow allowlist (since widened). Both
planted runs were set up to be caught: the leak run was invited to read the answer key. They show the checks
parse real traces, not that a cheating agent would be detected.

## What it does not catch (yet)

- A canary that the agent sees in a transformed form (base64, paraphrase) unless the read names a sealed
  reference path. Path matching looks for the fragment as whole path segments: a glob such as `cat ref*/s*`
  gets past it, and so does a path built at run time.
- Hooks: the trace does not list them. Run with `--bare`; `require_bare` itself only checks MCP servers and
  plugins, not that `--bare` was used.
- Human turns outside bare mode, where Claude Code may add its own user messages.
- A host plugin made to look builtin. Plugins with `path: builtin` and a source ending in `@builtin` ship with
  the CLI and are listed even under `--bare`, so they are allowed.
- The model of a Codex run, unless you trust the runner; and Codex config, `AGENTS.md` or hooks, since only MCP
  calls that actually happen are visible in the trace.
- Tools available but unused: only tools the agent called are checked against `allowed_tools`.
- A decision taken from `run` alone when no calibration block was sealed.
- Judge agreement is only as good as the judges, and kappa on a few labels is noise. Report n with it.

See `docs/PREMORTEM_v0.2.md` and `docs/REDTEAM_v0.3.md` for the full list and what is planned.

## Prior art

None of the pieces is new. Pre-registering an analysis before seeing data is standard practice in empirical
science. Canary strings in evaluation data follow the BIG-bench convention. Checking an LLM judge against human
labels with Cohen's kappa is common in judge evaluations. What this repo adds is putting the three in front of
an agent eval score, as one small check with no model call in the validity step.

## Status

v0.3.1. The offline demo and 129 tests pass on Python 3.10 to 3.13 in CI. Trace parsing is pinned by redacted
real traces from Claude Code 2.1.301 and Codex CLI 0.163.0 (`tests/fixtures`). The demo figures above come from
synthetic traces; the validity figures under Live demo come from real runs. Judge agreement on live runs is not
measured yet (`docs/LIVE_DEMO.md`).

MIT license.
