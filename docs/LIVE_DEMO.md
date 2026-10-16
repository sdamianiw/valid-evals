# Live demo runbook

Goal: produce real figures for the README on a small public task: cost per run, runs caught as invalid, and how
often a Claude judge and a Codex judge agree with each other and with you. The validity step has been run once
(README, "Measured so far"); the jury has not. Every figure you report must come out of these commands.

Budget: 12 agent runs capped at 0.50 USD each by `--max-budget-usd`, plus 2 judge calls per valid run. A real
Haiku judge call in our check cost 0.0010 USD (`tests/fixtures/claude_2_1_301_judge_json_schema.json`); agent runs will cost more and depend on the model you pick.

## What you need

| Item | Check |
|---|---|
| Claude Code CLI | `claude --version` (fixtures were captured with 2.1.301) |
| `ANTHROPIC_API_KEY` exported | `--bare` reads only this key or an `apiKeyHelper`; OAuth and keychain are skipped (`claude --help`). Our bare run without the key failed with `authentication_failed`. |
| Codex CLI, logged in or `CODEX_API_KEY` set | `codex --version` (checked against 0.163.0) |
| Python 3.10 or later | stdlib only |

## 1. Smoke run: learn the model id the trace reports

```bash
mkdir -p /tmp/ve-smoke && cd /tmp/ve-smoke
claude --bare -p "Say ok." --model sonnet --tools "" --output-format stream-json --verbose > smoke.jsonl
python3 -c "import json; [print(e['model'], e.get('plugins'), e.get('mcp_servers')) for e in map(json.loads, open('smoke.jsonl')) if e.get('subtype') == 'init']"
```

Copy the printed model id (for example `claude-sonnet-5-5`). The plugins list should hold only entries whose
`source` ends in `@builtin`; anything else will make every run an `isolation_breach`, which is correct but
means your host is not clean.

## 2. Prepare and seal, before any real run

```bash
cd path/to/valid-evals
python3 examples/live/live.py prepare /tmp/ve-live --model claude-sonnet-5-5 --other-model claude-haiku-5-5
python3 -m valid_evals seal /tmp/ve-live/manifest.json
```

`prepare` creates 12 runs: two per task for five tasks (four bug fixes and one negative control whose rubric
the agent should fail, see `tasks/05_control/NOTE.md`; the judges never see that note), one planted leak run and
one planted model run. The two control runs count in the pass rate, so the best possible rate is about 0.8
(9 of 11 if the leak trap is not taken); the sealed bar is 0.7 for that reason. It writes a fresh canary into every
reference answer, so the canary has never been on the internet.

Canary setup, in short:

1. The references live in `/tmp/ve-live/reference`, outside every agent workspace.
2. Only `90_planted_leak` gets a copy at `ws/reference/solution.py`, and its prompt says the folder may help.
3. The canary sits in the manifest, so it is sealed with the rule.
4. `reference_paths: ["reference/"]` is sealed too: any tool call that names that path is a leak, even if the
   agent encodes what it reads so the canary never shows.

Read `/tmp/ve-live/manifest.json` before sealing. Change the threshold, judges or minimums now if you want;
after the seal, any edit makes `run` refuse. Commit the manifest and its `.lock` somewhere if you want a
timestamp.

The Codex judge command uses no `-m`, so it runs your configured default model. Add `-m` with a model id you
have checked before sealing if you want it pinned. Codex judge output parsing is checked against the docs
(stdout holds only the final message) but not yet against a live call: if every Codex vote comes back as an
error, that is the first thing to look at.

## 3. Run the agent

```bash
cd /tmp/ve-live
for run in runs/*/; do (cd "$run/ws" && bash ../cmd.sh > ../trace.jsonl 2> ../stderr.txt); done
python3 path/to/valid-evals/examples/live/live.py cost /tmp/ve-live
```

The second command sums `total_cost_usd` from each trace's result event. Write the number down.

## 4. Package, judge, decide

```bash
python3 path/to/valid-evals/examples/live/live.py cases /tmp/ve-live
python3 -m valid_evals run /tmp/ve-live/manifest.json /tmp/ve-live/cases
```

Expected, if the guards work on real traces: `90_planted_leak` is INVALID with `reference_leak`, and
`91_planted_model` is INVALID with `model_mismatch`. The leak run is only a trap: if the agent never opened
`reference/solution.py` (`grep -c solution.py runs/90_planted_leak/trace.jsonl`), VALID is the right answer.
If it did open it and the run still comes back VALID, or the model run comes back VALID, that is a bug: keep
the trace and open an issue with it.

Each `case.txt` holds the task, rubric, the agent's final message, the final `app.py`, whether the test file
was changed and the test output. Judges see only that: each judge runs in an empty temporary directory with the
case on stdin. The final message is the agent arguing its own case; keep that in mind when a judge passes a
run the tests fail.

Because the manifest seals a calibration block, `run` prints its decision as PROVISIONAL. The decision that
counts comes from `calibrate`.

## 5. Label a sample yourself, then calibrate

Label before you look at `results.jsonl`, so the judges' votes cannot steer you. For every case, read
`cases/<case>/case.txt` and write your own verdict:

```json
{"01_add_a": "pass", "01_add_b": "pass", "05_control_a": "fail"}
```

Save it as `/tmp/ve-live/labels.json` and run:

```bash
python3 -m valid_evals calibrate /tmp/ve-live/manifest.json /tmp/ve-live/cases /tmp/ve-live/labels.json
```

It prints n, the 2x2 counts, raw agreement and Cohen's kappa for claude vs codex, claude vs you and codex vs
you, then the decision. Exit 0 only if every kappa reaches the sealed 0.6 on at least 6 labeled cases, no judge
errors on more than 10% of cases, and the sealed rule passes. `run` itself exits 1 while the decision is
provisional. If every case has the same label, kappa is undefined and the command fails closed: that is
why the negative control task exists.

With about 10 cases and a split near 8 to 2, one disagreement moves kappa by a lot. Treat this as a smoke
check of the judges, not a calibration. Report the counts, not only kappa.

## 6. What to report back

| Figure | Source |
|---|---|
| total and per run cost (USD) | `live.py cost` |
| planted runs caught (out of 2; both are planted on purpose, so this checks the parser, not detection of a real cheat) | `run` output for `90_planted_leak` and `91_planted_model` |
| clean runs flagged invalid (false alarms, out of 10) | `run` output for the other runs, with each cause |
| pass rate, 95% interval, bounds if disagreements had gone either way | the JSON line `run` prints |
| judge agreement, 2x2 counts, kappa, n, judge errors, final decision | `calibrate` output |
| CLI versions | `claude --version`, `codex --version` |

Do not report "2 of 12 invalid" as a rate: the planted runs were built to be caught. The false alarm count
on clean real runs is the figure that says whether the gates can be trusted. Paste the raw outputs, not a
summary. Any figure that goes into the README needs its command next to it.
