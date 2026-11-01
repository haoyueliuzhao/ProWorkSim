"""Real-world CPU controls for artifact handoffs and bounded sprint cycles."""
from __future__ import annotations

from test_organization_governance_v104 import M1, M2, M3, M4, accepted, denied, prepare


def state(prepared, key):
    prepared.world.state = prepared.world.store.load()
    return prepared.world.org_state()[key]


def task(call, task_id="repair"):
    return accepted(call, M1, "create_task", task_id=task_id,
                    description="Change the public fixture value")


def pipeline_candidate(call):
    task(call)
    accepted(call, M1, "org_pipeline_design", task_ids=["repair"], design="Set the public value to one")
    accepted(call, M2, "claim_task", task_id="repair", reason="Accept implementation responsibility")
    accepted(call, M2, "write_file", path="sample.py", text="value = 1\n")
    patch = accepted(call, M2, "fix_patch", task_ids=["repair"], message="Actual implementation")
    accepted(call, M2, "org_pipeline_implementation", patch_id=patch["patch_id"], summary="Value implementation")
    return patch["patch_id"]


def sprint_start(call):
    task(call)
    proposal = accepted(call, M3, "org_sprint_propose", goal="Fix the original public issue", task_ids=["repair"])
    accepted(call, M1, "org_sprint_plan", proposal_revision=proposal["revision"],
             task_ids=["repair"], plan="Implement the value change")
    accepted(call, M2, "org_sprint_plan", proposal_revision=proposal["revision"],
             task_ids=[], plan="Review and support the developer without duplicate ownership")
    accepted(call, M4, "org_sprint_start", proposal_revision=proposal["revision"])
    return proposal


def consume(prepared, count):
    for _ in range(count):
        prepared.world.consume_organization_opportunity(actor=M1)


def test_pipeline_real_handoffs_and_same_candidate_test_gate(tmp_path):
    prepared, _, call, tests = prepare(tmp_path, "PIPELINE")
    denied(call, M1, "submit_integration", message="No design or candidate")
    task(call)
    denied(call, M2, "org_pipeline_design", task_ids=["repair"], design="Wrong role")
    accepted(call, M1, "org_pipeline_design", task_ids=["repair"], design="Value repair")
    assert prepared.world.organization_active_members() == (M2,)
    consume(prepared, 40)
    assert state(prepared, "pipeline")["stage"] == "implementation"
    accepted(call, M2, "claim_task", task_id="repair", reason="Actual accepted ownership")
    accepted(call, M2, "write_file", path="sample.py", text="value = 1\n")
    patch = accepted(call, M2, "fix_patch", task_ids=["repair"], message="Real source")
    accepted(call, M2, "org_pipeline_implementation", patch_id=patch["patch_id"], summary="Hand off")
    denied(call, M3, "org_pipeline_validation", patch_id=patch["patch_id"], conclusion="No execution yet")
    denied(call, M1, "integrate_patch", patch_id=patch["patch_id"])
    accepted(call, M3, "integrate_patch", patch_id=patch["patch_id"])
    accepted(call, M3, "run_tests")
    validated = accepted(call, M3, "org_pipeline_validation", patch_id=patch["patch_id"],
                         conclusion="The public fixture ran; its failure remains disclosed")
    assert validated["validation"]["test"]["executed"] is True
    assert validated["validation"]["test"]["passed"] is False
    accepted(call, M1, "integrate_patch", patch_id=patch["patch_id"])
    accepted(call, M1, "run_tests")
    accepted(call, M1, "fix_patch", task_ids=[], message="Integrated final version")
    accepted(call, M1, "submit_integration", message="Explicit same-version delivery")
    assert len(tests) == 2
    assert len(prepared.world._software()["deliveries"]) == 1


def test_pipeline_changed_task_revision_requires_explicit_return(tmp_path):
    prepared, _, call, _ = prepare(tmp_path, "PIPELINE")
    task(call)
    accepted(call, M1, "org_pipeline_design", task_ids=["repair"], design="Original requirement")
    accepted(call, M2, "claim_task", task_id="repair", reason="Accept task")
    accepted(call, M2, "revise_task", task_id="repair", description="Clarified requirement", expected_revision=1,
             reason="Public requirement needs clarification")
    accepted(call, M2, "write_file", path="sample.py", text="value = 1\n")
    denied(call, M2, "fix_patch", task_ids=["repair"], message="Stale design cannot advance")
    accepted(call, M2, "org_pipeline_return", target_stage="design", reason="Task revision changed")
    renewed = accepted(call, M1, "org_pipeline_design", task_ids=["repair"], design="Clarified design")
    assert renewed["design"]["task_revisions"] == {"repair": 2}
    assert renewed["design_revision"] == 2
    assert state(prepared, "pipeline")["stage"] == "implementation"


