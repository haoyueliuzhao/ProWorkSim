"""Freeze each original member_001 committed tree after a role-pilot API failure.

This is a supplementary code endpoint, never a retroactive SDK close, legal
submission, model continuation or alternative selection using judge outcomes.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import tarfile

from .core.journal import validate_committed_prefix
from .repository_sources_v054 import RepositorySources, tree_manifest
from .software_benchmark_archive_storage_v064 import open_verified_archive, stream_reference
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_native_artifact_v054 import _native_tree
from .software_benchmark_snapshot_recovery_v061 import export_utf8_patch
from .storage import digest, json_bytes

ROOT = Path(__file__).resolve().parents[2]
BATCH = ROOT / "runs/software-benchmark-v142/role-pilot40-r1"
OUTPUT = ROOT / "runs/software-benchmark-v145/stopped-code-recovery-r1"
AUDIT = ROOT / "artifacts/software-benchmark-v145/recovery-inventory-r2"
VERSION = "v145-unique-committed-role-stop-supplement-r1"
ENDPOINT = "recovered_stopped_code"
TASKS = {10066: 'scikit-learn__scikit-learn-14894', 10068: 'scikit-learn__scikit-learn-14894', 10076: 'scikit-learn__scikit-learn-11310', 10078: 'django__django-13807', 10082: 'pydata__xarray-6461', 10084: 'sphinx-doc__sphinx-10614', 10086: 'sphinx-doc__sphinx-10614', 10089: 'matplotlib__matplotlib-26466', 10090: 'psf__requests-2931', 10091: 'psf__requests-2931', 10093: 'mwaskom__seaborn-3069', 10094: 'mwaskom__seaborn-3069', 10096: 'psf__requests-1921', 10098: 'psf__requests-1921', 10103: 'psf__requests-1766', 10104: 'psf__requests-1766', 10105: 'pylint-dev__pylint-4604', 10107: 'pylint-dev__pylint-4604', 10114: 'pytest-dev__pytest-6197', 10116: 'pytest-dev__pytest-6197', 10117: 'pydata__xarray-4966'}
STATE = "output/managed-world/world/control/state.json"
MANIFEST = "output/source-snapshot/source-manifest.json"
INITIAL = "output/source-snapshot/initial-tree.json"


def load(ref):
    return json.loads(checked(ref).read_bytes())


def artifact_paths(state):
    validate_committed_prefix(state)
    if state.get("runtime_kind") != "world_core":
        raise ValueError("Only the original committed managed world may supply a candidate")
    result = {}
    for alias, filename in (("baseline", "baseline.json"), ("member_001", "member_001.json")):
        values = [
            a
            for a in state["artifacts"].values()
            if a.get("project_id") == "SOFTWARE27" and a.get("alias") == alias
        ]
        if len(values) != 1:
            raise ValueError("A baseline/current member source is not unique")
        artifact = values[0]
        if (
            artifact.get("filename") != filename
            or artifact.get("kind") != "json"
            or "/" in artifact["artifact_id"]
            or artifact["current_version"] not in artifact["versions"]
        ):
            raise ValueError("The committed artifact identity changed")
        result[alias] = (
            artifact,
            "output/managed-world/world/control/versions/"
            + artifact["artifact_id"]
            + "/"
            + artifact["current_version"]
            + "/"
            + filename,
        )
    return result


def read_managed_archive(storage):
    """One streaming pass normally; no archive extraction or store recovery."""
    selected, member_refs, artifacts = {}, {}, None
    sdk_conversations, sdk_events, sdk_state_names = set(), 0, []
    wanted = {STATE, MANIFEST, INITIAL}

    def scan(missing_only=False):
        nonlocal artifacts, sdk_events
        seen = set()
        with open_verified_archive(storage) as stream:
            with tarfile.open(fileobj=stream, mode="r|*") as archive:
                for member in archive:
                    path = PurePosixPath(member.name.removeprefix("./"))
                    if (
                        path.is_absolute()
                        or ".." in path.parts
                        or not path.parts
                        or path.parts[0] != "output"
                    ):
                        raise ValueError("Controller archive path escapes its original output root")
                    name = str(path)
                    if name in wanted and name not in selected:
                        # The v141 state retains two private observation histories;
                        # the audited sklearn state is a regular 759,508,937-byte file.
                        maximum = 2*1024**3 if name == STATE else 512*1024**2
                        if name in seen or not member.isfile() or member.size > maximum:
                            raise ValueError(
                                f"Selected managed source is duplicate or not a bounded ordinary file: {name}, size={member.size}, limit={maximum}"
                            )
                        raw = archive.extractfile(member).read()
                        selected[name] = raw
                        member_refs[name] = {
                            "member": name,
                            "sha256": digest(raw),
                            "bytes": len(raw),
                        }
                        if name == STATE:
                            state = json.loads(raw)
                            artifacts = artifact_paths(state)
                            wanted.update(item[1] for item in artifacts.values())
                    elif name in wanted and name in seen:
                        raise ValueError("Duplicated selected archive member")
                    seen.add(name)
                    if (
                        not missing_only
                        and any("/managed-runtime/sdk-conversations/"+member+"/conversations/" in name
                                for member in ("member_001", "member_002"))
                    ):
                        tail = name.split("/conversations/", 1)[1].split("/")
                        if tail:
                            sdk_conversations.add(tail[0])
                        sdk_events += int("/events/event-" in name and member.isfile())
                        if member.isfile() and "/events/" not in name and name.endswith(".json"):
                            sdk_state_names.append(name)

    scan()
    if wanted - set(selected):
        scan(missing_only=True)
    if wanted - set(selected) or artifacts is None:
        raise ValueError("The selected committed state/version bytes are not all retained")
    return (
        selected,
        member_refs,
        {
            "conversation_ids": sorted(sdk_conversations),
            "event_files": sdk_events,
            "state_files": sdk_state_names,
            "in_place_session_resume_attempted": False,
        },
    )


def validate_original(row, result, writers, quiet, transfer, interrupted, baseline_provenance):
    if (
        row["slot_index"] not in TASKS
        or row["instance_id"] != TASKS[row["slot_index"]]
        or row["arm"] != "PROJECT"
        or result.get("status") != "technical_unknown"
        or result.get("candidate_lock") is not None
        or any(
            result.get(key) != row[key]
            for key in ("slot_id", "instance_id", "configuration", "condition_id", "seed", "arm")
        )
        or result.get("error")
        != {
            "type": "RuntimeError",
            "message": "The native controller did not produce a trusted closed episode",
        }
        or result.get("fixed_members") != row["fixed_members"]
        or result.get("organization_id") != row["organization_id"]
        or result.get("hidden_feedback_received", False) is not False
        or result.get("model_bridge_thread_finished") is not True
        or writers.get("all_quiet") is not True
        or writers.get("errors") != []
        or writers.get("create_result_unknown_roles") != []
        or quiet.get("quiescent") is not True
        or quiet.get("all_owned_objects_removed") is not True
        or quiet.get("cleanup_errors") != []
        or quiet.get("retained_objects") != []
        or quiet.get("create_result_unknown") is not False
        or interrupted.get("writer_quiescence") != writers
        or interrupted.get("official_final_candidate") is not False
        or interrupted.get("scoring_authorized_by_this_record") is not False
    ):
        raise ValueError(
            "Only these fully stopped original pilot API-failed attempts are admitted"
        )
    child = load(result["controller_result"])
    boundary = child.get("managed_boundary", {})
    if (child.get("slot_id") != row["slot_id"]
            or child.get("fixed_members") != row["fixed_members"]
            or child.get("status") != "technical_unknown"
            or child.get("hidden_feedback_received") is not False
            or boundary.get("execution_integrity_failure", {}).get("status") != "model_service_error"
            or child.get("ledger", {}).get("halted") != "APIUncertainFailure"):
        raise ValueError("Original private controller does not prove this audited model-service stop")
    by_role = {item["role"]: item for item in writers["writers"]}
    if set(by_role) != {"actor", "controller"} or len(writers["writers"]) != 2:
        raise ValueError("Both namespace writers must have unique stop proof")
    for role, item in by_role.items():
        state = item["state"]
        if (
            state.get("Status") != "exited"
            or state.get("Running") is not False
            or state.get("Pid") != 0
            or item["claim"] != quiet["claims"][role]
        ):
            raise ValueError("The source writer is not proven stopped under its exact claim")
    source = transfer["transfer"]
    storage = transfer["archive_storage"]
    if (
        source.get("role") != "controller"
        or source.get("container_path") != "/pws/output"
        or source.get("container_id") != by_role["controller"]["container_id"]
        or source.get("container_claim") != by_role["controller"]["claim"]
        or source.get("owned_volume_claim") != quiet["claims"]["volume"]
        or source.get("stream_sha256") != storage["decompressed_sha256"]
        or source.get("bytes") != storage["decompressed_bytes"]
        or storage.get("round_trip_verified") is not True
    ):
        raise ValueError("The managed state archive must belong to the stopped original controller")
    for archive in (interrupted["archive"], baseline_provenance["archive"]):
        if (
            archive.get("container_id") != by_role["actor"]["container_id"]
            or archive.get("container_claim") != by_role["actor"]["claim"]
            or archive.get("owned_volume_claim") != quiet["claims"]["volume"]
            or archive.get("container_path") != "/testbed"
        ):
            raise ValueError("Actor baseline/stop evidence is from another original attempt")


def select_managed(selected, row, baseline):
    state = json.loads(selected[STATE])
    artifacts = artifact_paths(state)
    facts = state["projects"]["SOFTWARE27"]["software"]
    case = facts["case"]
    if case["case_id"] != row["instance_id"] or case["active_roles"] != row["fixed_members"]:
        raise ValueError("The committed world belongs to another public task or execution unit")
    bundles = {}
    for alias, (artifact, name) in artifacts.items():
        if digest(selected[name]) != artifact["versions"][artifact["current_version"]]["sha256"]:
            raise ValueError("The committed version content hash differs from the retained bytes")
        bundles[alias] = json.loads(selected[name])
    baseline_tree = _native_tree(baseline)
    if (
        baseline.get("truncated") is not False
        or baseline_tree != baseline["tree"]
        or _native_tree(bundles["baseline"]) != baseline_tree
        or case["initial_binding"]["initial_tree_sha256"]
        != tree_manifest(bundles["baseline"]["files"], bundles["baseline"]["entry_metadata"])[
            "tree_sha256"
        ]
        or case["source_contract"]["source_manifest_sha256"] != digest(selected[MANIFEST])
        or case["initial_binding"]["source_manifest_sha256"] != digest(selected[MANIFEST])
    ):
        raise ValueError("The managed baseline and original actor/source provenance disagree")
    manifest = json.loads(selected[MANIFEST])
    initial = json.loads(selected[INITIAL])
    task = manifest["tasks"][0]
    if (
        len(manifest["tasks"]) != 1
        or task["task_id"] != row["instance_id"]
        or task["initial_tree"]["sha256"] != digest(selected[INITIAL])
        or initial["files"] != bundles["baseline"]["files"]
        or initial["entry_metadata"] != bundles["baseline"]["entry_metadata"]
    ):
        raise ValueError("The original complete source manifest no longer binds the baseline")
    # Use the original provider checks, but only already-materialized evidence
    # whose bytes have just been verified against the full controller stream.
    folder = BATCH / "episodes" / str(row["slot_index"]) / "controller-output/source-snapshot"
    if digest((folder / "source-manifest.json").read_bytes()) != digest(
        selected[MANIFEST]
    ) or digest((folder / "initial-tree.json").read_bytes()) != digest(selected[INITIAL]):
        raise ValueError("Relocated public source evidence differs from the controller archive")
    provider = RepositorySources(folder / "source-manifest.json")
    candidate = bundles["member_001"]
    provider.validate_files(
        row["instance_id"], candidate["files"], entry_metadata=candidate["entry_metadata"]
    )
    native = {
        **candidate,
        "truncated": False,
        "file_policy": copy.deepcopy(case["file_policy"]),
        "gitlinks": copy.deepcopy(baseline.get("gitlinks", [])),
    }
    native["tree"] = _native_tree(native, case["file_policy"])
    member = artifacts["member_001"][0]
    return native, {
        "world_id": state["world_id"],
        "instance_id": state["instance_id"],
        "branch_id": state["branch_id"],
        "state_revision": state["state_revision"],
        "committed_operations": len(state["operation_commits"]),
        "source_reference": {
            "object_id": member["artifact_id"],
            "version_id": member["current_version"],
        },
        "source_version_metadata": member["versions"][member["current_version"]],
        "baseline_reference": {
            "object_id": artifacts["baseline"][0]["artifact_id"],
            "version_id": artifacts["baseline"][0]["current_version"],
        },
        "legal_delivery_records": len(facts["deliveries"]),
        "last_delivery_source_reference": facts["deliveries"][-1]["source_reference"]
        if facts["deliveries"]
        else None,
        "committed_prefix_validated": True,
        "pending_actions_replayed": False,
    }


def provider_usage(rows):
    """Read actual settled usage while retaining the unpriced original call."""
    ledger = BATCH / "ledgers/pilot.sqlite"
    with sqlite3.connect(ledger.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        result = {}
        for row in rows:
            calls = [dict(item) for item in db.execute(
                "SELECT request_id,condition,usage_id,status,usage_json,settled_nanoyuan,reserved_nanoyuan FROM requests WHERE slot_id=? ORDER BY request_id",
                (row["slot_id"],))]
            uncertain = [c for c in calls if c["status"] == "uncertain"]
            settled = [c for c in calls if c["status"] == "settled"]
            if (len(uncertain) != 1 or len(settled)+len(uncertain) != len(calls)
                    or any(c["condition"] != row["condition_id"] for c in calls)
                    or any(not c["usage_json"] or c["settled_nanoyuan"] is None for c in settled)):
                raise ValueError("Every original unknown must retain exactly its one unresolved request")
            usages = [json.loads(c["usage_json"]) for c in settled]
            result[row["slot_index"]] = {
                "requests": len(calls), "all_settled": False, "usage_complete": False,
                "unresolved_requests": len(uncertain),
                "unresolved_request_ids": [c["request_id"] for c in uncertain],
                "uncertain_reserved_nanoyuan": sum(c["reserved_nanoyuan"] for c in uncertain),
                "input_tokens": sum(u["prompt_tokens"] for u in usages),
                "output_tokens": sum(u["completion_tokens"] for u in usages),
                "total_tokens": sum(u["total_tokens"] for u in usages),
                "total_tokens_is_lower_bound": True,
                "request_records_sha256": digest(json_bytes(calls)),
                "ledger_path": str(ledger), "ledger_rows_changed": False,
            }
        return result


def recover(index, usage):
    if os.getuid() == 0 or index not in TASKS:
        raise PermissionError(
            "Only ordinary-user offline recovery of the 21 declared pilot attempts is allowed"
        )
    folder, output = BATCH / "episodes" / str(index), OUTPUT / str(index)
    if output.exists():
        raise FileExistsError(
            "One supplemental candidate is already selected; never overwrite/reselect it"
        )
    plan_ref = reference(BATCH / "deployment-v143/execution-plan.json")
    rows = [r for r in load(plan_ref)["rows"] if r["slot_index"] == index]
    if len(rows) != 1:
        raise ValueError("Original attempt row is not unique")
    row = rows[0]
    original_ref = reference(folder / "result.json")
    result = load(original_ref)
    refs = {
        "original_result": original_ref,
        "writer_quiescence": result["writer_quiescence"],
        "quiescence": result["quiescence"],
        "controller_transfer": result["controller_output_transfer"],
        "interrupted_actor": result["interrupted_worktree"],
        "baseline_provenance": reference(folder / "baseline-snapshot-provenance.json"),
    }
    writers, quiet, transfer, interrupted, provenance = [
        load(refs[k])
        for k in (
            "writer_quiescence",
            "quiescence",
            "controller_transfer",
            "interrupted_actor",
            "baseline_provenance",
        )
    ]
    validate_original(row, result, writers, quiet, transfer, interrupted, provenance)
    refs["baseline"] = provenance["snapshot"]
    baseline = load(refs["baseline"])
    archive = transfer["archive_storage"]
    if (
        Path(archive["blob"]["path"]).resolve()
        != (folder / "controller-output.tar.zst").resolve()
    ):
        raise ValueError("Only the sole original stopped controller archive may supply source")
    selected, members, sdk = read_managed_archive(archive)
    candidate, binding = select_managed(selected, row, baseline)
    output.mkdir(parents=True, exist_ok=False)
    frozen = {}
    for name, raw in selected.items():
        filename = (
            "managed-state.json"
            if name == STATE
            else "source-manifest.json"
            if name == MANIFEST
            else "source-initial-tree.json"
            if name == INITIAL
            else "committed-baseline.json"
            if name.endswith("/baseline.json")
            else "committed-member.json"
        )
        frozen[name] = write_new(output / filename, raw)
    candidate_ref = write_new(output / "candidate-bundle.json", candidate)
    source = write_new(
        output / "recovery-source.json",
        {
            "version": VERSION,
            "endpoint": ENDPOINT,
            "slot": row,
            "plan": plan_ref,
            "source_module": reference(__file__),
            "original_evidence": refs,
            "controller_archive": archive,
            "archive_members": members,
            "frozen_selected_bytes": frozen,
            "binding": binding,
            "provider_usage": usage,
            "saved_session": sdk,
            "selection_rule": "The sole committed member_001 current_version in the fully stopped controller state; no actor-test-tree substitution, mirror repair, journal replay or score-based choice",
            "full_archive_stream_verified_once": True,
            "original_generation_status": "technical_unknown",
            "original_official_final_candidate": False,
            "old_result_changed": False,
            "model_calls": 0,
            "tool_calls": 0,
            "scoring_calls": 0,
        },
    )
    patch = export_utf8_patch(
        baseline, candidate, output / "candidate.patch", policy=candidate["file_policy"]
    )
    lock = write_new(
        output / "lock.json",
        {
            "version": VERSION,
            "endpoint": ENDPOINT,
            "slot": row,
            "baseline": refs["baseline"],
            "candidate": candidate_ref,
            "patch_receipt": patch,
            "tree_sha256": candidate["tree"]["tree_sha256"],
            "source_reference": binding["source_reference"],
            "recovery_source": source,
            "quiescence": refs["writer_quiescence"],
            "lock_before_grading": True,
            "candidate_selection_after_scoring": False,
            "original_generation_status": "technical_unknown",
            "replaces_original_endpoint": False,
            "model_calls": 0,
            "tool_calls": 0,
            "grading_calls": 0,
        },
    )
    result_ref = write_new(
        output / "recovery-result.json",
        {
            "version": VERSION,
            "status": "supplemental_candidate_locked",
            "endpoint": ENDPOINT,
            **{
                key: row[key]
                for key in ("slot_id", "slot_index", "instance_id", "condition_id", "configuration")
            },
            "original_result": original_ref,
            "candidate_lock": lock,
            "patch": patch["patch"],
            "source": source,
            "candidate_tree_sha256": candidate["tree"]["tree_sha256"],
            "original_generation_status": "technical_unknown",
            "replaces_original_endpoint": False,
            "model_resampling": False,
            "bad_action_replayed": False,
            "model_calls": 0,
            "scoring_calls": 0,
            "round_trip_verified": True,
            "actual_original_tokens": None,
            "known_original_tokens_lower_bound": usage["total_tokens"],
            "original_usage_complete": False,
            "unresolved_original_requests": usage["unresolved_requests"],
        },
    )
    return result_ref


def validate_recovery_result(ref, row):
    """Shallow frozen-source verification; do not decompress/reconstruct again."""
    output = OUTPUT / str(row["slot_index"])
    value = load(ref)
    if (
        Path(ref["path"]).resolve() != (output / "recovery-result.json").resolve()
        or value.get("version") != VERSION
        or value.get("status") != "supplemental_candidate_locked"
        or value.get("endpoint") != ENDPOINT
        or value.get("original_generation_status") != "technical_unknown"
        or value.get("replaces_original_endpoint") is not False
        or value.get("model_resampling") is not False
        or value.get("model_calls") != 0
        or value.get("scoring_calls") != 0
        or value.get("round_trip_verified") is not True
        or any(
            value.get(key) != row[key]
            for key in ("slot_id", "slot_index", "instance_id", "condition_id", "configuration")
        )
        or value.get("original_result")
        != reference(BATCH / "episodes" / str(row["slot_index"]) / "result.json")
    ):
        raise ValueError("Supplemental recovery cannot replace or change the original endpoint")
    lock, source = load(value["candidate_lock"]), load(value["source"])
    evidence = source["original_evidence"]
    records = {key: load(ref) for key, ref in evidence.items()}
    validate_original(
        row,
        records["original_result"],
        records["writer_quiescence"],
        records["quiescence"],
        records["controller_transfer"],
        records["interrupted_actor"],
        records["baseline_provenance"],
    )
    if (
        source.get("source_module") != reference(__file__)
        or source.get("slot") != row
        or source.get("full_archive_stream_verified_once") is not True
        or source.get("controller_archive") != records["controller_transfer"]["archive_storage"]
        or source.get("old_result_changed") is not False
        or source.get("model_calls") != 0
        or source.get("tool_calls") != 0
        or source.get("scoring_calls") != 0
    ):
        raise ValueError("The frozen source audit differs from its original controller transfer")
    # Hash the small compressed blob; only the initial recovery decompresses.
    if (
        stream_reference(source["controller_archive"]["blob"]["path"])
        != source["controller_archive"]["blob"]
    ):
        raise ValueError("The original compressed controller evidence changed")
    frozen = {
        name: checked(member).read_bytes()
        for name, member in source["frozen_selected_bytes"].items()
    }
    if any(
        source["archive_members"][name]
        != {"member": name, "sha256": digest(raw), "bytes": len(raw)}
        for name, raw in frozen.items()
    ):
        raise ValueError("Selected original member bytes changed after the archive audit")
    candidate, binding = select_managed(frozen, row, records["baseline"])
    if (
        binding != source["binding"]
        or load(lock["candidate"]) != candidate
        or lock.get("recovery_source") != value["source"]
        or lock.get("slot") != row
        or lock.get("endpoint") != ENDPOINT
        or lock.get("lock_before_grading") is not True
        or lock.get("candidate_selection_after_scoring") is not False
        or lock.get("tree_sha256") != candidate["tree"]["tree_sha256"]
        or value["candidate_tree_sha256"] != lock["tree_sha256"]
        or lock["patch_receipt"]["patch"] != value["patch"]
        or lock["patch_receipt"]["candidate_tree_sha256"] != lock["tree_sha256"]
        or lock["patch_receipt"]["base_tree_sha256"] != records["baseline"]["tree"]["tree_sha256"]
        or lock["patch_receipt"]["round_trip_verified"] is not True
    ):
        raise ValueError(
            "The frozen candidate/export no longer matches the uniquely selected committed version"
        )
    checked(value["patch"])
    return lock
