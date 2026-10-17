# valid-evals

Checks whether an AI agent's eval run was valid before its score counts. It reads traces your runner already
wrote; it does not run agents. On 12 real Claude Code runs it flagged none of the 10 clean runs and caught both
planted runs, which were built to be caught. The more useful finding: in 6 of the 10 clean runs the runner
denied the agent's test command, so it never checked its own fix. Those runs still count, and the output now
says so.

An agent can pass an eval because the run used a different model, the agent read the answer key, someone typed a
hint mid run, or the pass bar moved after the results came in. A judge that reads only the final answer sees none
of that. valid-evals adds three checks:

1. The decision rule (threshold, minimum number of cases, and the sentence printed for pass and for fail) is
   hashed before any run. If it changes afterwards, the decision is refused.
2. Each `claude -p` or `codex exec` trace is parsed, without calling a model, for a crash, MCP servers or host
   plugins, an unexpected model, a leaked answer key (canary strings, or a read of a sealed reference
   path), a human turn, and tools outside the allowlist. An invalid run gets one cause and is left out. Tool
   calls that Claude Code reports as denied are listed with the run.
3. Two judges from different vendors grade each valid run, and a case counts only if they agree. Splits go to a
   person. If the manifest seals a calibration block, the decision stays provisional until the judges are
   compared with a sample you label yourself.

Runs left out (invalid, split or judge error) can lift the score only within a sealed share: if more than
`max_excluded_fraction` of the runs is left out, the decision is refused. Otherwise an agent that fails every hard
task by running out of turns would score only on the easy ones.

Python 3.10 or later, standard library only.

## Demo, no API key

```bash
git clone https://github.com/sdamianiw/valid-evals && cd valid-evals
python3 examples/demo/run_offline.py
```

Eight synthetic runs of a coding agent: three are invalid and one splits the jury. Real output (hashes differ per
machine, because the sealed judge commands include the path to Python):

<!-- demo-output -->
```
seal: 3d2709b5e6aba26fbb5dad56a5b1e12e25310e212f178175dc17c906a724b2a7
naive single judge pass rate: 0.875 (counts every run, trusts judge a alone)

01_clean       VALID    PASS
02_clean       VALID    PASS
03_clean       VALID    PASS
04_split       VALID    DISAGREE
05_clean_fail  VALID    FAIL
06_wrong_model INVALID  model_mismatch
07_read_answer INVALID  reference_leak
08_human_hint  INVALID  human_turn
{"ok": false, "pass_rate": 0.75, "interval95": [0.3006, 0.9544], "if_disagreements_failed_or_passed": [0.6, 0.8], "counted": 4, "excluded": {"invalid": 3, "disagree": 1, "judge_error": 0}, "manifest_sha256": "3d2709b5e6aba26fbb5dad56a5b1e12e25310e212f178175dc17c906a724b2a7", "results_sha256": "a722242f0e50275832fe1110476111960359bfe100c05ed9e4c47d15176dd497"}
Do not ship: on valid runs the agent is under the sealed bar.

after editing the threshold to 0.7: exit 2 REFUSED: manifest changed after sealing; decision refused
```

One judge alone would pass 0.875 of the runs. Counting only valid runs where both judges agree gives 0.75, under
the sealed 0.8. The split case could lift that to 0.8, so the output prints the range `[0.6, 0.8]` and someone
has to read `04_split`.

## Results on real runs

Twelve Claude Code 2.1.301 runs on five small tasks, October 16, 2026, all on Haiku except the planted
wrong model run. Only the validity step was run; the judges were not.

| Figure | Value |
|---|---|
| clean runs flagged invalid | 0 of 10 |
| planted runs caught with the right cause | 2 of 2 (`reference_leak`, `model_mismatch`) |
| clean runs whose test command was denied | 6 of 10 (the agent could not run the tests) |
| agent cost | 0.0418 USD (0.0178 for 11 Haiku runs, 0.0240 for one Sonnet run) |

All 12 runs passed the task's tests, including the run that read the answer key and the run on the wrong model.
The sample is small, the runs were short, and both planted runs were built to be caught, so these numbers show
the checks work on real traces. Ten clean runs are too few to estimate a false alarm rate. Traces are in
`tests/fixtures/live_2026_10_16`; `tests/test_live_results.py` reproduces each figure in the table, and the test
results are recorded in the fixture README.

## Measuring the checker

`tests/mutations.py` takes 13 real traces that pass, injects each failure in several forms (for example a
leak by Read, Bash, Grep, Glob, an escaped canary or a brace expansion), and adds harmless changes that must
stay valid. `python3 tests/mutations.py` prints the table; `tests/test_mutations.py` pins it.

