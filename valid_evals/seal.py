"""Freeze the decision rule before any result is seen. The manifest is canonicalized (sorted keys, no spaces,
UTF-8) and hashed with sha256; manifest.lock holds the hash. Any later edit fails closed."""

from __future__ import annotations

import hashlib
import json
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


def validate(m: dict) -> None:
    missing = [k for k in REQUIRED if k not in m]
    if missing:
        raise SealError(f"manifest missing {missing}")
    if m["comparator"] not in COMPARATORS:
        raise SealError(f"comparator must be one of {COMPARATORS}")
    if set(m["outcome"]) != {"pass", "fail"}:
        raise SealError("outcome needs exactly a pass and a fail sentence")
    judges = m["judges"]
    if len(judges) != 2 or len({j["vendor"] for j in judges}) != 2:
        raise SealError("jury needs two judges from two different vendors")
    refs = m.get("reference_paths", [])
    if not isinstance(refs, list) or not all(isinstance(r, str) and r for r in refs):
        raise SealError("reference_paths must be a list of non empty strings")
    cal = m.get("calibration")
    if cal is not None and not (isinstance(cal, dict) and isinstance(cal.get("min_kappa"), (int, float))
                                and isinstance(cal.get("min_labels"), int) and cal["min_labels"] > 0):
        raise SealError("calibration needs a numeric min_kappa and a positive integer min_labels")


def lock_path(manifest_path: Path) -> Path:
    return manifest_path.with_suffix(".lock")


def seal(manifest_path: Path) -> str:
    m = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
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
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    if digest(m) != lock.read_text().strip():
        raise SealError("manifest changed after sealing; decision refused")
    validate(m)
    return m
