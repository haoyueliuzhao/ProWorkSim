"""Scheduler/SDK checks use explicit CPU scripts, never model support."""

import copy
import json

import pytest

from proworksim.experience import capture_port
from proworksim.software_collaboration_v028 import (
    CASE_IDS, MEMBERS, PROJECT, SoftwareCollaborationPort, build_software_collaboration_case, case_spec,
)
from proworksim.software_runtime_v028 import (
    _validate_window, build_runtime, close_runtime, collect_software_window, run_fragment, situation_id,
)
from proworksim.staff_runtime import StaffRuntime
from test_online_collection_v013 import FakeOwner
from test_software_collaboration_v027 import PATCHES, _combined


def action(name, **arguments):
    return (name, arguments)


def successful_cpu_actions(case_id=CASE_IDS[0], first_member=MEMBERS[0]):
    """Explicit known-code control only, usable for tokenizer/SDK qualification.

    Model experiments must never receive or execute this scripted controller.
    The witness includes advance negotiation, actual waiting/reactivation,
    exact partner import, a further edit, visible tests and independent delivery.
    """
    other = next(member for member in MEMBERS if member != first_member)
    upstream, downstream = (("string_api", "inventory_consumer") if case_id == CASE_IDS[0]
                            else ("whitespace", "casefold"))
    producer = [action("claim_task", task_id=upstream),
                action("send_message", recipient=other, task_id=downstream,
                       body="I will publish the upstream implementation. Please integrate its fixed patch, finish your requirement, test and submit."),
                action("replace_file", **PATCHES[0])]
    if case_id == CASE_IDS[1]:
        producer.append(action("replace_file", **PATCHES[1]))
    producer += [action("fix_patch", task_ids=[upstream], message="CPU witness upstream fixed tree"),
                 action("handoff_patch", patch_id="patch-1", to_member=other, message="Exact upstream patch is ready"),
                 action("staff_done", reason="Upstream CPU witness complete")]
    consumer_patch = PATCHES[1] if case_id == CASE_IDS[0] else {
        "path": PATCHES[0]["path"], "old": PATCHES[0]["new"], "new": _combined()}
    consumer = [action("claim_task", task_id=downstream), action("staff_wait", reason="Wait for upstream fixed patch"),
                action("integrate_patch", patch_id="patch-1"), action("replace_file", **consumer_patch),
                action("fix_patch", task_ids=[downstream], message="CPU witness combined fixed tree"),
                action("run_tests"), action("submit_integration", message="CPU witness completed integration"),
                action("staff_done", reason="CPU witness complete")]
    return {first_member: producer, other: consumer}


class ScriptedSoftwareOwner(FakeOwner):
    """Reusable CPU-only SDK action witness; output token trace is synthetic."""
    def __init__(self, actions, window_id="software-v028-cpu"):
        super().__init__(window_id=window_id)
        self.recipe["max_length"] = 16384
        self.script = actions

    def complete(self, request, **kwargs):
        response = super().complete(request, **kwargs)
        actor = response["body"]["id"].rsplit("-", 1)[0]
        name, arguments = self.script[actor][self.calls[actor] - 1]
        call = response["body"]["choices"][0]["message"]["tool_calls"][0]
        call["function"] = {"name": name, "arguments": json.dumps(arguments)}
        response["body"]["token_trace"]["fixture_only"] = True
        response["raw_body"] = json.dumps(response["body"])
        return response


def cpu_runtime(tmp_path, scripts, *, first=MEMBERS[0], limit=8):
    prepared = build_software_collaboration_case(case_spec(first_member=first,
        role_decision_limits=dict.fromkeys(MEMBERS, limit)), tmp_path / "case")

    class Policy:
        def __init__(self, script):
            self.script = iter(script)

        def decide(self, context):
            name, arguments = next(self.script)
            if name in {"staff_wait", "staff_done"}:
                return {"kind": "wait" if name == "staff_wait" else "done", "reason": arguments["reason"], "memory": {}}
            return {"kind": "act", "action": name, "arguments": arguments, "memory": {}}

    captures = {member: [] for member in MEMBERS}
    ports = {member: capture_port(SoftwareCollaborationPort(prepared.world.session(member, PROJECT), member), captures[member])
             for member in MEMBERS}
    return prepared, StaffRuntime(ports, {member: Policy(scripts[member]) for member in MEMBERS}), captures


