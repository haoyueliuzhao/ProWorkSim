"""Runtime scheduling, context isolation and completed-action checkpoints."""

import copy
import json

import pytest

from proworksim.core.world import WorldSpec
from proworksim.experience import capture_port
from proworksim.staff_runtime import StaffRuntime
from proworksim.world_core import WorldCore


class ReaderPolicy:
    config = {}

    def __init__(self):
        self.inputs = []

    def decide(self, context):
        self.inputs.append(copy.deepcopy(context))
        memory = context["memory"]
        if context["last_result"] is not None:
            memory["seen"] = context["last_result"]["result"]["data"]
            return {"kind": "done", "reason": "Read actual material", "memory": memory}
        return {"kind": "act", "action": "read_object", "arguments": {"alias": "material"},
                "memory": memory}


def make_ports(tmp_path):
    world = WorldCore.create(tmp_path / "world", WorldSpec(
        "isolated-contexts", {"alice": {}, "bob": {}, "manager": {}},
        bootstrap_grants=[{"actor_id": "manager", "scope": "world", "power": "install_project"}],
    ))
    captures, ports = {}, {}
    for pid, actor in (("A", "alice"), ("B", "bob")):
        package = {
            "project_id": pid, "goal": "Read only authorized material", "participants": [actor],
            "objects": [{"alias": "material", "filename": "material.json", "kind": "json",
                         "owner": actor, "data": {"private": "private-canary-" + pid}}],
            "works": [],
        }
        assert world.session("manager").call("install_project", package=package)["ok"]
        captures[pid] = []
        ports[pid] = capture_port(world.session(actor, pid), captures[pid])
    return world, ports, captures


def test_contexts_are_separate_and_public_capture_matches_every_actual_return(tmp_path):
    _, ports, captured = make_ports(tmp_path)
    policies = {label: ReaderPolicy() for label in ports}
    runner = StaffRuntime(ports, policies, run_id="separate")
    result = runner.run(max_actions=5, max_opportunities=8)
    assert result["status"] == "completed"
    assert result["actions"] == 2
    assert all(step["action_performed"] in (True, False) for step in result["outcomes"])
    for label, other in (("A", "B"), ("B", "A")):
        assert runner.roles[label]["memory"]["seen"]["private"] == "private-canary-" + label
        assert "private-canary-" + other not in json.dumps(policies[label].inputs)
        recorded = [{"kind": e["kind"], "payload": e["payload"]}
                    for e in runner.recorder.for_worker(label)
                    if e["kind"] in {"public_tools", "public_observation", "tool_call"}]
        assert recorded == captured[label]
    assert [x["worker_id"] for x in result["outcomes"]] == ["A", "B", "A", "B"]


def test_completed_action_checkpoint_keeps_original_returns_and_isolated_progress(tmp_path):
    _, ports, _ = make_ports(tmp_path)
    runner = StaffRuntime(ports, {k: ReaderPolicy() for k in ports}, run_id="resume")
    first = runner.step()
    assert first["action_performed"]
    checkpoint = json.loads(json.dumps(runner.snapshot()))
    prior = copy.deepcopy(checkpoint["experience"]["events"])
    resumed = StaffRuntime(ports, {k: ReaderPolicy() for k in ports}, checkpoint=checkpoint)
    result = resumed.run(max_actions=5, max_opportunities=8)
    assert result["status"] == "completed"
    assert result["total_actions"] == 2
    assert result["experience"]["events"][:len(prior)] == prior
    keys = [e["payload"]["request_key"] for e in result["experience"]["events"]
            if e["kind"] == "tool_call"]
    assert keys == ["staff-resume-1", "staff-resume-2"]
    with pytest.raises(ValueError, match="labels/order"):
        StaffRuntime(dict(reversed(list(ports.items()))), {k: ReaderPolicy() for k in ports}, checkpoint=checkpoint)


def test_policy_error_action_receives_real_refusal_without_runtime_repair(tmp_path):
    world, ports, _ = make_ports(tmp_path)

    class BadPolicy:
        config = {}

        def decide(self, context):
            if context["last_result"] is not None:
                return {"kind": "wait", "memory": context["memory"], "reason": "Cannot proceed"}
            return {"kind": "act", "action": "never_registered", "arguments": {}, "memory": {}}

    before = copy.deepcopy(world.store.load()["artifacts"])
    runner = StaffRuntime({"A": ports["A"]}, {"A": BadPolicy()})
    first = runner.step()
    assert first["status"] == "capability_gap"
    assert first["response"]["ok"] is False
    assert runner.roles["A"]["last_result"] == first["response"]
    assert runner.step()["status"] == "worker_waiting"
    assert runner.actions == 1
    assert world.store.load()["artifacts"] == before


def test_checkpoint_cannot_supply_one_roles_saved_inputs_to_a_new_binding(tmp_path):
    _, ports, _ = make_ports(tmp_path)
    original = StaffRuntime({"worker": ports["A"]}, {"worker": ReaderPolicy()})
    original.step()
    replacement_policy = ReaderPolicy()
    changed = StaffRuntime({"worker": ports["B"]}, {"worker": replacement_policy},
                           checkpoint=original.snapshot())
    assert changed.step()["status"] == "binding_mismatch"
    assert replacement_policy.inputs == []


def test_budget_zero_performs_no_observation_or_action():
    class Inaccessible:
        def tools(self):
            pytest.fail("Zero budget accessed a port")

    runtime = StaffRuntime({"w": Inaccessible()}, {"w": ReaderPolicy()})
    result = runtime.run(max_actions=0, max_opportunities=3)
    assert result["status"] == "budget_exhausted"
    assert result["actions"] == result["opportunities"] == 0
    with pytest.raises(ValueError):
        runtime.run(max_actions=True)


@pytest.mark.parametrize("reserved", ["request_key", "action"])
def test_policy_cannot_override_transport_identity_or_cause_a_false_environment_error(tmp_path, reserved):
    _, ports, capture = make_ports(tmp_path)

    class MalformedPolicy:
        def decide(self, context):
            return {"kind": "act", "action": "wait", "arguments": {reserved: "override"}, "memory": {}}

    runner = StaffRuntime({"A": ports["A"]}, {"A": MalformedPolicy()})
    result = runner.step()
    assert result["status"] == "policy_error"
    assert not result["action_performed"]
    assert not any(event["kind"] == "tool_call" for event in capture["A"])


def test_same_named_different_world_instances_cannot_receive_saved_private_context(tmp_path):
    first_world, first_ports, _ = make_ports(tmp_path / "first")
    second_world, second_ports, _ = make_ports(tmp_path / "second")
    assert first_world.state["world_id"] == second_world.state["world_id"]
    assert first_world.state["instance_id"] != second_world.state["instance_id"]
    first = StaffRuntime({"reader": first_ports["A"]}, {"reader": ReaderPolicy()})
    assert first.step()["action_performed"]
    receiving = ReaderPolicy()
    second = StaffRuntime({"reader": second_ports["A"]}, {"reader": receiving}, checkpoint=first.snapshot())
    assert second.step()["status"] == "binding_mismatch"
    assert receiving.inputs == []
    assert second.recorder.events[-1]["kind"] == "binding_error"
    assert second.recorder.events[-1]["payload"]["policy_invoked"] is False
