# Reference

## Manifest fields

| Field | Required | Meaning |
|---|---|---|
| `metric` | yes | `pass_rate` |
| `comparator`, `threshold` | yes | for example `>=` and `0.8`; the threshold is between 0 and 1 |
| `min_valid_cases` | yes | with fewer counted cases the decision is refused |
| `max_excluded_fraction` | yes | between 0 and 1. If a larger share of runs is left out of the pass rate (invalid, split or judge error), the decision is refused. Dropping runs can still lift the score, but only within that share |
| `outcome` | yes | `{"pass": "...", "fail": "..."}`, the sentence printed for each result |
| `allowed_models` | yes | model ids the trace must report; an alias matches its dated snapshots, a dated id only itself |
| `allowed_tools` | yes | tool names as the trace shows them (Claude Code 2.1.301 logs `--tools Task` as `Agent`) |
| `canaries` | yes | at least one string, planted in every reference file |
| `require_bare` | yes | `true`: an MCP server, or a plugin that is not one of the CLI's builtin plugins, makes the run invalid |
| `judges` | yes | two judges with different names, vendors and commands, each `{"name", "vendor", "cmd": [...]}` |
| `reference_paths` | no | path fragments; a tool call that names one as whole path segments is a leak. Case folded, `\` read as `/`, prose fields such as `content` or `description` skipped |
| `trust_runner_model` | no | `true` accepts Codex runs, whose trace names no model |
| `calibration` | no | `{"min_kappa", "min_labels", "max_judge_error_rate"}`; `run` stays provisional until `calibrate` passes |

Unknown keys, duplicate keys, NaN and Infinity are refused, so a typo cannot switch a guard off.

## Exit codes

| Command | 0 | 1 | 2 |
|---|---|---|---|
| `run` | rule passed, no calibration sealed | rule failed, or provisional | refused: broken seal, too few counted cases, too many runs left out, bad input |
| `calibrate` | jury calibrated and rule passed | jury calibrated, rule failed | refused: jury not calibrated, no calibration sealed, too few or bad labels, `results.jsonl` not from this rule, code and traces |
| `check` | every trace valid | a trace is invalid | refused |

## Running the agent

For Claude Code, `--tools` limits what the agent can call and `--allowedTools` only pre approves, so pass both:

```bash
claude --restricted --strict-mcp-config -p "$TASK" --model claude-sonnet-5-5 \
  --tools "Read,Grep,Edit" --allowedTools "Read,Grep,Edit" \
  --output-format stream-json --verbose > cases/01/trace.jsonl
```

## Keeping Claude Code clean of host config

Run the agent and the Claude judge with `--bare` if you use `ANTHROPIC_API_KEY`, or with
`--restricted --strict-mcp-config` if you log in with a subscription. `--bare` reads only the API key. `--restricted`
ignores user, project and local settings files, so their hooks, and `--strict-mcp-config` drops MCP servers
(both per `claude --help`). With a subscription login on 2.1.301, a restricted run also did not load a CLAUDE.md
that a normal run obeyed (0 of 2 against 2 of 2). The init event shows MCP servers and
plugins, which `require_bare` checks, but it does not show which of the two modes ran, so keep the command with
the results.

## Judges

A judge is any command that reads the case on stdin and prints `{"verdict": "pass"}` or `{"verdict": "fail"}`. It
runs in an empty temporary directory, so it sees only the case. Its output is read as one JSON value, or else as
its last line. The output of `claude -p --output-format json --json-schema` is understood through its
`structured_output` field, a shape pinned by a real call in `tests/fixtures`.

```json
{"name": "claude", "vendor": "anthropic",
 "cmd": ["claude", "--restricted", "--strict-mcp-config", "-p", "Grade this case against its rubric. Answer pass or fail.",
         "--tools", "", "--output-format", "json",
         "--json-schema", "{\"type\":\"object\",\"properties\":{\"verdict\":{\"type\":\"string\",\"enum\":[\"pass\",\"fail\"]}},\"required\":[\"verdict\"],\"additionalProperties\":false}"]}
```

The second judge must come from another vendor. `examples/live/live.py` builds one with `codex exec
--output-schema`; that judge has not been run against a live call yet.

## Codex traces

A `codex exec --json` trace is detected by its shape. One real failed run and the Codex SDK event types pin the
format; no successful Codex run has been checked yet. Flags from `codex exec --help` (0.163.0):
`codex exec --json --ephemeral --ignore-user-config -s workspace-write "$TASK" > cases/01/trace.jsonl`.

The Codex trace does not name the model, so a Codex run is INVALID with `model_unverified` unless the sealed
manifest sets `"trust_runner_model": true`. In `allowed_tools`, Codex tools are named by item type:
`command_execution`, `file_change`, `web_search`, `mcp:<server>/<tool>`. An MCP call in a `require_bare` run is an
isolation breach, and a second `turn.started` means a prompt was added during the run, which counts as a human turn.

## Calibrating the judges

Seal a block such as `"calibration": {"min_kappa": 0.6, "min_labels": 20, "max_judge_error_rate": 0.1}`. After
`run`, label a sample as `{"case": "pass"|"fail"}` without looking at the votes, then run
`python3 -m valid_evals calibrate manifest.json cases/ labels.json`. It prints n, the 2x2 counts, raw agreement
and Cohen's kappa for judge against judge and each judge against you, each judge's error rate, and the decision.
Kappa is undefined when every label is the same, and that fails. Your labels say whether to trust the jury; they
do not change the decision.

`calibrate` checks `results.jsonl` before using it. Every row must carry the hashes of this manifest and of this
version of the code, every case folder needs its row, each trace is hashed and checked again, and each verdict
must follow from its votes.

`run` prints a Wilson 95% interval and the pass rate if every split case had gone to fail or to pass.
When that range crosses the bar, the split cases decide the outcome.
