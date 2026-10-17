"""Decide whether one agent run may count, from its `claude -p --output-format stream-json --verbose` or
`codex exec --json` trace. An unknown trace shape is a run_error. Pure Python, no model calls. One cause is reported by fixed priority; every finding is kept in details."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from valid_evals import codex

PRIORITY = ("run_error", "isolation_breach", "model_mismatch", "model_unverified", "reference_leak", "human_turn",
            "tool_not_allowed")
_DATED = re.compile(r"-\d{8}$")


@dataclass
class Validity:
    valid: bool
    cause: str | None
    details: dict = field(default_factory=dict)


def _events(text: str) -> tuple[list[dict], int]:
    """Parsed events and the number of lines that are not a JSON object. Unknown event types are fine; a line we
    cannot read could hide anything, so the caller treats it as a run error."""
    out, bad = [], 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(obj, dict):
            out.append(obj)
        else:
            bad += 1
    return out, bad


def strings(obj):
    """Every string value inside a parsed JSON value, decoded, so escapes cannot hide a match."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def norm_path(s: str) -> str:
    return s.casefold().replace("\\", "/")


# Claude Code tags messages it generates itself (errors, interrupts) with this marker, not a served model
SYNTHETIC = "<synthetic>"


def _model_ok(model, allowed: list[str]) -> bool:
    """An allowed alias matches its dated snapshots; an allowed dated id matches only itself."""
    if not isinstance(model, str):
        return False
    return any(model == a or (not _DATED.search(a) and _DATED.sub("", model) == a) for a in allowed)


# text the agent writes or explains, not a location it reads: a path mentioned here is not a read
PROSE_KEYS = frozenset({"content", "new_string", "old_string", "description", "prompt", "activeForm", "query"})
_BEFORE = r"(?:^|(?<=[\s/\"'=:(<>|;&,`{]))"
_AFTER = r"(?=/|$|[\s\"'):;|&>,`}])"


