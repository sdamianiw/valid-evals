"""Apply the sealed rule to the rows that count: VALID runs with an agreed verdict. Fails closed."""

from __future__ import annotations

import math
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
    interval: tuple = ()  # Wilson 95% interval of the pass rate over counted cases
    bounds: tuple = ()  # pass rate if every DISAGREE case had been a fail, or a pass; the decision does not use it


def wilson(passes: int, n: int, z: float = 1.959964) -> tuple:
    p, z2 = passes / n, z * z
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return (round(centre - half, 4), round(centre + half, 4))


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
    passes, n, k = sum(counted), len(counted), excluded["disagree"]
    value = passes / n
    ok = OPS[m["comparator"]](value, m["threshold"])
    return Decision(ok, m["outcome"]["pass" if ok else "fail"], value, n, excluded, seal.digest(m),
                    wilson(passes, n), (passes / (n + k), (passes + k) / (n + k)))
