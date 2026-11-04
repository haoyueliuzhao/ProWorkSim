"""Recover the host export of an already closed, uniquely locked v131 team.

Original results, model histories, costs and candidate bytes remain untouched.
This is a measurement repair, not a stopped-tree endpoint or a new attempt.
Only local immutable evidence is read; no scorer, SDK, Docker or API is started.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .software_benchmark_alignment_contract_v131 import shared_strategy, validate_plan_identity
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_episode_v066 import controller_ref, validate_closed_usage
from .software_benchmark_native_artifact_v054 import native_tree_manifest, validate_native_tree
from .software_benchmark_project_closure_v131 import validate_delivery_evidence

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL_BATCH = ROOT / "runs/software-benchmark-v131/fixed-organization-50-r1"
ORIGINAL_PLAN = ORIGINAL_BATCH / "execution-plan.json"
DEFAULT_OUTPUT = ROOT / "runs/software-benchmark-v132/candidate-recovery-r1/episodes"
VERSION = "v132-original-closed-team-host-lock-recovery-r1"
EXPECTED_ERROR = {"type": "KeyError", "message": "'project_candidate_lock'"}
IDENTITY_FIELDS = ("slot_id", "source_slot_id", "instance_id", "condition_id", "seed",
                   "arm", "execution_arm", "replicate", "model_key", "configuration",
                   "group_id", "organization_id", "fixed_members")


class IneligibleRecovery(ValueError):
    """An original attempt cannot use this narrowly defined measurement repair."""


def load(ref):
    return json.loads(checked(ref).read_bytes())


def require(value, message):
    if not value:
        raise IneligibleRecovery(message)


def _exact_file(ref, path):
    require(isinstance(ref, dict) and Path(ref.get("path", "")).resolve() == path.resolve(),
            "Evidence belongs to another original episode or filename")
    return load(ref)


def _planned(row, original_plan_ref):
    require(original_plan_ref == reference(ORIGINAL_PLAN), "Use the frozen original v131 plan")
    plan = load(original_plan_ref)
    selected = [item for item in plan["rows"] if item["slot_id"] == row.get("slot_id")]
    require(len(selected) == 1 and row == selected[0], "The complete original row changed")
    validate_plan_identity(row)
    require(row["arm"] == "PROJECT" and row["generation_token_upper_bound"] == 5_000_000,
            "Only the original five-million-token fixed teams are in scope")
    return ORIGINAL_BATCH / "episodes" / str(row["slot_index"])


def _sources_equal(left, right):
    return all(left.get(key) == right.get(key) for key in ("files", "entry_metadata"))


def _validated_original(row, original_result_ref, original_plan_ref):
    folder = _planned(row, original_plan_ref)
    original = _exact_file(original_result_ref, folder / "result.json")
    require(original.get("status") == "technical_unknown" and original.get("error") == EXPECTED_ERROR
            and original.get("candidate_lock") is None,
            "Only the exact post-closure host key mismatch is recoverable")
    require(all(original.get(key) == row[key] for key in IDENTITY_FIELDS),
            "Original result identity differs from its frozen team/issue/attempt")
    require(original.get("controller_status") == "closed" and original.get("controller_exit_code") == 0
            and original.get("terminal_capture_after_trusted_closure") is True
            and original.get("lifecycle_deadline_reached") is False
            and original.get("model_bridge_thread_finished") is True
            and not original.get("shared_integrity_fault"),
            "The original generation was not already closed and completely stopped")
    out = folder / "controller-output"
    child = _exact_file(original["controller_result"], out / "controller-result.json")
    require(child.get("status") == "closed" and all(child.get(key) == row[key] for key in (
        "slot_id", "condition_id", "arm", "model_key", "organization_id", "group_id", "fixed_members"))
        and child.get("execution_alignment") == shared_strategy(row["organization_id"]),
        "The private controller did not close under this exact team strategy")
    sessions, registry = child.get("private_sessions", {}), child.get("actual_member_registry", {})
    require(list(registry) == row["fixed_members"]
            and all(value.get("status") == "live" for value in registry.values())
            and set(sessions) == set(row["fixed_members"])
            and all(isinstance(value, str) and value for value in sessions.values())
            and len(set(sessions.values())) == row["member_count"],
            "The fixed roster/private SDK sessions are incomplete")
    ledger = validate_closed_usage(child.get("ledger"), {
        "all_model_attempts": 512, "agent_decisions": 512, "input_plus_output_tokens": 5_000_000})
    saved_ledger = _exact_file(original["controller_ledger"], out / "model-ledger/ledger.json")
    require(saved_ledger == ledger and original.get("ledger") == ledger,
            "Original controller and aggregate ledger snapshots disagree")
    require(set(ledger.get("per_member", {})) == set(row["fixed_members"])
            and ledger.get("shared_team_pool") is True
            and sum(value["attempts"] for value in ledger["per_member"].values()) == ledger["attempts"]
            and sum(value["known_actual_tokens"] for value in ledger["per_member"].values()) == ledger["known_actual_tokens"],
            "Each actual member must belong to the same original shared pool")
    for member in row["fixed_members"]:
        calls = [call for call in ledger["calls"] if call.get("member_id") == member]
        counters = ledger["per_member"][member]
        require(len(calls) == counters["attempts"]
                and sum(call["usage"]["total_tokens"] for call in calls) == counters["known_actual_tokens"]
                and all(call.get("team_slot_id") == row["slot_id"] and call["request_id"].startswith(
                    row["slot_id"] + ":" + member + ":") for call in calls),
                "Paid requests lost their exact team/member namespace")
    require(len({call["request_id"] for call in ledger["calls"]}) == ledger["attempts"],
            "One paid provider request cannot be counted twice")
    refs = {"original_plan": original_plan_ref, "original_result": original_result_ref,
            "controller_result": original["controller_result"], "controller_ledger": original["controller_ledger"]}
    for name, filename in (("writer_quiescence", "writer-quiescence.json"),
                           ("quiescence", "quiescence.json"),
                           ("controller_output_transfer", "controller-output-transfer.json")):
        refs[name] = original[name]
        _exact_file(refs[name], folder / filename)
    writers, quiet, transfer = (load(refs[key]) for key in (
        "writer_quiescence", "quiescence", "controller_output_transfer"))
    require(writers.get("all_quiet") is True and writers.get("errors") == []
            and writers.get("create_result_unknown_roles") == []
            and quiet.get("quiescent") is True and quiet.get("all_owned_objects_removed") is True
            and quiet.get("cleanup_errors") == [] and quiet.get("retained_objects") == []
            and quiet.get("create_result_unknown") is False,
            "Original writers or owned resource cleanup are unresolved")
    by_role = {item["role"]: item for item in writers["writers"]}
    require(set(by_role) == {"actor", "controller"} and len(writers["writers"]) == 2,
            "Both actual writers need unique stop evidence")
    for role, item in by_role.items():
        state = item["state"]
        require(state.get("Status") == "exited" and state.get("Running") is False
                and state.get("Pid") == 0 and state.get("ExitCode") == 0
                and state.get("OOMKilled") is False and item["claim"] == quiet["claims"][role],
                "An OOM, killed or unclosed writer cannot become a normal recovered episode")
        claim = load(item["claim"])
        require(claim.get("plan") == original_plan_ref and claim["spec"].get("slot_id") == row["slot_id"]
                and claim["spec"].get("role") == role, "Writer claim belongs to another original attempt")
    copied, storage, relocation = transfer["transfer"], transfer["archive_storage"], transfer["relocation"]
    require(copied.get("container_id") == by_role["controller"]["container_id"]
            and copied.get("container_claim") == by_role["controller"]["claim"]
            and copied.get("owned_volume_claim") == quiet["claims"]["volume"]
            and copied.get("role") == "controller" and copied.get("container_path") == "/pws/output"
            and storage.get("round_trip_verified") is True
            and storage.get("decompressed_sha256") == copied.get("stream_sha256")
            and storage.get("decompressed_bytes") == copied.get("bytes")
            and relocation.get("host_prefix") == str(out) and relocation.get("raw_json_references_rewritten") is False
            and relocation.get("complete_archive_roundtrip_verified") is True,
            "The immutable controller archive is not bound to its actual stopped writer")
    checked(storage["blob"])
    refs["controller_archive"] = storage["blob"]
    for name in ("native-bridge", "model-transport", "candidate-claim"):
        refs[name] = reference(folder / (name + ".json"))
    bridge, model, claim = (load(refs[name]) for name in ("native-bridge", "model-transport", "candidate-claim"))
    require(bridge.get("threads_finished") is True and bridge.get("errors") == []
            and model.get("status") in {"channel_closed", "stopped_after_controller"}
            and claim.get("writer_quiescence") == refs["writer_quiescence"]
            and claim.get("slot_id") == row["slot_id"], "Original terminal selection/transport did not close")
    baseline_ref = reference(folder / "baseline-snapshot.json")
    terminal_ref = original["unscored_terminal_snapshot"]
    baseline = load(baseline_ref)
    terminal = _exact_file(terminal_ref, folder / "terminal-snapshot.json")
    for label, bundle, ref in (("baseline", baseline, baseline_ref), ("terminal", terminal, terminal_ref)):
        require(bundle.get("truncated") is False, "A truncated tree cannot supply the original candidate")
        validate_native_tree(bundle["files"], bundle["entry_metadata"], bundle["file_policy"])
        require(native_tree_manifest(bundle["files"], bundle["entry_metadata"]) == bundle["tree"],
                "Retained complete source tree disagrees with its actual files/modes")
        refs[label] = ref
        provenance_ref = reference(folder / (label + "-snapshot-provenance.json"))
        provenance = load(provenance_ref)
        archive = provenance["archive"]
        require(provenance.get("snapshot") == ref
                and archive.get("container_id") == by_role["actor"]["container_id"]
                and archive.get("container_claim") == by_role["actor"]["claim"]
                and archive.get("owned_volume_claim") == quiet["claims"]["volume"],
                "Retained source snapshot belongs to another actor or capture")
        refs[label + "_provenance"] = provenance_ref
    closure = copy.deepcopy(child["project_closure"])
    require("project_candidate_lock" not in closure, "An already repaired interface cannot be selected again")
    for name in ("terminal_snapshot", "baseline_snapshot", "delivery_snapshot", "delivery_evidence",
                 "controller_candidate_lock"):
        refs[name] = controller_ref(closure[name], out)
        closure[name] = refs[name]
    closure["project_candidate_lock"] = refs["controller_candidate_lock"]
    require(_sources_equal(load(refs["terminal_snapshot"]), terminal)
            and _sources_equal(load(refs["baseline_snapshot"]), baseline),
            "Controller and actual stopped actor trees disagree")
    pair = load(refs["controller_candidate_lock"])
    require(pair.get("task_id") == row["instance_id"] and pair.get("same_world_transaction") is True
            and pair.get("locked_before_grading") is True
            and pair.get("organization_closure_version") == "v131-private-fixed-team-shared-pool-runtime-r1"
            and pair.get("candidate_selection") == "Predeclared member_001 only; other unmerged member trees never selected"
            and all(pair.get(key) == 0 for key in ("model_calls", "public_test_calls", "grading_calls")),
            "No unique original member001 candidate lock is available")
    endpoints = {}
    for name, key in (("code", "terminal_code"), ("delivery", "last_legal_delivery")):
        if pair[key] is None:
            require(name == "delivery" and pair.get("submitted") is False, "Missing original code lock")
            continue
        lock_ref = controller_ref(pair[key], out)
        lock = load(lock_ref)
        binding_ref, candidate_ref, receipt_ref = (controller_ref(lock[field], out)
            for field in ("binding", "candidate", "patch_receipt"))
        binding, bundle, receipt = (load(ref) for ref in (binding_ref, candidate_ref, receipt_ref))
        patch_ref = controller_ref(receipt["patch"], out)
        checked(patch_ref).read_bytes().decode("utf-8", "strict")
        tree = native_tree_manifest(bundle["files"], bundle["entry_metadata"])
        require(lock.get("task_id") == row["instance_id"] and lock.get("lock_before_grading") is True
                and lock.get("candidate_selection_after_scoring") is False
                and lock.get("tree_sha256") == tree["tree_sha256"]
                and receipt.get("round_trip_verified") is True
                and receipt.get("candidate_tree_sha256") == tree["tree_sha256"]
                and receipt.get("base_tree_sha256") == baseline["tree"]["tree_sha256"],
                "The pre-locked patch/bundle has inconsistent identity or tree evidence")
        if name == "code":
            require(binding.get("actor_id") == "member_001"
                    and binding.get("source_sha256") == candidate_ref["sha256"]
                    and binding.get("source_reference") == lock.get("source_reference") == closure.get("terminal_source_reference")
                    and _sources_equal(bundle, terminal), "Code candidate is not the original final member001 source")
        endpoints[name] = {"lock": lock, "lock_ref": lock_ref, "binding_ref": binding_ref,
            "candidate_ref": candidate_ref, "bundle": bundle, "patch_ref": patch_ref,
            "receipt": receipt, "receipt_ref": receipt_ref}
    delivery, evidence = load(refs["delivery_snapshot"]), load(refs["delivery_evidence"])
    verdict = validate_delivery_evidence(evidence, delivery, baseline)
    require(verdict == child["project_closure"]["delivery_validation"]
            and evidence.get("locked_before_grading") is True and evidence.get("model_calls_after_lock") == 0
            and evidence.get("controller_candidate_lock") == child["project_closure"]["controller_candidate_lock"]
            and evidence.get("terminal_tree_sha256") == terminal["tree"]["tree_sha256"]
            and pair.get("submitted") is verdict["submitted"]
            and pair.get("same_tree") is verdict["same_tree"], "Original organization delivery proof changed")
    if verdict["submitted"]:
        require("delivery" in endpoints and _sources_equal(endpoints["delivery"]["bundle"], delivery["candidate"]),
                "Last legal submission and its original patch select different trees")
    require(child.get("terminal_sync", {}).get("terminal_locked") is True
            and child["terminal_sync"].get("tree_sha256") == terminal["tree"]["tree_sha256"],
            "Original actor did not acknowledge its uniquely locked final tree")
    proof = {"version": VERSION, "original_plan": original_plan_ref, "original_result": original_result_ref,
        "original_episode_folder": str(folder), "slot_id": row["slot_id"], "original_status": "technical_unknown",
        "original_error": EXPECTED_ERROR, "original_controller_status": "closed", "evidence": refs,
        "endpoint_locks": {name: item["lock_ref"] for name, item in endpoints.items()},
        "original_patches": {name: item["patch_ref"] for name, item in endpoints.items()},
        "terminal_tree_sha256": terminal["tree"]["tree_sha256"], "designated_delivery_member": "member_001",
        "delivery_validation": verdict, "known_actual_tokens": ledger["known_actual_tokens"],
        "original_controller_calls": ledger["attempts"], "candidate_content_changed": False,
        "original_records_overwritten": False, "candidate_reselection": False,
        "new_model_calls": 0, "new_scoring_calls": 0, "Docker_operations": 0,
        "original_archive_round_trip_receipt_retained": True, "new_archive_redecode": False,
        "scorer_still_must_bind_original_archive_members": True, "source_module": reference(__file__)}
    return {"row": row, "original": original, "child": child, "baseline": baseline, "terminal": terminal,
            "endpoints": endpoints, "closure": closure, "proof": proof, "refs": refs, "folder": folder}


def inspect_recoverable(row, original_result_ref, *, original_plan_ref):
    """Read-only exact evidence gate. Raises for missing/OOM/stopped/other failures."""
    return copy.deepcopy(_validated_original(row, original_result_ref, original_plan_ref)["proof"])


def _slot(row):
    keys = ("slot_index", "slot_id", "instance_id", "repo", "condition_id", "seed",
            "execution_arm", "replicate", "source_slot_id", "arm", "model_key")
    return {**{key: row[key] for key in keys}, "input_plus_output_tokens": row["generation_token_upper_bound"]}


def _patch_receipt(endpoint, copied_patch):
    return {**endpoint["receipt"], "patch": copied_patch, "utf8_strict": True,
            "candidate_content_changed": False, "original_patch_receipt": endpoint["receipt_ref"],
            "original_patch": endpoint["patch_ref"], "patch_bytes_changed": False}


def _lock(data, endpoint, candidate_ref, patch_ref, proof_ref):
    row, item, refs = data["row"], data["endpoints"][endpoint], data["refs"]
    writers = load(refs["writer_quiescence"])
    actor = next(value for value in writers["writers"] if value["role"] == "actor")
    return {"version": "software-benchmark-native-closure-v054", "implementation": VERSION,
        "claim_id": actor["claim"]["sha256"], "slot": _slot(row), "source_slot_id": row["source_slot_id"],
        "measurement_kind": "full_verified_comparison", "endpoint": "terminal_code" if endpoint == "code" else "last_legal_delivery",
        "quiescence": refs["writer_quiescence"], "baseline": refs["baseline"], "candidate": candidate_ref,
        "patch_receipt": _patch_receipt(item, patch_ref), "tree_sha256": item["lock"]["tree_sha256"],
        "delivery": None if endpoint == "code" else refs["delivery_evidence"],
        "lock_before_grading": True, "model_calls": 0, "grading_calls": 0,
        "recovery_proof": proof_ref, "original_controller_candidate_lock": item["lock_ref"]}


def _delivery_native(data):
    bundle = data["endpoints"]["delivery"]["bundle"]
    result = {**data["terminal"], "files": bundle["files"], "entry_metadata": bundle["entry_metadata"]}
    result["tree"] = native_tree_manifest(result["files"], result["entry_metadata"])
    return result


def _result(data, proof_ref, code_lock, delivery_lock):
    original, child, refs = data["original"], data["child"], data["refs"]
    result = copy.deepcopy(original)
    for key in ("error", "traceback"):
        result.pop(key, None)
    result.update(version=VERSION, status="closed", original_status="technical_unknown",
        measurement_recovery_only=True, original_result=refs["original_result"],
        original_episode_folder=str(data["folder"]), recovery_proof=proof_ref,
        candidate_lock=code_lock, delivery_candidate_lock=delivery_lock,
        delivery_evidence=refs["delivery_evidence"], delivery_snapshot=refs["delivery_snapshot"],
        project_baseline_snapshot=refs["baseline"], project_closure=data["closure"],
        delivery_validation=data["proof"]["delivery_validation"],
        same_code_and_delivery_tree=data["proof"]["delivery_validation"]["same_tree"],
        model_calls=child["ledger"]["attempts"], known_actual_tokens=child["ledger"]["known_actual_tokens"],
        new_model_calls=0, new_scoring_calls=0, candidate_content_changed=False,
        original_records_overwritten=False, model_can_resume=False)
    return result


def recover_closed_candidate(row, original_result_ref, output, *, original_plan_ref):
    """Emit fresh standard host endpoints, copying only the original locked patch bytes."""
    data = _validated_original(row, original_result_ref, original_plan_ref)
    output = Path(output).resolve()
    require(not output.is_relative_to(ORIGINAL_BATCH.resolve()), "Never write into the original experiment")
    output.mkdir(parents=True, exist_ok=False)
    proof_ref = write_new(output / "recovery-proof.json", data["proof"])
    code_patch = write_new(output / "candidate.patch", checked(data["endpoints"]["code"]["patch_ref"]).read_bytes())
    code = write_new(output / "candidate-lock.json", _lock(data, "code", data["refs"]["terminal"], code_patch, proof_ref))
    delivery = None
    if "delivery" in data["endpoints"]:
        native = write_new(output / "delivery-native-snapshot.json", _delivery_native(data))
        patch = write_new(output / "delivery-candidate.patch", checked(data["endpoints"]["delivery"]["patch_ref"]).read_bytes())
        delivery = write_new(output / "delivery-candidate-lock.json", _lock(data, "delivery", native, patch, proof_ref))
    return write_new(output / "result.json", _result(data, proof_ref, code, delivery))


def validate_recovered_result(result_ref, *, original_plan_ref):
    """Independently bind a derived endpoint to immutable original closure evidence."""
    result = load(result_ref)
    require(result.get("version") == VERSION and result.get("measurement_recovery_only") is True,
            "A tag alone cannot authorize another recovered generation")
    plan = load(original_plan_ref)
    rows = [row for row in plan["rows"] if row["slot_id"] == result.get("slot_id")]
    require(len(rows) == 1, "Recovery belongs to no unique original planned team")
    data = _validated_original(rows[0], result["original_result"], original_plan_ref)
    output = checked(result_ref).parent.resolve()
    require(not output.is_relative_to(ORIGINAL_BATCH.resolve()), "Original result cannot be overwritten")
    proof_ref = result["recovery_proof"]
    require(_exact_file(proof_ref, output / "recovery-proof.json") == data["proof"],
            "Recovery proof differs from the original evidence or source implementation")
    for endpoint, name, lock_name in (("code", "candidate.patch", "candidate-lock.json"),
                                      ("delivery", "delivery-candidate.patch", "delivery-candidate-lock.json")):
        field = "candidate_lock" if endpoint == "code" else "delivery_candidate_lock"
        if endpoint not in data["endpoints"]:
            require(result.get(field) is None, "Absent legal delivery cannot acquire a candidate")
            continue
        item = data["endpoints"][endpoint]
        patch_ref = reference(output / name)
        require(checked(patch_ref).read_bytes() == checked(item["patch_ref"]).read_bytes(),
                "A recovered patch must preserve the exact original selected patch bytes")
        native_ref = data["refs"]["terminal"]
        if endpoint == "delivery":
            native_ref = reference(output / "delivery-native-snapshot.json")
            require(load(native_ref) == _delivery_native(data), "The recovered delivery tree changed")
        require(_exact_file(result[field], output / lock_name) == _lock(data, endpoint, native_ref, patch_ref, proof_ref),
                "The recovered candidate lock is not the deterministic original endpoint")
    require(result == _result(data, proof_ref, result["candidate_lock"], result["delivery_candidate_lock"]),
            "Derived result contains an unauthorized status, usage, identity or evidence change")
    return result
