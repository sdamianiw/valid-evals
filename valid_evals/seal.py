"""Freeze the decision rule before any result is seen. The manifest is canonicalized (sorted keys, no spaces,
UTF-8) and hashed with sha256; manifest.lock holds the hash. Any later edit fails closed."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

REQUIRED = ("metric", "comparator", "threshold", "min_valid_cases", "outcome", "allowed_models", "allowed_tools",
            "canaries", "require_bare", "judges")
COMPARATORS = (">=", ">", "<=", "<")


class SealError(Exception):
    pass


def canonical(manifest: dict) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(manifest: dict) -> str:
    return hashlib.sha256(canonical(manifest)).hexdigest()


def _number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _count(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x > 0


def _strings(x, allow_empty_list=True) -> bool:
    return isinstance(x, list) and (allow_empty_list or x) and all(isinstance(s, str) and s for s in x)


def _pairs(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise SealError(f"duplicate keys in manifest: {sorted({k for k in keys if keys.count(k) > 1})}")
    return dict(pairs)


def _no_constant(name):
    raise SealError(f"{name} is not valid in a manifest")


def load(manifest_path: Path) -> dict:
    """Strict read: duplicate keys, NaN and Infinity are refused, so what is hashed is what is applied."""
    try:
        m = json.loads(Path(manifest_path).read_text(encoding="utf-8"), object_pairs_hook=_pairs,
                       parse_constant=_no_constant)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise SealError(f"manifest is not valid JSON: {e}") from None
    if not isinstance(m, dict):
        raise SealError("manifest must be a JSON object")
    return m


def validate(m: dict) -> None:
    missing = [k for k in REQUIRED if k not in m]
    if missing:
        raise SealError(f"manifest missing {missing}")
    if m["comparator"] not in COMPARATORS:
        raise SealError(f"comparator must be one of {COMPARATORS}")
    if not _number(m["threshold"]):
        raise SealError("threshold must be a number")
    if not _count(m["min_valid_cases"]):
        raise SealError("min_valid_cases must be a positive integer")
    if not isinstance(m["outcome"], dict) or set(m["outcome"]) != {"pass", "fail"} \
            or not all(isinstance(v, str) and v for v in m["outcome"].values()):
        raise SealError("outcome needs exactly a pass and a fail sentence")
    if not _strings(m["allowed_models"], allow_empty_list=False):
        raise SealError("allowed_models must be a non empty list of model ids")
    if not _strings(m["allowed_tools"]):
        raise SealError("allowed_tools must be a list of tool names")
    if not _strings(m["canaries"], allow_empty_list=False):
        raise SealError("canaries must be a non empty list of non empty strings")
    for flag in ("require_bare", "trust_runner_model"):
        if flag in m and not isinstance(m[flag], bool):
            raise SealError(f"{flag} must be true or false")
    judges = m["judges"]
    if not isinstance(judges, list) or len(judges) != 2 \
            or not all(isinstance(j, dict) and isinstance(j.get("cmd"), list) and j["cmd"]
                       and all(isinstance(a, str) for a in j["cmd"]) and j["cmd"][0]
                       and isinstance(j.get("name"), str) and isinstance(j.get("vendor"), str) for j in judges):
        raise SealError("jury needs two judges, each with a name, a vendor and a cmd list")
    if len({j["name"] for j in judges}) != 2:
        raise SealError("judge names must differ")
    if len({j["vendor"].strip().casefold() for j in judges}) != 2:
        raise SealError("jury needs two judges from two different vendors")
    refs = m.get("reference_paths", [])
    if not isinstance(refs, list) or not all(isinstance(r, str) and r for r in refs):
        raise SealError("reference_paths must be a list of non empty strings")
    cal = m.get("calibration")
    if cal is not None and not (isinstance(cal, dict) and _number(cal.get("min_kappa"))
                                and 0 <= cal["min_kappa"] <= 1 and _count(cal.get("min_labels"))
                                and _number(cal.get("max_judge_error_rate"))
                                and 0 <= cal["max_judge_error_rate"] < 1):
        raise SealError("calibration needs min_kappa in [0, 1], a positive integer min_labels and "
                        "max_judge_error_rate in [0, 1)")


def lock_path(manifest_path: Path) -> Path:
    return manifest_path.with_suffix(".lock")


def seal(manifest_path: Path) -> str:
    m = load(manifest_path)
    validate(m)
    h = digest(m)
    lock = lock_path(Path(manifest_path))
    if lock.exists() and lock.read_text().strip() != h:
        raise SealError(f"{lock} already holds another hash; a sealed rule is never resealed in place")
    lock.write_text(h + "\n")
    return h


def verify(manifest_path: Path) -> dict:
    manifest_path = Path(manifest_path)
    lock = lock_path(manifest_path)
    if not lock.exists():
        raise SealError(f"no {lock}: seal the manifest before the run")
    m = load(manifest_path)
    if digest(m) != lock.read_text().strip():
        raise SealError("manifest changed after sealing; decision refused")
    validate(m)
    return m
