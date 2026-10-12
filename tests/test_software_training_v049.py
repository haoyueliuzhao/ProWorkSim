"""v049 export integration uses real CPU SDK/WorldCore with programmed outputs.

All token IDs and completions here are explicitly synthetic structural controls,
never qualified production model samples, real learning, or performance evidence.
"""
import copy
import json

import pytest

from proworksim import online_support
from proworksim import software_organization_runtime_v049 as runtime_module
from proworksim import software_training_v049 as training
from proworksim.episode import assess_historical_episode
from proworksim.online_training import prepare_window, recipe_config
from proworksim.software_context_v048 import SoftwareContextTransport, CANDIDATE_SHA256, VERSION as CONTEXT_VERSION
from proworksim.software_mapper_v049 import mapping_spec
from proworksim.software_organization_tasks_v049 import reference_solution, TRAINING_CASE_IDS, DEVELOPMENT_CASE_IDS
from proworksim.software_organization_v049 import build_software_collaboration_case, case_spec, PROJECT
from proworksim.storage import atomic_write, digest, json_bytes, read_json
from test_software_organization_runtime_v038 import CPUOwner, action
from test_software_organization_runtime_v040 import SelectedCPUTransport, tokenize

MEMBERS = ["member_001", "member_002"]


def gamma():
    spec = mapping_spec()
    return {"harness": "openhands_v16", "source_usage": "policy_training",
        "collection_mode": "current_policy_collection", "optimizer_update_allowed": True,
        "gamma_version": training.GAMMA_VERSION, "runtime_version": runtime_module.VERSION,
        "presentation_version": CONTEXT_VERSION, "sdk_context_selection": training.SDK_CONTEXT_SELECTION,
        "mapper_specification": spec, "mapper_spec_sha256": digest(json_bytes(spec)),
        "presentation_identity": {"candidate_sha256": CANDIDATE_SHA256, "presentation_version": CONTEXT_VERSION},
        "fixture_only": True}


def owner_for(script):
    pytest.importorskip("openhands.sdk")
    owner = CPUOwner(script)
    owner.recipe.update(max_length=18432, members=[*MEMBERS, "software_inactive"])
    identity = {"version": "shared-actor-identity-v0.13", "policy_version": "explicit-cpu-no-model-v049",
        "adapter_sha256": "a" * 64, "base_manifest_sha256": "b" * 64, "inference_profile_sha256": "c" * 64}
    owner.freeze_identity = lambda: copy.deepcopy(identity)
    owner.actor_steps = owner.critic_steps = owner.policy_revision = 3
    owner.prepare_request = lambda request: (json.dumps(request, ensure_ascii=False, sort_keys=True), None, None)
    owner.tokenizer = tokenize

    def complete_shape(body):
        request = owner.transport.requests[-1]
        trace = body["token_trace"]
        trace.update(input_mask=[0] * len(trace["input_ids"]), output_mask=[1] * len(trace["output_ids"]),
            behavior_logprobs=[-1.0] * len(trace["output_ids"]),
            raw_output_ids=list(trace["output_ids"]), raw_behavior_logprobs=[-1.0] * len(trace["output_ids"]),
            sampling_temperature=0.7, sampling_top_p=1, sampling_top_k=0,
            source="actual generation token IDs and sampling logits, not retokenized text")
        body.update(system_fingerprint=identity["policy_version"], fixture_only=True,
            prompt_projection={"request_sha256": digest(json_bytes(request)),
                "rendered_prompt_sha256": digest(owner.prepare_request(request)[0].encode())})

    owner.transport = SelectedCPUTransport(owner, mutate=complete_shape)
    return owner


def declaration_for(owner, prepared, slot_id):
    policies = training.policy_spec(owner, prepared)
    original = {"xi_id": training.situation_id(prepared.case),
        "xi_fingerprint": training.situation_fingerprint(prepared), "active_members": MEMBERS,
        "policies": policies, "mapping_spec_id": training.MAPPER}
    return training.declare_window(training.TRAINING_WINDOW_ID, actor_identity=owner.freeze_identity(),
        gamma_identity=gamma(), slot_specs=[{**copy.deepcopy(original), "slot_id": name}
            for name in [slot_id, *["unavailable-" + str(i) for i in range(7)]]])


