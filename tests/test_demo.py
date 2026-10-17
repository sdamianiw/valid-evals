"""End to end: the offline demo is the contract. Naive single judge ships, valid-evals refuses on valid runs,
and an edited threshold is refused."""
import re
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
        # judge commands hold the interpreter path and are part of the sealed rule, so hashes differ per machine
        mask = lambda t: re.sub(r"\b[0-9a-f]{64}\b", "<sha256>", t)
        self.assertEqual(mask(block.strip()), mask(out))
        self.assertEqual(readme.count("after editing the threshold to 0.7: exit 2"), 1, "demo output pasted outside its block")



class TestReadmeVersion(unittest.TestCase):
    def test_readme_status_names_the_package_version(self):
        import re
        sys.path.insert(0, str(ROOT))
        import valid_evals
        stated = re.search(r"## Status\n\nv([0-9.]+)\.", (ROOT / "README.md").read_text()).group(1)
        self.assertEqual(stated, valid_evals.__version__)

if __name__ == "__main__":
    unittest.main()
