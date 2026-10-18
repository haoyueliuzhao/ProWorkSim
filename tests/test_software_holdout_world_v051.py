"""Independent synthetic HOLD assembly controls; no HOLD business material."""
import copy
import json

import pytest

from proworksim import software_holdout_collector_v051 as collector
from proworksim import software_holdout_world_v051 as world_module
from proworksim.software_context_v048 import SoftwareContextTransport
from proworksim.storage import digest, json_bytes
from test_software_organization_runtime_v038 import CPUOwner, action
from test_software_organization_runtime_v040 import SelectedCPUTransport, tokenize

MEMBERS = world_module.MEMBERS
PROJECT = world_module.PROJECT


class SyntheticProvider:
    """Programmed protocol facts, not actual test execution or real source data."""
    def __init__(self, *, public_passed=True, assessment_known=True):
        self.public_passed = public_passed
        self.assessment_known = assessment_known
        self.manifest_sha256 = digest(b"explicit-synthetic-HOLD-provider")
        self.runner = self
        self.public_calls = []
        self.final_calls = []
        self.files = {"app.py": "value = 0\r\n", "tests/test_app.py": "# synthetic test only\r\n",
                      "LICENSE": "CPU fixture\r\n"}

    def build_case(self, case_id):
        assert case_id == "CPU-hold-interface"
        sha = self.manifest_sha256
        source = {key: sha for key in ("source_manifest_sha256", "source_partition_sha256",
            "requirements_sha256", "public_checks_sha256", "independent_verifier_sha256",
            "public_driver_sha256", "independent_driver_sha256")}
        source.update(source_asset_ids=[case_id], source_revision="CPU-only",
            source_environment="synthetic", source_kind="synthetic_control_only",
            public_requirements="Synthetic task: change value to one.", contract_symbols={},
            complete_delivery_requires=["original_contract", "all_original_tests", "current_tested_fixed_submission"],
            public_production_files=["app.py"], readonly_support_files=["tests/test_app.py", "LICENSE"],
            member_test_file=None, purpose=world_module.PURPOSE, training_eligible=False)
        return {"task_id": case_id, "files": copy.deepcopy(self.files), "editable_paths": ["app.py"],
            "root_goal": source["public_requirements"], "family": "synthetic-HOLD-interface",
            "purpose": world_module.PURPOSE, "training_eligible": False,
            "source_contract": source, "source_partition_sha256": sha,
            "initial_binding": {"initial_files_sha256": digest(json_bytes(self.files)),
                "initial_application_sha256": {"app.py": digest(self.files["app.py"].encode())},
                **{key: source[key] for key in ("source_manifest_sha256", "source_partition_sha256",
                    "public_checks_sha256", "independent_verifier_sha256", "public_driver_sha256", "independent_driver_sha256")}}}

    def validate_files(self, case_id, files):
        assert case_id == "CPU-hold-interface"
        assert set(files) == set(self.files)
        assert all(files[name] == self.files[name] for name in self.files if name != "app.py")

    def run_public_tests(self, case_id, files, *, run_root):
        self.validate_files(case_id, files)
        self.public_calls.append(copy.deepcopy(files))
        passed = self.public_passed
        execution = {"executed": True, "command_executed": True,
                     "scope": "CPU_PROGRAMMED_NO_ACTUAL_TEST_EXECUTION"}
        tests = [{"test_id": "synthetic_original_test", "passed": passed,
                  "observed": {"test_status": "passed" if passed else "failed"},
                  "text": "Synthetic permitted report body " * 260}]
        group = {"status": "passed" if passed else "failed", "executed": True, "passed": passed,
                 "tests": tests, "execution": execution}
        return {"execution": execution, "groups": {"repository_tests": group}, "tests": tests,
                "passed": passed, "public_diagnostics": {}}

    def assess_files(self, case_id, files, *, run_root):
        self.validate_files(case_id, files)
        self.final_calls.append(copy.deepcopy(files))
        known = self.assessment_known
        execution = {"executed": known, "command_executed": known,
                     "scope": "CPU_PROGRAMMED_NO_ACTUAL_TEST_EXECUTION"}
        return {"executed": known, "passed": known, "components": {},
            "purpose": world_module.PURPOSE, "training_eligible": False,
            "content_correct": True if known else None, "required_process_satisfied": True if known else None,
            "process_observation_complete": known, "dimension_checks": [],
            "independent_acceptance": {"checks": [{"case_id": "synthetic_original_test", "passed": True if known else None}],
                                       "execution": execution},
            "public_acceptance": {"execution": execution, "passed": known}}


def prepare(tmp_path, provider=None):
    provider = provider or SyntheticProvider()
    prepared = world_module.build_software_collaboration_case("CPU-hold-interface", tmp_path / "prepared", provider=provider)
    return provider, prepared


def call(world, member, name, **arguments):
    result = world.session(member, PROJECT).call(name, **arguments)
    assert result["ok"], result
    return result["result"]


