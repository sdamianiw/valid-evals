# Real trace fixtures

Captured on 2026 10 16 with Claude Code 2.1.301, `claude [--bare] -p ... --output-format stream-json --verbose`,
then redacted: host paths become `/work`, session ids become `redacted`, the init event keeps only the fields
valid-evals reads plus a few for context, the tool list is trimmed, and account rate limit events are removed.
Event order, types and the fields validity uses are untouched.

| File | Run | What it pins |
|---|---|---|
| `claude_2_1_301_bare_auth_error.jsonl` | `--bare`, no API key | `<synthetic>` model on an API error message; `result` with `subtype: success` and `is_error: true`; builtin plugins listed even in bare mode |
| `claude_2_1_301_read_canary.jsonl` | Haiku, `--allowedTools Read`, reads a file holding a canary | the prompt is not echoed as a `user` event; tool results arrive as main thread `user` events with `parent_tool_use_id: null`; unknown event types (`active_goal`, `autocompact_state`, system `task_summary`) and a system event after `result` |
| `claude_2_1_301_max_turns.jsonl` | Haiku, `--tools Read,Edit --max-turns 1` | `result` with `subtype: error_max_turns`, `is_error: true`, `terminal_reason: max_turns` |
| `claude_2_1_301_judge_json_schema.json` | judge call: case on stdin, `claude -p PROMPT --model claude-haiku-5-5 --tools "" --output-format json --json-schema '{verdict: pass or fail}'` | one line JSON; stdin is read with the prompt; `structured_output: {"verdict": "pass"}`; `total_cost_usd: 0.0010066` |
| `claude_2_1_301_subagent.jsonl` | Haiku, `--tools Task,Read`, one subagent | the subagent prompt is a `user` text event with `parent_tool_use_id` set (not a human turn); subagent messages carry their own model; the tool is named `Agent` in `tool_use` although the flag says `Task`; a `thinking` block |
| `claude_2_1_301_restricted.jsonl` | Haiku, `--restricted --strict-mcp-config --tools ""`, subscription login, no API key | authenticates where `--bare` did not; init lists only builtin plugins and no MCP server, and nothing marks the mode. Same day check: with a CLAUDE.md asking to end each answer with a fixed word, normal runs obeyed 2 of 2, restricted runs 0 of 2 |
| `codex_0_163_0_auth_error.jsonl` | `codex exec --json --ephemeral -s read-only`, no credentials (Codex CLI 0.163.0) | `thread.started`, `turn.started`, top level `error` events for retries, an `error` item, then `turn.failed`; no event names the model |

Successful Codex traces in the tests are synthetic, built from the event and item types in the Codex TypeScript
SDK (`sdk/typescript/src/events.ts` and `items.ts` in github.com/openai/codex, read 2026 10 16), which mirror
`codex-rs/exec/src/exec_events.rs`, and from the sample lines in the official non interactive mode docs.
