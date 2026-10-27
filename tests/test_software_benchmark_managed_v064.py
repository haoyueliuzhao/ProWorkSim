"""CPU controls for actual aligned resources, controlled tools and evidence."""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_managed_v064 as managed
from proworksim import software_benchmark_world_v064 as world
from proworksim.harness_port import HarnessPort
from proworksim.repository_sources_v054 import capture_repository, tree_manifest
from proworksim.software_benchmark_candidates_v054 import checked, read_episode_candidates
from proworksim.software_benchmark_project_closure_v064 import export_managed_closure, validate_delivery_evidence
from proworksim.software_organization_runtime_v047 import DispatchDeadline
from proworksim.storage import digest, json_bytes
from proworksim.tool_outcomes import ToolRejection


def fixture(tmp_path, budget=7_500_000):
    source = tmp_path / "public"
    source.mkdir()
    (source / "sample.py").write_text("value = 0\n")
    manifest = capture_repository(source, tmp_path / "snapshot", task_id="fixture__aligned-064",
        problem_statement="Keep this exact public issue: change value to 1.",
        source_identity={"instance_id": "fixture__aligned-064", "repo": "fixture/aligned",
                         "base_commit": "a" * 40, "dataset_revision": "b" * 40})
    calls = []
    def public_test(**payload):
        calls.append(copy.deepcopy(payload))
        tree = tree_manifest(payload["files"], payload["entry_metadata"])["tree_sha256"]
        return {"passed": False, "execution": {"executed": True, "input_tree_sha256": tree},
                "groups": {"public": {"status": "failed", "executed": True, "passed": False,
                                      "tests": [{"test_id": "fixture", "passed": False}]}}}
    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    prepared = managed.prepare_case(manifest, tmp_path / "world", max_total_tokens=budget,
        public_test_callback=public_test, deadline=deadline)
    port = HarnessPort(world.SoftwareCollaborationPort(
        prepared.world.session("member_001", world.PROJECT), "member_001"), "member_001", project_id=world.PROJECT,
        public_sink=lambda *_: None, world_sink=lambda *_: None, harness_sink=lambda *_: None)
    return prepared, port, calls, deadline


@pytest.mark.parametrize("budget", sorted(world.BUDGETS))
def test_real_runtime_assembly_binds_all_numeric_gates_and_repaired_tools(tmp_path, budget):
    prepared, port, calls, deadline = fixture(tmp_path, budget)
    before = copy.deepcopy(prepared.world.store.load())
    workers = []
    class InertWorker:
        def __init__(self, member, tools, config, **kwargs):
            self.config, self.definitions, self.kwargs = copy.deepcopy(config), tools, kwargs
            workers.append(self)
        def step(self, *_args, **_kwargs):
            pytest.fail("Assembly cannot sample")
    adapter = SimpleNamespace(limits={"context_limit": 131072}, maximum_input_tokens=98304,
        maximum_output_tokens=32768, model="fixture-model", thinking=True)
    owner = managed.ProjectOwner(adapter, window_id="fixture-slot", identity={"policy_version": "fixture"})
    runtime, _, _ = managed.build_runtime(owner, prepared, tmp_path / "runtime", deadline=deadline,
        public_initial_message=prepared.case["root_goal"] + "\nPublic Python: /fixture/python",
        worker_factory=InertWorker)
    config = workers[0].config
    assert config["max_context_tokens"] == 131072 and config["max_output_tokens"] == 32768
    assert config["timeout_seconds"] == 1800 and config["api_key_env"] is None
    assert config["budget"]["max_total_tokens"] == budget
    assert config["budget"]["max_decisions"] == config["budget"]["max_http_attempts"] == 512
    assert workers[0].kwargs["context_selection"] == "full_history"
    assert runtime.team_budget.snapshot()["limits"]["max_total_tokens"] == budget
    names = {tool["name"] for tool in port.tools()}
    assert {"search_repository", "delivery_status", "create_file", "delete_file", "rename_file"} <= names
    assert not {"bash", "terminal", "spawn_member", "send_message", "handoff_patch"} & names
    assert port.observe()["aligned_resource_allowances"]["max_test_runs"] == 512
    assert calls == [] and prepared.world.store.load() == before


def test_public_test_quota_has_no_old_32_call_cutoff(tmp_path):
    budget = world.TestBudget(tmp_path / "tests.json")
    for _ in range(33):
        budget.consume("member_001")
    assert budget.snapshot()["used"] == 33 and budget.snapshot()["remaining"] == 479
    budget.records = [{}] * 511
    budget.consume("member_001")
    with pytest.raises(ToolRejection):
        budget.consume("member_001")


