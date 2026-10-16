"""Apply the sealed rule to the rows that count: VALID runs with an agreed verdict. Fails closed."""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from pathlib import Path

from valid_evals import seal

OPS = {">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt}


class DecisionError(Exception):
    pass


@dataclass
class Decision:
    ok: bool
    sentence: str
    value: float
    counted: int
    excluded: dict = field(default_factory=dict)
    manifest_sha256: str = ""


def decide(manifest_path: Path, rows: list[dict]) -> Decision:
    m = seal.verify(manifest_path)
    if m["metric"] != "pass_rate":
        raise DecisionError(f"unknown metric {m['metric']}")
    excluded = {"invalid": 0, "disagree": 0, "judge_error": 0}
    counted = []
    for r in rows:
        if not r.get("valid"):
            excluded["invalid"] += 1
        elif r.get("verdict") == "DISAGREE":
            excluded["disagree"] += 1
        elif r.get("verdict") not in ("PASS", "FAIL"):
            excluded["judge_error"] += 1
        else:
            counted.append(r["verdict"] == "PASS")
    if len(counted) < m["min_valid_cases"]:
        raise DecisionError(f"{len(counted)} counted cases, the sealed minimum is {m['min_valid_cases']}")
    value = sum(counted) / len(counted)
    ok = OPS[m["comparator"]](value, m["threshold"])
    return Decision(ok, m["outcome"]["pass" if ok else "fail"], value, len(counted), excluded, seal.digest(m))
