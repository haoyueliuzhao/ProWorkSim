"""Finite host controls for the immutable ten plus unopened fourteen inventory."""

import copy
import hashlib

import pytest

from proworksim.storage import digest
from scripts import software_organization_complete_admission_v045 as admission
from scripts import software_organization_v045 as original


def plan_fixture():
    units = original.assignments()
    return {
        "assignments": units,
        "cases": {
            worker: [
                {
                    **{k: u[k] for k in ("case_id", "condition", "first_member")},
                    "team_limits": dict(admission.TEAM_LIMITS),
                }
                for u in rows
            ]
            for worker, rows in units.items()
        },
    }


def test_original_plan_remaining_order_seeds_and_cases_are_preserved():
    plan = plan_fixture()
    before = copy.deepcopy(plan)
    inventory = admission.remaining_inventory(plan)
    cases = admission.remaining_cases(plan, inventory)
    assert plan == before and sum(map(len, inventory.values())) == 14
    assert inventory["block-r1-s1"] == plan["assignments"]["block-r1-s1"][1:]
    assert cases["block-r1-s1"] == plan["cases"]["block-r1-s1"][1:]
    assert {u["sampling_seed"] for rows in inventory.values() for u in rows} == {
        202610100451,
        202610100452,
    }
    assert admission.budget_caps() == {
        "old_actual": {"decisions": 198, "attempts": 191, "total_tokens": 2563352, "run_tests": 19},
        "new": {"decisions": 1792, "attempts": 1792, "total_tokens": 7000000, "run_tests": 448},
        "combined": {
            "decisions": 1990,
            "attempts": 1983,
            "total_tokens": 9563352,
            "run_tests": 467,
        },
        "old_unused_tokens": 2436648,
        "transfer_old_unused": False,
        "optional_probe_budget_authorized": False,
    }


@pytest.mark.parametrize(
    "fault", ["seed", "order", "first", "budget", "retained", "duplicate", "case"]
)
def test_changed_inventory_or_unused_budget_transfer_rejected(fault):
    plan = plan_fixture()
    row = plan["assignments"]["block-r1-s1"][1]
    retained = admission.RETAINED_IDS
    if fault == "seed":
        row["sampling_seed"] = 202610100442
    elif fault == "order":
        plan["assignments"]["block-r1-s1"][1:] = list(
            reversed(plan["assignments"]["block-r1-s1"][1:])
        )
    elif fault == "first":
        row["first_member"] = "member_002"
    elif fault == "budget":
        plan["cases"]["block-r1-s1"][1]["team_limits"]["max_total_tokens"] += 2436648
    elif fault == "retained":
        retained = retained[:-1]
    elif fault == "duplicate":
        plan["assignments"]["block-r1-s1"][2] = copy.deepcopy(row)
    else:
        plan["cases"]["block-r1-s1"][1]["case_id"] = "other-root"
    with pytest.raises(ValueError):
        admission.remaining_inventory(plan, retained)


def source_fixture(tmp_path, monkeypatch):
    path = tmp_path / "src/model.py"
    path.parent.mkdir()
    content = b"# frozen code\n"
    path.write_bytes(content)
    sha = hashlib.sha256(b"src/model.py" + content).hexdigest()
    monkeypatch.setattr(admission, "ORIGINAL_TREE", sha)
    for name in admission.ALLOWED_NEW_CODE:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("# host addition\n")
    return {
        "source_files": {"src/model.py": digest(content)},
        "source": {"source_tree_sha256": sha},
    }


def test_saved_qualifications_require_old_bytes_and_only_declared_host_additions(
    tmp_path, monkeypatch
):
    plan = source_fixture(tmp_path, monkeypatch)
    assert admission.source_audit(plan, tmp_path)["all_prior_bytes_unchanged"] is True
    (tmp_path / "src/model.py").write_text("# changed model-visible protocol\n")
    with pytest.raises(ValueError, match="prior plan source bytes"):
        admission.source_audit(plan, tmp_path)


def test_undeclared_helper_or_missing_measurement_source_rejected(tmp_path, monkeypatch):
    plan = source_fixture(tmp_path, monkeypatch)
    (tmp_path / "scripts/extra.py").write_text("# undeclared\n")
    with pytest.raises(ValueError, match="nine declared"):
        admission.source_audit(plan, tmp_path)