def collect_control(folder, route):
    """Finite synthetic record with genuine world receipts and SDK archives."""
    reference = reference_solution(TRAINING_CASE_IDS[0])["event_time.py"]
    script = {member: [action("staff_done", reason="Explicit CPU control complete")] for member in MEMBERS}
    if route == "local":
        script[MEMBERS[0]] = [action("write_file", path="event_time.py", text=reference),
            action("run_tests"), action("fix_patch", task_ids=[], message="CPU witness"),
            action("submit_integration", message="CPU witness, not model success"), action("staff_done", reason="CPU done")]
    if route == "peer":
        script[MEMBERS[0]] = [action("write_file", path="event_time.py", text=reference),
            action("fix_patch", task_ids=[], message="CPU partner fixed source"),
            action("staff_done", reason="CPU author current work ended")]
        script[MEMBERS[1]] = [action("staff_wait", reason="CPU wait for actual fixed publication"),
            action("adopt_candidate", patch_id="patch-1"), action("run_tests"),
            action("fix_patch", task_ids=[], message="CPU recipient fixed tree"),
            action("submit_integration", message="CPU peer-route witness, not model success"),
            action("staff_done", reason="CPU recipient done")]
    owner = owner_for(script)
    owner.begin_window(training.TRAINING_WINDOW_ID)
    prepared = build_software_collaboration_case(case_spec(TRAINING_CASE_IDS[0]), folder / "prepared")
    slot_id = "explicit-cpu-v049-" + route
    declaration = declaration_for(owner, prepared, slot_id)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(runtime_module, "_capture_slot_guard", lambda current: copy.deepcopy(current.learning))
        row = runtime_module.collect_episode(owner, prepared, folder / "slot", sampling_seed=49,
            slot_id=slot_id, manage_owner_window=False,
            transport_factory=lambda current, directory: SoftwareContextTransport(current, directory,
                evidence_kind="cpu_programmed_fixture"))
    episode = folder / "slot/episode"
    captured = read_json(folder / "slot/public-capture.json")
    entry, detail = training.export_software_episode(prepared, episode, row["assessment"],
        declaration=declaration, slot_id=slot_id, captured=captured, runtime_row=row)
    atomic_write(folder / "export-control.json", json_bytes({"route": route, "entry": entry, "detail": detail,
        "explicit_synthetic_cpu_fixture": True, "real_model_calls": 0, "GPU_calls": 0,
        "tokenizer": "deterministic synthetic 64-character hash blocks"}))
    return {"owner": owner, "prepared": prepared, "declaration": declaration, "entry": entry,
        "detail": detail, "row": row, "episode": episode, "captured": captured, "folder": folder}


@pytest.fixture(scope="module")
def controls(tmp_path_factory):
    root = tmp_path_factory.mktemp("v049-export-controls")
    return {route: collect_control(root / route, route) for route in ("failure", "local")}


def test_declares_true_new_worker_without_mutating_old_support_gate(controls):
    control = controls["failure"]
    manifest = read_json(control["episode"] / "manifest.json")
    declared = control["declaration"]["slots"][0]["policies"]
    assert manifest["policies"] == declared
    assert all(row["implementation"] == "proworksim.software_organization_runtime_v049.worker_type.<locals>.StableO1Worker"
               for row in declared.values())
    with pytest.raises(ValueError, match="Active members"):
        online_support.expected_window(control["declaration"], control["entry"]["slot_id"])
    assert training.expected_window(control["declaration"], control["entry"]["slot_id"]) == control["entry"]["rollout"]["window"]


def test_failed_complete_own_trajectories_still_enter_base_and_keep_eight_slot_denominators(controls):
    control = controls["failure"]
    entry, detail = control["entry"], control["detail"]
    assert entry["reward"]["eligible"] is True and entry["reward"]["reward"] == 0
    assert detail["work_validity"]["components"]["record"]["value"] is True
    assert detail["work_validity"]["components"]["delivery"]["value"] is False
    assert entry["mapping"]["status"] == "unmapped"
    entries = [entry, *[training.unavailable_slot_entry(control["declaration"], "unavailable-" + str(i),
        "Explicit missing-material CPU control") for i in range(7)]]
    recipe = {**recipe_config({"max_length": 18432}), "members": [*MEMBERS, "software_inactive"]}
    prepared = prepare_window(entries, control["owner"].freeze_identity(), training.TRAINING_WINDOW_ID, recipe,
        lambda *args: ([0.0] * 30, {"fixture_only": True}))
    assert len(prepared["decisions"]) == 2 and prepared["slot_count"] == 8
    assert {row["actor_denominator"] for row in prepared["decisions"]} == {16}
    assert {row["critic_denominator"] for row in prepared["decisions"]} == {16}
    assert all(row["reward"] == 0 for row in prepared["decisions"])
    assert all(row["tokens"]["fixture_only"] is True for row in prepared["decisions"])
    assert all(row["exclusions"] == ["episode_or_reward_record_missing"] for row in prepared["slots"][1:])


