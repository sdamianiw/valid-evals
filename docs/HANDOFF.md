# Handoff

Checkpoint for the next working session. Update it at the end of each session; keep it short.

## Why this exists

An agent eval score can be wrong for reasons the score cannot show: another model ran, the agent read the answer
key, a person helped, the bar moved after the results. valid-evals answers one question before a score counts:
was the run valid, and was the rule fixed before anyone looked? It judges runs other tools produce; it is not a
runner. The prior art audit (2026 10 16, by the author) found runners, tracing and judges covered elsewhere, and
no tool combining a sealed rule, a run invalidity gate and a cross vendor jury that must agree.

It does not measure code quality over time. Degradation across many agent sessions is a different question; see
Open decisions.

## State (2026 10 17)

- v0.4.0 on `main`. The sealed `max_excluded_fraction` (required) refuses a decision when too many runs are left
  out; denied tool calls are reported per run. CI on 3.10 to 3.13. `valid_evals.__version__` is the version of record.
- Modules: seal, validity (Claude stream-json and Codex `exec --json`), jury, decide, calibrate, cli.
- Docs: README (short), docs/REFERENCE.md, docs/LIVE_DEMO.md, docs/PREMORTEM_v0.2.md, docs/REDTEAM_v0.3.md.
- Real traces pin the formats: tests/fixtures (Claude Code 2.1.301, Codex CLI 0.163.0).
- Live result: 12 real runs, 0 of 10 clean runs flagged, 2 of 2 planted runs caught, 0.0418 USD. Judges never run
  live.

## Verified facts about the CLIs (2.1.301 and 0.163.0)

- `--bare` reads only `ANTHROPIC_API_KEY`; without it, `authentication_failed`.
- `--restricted --strict-mcp-config` works with a subscription login and did not load a CLAUDE.md (0 of 2 vs 2 of
  2 for a normal run). The init event does not show which mode ran.
- Builtin plugins (`path: builtin`, source `@builtin`) are listed even under `--bare`.
- `claude -p` does not echo the prompt as a user event; subagent prompts carry `parent_tool_use_id`.
- `--tools Task` appears in the trace as tool `Agent`.
- `error_max_turns` arrives with `is_error: true`; API errors can arrive with `subtype: success, is_error: true`.
- `claude -p --output-format json --json-schema` puts the verdict in `structured_output`, one line, stdin appended.
- `codex exec --json` names no model; stdout without `--json` holds only the final message (docs).
- Codex is listed for the free ChatGPT plan, but CLI access on it is unconfirmed; API keys bill at API rates.

## Waiting on the author

1. Run the jury part of docs/LIVE_DEMO.md on his machine: Claude with his subscription login (default
   `--isolation restricted`), Codex via `codex login` first, else `CODEX_API_KEY`; pick a cheap Codex model with
   `--codex-model`.
2. Label `labels.json` himself before looking at votes.
3. Add GitHub topics: evals, llm-evaluation, ai-agents, claude-code, codex, llm-as-judge, pre-registration.

## Roadmap (agreed 2026 10 17, cap two weeks)

| Step | What | Who | State |
|---|---|---|---|
| 1 | Exclusions cannot lift the score: sealed `max_excluded_fraction`, refuse above it | agent | done, v0.4.0 |
| 2 | README leads with the denied tests finding; limits of seal, planted runs, calibration power | agent | done, v0.4.0 |
| 3 | Run the jury live (Max login plus Codex), label blind | author | waiting |
| 4 | Mutation corpus: per cause recall and false alarms, pinned by a test | agent | done: 3 bugs fixed, table in README |
| 5 | Per run footprint (files changed, test file touched) in details | agent | later, after 4 |

Out of scope for now: a `drift` metric over snapshots, an external timestamp for the lock, more Codex work.
Decisions taken by default with the author's OK: exclusion limit refuses (option a); denied calls are reported,
not a cause.

## Round 3 review (2026 10 17): framing red team and advisor, audited

Reproduced here:

1. Exclusions inflate the score. `decide` drops INVALID, DISAGREE and JUDGE_ERROR rows from the denominator, so 3
   PASS plus 7 runs that hit max turns gives value 1.0 and ok. This breaks fail closed. Fix options: refuse when
   exclusions exceed a sealed fraction, or count run_error and JUDGE_ERROR as FAIL. Owner picks.
2. 6 of 10 clean live runs had their test command denied and are VALID; the README does not say so.
3. The seal binds the manifest, not time, the case list or reruns. Sealing after looking, resealing, or deleting a
   case folder all go through. Today this is a documented limit, not a guard.
4. Calibration on 6 balanced labels at min_kappa 0.6: an 80% accurate judge passes about 66% of draws, a 90% one
   about 89% (20k draws). It is a smoke check, not a calibration.
5. The planted runs were built to be caught; 2 of 2 proves the parser reads the init event and a path.

Exact calibration power, pinned in tests/test_v04.py: with 3 pass and 3 fail labels and min_kappa 0.6, a judge
right 60%, 80% or 90% of the time passes with probability 0.233, 0.655 or 0.886.

## Lessons

- A mutation corpus over real traces found three bugs that three review rounds missed (brace expansion, a made
  up parent id hiding a human turn, Grep pattern read as a path). Measure the checker before hardening it more.
- A synthetic test can encode the bug: the old subagent test used a parent id that named no tool_use. Shape
  synthetic events after a real fixture.

- A fix for recall needs a false alarm test in the same commit. The round 2 path fix flagged `cross-reference`.
- Never trust an intermediate file the user can edit: `calibrate` re-checks traces, hashes, votes and code.
- Placeholders in generated docs must be unique strings; `DEMO` also matched `LIVE_DEMO.md`.
- Anything sealed that holds a machine path (judge commands) changes the hash per machine; tests mask hashes.
- When a fixture helper changes (a default assistant message), re-check every test that relied on its absence.
- Predict, run, compare matched every time it was used here; keep doing it before each fix.
- Independent agents found what self review missed every round: red team twice, an adversarial reader, an
  advisor before done. Audit each finding against the code before acting; two of their premises were stale.
