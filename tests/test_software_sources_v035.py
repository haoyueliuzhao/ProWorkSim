"""Only new purpose-bound source/world controls; references are not training data."""
import copy
import json
import os
from pathlib import Path

import pytest

from proworksim import software_collaboration_v035 as world
from proworksim import software_tasks_v035 as source
from proworksim.episode import begin_episode, finish_episode
from proworksim.software_context_v034 import SoftwareContextTransport
from proworksim.storage import atomic_write, json_bytes
from test_software_v033 import ScriptedCPUOwner


def output(tmp_path, name):
    return Path(os.environ.get("PROWORKSIM_V035_CONTROL_RUN", str(tmp_path))) / name


@pytest.mark.parametrize("case_id", source.TASK_IDS)
def test_new_purpose_root_actual_joint_and_single_side_programs(tmp_path, case_id):
    root = output(tmp_path, "program-controls/" + case_id)
    results = {}
    for name, files in source.dependency_controls(case_id).items():
        result = source.assess_files(case_id, files, run_root=root / name)
        atomic_write(root / (name + ".json"), json_bytes(result))
        results[name] = result
    assert all(result["executed"] for result in results.values())
    assert {name: result["passed"] for name, result in results.items()} == {
        "original": False, "shared_api_only": False, "consumer_only": False, "joint_reference": True}
    joint = results["joint_reference"]
    assert joint["content_correct"] is joint["required_process_satisfied"] is joint["process_observation_complete"] is True
    assert all(row["passed"] for row in results["shared_api_only"]["independent_acceptance"]["checks"] if row["group"] == "shared_api")
    _, row, _ = source._entry(case_id)
    witnesses = []
    for check in joint["independent_acceptance"]["checks"]:
        if check["group"] != "consumer":
            continue
        observed = check["observed"]
        returns = [event["value"] for event in observed["source_api_trace"]
                   if event["api"] == row["product_api"] and event.get("json_value_recorded") is True]
        assert returns and observed["source_api_used"][row["product_api"]] is True
        witnesses.append({"case_id": check["case_id"], "actual_product_api": row["product_api"],
                          "actual_product_returns": returns, "consumer_output": observed["value"],
                          "calls_observed": observed["source_api_used"], "complete_contract_passed": check["passed"]})
    atomic_write(root / "dependency-witnesses.json", json_bytes({"case_id": case_id, "purpose": source.CASE_PURPOSES[case_id],
        "passed": True, "witnesses": witnesses, "model_calls": 0, "optimizer_eligible": False,
        "scope": "Actual pinned API and reusable product calls plus complete returned-value checks for the joint reference; finite observations, not arbitrary-code causal proof or current-policy support."}))


def test_exact_training_situation_purpose_binding_and_empty_autonomous_worlds(tmp_path):
    root = output(tmp_path, "initial-worlds")
    first = world.build_software_collaboration_case(world.case_spec(source.TRAINING_CASE_ID), root / "first")
    second = world.build_software_collaboration_case(world.case_spec(source.TRAINING_CASE_ID), root / "second")
    assert first.case == second.case
    assert first.prefix["prepared_business_state_sha256"] == second.prefix["prepared_business_state_sha256"]
    for prepared in (first, second):
        proof = world.prove_initial_team(prepared)
        assert proof["initial_task_count"] == 0 and proof["actual_private_work_copies"] == 2
        assert prepared.case["training_eligible"] is prepared.reward_spec["training_supported"] is True
        assert "seed" not in prepared.case and "sampling_seed" not in prepared.case
    for case_id in source.TASK_IDS:
        case = world.case_spec(case_id)
        assert case["purpose"] == case["usage"] == case["split"] == source.CASE_PURPOSES[case_id]
        assert case["training_eligible"] is (case_id == source.TRAINING_CASE_ID)
        changed = copy.deepcopy(case)
        changed.update(purpose="policy_training", usage="policy_training", split="policy_training", training_eligible=True)
        if case_id != source.TRAINING_CASE_ID:
            with pytest.raises(ValueError, match="changed"):
                world.validate_case(changed)
        files = source.build_case(case_id)["files"]
        assert "acceptance.json" not in files and not any(name.startswith("reference/") for name in files)
        changed = copy.deepcopy(files)
        changed["contract.md"] += "\nWeaker requirements\n"
        with pytest.raises(ValueError, match="editable"):
            source._validate_files(case_id, changed)
    for old in ("sqlparse-comparison-records", "schema-catalog", "textfsm-record-items", "mm-directory-rootgoal-v034", "mm-ledger-rootgoal"):
        with pytest.raises(ValueError, match="new purpose-isolated"):
            world.case_spec(old)
    atomic_write(root / "proof.json", json_bytes({"passed": True,
        "training_case": source.TRAINING_CASE_ID, "first_member": "member_a",
        "first_initial_business_sha256": first.prefix["prepared_business_state_sha256"],
        "second_initial_business_sha256": second.prefix["prepared_business_state_sha256"],
        "sampling_seed_in_case": False, "source_partition": source.source_partition(),
        "old_task_relabeling_rejected": True, "model_calls": 0}))


