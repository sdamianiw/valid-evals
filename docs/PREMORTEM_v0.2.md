# Premortem, v0.2 (2026 10 16)

Assume it is three months from now and v0.2 let a bad eval through or blocked good ones. The likely reasons,
ordered by how much damage they would do before anyone noticed.

| # | How it failed | Today | Mitigation or open item |
|---|---|---|---|
| 1 | A user set `trust_runner_model: true` for Codex out of habit, and a silent model switch went unseen | Codex `--json` names no model; we can only refuse or trust | Open: read the model from the Codex session rollout file once its format is checked against a real run. The flag is sealed, so the trust is at least visible in review |
| 2 | Judges agreed with each other, the decision passed, and nobody had run `calibrate` | `run` does not require a calibration report | Open: let `decide` require a passing calibration report bound to the same manifest hash |
| 3 | `calibrate` passed on 6 labels by luck | the sealed minimum is set by the user; the live demo uses 6 | n is always printed next to kappa. Six is a smoke threshold, not evidence about a judge |
| 4 | `results.jsonl` votes were edited before `calibrate` read them | votes are not hashed | Open: print a hash of `results.jsonl` in the `run` output and check it in `calibrate` |
| 5 | A new Claude Code version renamed the builtin plugin marker, and every run became `isolation_breach` | fails closed and loud, so it blocks rather than leaks | Re run the smoke step of the live demo after each CLI upgrade; add the trace as a fixture |
| 6 | A host plugin was configured to look builtin (`path: builtin`, source ending in `@builtin`) | we trust those two fields | Low likelihood; it needs a deliberately forged config. Listed under what it does not catch |
| 7 | Claude Code injected its own user text after an assistant turn (hooks, skills), and clean runs read as `human_turn` | not seen in bare mode in our captures | Fails closed. Keep `require_bare`; add a fixture if it shows up |
| 8 | The agent read the reference through a transform (`base64`, partial `sed`), so the canary never appeared | known gap since v0.1 | Keep references out of the workspace; the canary is a tripwire, not a wall |
| 9 | Codex runs pulled in `AGENTS.md`, user config or hooks and nothing flagged it | only MCP tool calls that actually happen are seen | Run Codex with `--ignore-user-config` and a clean workspace; there is no `--bare` equivalent we could verify |
| 10 | The Codex judge returned prose and every vote was `JUDGE_ERROR` | parse checked against the docs, not a live call | Fails closed (no vote counts). First live run settles it |
| 11 | Two runs of the same task were treated as independent evidence | the live demo repeats each task twice | Read the pass rate per task too; the decision rule does not model correlation |