def _tool_strings(obj):
    """Decoded strings of a tool input, skipping prose fields."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k not in PROSE_KEYS:
                yield from _tool_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _tool_strings(v)


def reference_paths(tool_input, manifest: dict, add) -> None:
    """A tool call that names a sealed reference path is a leak, whatever it did with the content. The fragment
    must appear as whole path segments (case folded, backslashes read as slashes) in a field that is not prose,
    so `cross-reference` or `preferences/` do not match."""
    texts = [norm_path(s) for s in _tool_strings(tool_input)]
    for path in manifest.get("reference_paths", []):
        pattern = re.compile(_BEFORE + re.escape(norm_path(path).strip("/")) + _AFTER, re.M)
        if any(pattern.search(t) for t in texts):
            add("reference_leak", {"path": path})


def _builtin(plugin) -> bool:
    # plugins shipped inside the CLI are listed even under --bare (seen in 2.1.301); host plugins are not
    return isinstance(plugin, dict) and plugin.get("path") == "builtin" \
        and str(plugin.get("source", "")).endswith("@builtin")


def _content(ev: dict):
    msg = ev.get("message")
    return msg.get("content") if isinstance(msg, dict) else None


def _is_human(ev: dict) -> bool:
    """Main thread user content that is not a tool result: text, images, anything a person could send."""
    content = _content(ev)
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(not (isinstance(b, dict) and b.get("type") == "tool_result") for b in content)
    return content is not None


def check(text: str, manifest: dict) -> Validity:
    events, bad = _events(text)
    found: dict[str, list] = {}

    def add(cause, info):
        if info not in found.setdefault(cause, []):
            found[cause].append(info)

    if bad:
        add("run_error", f"{bad} lines are not JSON objects")
    decoded = [s for e in events for s in strings(e)]
    for canary in manifest.get("canaries", []):
        if canary in text or any(canary in s for s in decoded):
            add("reference_leak", canary)

    is_claude = any(e.get("type") == "system" and e.get("subtype") == "init" for e in events)
    try:
        if is_claude and codex.is_codex(events):
            add("run_error", "trace mixes Claude and Codex events")
        elif codex.is_codex(events):
            codex.findings(events, manifest, add)
        else:
            _claude_findings(events, manifest, add)
    except (AttributeError, TypeError, ValueError) as e:  # a field we use has the wrong type
        add("run_error", f"malformed trace: {type(e).__name__}")
    cause = next((c for c in PRIORITY if c in found), None)
    return Validity(valid=cause is None, cause=cause, details=found)


def _claude_findings(events: list[dict], manifest: dict, add) -> None:
    inits = [e for e in events if e.get("type") == "system" and e.get("subtype") == "init"]
    results = [i for i, e in enumerate(events) if e.get("type") == "result"]
    agent = [i for i, e in enumerate(events) if e.get("type") in ("assistant", "user")]
    if len(inits) != 1:
        add("run_error", f"{len(inits)} init events")
    elif agent and events.index(inits[0]) > agent[0]:
        add("run_error", "init after agent events")
    if len(results) != 1:
        add("run_error", f"{len(results)} result events")
    else:
        r = events[results[0]]
        if r.get("subtype") != "success" or r.get("is_error") is not False:
            # an API error can end with subtype "success"; terminal_reason names it when present
            add("run_error", r.get("terminal_reason") or r.get("subtype") or "is_error")
        if agent and agent[-1] > results[0]:
            add("run_error", "agent events after the result")
        denials = r.get("permission_denials")
        for d in denials if isinstance(denials, list) else []:  # reported, not a cause: the runner's own setting
            if isinstance(d, dict):  # the tool_use_id keeps two identical denials apart
                add("permission_denied", f"{d.get('tool_use_id')} {d.get('tool_name')}: "
                                         f"{json.dumps(d.get('tool_input'), sort_keys=True)}")

    allowed_models = manifest["allowed_models"]
    if inits:
        init = inits[0]
        plugins = [p for p in init.get("plugins") or [] if not _builtin(p)]
        if manifest.get("require_bare") and (init.get("mcp_servers") or plugins):
            add("isolation_breach", {"mcp_servers": init.get("mcp_servers"), "plugins": plugins})
        if init.get("model") == SYNTHETIC:
            add("model_unverified", {"init": SYNTHETIC})
        elif not _model_ok(init.get("model"), allowed_models):
            add("model_mismatch", {"init": init.get("model")})

    served = False
    # claude -p does not echo the prompt; when a runner does, it comes before the first assistant message
    prompt_slot = True
    tool_ids = set()  # a subagent event names a tool_use seen earlier; any other parent id hides nothing
    denied = {d.get("tool_use_id") for e in events if e.get("type") == "result"
              for d in (e.get("permission_denials") if isinstance(e.get("permission_denials"), list) else [])
              if isinstance(d, dict)}  # a denied call never ran, so it used no tool
    for ev in events:
        if ev.get("type") == "assistant":
            prompt_slot = False
            msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
            msg_model = msg.get("model")
            if msg_model and msg_model != SYNTHETIC:
                served = True
                if not _model_ok(msg_model, allowed_models):
                    add("model_mismatch", {"message": msg_model})
            for block in _content(ev) or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_ids.add(block.get("id"))
                    if block.get("name") not in manifest["allowed_tools"] and block.get("id") not in denied:
                        add("tool_not_allowed", block.get("name"))
                    inp = block.get("input")
                    if block.get("name") == "Grep" and isinstance(inp, dict):
                        inp = {k: v for k, v in inp.items() if k != "pattern"}  # a regex over contents, not a path
                    reference_paths(inp, manifest, add)
        elif ev.get("type") == "user" and ev.get("parent_tool_use_id") not in tool_ids and _is_human(ev):
            if prompt_slot:
                prompt_slot = False
            else:
                add("human_turn", "user turn after the first prompt")
    if not served:
        add("model_unverified", "no assistant message names a served model")
