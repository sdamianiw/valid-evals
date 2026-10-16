"""Decide whether one agent run may count, from its `claude -p --output-format stream-json --verbose` trace.
Pure Python, no model calls. One cause is reported by fixed priority; every finding is kept in details."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

PRIORITY = ("run_error", "isolation_breach", "model_mismatch", "reference_leak", "human_turn", "tool_not_allowed")
_DATED = re.compile(r"-\d{8}$")


@dataclass
class Validity:
    valid: bool
    cause: str | None
    details: dict = field(default_factory=dict)


def _events(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue  # tolerate partial lines; the fields we need are checked below
        if isinstance(obj, dict):
            out.append(obj)
    return out


# Claude Code tags messages it generates itself (errors, interrupts) with this marker, not a served model
SYNTHETIC = "<synthetic>"


def _model_ok(model: str, allowed: list[str]) -> bool:
    return model == SYNTHETIC or _DATED.sub("", model or "") in allowed


def _content(ev: dict):
    return (ev.get("message") or {}).get("content")


def _is_human_text(ev: dict) -> bool:
    content = _content(ev)
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(isinstance(b, dict) and b.get("type") == "text" for b in content)
    return False


def check(text: str, manifest: dict) -> Validity:
    events = _events(text)
    found: dict[str, list] = {}

    def add(cause, info):
        found.setdefault(cause, []).append(info)

    results = [e for e in events if e.get("type") == "result"]
    if not results:
        add("run_error", "no result event")
    elif results[-1].get("is_error"):
        add("run_error", results[-1].get("subtype", "is_error"))

    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), None)
    allowed_models = manifest["allowed_models"]
    if init is None:
        add("run_error", "no init event")
    else:
        if manifest.get("require_bare") and (init.get("mcp_servers") or init.get("plugins")):
            add("isolation_breach", {"mcp_servers": init.get("mcp_servers"), "plugins": init.get("plugins")})
        if not _model_ok(init.get("model", ""), allowed_models):
            add("model_mismatch", {"init": init.get("model")})

    for canary in manifest.get("canaries", []):
        if canary and canary in text:
            add("reference_leak", canary)

    first_main_user = True
    for ev in events:
        if ev.get("type") == "assistant":
            msg_model = (ev.get("message") or {}).get("model")
            if msg_model and not _model_ok(msg_model, allowed_models):
                add("model_mismatch", {"message": msg_model})
            for block in _content(ev) or []:
                if isinstance(block, dict) and block.get("type") == "tool_use" \
                        and block.get("name") not in manifest["allowed_tools"]:
                    add("tool_not_allowed", block.get("name"))
        elif ev.get("type") == "user" and ev.get("parent_tool_use_id") is None and _is_human_text(ev):
            if first_main_user:
                first_main_user = False
            else:
                add("human_turn", "user text turn after the first prompt")

    cause = next((c for c in PRIORITY if c in found), None)
    return Validity(valid=cause is None, cause=cause, details=found)
