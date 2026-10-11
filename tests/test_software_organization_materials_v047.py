"""Small structural controls for the fixed v047 CPU materials program."""

import copy

import pytest

from proworksim.software_organization_v047 import (
    PROJECT,
    build_software_collaboration_case,
    case_spec,
)
from scripts.software_organization_qualification_v047 import (
    material_action,
    material_coverage,
    validate_programmed_request_accounting,
)


def accounting_fixture():
    rows = []
    records = {}
    for call_id in ("completed", "prepared-only"):
        prep = {"preparation_sha256": "sealed-" + call_id, "input_ids_sha256": "ids-" + call_id}
        rows.append(
            {
                "member": "member_001",
                "stage_id": "generate",
                "association": {"call_id": call_id},
                **prep,
            }
        )
        records[call_id] = {
            "member": "member_001",
            "stage_id": "generate",
            "reservation": {"preparation": prep},
        }
    usage = {"prompt_tokens": 123, "completion_tokens": 12, "total_tokens": 135}
    records["completed"].update(
        status="settled",
        attempt_started=True,
        charge={
            "response_id": "reply",
            "usage_status": "reported_actual_trace",
            "reported_usage": usage,
        },
    )
    records["prepared-only"].update(
        status="admission_rejected",
        attempt_started=False,
        budget_kind="stage_budget",
        admission_limits=["stage_max_total_tokens"],
        rejected_reservation=records["prepared-only"]["reservation"],
    )
    responses = [{"response_id": "reply", "usage": usage}]
    return rows, responses, {"records": records}


def test_complete_and_prepared_only_stage_rejection_have_distinct_valid_denominators():
    rows, responses, ledger = accounting_fixture()
    result = validate_programmed_request_accounting(rows, responses, ledger)
    assert result["completed_programmed_responses"] == 1
    assert result["prepared_only_stage_rejections"] == 1
    assert result["requests"][1]["response_id"] is None


@pytest.mark.parametrize(
    "defect",
    ["attempted", "charged", "wrong_member", "wrong_input", "orphan_reply", "duplicate_prepare"],
)
def test_no_other_missing_or_uncertain_material_response_is_relabelled(defect):
    rows, responses, ledger = accounting_fixture()
    row = ledger["records"]["prepared-only"]
    if defect == "attempted":
        row["attempt_started"] = True
    elif defect == "charged":
        row["charge"] = {"charged_tokens": 999}
    elif defect == "wrong_member":
        row["member"] = "member_002"
    elif defect == "wrong_input":
        row["rejected_reservation"] = copy.deepcopy(row["rejected_reservation"])
        row["rejected_reservation"]["preparation"]["input_ids_sha256"] = "other"
    elif defect == "orphan_reply":
        responses.append({"response_id": "orphan", "usage": responses[0]["usage"]})
    else:
        rows.append(copy.deepcopy(rows[0]))
    with pytest.raises(ValueError):
        validate_programmed_request_accounting(rows, responses, ledger)


@pytest.mark.parametrize("condition", ["I4", "P4"])
def test_scripted_native_shape_itinerary_reaches_real_candidates_and_adoption(tmp_path, condition):
    prepared = build_software_collaboration_case(
        case_spec(condition=condition), tmp_path / condition
    )
    world = prepared.world
    measurements, actions = [], []
    while not world.stage_state()["closed"]:
        stage = world.stage_state()["stage_id"]
        for member in list(world.runnable_members()):
            ordinal = 0
            while member in world.runnable_members():
                action = material_action(prepared, member, stage, ordinal)
                call_id = "cpu-" + str(len(measurements))
                association = {"call_id": call_id}
                measurements.append(
                    {"member": member, "stage_id": stage, "association": association}
                )
                actions.append(
                    {
                        "member": member,
                        "stage_id": stage,
                        "association": association,
                        "programmed_action": action,
                    }
                )
                result = world.session(member, PROJECT).call(action["name"], **action["arguments"])
                assert result["ok"], result
                ordinal += 1
                assert ordinal < 8
        assert world.advance_stage()
    coverage = material_coverage(prepared, measurements, actions)
    assert coverage["complete"], coverage
    assert not any(event["kind"] in {"test", "submit"} for event in world.state["software_events"])
    assert all(
        row["changed_paths"] == ["test_member.py"] for row in world._software()["patches"].values()
    )
    # Removing the post-adoption input visibly invalidates coverage; it cannot pass silently.
    last_adopt = next(
        row for row in reversed(actions) if row["programmed_action"]["name"] == "adopt_candidate"
    )
    position = next(
        i for i, row in enumerate(measurements) if row["association"] == last_adopt["association"]
    )
    gap = material_coverage(prepared, measurements[: position + 1], actions[: position + 1])
    assert not gap["complete"]
    assert any("follow-up not measured" in text for text in gap["missing_shapes"])


def test_explicit_material_subset_is_unique_frozen_and_keeps_inventory_order():
    from scripts.software_organization_qualification_v047 import select_route_units
    from scripts.software_organization_v047 import assignments

    inventory = assignments()
    all_units = select_route_units(inventory)
    assert len(all_units) == 44
    ids = ["org47-A-r1-P4-B250000", "org47-B-r1-P4-B500000"]
    selected = select_route_units(inventory, list(reversed(ids)))
    assert [row["slot_id"] for row in selected] == ids
    assert selected == [row for row in all_units if row["slot_id"] in ids]
    assert len(select_route_units(inventory)) == 44


@pytest.mark.parametrize("route_ids", [[], ["known", "known"], ["unknown"], "known"])
def test_material_subset_rejects_empty_duplicate_unknown_or_implicit_string(route_ids):
    from scripts.software_organization_qualification_v047 import select_route_units

    with pytest.raises(ValueError):
        select_route_units({"worker": [{"slot_id": "known"}]}, route_ids)


def test_material_positive_read_is_the_short_file_of_the_next_exact_edit():
    from types import SimpleNamespace

    prepared = SimpleNamespace(
        case={"condition": "I2"}, world=SimpleNamespace(visible_patches=lambda member: [])
    )
    read = material_action(prepared, "member_001", "generate", 0)
    edit = material_action(prepared, "member_001", "generate", 1)
    assert read == {
        "name": "read_file",
        "arguments": {"path": "test_member.py", "start_line": 1, "max_lines": 30},
    }
    assert edit["name"] == "replace_file" and edit["arguments"]["path"] == read["arguments"]["path"]
