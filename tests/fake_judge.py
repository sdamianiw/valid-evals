"""Stand-in judge for tests and the offline demo: prints a fixed verdict, garbage, or crashes."""
import json
import sys

mode = sys.argv[1]
sys.stdin.read()
if mode == "crash":
    sys.exit(3)
if mode == "structured_pass":  # shape of claude -p --output-format json --json-schema
    print(json.dumps({"type": "result", "is_error": False, "structured_output": {"verdict": "pass"}}))
else:
    print("not json at all" if mode == "garbage" else json.dumps({"verdict": mode}))
