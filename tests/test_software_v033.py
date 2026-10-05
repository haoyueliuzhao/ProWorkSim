"""CPU same-root organization controls; scripted responses are not model results."""
import copy
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_collaboration_v033 as world
from proworksim import software_runtime_v033 as runtime
from proworksim import software_tasks_v030 as original_source
from proworksim.experience import ExperienceRecorder
from proworksim.storage import digest, read_json
from proworksim.team_budget_v033 import SharedTeamBudget
from proworksim.team_rollout import optimizer_scope_allows_update


def checked(port, name, **arguments):
    response = port.call(name, **arguments)
    assert response["ok"], response
    return response["result"]


def ports(prepared):
    return {member: world.SoftwareCollaborationPort(prepared.world.session(member, world.PROJECT), member)
            for member in prepared.case["active_roles"]}


@pytest.mark.parametrize("case_id", world.CASE_IDS)
def test_actual_paired_initial_information_code_contract_and_private_copy_counts(tmp_path, case_id):
    single = world.build_software_collaboration_case(world.case_spec(case_id, condition="S"), tmp_path / "S")
    team = world.build_software_collaboration_case(world.case_spec(case_id, condition="T", first_member="member_b"), tmp_path / "T")
    proof = world.prove_initial_pair(single, team)
    assert proof["single_business_information_equals_team_union"] is True
    assert set(single.world.state["actors"]) == {"member_a", "operator"}
    assert len(single.world.state["artifacts"]) == 2 and len(team.world.state["artifacts"]) == 3
    assert single.case["root_goal"] == team.case["root_goal"]
    source = original_source.build_case(case_id)
    assert source["source_contract"]["independent_verifier_sha256"] == single.case["source_contract"]["independent_verifier_sha256"]
    assert source["source_contract"]["public_checks_sha256"] == single.case["source_contract"]["public_checks_sha256"]
    assert single.case["initial_binding"]["paired_contract_sha256"] != single.case["initial_binding"]["original_contract_sha256"]
    for prepared in (single, team):
        assert world.software_collaboration_facts(prepared)["tasks"] == {}
        assert world.software_collaboration_facts(prepared)["events"] == []
    a, b = ports(team).values()
    checked(a, "write_file", path="test_member.py", text="# A private CPU-controlled edit\n")
    assert "private CPU-controlled" not in checked(b, "read_file", path="test_member.py", start_line=1, max_lines=1)["text"]
    assert not a.call("write_file", path="contract.md", text="Weaker contract")["ok"]
    assert "acceptance.json" not in proof["single_views"]["member_a"]["readable_files_sha256"]


def test_inventory_uses_matched_shared_budgets_and_counterbalanced_conditions():
    rows = runtime.inventory()
    assert len(rows) == 8 and runtime._validate_window(runtime.window_spec("cpu-v033")) == rows
    for seed_index, seed in enumerate(runtime.SAMPLING_SEEDS):
        selected = [row for row in rows if row["sampling_seed"] == seed]
        assert [row["condition"] for row in selected] == (["S", "T", "S", "T"] if seed_index == 0 else ["T", "S", "T", "S"])
        assert all(row["first_member"] == ("member_b" if seed_index == 1 and row["condition"] == "T" else "member_a") for row in selected)
    assert all(row["team_limits"] == {"max_decisions": 128, "max_attempts": 128, "max_total_tokens": 500000, "max_test_runs": 32} for row in rows)
    assert all(set(row["role_decision_limits"].values()) == {128} for row in rows)
    changed = runtime.window_spec("cpu-v033")
    changed["slots"][1]["team_limits"]["max_total_tokens"] = 1000000
    with pytest.raises(ValueError, match="shared team limits"):
        runtime._validate_window(changed)
    assert runtime.window_spec("cpu-v033")["budget"]["max_model_calls"] == 1024