def test_public_callback_and_dual_endpoints_preserve_actual_version_evidence(tmp_path):
    prepared, port, calls, _ = fixture(tmp_path)
    def call(tool, **arguments):
        value = port.call(tool, request_key=f"call-{len(prepared.world.store.load()['software_events'])}",
                          association={}, **arguments)
        assert value["ok"], value
        return value["result"]
    call("write_file", path="sample.py", text="value = 1\n")
    call("run_tests")
    call("fix_patch", task_ids=[], message="fixed exact publicly tested version")
    call("submit_integration", message="actual same-version delivery")
    call("write_file", path="sample.py", text="value = 2\n")
    closure = export_managed_closure(prepared, tmp_path / "closed",
        slot_id="v064:fixture__aligned-064:QWEN_PROJECT_B7500K:1", sdk_closed=True)
    pair = read_episode_candidates(closure["project_candidate_lock"])
    assert pair["terminal_code"]["files"]["sample.py"] == "value = 2\n"
    assert pair["last_legal_delivery"]["files"]["sample.py"] == "value = 1\n"
    assert len(calls) == 1
    assert calls[0]["request"]["hidden_evaluation"] is False
    assert calls[0]["request"]["source_reference"]["version_id"]
    assert calls[0]["request"]["tree_sha256"] == tree_manifest(calls[0]["files"], calls[0]["entry_metadata"])["tree_sha256"]
    evidence = json.loads(checked(closure["delivery_evidence"]).read_bytes())
    snapshot = json.loads(checked(closure["delivery_snapshot"]).read_bytes())
    baseline = json.loads(checked(closure["baseline_snapshot"]).read_bytes())
    assert validate_delivery_evidence(evidence, snapshot, baseline)["same_tree"] is False
    tampered = copy.deepcopy(evidence)
    tampered["binding"]["public_test_event"]["executed"] = False
    with pytest.raises(ValueError, match="actual member/version/test"):
        validate_delivery_evidence(tampered, snapshot, baseline)


def history():
    messages = [{"role": "system", "content": "Same permitted rules"}]
    for i in range(7):
        messages.append({"role": "user", "content": json.dumps({"observation": {"index": i}})})
        messages.append({"role": "assistant", "content": "", "reasoning_content": f"thought-{i}",
            "tool_calls": [{"id": f"c{i}", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]})
        messages.append({"role": "tool", "tool_call_id": f"c{i}", "content": f"actual-{i}"})
    messages.append({"role": "user", "content": json.dumps({"observation": {"index": 7}})})
    return {"messages": messages, "tools": []}


def counter(per_message):
    return SimpleNamespace(request=lambda messages, tools: {"messages": messages, "tools": tools},
        count=lambda wire: {"prompt_tokens": len(wire["messages"]) * per_message,
                            "method": "programmed CPU count", "request_sha256": digest(json_bytes(wire))})


def test_history_beyond_four_rounds_remains_until_measured_capacity_requires_removal():
    request = history()
    selected, _, projection = managed.project_request(request, adapter=counter(1000), ledger=None, member_id="member_001")
    assert projection["fits"] and projection["removed_indices"] == []
    assert selected == request and len([m for m in selected["messages"] if m["role"] == "assistant"]) == 7
    selected, _, projection = managed.project_request(request, adapter=counter(5000), ledger=None, member_id="member_001")
    assert projection["fits"] and projection["removed_indices"]
    assert selected["messages"][1] == request["messages"][1]
    assert selected["messages"][-1] == request["messages"][-1]
    assert any(m.get("tool_call_id") == "c6" for m in selected["messages"])
    for i, message in enumerate(selected["messages"]):
        if message["role"] == "assistant":
            assert selected["messages"][i + 1]["tool_call_id"] == message["tool_calls"][0]["id"]


def test_request_count_and_admission_are_sealed_not_byte_or_legacy_18k_estimates():
    request = history()
    fake = counter(1000)
    fake.count = lambda wire: {"prompt_tokens": 90000, "method": "programmed", "request_sha256": "wrong"}
    with pytest.raises(ValueError, match="exact complete"):
        managed.project_request(request, adapter=fake, ledger=None, member_id="member_001")
    preparation = {"version": "v064-managed-budget-preparation-r1", "original_request_sha256": digest(json_bytes(request)),
                   "reserved_output_tokens": 32768, "context_limit": 131072, "prompt_tokens": 98304,
                   "fits": True, "count_method": "programmed full wire"}
    preparation["preparation_sha256"] = digest(json_bytes(preparation))
    assert managed.model_reservation(request, preparation)["token_reservation"] == 131072
    preparation["prompt_tokens"] = 98305
    preparation["preparation_sha256"] = digest(json_bytes({k: v for k, v in preparation.items() if k != "preparation_sha256"}))
    with pytest.raises(ValueError, match="contradicts"):
        managed.model_reservation(request, preparation)
