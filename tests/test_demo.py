"""End to end: the offline demo is the contract. Naive single judge ships, valid-evals refuses on valid runs,
and an edited threshold is refused."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestDemo(unittest.TestCase):
    def test_offline_demo_contract(self):
        p = subprocess.run([sys.executable, "examples/demo/run_offline.py"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("naive single judge pass rate: 0.875", p.stdout)
        self.assertIn('"pass_rate": 0.75', p.stdout)
        self.assertIn("REFUSED: manifest changed after sealing", p.stdout)


if __name__ == "__main__":
    unittest.main()