def test_optional_submission_note_never_substitutes_current_tests_or_fixed_version(tmp_path):
    prepared = world.build_software_collaboration_case(world.case_spec(condition="S"), tmp_path / "S")
    a = ports(prepared)["member_a"]
    definition = next(row for row in a.tools() if row["name"] == "submit_integration")
    assert "message" not in definition["parameters"]["required"]
    checked(a, "create_task", task_id="self-chosen", description="A CPU control chooses this work, not the environment")
    checked(a, "claim_task", task_id="self-chosen")
    assert not a.call("submit_integration")["ok"]
    checked(a, "write_file", path="test_member.py", text="# CPU edit before test and fixed publication\n")
    tested = checked(a, "run_tests")
    assert tested["executed"] is True
    assert not a.call("submit_integration")["ok"]
    checked(a, "fix_patch", task_ids=["self-chosen"], message="CPU controlled incomplete delivery")
    submitted = checked(a, "submit_integration")
    assert submitted["message"] == "" and submitted["accepted"] is None
    checked(a, "write_file", path="test_member.py", text="assert True\n")
    assert not a.call("submit_integration")["ok"]
    assert prepared.world.test_budget.snapshot()["used"] == 1


def test_test_resource_cap_is_one_pool_for_both_members(tmp_path, monkeypatch):
    prepared = world.build_software_collaboration_case(world.case_spec(condition="T"), tmp_path / "T")
    a, b = ports(prepared).values()
    def feedback(*args, **kwargs):
        return {"groups": {name: {"status": "passed", "executed": True, "passed": True, "tests": []}
                           for name in ("upstream_regressions", "public_normal")},
                "passed": True, "executed": True, "explicit_cpu_fixture": True}
    monkeypatch.setattr(world, "_public_feedback", feedback)
    monkeypatch.setattr(world.previous, "_member_test_feedback", lambda *args, **kwargs: {
        "status": "untested", "executed": False, "passed": None, "explicit_cpu_fixture": True})
    for index in range(32):
        checked(a if index % 2 == 0 else b, "run_tests")
    rejected = a.call("run_tests")
    assert rejected["ok"] is False
    assert rejected["error"]["rejection"]["code"] == "team_test_budget_exhausted"
    assert prepared.world.test_budget.snapshot()["used"] == 32
    assert len([event for event in world.software_collaboration_facts(prepared)["events"] if event["kind"] == "test"]) == 32


@pytest.mark.parametrize("case_id", world.CASE_IDS)
def test_unchanged_reference_business_and_api_obligations_still_pass_new_assessment(tmp_path, case_id):
    files = original_source.reference_solution(case_id)
    files["contract.md"] = world.material(case_id)["files"]["contract.md"]
    result = world.assess_files(case_id, files, run_root=tmp_path / "private-control")
    assert result["passed"] is result["content_correct"] is result["required_process_satisfied"] is True
    assert result["independent_acceptance"]["fixture_sha256"] == world.case_spec(case_id)["source_contract"]["independent_verifier_sha256"]


def test_content_split_retains_input_preservation_and_separates_only_measured_api_calls():
    expected = {"kind": "return", "value": {"state": {"token": "keep"}}, "input_unchanged": True,
                "source_api_used": {"models.SettingsSchema.load": True, "models.SettingsSchema.dump": True}}
    observed = copy.deepcopy(expected)
    observed["source_api_used"]["models.SettingsSchema.dump"] = False
    independent = {"execution": {"executed": True}, "checks": [{"case_id": "explicit_cpu_fixture", "expected": expected, "observed": observed}]}
    public = {"execution": {"executed": True}, "tests": [{"test_id": "explicit_public_cpu_fixture", "passed": True}]}
    result = world.acceptance_dimensions(independent, public)
    assert result["content_correct"] is True and result["required_process_satisfied"] is False
    observed["input_unchanged"] = False
    assert world.acceptance_dimensions(independent, public)["content_correct"] is False