def test_two_private_trees_and_repository_observation_without_injected_work(tmp_path):
    provider, prepared = prepare(tmp_path)
    world = prepared.world
    assert set(world.store.load()["actors"]) == {"operator", *MEMBERS}
    assert len(world.state["artifacts"]) == 3
    assert world._software()["tasks"] == world._software()["initial_diagnostics"] == {}
    assert world._software()["initial_diagnostic_assignments"] == dict.fromkeys(MEMBERS, [])
    assert provider.public_calls == provider.final_calls == []
    for member in MEMBERS:
        obs = world_module.SoftwareCollaborationPort(world.session(member, PROJECT), member).observe()
        assert obs["purpose"] == world_module.PURPOSE
        assert obs["execution_condition"]["private_working_copies"] == 2
        assert obs["task_formation"]["population"] == "stable_two"
        assert obs["contract"] == provider.build_case(prepared.case["case_id"])["root_goal"]
        assert obs["initial_diagnostics"] == []
        assert set(world._bundle(member)[2]["files"]) == set(provider.files)
        assert not world.session(member, PROJECT).call("write_file", path="tests/test_app.py", text="changed")["ok"]
        assert not {"spawn_member", "retire_member"} & {tool["name"] for tool in world.session(member, PROJECT).tools()}
    call(world, MEMBERS[0], "write_file", path="app.py", text="value = 1\n")
    assert world._bundle(MEMBERS[1])[2]["files"]["app.py"] == provider.files["app.py"]
    own_artifact, own_version, _ = world._bundle(MEMBERS[0])
    reference = world_module.previous.previous.base._reference(own_artifact, own_version)
    with pytest.raises(Exception):
        world._bundle(MEMBERS[1], reference=reference)


def test_partner_fixed_adoption_and_private_paged_test_report(tmp_path):
    provider, prepared = prepare(tmp_path)
    world = prepared.world
    call(world, MEMBERS[0], "write_file", path="app.py", text="value = 1\n")
    report = call(world, MEMBERS[0], "run_tests")
    assert not world.session(MEMBERS[1], PROJECT).call("read_test_result", report_id=report["report_id"], cursor=report["page"]["cursor"])["ok"]
    exact = call(world, MEMBERS[0], "read_test_result", report_id=report["report_id"], cursor=report["page"]["cursor"])
    assert exact["page"] == report["page"] and len(provider.public_calls) == 1
    patch = call(world, MEMBERS[0], "fix_patch", task_ids=[], message="CPU exact shared snapshot")
    call(world, MEMBERS[1], "adopt_candidate", patch_id=patch["patch_id"])
    assert world._bundle(MEMBERS[1])[2]["files"] == world._bundle(MEMBERS[0])[2]["files"]
    assert len(provider.public_calls) == 1 and provider.final_calls == []
    assert world._software()["deliveries"] == []
    call(world, MEMBERS[1], "run_tests")
    assert world.test_budget.snapshot()["used"] == 2
    assert set(world.test_budget.snapshot().get("by_member", {})) <= set(MEMBERS)


def test_fixed_submission_only_assessment_and_unknown_preserved(tmp_path):
    provider, prepared = prepare(tmp_path)
    world = prepared.world
    absent = world_module.assess_software_collaboration(prepared, run_root=tmp_path / "absent")
    assert absent["R"] == 0 and provider.final_calls == []
    assert not hasattr(world_module, "assess_terminal_working_tree")
    call(world, MEMBERS[1], "write_file", path="app.py", text="value = 1\n")
    call(world, MEMBERS[1], "run_tests")
    call(world, MEMBERS[1], "fix_patch", task_ids=[], message="CPU fixed submission")
    delivery = call(world, MEMBERS[1], "submit_integration", message="CPU fixture")
    fixed_files = copy.deepcopy(world._bundle(MEMBERS[1])[2]["files"])
    call(world, MEMBERS[1], "write_file", path="app.py", text="value = 2\n")
    provider.assessment_known = False
    result = world_module.assess_software_collaboration(prepared, run_root=tmp_path / "final")
    assert result["R"] is None and result["status"] == "unknown"
    assert provider.final_calls == [fixed_files]
    assert result["source_reference"] == delivery["source_reference"]


def fixture_owner(script=None, condition="S_star"):
    owner = CPUOwner(script or {})
    owner.path = "project"
    owner.contract = copy.deepcopy(collector.NATIVE_CONTRACT)
    owner.recipe.update(max_length=18432, members=[*MEMBERS, "software_inactive"])
    steps = 4 if condition == "S_star" else 5
    owner.actor_steps = owner.critic_steps = owner.policy_revision = steps
    owner.learning.update(actor_steps=steps, critic_steps=steps)
    authorization = {"checkpoint": {"path": "CPU-no-checkpoint", "sha256": "CPU-fixture", "bytes": 0},
        "actor_identity": {"adapter_sha256": "no-weights", "policy_version": "CPU-" + condition},
        "historical_steps": [steps, steps],
        "state_file_reference_from_original_metadata": {"path": "CPU-no-state", "sha256": "CPU-fixture", "bytes": 0}}
    identity = {"policy_version": "synthetic-no-tensor-cpu-owner", "adapter_sha256": "no-weights",
        "checkpoint": authorization["checkpoint"], "source_actor_identity": authorization["actor_identity"],
        "retained_state_authorization": authorization}
    owner.freeze_identity = lambda: copy.deepcopy(identity)
    owner.prepare_request = lambda request: (json.dumps(request, ensure_ascii=False, sort_keys=True), None, None)
    owner.tokenizer = tokenize
    owner.transport = SelectedCPUTransport(owner)
    return owner, authorization


