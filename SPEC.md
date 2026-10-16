# valid-evals SPEC v0.1

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
   outcome sentences, allowed_models, allowed_tools, canaries, require_bare, and the judges.
2. `validity`: reads a `claude -p --output-format stream-json --verbose` trace. It returns VALID, or INVALID with
   exactly one cause, picked by a fixed priority:
   run_error > isolation_breach > model_mismatch > reference_leak > human_turn > tool_not_allowed.
   All findings stay in `details`.
3. `jury`: two judge commands from two different vendors. Each reads the case on stdin and prints
   `{"verdict": "pass"|"fail"}`. Both pass gives PASS; both fail gives FAIL; any other result gives DISAGREE,
   which goes to a queue for a human. Anything that does not parse is JUDGE_ERROR and does not count.
4. `decide`: verifies the seal, keeps only cases that are VALID and agreed, checks min_valid_cases, applies the
   comparator, and prints the pre-written sentence. A broken seal, too few valid cases, or a bad input exits
   non-zero (fail closed).

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
| 10 | stream-json format changes | parser tolerant to unknown events, strict on the fields it uses; fixtures pin the format |

## DoD
Unit tests for every guard (a RED test first), one command demo on fixtures, README figures only from real runs
(marked pending until Sebas runs the live demo), stdlib only, MIT, no employer material.