@pytest.mark.parametrize("condition", ["S", "T"])
def test_scheduler_allows_one_role_the_whole_remaining_pool_and_does_not_retire_format_feedback(tmp_path, condition):
    prepared = world.build_software_collaboration_case(world.case_spec(condition=condition), tmp_path / condition)
    members = prepared.case["active_roles"]
    ledger = SharedTeamBudget(members=members, team_id="explicit-cpu-decision-only", require_exact_resident=False)
    recorder = ExperienceRecorder()
    rt = SimpleNamespace(team_budget=ledger, labels=members, cursor=0, opportunities=0, actions=0,
        roles={member: {"status": "ready", "opportunities": 0} for member in members},
        policies={member: SimpleNamespace(meter={"decisions": 0}) for member in members}, recorder=recorder)
    scheduled = []
    def step():
        member = rt.labels[rt.cursor % len(rt.labels)]
        rt.cursor += 1
        rt.opportunities += 1
        rt.roles[member]["opportunities"] += 1
        rt.policies[member].meter["decisions"] += 1
        ledger.consume_decision(member, "cpu-" + str(rt.opportunities))
        status = "completed" if condition == "T" and member == "member_a" else "model_format_feedback"
        rt.roles[member]["status"] = status
        scheduled.append(member)
        return {"worker_id": member, "status": status, "action_performed": False, "reason": "Explicit CPU scheduler control"}
    rt.step = step
    result = runtime.run_fragment(prepared, rt)
    assert result["team_budget"]["model"]["decisions"] == 128
    assert len(scheduled) == 128
    if condition == "T":
        assert scheduled[0] == "member_a" and scheduled.count("member_b") == 127
    else:
        assert scheduled.count("member_a") == 128
    assert "model_format_error" not in result["role_stops"].values()


