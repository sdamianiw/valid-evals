"""The seal records when it was made; a run that started before it cannot count (red team round 3, finding 2)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from valid_evals import cli, seal  # noqa: E402
from tests.test_core import manifest, trace  # noqa: E402

SCRIPTED = str(ROOT / "examples" / "demo" / "scripted_judge.py")
JUDGES = [{"name": "a", "vendor": "anthropic", "cmd": [sys.executable, SCRIPTED, "a"]},
          {"name": "b", "vendor": "openai", "cmd": [sys.executable, SCRIPTED, "b"]}]


def timed(ts):
    lines = [json.loads(x) for x in trace().splitlines()]
    for e in lines:
        if e["type"] in ("assistant", "user"):
            e["timestamp"] = ts
    return "\n".join(json.dumps(e) for e in lines) + "\n"


class TestSealTime(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.p = self.d / "manifest.json"
        self.p.write_text(json.dumps(manifest(threshold=0.5, min_valid_cases=1, judges=JUDGES)))

    def cases(self, *stamps):
        for i, ts in enumerate(stamps):
            c = self.d / "cases" / f"c{i}"
            c.mkdir(parents=True)
            (c / "trace.jsonl").write_text(timed(ts))
            (c / "case.txt").write_text("demo-votes: a=pass b=pass\n")
        return str(self.d / "cases")

    def test_sealing_after_the_runs_is_refused(self):
        cases = self.cases("2026-10-16T21:28:37.844Z")
        seal.seal(self.p)
        self.assertEqual(cli.main(["run", str(self.p), cases]), 2)

    def test_runs_after_the_seal_count(self):
        seal.seal(self.p)
        self.assertEqual(cli.main(["run", str(self.p), self.cases("2099-01-01T00:00:00Z")]), 0)

    def test_resealing_the_same_rule_keeps_the_first_time(self):
        seal.seal(self.p)
        first = seal.lock_path(self.p).read_text()
        seal.seal(self.p)
        self.assertEqual(seal.lock_path(self.p).read_text(), first)
        self.assertIn("sealed_at", first)

    def test_deleting_the_lock_and_resealing_is_refused(self):
        seal.seal(self.p)
        cases = self.cases("2099-01-01T00:00:00Z")
        lock = seal.lock_path(self.p)  # what deleting the lock and sealing again later leaves behind
        lock.write_text(lock.read_text().split("\n")[0] + "\nsealed_at 2100-01-01T00:00:00+00:00\n")
        self.assertEqual(cli.main(["run", str(self.p), cases]), 2)

    def test_calibrate_refuses_too(self):
        self.p.write_text(json.dumps(manifest(threshold=0.5, min_valid_cases=1, judges=JUDGES, calibration={
            "min_kappa": 0.0, "min_labels": 1, "max_judge_error_rate": 0.5})))
        seal.seal(self.p)
        cases = self.cases("2099-01-01T00:00:00Z")
        cli.main(["run", str(self.p), cases])
        labels = self.d / "labels.json"
        labels.write_text(json.dumps({"c0": "pass"}))
        lock = seal.lock_path(self.p)
        lock.write_text(lock.read_text().split("\n")[0] + "\nsealed_at 2100-01-01T00:00:00+00:00\n")
        self.assertEqual(cli.main(["calibrate", str(self.p), cases, str(labels)]), 2)

    def test_a_trace_without_timestamps_is_not_refused(self):
        seal.seal(self.p)
        c = self.d / "cases" / "c0"
        c.mkdir(parents=True)
        (c / "trace.jsonl").write_text(trace() + "\n")
        (c / "case.txt").write_text("demo-votes: a=pass b=pass\n")
        self.assertEqual(cli.main(["run", str(self.p), str(self.d / "cases")]), 0)


if __name__ == "__main__":
    unittest.main()
