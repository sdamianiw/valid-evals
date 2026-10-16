# valid-evals principles (read before any action)

1. No employer names. The author's own methods may be reused, but no company name, client, project name or
   internal path appears anywhere in the repo. `tests/test_clean_room.py` guards this by hash. If in doubt, ask.
2. Not a runner. We judge runs that other tools produce. Anything that turns this into a framework needs an ADR.
3. Deterministic first: if a check can be a regex, a table or a parse, it is not a prompt. Validity never calls a model.
4. Fail closed. A broken seal, too few valid cases, an unknown trace shape or an unparsable judge never counts as a pass.
5. TDD: reproduce the failure with a RED test before every fix. The offline demo is the end to end contract.
6. Report only what a command proves. README figures come from real runs or are marked synthetic.
7. Simplicity first, minimal impact, stdlib only unless an ADR says otherwise.
8. No dashes in human facing text. Humanizer style: no filler, no promotional words.
9. Never push to main without the full suite green: `python3 -m unittest discover -s tests`.
