"""Finite strict O1 lifecycle and loaded-state controls; all outputs are CPU fixtures."""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim import software_organization_runtime_v049 as runtime_module
from proworksim.software_context_v048 import SoftwareContextTransport
from proworksim.software_organization_v049 import (
    CASE_IDS, PROJECT, SoftwareCollaborationPort, build_software_collaboration_case,
    case_spec, material,
)
from test_software_organization_runtime_v038 import CPUOwner, ScriptedWorker, action
from test_software_organization_runtime_v040 import SelectedCPUTransport, tokenize

MEMBERS = ("member_001", "member_002")


def scripted(tmp_path, script, *, first_member=MEMBERS[0]):
    prepared = build_software_collaboration_case(case_spec(CASE_IDS[0], first_member=first_member), tmp_path / "prepared")
    owner = CPUOwner(script)
    owner.begin_window("v049-o1-learning-window-01")
    owner.transport = SimpleNamespace(script=script, feedback_ledger=SimpleNamespace(snapshot=lambda: {}))
    runtime, capture, interfaces = runtime_module.build_runtime(
        owner, prepared, tmp_path / "runtime", worker_factory=ScriptedWorker)
    return owner, prepared, runtime, capture, interfaces


def test_initial_members_equal_tasks_empty_and_exit_tools_unavailable(tmp_path):
    _, prepared, runtime, _, interfaces = scripted(tmp_path, {})
    try:
        assert list(prepared.world._software()["registry"]) == list(MEMBERS)
        assert prepared.world._software()["tasks"] == {}
        assert all(row["status"] == "live" and row["briefing"] == ""
                   for row in prepared.world._software()["registry"].values())
        for member, interface in interfaces.items():
            obs = interface.observe()
            assert obs["actor_id"] == member
            assert obs["execution_condition"]["stable_members"]
            assert obs["task_formation"]["level"] == "O1"
            assert obs["task_formation"]["population"] == "stable_two"
            assert not {"spawn_member", "retire_member"} & {row["name"] for row in interface.tools()}
            assert obs["scheduling"]["done"].startswith("End current work")
        before = copy.deepcopy(prepared.world._software()["registry"])
        session = prepared.world.session(MEMBERS[0], PROJECT)
        for name, args in (action("spawn_member", briefing="No birth"), action("retire_member", reason="No exit")):
            assert session.call(name, **args)["ok"] is False
        assert prepared.world._software()["registry"] == before
        assert prepared.world._software()["tasks"] == {}
    finally:
        runtime_module.close_runtime(runtime)


def test_done_sleeps_preserving_responsibility_and_private_event_does_not_wake(tmp_path):
    _, prepared, runtime, _, _ = scripted(tmp_path, {
        MEMBERS[0]: [action("staff_done", reason="My present work is done"),
                     action("work_note", key="awake", text="I received new work")],
        MEMBERS[1]: [action("work_note", key="private", text="Does not wake anyone"),
                     action("send_message", recipient=MEMBERS[0], task_id="root_goal", body="Actual new request")],
    })
    session = prepared.world.session(MEMBERS[0], PROJECT)
    assert session.call("create_task", task_id="chosen", description="Self chosen responsibility")["ok"]
    assert session.call("claim_task", task_id="chosen")["ok"]
    try:
        before_workers = dict(runtime.policies)
        boundary = runtime_module.run_fragment(prepared, runtime)
        assert [row["worker_id"] for row in boundary["outcomes"]][:4] == [MEMBERS[0], MEMBERS[1], MEMBERS[1], MEMBERS[0]]
        assert runtime.policies == before_workers
        assert prepared.world._software()["tasks"]["chosen"]["owner"] == MEMBERS[0]
        assert all(row["status"] == "live" for row in prepared.world._software()["registry"].values())
        assert not [row for row in prepared.world.state["software_events"] if row["kind"] == "member_retired"]
        assert runtime.ports[MEMBERS[0]].notes["awake"] == "I received new work"
        wakes = [row for row in runtime.recorder.events if row["kind"] == "role_reactivated"]
        assert len(wakes) == 1 and wakes[0]["payload"]["budget_reset"] is False
        assert runtime.team_budget.snapshot()["decisions"] == len(boundary["outcomes"]) == 6
    finally:
        runtime_module.close_runtime(runtime)


