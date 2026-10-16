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



class TestReadmeShowsTheRealDemo(unittest.TestCase):
    """The README output block is the demo's real output, not typed by hand."""

    def test_readme_block_equals_demo_output(self):
        out = subprocess.run([sys.executable, "examples/demo/run_offline.py"], cwd=ROOT, capture_output=True,
                             text=True).stdout.strip()
        readme = (ROOT / "README.md").read_text()
        start = readme.index("<!-- demo-output -->")
        block = readme[start:].split("```", 2)[1]
        self.assertEqual(block.strip(), out)
        self.assertEqual(readme.count("after editing the threshold to 0.7: exit 2"), 1, "demo output pasted outside its block")



class TestReadmeTestCount(unittest.TestCase):
    def test_readme_states_the_real_test_count(self):
        import re
        n = unittest.TestLoader().discover(str(ROOT / "tests"), top_level_dir=str(ROOT)).countTestCases()
        stated = int(re.search(r"and (\d+) tests pass", (ROOT / "README.md").read_text()).group(1))
        self.assertEqual(stated, n)


if __name__ == "__main__":
    unittest.main()
