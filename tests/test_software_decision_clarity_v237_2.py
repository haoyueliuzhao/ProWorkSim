"""Five graph-derived fields cannot be fabricated through the decision interface."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_obligation_scope_v237_1 as old
from proworksim import software_decision_clarity_v237_2 as policy
from proworksim.storage import read_json


class DecisionBinding(unittest.TestCase):
    def setUp(self):
        self.row = next(r for r in read_json(old.first.PLAN / "panel.json") if r["id"] == "s01")
        self.proposal = next(
            r["proposal"]
            for r in read_json(old.PLAN / "results.json")["records"]
            if r["state"] == "s01"
        )
        self.raw = deepcopy(self.proposal)
        for name, fields in policy.BOUND_FIELDS.items():
            for field in fields:
                del self.raw[name][field]

    def evaluate(self):
        body = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "activate_organization",
                                    "arguments": json.dumps(self.raw),
                                }
                            }
                        ]
                    }
                }
            ]
        }
        return policy.evaluate(self.row, body, old.wire, old.validate, bound=True)

    def test_round_trip_and_source_immutability(self):
        before = deepcopy(self.row)
        compiled, graph = self.evaluate()
        self.assertEqual(compiled, self.proposal)
        self.assertEqual(graph["disposition"], "CHANGE")
        self.assertEqual(self.row, before)

    def test_reject_role_injection(self):
        self.raw["keep"]["owner"] = "member_002"
        with self.assertRaisesRegex(ValueError, "schema"):
            self.evaluate()

    def test_false_product_not_repaired_by_compiler(self):
        self.raw["alternative"]["additional_product"] = "implemented_patch"
        with self.assertRaisesRegex(ValueError, "diagnostic handoff"):
            self.evaluate()

    def test_wrong_package_is_rejected(self):
        self.row["targets"].append("another")
        self.row["graph"]["work"]["another"] = deepcopy(self.row["graph"]["work"]["work_root"])
        self.raw["work"]["package"] = "another"
        with self.assertRaisesRegex(ValueError, "different package"):
            self.evaluate()


if __name__ == "__main__":
    unittest.main()
