"""Exercise both plan comparisons, abstention and immutability without a provider."""

from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_structured_decisions_v237 import PLAN, save
from proworksim.software_structured_policy_v237 import validate, options
from proworksim.storage import read_json


def body(d):
    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {"function": {"name": "activate_organization", "arguments": json.dumps(d)}}
                    ]
                }
            }
        ]
    }


def main():
    r = read_json(PLAN / "panel.json")[0]
    before = deepcopy(r["graph"])
    d = dict(
        assessment=dict(situation="A1", status="open", stage="diagnosis", evidence=["E2", "E4"]),
        work=dict(package="work_root", obligations=["diagnose_failure"]),
        keep=dict(
            owner="member_001",
            verifier="member_002",
            next_step="investigate_failure",
            product="implemented_patch",
            verification="public_test",
            feasible=True,
            progress=[],
            blockers=["E2", "E4"],
            risk="repeat_failure",
            worker_turns=3,
            token_estimate="100k_to_500k",
        ),
        alternative=dict(
            option="D1",
            graph_dimensions=["D2"],
            assignee="member_002",
            additional_product="independent_diagnosis",
            consumer="member_001",
            handoff="one",
            verification="inspect_evidence",
            cost="medium",
            risk="coordination",
        ),
        decision=dict(
            result="CHANGE",
            basis=["E2", "E4"],
            next_step="investigate_failure",
            reconsider_on="new_test_result",
            missing_evidence="none",
        ),
    )
    _, z = validate(r, body(d))
    assert (
        z["dimensions"] == ["D2"]
        and z["schedule"] == ["D7"]
        and z["graph"]["work"] == before["work"]
        and r["graph"] == before
    )
    for choice, missing, step in [
        ("KEEP", "none", "investigate_failure"),
        ("ABSTAIN", "current_test", "inspect_evidence"),
    ]:
        q = deepcopy(d)
        q["decision"].update(result=choice, missing_evidence=missing, next_step=step)
        _, z = validate(r, body(q))
        assert z["graph"] == before and z["disposition"] == choice
    checks = []
    for section, field, value in [
        ("keep", "owner", "member_002"),
        ("keep", "blockers", []),
        ("alternative", "graph_dimensions", ["D2", "D4"]),
        ("alternative", "consumer", "member_002"),
        ("decision", "basis", ["E999"]),
        ("decision", "missing_evidence", "review_receipt"),
    ]:
        q = deepcopy(d)
        q[section][field] = value
        try:
            validate(r, body(q))
        except ValueError:
            checks.append(field)
        else:
            raise AssertionError(field)
    assert options({**r, "available_tokens": 1000}) == {"K": {"op": "keep"}}
    save(
        PLAN / "cpu-controls.json",
        dict(
            Change=True,
            Keep=True,
            Abstain=True,
            graph_source_unchanged=True,
            rejected_mutations=checks,
            underfunded_change_excluded=True,
            provider_calls=0,
        ),
    )


if __name__ == "__main__":
    main()