@pytest.mark.parametrize("phase", [0, 1])
def test_partial_unstarted_slot_in_either_historical_phase_prevents_replay(tmp_path, phase):
    roots = [tmp_path / "first", tmp_path / "resume"]
    inventory = admission.remaining_inventory(plan_fixture())
    assert len(admission.validate_never_started(roots, inventory)) == 14
    path = roots[phase] / "block-r1-s1/actual/episodes/org45-r1-s1-O3"
    path.mkdir(parents=True)
    with pytest.raises(ValueError, match="partial launch"):
        admission.validate_never_started(roots, inventory)


def review_fixture():
    slot = {"slot_id": admission.FIXED_SLOT}
    formal = {"status": "closed", "R": 0, "submitted": False, "complete_delivery": False}
    result = {"slot_id": admission.FIXED_SLOT, **formal, "usage": {"attempts": 1}}
    denominator = {
        "all_saved_feedback_units": 1,
        "protocol_feedback_saved_exactly": 1,
        "with_later_actual_generation": 0,
        "presented_in_later_actual_generation": 0,
        "presented_in_first_actual_followup": 0,
        "without_later_actual_generation": 1,
    }
    record = {
        "feedback_id": "feedback-698",
        "presentation": {"status": "no_actual_followup"},
        "feedback_payload_sha256": "original",
        "no_actual_followup": {"reason": "unknown_no_actual_followup"},
    }
    before = {
        "feedback_records": [record],
        "denominators": denominator,
        "projection_audit": [{"status": "verified", "input": "original"}],
    }
    after = copy.deepcopy(before)
    after.update(
        slot_id=admission.FIXED_SLOT, measurement_gaps=[], mechanism_gate_inputs={"resolved": True}
    )
    after["feedback_records"][0]["no_actual_followup"] = {"reason": "member_fixed_budget"}
    after["feedback_records"][0]["member_fixed_budget_attribution"] = {
        "status": "bound_original_member_fixed_budget",
        "slot_id": admission.FIXED_SLOT,
        "feedback_id": "feedback-698",
        "member_fixed_token_cap": 500000,
        "member_accounted_tokens": 498562,
        "member_available_tokens": 1438,
        "hard_context_headroom_tokens": 1058,
        "charged_tokens": 0,
        "member_remains_stopped": True,
        **{
            k: False
            for k in (
                "attempt_started",
                "actual_output",
                "world_side_effect",
                "later_member_generation",
                "actual_feedback_presentation_added",
                "R_used_for_classification",
            )
        },
    }
    old_stop = {
        "version": "v045-batch-stop-scope-v044r2",
        "decision": "measurement_pending",
        "formal_result": formal,
    }
    stop = {
        **old_stop,
        "slot_id": admission.FIXED_SLOT,
        "decision": "continue",
        "global_violations": [],
        "unresolved": [],
        **{
            k: False
            for k in (
                "R_used_for_scope",
                "restart_current_member",
                "feedback_visibility_changed",
                "model_visible_Gamma_changed",
            )
        },
        **{
            k: 0
            for k in (
                "new_model_calls",
                "new_tokenizer_calls",
                "new_test_or_acceptance_executions",
                "new_world_actions",
            )
        },
    }
    work = {
        "current_program_work": [{"produced": "unknown"}] * 3,
        "pending_semantic_relations": [],
        "cross_member_applicability": "not_applicable_no_partner",
        "recorded_R": 0,
        "recorded_submitted": False,
    }
    revised = {**copy.deepcopy(work), "first_stage_opportunities": [{"preparation": "bound"}]}
    return slot, result, before, old_stop, after, stop, work, revised


def test_only_derived_fixed_budget_reason_changes_without_clearing_structure_unknowns():
    args = review_fixture()
    before = copy.deepcopy(args)
    assert admission.validate_review_slot(*args)["all_saved_feedback_units"] == 1
    assert args == before


