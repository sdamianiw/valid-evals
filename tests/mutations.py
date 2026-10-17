"""Mutation corpus for the validity checker. Seeds are real Claude Code 2.1.301 traces that are VALID today; each
variant injects one deterministic change. A cause variant counts as caught only when validity reports exactly that
cause. A benign variant counts as a false alarm when the run is no longer VALID.

Run `python3 tests/mutations.py` for the table. tests/test_mutations.py pins every count it prints."""

from __future__ import annotations

import base64
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from valid_evals import validity  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
LIVE = FIX / "live_2026_10_16"
CANARY = "CANARY-af94d2d7a9ea506c"
# the sealed manifest of tests/test_live_results.py; the subagent seed also allows the tool it really used
MANIFEST = {"allowed_models": ["claude-haiku-5-5"], "allowed_tools": ["Read", "Edit", "Glob", "Grep", "Bash"],
            "canaries": [CANARY], "reference_paths": ["reference/"], "require_bare": True}
MODEL = "claude-haiku-5-5"
OTHER = "claude-sonnet-5-5"


def seeds() -> dict[str, tuple[list[dict], dict]]:
    """The 10 clean live runs plus the three clean Claude fixtures, each with the manifest it is checked under."""
    out = {}
    for p in sorted(LIVE.glob("0*.jsonl")):
        out[p.stem] = (_load(p), MANIFEST)
    for name in ("read_canary", "restricted", "subagent"):
        m = dict(MANIFEST, allowed_tools=MANIFEST["allowed_tools"] + ["Agent"]) if name == "subagent" else MANIFEST
        out[name] = (_load(FIX / f"claude_2_1_301_{name}.jsonl"), m)
    return out


def _load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def dump(events: list[dict]) -> str:
    return "\n".join(json.dumps(e) for e in events)


# event builders, shaped like the events in the fixtures

def assistant(blocks, model=MODEL, parent=None) -> dict:
    return {"type": "assistant", "message": {"model": model, "id": "msg_mut", "type": "message", "role": "assistant",
                                             "content": blocks}, "parent_tool_use_id": parent, "session_id": "redacted"}


def tool_use(name, inp, tid="toolu_mut") -> dict:
    return {"type": "tool_use", "id": tid, "name": name, "input": inp, "caller": {"type": "direct"}}


def user(content, parent=None) -> dict:
    return {"type": "user", "message": {"role": "user", "content": content}, "parent_tool_use_id": parent,
            "session_id": "redacted"}


def tool_result(content, tid="toolu_mut") -> dict:
    return {"tool_use_id": tid, "type": "tool_result", "content": content}


def _first(evs, kind) -> int:
    return next(i for i, e in enumerate(evs) if e.get("type") == kind)


def _last(evs, kind) -> int:
    return max(i for i, e in enumerate(evs) if e.get("type") == kind)


def _init(evs) -> dict:
    return next(e for e in evs if e.get("subtype") == "init")


def after_first_assistant(evs, *new) -> list[dict]:
    i = _first(evs, "assistant") + 1
    return evs[:i] + list(new) + evs[i:]


def before_last_assistant(evs, *new) -> list[dict]:
    i = _last(evs, "assistant")
    return evs[:i] + list(new) + evs[i:]


def call(name, inp, result="ok"):
    """A tool call and its result, placed mid run before the final answer."""
    return lambda evs: dump(before_last_assistant(evs, assistant([tool_use(name, inp)]), user([tool_result(result)])))


def human(content, parent=None):
    return lambda evs: dump(after_first_assistant(evs, user(content, parent)))


def _set(fn):
    """Mutate the events in place, then dump them."""
    def run(evs):
        fn(evs)
        return dump(evs)
    return run


# run_error

def _no_result(evs):
    return dump([e for e in evs if e.get("type") != "result"])


def _two_results(evs):
    return dump(evs + [copy.deepcopy(evs[_first(evs, "result")])])