def test_wait_message_wakes_without_reset_and_other_member_keeps_turns(tmp_path):
    scripts = {
        MEMBERS[0]: [action("staff_wait", reason="Await negotiation"), action("claim_task", task_id="string_api"), action("staff_done", reason="Done")],
        MEMBERS[1]: [action("send_message", recipient=MEMBERS[0], task_id="string_api", body="Please own API"), action("staff_done", reason="Done")],
    }
    prepared, runtime, _ = cpu_runtime(tmp_path, scripts)
    boundary = run_fragment(prepared, runtime)
    assert boundary["status"] == "workers_done"
    wake = next(event for event in runtime.recorder.events if event["kind"] == "role_reactivated")
    assert wake["payload"]["decisions_already_consumed"] == 1
    assert wake["payload"]["remaining_decisions"] == 7 and wake["payload"]["budget_reset"] is False
    assert runtime.roles[MEMBERS[0]]["opportunities"] == 3
    assert runtime.roles[MEMBERS[1]]["opportunities"] == 2


@pytest.mark.parametrize("trigger", ["delegate_task", "fix_patch"])
def test_responsibility_or_published_patch_wakes_waiting_member(tmp_path, trigger):
    other = [action("claim_task", task_id="string_api")]
    if trigger == "delegate_task":
        other += [action("delegate_task", task_id="string_api", to_member=MEMBERS[0])]
    else:
        other += [action("write_file", path="test_member.py", text="# CPU event wake witness\n"),
                  action("fix_patch", task_ids=["string_api"], message="new fixed artifact")]
    other += [action("staff_done", reason="Done")]
    prepared, runtime, _ = cpu_runtime(tmp_path, {
        MEMBERS[0]: [action("staff_wait", reason="Await new work"), action("staff_done", reason="Event observed")], MEMBERS[1]: other})
    run_fragment(prepared, runtime)
    wake = [event for event in runtime.recorder.events if event["kind"] == "role_reactivated"]
    assert len(wake) == 1 and wake[0]["worker_id"] == MEMBERS[0]


def test_all_waiting_is_terminal_blocked_without_hidden_work(tmp_path):
    scripts = {member: [action("staff_wait", reason="Await partner")] for member in MEMBERS}
    prepared, runtime, _ = cpu_runtime(tmp_path, scripts)
    boundary = run_fragment(prepared, runtime)
    assert boundary["status"] == "blocked_no_reachable_events"
    assert set(boundary["waiting_members"]) == set(MEMBERS)
    assert runtime.opportunities == 2 and runtime.actions == 0
    assert not prepared.world.store.load()["software_events"]


def test_reactivated_member_cannot_exceed_original_limit(tmp_path):
    scripts = {
        MEMBERS[0]: [action("staff_wait", reason="Wait"), action("staff_wait", reason="Wait again")],
        MEMBERS[1]: [action("send_message", recipient=MEMBERS[0], task_id="string_api", body="wake"), action("staff_done", reason="Done")],
    }
    prepared, runtime, _ = cpu_runtime(tmp_path, scripts, limit=2)
    boundary = run_fragment(prepared, runtime)
    assert boundary["role_stops"][MEMBERS[0]] == "model_budget_exhausted"
    assert runtime.roles[MEMBERS[0]]["opportunities"] == 2


def test_done_cannot_be_assigned_new_work_and_first_member_is_respected(tmp_path):
    scripts = {
        MEMBERS[0]: [action("staff_done", reason="Finished permanently")],
        MEMBERS[1]: [action("claim_task", task_id="string_api"), action("delegate_task", task_id="string_api", to_member=MEMBERS[0]), action("staff_done", reason="Done")],
    }
    prepared, runtime, captured = cpu_runtime(tmp_path, scripts, first=MEMBERS[1])
    boundary = run_fragment(prepared, runtime)
    assert boundary["outcomes"][0]["worker_id"] == MEMBERS[1]
    calls = [event for event in captured[MEMBERS[1]] if event["kind"] == "tool_call"]
    assert not calls[-1]["payload"]["response"]["ok"]
    assert runtime.roles[MEMBERS[1]]["opportunities"] == 3
    assert runtime.roles[MEMBERS[0]]["opportunities"] == 1


