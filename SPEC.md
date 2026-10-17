# valid-evals SPEC v0.4.0

## Goal
An agent eval can pass for the wrong reasons: the run used another model, read the answer key, got help from a
human, or the pass bar moved after the results came in. valid-evals is a small layer that sits after any runner
and answers one question before a score counts: was the run valid, and was the rule fixed before we looked?

Success: a reviewer can clone the repo, run one command, and see an invalid run rejected with exactly one cause,
a disagreement between two judges routed to a human, and a decision that fails closed when the rule was edited.

## Non goals
Not a runner (promptfoo, caliper, Harbor exist). No UI. No graph framework. No API client: judges are commands.

## Modules
1. `seal`: canonical JSON of the manifest, then sha256. `seal` writes `manifest.lock`. Every later step verifies
   the hash and stops on mismatch. The manifest holds: metric, comparator, threshold, min_valid_cases, the two
   outcome sentences, max_excluded_fraction, allowed_models, allowed_tools, canaries, require_bare, and the judges; optionally
   reference_paths, trust_runner_model and a calibration block. Types and bounds are checked at seal; duplicate
   keys, NaN and Infinity are refused.
2. `validity`: reads a `claude -p --output-format stream-json --verbose` trace or a `codex exec --json` trace
   (`codex.py`), told apart by shape; any other shape is a run_error. It returns VALID, or INVALID with exactly one
   cause, picked by a fixed priority:
   run_error > isolation_breach > model_mismatch > model_unverified > reference_leak > human_turn > tool_not_allowed.
   All findings stay in `details`. Codex traces name no model, so they are model_unverified unless the sealed
   manifest sets `trust_runner_model: true`. Codex tools are named by item type (`command_execution`,
   `file_change`, `web_search`, `mcp:<server>/<tool>`).
3. `jury`: two judge commands from two different vendors. Each reads the case on stdin and prints
   `{"verdict": "pass"|"fail"}`. Both pass gives PASS; both fail gives FAIL; any other result gives DISAGREE,
   which goes to a queue for a human. Anything that does not parse is JUDGE_ERROR and does not count.
4. `decide`: verifies the seal, keeps only cases that are VALID and agreed, refuses when the share of runs left
   out exceeds max_excluded_fraction, checks min_valid_cases, applies the comparator, and prints the pre-written
   sentence. A broken seal, too few valid cases, too many runs left out, or a bad input exits non-zero (fail
   closed).
5. `calibrate`: reads the votes `run` wrote to `results.jsonl` and a human label file `{"case": "pass"|"fail"}`.
   Reports n, 2x2 counts, raw agreement and Cohen's kappa for judge vs judge and each judge vs the people, plus
   each judge's error rate, then the decision. Passes only if every kappa meets the sealed
   `calibration.min_kappa` and every judge error rate is at most `calibration.max_judge_error_rate`; fewer than
   `calibration.min_labels` labeled cases, a missing calibration block, a bad label or an undefined kappa (one
   label only) fail closed. With a sealed calibration block, `run` is provisional and never exits 0; the final
   decision is `calibrate`'s (exit 0 only when calibrated and the rule passes).

## Determinism
Validity is pure Python over the trace, with no model calls. Canaries are fixed strings placed inside the
reference files; the run is INVALID if any canary appears anywhere in the trace.

## Failure modes covered
| # | Failure | Guard |
|---|---|---|
| 1 | Pass bar edited after results | seal hash check, fail closed |
| 2 | Run silently used another model | init and per message model vs allowed_models |
| 3 | Agent read the reference answer | canary scan over the whole trace |
| 4 | A human steered the run | user text turn after the first prompt in the main thread |
| 5 | Host hooks, MCP or plugins changed the run | require_bare: init mcp_servers and plugins must be empty |
| 6 | Run crashed or hit the budget, still scored | result missing or is_error counts as run_error |
| 7 | One judge's bias | two vendors that must agree; vendors must differ at seal time |
| 8 | Judge output drift or garbage | strict JSON parse, JUDGE_ERROR excluded and counted |
| 9 | Tiny sample passes by luck | min_valid_cases |
| 10 | stream-json format changes | parser tolerant to unknown events, strict on the fields it uses; redacted real traces pin the format (tests/fixtures) |
| 11 | Runner cannot prove the model (Codex) | model_unverified, unless the sealed rule says to trust the runner |
| 12 | A prompt added mid run (Codex resume) | more than one turn.started is a human_turn |
| 13 | Judges agree with each other but not with people | calibrate: sealed min kappa against a human sample |
| 14 | Agent read the reference but encoded it (canary hidden) | sealed reference_paths: a tool call naming one is a leak |
| 15 | Only synthetic messages, no served model | model_unverified |
| 16 | A trace edited or padded to look clean (two results, two inits, mixed shapes, events after the result) | run_error |
| 17 | Manifest with duplicate keys, NaN, wrong types, or values that switch a gate off | refused at seal and verify |
| 18 | A judge sees more than the case, or prose after its JSON | empty cwd; whole output or last line only |
| 19 | Calibration passes while judges mostly error | sealed max_judge_error_rate |
| 20 | Split cases decide the outcome unseen | Wilson interval and bounds printed with every decision |
| 21 | The code that applies the rule changed between run and calibrate | code_sha256 in every row; calibrate refuses a mismatch |
| 22 | Runs that crash, run out of turns or split the jury are dropped, so hard tasks vanish and the rate rises | sealed max_excluded_fraction; above it the decision is refused |
| 23 | The runner denied the agent's test command, so it never checked its work | denials reported in details and next to the run; not a cause, the allowlist is the author's setting |
| 24 | The rule is sealed after looking at the runs, or sealed again after deleting the lock | the lock records sealed_at; run and calibrate refuse a trace event older than it (local clocks, Claude traces only) |

## DoD
Unit tests for every guard (a RED test first), one command demo on fixtures, README figures only from real runs
(marked pending until Sebas runs the live demo), stdlib only, MIT, no employer material.
