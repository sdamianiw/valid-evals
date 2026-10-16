"""Offline demo judge. Reads the `demo-votes:` line of the case and prints this judge's vote. A live judge
replaces this with a real CLI call (see README)."""
import json
import re
import sys

name = sys.argv[1]
votes = dict(re.findall(r"(\w+)=(pass|fail)", re.search(r"demo-votes:(.*)", sys.stdin.read()).group(1)))
print(json.dumps({"verdict": votes[name]}))
