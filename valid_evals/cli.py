"""valid-evals command line.

  python -m valid_evals seal MANIFEST            freeze the rule (writes MANIFEST.lock)
  python -m valid_evals check MANIFEST TRACE...  validity of each run trace
  python -m valid_evals run MANIFEST CASES_DIR   check + jury + decide over CASES_DIR/<case>/{trace.jsonl,case.txt}

Exit codes: 0 sealed rule passed, 1 sealed rule failed, 2 refused (broken seal, too few valid cases, bad input).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from valid_evals import decide, jury, seal, validity


def _check(manifest: dict, trace: Path) -> dict:
    v = validity.check(trace.read_text(encoding="utf-8"), manifest)
    return {"trace": str(trace), "valid": v.valid, "cause": v.cause, "details": v.details}


def cmd_run(manifest_path: Path, cases_dir: Path) -> int:
    m = seal.verify(manifest_path)
    rows, queue = [], []
    for case in sorted(p for p in cases_dir.iterdir() if p.is_dir()):
        row = {"case": case.name, **_check(m, case / "trace.jsonl")}
        if row["valid"]:
            j = jury.judge((case / "case.txt").read_text(encoding="utf-8"), m["judges"])
            row.update(verdict=j.verdict, votes=j.votes)
            if j.verdict == "DISAGREE":
                queue.append(row)
        rows.append(row)
    (cases_dir / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (cases_dir / "human_queue.jsonl").write_text("".join(json.dumps(r) + "\n" for r in queue))
    d = decide.decide(manifest_path, rows)
    for r in rows:
        print(f"{r['case']:<14} {'VALID' if r['valid'] else 'INVALID':<8} {r.get('cause') or r.get('verdict')}")
    print(json.dumps({"ok": d.ok, "pass_rate": round(d.value, 3), "counted": d.counted, "excluded": d.excluded,
                      "manifest_sha256": d.manifest_sha256}))
    print(d.sentence)
    return 0 if d.ok else 1


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
        return cmd_run(a.manifest, a.cases_dir)
    except (seal.SealError, decide.DecisionError, OSError, json.JSONDecodeError, KeyError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