def test_rejected_arguments_do_not_retire_a_recoverable_member(tmp_path):
    scripts = {
        MEMBERS[0]: [action("claim_task", task_id="string_api", unexpected="invalid"), action("staff_done", reason="Done")],
        MEMBERS[1]: [action("send_message", recipient=MEMBERS[0], task_id="string_api", body="Try again"), action("staff_done", reason="Done")],
    }
    prepared, runtime, captured = cpu_runtime(tmp_path, scripts)
    boundary = run_fragment(prepared, runtime)
    assert boundary["outcomes"][0]["status"] == "policy_error"
    message = next(event for event in captured[MEMBERS[1]] if event["kind"] == "tool_call")
    assert message["payload"]["response"]["ok"]
    assert runtime.roles[MEMBERS[0]]["opportunities"] == 2


def window_spec(first=MEMBERS[0]):
    return {"window_id": "software-v028-cpu", "harness": "openhands_v16", "usage": "interface_dev",
            "mode": "frozen_development", "min_class_count": 2,
            "budget": {"max_slots": 1, "max_model_calls": 16},
            "slots": [{"slot_id": "software-fixture", "case_id": CASE_IDS[0], "sampling_seed": 28,
                       "first_member": first, "role_decision_limits": dict.fromkeys(MEMBERS, 8)}]}


def test_validate_new_budget_and_first_speaker_protocol():
    spec = window_spec()
    assert _validate_window(spec) == spec["slots"]
    invalid = copy.deepcopy(spec)
    invalid["budget"]["max_model_calls"] = 48
    with pytest.raises(ValueError, match="caps"):
        _validate_window(invalid)
    assert situation_id(case_spec()) != situation_id(case_spec(first_member=MEMBERS[1]))


def test_real_sdk_streams_raw_events_and_collects_complete_episode(tmp_path):
    pytest.importorskip("openhands.sdk")
    scripts = {member: [action("staff_done", reason="CPU fixture complete")] for member in MEMBERS}
    owner = ScriptedSoftwareOwner(scripts)
    output = tmp_path / "window"
    entries = collect_software_window(owner, window_spec(MEMBERS[1]), output)
    assert len(entries) == 1
    folder = output / "slot-0"
    events = [json.loads(line) for line in (folder / "experience.jsonl").read_text().splitlines()]
    saved = json.loads((folder / "runtime.json").read_text())
    assert events == saved["experience"]["events"]
    responses = [event for event in events if event["kind"] == "model_response"]
    assert len(responses) == 2
    assert all(event["payload"]["response"]["token_trace"]["fixture_only"] for event in responses)
    capture = json.loads((folder / "public-capture.json").read_text())
    for member in MEMBERS:
        assert [json.loads(line) for line in (folder / "public-capture" / (member + ".jsonl")).read_text().splitlines()] == capture[member]
    boundary = json.loads((folder / "episode/manifest.json").read_text())["termination"]
    assert boundary["first_member"] == MEMBERS[1]
    assert boundary["outcomes"][0]["worker_id"] == MEMBERS[1]
    assert entries[0]["rollout"]["work_validity"]["components"]["record"]["value"] is True
    assert (folder / "entry.json").exists() and (folder / "team-rollout.json").exists()


def test_sdk_stream_exists_before_final_episode_snapshot(tmp_path):
    pytest.importorskip("openhands.sdk")
    owner = ScriptedSoftwareOwner({member: [action("staff_done", reason="CPU fixture")] for member in MEMBERS})
    prepared = build_software_collaboration_case(case_spec(), tmp_path / "case")
    runtime, captured, _ = build_runtime(owner, prepared, tmp_path / "runtime")
    try:
        runtime.step()
        assert (tmp_path / "runtime/experience.jsonl").exists()
        assert (tmp_path / "runtime/public-capture/member_a.jsonl").exists()
        before = (tmp_path / "runtime/public-capture/member_a.jsonl").read_text()
        copy.deepcopy(captured)
        assert (tmp_path / "runtime/public-capture/member_a.jsonl").read_text() == before
    finally:
        close_runtime(runtime)