class ScriptedCPUOwner:
    """Synthetic tokenizer and sampled IDs for the real SDK/archive glue only."""
    def __init__(self, directory, *, invalid_identity=False):
        import torch
        self.torch, self.device, self.phase, self.busy = torch, "cpu", "collecting", False
        self.window_id = "v033-scripted-cpu"
        self.recipe = {"temperature": .7, "max_output_tokens": 2048, "max_length": 16384,
                       "members": ["member_a", "member_b", "software_inactive"]}
        self.identity = {"version": "shared-actor-identity-v0.13", "policy_version": "explicit-cpu-fixture",
                         "adapter_sha256": digest(b"adapter"), "base_manifest_sha256": digest(b"base"),
                         "inference_profile_sha256": digest(b"profile")}
        self.inference_profile = {"explicit_cpu_fixture": True}
        self.base_identity = {"explicit_cpu_fixture": True}
        self.software_learning_binding = {"explicit_cpu_fixture": True}
        self.invalid_identity, self.requests, self.seeds, self.calls = invalid_identity, [], [], Counter()
        from proworksim.software_context_v028 import SoftwareContextTransport
        self.transport = SimpleNamespace(complete=self.complete)
        class Facade:
            def __init__(self, owner):
                self.owner = owner
                self.transport = SoftwareContextTransport(owner, directory)
            def __getattr__(self, name):
                return getattr(self.owner, name)
        self.facade = Facade(self)
    def freeze_identity(self):
        return copy.deepcopy(self.identity)
    def prepare_request(self, request):
        return json.dumps(request, sort_keys=True), request["messages"], {"scope": "synthetic CPU serializer, not any real model tokenizer"}
    def tokenizer(self, text, **kwargs):
        return {"input_ids": [sum(map(ord, text[index:index + 16])) for index in range(0, len(text), 16)]}
    def reseed(self, seed, *, label):
        self.torch.manual_seed(seed)
        self.seeds.append((seed, label))
    def _state_bundle(self):
        return {"actor": {"cpu_fixture": 1}, "critic": {"cpu_fixture": 2},
                "actor_optimizer": {}, "critic_optimizer": {}, "policy_revision": 0,
                "actor_steps": 0, "critic_steps": 0, "critic_has_nonzero_reward_history": False,
                "rng_cpu": self.torch.get_rng_state(), "rng_cuda": []}
    def capture_evaluation_state(self):
        from proworksim.online_training import SharedActor
        return SharedActor.capture_evaluation_state(self)
    def finish_evaluation_guard(self, snapshot):
        from proworksim.online_training import SharedActor
        return SharedActor.finish_evaluation_guard(self, snapshot)
    def complete(self, request, **kwargs):
        self.requests.append(copy.deepcopy(request))
        observed = next(json.loads(message["content"])["observation"] for message in reversed(request["messages"])
                        if message["role"] == "user" and "observation" in json.loads(message["content"]))
        member = observed["actor_id"]
        self.calls[member] += 1
        rendered, _, _ = self.prepare_request(request)
        inputs = self.tokenizer(rendered)["input_ids"]
        identity = self.freeze_identity()
        if self.invalid_identity:
            identity["adapter_sha256"] = "changed-identity-cpu-negative-control"
        cid = "explicit-cpu-response-" + str(len(self.requests))
        body = {"id": cid, "model": "shared-local-actor", "system_fingerprint": self.identity["policy_version"],
            "actor_identity": identity, "online_window_id": self.window_id,
            "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "tool-" + cid,
                "type": "function", "function": {"name": "staff_done", "arguments": '{"reason":"Explicit CPU archival control"}'}}]}, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": len(inputs), "completion_tokens": 1, "total_tokens": len(inputs) + 1},
            "token_trace": {"input_ids": inputs, "output_ids": [7], "input_mask": [0] * len(inputs), "output_mask": [1],
                "behavior_logprobs": [-.5], "sampling_temperature": .7, "sampling_top_p": 1.0, "sampling_top_k": 0,
                "fixture_only": True, "source": "actual generation token IDs and sampling logits, not retokenized text",
                "fixture_disclaimer": "Synthetic CPU token provenance control; no model is constructed or sampled"}}
        return {"http_status": 200, "body": body, "raw_body": json.dumps(body)}


def test_real_sdk_eight_slot_capture_preserves_shared_accounting_and_forbids_training(tmp_path):
    pytest.importorskip("openhands.sdk")
    owner = ScriptedCPUOwner(tmp_path / "projection")
    entries = runtime.collect_software_window(owner.facade, runtime.window_spec(owner.window_id), tmp_path / "window")
    assert len(entries) == 8 and len(owner.requests) == 12
    assert owner.seeds == [(row["sampling_seed"], row["slot_id"]) for row in runtime.inventory()]
    assert len(read_json(tmp_path / "window/initial-pair-proofs.json")) == 4
    progress = read_json(tmp_path / "window/progress.json")
    assert len(progress) == 8
    for entry, row in zip(entries, progress, strict=True):
        assert not optimizer_scope_allows_update(entry["rollout"])
        assert row["record_validity"] is True and row["R"] == 0 and row["complete_delivery"] is False
        assert row["content_correct"] is None and row["required_process_satisfied"] is None
        budget = row["team_budget"]["model"]
        assert budget["decisions"] == (1 if row["condition"] == "S" else 2)
        assert budget["attempts"] == budget["decisions"] and budget["held_tokens"] == 0
        assert all(record["charge"]["usage_status"] == "reported_actual_trace" for record in budget["records"].values())
        assert row["team_budget"]["tests"]["used"] == 0
        evidence = read_json(Path(row["entry"]["path"]).parent / "software-evidence.json")
        assert all(view["complete_actor_trajectory"] and view["own_action_tokens"] == 1 for view in evidence["member_views"].values())
        responses = [event["payload"]["response"] for event in entry["rollout"]["events"] if event["kind"] == "model_response"]
        assert len(responses) == len(entry["active_members"])
        assert all(response["token_trace"]["output_ids"] == [7] for response in responses)


