"""Real managed SDK with explicitly synthetic CPU response/token fixtures."""

import json

import pytest

from proworksim.software_collaboration_v027 import (
    CASE_IDS, MEMBERS, build_software_collaboration_case, software_collaboration_facts,
)
from proworksim.software_runtime_v027 import build_runtime, close_runtime, collect_software_window
from test_online_collection_v013 import FakeOwner


class SoftwareFixtureOwner(FakeOwner):
    def __init__(self):
        super().__init__(window_id="software-cpu-window")
        self.recipe["max_length"] = 16384

    def complete(self, request, **kwargs):
        response = super().complete(request, **kwargs)
        actor = response["body"]["id"].rsplit("-", 1)[0]
        count = self.calls[actor]
        task = "string_api" if actor == MEMBERS[0] else "inventory_consumer"
        name, arguments = [
            ("claim_task", {"task_id": task}),
            ("read_file", {"path": "consumer.py", "start_line": 1, "max_lines": 20}),
            ("staff_done", {"reason": "Explicit CPU transport fixture complete"}),
        ][count - 1]
        call = response["body"]["choices"][0]["message"]["tool_calls"][0]
        call["function"] = {"name": name, "arguments": json.dumps(arguments)}
        response["body"]["token_trace"]["fixture_only"] = True
        response["raw_body"] = json.dumps(response["body"])
        return response


def spec():
    return {"window_id": "software-cpu-window", "harness": "openhands_v16",
            "usage": "interface_dev", "mode": "frozen_development", "min_class_count": 2,
            "budget": {"max_slots": 1, "max_model_calls": 48},
            "slots": [{"slot_id": "software-fixture", "case_id": CASE_IDS[0], "sampling_seed": 27}]}


def test_software_window_requires_new_explicit_budget_and_development_usage(tmp_path):
    owner = SoftwareFixtureOwner()
    invalid = spec()
    invalid.pop("budget")
    with pytest.raises(ValueError, match="cap"):
        collect_software_window(owner, invalid, tmp_path / "no-budget")
    invalid = spec()
    invalid["usage"] = "policy_train"
    with pytest.raises(ValueError, match="development"):
        collect_software_window(owner, invalid, tmp_path / "train")
    assert owner.calls == {} and not (tmp_path / "no-budget").exists()
    invalid = spec()
    invalid["window_id"] = "some-other-window"
    with pytest.raises(ValueError, match="exact software window"):
        collect_software_window(owner, invalid, tmp_path / "wrong-window")
    assert owner.calls == {} and not (tmp_path / "wrong-window").exists()


def test_actual_sdk_software_gateway_preserves_identity_raw_tokens_and_world_receipts(tmp_path):
    pytest.importorskip("openhands.sdk")
    owner = SoftwareFixtureOwner()
    prepared = build_software_collaboration_case(CASE_IDS[0], tmp_path / "case")
    before = prepared.world.store.load()
    runtime, captured, interfaces = build_runtime(owner, prepared, tmp_path / "runtime")
    try:
        assert owner.calls == {} and prepared.world.store.load() == before
        assert runtime.recorder.events == [] and all(not rows for rows in captured.values())
        assert set(interfaces) == set(MEMBERS)
        assert all(identity["implementation"] == "proworksim.harness_sdk.HarnessWorker"
                   for identity in runtime.policy_identities.values())
        for _ in range(2):
            for _member in MEMBERS:
                step = runtime.step()
                assert step["status"] == "running", step
        for _member in MEMBERS:
            assert runtime.step()["status"] == "completed"
        assert owner.calls == {member: 3 for member in MEMBERS}
        events = runtime.recorder.events
        model_responses = [event for event in events if event["kind"] == "model_response"]
        assert len(model_responses) == 6
        assert all(event["payload"]["response"]["token_trace"]["output_ids"] == [3] for event in model_responses)
        assert all(event["payload"]["response"]["token_trace"]["fixture_only"] for event in model_responses)
        world_calls = [event for event in events if event["kind"] == "tool_call"]
        assert len(world_calls) == 4
        state = prepared.world.store.load()
        for event in world_calls:
            payload = event["payload"]
            assert payload["model_call_id"] and payload["decision_id"]
            response = payload["response"]
            assert state["operation_commits"][response["command_id"]]["public_result"] == response
        facts = software_collaboration_facts(state)
        assert {event["actor_id"] for event in facts["events"]} == set(MEMBERS)
        assert all(captured[member] for member in MEMBERS)
        assert all(runtime.roles[member]["identity"]["actor_id"] == member for member in MEMBERS)
        names = {tool["function"]["name"] for tool in owner.requests[0]["tools"]}
        assert "write_object" not in names and "work_replace_text" not in names
        assert {"write_file", "integrate_patch", "claim_task", "staff_done"} <= names
    finally:
        close_runtime(runtime)


