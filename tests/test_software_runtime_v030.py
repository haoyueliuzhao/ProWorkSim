"""CPU scripted SDK controls; fixture outputs are not model performance evidence."""
import copy
import json

import pytest

from proworksim import software_runtime_v030 as module
from proworksim import software_tasks_v030 as source
from proworksim.online_training import prepare_window, recipe_config
from proworksim.software_collaboration_v030 import CASE_IDS, MEMBERS, build_software_collaboration_case, case_spec
from proworksim.software_learning_v029 import CRITIC_MEMBERS, software_feature_function
from proworksim.software_runtime_v030 import (
    MODE, SDK_CONTEXT_SELECTION, _validate_window, build_runtime, close_runtime, collect_software_window, situation_id,
)
from proworksim.storage import read_json
from proworksim.team_rollout import optimizer_scope_allows_update
from test_online_collection_v013 import FakeOwner


class ScriptedOwner(FakeOwner):
    """No tensors or model: raw IDs/logprobs below are explicitly synthetic."""
    def __init__(self, actions, window_id="software-v030-cpu"):
        super().__init__(window_id=window_id)
        self.recipe.update(max_length=16384, members=list(CRITIC_MEMBERS))
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


def action(name, **arguments):
    return name, arguments


def window_spec(case_id=CASE_IDS[0], *, first=None, limit=12):
    case = case_spec(case_id, first_member=first)
    roles = case["active_roles"]
    return {"window_id": "software-v030-cpu", "harness": "openhands_v16", "usage": "model_interface_development",
            "mode": MODE, "min_class_count": 2,
            "budget": {"max_slots": 1, "max_model_calls": limit * len(roles)},
            "slots": [{"slot_id": "cpu-control", "case_id": case_id, "sampling_seed": 30,
                       "first_member": case["first_member"], "role_decision_limits": dict.fromkeys(roles, limit)}]}


def successful_actions(case_id):
    solution = source.reference_solution(case_id)
    if case_id == CASE_IDS[0]:
        return {MEMBERS[0]: [
            action("create_task", task_id="chosen-plan", description="CPU-authored development control"),
            action("claim_task", task_id="chosen-plan"),
            action("write_file", path="models.py", text=solution["models.py"]),
            action("write_file", path="consumer.py", text=solution["consumer.py"]),
            action("run_tests"), action("fix_patch", task_ids=["chosen-plan"], message="CPU fixed reference witness"),
            action("submit_integration", message="CPU satisfiability witness, never model work"),
            action("staff_done", reason="CPU control complete")],
        }
    return {
        MEMBERS[0]: [
            action("create_task", task_id="chosen-schema", description="CPU controller chooses this task"),
            action("claim_task", task_id="chosen-schema"),
            action("send_message", recipient=MEMBERS[1], task_id="root_goal", body="My chosen task will yield a fixed patch"),
            action("write_file", path="models.py", text=solution["models.py"]),
            action("fix_patch", task_ids=["chosen-schema"], message="CPU fixed schema witness"),
            action("staff_done", reason="CPU control producer done")],
        MEMBERS[1]: [
            action("staff_wait", reason="Await real root-goal negotiation"),
            action("create_task", task_id="chosen-delivery", description="CPU controller chooses integration work"),
            action("claim_task", task_id="chosen-delivery"),
            action("declare_dependency", task_id="chosen-delivery", depends_on="chosen-schema"),
            action("integrate_patch", patch_id="patch-1"),
            action("write_file", path="consumer.py", text=solution["consumer.py"]),
            action("run_tests"), action("fix_patch", task_ids=["chosen-delivery"], message="CPU combined witness"),
            action("submit_integration", message="CPU full delivery control"),
            action("staff_done", reason="CPU control integrator done")],
    }


def test_screening_spec_is_finite_and_cannot_relabel_development():
    spec = window_spec()
    assert _validate_window(spec) == spec["slots"]
    for name, value in (("usage", "policy_training"), ("mode", "current_policy_collection"), ("min_class_count", 1)):
        changed = copy.deepcopy(spec)
        changed[name] = value
        with pytest.raises(ValueError):
            _validate_window(changed)
    changed = copy.deepcopy(spec)
    changed["budget"]["max_model_calls"] += 1
    with pytest.raises(ValueError, match="caps"):
        _validate_window(changed)
    changed = copy.deepcopy(spec)
    changed["slots"][0]["role_decision_limits"][MEMBERS[1]] = 12
    with pytest.raises(ValueError, match="active member"):
        _validate_window(changed)
    assert "::active=member_a::first=member_a" in situation_id(case_spec(CASE_IDS[0]))
    assert "::active=member_a,member_b::first=member_b" in situation_id(case_spec(CASE_IDS[-1], first_member=MEMBERS[1]))


@pytest.mark.parametrize("case_id,first", [(CASE_IDS[0], MEMBERS[0]), (CASE_IDS[4], MEMBERS[1])])
def test_real_sdk_construction_is_nonsampling_and_has_only_active_roles(tmp_path, case_id, first):
    pytest.importorskip("openhands.sdk")
    case = case_spec(case_id, first_member=first)
    owner = ScriptedOwner({})
    prepared = build_software_collaboration_case(case, tmp_path / "case")
    before = prepared.world.store.load()
    runtime, captured, interfaces = build_runtime(owner, prepared, tmp_path / "runtime")
    try:
        assert not owner.requests and not owner.calls
        assert prepared.world.store.load() == before
        assert set(runtime.policies) == set(case["active_roles"]) == set(interfaces) == set(captured)
        assert runtime.labels[runtime.cursor] == first
        assert all(worker.context_selection == SDK_CONTEXT_SELECTION for worker in runtime.policies.values())
        assert runtime.recorder.events == [] and all(not events for events in captured.values())
    finally:
        close_runtime(runtime)


