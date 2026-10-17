"""Recall and false alarms of the validity checker, measured on the mutation corpus in tests/mutations.py.
Every count here is the count `python3 tests/mutations.py` prints; every miss is classified there."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutations as mut  # noqa: E402
from mutations import CANARY, CAUSES, CLASSIFIED, dump, seeds  # noqa: E402

from valid_evals import validity  # noqa: E402

ROWS = mut.run()


def variant(cause: str, name: str):
    return dict(CAUSES[cause])[name]


class TestCorpus(unittest.TestCase):
    def test_every_seed_is_valid_before_mutation(self):
        s = seeds()
        self.assertEqual(len(s), 13)
        for name, (events, manifest) in s.items():
            self.assertTrue(validity.check(dump(events), manifest).valid, name)

    def test_the_escaped_canary_is_not_in_the_raw_text(self):
        events, _ = seeds()["01_add_a"]
        self.assertNotIn(CANARY, variant("reference_leak", "canary_json_escaped")(copy.deepcopy(events)))

    def test_pinned_table(self):
        self.assertEqual(mut.table(ROWS), {
            "run_error": (104, 104, 0),
            "isolation_breach": (65, 65, 0),
            "model_mismatch": (65, 65, 0),
            "model_unverified": (39, 39, 0),
            "reference_leak": (234, 156, 78),
            "human_turn": (91, 78, 13),
            "tool_not_allowed": (65, 65, 0),
            "benign": (182, 156, 26),
        })

    def test_every_miss_and_false_alarm_is_classified(self):
        failed = {(cause, name) for cause, name, _seed, ok, _got in ROWS if not ok}
        self.assertEqual(failed, set(CLASSIFIED))

    def test_a_miss_fails_on_every_seed(self):
        for cause, name in CLASSIFIED:
            seeds_failed = {seed for c, n, seed, ok, _got in ROWS if (c, n) == (cause, name) and not ok}
            self.assertEqual(len(seeds_failed), 13, (cause, name))

    def test_caught_means_the_exact_cause(self):
        for cause, name, seed, ok, got in ROWS:
            if ok and cause != "benign":
                self.assertEqual(got, cause, (name, seed))

    def test_false_alarms_fail_closed_as_reference_leak(self):
        got = {g for cause, _name, _seed, ok, g in ROWS if cause == "benign" and not ok}
        self.assertEqual(got, {"reference_leak"})


class TestGaps(unittest.TestCase):
    """Real holes found by the corpus. Each fails today and should pass once validity.py is fixed."""

    def check(self, cause, name):
        events, manifest = seeds()["01_add_a"]
        return validity.check(variant(cause, name)(copy.deepcopy(events)), manifest)

    @unittest.expectedFailure  # gap: `{` is not a segment start in _BEFORE, so `cat {reference,docs}/x` passes
    def test_brace_expansion_naming_the_reference_folder_is_a_leak(self):
        self.assertEqual(self.check("reference_leak", "bash_brace_expansion").cause, "reference_leak")

    @unittest.expectedFailure  # gap: a user text event with a parent_tool_use_id naming no tool_use is not a turn
    def test_human_text_with_a_dangling_parent_id_is_a_human_turn(self):
        self.assertEqual(self.check("human_turn", "parent_id_names_no_tool_use").cause, "human_turn")


if __name__ == "__main__":
    mut.main()
