"""valid-evals command line.

  python -m valid_evals seal MANIFEST            freeze the rule (writes MANIFEST.lock)
  python -m valid_evals check MANIFEST TRACE...  validity of each run trace
  python -m valid_evals run MANIFEST CASES_DIR   check + jury + decide over CASES_DIR/<case>/{trace.jsonl,case.txt}
  python -m valid_evals calibrate MANIFEST CASES_DIR LABELS
                                                 judge agreement from CASES_DIR/results.jsonl vs LABELS
                                                 ({"case": "pass"|"fail"}), gated by the sealed minimum kappa

Exit codes: 0 sealed rule passed, 1 sealed rule failed or still provisional (calibration sealed, `calibrate` gives
the final decision), 2 refused (broken seal, too few valid cases, too many runs left out,
bad input). `check`: 0 all valid, 1 any invalid.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from valid_evals import calibrate, decide, jury, seal, validity


def _check(manifest: dict, trace: Path) -> dict:
    raw = trace.read_bytes()
    v = validity.check(raw.decode("utf-8"), manifest)
    return {"trace": str(trace), "trace_sha256": hashlib.sha256(raw).hexdigest(), "valid": v.valid, "cause": v.cause,
            "details": v.details}


def cmd_run(manifest_path: Path, cases_dir: Path) -> int:
    m = seal.verify(manifest_path)
    rows, queue = [], []
    cases = sorted(p for p in cases_dir.iterdir() if p.is_dir())
    for case in cases:  # before any judge call: a run older than the rule never counts
        seal.check_started_after(manifest_path, case.name, (case / "trace.jsonl").read_text(encoding="utf-8"))
    for case in cases:
        # paths relative to cases_dir, so results.jsonl and its hash are the same on any machine
        row = {"case": case.name, **_check(m, case / "trace.jsonl"), "trace": f"{case.name}/trace.jsonl",
               "manifest_sha256": seal.digest(m), "code_sha256": seal.code_digest()}
        if row["valid"]:
            j = jury.judge((case / "case.txt").read_text(encoding="utf-8"), m["judges"])
            row.update(verdict=j.verdict, votes=j.votes)
            if j.verdict == "DISAGREE":
                queue.append(row)
        rows.append(row)
    results = "".join(json.dumps(r) + "\n" for r in rows)
    (cases_dir / "results.jsonl").write_text(results)
    (cases_dir / "human_queue.jsonl").write_text("".join(json.dumps(r) + "\n" for r in queue))
    for r in rows:  # printed before deciding, so a refused decision still shows each run
        denied = len(r["details"].get("permission_denied", []))
        print(f"{r['case']:<14} {'VALID' if r['valid'] else 'INVALID':<8} {r.get('cause') or r.get('verdict')}"
              + (f"  ({denied} tool calls denied)" if denied else ""))
    d = decide.decide(manifest_path, rows)
    pending = "calibration" in m
    print(json.dumps({"ok": d.ok, "pass_rate": round(d.value, 3), "interval95": d.interval,
                      "if_disagreements_failed_or_passed": [round(b, 3) for b in d.bounds],
                      "counted": d.counted, "excluded": d.excluded, "manifest_sha256": d.manifest_sha256,
                      "results_sha256": hashlib.sha256(results.encode()).hexdigest(),
                      **({"calibration": "pending"} if pending else {})}))
    print(("PROVISIONAL until calibrate passes: " if pending else "") + d.sentence)
    return 0 if d.ok and not pending else 1  # a provisional pass is not a pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="valid-evals")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seal").add_argument("manifest", type=Path)
    c = sub.add_parser("check")
    c.add_argument("manifest", type=Path)
    c.add_argument("traces", type=Path, nargs="+")
    r = sub.add_parser("run")
    r.add_argument("manifest", type=Path)
    r.add_argument("cases_dir", type=Path)
    k = sub.add_parser("calibrate")
    k.add_argument("manifest", type=Path)
    k.add_argument("cases_dir", type=Path)
    k.add_argument("labels", type=Path)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "seal":
            print(seal.seal(a.manifest))
            return 0
        if a.cmd == "check":
            m = seal.verify(a.manifest)
            results = [_check(m, t) for t in a.traces]
            for res in results:
                print(json.dumps(res))
            return 0 if all(res["valid"] for res in results) else 1
        if a.cmd == "calibrate":
            raw = (a.cases_dir / "results.jsonl").read_bytes()
            rows = [json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip()]
            calibrate.verify_rows(a.manifest, rows, a.cases_dir)
            report = calibrate.calibrate(a.manifest, rows, json.loads(a.labels.read_text(encoding="utf-8")))
            report["results_sha256"] = hashlib.sha256(raw).hexdigest()
            print(json.dumps(report))
            if not report["ok"]:
                print("REFUSED: jury not calibrated, so there is no decision", file=sys.stderr)
                return 2
            print(report["decision"]["sentence"])
            return 0 if report["final"] else 1
        return cmd_run(a.manifest, a.cases_dir)
    except (seal.SealError, decide.DecisionError, calibrate.CalibrationError, OSError, json.JSONDecodeError, KeyError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # anything unexpected refuses; it never reads as "the rule failed"
        print(f"REFUSED: unexpected {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
