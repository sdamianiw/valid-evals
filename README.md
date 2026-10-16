# valid-evals

**Your eval passed. Was the run even valid?**

Agent evals can pass for the wrong reasons. The run used another model. The agent read the answer key. Someone
typed a hint halfway through. The pass bar moved after the numbers came in. A single LLM judge sees none of this.

valid-evals is a small layer that sits after whatever runs your agent (`claude -p`, promptfoo, caliper, your own
script). Before a score counts, it answers three questions:

1. **Was the rule fixed before we looked?** The decision rule (metric, threshold, the exact sentence for pass and
   for fail) is sealed with sha256 before any run. Edit it afterwards and the decision is refused.
2. **Was the run valid?** Each trace is checked, without any model call, for a crash, host hooks or MCP servers
   leaking in, a model other than the one you asked for, the answer key showing up (canary strings), a human turn,
   or a tool outside the allowlist. An invalid run gets exactly one cause and never counts.
3. **Do two judges from different vendors agree?** A case counts only when both say pass or both say fail. A split
   goes to a queue for a person. Output a judge cannot parse is counted as an error, never as a vote.

It is not a runner, a dashboard or a framework. Python standard library only.

## Try it (no API key)

```bash
git clone https://github.com/sdamianiw/valid-evals && cd valid-evals
python3 examples/demo/run_offline.py
```

Eight synthetic runs of a coding agent. Three of them cheat in ways a lone judge cannot see.

```
naive single judge pass rate: 0.875 (counts every run, trusts judge a alone)

01_clean       VALID    PASS
04_split       VALID    DISAGREE
06_wrong_model INVALID  model_mismatch
07_read_answer INVALID  reference_leak
08_human_hint  INVALID  human_turn
...
{"ok": false, "pass_rate": 0.75, "counted": 4, "excluded": {"invalid": 3, "disagree": 1, "judge_error": 0}, ...}
Do not ship: on valid runs the agent is under the sealed bar.

after editing the threshold to 0.7: exit 2 REFUSED: manifest changed after sealing; decision refused
```

The naive number says ship. The valid number says do not.

## Use it on your own runs

1. Write `manifest.json` (see `examples/demo/run_offline.py` for every field) and seal it:
   `python3 -m valid_evals seal manifest.json`. Commit `manifest.lock` before you run anything; git history is
   your timestamp.
2. Put a canary string inside every reference or answer file the agent must not read.
3. Run your agent in bare mode and keep the trace:
   `claude --bare -p "$TASK" --model claude-sonnet-5-5 --allowedTools "Read,Grep,Edit" --output-format stream-json --verbose > cases/01/trace.jsonl`
4. Put what the judges should grade in `cases/01/case.txt` (task, rubric, the agent's final output).
5. `python3 -m valid_evals run manifest.json cases/`

Exit code 0 means the sealed rule passed, 1 means it failed, 2 means the decision was refused.

### Judges

A judge is any command that reads the case on stdin and prints `{"verdict": "pass"}` or `{"verdict": "fail"}`.
The output of `claude -p --output-format json --json-schema` is also understood (it reads `structured_output`).

```json
{"name": "claude", "vendor": "anthropic",
 "cmd": ["claude", "--bare", "-p", "Grade this case against its rubric. Answer pass or fail.",
         "--output-format", "json",
         "--json-schema", "{\"type\":\"object\",\"properties\":{\"verdict\":{\"enum\":[\"pass\",\"fail\"]}},\"required\":[\"verdict\"]}"]}
```

The second judge must come from another vendor, for example an OpenAI model through the Codex CLI or a small
script that calls any other API. The seal step rejects two judges from the same vendor.

## What it does not catch (yet)

- A canary that the agent sees in a transformed form (base64, paraphrase). Canaries catch copies, not understanding.
- Human turns outside bare mode, where Claude Code adds its own user messages. Use `require_bare`.
- Traces from runners other than `claude -p` stream-json. Codex is next, behind an adapter.
- Judge agreement is only as good as the judges. Measure their agreement with a person on a sample before you
  trust a pass rate.

## Status

v0.1. The offline demo and 29 tests pass. The figures above come from synthetic traces; figures from live
runs will be added once measured.

MIT license.