class OneReferenceCPUOwner(ScriptedCPUOwner):
    def __init__(self, directory):
        super().__init__(directory)
        self.window_id = "v035-reference-control-never-training"
        self.facade.transport = SoftwareContextTransport(self, directory)
        files = source.reference_solution(source.TRAINING_CASE_ID)
        self.script = {"member_a": [
            ("create_task", {"task_id": "OwnRoute", "description": "CPU reference witness only, never supplied to the real policy"}),
            ("claim_task", {"task_id": "OwnRoute"}),
            ("write_file", {"path": "reader.py", "text": files["reader.py"]}),
            ("write_file", {"path": "report.py", "text": files["report.py"]}),
            ("run_tests", {}), ("fix_patch", {"task_ids": ["OwnRoute"], "message": "CPU current fixed product"}),
            ("submit_integration", {}), ("staff_done", {"reason": "Explicit reference path ended"})],
            "member_b": [("staff_done", {"reason": "Concentrated completion is legal; no forced contribution"})]}

    def complete(self, request, **kwargs):
        response = super().complete(request, **kwargs)
        observation = next(json.loads(message["content"])["observation"] for message in reversed(request["messages"])
                           if message.get("role") == "user" and "observation" in json.loads(message["content"]))
        name, arguments = self.script[observation["actor_id"]].pop(0)
        response["body"]["choices"][0]["message"]["tool_calls"][0]["function"] = {"name": name, "arguments": json.dumps(arguments)}
        response["raw_body"] = json.dumps(response["body"])
        return response


def test_one_real_sdk_training_source_path_keeps_reference_out_of_learning(tmp_path):
    pytest.importorskip("openhands.sdk")
    from proworksim import software_runtime_v035 as runtime
    root = output(tmp_path, "one-sdk-source-path")
    prepared = world.build_software_collaboration_case(world.case_spec(source.TRAINING_CASE_ID), root / "case")
    owner = OneReferenceCPUOwner(root / "projection")
    rt, captured, _ = runtime.build_runtime(owner.facade, prepared, root / "runtime")
    rt.slot_id = "cpu-source-path-not-a-P2-slot"
    scenario = copy.deepcopy(prepared.scenario)
    scenario.setdefault("variation", {}).update(software_case=copy.deepcopy(prepared.case), cpu_reference_only=True,
        optimizer_update_allowed=False, actor_trajectory_origin="offline_fixture")
    episode = root / "episode"
    before = runtime._capture_slot_guard(owner)
    begin_episode(prepared.world, episode, work_ids=[], experience=rt.recorder.snapshot(), scenario=scenario, policies=rt.policy_identities)
    try:
        boundary = runtime.run_fragment(prepared, rt)
        finish_episode(prepared.world, episode, experience=rt.recorder.snapshot(), termination=boundary)
    finally:
        runtime.close_runtime(rt)
    assessment = world.assess_software_collaboration(prepared, run_root=root / "private-assessment")
    guard = owner.finish_evaluation_guard(before)
    assert assessment["R"] == 1 and assessment["content_correct"] is True
    assert assessment["required_process_satisfied"] is assessment["process_observation_complete"] is True
    assert boundary["execution_integrity_failure"] is None
    assert guard["learning_unchanged"] is guard["rng_restored_exactly"] is True
    budget = boundary["team_budget"]
    assert budget["model"]["decisions"] == budget["model"]["attempts"] == len(owner.requests) == 9
    assert budget["tests"]["used"] == 1
    assert all(status == "completed" for status in boundary["role_stops"].values())
    assert not (root / "entry.json").exists()  # Deliberately no trainable export of a program witness.
    atomic_write(root / "assessment.json", json_bytes(assessment))
    atomic_write(root / "public-capture.json", json_bytes(captured))
    atomic_write(root / "guard.json", json_bytes(guard))
    atomic_write(root / "proof.json", json_bytes({"passed": True, "R": 1, "source_contract_purpose": prepared.case["purpose"],
        "reference_trajectory_origin": "offline_fixture", "optimizer_eligible": False, "training_export_created": False,
        "model_calls": 0, "scripted_cpu_responses": len(owner.requests), "optimizer_steps": 0, "gpu_used": False,
        "budget": budget, "scope": "One actual SDK/world source path only; script choices and synthetic tokens are not current-policy support, actor training material or a new model qualification."}))


def test_source_admission_is_not_actor_target_or_cross_purpose_permission():
    from proworksim.software_mapper_v035 import mapping_spec
    from proworksim.software_runtime_v035 import MODES
    from proworksim.software_training_v035 import source_training_admission
    for case_id in source.TASK_IDS:
        case = world.case_spec(case_id)
        gamma = {"source_usage": case["purpose"], "collection_mode": MODES[case["purpose"]],
                 "optimizer_update_allowed": case["training_eligible"], "mapper_specification": mapping_spec()}
        admission = source_training_admission(case, gamma)
        assert admission["training_eligible"] is (case_id == source.TRAINING_CASE_ID)
        if case_id != source.TRAINING_CASE_ID:
            gamma.update(source_usage="policy_training", collection_mode=MODES["policy_training"], optimizer_update_allowed=True)
            with pytest.raises(ValueError, match="relabeled"):
                source_training_admission(case, gamma)