@pytest.mark.parametrize("control", ["staff_done", "staff_wait"])
def test_two_sleepers_close_without_generated_events_or_retirement(tmp_path, control):
    _, prepared, runtime, _, _ = scripted(tmp_path, {member: [action(control, reason="No pending work")] for member in MEMBERS})
    before = copy.deepcopy(prepared.world.state["software_events"])
    try:
        boundary = runtime_module.run_fragment(prepared, runtime)
        assert boundary["opportunities"] == 2
        assert boundary["closure_reason"] == "all_members_stopped_or_no_reachable_event"
        assert boundary["role_stops"] == {}
        assert set(boundary["waiting_members"]) == set(MEMBERS)
        assert prepared.world.state["software_events"] == before
        assert all(row["status"] == "live" for row in prepared.world._software()["registry"].values())
        assert not [row for row in runtime.recorder.events if row["kind"] == "role_reactivated"]
    finally:
        runtime_module.close_runtime(runtime)


def test_public_fixed_patch_can_wake_same_member(tmp_path):
    path = next(p for p in material(CASE_IDS[0])["editable_paths"] if p != "test_member.py")
    _, prepared, runtime, _, _ = scripted(tmp_path, {
        MEMBERS[0]: [action("staff_done", reason="Sleep until real public work")],
        MEMBERS[1]: [action("write_file", path=path, text=material(CASE_IDS[0])["files"][path] + "\n# fixture\n"),
                     action("fix_patch", task_ids=[], message="A real fixed fixture patch")],
    })
    try:
        boundary = runtime_module.run_fragment(prepared, runtime)
        order = [row["worker_id"] for row in boundary["outcomes"]]
        assert order[:4] == [MEMBERS[0], MEMBERS[1], MEMBERS[1], MEMBERS[0]]
        assert len([row for row in runtime.recorder.events if row["kind"] == "role_reactivated"]) == 1
        assert len(prepared.world._software()["registry"]) == 2
    finally:
        runtime_module.close_runtime(runtime)


@pytest.mark.parametrize("status", ["model_context_exhausted", "model_budget_exhausted", "team_budget_exhausted"])
def test_terminal_unavailable_session_never_revives(tmp_path, status):
    _, prepared, runtime, _, _ = scripted(tmp_path, {})
    try:
        runtime.waiting[MEMBERS[0]] = 0
        runtime.work_ended[MEMBERS[0]] = {"reason": "fixture previous end"}
        session = prepared.world.session(MEMBERS[1], PROJECT)
        assert session.call("send_message", recipient=MEMBERS[0], task_id="root_goal", body="Visible before stop")["ok"]
        runtime.stopped[MEMBERS[0]] = status
        runtime_module._wake_reachable(runtime)
        assert MEMBERS[0] in runtime.waiting and runtime.stopped[MEMBERS[0]] == status
        assert not runtime.availability()[MEMBERS[0]]["can_receive_work"]
        assert prepared.world._software()["registry"][MEMBERS[0]]["status"] == "live"
        assert not [row for row in runtime.recorder.events if row["kind"] == "role_reactivated"]
    finally:
        runtime_module.close_runtime(runtime)


def sdk_owner(script):
    pytest.importorskip("openhands.sdk")
    owner = CPUOwner(script)
    owner.recipe.update(max_length=18432, members=[*MEMBERS, "software_inactive"])
    owner.actor_steps, owner.critic_steps, owner.policy_revision = 4, 4, 4
    owner.learning.update(actor_steps=4, critic_steps=4)
    owner.prepare_request = lambda request: (json.dumps(request, ensure_ascii=False, sort_keys=True), None, None)
    owner.tokenizer = tokenize
    owner.transport = SelectedCPUTransport(owner)
    return owner


def fixture_transport(owner, directory):
    return SoftwareContextTransport(owner, directory, evidence_kind="cpu_programmed_fixture")


