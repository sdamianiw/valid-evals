"""How far can the jury be trusted? Agreement between the two judges, and of each judge with a small human
labeled sample, as raw agreement and Cohen's kappa with counts. Reads the votes `run` already wrote, so no
judge is called again. Fails closed: no sealed minimum, too few labels, a bad label or an undefined kappa
never pass."""

from __future__ import annotations

from pathlib import Path

from valid_evals import decide, seal

LABELS = ("pass", "fail")


class CalibrationError(Exception):
    pass


def kappa(a: list[str], b: list[str]) -> float | None:
    """Cohen's kappa for two raters over the same items; None when chance agreement is 1 (one label only)."""
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(k) / n) * (b.count(k) / n) for k in LABELS)
    return None if pe == 1 else (po - pe) / (1 - pe)


def _pair(x: dict, y: dict) -> dict:
    keys = sorted(k for k in x if k in y and x[k] in LABELS and y[k] in LABELS)
    a, b = [x[k] for k in keys], [y[k] for k in keys]
    k = kappa(a, b)
    counts = {f"{p}_{q}": sum(x == p and y == q for x, y in zip(a, b)) for p in LABELS for q in LABELS}
    return {"n": len(keys), "agreement": round(sum(p == q for p, q in zip(a, b)) / len(keys), 4) if keys else None,
            "kappa": None if k is None else round(k, 4), "counts": counts}


def calibrate(manifest_path: Path, rows: list[dict], human: dict) -> dict:
    m = seal.verify(manifest_path)
    cal = m.get("calibration")
    if not cal:
        raise CalibrationError("no sealed calibration minimum (calibration.min_kappa, calibration.min_labels)")
    if not isinstance(human, dict):
        raise CalibrationError('human labels must be a JSON object {"case": "pass"|"fail"}')
    bad = {k: v for k, v in human.items() if v not in LABELS}
    if bad:
        raise CalibrationError(f"human labels must be pass or fail: {bad}")
    names = [j["name"] for j in m["judges"]]
    votes = {n: {r["case"]: r["votes"].get(n) for r in rows if r.get("valid") and r.get("votes")} for n in names}
    pairs = {f"{names[0]}~{names[1]}": _pair(votes[names[0]], votes[names[1]])}
    for n in names:
        pairs[f"{n}~human"] = _pair(votes[n], human)
    labeled = min(pairs[f"{n}~human"]["n"] for n in names)
    if labeled < cal["min_labels"]:
        raise CalibrationError(f"{labeled} human labeled cases with a vote, the sealed minimum is {cal['min_labels']}")
    errors = {n: sum(v not in LABELS for v in votes[n].values()) for n in names}
    rates = {n: errors[n] / len(votes[n]) if votes[n] else 1.0 for n in names}
    ok = all(p["kappa"] is not None and p["kappa"] >= cal["min_kappa"] for p in pairs.values()) \
        and all(r <= cal["max_judge_error_rate"] for r in rates.values())
    d = decide.decide(manifest_path, rows)
    return {"ok": ok, "min_kappa": cal["min_kappa"], "pairs": pairs, "judge_errors": errors,
            "judge_error_rate": {n: round(r, 4) for n, r in rates.items()},
            "decision": {"ok": d.ok, "pass_rate": round(d.value, 4), "counted": d.counted, "sentence": d.sentence},
            "final": ok and d.ok, "manifest_sha256": seal.digest(m)}