def test_closed_software_collection_exports_fixed_development_evidence(tmp_path):
    pytest.importorskip("openhands.sdk")
    from proworksim.member_views import member_view

    owner = SoftwareFixtureOwner()
    output = tmp_path / "collected"
    entries = collect_software_window(owner, spec(), output)
    assert len(entries) == 1
    assessment = json.loads((output / "slot-0/assessment.json").read_text())
    assert assessment["R"] == 0 and not assessment["submitted"]
    components = entries[0]["rollout"]["work_validity"]["components"]
    assert components["record"]["value"] is True
    assert components["permission"]["value"] is True
    declaration = json.loads((output / "declaration.json").read_text())
    assert declaration["gamma_identity"]["harness"] == "openhands_v16"
    assert declaration["gamma_identity"]["budget"] == spec()["budget"]
    scenario = json.loads((output / "slot-0/model-scenario.json").read_text())
    assert scenario["variation"]["software_case"]["usage"] == "interface_dev"
    assert owner.seeds == [(27, "software-fixture")]
    for member in MEMBERS:
        view = member_view(entries[0]["rollout"], member)
        assert len(view["decisions"]) == 3
        assert all(decision["tokens"]["output_ids"] == [3] for decision in view["decisions"])
    summary = json.loads((output / "summary.json").read_text())
    assert summary["training_eligible"] is False


def test_repeated_situation_keeps_semantic_and_sdk_policy_binding_across_distinct_worlds(tmp_path):
    pytest.importorskip("openhands.sdk")

    class DoneFixtureOwner(FakeOwner):
        def complete(self, request, **kwargs):
            response = super().complete(request, **kwargs)
            call = response["body"]["choices"][0]["message"]["tool_calls"][0]
            call["function"]["name"] = "staff_done"
            response["body"]["token_trace"]["fixture_only"] = True
            response["raw_body"] = json.dumps(response["body"])
            return response

    owner = DoneFixtureOwner(window_id="software-cpu-window")
    owner.recipe["max_length"] = 16384
    window = spec()
    window["budget"] = {"max_slots": 2, "max_model_calls": 96}
    window["slots"] += [{"slot_id": "software-repeat", "case_id": CASE_IDS[0], "sampling_seed": 28}]
    output = tmp_path / "repeated"
    entries = collect_software_window(owner, window, output)
    assert len(entries) == 2 and len(owner.requests) == 4
    declaration = json.loads((output / "declaration.json").read_text())
    first, second = declaration["slots"]
    assert first["xi_fingerprint"] == second["xi_fingerprint"]
    assert first["policies"] == second["policies"]
    assert first["window"]["team_policy_fingerprint"] == second["window"]["team_policy_fingerprint"]
    starts = [json.loads((output / f"slot-{i}/episode/start/control/state.json").read_text()) for i in range(2)]
    assert starts[0]["instance_id"] != starts[1]["instance_id"]
    assert starts[0]["branch_id"] != starts[1]["branch_id"]
    # Installation command IDs and business facts remain in the strict semantic
    # comparison; their deterministic preparation does not split repeated xi.
    assert set(starts[0]["operation_commits"]) == set(starts[1]["operation_commits"])
    preparations = [json.loads((output / f"slot-{i}/preparation.json").read_text()) for i in range(2)]
    assert preparations[0]["prepared_business_state_sha256"] == preparations[1]["prepared_business_state_sha256"]
    assert owner.seeds == [(27, "software-fixture"), (28, "software-repeat")]
