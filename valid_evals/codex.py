"""Findings for a `codex exec --json` trace. Event and item types follow the Codex TypeScript SDK
(sdk/typescript/src/events.ts and items.ts, which mirror codex-rs/exec/src/exec_events.rs).

The stream names no model, so the model cannot be checked from the trace: it is reported as model_unverified
unless the sealed manifest sets trust_runner_model. Tools are named by item type (command_execution,
file_change, web_search); MCP calls are named mcp:<server>/<tool>."""

from __future__ import annotations

import json

NOT_TOOLS = ("agent_message", "reasoning", "todo_list", "error")


def is_codex(events: list[dict]) -> bool:
    return any(e.get("type") == "thread.started" for e in events)


CLAUDE_TYPES = ("system", "assistant", "user", "result")


def findings(events: list[dict], manifest: dict, add) -> None:
    from valid_evals import validity  # validity imports this module; a top level import would be circular
    if any(e.get("type") in CLAUDE_TYPES for e in events):
        add("run_error", "Claude events inside a Codex trace")
    turns = [e.get("type") for e in events if e.get("type") in ("turn.started", "turn.completed", "turn.failed")]
    if turns[0::2] != ["turn.started"] * len(turns[0::2]) or any(t == "turn.started" for t in turns[1::2]):
        add("run_error", "turn events out of order")
    if "turn.failed" in turns:
        failed = next(e for e in events if e.get("type") == "turn.failed")
        add("run_error", (failed.get("error") or {}).get("message", "turn.failed"))
    elif not turns or turns[-1] != "turn.completed":
        add("run_error", "no turn.completed after the last turn.started")

    if manifest.get("trust_runner_model") is not True:
        add("model_unverified", "codex exec --json names no model")

    if turns.count("turn.started") > 1:
        add("human_turn", f"{turns.count('turn.started')} turns: a prompt was added after the first")

    for ev in events:  # a tool counts as soon as it is started, whatever happens to it later
        it = ev.get("item")
        if ev.get("type") not in ("item.started", "item.updated", "item.completed") or not isinstance(it, dict):
            continue
        kind = it.get("type")
        if kind in NOT_TOOLS:
            continue
        name = f"mcp:{it.get('server')}/{it.get('tool')}" if kind == "mcp_tool_call" else kind
        named = {"command_execution": it.get("command"), "file_change": it.get("changes"),
                 "mcp_tool_call": it.get("arguments"), "web_search": it.get("query")}.get(kind)
        validity.reference_paths(named, manifest, add)
        if kind == "mcp_tool_call" and manifest.get("require_bare"):
            add("isolation_breach", {"mcp_tool_call": name})
        if name not in manifest["allowed_tools"]:
            add("tool_not_allowed", name)