@pytest.mark.parametrize("case_id,first", [(CASE_IDS[0], MEMBERS[0]), (CASE_IDS[4], MEMBERS[1])])
def test_scripted_sdk_full_delivery_exports_original_views_and_forbids_all_training(tmp_path, case_id, first):
    pytest.importorskip("openhands.sdk")
    owner = ScriptedOwner(successful_actions(case_id))
    output = tmp_path / "window"
    callbacks = []
    entries = collect_software_window(owner, window_spec(case_id, first=first), output,
                                      on_slot=lambda event, row, folder: callbacks.append((event, row["slot_id"], folder.name)))
    entry = entries[0]
    assert callbacks == [("started", "cpu-control", "slot-0"), ("closed", "cpu-control", "slot-0")]
    assert entry["reward"]["reward"] == 1
    assert entry["rollout"]["work_validity"]["value"] is True
    assert read_json(output / "declaration.json")["gamma_identity"]["sdk_context_selection"] == SDK_CONTEXT_SELECTION
    archived_runtime = entry["rollout"]["manifest"]["scenario"]["variation"]["software_runtime"]
    assert archived_runtime["sdk_context_selection"] == SDK_CONTEXT_SELECTION
    assert "mapping" not in entry and not (output / "slot-0/mapping.json").exists()
    assert entry["process_diagnostics"]["counts"]["task_created"] == len(entry["active_members"])
    assert entry["process_diagnostics"]["counts"]["submit"] == 1
    assert entry["process_diagnostics"]["method_classification_performed"] is False
    assert not optimizer_scope_allows_update(entry["rollout"])
    stripped = copy.deepcopy(entry["rollout"])
    stripped.pop("online_scope")
    assert not optimizer_scope_allows_update(stripped)
    stripped["online_scope"] = {"optimizer_update_allowed": True, "source_training_admission": True, "purpose": "policy_training"}
    assert not optimizer_scope_allows_update(stripped)
    recipe = recipe_config()
    recipe["members"] = list(CRITIC_MEMBERS)
    batch = prepare_window(entries, owner.freeze_identity(), owner.window_id, recipe, software_feature_function)
    assert not batch["decisions"]
    assert batch["slots"][0]["exclusions"] == ["declared_scope_forbids_optimizer_update"]
    folder = output / "slot-0"
    events = [json.loads(line) for line in (folder / "experience.jsonl").read_text().splitlines()]
    assert events == read_json(folder / "runtime.json")["experience"]["events"]
    captures = read_json(folder / "public-capture.json")
    evidence = read_json(folder / "software-evidence.json")
    assert evidence["binding_matches_views"]
    assert set(evidence["member_views"]) == set(entry["active_members"])
    for member in entry["active_members"]:
        assert captures[member] == [json.loads(line) for line in (folder / "public-capture" / (member + ".jsonl")).read_text().splitlines()]
        view = evidence["member_views"][member]
        assert view["complete_actor_trajectory"]
        assert view["own_action_tokens"] == owner.calls[member]
    if len(entry["active_members"]) == 1:
        assert MEMBERS[1] not in captures and MEMBERS[1] not in owner.calls
    else:
        wake = [event for event in events if event["kind"] == "role_reactivated"]
        assert wake and wake[0]["payload"]["budget_reset"] is False
        assert entry["process_diagnostics"]["counts"]["integrate"] == 1


def test_sdk_service_unknown_keeps_requests_raw_assessment_and_views(tmp_path):
    pytest.importorskip("openhands.sdk")

    class FailedOwner(ScriptedOwner):
        def complete(self, request, **kwargs):
            raise ConnectionError("Explicit CPU transport failure")

    entries = collect_software_window(FailedOwner({}), window_spec(), tmp_path / "window")
    entry = entries[0]
    assert entry["reward"]["eligible"] is False and entry["reward"]["reward"] is None
    assert entry["rollout"]["work_validity"]["components"]["delivery"]["value"] is None
    folder = tmp_path / "window/slot-0"
    assert read_json(folder / "raw-independent-assessment.json")["R"] == 0
    assert read_json(folder / "assessment.json")["R"] is None
    events = [json.loads(line) for line in (folder / "experience.jsonl").read_text().splitlines()]
    requests = [event for event in events if event["kind"] == "model_attempt" and event["payload"]["stage"] == "started"]
    assert len(requests) == 1 and requests[0]["payload"]["request"]["messages"]
    assert read_json(tmp_path / "window/records.json")[0]["status"] == "closed_unassessed"


def test_interruption_preserves_committed_o1_creation_and_original_captures(tmp_path, monkeypatch):
    pytest.importorskip("openhands.sdk")
    owner = ScriptedOwner({MEMBERS[0]: [action("create_task", task_id="original-task", description="Committed before interruption")]})

    def interrupt(prepared, runtime, **kwargs):
        runtime.step()
        raise RuntimeError("Explicit CPU interruption")

    monkeypatch.setattr(module, "run_fragment", interrupt)
    with pytest.raises(RuntimeError, match="CPU interruption"):
        collect_software_window(owner, window_spec(), tmp_path / "window")
    folder = tmp_path / "window/slot-0"
    manifest = read_json(folder / "episode/manifest.json")
    assert manifest["status"] == "closed" and manifest["termination"]["status"] == "interrupted"
    assert read_json(folder / "episode/end/control/state.json")["software_events"][0]["kind"] == "task_created"
    assert (folder / "public-capture.json").exists() and (folder / "runtime.json").exists()
    assert not (folder / "entry.json").exists()
