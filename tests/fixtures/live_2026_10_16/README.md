# Live validity run, 2026 10 16

Twelve real agent runs prepared with `examples/live/live.py prepare --model claude-haiku-5-5 --other-model
claude-sonnet-5-5`, run with Claude Code 2.1.301 in a cloud container. Two differences from `docs/LIVE_DEMO.md`:
the runs used Haiku, and `--bare` was removed from each `cmd.sh` because bare mode cannot authenticate in that
container (it reads only `ANTHROPIC_API_KEY`). The init events still list only the CLI's builtin plugins and no
MCP server. No judge was run: these traces measure the validity step only.

Redacted like the other fixtures: paths, session ids, account rate limit events and most init fields removed.
The canary was generated for this run and is published here on purpose.

| Figure | Value | Test |
|---|---|---|
| clean runs flagged invalid | 0 of 10 | `test_no_false_alarm_on_the_ten_clean_runs` |
| planted runs caught, right cause | 2 of 2 (`reference_leak` with canary and path, `model_mismatch`) | `test_both_planted_runs_caught_with_the_right_cause` |
| agent cost, 12 runs | 0.0418 USD total, 0.024 USD the most expensive run | `test_agent_cost` |

All 12 final `app.py` files passed the original tests in a clean folder, including both planted runs: a score
taken from tests alone would have counted the run that read the answer key and the run on the wrong model.