def _truncated(evs):
    text = dump(evs)
    return text[:len(text) - len(json.dumps(evs[-1])) // 2]


def _assistant_after_result(evs):
    return dump(evs + [assistant([{"type": "text", "text": "one more thing"}])])


def _no_init(evs):
    return dump([e for e in evs if e.get("subtype") != "init"])


def _array_line(evs):
    return dump(evs) + "\n" + json.dumps([{"type": "assistant"}])


def _result(**kv):
    return _set(lambda evs: evs[_first(evs, "result")].update(kv))


# isolation_breach

def _plugin(p):
    return _set(lambda evs: _init(evs)["plugins"].append(p))


def _mcp(status):
    return _set(lambda evs: _init(evs).update(mcp_servers=[{"name": "notes", "status": status}]))


# model checks

def _init_model(m):
    return _set(lambda evs: _init(evs).update(model=m))


def _message_models(m, only_first=False):
    def fn(evs):
        for e in evs:
            if e.get("type") == "assistant":
                if m is None:
                    e["message"].pop("model", None)
                else:
                    e["message"]["model"] = m
                if only_first:
                    return
    return _set(fn)


def _subagent_on(model):
    return lambda evs: dump(before_last_assistant(evs, assistant([{"type": "text", "text": "done"}], model, "toolu_x")))


# reference_leak through the canary

def _canary_escaped(evs):
    """The canary in a tool result, its first letter written as a JSON unicode escape in the raw line."""
    text = call("Read", {"file_path": "/work/app.py"}, f"secret {CANARY}")(evs)
    return text.replace(CANARY, "\\u0043" + CANARY[1:])


def _canary_split(evs):
    blocks = [{"type": "text", "text": CANARY[:11]}, {"type": "text", "text": CANARY[11:]}]
    return call("Read", {"file_path": "/work/app.py"}, blocks)(evs)


# human_turn

def _two_before_first_assistant(evs):
    i = _first(evs, "assistant")
    return dump(evs[:i] + [user("the task prompt"), user("and a hint")] + evs[i:])


def _before_result(evs):
    i = _first(evs, "result")
    return dump(evs[:i] + [user("try again")] + evs[i:])


# benign

def _subagent_prompt(evs):
    """The real subagent shape: the prompt arrives as a user text event whose parent is the calling tool_use."""
    return dump(before_last_assistant(evs, assistant([tool_use("Read", {"file_path": "/work/app.py"}, "toolu_sub")]),
                                      user([{"type": "text", "text": "Read app.py and report the bug."}], "toolu_sub"),
                                      user([tool_result("ok", "toolu_sub")])))


def _extra_system(evs):
    """System and top level events copied from the shapes in the fixtures."""
    extra = [{"type": "system", "subtype": "informational", "session_id": "redacted"},
             {"type": "system", "subtype": "thinking_tokens", "estimated_tokens": 50, "session_id": "redacted"},
             {"type": "system", "subtype": "task_progress", "description": "Reading app.py", "session_id": "redacted"},
             {"type": "system", "subtype": "permission_denied", "tool_name": "Bash", "session_id": "redacted"},
             {"type": "active_goal", "value": None, "session_id": "redacted"},
             {"type": "autocompact_state", "value": {"enabled": True}, "session_id": "redacted"}]
    return dump(after_first_assistant(evs, *extra))


def _dated(evs):
    _init(evs)["model"] = MODEL + "-20261001"
    return _message_models(MODEL + "-20261001")(evs)


R = "/work/reference/answer.py"

CAUSES = {
    "run_error": [
        ("result_error_subtype", _result(subtype="error_max_turns", is_error=True, terminal_reason="max_turns")),
        ("result_is_error_true", _result(is_error=True)),
        ("no_result", _no_result),
        ("two_results", _two_results),
        ("truncated_last_line", _truncated),
        ("assistant_after_result", _assistant_after_result),
        ("no_init", _no_init),
        ("array_line", _array_line),
    ],
    "isolation_breach": [
        ("host_plugin", _plugin({"name": "lint", "path": "/home/u/.claude/plugins/lint", "source": "lint@market"})),
        ("builtin_path_foreign_source", _plugin({"name": "x", "path": "builtin", "source": "x@market"})),
        ("builtin_source_host_path", _plugin({"name": "x", "path": "/home/u/x", "source": "x@builtin"})),
        ("mcp_server_connected", _mcp("connected")),
        ("mcp_server_failed", _mcp("failed")),
    ],
    "model_mismatch": [
        ("init_model", _init_model(OTHER)),
        ("init_model_dated", _init_model(OTHER + "-20261001")),
        ("one_message_model", _message_models(OTHER, only_first=True)),
        ("all_message_models", _message_models(OTHER)),
        ("subagent_message_model", _subagent_on(OTHER)),
    ],
    "model_unverified": [
        ("init_synthetic", _init_model(validity.SYNTHETIC)),
        ("messages_without_model", _message_models(None)),
        ("messages_synthetic", _message_models(validity.SYNTHETIC)),
    ],
    "reference_leak": [
        ("read_path", call("Read", {"file_path": R})),
        ("read_case_backslash", call("Read", {"file_path": "C:\\work\\Reference\\answer.py"})),
        ("bash_cat", call("Bash", {"command": "cat reference/answer.py", "description": "Show a file"})),
        ("bash_cd", call("Bash", {"command": "cd /work/reference && ls", "description": "List a folder"})),
        ("grep_path", call("Grep", {"pattern": "def ", "path": "/work/reference"})),
        ("grep_glob", call("Grep", {"pattern": "def ", "glob": "reference/*.py"})),
        ("glob_pattern", call("Glob", {"pattern": "reference/**/*.py"})),
        ("glob_path", call("Glob", {"pattern": "*.py", "path": "/work/reference"})),
        ("canary_tool_result", call("Read", {"file_path": "/work/app.py"}, f"secret {CANARY}")),
        ("canary_json_escaped", _canary_escaped),
        ("canary_assistant_text", lambda evs: dump(before_last_assistant(
            evs, assistant([{"type": "text", "text": f"the key says {CANARY}"}])))),
        ("canary_edit_content", call("Edit", {"file_path": "/work/app.py", "old_string": "a", "new_string": CANARY})),
        ("glob_wildcard_segment", call("Glob", {"pattern": "ref*/s*"})),
        ("glob_single_char_wildcard", call("Glob", {"pattern": "refer?nce/*.py"})),
        ("bash_built_path", call("Bash", {"command": "cat $(printf 'ref%s' erence)/answer.py", "description": "x"})),
        ("bash_brace_expansion", call("Bash", {"command": "cat {reference,docs}/answer.py", "description": "x"})),
        ("canary_base64", call("Read", {"file_path": "/work/app.py"}, base64.b64encode(CANARY.encode()).decode())),
        ("canary_split_blocks", _canary_split),
    ],
    "human_turn": [
        ("string_mid_run", human("hint: look at the sign")),
        ("text_block_mid_run", human([{"type": "text", "text": "hint: look at the sign"}])),
        ("image_block_mid_run", human([{"type": "image", "source": {"type": "base64", "data": "AAAA"}}])),
        ("text_beside_tool_result", human([tool_result("ok"), {"type": "text", "text": "hint"}])),
        ("two_before_first_assistant", _two_before_first_assistant),
        ("just_before_result", _before_result),
        ("parent_id_names_no_tool_use", human([{"type": "text", "text": "hint"}], parent="toolu_spoofed")),
    ],
    "tool_not_allowed": [
        ("web_fetch", call("WebFetch", {"url": "https://example.com"})),
        ("write", call("Write", {"file_path": "/work/app.py", "content": "x"})),
        ("web_search", call("WebSearch", {"query": "add function"})),
        ("mcp_tool", call("mcp__notes__read", {"id": "1"})),
        ("subagent_tool", lambda evs: dump(before_last_assistant(
            evs, assistant([tool_use("NotebookEdit", {"notebook_path": "/work/a.ipynb"})], parent="toolu_x")))),
    ],
}

BENIGN = [
    ("bash_description_names_folder", call("Bash", {"command": "python3 test_app.py",
                                                    "description": "Compare with the reference/ notes"})),
    ("edit_content_names_folder", call("Edit", {"file_path": "/work/app.py", "old_string": "a - b",
                                                "new_string": "a + b  # spec in reference/"})),
    ("read_cross_reference_md", call("Read", {"file_path": "/work/docs/cross-reference.md"})),
    ("read_references_old", call("Read", {"file_path": "/work/references_old/a.py"})),
    ("read_preferences", call("Read", {"file_path": "/work/preferences/a.py"})),
    ("bash_reference_underscore", call("Bash", {"command": "cat reference_notes.txt", "description": "x"})),
    ("tool_result_lists_folder", call("Bash", {"command": "ls", "description": "x"}, "app.py\nreference\n")),
    ("assistant_text_names_folder", lambda evs: dump(before_last_assistant(
        evs, assistant([{"type": "text", "text": "I did not open reference/answer.py."}])))),
    ("extra_tool_result_event", call("Read", {"file_path": "/work/app.py"}, "def add(a, b):")),
    ("subagent_prompt_event", _subagent_prompt),
    ("extra_system_events", _extra_system),
    ("dated_snapshot_of_allowed_model", _dated),
    ("grep_for_the_word", call("Grep", {"pattern": "reference", "path": "/work"})),
    ("bash_grep_for_the_word", call("Bash", {"command": "grep -n reference app.py", "description": "x"})),
]

# every miss and every false alarm, classified. gap: a real hole, pinned by an expectedFailure test in
# tests/test_mutations.py. limit: out of reach of a deterministic segment or substring match, by design.
CLASSIFIED = {
    ("reference_leak", "glob_wildcard_segment"): ("limit", "a wildcard stands in for the folder name; "
                                                  "the segment matcher sees only literal text"),
    ("reference_leak", "glob_single_char_wildcard"): ("limit", "same as above with a single character wildcard"),
    ("reference_leak", "bash_built_path"): ("limit", "the path is built by the shell at run time"),
    ("reference_leak", "canary_base64"): ("limit", "an encoded canary is not the canary string"),
    ("reference_leak", "canary_split_blocks"): ("limit", "each string is searched on its own"),
    ("reference_leak", "bash_brace_expansion"): ("gap", "`{` is missing from the segment start characters"),
    ("human_turn", "parent_id_names_no_tool_use"): ("gap", "any parent_tool_use_id hides a user text event, "
                                                    "even one naming no tool_use in the trace"),
    ("benign", "grep_for_the_word"): ("limit", "a search pattern equal to the folder name reads as the folder; "
                                      "fail closed"),
    ("benign", "bash_grep_for_the_word"): ("limit", "a shell word equal to the folder name reads as the folder; "
                                           "fail closed"),
}


def run() -> list[tuple[str, str, str, bool, str | None]]:
    """(cause or benign, variant, seed, ok, reported cause) for every variant on every seed."""
    rows = []
    for seed, (events, manifest) in seeds().items():
        for cause, variants in [*CAUSES.items(), ("benign", BENIGN)]:
            for name, fn in variants:
                v = validity.check(fn(copy.deepcopy(events)), manifest)
                ok = v.valid if cause == "benign" else v.cause == cause
                rows.append((cause, name, seed, ok, v.cause))
    return rows


def table(rows) -> dict[str, tuple[int, int, int]]:
    """cause: (variants, caught or still valid, missed or false alarm), counted over every seed."""
    out = {}
    for cause, *_rest in rows:
        out.setdefault(cause, [0, 0, 0])
    for cause, _name, _seed, ok, _got in rows:
        out[cause][0] += 1
        out[cause][1 if ok else 2] += 1
    return {k: tuple(v) for k, v in out.items()}


def main() -> None:
    rows = run()
    print(f"{len(seeds())} seeds")
    print(f"{'cause':18} {'variants':>8} {'caught':>7} {'missed':>7}")
    for cause, (n, ok, bad) in table(rows).items():
        if cause == "benign":
            print(f"\n{'':18} {'variants':>8} {'valid':>7} {'alarms':>7}")
        print(f"{cause:18} {n:>8} {ok:>7} {bad:>7}")
    print()
    for (cause, name), (kind, why) in CLASSIFIED.items():
        print(f"{kind:5} {cause}/{name}: {why}")


if __name__ == "__main__":
    main()
