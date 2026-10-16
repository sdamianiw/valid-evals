# Real trace fixtures

Captured on 2026 10 16 with Claude Code 2.1.301, `claude [--bare] -p ... --output-format stream-json --verbose`,
then redacted: host paths become `/work`, session ids become `redacted`, the init event keeps only the fields
valid-evals reads plus a few for context, the tool list is trimmed, and account rate limit events are removed.
Event order, types and the fields validity uses are untouched.

| File | Run | What it pins |
|---|---|---|
| `claude_2_1_301_bare_auth_error.jsonl` | `--bare`, no API key | `<synthetic>` model on an API error message; `result` with `subtype: success` and `is_error: true`; builtin plugins listed even in bare mode |
| `claude_2_1_301_read_canary.jsonl` | Haiku, `--allowedTools Read`, reads a file holding a canary | the prompt is not echoed as a `user` event; tool results arrive as main thread `user` events with `parent_tool_use_id: null`; unknown event types (`active_goal`, `autocompact_state`, system `task_summary`) and a system event after `result` |
