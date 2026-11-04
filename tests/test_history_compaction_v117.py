"""Lossless observation projection and real SDK-count/transport controls, CPU only."""
import copy
import json
import os
from types import SimpleNamespace

os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
os.environ["OPENHANDS_SUPPRESS_BANNER"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"

import pytest

from proworksim import software_benchmark_history_v117 as history
from proworksim.storage import digest, json_bytes


def observation(index, *, actor="member_001", contract="issue-A", failure=None):
    value = {"role_task": "Stable original coding task " * 200,
             "observation": {"world_id": "world", "instance_id": "fixture__repo-117", "branch_id": "branch",
                 "project_id": "project", "actor_id": actor, "interface_revision": "managed-public",
                 "source_contract_sha256": "a"*64, "initial_binding_sha256": "b"*64, "file_policy_sha256": "c"*64,
                 "contract": {"description": contract, "requirements": "Issue rules "*100},
                 "root_goal": {"description": contract}, "file_directory": [f"source/{i}.py" for i in range(80)],
                 "workspace_reference": {"object_id": "source", "version_id": "v"+str(index)},
                 "team_model_budget": {"available_tokens": 5_000_000-index*500},
                 "current_version_test_coverage": {"version": "v"+str(index), "passed": False, "failure": failure},
                 "delivery_status": {"submitted": False, "version": "v"+str(index)},
                 "messages": [{"private_received": "message "+str(index)}]}}
    return json.dumps(value, ensure_ascii=False)


def request():
    observations = [observation(i, failure="new test failed" if i == 3 else None) for i in range(4)]
    messages = [{"role": "system", "content": "Use the actual managed permissions."}]
    for i, text in enumerate(observations):
        messages.append({"role": "user", "content": text})
        if i < 3:
            messages += [{"role": "assistant", "content": "", "tool_calls": [{"id": f"call-{i}", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]},
                         {"role": "tool", "tool_call_id": f"call-{i}", "content": json.dumps({"ok": False, "error": "actual failure", "source_version": i})}]
    messages.insert(3, {"role": "user", "content": "Derived history summary: uncertain; no new world authority."})
    return {"model": "deepseek-flash", "messages": messages, "max_tokens": 32768, "tools": []}, observations


def test_exact_reconstruction_preserves_current_tools_failures_and_versions():
    original, observations = request()
    retained = copy.deepcopy(original)
    selected, evidence = history.project_observation_history(original, member_id="member_001", registered_observations=observations)
    assert original == retained
    assert len(evidence["rewritten_observations"]) == 3
    assert evidence["validation"]["lossless_same_input_reconstruction"]
    assert len(json_bytes(selected)) < len(json_bytes(original)) * .6
    assert selected["messages"][-1] == original["messages"][-1]
    for before, after in zip(original["messages"], selected["messages"]):
        if before["content"] not in observations:
            assert after == before
    old = json.loads(selected["messages"][1]["content"])
    assert old["observation"]["workspace_reference"]["version_id"] == "v0"
    assert old["observation"]["team_model_budget"]["available_tokens"] == 5_000_000
    assert old["observation"]["current_version_test_coverage"]["passed"] is False
    assert old["observation"]["delivery_status"]["submitted"] is False


@pytest.mark.parametrize("mutate", ["tool_result", "latest_version", "marker_target", "old_failure"])
def test_projection_rejects_forged_result_anchor_or_dynamic_evidence(mutate):
    original, observations = request()
    selected, evidence = history.project_observation_history(original, member_id="member_001", registered_observations=observations)
    if mutate == "tool_result":
        next(m for m in selected["messages"] if m["role"] == "tool")["content"] = "passed"
    elif mutate == "latest_version":
        value = json.loads(selected["messages"][-1]["content"])
        value["observation"]["workspace_reference"]["version_id"] = "fake"
        selected["messages"][-1]["content"] = json.dumps(value)
    else:
        value = json.loads(selected["messages"][1]["content"])
        if mutate == "marker_target":
            value[history.REFERENCE_KEY]["anchor_message_index"] = 0
        else:
            value["observation"]["current_version_test_coverage"]["passed"] = True
        selected["messages"][1]["content"] = json.dumps(value)
    # Updating the outer hash is insufficient to forge the reconstruction proof.
    evidence["selected_request_sha256"] = digest(json_bytes(selected))
    for row in evidence["rewritten_observations"]:
        row["selected_content_sha256"] = digest(selected["messages"][row["message_index"]]["content"].encode())
    with pytest.raises(ValueError):
        history.validate_projection(original, selected, evidence)


def test_no_cross_member_root_or_unregistered_text_compaction():
    texts = [observation(0, actor="member_002"), observation(1, contract="other issue"), observation(2)]
    original = {"messages": [{"role": "user", "content": t} for t in texts]}
    selected, evidence = history.project_observation_history(original, member_id="member_001", registered_observations=texts)
    assert selected == original and not evidence["rewritten_observations"]
    original, texts = request()
    selected, evidence = history.project_observation_history(original, member_id="member_001", registered_observations=texts[-1:])
    assert selected == original and not evidence["rewritten_observations"]


def test_current_real_world_string_contract_and_digest_root_shape():
    texts = []
    for i in range(3):
        value = json.loads(observation(i))
        value["observation"]["contract"] = "Actual public problem statement " * 80
        value["observation"]["root_goal"] = {"sha256": "d"*64, "total_characters": 2400, "read_tool": "read_task"}
        texts.append(json.dumps(value))
    original = {"messages": [{"role": "user", "content": value} for value in texts]}
    selected, evidence = history.project_observation_history(original, member_id="member_001", registered_observations=texts)
    assert len(evidence["rewritten_observations"]) == 2
    assert selected["messages"][-1] == original["messages"][-1]
    assert evidence["validation"]["lossless_same_input_reconstruction"]


def test_sdk_count_and_actual_dispatch_use_identical_compact_wire(tmp_path):
    from openhands.sdk.llm import Message, TextContent
    calls, dispatched = [], []

    class Adapter:
        ledger = SimpleNamespace(token_budget=5_000_000, actual=0, inflight=None)

        def request(self, messages, tools):
            return {"model": "deepseek-flash", "messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools or []), "max_tokens": 32768}

        def count(self, wire):
            calls.append(copy.deepcopy(wire))
            return {"prompt_tokens": len(json_bytes(wire))//4, "method": "scripted-CPU-count-not-provider-tokens"}

    adapter = Adapter()
    def complete(wire, **kwargs):
        dispatched.append(copy.deepcopy(wire))
        return {"http_status": 200, "body": {"id": "scripted", "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11}}}
    owner = SimpleNamespace(adapter=adapter, window_id="cpu-v117", freeze_identity=lambda: {"cpu": True}, transport=SimpleNamespace(complete=complete))
    transport = history.SummarizingManagedContextTransport(owner, tmp_path/"transport")
    texts = [observation(i) for i in range(4)]
    worker = SimpleNamespace(role_id="member_001", transport=transport, meter={"decisions": 0, "budget_accounted_tokens": 0},
        _in_step=False, _observation_texts=texts, _assistant_messages={}, definitions=[],
        _history_trace_v110=SimpleNamespace(assert_healthy=lambda: None))
    transport.bind_observation_source(worker)
    team = SimpleNamespace(snapshot=lambda: {"available_tokens": 5_000_000, "integrity_failure": None, "state_sha256": "x"})
    transport.bind_budget_sources(worker.role_id, meter=worker.meter, team_budget=team, local_limit=5_000_000)
    llm = history.managed_counting_llm_type()(model="openai/deepseek-flash", num_retries=0, stream=False)
    llm._worker = worker
    messages = [Message(role="user", content=[TextContent(text=text)]) for text in texts]
    counted = llm.get_token_count(messages)
    counted_wire = calls[-1]
    original = adapter.request(history.previous._project_messages(messages, worker), [])
    association = {"worker_id": worker.role_id, "call_id": "scripted-1"}
    transport.bind_turn(worker.role_id, association)
    prepared = transport.prepare_for_budget(original)
    assert prepared["prompt_tokens"] == counted
    assert transport._prepared["wire"] == counted_wire
    response = transport.complete(original, timeout_seconds=1)
    assert dispatched == [counted_wire]
    binding = transport.generation_binding(association["call_id"], response)
    assert binding["selected_request"]["messages"] == counted_wire["messages"]
    proof = json.loads((tmp_path/"transport/request-00001/projection.json").read_text())
    assert proof["observation_history_projection"]["validation"]["passed"]
    assert adapter.ledger.actual == 0  # Scripted fixture did not fabricate provider usage.
