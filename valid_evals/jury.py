"""Two judges from two vendors. Each judge is a command that reads the case on stdin and prints
{"verdict": "pass"|"fail"}. Only agreement counts; a split goes to a human queue."""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass, field

TIMEOUT_S = 300


@dataclass
class JuryResult:
    verdict: str  # PASS, FAIL, DISAGREE or JUDGE_ERROR
    votes: dict = field(default_factory=dict)


def _strict(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate keys")
    return dict(pairs)


def _vote(judge: dict, case_text: str) -> str:
    try:
        with tempfile.TemporaryDirectory() as empty:  # a judge sees the case on stdin and nothing else
            # UTF-8 both ways whatever the locale (Windows defaults to cp1252); bytes that do not decode
            # become U+FFFD, so the vote fails to parse and counts as an error instead of a crash
            proc = subprocess.run(judge["cmd"], input=case_text, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=TIMEOUT_S, cwd=empty)
    except (OSError, subprocess.TimeoutExpired):
        return "error"
    if proc.returncode != 0:
        return "error"
    out = proc.stdout.strip()
    try:  # the whole output as one JSON value, or else only its last line: never an earlier line
        obj = json.loads(out, object_pairs_hook=_strict)
    except json.JSONDecodeError:
        try:
            obj = json.loads(out.splitlines()[-1], object_pairs_hook=_strict) if out else None
        except (json.JSONDecodeError, ValueError):
            return "error"
    except ValueError:  # duplicate keys: two answers in one object
        return "error"
    if not isinstance(obj, dict) or obj.get("is_error"):
        return "error"
    # plain {"verdict": ...}, or claude -p --output-format json --json-schema, which nests it
    nested = obj.get("structured_output")
    v = obj.get("verdict", nested.get("verdict") if isinstance(nested, dict) else None)
    return v if v in ("pass", "fail") else "error"


def combine(votes: dict) -> str:
    """The jury rule, also used by calibrate to check that a stored verdict follows from its votes."""
    vals = set(votes.values())
    if "error" in vals:
        verdict = "JUDGE_ERROR"
    elif vals == {"pass"}:
        verdict = "PASS"
    elif vals == {"fail"}:
        verdict = "FAIL"
    else:
        verdict = "DISAGREE"
    return verdict


def judge(case_text: str, judges: list[dict]) -> JuryResult:
    votes = {j["name"]: _vote(j, case_text) for j in judges}
    return JuryResult(combine(votes), votes)