def test_pipeline_edit_after_validation_cannot_submit_unvalidated_tree(tmp_path):
    prepared, _, call, _ = prepare(tmp_path, "PIPELINE")
    patch_id = pipeline_candidate(call)
    accepted(call, M3, "integrate_patch", patch_id=patch_id)
    accepted(call, M3, "run_tests")
    accepted(call, M3, "org_pipeline_validation", patch_id=patch_id, conclusion="Actual execution")
    accepted(call, M1, "integrate_patch", patch_id=patch_id)
    accepted(call, M1, "write_file", path="sample.py", text="value = 2\n")
    accepted(call, M1, "run_tests")
    accepted(call, M1, "fix_patch", task_ids=[], message="New unvalidated final code")
    denied(call, M1, "submit_integration", message="Old validation is insufficient")
    accepted(call, M1, "org_pipeline_return", target_stage="implementation", reason="Final integration needs a new candidate")
    assert state(prepared, "pipeline")["validation"] is None
    assert prepared.world._software()["deliveries"] == []


def test_pipeline_equal_content_requires_explicit_handoff_integration(tmp_path):
    prepared, _, call, _ = prepare(tmp_path, "PIPELINE")
    patch_id = pipeline_candidate(call)
    accepted(call, M3, "integrate_patch", patch_id=patch_id)
    accepted(call, M3, "run_tests")
    accepted(call, M3, "org_pipeline_validation", patch_id=patch_id, conclusion="Actual candidate verification")
    accepted(call, M1, "write_file", path="sample.py", text="value = 1\n")
    accepted(call, M1, "run_tests")
    accepted(call, M1, "fix_patch", task_ids=[], message="Matching bytes without handoff adoption")
    denied(call, M1, "submit_integration", message="Equal bytes do not record explicit integration")
    assert prepared.world._software()["deliveries"] == []
    accepted(call, M1, "integrate_patch", patch_id=patch_id)
    accepted(call, M1, "run_tests")
    accepted(call, M1, "fix_patch", task_ids=[], message="Same bytes with actual integrated provenance")
    accepted(call, M1, "submit_integration", message="Explicit handoff and same-version evidence")
    assert len(prepared.world._software()["deliveries"]) == 1


def test_sprint_requires_po_and_both_developers_without_manager_assignment(tmp_path):
    prepared, _, call, _ = prepare(tmp_path, "SPRINT")
    task(call)
    denied(call, M4, "org_sprint_propose", goal="SM cannot rank work", task_ids=["repair"])
    proposal = accepted(call, M3, "org_sprint_propose", goal="Public goal", task_ids=["repair"])
    denied(call, M3, "claim_task", task_id="repair", reason="PO cannot assign self")
    denied(call, M3, "org_sprint_plan", proposal_revision=proposal["revision"], task_ids=["repair"], plan="PO cannot plan for dev")
    accepted(call, M1, "org_sprint_plan", proposal_revision=proposal["revision"], task_ids=["repair"], plan="My work")
    denied(call, M2, "org_sprint_plan", proposal_revision=proposal["revision"], task_ids=["repair"], plan="Duplicate selection")
    denied(call, M4, "org_sprint_start", proposal_revision=proposal["revision"])
    accepted(call, M2, "org_sprint_plan", proposal_revision=proposal["revision"], task_ids=[], plan="Independent review support")
    accepted(call, M4, "org_sprint_start", proposal_revision=proposal["revision"])
    assert state(prepared, "sprint")["phase"] == "active"
    assert prepared.world._software()["tasks"]["repair"]["owner"] is None


def test_sprint_no_candidate_cycle_can_close_truthfully_without_automatic_work(tmp_path):
    prepared, _, call, tests = prepare(tmp_path, "SPRINT")
    sprint_start(call)
    consume(prepared, 24)
    current = state(prepared, "sprint")
    assert current["phase"] == "review" and current["used_opportunities"] == 24
    denied(call, M4, "org_sprint_start", proposal_revision=current["proposal_revision"])
    one = accepted(call, M1, "org_sprint_inspect", conclusion="No fixed candidate was produced")
    two = accepted(call, M2, "org_sprint_inspect", conclusion="The failed cycle produced no fixed artifact")
    closed = accepted(call, M4, "org_sprint_close", review_ids=[one["inspection_id"], two["inspection_id"]],
                      retrospective="Revise the next plan using the observed lack of an artifact")
    assert closed["success_declared"] is False
    assert state(prepared, "sprint")["cycle"] == 2
    assert state(prepared, "sprint")["phase"] == "planning"
    assert tests == [] and prepared.world._software()["patches"] == {}
    assert prepared.world._software()["deliveries"] == []