@pytest.mark.parametrize("case_id,first", [(CASE_IDS[0], MEMBERS[1]), (CASE_IDS[1], MEMBERS[0])])
def test_sdk_positive_witness_closes_real_combined_delivery(tmp_path, case_id, first):
    pytest.importorskip("openhands.sdk")
    owner = ScriptedSoftwareOwner(successful_cpu_actions(case_id, first))
    spec = window_spec(first)
    spec["slots"][0]["case_id"] = case_id
    entries = collect_software_window(owner, spec, tmp_path / "window")
    assert entries[0]["reward"]["reward"] == 1
    assert entries[0]["rollout"]["work_validity"]["value"] is True
    assert entries[0]["mapping"]["status"] == "mapped"
    boundary = json.loads((tmp_path / "window/slot-0/episode/manifest.json").read_text())["termination"]
    assert boundary["outcomes"][0]["worker_id"] == first


def test_interrupted_collector_preserves_original_event_and_all_world_versions(tmp_path, monkeypatch):
    pytest.importorskip("openhands.sdk")
    from proworksim import software_runtime_v028 as module

    owner = ScriptedSoftwareOwner({
        member: [action("write_file", path="test_member.py", text="# Original interrupted action\n")]
        for member in MEMBERS})

    def interrupt_after_effect(prepared, runtime, **kwargs):
        runtime.step()
        raise RuntimeError("Explicit CPU interruption after a committed world edit")

    monkeypatch.setattr(module, "run_fragment", interrupt_after_effect)
    output = tmp_path / "interrupted"
    with pytest.raises(RuntimeError, match="CPU interruption"):
        collect_software_window(owner, window_spec(), output)
    folder = output / "slot-0"
    manifest = json.loads((folder / "episode/manifest.json").read_text())
    assert manifest["status"] == "closed" and manifest["termination"]["status"] == "interrupted"
    assert manifest["termination"]["business_result"] is None
    end = json.loads((folder / "episode/end/control/state.json").read_text())
    assert end["software_events"][0]["kind"] == "edit"
    assert all(entry["availability"] == "available" for entry in manifest["end"]["files"])
    assert (folder / "public-capture.json").exists() and (folder / "runtime.json").exists()
    assert (folder / "experience.jsonl").exists() and not (folder / "entry.json").exists()
    assert json.loads((output / "progress.json").read_text())[0]["R"] is None


def test_sdk_service_failure_keeps_raw_request_and_unknown_business_result(tmp_path):
    pytest.importorskip("openhands.sdk")

    class FailingOwner(ScriptedSoftwareOwner):
        def complete(self, request, **kwargs):
            raise ConnectionError("Explicit CPU service failure after original request construction")

    owner = FailingOwner({})
    output = tmp_path / "window"
    entries = collect_software_window(owner, window_spec(), output)
    entry = entries[0]
    assert entry["reward"]["eligible"] is False and entry["reward"]["reward"] is None
    assert entry["mapping"]["status"] == "unmapped"
    assert entry["rollout"]["work_validity"]["components"]["delivery"]["value"] is None
    folder = output / "slot-0"
    raw = json.loads((folder / "raw-independent-assessment.json").read_text())
    assert raw["status"] == "evaluable" and raw["R"] == 0
    assessment = json.loads((folder / "assessment.json").read_text())
    assert assessment["status"] == "unknown" and assessment["R"] is None
    assert set(assessment["execution_failure"]["role_stops"].values()) == {"model_service_error"}
    events = [json.loads(line) for line in (folder / "experience.jsonl").read_text().splitlines()]
    requests = [event for event in events if event["kind"] == "model_attempt"
                and event["payload"]["stage"] == "started"]
    assert len(requests) == 2 and all(event["payload"]["request"]["messages"] for event in requests)
    assert not any(event["kind"] == "model_response" for event in events)
    assert json.loads((output / "progress.json").read_text())[0]["status"] == "execution_unknown"
