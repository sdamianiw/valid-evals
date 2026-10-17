# valid-evals

Checks whether an AI agent's eval run was valid before its score counts. It reads traces your runner already
wrote; it does not run agents.

An agent can pass an eval because the run used a different model, the agent read the answer key, someone typed a
hint mid run, or the pass bar moved after the results came in. A judge that reads only the final answer sees none
of that. valid-evals adds three checks:

1. The decision rule (threshold, minimum number of cases, and the sentence printed for pass and for fail) is
   hashed before any run. If it changes afterwards, the decision is refused.
2. Each `claude -p` or `codex exec` trace is checked with plain parsing, no model call, for a crash, MCP servers
   or host plugins, an unexpected model, a leaked answer key (canary strings, or a read of a sealed reference
   path), a human turn, and tools outside the allowlist. An invalid run gets one cause and is left out.
3. Two judges from different vendors grade each valid run, and a case counts only if they agree. Splits go to a
   person. Before the decision is final, the judges are compared with a sample you label yourself.

Python 3.10 or later, standard library only.

## Demo, no API key

```bash
git clone https://github.com/sdamianiw/valid-evals && cd valid-evals
python3 examples/demo/run_offline.py
```

Eight synthetic runs of a coding agent: three cheat and one splits the jury. Real output (hashes differ per
machine, because the sealed judge commands include the path to Python):

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
{"ok": false, "pass_rate": 0.75, "interval95": [0.3006, 0.9544], "if_disagreements_failed_or_passed": [0.6, 0.8], "counted": 4, "excluded": {"invalid": 3, "disagree": 1, "judge_error": 0}, "manifest_sha256": "286e64daab3dcd8023072ec8123a7fe645a09b2d7ea8a7d97676e467c9efa1c8", "results_sha256": "7e06165d61c7a9834fdaf3c2106f1dc530006a8a7919d2923061418e603a0cbd"}
Do not ship: on valid runs the agent is under the sealed bar.

after editing the threshold to 0.7: exit 2 REFUSED: manifest changed after sealing; decision refused
```

One judge alone would pass 0.875 of the runs. Counting only valid runs where both judges agree gives 0.75, under
the sealed 0.8. The split case could lift that to 0.8, so the output prints the range `[0.6, 0.8]` and someone
has to read `04_split`. The edited threshold is refused.

## Results on real runs

Twelve Claude Code 2.1.301 runs on five small tasks, October 16, 2026, all on Haiku except the planted
wrong model run. Only the validity step was run;
the judges were not.

| Figure | Value |
|---|---|
| clean runs flagged invalid | 0 of 10 |
| planted runs caught with the right cause | 2 of 2 (`reference_leak`, `model_mismatch`) |
| agent cost | 0.0418 USD (0.0178 for 11 Haiku runs, 0.0240 for one Sonnet run) |

All 12 runs passed the task's tests, including the run that read the answer key and the run on the wrong model.
The sample is small, the runs were short, and both planted runs were built to be caught, so these numbers show
the checks work on real traces, not a false alarm rate. Traces: `tests/fixtures/live_2026_10_16`; each figure is
reproduced by `tests/test_live_results.py`.

## Use it

Run from the repo root, or put it on `PYTHONPATH`.

1. Write `manifest.json` ([fields](docs/REFERENCE.md#manifest-fields)) and seal it with
   `python3 -m valid_evals seal manifest.json`. Commit `manifest.lock` before any run.
2. Plant a canary string in every file the agent must not read, and list where those files live in
   `reference_paths`.
3. Run the agent and save its trace. For Claude Code, `--tools` limits what the agent can call and
   `--allowedTools` only pre approves, so pass both. Use `--bare` with an API key, or
   `--restricted --strict-mcp-config` with a subscription login:
   `claude --restricted --strict-mcp-config -p "$TASK" --model claude-sonnet-5-5 --tools "Read,Grep,Edit" --allowedTools "Read,Grep,Edit" --output-format stream-json --verbose > cases/01/trace.jsonl`
4. Write what the judges grade to `cases/01/case.txt`: task, rubric, the agent's final output.
5. `python3 -m valid_evals run manifest.json cases/` checks each trace and asks the jury about the valid ones.
6. Label a sample yourself, then `python3 -m valid_evals calibrate manifest.json cases/ labels.json` gives the
   final decision.

[docs/REFERENCE.md](docs/REFERENCE.md) covers exit codes, judge commands, Codex traces and calibration.
[docs/LIVE_DEMO.md](docs/LIVE_DEMO.md) is a runbook for reproducing the real runs with your own Claude Code and
Codex.

## Limits

- A canary read in transformed form (base64, a paraphrase) is caught only if the read names a sealed reference
  path, and a glob such as `cat ref*/s*` gets past the path check.
- The trace does not show hooks, CLAUDE.md, or whether `--bare` or `--restricted` was used.
- Builtin plugins are allowed, so a host plugin made to look builtin would pass.
- Codex traces do not name the model; you either trust the runner or the run is invalid.
- Only tools the agent called are checked, not tools it had available.
- Kappa on a few labels is noise; report n with it.

More in [docs/PREMORTEM_v0.2.md](docs/PREMORTEM_v0.2.md) and [docs/REDTEAM_v0.3.md](docs/REDTEAM_v0.3.md).

## Prior art

Each piece is known: pre-registering an analysis, canary strings in eval data as in BIG-bench, and checking LLM
judges against human labels with Cohen's kappa. This repo puts the three in front of an agent eval score.

## Status

v0.3.1. The offline demo and 133 tests pass on Python 3.10 to 3.13 in CI. Real Claude Code 2.1.301 and Codex CLI
0.163.0 traces, redacted, pin the trace formats. The demo figures are synthetic. Judge agreement on real runs
has not been measured yet.

MIT license.