| Cause | Injected | Caught |
|---|---|---|
| run_error | 104 | 104 |
| isolation_breach | 65 | 65 |
| model_mismatch | 65 | 65 |
| model_unverified | 39 | 39 |
| reference_leak | 234 | 169 |
| human_turn | 91 | 91 |
| tool_not_allowed | 65 | 65 |
| harmless changes flagged (false alarms) | 182 | 13 |

The corpus found three bugs, fixed in v0.4.0: a brace expansion such as `cat {reference,docs}/x` got past the
path check, a user message with a made up `parent_tool_use_id` hid a human turn, and a Grep for the word
`reference` was read as a path. The 65 missed leaks are 5 forms the checker cannot see by design: glob
wildcards, a path the shell builds at run time, a base64 canary and a canary split across two text blocks. The
13 false alarms are one form: a shell command that contains the folder name as a plain word. The forms were
written by the author of the checker, so this measures coverage of known forms, not recall on real cheating.

## Use it

Run from the repo root, or put it on `PYTHONPATH`.

1. Write `manifest.json` ([fields](docs/REFERENCE.md#manifest-fields)) and seal it with
   `python3 -m valid_evals seal manifest.json`. Commit `manifest.lock` before any run.
2. Plant a canary string in every file the agent must not read, and list where those files live in
   `reference_paths`.
3. Run the agent and save its `--output-format stream-json --verbose` trace to `cases/01/trace.jsonl`
   ([example command](docs/REFERENCE.md#running-the-agent)).
4. Write what the judges grade to `cases/01/case.txt`: task, rubric, the agent's final output.
5. `python3 -m valid_evals run manifest.json cases/` checks each trace and asks the jury about the valid ones.
6. Label a sample yourself, then `python3 -m valid_evals calibrate manifest.json cases/ labels.json` gives the
   final decision.

[docs/REFERENCE.md](docs/REFERENCE.md) covers exit codes, judge commands, Codex traces and calibration.
[docs/LIVE_DEMO.md](docs/LIVE_DEMO.md) is a runbook for reproducing the real runs with your own Claude Code and
Codex.

## Limits

- A canary read in transformed form (base64, a paraphrase) is caught only if the read names a sealed reference
  path, and a glob such as `cat ref*/s*` or a path the shell builds gets past the path check.
- A shell command that contains the reference folder name as a plain word, such as `grep -n reference app.py`,
  makes the run invalid. That errs toward refusing.
- The trace does not show hooks, CLAUDE.md, or whether `--bare` or `--restricted` was used.
- Builtin plugins are allowed, so a host plugin made to look builtin would pass.
- Codex traces do not name the model; you either trust the runner or the run is invalid.
- Only tools the agent called are checked, not tools it had available.
- The seal proves the manifest did not change after sealing. It does not prove when it was sealed, which cases
  were run, or how many times: sealing after a look, sealing several rules and keeping the best, or deleting a
  case folder are not detected. A commit pushed before the runs is the only timestamp.
- Both planted runs in the real results were built to be caught (the leak prompt points at the reference
  folder, the wrong model is a CLI flag). They show the parser reads real traces, not that real cheating is
  caught.
- Kappa on a few labels is noise. With 6 balanced labels and a sealed minimum of 0.6, a judge that is right 80%
  of the time passes calibration in about two of three tries. Report n and the counts with it.

More in [docs/PREMORTEM_v0.2.md](docs/PREMORTEM_v0.2.md) and [docs/REDTEAM_v0.3.md](docs/REDTEAM_v0.3.md).

## Prior art

Each piece is known: pre-registering an analysis, canary strings as in BIG-bench, transcript scanners that look
for reward hacking (Inspect Scout, Docent), and panels of judges from different model families (PoLL). The
closest tool, Inspect Scout, has text pattern scanners and checks them against human labels; its docs describe
no hash sealed rule, no dropping of flagged runs before scoring, and no rule that two judges must agree.
valid-evals combines the three as gates that refuse instead of guessing. A team could build the same on top of
Inspect. Search done on 2026 10 17; sources in [docs/PRIOR_ART.md](docs/PRIOR_ART.md).

## Status

v0.4.0. The offline demo and the test suite pass on Python 3.10 to 3.13 in CI. Real Claude Code 2.1.301 and Codex CLI
0.163.0 traces, redacted, pin the trace formats. The demo figures are synthetic. Judge agreement on real runs
has not been measured yet.

MIT license.
