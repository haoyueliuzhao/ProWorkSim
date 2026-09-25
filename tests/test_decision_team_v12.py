"""Finite team task: public source contract, real SQL and justified review."""

import copy

from proworksim.domains.decision_team import evaluate_check
from proworksim.templates.decision_team import (
    ROLE_TASKS,
    basis_fixture,
    data_fixture,
    package,
    scenario_spec,
)
from scripts.decision_team_experiment import run_witness


def test_three_real_members_can_request_deliver_execute_and_review(tmp_path):
    result = run_witness(
        tmp_path / "requested", instance="orders_b", layout="split_b", method="requested"
    )
    assert result["status"] == "completed"
    assert result["validity"]["value"] is True
    assert result["capture_matches_retained"] is True
    assert len(result["handoffs"]) == 2
    assert all(
        h["request_id"] and h["origin"] == "member_action" for h in result["handoffs"].values()
    )
    assert all(count >= 2 for count in result["actual_member_actions"].values())
    assert result["model_support"] is False


def test_actual_located_review_repair_preserves_initial_bad_submission(tmp_path):
    result = run_witness(tmp_path / "repair", method="requested", repair=True)
    assert result["status"] == "completed" and result["validity"]["value"] is True
    assert result["issue_id"] and result["submission_id"].endswith("submission-2")
    import json

    state = json.loads((tmp_path / "repair/episode/end/control/state.json").read_text())
    assert [s["review"]["decision"] for s in state["work_items"]["TEAM::build"]["submissions"]] == [
        "withdrawn",
        "accepted",
    ]
    assert len(state["issue_responses"]) == 1


def test_delivery_receipt_does_not_certify_retired_or_wrong_basis():
    spec = package()["works"][0]["deliverable_contract"]["content_checks"][0]
    data = data_fixture("orders_a")
    # Literal oracle independently distinguishes transaction counts from orders.
    output = {
        "tables": {
            "metrics": {
                "columns": [
                    {"name": n, "type": "BIGINT"}
                    for n in ["customer_id", "revenue_cents", "order_count"]
                ],
                "rows": [[1, 1500, 1], [2, 400, 1], [3, 0, 0]],
            }
        }
    }
    sources = {"data": data, "basis": basis_fixture("orders_a")}
    assert evaluate_check(spec, output, sources.__getitem__)["passed"]
    wrong = copy.deepcopy(output)
    wrong["tables"]["metrics"]["rows"][0][2] = 2
    assert evaluate_check(spec, wrong, sources.__getitem__)["passed"] is False
    sources["basis"] = basis_fixture("orders_a", old=True)
    assert (
        evaluate_check(spec, output, sources.__getitem__)["reason"]
        == "chosen_basis_not_approved_for_public_period"
    )


def test_public_role_tasks_do_not_prescribe_private_program_path():
    specs = [
        scenario_spec(instance=instance, layout=layout)
        for instance in ["orders_a", "orders_b"]
        for layout in ["split_a", "split_b"]
    ]
    for spec in specs:
        assert {r["role_id"]: r["config"]["task"] for r in spec["roles"]} == ROLE_TASKS
        assert spec["variation"]["validity_spec"]["blocked_outcome"] == "unknown"
        assert "private_program_schedule" not in spec
