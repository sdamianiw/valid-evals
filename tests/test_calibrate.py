"""Judge calibration: agreement between the two judges and with human labels, gated by a sealed minimum."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from valid_evals import calibrate, cli, seal  # noqa: E402
from tests.test_core import manifest  # noqa: E402


def rows(*votes):
    return [{"case": f"c{n}", "valid": True, "votes": {"a": a, "b": b}} for n, (a, b) in enumerate(votes)]


class TestKappa(unittest.TestCase):
    def test_perfect_agreement(self):
        self.assertEqual(calibrate.kappa(["pass", "fail"], ["pass", "fail"]), 1.0)

    def test_chance_level_is_zero(self):
        self.assertAlmostEqual(calibrate.kappa(["pass", "pass", "fail", "fail"], ["pass", "fail", "pass", "fail"]), 0.0)

    def test_known_value(self):
        # po = 0.8, pe = 0.6*0.8 + 0.4*0.2 = 0.56, kappa = 0.24 / 0.44; then po = 0.6, pe = 0.52
        a = ["pass", "pass", "pass", "fail", "fail"]
        b = ["pass", "pass", "fail", "fail", "pass"]
        self.assertAlmostEqual(calibrate.kappa(a * 2, ["pass", "pass", "pass", "fail", "pass"] * 2), 0.5454545, 5)
        self.assertAlmostEqual(calibrate.kappa(a, b), (0.6 - 0.52) / 0.48, 5)

    def test_one_label_only_is_undefined(self):
        self.assertIsNone(calibrate.kappa(["pass", "pass"], ["pass", "pass"]))


class TestCalibrate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def sealed(self, **cal):
        m = manifest(calibration={"min_kappa": 0.6, "min_labels": 4, **cal})
        p = self.d / "manifest.json"
        p.write_text(json.dumps(m))
        seal.seal(p)
        return p

    AGREE = [("pass", "pass"), ("fail", "fail"), ("pass", "pass"), ("fail", "fail"), ("error", "pass")]
    HUMAN = {"c0": "pass", "c1": "fail", "c2": "pass", "c3": "fail", "c4": "pass"}

    def test_report_counts_and_passes_the_sealed_minimum(self):
        r = calibrate.calibrate(self.sealed(), rows(*self.AGREE), self.HUMAN)
        self.assertTrue(r["ok"])
        self.assertEqual(r["pairs"]["a~b"], {"n": 4, "agreement": 1.0, "kappa": 1.0})
        self.assertEqual(r["pairs"]["a~human"]["n"], 4)
        self.assertEqual(r["pairs"]["b~human"]["n"], 5)
        self.assertEqual(r["judge_errors"], {"a": 1, "b": 0})

    def test_low_agreement_with_people_fails(self):
        human = {"c0": "fail", "c1": "pass", "c2": "pass", "c3": "fail"}
        r = calibrate.calibrate(self.sealed(), rows(*self.AGREE), human)
        self.assertFalse(r["ok"])

    def test_too_few_labels_is_refused(self):
        with self.assertRaises(calibrate.CalibrationError):
            calibrate.calibrate(self.sealed(min_labels=10), rows(*self.AGREE), self.HUMAN)

    def test_undefined_kappa_fails(self):
        same = [("pass", "pass")] * 5
        r = calibrate.calibrate(self.sealed(), rows(*same), {f"c{n}": "pass" for n in range(5)})
        self.assertFalse(r["ok"])

    def test_no_sealed_minimum_is_refused(self):
        p = self.d / "manifest.json"
        p.write_text(json.dumps(manifest()))
        seal.seal(p)
        with self.assertRaises(calibrate.CalibrationError):
            calibrate.calibrate(p, rows(*self.AGREE), self.HUMAN)

    def test_bad_human_label_is_refused(self):
        with self.assertRaises(calibrate.CalibrationError):
            calibrate.calibrate(self.sealed(), rows(*self.AGREE), {**self.HUMAN, "c0": "maybe"})

    def test_labels_that_are_not_a_mapping_are_refused(self):
        with self.assertRaises(calibrate.CalibrationError):
            calibrate.calibrate(self.sealed(), rows(*self.AGREE), ["pass", "fail"])

    def test_cli_exit_codes(self):
        p = self.sealed()
        cases = self.d / "cases"
        cases.mkdir()
        (cases / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows(*self.AGREE)))
        labels = self.d / "labels.json"
        labels.write_text(json.dumps(self.HUMAN))
        self.assertEqual(cli.main(["calibrate", str(p), str(cases), str(labels)]), 0)
        labels.write_text(json.dumps({"c0": "fail", "c1": "pass", "c2": "pass", "c3": "fail"}))
        self.assertEqual(cli.main(["calibrate", str(p), str(cases), str(labels)]), 1)
        p.write_text(p.read_text().replace("0.6", "0.1"))
        self.assertEqual(cli.main(["calibrate", str(p), str(cases), str(labels)]), 2)

    def test_seal_rejects_a_malformed_calibration_block(self):
        with self.assertRaises(seal.SealError):
            seal.validate(manifest(calibration={"min_kappa": "high"}))


if __name__ == "__main__":
    unittest.main()