def test_all_four_loaded_metadata_bindings_and_wrong_condition_refused():
    for condition in collector.CONDITIONS:
        owner, auth = fixture_owner(condition=condition)
        assert collector.validate_loaded_actor(owner, heldout_condition=condition, authorization=auth)["historical_steps"] == auth["historical_steps"]
        bad = copy.deepcopy(auth)
        bad["checkpoint"]["sha256"] = "different"
        with pytest.raises(ValueError):
            collector.validate_loaded_actor(owner, heldout_condition=condition, authorization=bad)
    with pytest.raises(ValueError):
        collector.validate_loaded_actor(owner, heldout_condition="S_star", authorization=auth)


def test_real_sdk_two_sessions_sleep_partner_wake_and_no_terminal_rescue(tmp_path, monkeypatch):
    pytest.importorskip("openhands.sdk")
    provider, prepared = prepare(tmp_path)
    owner, auth = fixture_owner({
        MEMBERS[0]: [action("staff_done", reason="Current work ended"),
                     action("work_note", key="awake", text="Same session received genuine partner work")],
        MEMBERS[1]: [action("work_note", key="private", text="No partner event"),
                     action("send_message", recipient=MEMBERS[0], task_id="root_goal", body="Actual visible partner request")],
    })
    built = []
    original = collector.build_runtime

    def capture_runtime(*args, **kwargs):
        result = original(*args, **kwargs)
        runtime = result[0]
        built.append({"runtime": runtime, "workers": dict(runtime.policies),
                      "conversations": {member: worker.conversation for member, worker in runtime.policies.items()}})
        assert len({id(value) for value in built[-1]["conversations"].values()}) == 2
        assert len({id(worker.team_budget) for worker in runtime.policies.values()}) == 1
        return result

    monkeypatch.setattr(collector, "build_runtime", capture_runtime)
    row = collector.collect_episode(owner, prepared, tmp_path / "collection", sampling_seed=51,
        slot_id="CPU-holdout-two-conversation", heldout_condition="S_star", checkpoint_authorization=auth,
        transport_factory=lambda current, directory: SoftwareContextTransport(current, directory, evidence_kind="cpu_programmed_fixture"))
    runtime = built[0]["runtime"]
    assert runtime.policies == built[0]["workers"]
    assert all(runtime.policies[member].conversation is value for member, value in built[0]["conversations"].items())
    assert row["condition"] == "O1" and row["F"] == row["R_joint"] == 0
    assert row["online_window_id"] == "holdout-v051:CPU-holdout-two-conversation"
    assert row["host_final_evaluation_attempts"] == row["host_final_test_executions"] == 0
    assert "R_code" not in row and "terminal_code" not in row and not row["mutable_terminal_working_tree_assessed"]
    assert provider.public_calls == provider.final_calls == []
    assert owner.phase == "idle" and owner.learning == {"actor_steps": 4, "critic_steps": 4, "backward_calls": 0}
    assert [value["worker_id"] for value in row["boundary"]["outcomes"]][:4] == [MEMBERS[0], MEMBERS[1], MEMBERS[1], MEMBERS[0]]
    assert row["team_budget"]["model"]["limits"] == {"max_decisions": 128, "max_attempts": 128, "max_total_tokens": 500000}
    assert row["team_budget"]["model"]["decisions"] == len(owner.transport.requests) == 6
    assert row["team_budget"]["model"]["charged_tokens"] == sum(body["usage"]["total_tokens"] for body in owner.transport.responses)
    assert all(body["online_window_id"] == row["online_window_id"] for body in owner.transport.responses)
    history = [json.loads(line) for line in (tmp_path / "collection/experience.jsonl").read_text().splitlines()]
    reopened = [event for event in history if event["kind"] == "organization_work_reopened_v049"]
    assert len(reopened) == 1 and reopened[0]["payload"]["same_sdk_conversation"] is True
    assert reopened[0]["payload"]["budget_reset"] is False
    manifest = json.loads((tmp_path / "collection/episode/manifest.json").read_text())
    assert set(manifest["policies"]) == set(MEMBERS)
    assert manifest["scenario"]["variation"]["organization_runtime"]["checkpoint_authorization"] == auth
    for request in owner.transport.requests:
        payload = next(json.loads(message["content"]) for message in reversed(request["messages"])
                       if message["role"] == "user" and '"observation"' in message["content"])
        observation = payload["observation"]
        assert observation["interface_revision"] == world_module.INTERFACE_REVISION
        assert observation["purpose"] == world_module.PURPOSE and observation["initial_diagnostics"] == []
        assert "adopt_candidate" in {tool["function"]["name"] for tool in request["tools"]}
    assert not [event for event in prepared.world.state["software_events"] if event["kind"] == "member_retired"]
