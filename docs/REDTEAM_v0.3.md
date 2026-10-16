# Red team and advisor review, v0.2 to v0.3 (2026 10 16)

An independent red team agent attacked v0.2 in an isolated worktree, recomputing kappa on its own (0 mismatches
over 40 random label sets). A second model reviewed the design. Every finding below was reproduced as a failing
test before its fix; the tests are `tests/test_redteam.py` and `tests/test_v03.py`, and they now act as the
regression bank.

| Finding | Severity | Fix |
|---|---|---|
| Error subtypes counted as VALID when `is_error` was false or missing | fail open | run_error unless `subtype` is `success` and `is_error` is false. Real 2.1.301 sets `is_error: true` on `error_max_turns` (fixture), so this mattered only for other versions or runners |
| Two judges with one name hid the second vote | fail open | seal refuses duplicate names; vendors compared ignoring case |
| Only `<synthetic>` messages, so no model was ever checked | fail open | model_unverified |
| Canaries with quotes, backslashes, tabs or non ASCII never matched the JSON escaped trace; empty canaries checked nothing | fail open | match raw and escaped forms; seal needs a non empty list of non empty canaries |
| Only the last result was read; events after it ignored | fail open | exactly one result, nothing from the agent after it, exactly one init |
| A Claude trace with Codex events took the weaker path; `"false"` read as trust | fail open | mixed shapes are a run_error; flags must be booleans |
| Codex tools seen only in `item.started` or `item.updated`, or behind a reused id, were missed | fail open | every item event is read |
| Calibration passed while nearly every vote was an error | misleading | sealed `max_judge_error_rate` |
| `min_kappa` of -1, Infinity or `true` switched calibration off | misleading | seal bounds and types |
| Duplicate keys in the manifest applied a different value than the reader saw | misleading | strict loader refuses duplicates, NaN and Infinity |
| Empty parent id or image only user turns were not human turns; a judge's earlier JSON line beat its last word | misleading | fixed; judge output is read whole or by last line only |
| Bad input crashed with exit 1, which means "the rule failed" | robustness | any unexpected error refuses with exit 2; malformed traces are a run_error |
| Dated allowed model ids never matched | robustness | dates stripped on both sides |
| `live.py cost` summed result events, not runs | misleading figure | one cost per run; runs without exactly one result are listed |
| Advisor: the negative control rubric told judges the answer | misleading figure | rubric neutral; the note lives in a file judges never see |
| Advisor: split cases dropped silently; no uncertainty | misleading | bounds and Wilson interval printed; people label but never change the result |
| Advisor: judges could read traces and references from the working directory | fail open risk | judges run in an empty temporary directory |

Not fixed, by choice:

- Subagent messages on another model are a model_mismatch. That is strict on purpose: list subagent models in
  `allowed_models`.
- One user text before the first assistant message is still allowed as an echoed prompt, for runners that echo
  it. `claude -p` does not, per the fixtures.
- The available tool set in the init event is not compared with `allowed_tools` yet; only tools actually used
  are. Planned, since it would change how the README example has to be run.