def test_real_sdk_done_wake_generates_again_with_same_history_and_meters(tmp_path, monkeypatch):
    owner = sdk_owner({
        MEMBERS[0]: [action("staff_done", reason="Present work done"), action("work_note", key="resumed", text="After real message")],
        MEMBERS[1]: [action("send_message", recipient=MEMBERS[0], task_id="root_goal", body="New actual request")],
    })
    monkeypatch.setattr(runtime_module, "_capture_slot_guard", lambda current: copy.deepcopy(current.learning))
    owner.begin_window("v049-o1-learning-window-01")
    prepared = build_software_collaboration_case(case_spec(CASE_IDS[0]), tmp_path / "prepared")
    row = runtime_module.collect_episode(owner, prepared, tmp_path / "episode-output", sampling_seed=49,
        slot_id="v049-explicit-cpu-training", manage_owner_window=False,
        transport_factory=fixture_transport, learning_binding={"branch": "loaded-new-state"})
    assert row["R"] == 0 and row["training_eligible"] is True
    assert row["usage"]["attempts"] == len(owner.transport.requests) == 5
    assert owner.transport.calls[MEMBERS[0]] == 3
    assert owner.phase == "collecting" and owner.window_id == "v049-o1-learning-window-01"
    assert row["episode_start_steps"] == {"actor_steps": 4, "critic_steps": 4, "policy_revision": 4}
    assert owner.learning["actor_steps"] == owner.learning["critic_steps"] == 4
    manifest = json.loads((tmp_path / "episode-output/episode/manifest.json").read_text())
    scope = manifest["scenario"]["variation"]["organization_runtime"]
    assert scope["training_eligible"] is True and scope["online_window_id"] == owner.window_id
    assert all(body["online_window_id"] == owner.window_id for body in owner.transport.responses)
    history = [json.loads(line) for line in (tmp_path / "episode-output/experience.jsonl").read_text().splitlines()]
    reopened = [e for e in history if e["kind"] == "organization_work_reopened_v049"]
    assert len(reopened) == 1 and reopened[0]["payload"]["same_sdk_conversation"] is True
    assert reopened[0]["payload"]["budget_reset"] is False
    assert (tmp_path / "episode-output/public-capture.json").is_file()
    assert row["member_lifecycle"]["live_at_end"] == 2
    assert all(p["status"] == "live" for p in row["member_lifecycle"]["registry"].values())


def test_training_cannot_silently_make_one_window_per_episode(tmp_path):
    owner = CPUOwner({})
    prepared = build_software_collaboration_case(case_spec(CASE_IDS[0]), tmp_path / "prepared")
    with pytest.raises(ValueError, match="share the predeclared"):
        runtime_module.collect_episode(owner, prepared, tmp_path / "bad", sampling_seed=49, slot_id="bad")
    assert owner.phase == "idle"


def test_development_collect_preserves_loaded_update_and_never_promotes_source(tmp_path):
    owner = sdk_owner({})
    development_id = next(case_id for case_id in CASE_IDS if material(case_id)["purpose"] == "policy_development")
    prepared = build_software_collaboration_case(case_spec(development_id), tmp_path / "prepared")
    row = runtime_module.collect_episode(owner, prepared, tmp_path / "dev", sampling_seed=149, slot_id="v049-cpu-dev",
        transport_factory=fixture_transport, learning_binding={"branch": "B", "actor_steps": 4})
    assert row["training_eligible"] is False and row["purpose"] == "policy_development"
    assert row["episode_start_steps"]["actor_steps"] == 4
    assert owner.learning["actor_steps"] == owner.learning["critic_steps"] == 4 and owner.phase == "idle"
    assert row["learning_binding"]["branch"] == "B"
    for purpose in ("policy_training", "organization_development"):
        with pytest.raises(ValueError, match="predeclared"):
            case_spec(development_id, purpose=purpose)
    observation = SoftwareCollaborationPort(prepared.world.session(MEMBERS[0], PROJECT), MEMBERS[0]).observe()
    assert observation["purpose"] == "policy_development"


def test_wrong_training_window_cannot_generate_native_material(tmp_path):
    owner = CPUOwner({})
    owner.begin_window("wrong-logical-window")
    prepared = build_software_collaboration_case(case_spec(CASE_IDS[0]), tmp_path / "prepared")
    with pytest.raises(ValueError, match="frozen shared logical window"):
        runtime_module.collect_episode(owner, prepared, tmp_path / "bad", sampling_seed=49,
                                       slot_id="bad", manage_owner_window=False)
    assert owner.phase == "collecting"