def test_mapper_receives_real_paged_test_fixed_delivery_and_original_native_tokens(controls):
    control = controls["local"]
    entry, details = control["entry"], control["detail"]
    assert control["row"]["R"] == 1
    assert details["work_validity"]["value"] is True
    assert entry["mapping"]["class_id"] == "local_lineage_delivery"
    evidence = details["original_work_evidence"]
    assert evidence["delivery"] == control["row"]["assessment"]["delivery"]
    assert {event["kind"] for event in evidence["original_events"]} >= {"edit", "test", "patch_fixed", "submit"}
    assert details["binding_matches_views"] is True
    for view in details["member_views"].values():
        for decision in view["decisions"]:
            if decision["actor_trainable"]:
                assert decision["tokens"] == decision["actual_response"]["token_trace"]
                assert decision["tokens"]["input_mask"] == [0] * len(decision["tokens"]["input_ids"])
                assert decision["loss_mask"] == decision["tokens"]["input_mask"] + decision["tokens"]["output_mask"]
    assert assess_historical_episode(control["episode"])["assessment_execution"]["status"] == "complete"


def test_new_situation_identity_ignores_uuid_and_control_cost_but_keeps_permissions_and_facts(tmp_path, controls):
    control = controls["failure"]
    other = build_software_collaboration_case(copy.deepcopy(control["prepared"].case), tmp_path / "other")
    expected = control["declaration"]["slots"][0]["xi_fingerprint"]
    assert training.situation_fingerprint(other) == expected
    assert training.situation_fingerprint(control["prepared"], episode=control["episode"]) == expected
    with other.world.store.lock():
        state = other.world.store.load()
        state["projects"][PROJECT]["software"]["initial_diagnostic_assignments"][MEMBERS[0]] = []
        other.world.store.save(state)
    assert training.situation_fingerprint(other) != expected


def test_frozen_new_source_cannot_relabel_development_or_mapper(controls):
    control = controls["failure"]
    assert training.source_training_admission(control["prepared"].case, gamma())["training_eligible"] is True
    with pytest.raises(ValueError, match="cannot be relabeled"):
        training.source_training_admission(case_spec(DEVELOPMENT_CASE_IDS[0]), gamma())
    changed = gamma()
    changed["mapper_specification"] = {**changed["mapper_specification"], "later_change": True}
    with pytest.raises(ValueError, match="cannot be relabeled"):
        training.source_training_admission(control["prepared"].case, changed)


@pytest.mark.parametrize("part", ["capture", "runtime", "assessment"])
def test_export_rejects_detached_actual_capture_runtime_or_assessment(controls, part):
    control = controls["failure"]
    capture, row, assessment = (copy.deepcopy(control[key]) for key in ("captured", "row", "row"))
    assessment = assessment["assessment"]
    if part == "capture":
        capture[MEMBERS[0]].append({"fabricated": True})
    elif part == "runtime":
        row["sampling_seed"] += 1
    else:
        assessment["R"] = 1
    with pytest.raises(ValueError, match="capture|binding"):
        training.export_software_episode(control["prepared"], control["episode"], assessment,
            declaration=control["declaration"], slot_id=control["entry"]["slot_id"], captured=capture, runtime_row=row)


@pytest.mark.parametrize("value", [0, 1, None])
def test_known_joint_reward_survives_administrative_censoring_while_unknown_stays_unavailable(value):
    assessment = {"status": "unknown" if value is None else "evaluable", "R": value}
    reward = training.reward_record({"episode_id": "explicit-cpu-reward-shape"}, "a" * 64,
        assessment, {"R_joint": value, "R_token": None, "administrative_censoring": True},
        case={"task_type": "stable_o1_root_goal"}, reward_spec={"training_supported": True})
    assert reward["eligible"] is (value is not None)
    assert reward["reward"] == reward["formal_R_joint"] == value
    assert reward["R_token"] is None and reward["administrative_censoring"] is True
    assert reward["completed"] is (value == 1)
