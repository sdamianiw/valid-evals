"""No employer name in any tracked file or commit message. Names are kept as sha256 of lowercase tokens, so this
file does not contain them either."""

from __future__ import annotations

import hashlib
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = {
    "1aa1ff1fd55961372a21c1dd536ccbb667d8dd467c12ca1cd5ed64023c8ee900",
    "ad589ceb8b5ccca048911a0e4dcf5466a1f14dc9f50517c9a2c53988d7de2521",
    "9b925b5b94a1f5cbfc4cc3101f9be5fb204c3c92d285c8ab96f0326490b44c2e",
    "0874fc2a18ccda9ef24b2d5e5b33efcfd08c45d9fd84accc37866bfa984f1030",
}
_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def hits(text: str, forbidden=frozenset(FORBIDDEN)) -> set[str]:
    out = set()
    for tok in _TOKEN.findall(text.lower()):
        for cand in {tok, *tok.split("-"), tok.replace("-", "")}:
            if hashlib.sha256(cand.encode()).hexdigest() in forbidden:
                out.add(cand)
    return out


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


class TestCleanRoom(unittest.TestCase):
    def test_the_check_catches_a_planted_name(self):
        planted = {hashlib.sha256(b"zebrafin").hexdigest()}
        self.assertEqual(hits("Built for Zebrafin-Global.", planted), {"zebrafin"})
        self.assertEqual(hits("nothing here", planted), set())

    def test_no_forbidden_name_in_tracked_files(self):
        bad = {}
        for name in git("ls-files").splitlines():
            p = ROOT / name
            try:
                found = hits(name + "\n" + p.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, FileNotFoundError):
                continue
            if found:
                bad[name] = sorted(found)
        self.assertEqual(bad, {})

    def test_no_forbidden_name_in_commit_messages(self):
        self.assertEqual(hits(git("log", "--format=%B")), set())


if __name__ == "__main__":
    unittest.main()