def test_integrity_failure_stops_remaining_window_and_never_becomes_zero_score(tmp_path):
    pytest.importorskip("openhands.sdk")
    owner = ScriptedCPUOwner(tmp_path / "projection", invalid_identity=True)
    output = tmp_path / "window"
    with pytest.raises(ValueError):
        runtime.collect_software_window(owner.facade, runtime.window_spec(owner.window_id), output)
    assert len(owner.requests) == 1
    progress = read_json(output / "progress.json")
    assert len(progress) == 1 and progress[0]["R"] is None
    assert (output / "slot-0/interruption.json").exists()
    assert not (output / "slot-1/episode/manifest.json").exists()


@pytest.mark.parametrize("code,critical", [
    ("world_power_denied", True), ("project_power_denied", True),
    ("trusted_context_override", True), ("public_argument_schema", False),
])
def test_declared_permission_boundaries_block_whole_episode_but_schema_can_recover(tmp_path, code, critical):
    prepared = world.build_software_collaboration_case(world.case_spec(condition="T"), tmp_path / "T")
    members = prepared.case["active_roles"]
    ledger = SharedTeamBudget(members=members, team_id="explicit-cpu-authority-control", require_exact_resident=False)
    rt = SimpleNamespace(team_budget=ledger, labels=members, cursor=0, opportunities=0, actions=0,
        roles={member: {"status": "ready", "opportunities": 0} for member in members},
        policies={member: SimpleNamespace(meter={"decisions": 0}) for member in members}, recorder=ExperienceRecorder())
    def step():
        member = rt.labels[rt.cursor % len(rt.labels)]
        rt.cursor += 1
        rt.opportunities += 1
        rt.roles[member]["opportunities"] += 1
        rt.policies[member].meter["decisions"] += 1
        ledger.consume_decision(member, "authority-cpu-" + str(rt.opportunities))
        status = "policy_error" if rt.opportunities == 1 else "completed"
        rt.roles[member]["status"] = status
        return {"worker_id": member, "status": status, "action_performed": True,
                "response": {"ok": False, "error": {"rejection": {"code": code}}} if rt.opportunities == 1 else {"ok": True}}
    rt.step = step
    result = runtime.run_fragment(prepared, rt)
    assert result["status"] == ("execution_integrity_blocked" if critical else "workers_done")
    assert rt.opportunities == (1 if critical else 3)
    assert bool(result["execution_integrity_failure"]) is critical


def test_collecting_slot_guard_preserves_real_owner_idle_capture_contract(tmp_path):
    owner = ScriptedCPUOwner(tmp_path / "projection")
    with pytest.raises(ValueError, match="idle"):
        owner.capture_evaluation_state()
    snapshot = runtime._capture_slot_guard(owner)
    assert owner.phase == "collecting" and owner.busy is False
    guard = owner.finish_evaluation_guard(snapshot)
    assert guard["learning_unchanged"] is True and guard["rng_restored_exactly"] is True
    owner.busy = True
    with pytest.raises(ValueError, match="no operation in flight"):
        runtime._capture_slot_guard(owner)


def test_context_preflight_capacity_remains_a_normal_bounded_role_stop():
    rt = SimpleNamespace(policies={"member_a": SimpleNamespace(meter={"decisions": 1})},
                         roles={"member_a": {"status": "model_budget_exhausted", "opportunities": 1}})
    event = {"sequence": 4, "worker_id": "member_a", "kind": "model_boundary_error", "payload": {
        "budget_kind": "context_capacity", "limits": ["context_capacity"]}}
    detail = runtime._terminal_detail("member_a", {"status": "model_budget_exhausted"}, rt, [event])
    assert detail["cause"] == "context_capacity" and detail["generation_started"] is False
    assert detail["limits"] == ["context_capacity"]