@pytest.mark.parametrize(
    "fault",
    [
        "presentation",
        "payload",
        "R",
        "projection",
        "denominator",
        "structure",
        "restart",
        "policy",
        "unresolved",
        "missing_correction",
    ],
)
def test_review_rejects_visibility_outcome_scope_or_structure_reinterpretation(fault):
    args = review_fixture()
    new, stop, work = args[4], args[5], args[7]
    if fault == "presentation":
        new["feedback_records"][0]["presentation"]["status"] = "presented"
    elif fault == "payload":
        new["feedback_records"][0]["feedback_payload_sha256"] = "modified"
    elif fault == "R":
        stop["formal_result"] = {**stop["formal_result"], "R": 1}
    elif fault == "projection":
        new["projection_audit"][0]["input"] = "changed"
    elif fault == "denominator":
        new["denominators"]["presented_in_first_actual_followup"] = 1
    elif fault == "structure":
        work["current_program_work"].clear()
    elif fault == "restart":
        stop["restart_current_member"] = True
    elif fault == "policy":
        stop["version"] = "broader-budget-policy"
    elif fault == "unresolved":
        new["measurement_gaps"] = ["missing proof"]
    else:
        new["feedback_records"] = copy.deepcopy(args[2]["feedback_records"])
    with pytest.raises(ValueError):
        admission.validate_review_slot(*args)


def test_existing_admission_receipt_cannot_be_overwritten(tmp_path):
    path = tmp_path / "saved.json"
    path.write_text("original")
    with pytest.raises(ValueError, match="preserve prior receipt"):
        admission.create_admission("missing", "missing", "missing", path)
    assert path.read_text() == "original"


@pytest.mark.parametrize("fault", ["missing", "charged"])
def test_bound_fixed_refusal_proof_required_for_releasing_remaining_inventory(fault):
    args = review_fixture()
    proof = args[4]["feedback_records"][0]["member_fixed_budget_attribution"]
    if fault == "missing":
        proof.clear()
    else:
        proof["charged_tokens"] = 1
    with pytest.raises(ValueError, match="refusal proof"):
        admission.validate_review_slot(*args)


def test_work_revision_adds_only_unexecuted_prepared_opportunity_and_keeps_s1_applicability():
    old = {
        "cross_member_applicability": "not_applicable_no_partner",
        "has_evidenced_cross_member_chain": None,
        "has_evidenced_cross_member_use": None,
        "has_use_linked_to_final_fixed_delivery": None,
        "pending_program_relations": [{"produced": None}] * 3,
        "current_information_work": [
            {
                "body_sha256": "same",
                "actual_input": {
                    "resource": {
                        "status": "recorded",
                        "later_member_opportunities": 2,
                        "later_member_call_ids": ["a", "b"],
                        "later_member_actual_generations": 2,
                    }
                },
            }
        ],
    }
    new = copy.deepcopy(old)
    for key in (
        "has_evidenced_cross_member_chain",
        "has_evidenced_cross_member_use",
        "has_use_linked_to_final_fixed_delivery",
    ):
        new[key] = False
    resource = new["current_information_work"][0]["actual_input"]["resource"]
    resource["later_member_opportunities"] = 3
    resource["later_member_call_ids"].append("fixed-declined")
    admission.validate_work_revision(old, new, "fixed-declined")
    assert len(new["pending_program_relations"]) == 3
    resource["later_member_actual_generations"] = 3
    with pytest.raises(ValueError, match="generation count changed"):
        admission.validate_work_revision(old, new, "fixed-declined")


@pytest.mark.parametrize("fault", ["wrong_call", "content"])
def test_work_resource_repair_cannot_hide_another_request_or_changed_information(fault):
    old = {
        "cross_member_applicability": "not_applicable_no_partner",
        "current_information_work": [
            {
                "body_sha256": "same",
                "resource": {
                    "status": "recorded",
                    "later_member_opportunities": 0,
                    "later_member_call_ids": [],
                    "later_member_actual_generations": 0,
                },
            }
        ],
    }
    new = copy.deepcopy(old)
    if fault == "wrong_call":
        new["current_information_work"][0]["resource"].update(
            later_member_opportunities=1, later_member_call_ids=["wrong"]
        )
    else:
        new["current_information_work"][0]["body_sha256"] = "changed"
    with pytest.raises(ValueError):
        admission.validate_work_revision(old, new, "fixed-declined")