def test_sprint_public_test_evidence_is_reused_for_same_candidate_without_rerunning(tmp_path):
    prepared, _, call, tests = prepare(tmp_path, "SPRINT")
    sprint_start(call)
    accepted(call, M1, "claim_task", task_id="repair", reason="Take my selected work")
    accepted(call, M1, "write_file", path="sample.py", text="value = 1\n")
    accepted(call, M1, "run_tests")
    patch = accepted(call, M1, "fix_patch", task_ids=["repair"], message="Published sprint result")
    accepted(call, M1, "submit_integration", message="Early delivery does not wait for review")
    consume(prepared, 24)
    denied(call, M1, "org_sprint_inspect", conclusion="Cannot hide the actual candidate")
    one = accepted(call, M1, "org_sprint_inspect", patch_id=patch["patch_id"], conclusion="Public test executed on this version")
    denied(call, M2, "org_sprint_inspect", patch_id=patch["patch_id"], evidence_id="made-up", conclusion="Invalid evidence")
    two = accepted(call, M2, "org_sprint_inspect", patch_id=patch["patch_id"],
                   evidence_id=one["inspection_id"], conclusion="Reviewed the published executed-test receipt")
    closed = accepted(call, M4, "org_sprint_close", review_ids=[one["inspection_id"], two["inspection_id"]],
                      retrospective="Preserve the observed test result and explicit candidate")
    assert len(tests) == 1
    assert closed["inspections"][0]["test"] == closed["inspections"][1]["test"]
    assert closed["inspections"][0]["test"]["passed"] is False
    assert "groups" not in closed["inspections"][0]["test"]


def test_sprint_goal_amendment_preserves_spent_opportunities(tmp_path):
    prepared, _, call, _ = prepare(tmp_path, "SPRINT")
    sprint_start(call)
    consume(prepared, 7)
    denied(call, M3, "org_sprint_propose", goal="Changed target", task_ids=["repair"])
    updated = accepted(call, M3, "org_sprint_propose", goal="Clarified original public goal", task_ids=["repair"],
                       reason="Observed public evidence requires clarification, not deleting requirements")
    assert state(prepared, "sprint")["phase"] == "amendment"
    denied(call, M4, "org_sprint_start", proposal_revision=updated["revision"])
    accepted(call, M1, "org_sprint_plan", proposal_revision=updated["revision"], task_ids=["repair"], plan="Reconfirmed own plan")
    accepted(call, M2, "org_sprint_plan", proposal_revision=updated["revision"], task_ids=[], plan="Reconfirmed supporting plan")
    resumed = accepted(call, M4, "org_sprint_start", proposal_revision=updated["revision"])
    assert resumed["used_opportunities"] == 7
    consume(prepared, 17)
    assert state(prepared, "sprint")["phase"] == "review"
    assert state(prepared, "sprint")["used_opportunities"] == 24
    assert state(prepared, "sprint")["started_cycles"] == 1


def test_sprint_amendment_cannot_pause_or_extend_started_cycle(tmp_path):
    prepared, _, call, _ = prepare(tmp_path, "SPRINT")
    sprint_start(call)
    consume(prepared, 23)
    proposal = accepted(call, M3, "org_sprint_propose", goal="Negotiate clearer public scope",
                        task_ids=["repair"], reason="A bounded negotiation inside the existing cycle")
    assert state(prepared, "sprint")["phase"] == "amendment"
    prepared.world.consume_organization_opportunity(actor=M3)
    current = state(prepared, "sprint")
    assert current["phase"] == "review"
    assert current["used_opportunities"] == 24
    assert current["started_cycles"] == 1
    denied(call, M4, "org_sprint_start", proposal_revision=proposal["revision"])
    denied(call, M3, "org_sprint_propose", goal="Cannot open another negotiation after expiry",
           task_ids=["repair"], reason="This cannot extend the window")
    assert state(prepared, "sprint")["phase"] == "review"
    assert state(prepared, "sprint")["used_opportunities"] == 24
