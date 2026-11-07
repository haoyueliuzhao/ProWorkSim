"""Export completed SDK work after the sole v146/v142 metadata identity failure.

Never resumes a controller, replays a world command, selects another member,
substitutes an actor test tree, or rewrites the original failed host result.
A read-only world facade feeds the real unchanged candidate/delivery validators.
"""

from __future__ import annotations

from contextlib import nullcontext
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import tarfile
from types import SimpleNamespace

from . import software_benchmark_project_closure_v149 as closure
from . import software_benchmark_stopped_recovery_v145 as previous
from .core.journal import validate_committed_prefix
from .repository_sources_v054 import RepositorySources
from .software_benchmark_archive_storage_v064 import open_verified_archive, stream_reference
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .storage import digest, json_bytes

ROOT = Path(__file__).resolve().parents[2]
BATCH = ROOT / "runs/software-benchmark-v146/api-recovery21-r1"
OUTPUT = ROOT / "runs/software-benchmark-v149/closed-export-recovery-r1"
AUDIT = ROOT / "artifacts/software-benchmark-v149/closed-export-recovery-r1"
PLAN = BATCH / "execution-plan.json"
LEDGER = ROOT / "runs/software-benchmark-v145/api-recovery-prepared-r1/ledger.sqlite"
VERSION = "v149-completed-sdk-identity-export-recovery-r1"
STATE, MANIFEST, INITIAL = previous.STATE, previous.MANIFEST, previous.INITIAL
CHILD = "output/controller-result.json"


def load(ref):
    return json.loads(checked(ref).read_bytes())


def validate_completed_work(row, result, child, writers, quiet, transfer):
    closure.validate_slot_identity(row["slot_id"], row["instance_id"], identity=row)
    boundary = child.get("managed_boundary", {})
    ledger = child.get("ledger", {})
    if (
        result.get("status") != "technical_unknown"
        or result.get("candidate_lock") is not None
        or child.get("status") != "technical_unknown"
        or child.get("error")
        != {
            "type": "ValueError",
            "message": "An exact v142 task/organization/seed identity is required",
        }
        or "software_benchmark_project_closure_v141.py" not in child.get("traceback", "")
        or "validate_slot_identity" not in child.get("traceback", "")
        or boundary.get("status") != "bounded_work_closed"
        or boundary.get("execution_integrity_failure") is not None
        or boundary.get("continuation") is not False
        or boundary.get("administrative_censoring") is not False
        or boundary.get("cash_censored") is not False
        or child.get("cash_censored") is not False
        or ledger.get("halted") is not None
        or ledger.get("inflight") is not None
        or ledger.get("uncertain_reserved_tokens") != 0
        or ledger.get("known_actual_tokens") != ledger.get("complete_actual_tokens")
        or any(
            child.get(k) != row[k] or result.get(k) != row[k]
            for k in ("slot_id", "condition_id", "organization_id", "fixed_members")
        )
        or result.get("instance_id") != row["instance_id"]
        or result.get("model_bridge_thread_finished") is not True
        or child.get("hidden_feedback_received") is not False
        or writers.get("all_quiet") is not True
        or writers.get("errors") != []
        or writers.get("create_result_unknown_roles") != []
        or quiet.get("quiescent") is not True
        or quiet.get("all_owned_objects_removed") is not True
        or quiet.get("cleanup_errors") != []
        or quiet.get("retained_objects") != []
        or quiet.get("create_result_unknown") is not False
    ):
        raise ValueError(
            "Only already-bounded-work-closed, solely identity-export-failed evidence may recover"
        )
    by_role = {x["role"]: x for x in writers["writers"]}
    if set(by_role) != {"actor", "controller"} or len(writers["writers"]) != 2:
        raise ValueError("Both original writers must be uniquely stopped")
    for role, item in by_role.items():
        state = item["state"]
        if (
            state.get("Status") != "exited"
            or state.get("Running") is not False
            or state.get("Pid") != 0
            or item["claim"] != quiet["claims"][role]
        ):
            raise ValueError("Writer identity/quiescence is not proven")
    source, storage = transfer["transfer"], transfer["archive_storage"]
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
        raise ValueError("Retained archive is not the original stopped controller output")
    return {
        "sdk_work_closed_before_export": True,
        "original_error_is_only_slot_identity_export": True,
        "closure_reason": boundary["closure_reason"],
        "controller_known_actual_tokens": ledger["known_actual_tokens"],
        "original_failure_status_preserved": True,
        "sdk_or_world_actions_replayed": False,
        "actor_terminal_sync_replayed": False,
        "terminal_candidate_source": "committed_controller_member_001_only",
    }


def _version_name(artifact, version):
    if (
        not isinstance(version, str)
        or not version
        or "/" in version
        or ".." in version
        or not isinstance(artifact.get("artifact_id"), str)
        or "/" in artifact["artifact_id"]
        or artifact.get("kind") != "json"
        or "/" in artifact.get("filename", "")
    ):
        raise ValueError("Unsafe committed version identity")
    return (
        "output/managed-world/world/control/versions/"
        + artifact["artifact_id"]
        + "/"
        + version
        + "/"
        + artifact["filename"]
    )


def wanted_versions(state):
    artifacts = previous.artifact_paths(state)
    selected = {(a["artifact_id"], a["current_version"]): name for a, name in artifacts.values()}
    deliveries = state["projects"]["SOFTWARE27"]["software"]["deliveries"]
    if deliveries:
        source = deliveries[-1]["source_reference"]
        artifact = state["artifacts"][source["object_id"]]
        if (
            artifact["artifact_id"] != artifacts["member_001"][0]["artifact_id"]
            or source["version_id"] not in artifact["versions"]
        ):
            raise ValueError("Last delivery must be an existing original member001 version")
        selected[(source["object_id"], source["version_id"])] = _version_name(
            artifact, source["version_id"]
        )
    return selected


def read_archive(storage):
    selected, proofs = {}, {}
    wanted = {STATE, MANIFEST, INITIAL, CHILD}

    def scan():
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
                        raise ValueError("Archive member escapes the original output tree")
                    name = str(path)
                    if name in seen and name in wanted:
                        raise ValueError("Duplicate required archive member")
                    seen.add(name)
                    if name in wanted and name not in selected:
                        limit = 2 * 1024**3 if name == STATE else 512 * 1024**2
                        if not member.isfile() or member.size > limit:
                            raise ValueError(
                                "Required archive member is not a bounded ordinary file"
                            )
                        raw = archive.extractfile(member).read()
                        selected[name] = raw
                        proofs[name] = {"member": name, "sha256": digest(raw), "bytes": len(raw)}
                        if name == STATE:
                            state = json.loads(raw)
                            validate_committed_prefix(state)
                            wanted.update(wanted_versions(state).values())

    scan()
    if wanted - set(selected):
        scan()
    if wanted - set(selected):
        raise ValueError("The committed closed world has missing selected version bytes")
    state = json.loads(selected[STATE])
    for (object_id, version), name in wanted_versions(state).items():
        if digest(selected[name]) != state["artifacts"][object_id]["versions"][version]["sha256"]:
            raise ValueError("Committed version digest differs from its retained bytes")
    return state, selected, proofs


class FrozenWorld:
    """Read-only state/version adapter: no World constructor or journal replay."""

    def __init__(self, state, selected, control):
        self.state = state
        self.selected = selected
        self.store = SimpleNamespace(
            control=control, lock=lambda: nullcontext(), load=lambda: state
        )

    def _software(self):
        return self.state["projects"]["SOFTWARE27"]["software"]

    def _bundle(self, actor, *, baseline=False, reference=None):
        if actor != "member_001":
            raise ValueError("Only the predeclared delivery member may be exported")
        artifacts = previous.artifact_paths(self.state)
        artifact = artifacts["baseline" if baseline else "member_001"][0]
        version = artifact["current_version"]
        if reference is not None:
            if baseline or reference.get("object_id") != artifact["artifact_id"]:
                raise ValueError("Cross-member or substituted delivery source")
            version = reference["version_id"]
        name = _version_name(artifact, version)
        if name not in self.selected:
            raise ValueError("Only the exact preselected immutable versions may be read")
        return artifact, version, json.loads(self.selected[name])


def provider_usage(row):
    with sqlite3.connect(LEDGER.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        records = [
            dict(r)
            for r in db.execute(
                "SELECT request_id,logical_id,condition,member_id,status,usage_json,"
                "settled_nanoyuan,reserved_nanoyuan,reserved_tokens FROM requests WHERE slot_id=? ORDER BY request_id",
                (row["slot_id"],),
            )
        ]
    if not records or any(
        r["condition"] != row["condition_id"] or r["member_id"] not in row["fixed_members"]
        for r in records
    ):
        raise ValueError("Provider calls lost original new-attempt identity")
    settled = {r["logical_id"] for r in records if r["status"] == "settled"}
    if any(r["status"] == "reserved" or r["logical_id"] not in settled for r in records):
        raise ValueError("An unfinished logical API call is not a pure export failure")
    known = [json.loads(r["usage_json"]) for r in records if r["status"] == "settled"]
    unknown = [r for r in records if r["status"] != "settled"]
    if any(r["status"] != "http_error_uncertain" for r in unknown):
        raise ValueError(
            "Only successfully recovered transient HTTP reservations may accompany closed work"
        )
    return {
        "ledger_path": str(LEDGER),
        "physical_requests": len(records),
        "settled_logical_requests": len(settled),
        "actual_usage_complete": not unknown,
        "known_actual_tokens": sum(u["total_tokens"] for u in known),
        "unknown_tokens_upper": sum(r["reserved_tokens"] for r in unknown),
        "settled_nanoyuan": sum(r["settled_nanoyuan"] for r in records if r["status"] == "settled"),
        "unknown_reserved_nanoyuan": sum(r["reserved_nanoyuan"] for r in unknown),
        "request_records_sha256": digest(json_bytes(records)),
        "unknown_cost_not_filled_with_zero": True,
        "old_requests_changed": False,
    }


def recover(index):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("Ordinary-user offline export only")
    plan_ref = reference(PLAN)
    matches = [r for r in load(plan_ref)["rows"] if r["slot_index"] == index]
    if len(matches) != 1:
        raise ValueError("Unknown independent recovery slot")
    row = matches[0]
    folder = BATCH / "episodes" / str(index)
    out = OUTPUT / str(index)
    if out.exists():
        raise FileExistsError("A closure export may only be locked once")
    refs = {"original_result": reference(folder / "result.json")}
    result = load(refs["original_result"])
    for k in ("controller_result", "writer_quiescence", "quiescence", "controller_output_transfer"):
        refs[k] = result[k]
    child, writers, quiet, transfer = [
        load(refs[k])
        for k in (
            "controller_result",
            "writer_quiescence",
            "quiescence",
            "controller_output_transfer",
        )
    ]
    boundary = validate_completed_work(row, result, child, writers, quiet, transfer)
    usage = provider_usage(row)
    if usage["known_actual_tokens"] != boundary["controller_known_actual_tokens"]:
        raise ValueError("Host provider and closed controller known token totals disagree")
    state, selected, members = read_archive(transfer["archive_storage"])
    if selected[CHILD] != checked(refs["controller_result"]).read_bytes():
        raise ValueError("The controller completion proof differs from its exact retained archive")
    facts = state["projects"]["SOFTWARE27"]["software"]
    case = facts["case"]
    if case["case_id"] != row["instance_id"] or case["active_roles"] != row["fixed_members"]:
        raise ValueError("The closed world belongs to another task or roster")
    source_folder = folder / "controller-output/source-snapshot"
    for name, file in ((MANIFEST, "source-manifest.json"), (INITIAL, "initial-tree.json")):
        if (source_folder / file).read_bytes() != selected[name]:
            raise ValueError("Relocated original source bytes changed")
    provider = RepositorySources(source_folder / "source-manifest.json")
    if case["source_contract"]["source_manifest_sha256"] != digest(selected[MANIFEST]):
        raise ValueError("Closed world source manifest differs")
    out.mkdir(parents=True, exist_ok=False)
    frozen = out / "frozen-original"
    frozen.mkdir()
    retained = {
        name: write_new(frozen / (str(i) + ".json"), raw)
        for i, (name, raw) in enumerate(selected.items())
    }
    control = out / "offline-control"
    control.mkdir()
    facade = FrozenWorld(state, selected, control)
    prepared = SimpleNamespace(world=facade, case=case, source_provider=provider)
    before = digest(json_bytes(state))
    exported = closure.export_managed_closure(
        prepared, out / "closure", slot_id=row["slot_id"], sdk_closed=True, validated_identity=row
    )
    after = digest(json_bytes(state))
    if before != after:
        raise ValueError("Offline export modified the retained world state")
    terminal = exported.pop("terminal_bundle")
    episode_lock = load(exported["controller_candidate_lock"])
    proof = write_new(
        out / "closure-proof.json",
        {
            "version": VERSION,
            "row": row,
            "plan": plan_ref,
            "original_evidence": refs,
            "original_controller_archive": transfer["archive_storage"],
            "archive_members": members,
            "frozen_selected_bytes": retained,
            "closure_adapter": reference(closure.__file__),
            "recovery_implementation": reference(__file__),
            "completion_boundary": boundary,
            "provider_usage": usage,
            "committed_prefix_validated": True,
            "whole_archive_verified": True,
            "state_before_sha256": before,
            "state_after_sha256": after,
            "world_state_changed": False,
            "new_model_calls": 0,
            "new_tool_calls": 0,
            "new_tests": 0,
            "new_grading_calls": 0,
            "original_failure_changed": False,
            "candidate_selection": "Same unique committed member001 current version and last actual legal delivery; no best-of or actor-tree selection",
        },
    )
    value = {
        "version": VERSION,
        "status": "recovered_closed_export",
        "row": row,
        "slot_id": row["slot_id"],
        "slot_index": index,
        "instance_id": row["instance_id"],
        "condition_id": row["condition_id"],
        "configuration": row["configuration"],
        "original_result": refs["original_result"],
        "controller_result": refs["controller_result"],
        "closure_proof": proof,
        "candidate_lock": episode_lock["terminal_code"],
        "delivery_lock": episode_lock["last_legal_delivery"],
        "closure": exported,
        "delivery_evidence": exported["delivery_evidence"],
        "delivery_snapshot": exported["delivery_snapshot"],
        "baseline_snapshot": exported["baseline_snapshot"],
        "submitted": exported["submitted"],
        "same_tree": exported["same_tree"],
        "candidate_tree_sha256": exported["terminal_tree_sha256"],
        "original_status": "technical_unknown",
        "original_status_preserved": True,
        "completed_work_proven_before_export": True,
        "model_resampling": False,
        "new_model_calls": 0,
        "new_tool_calls": 0,
        "new_grading_calls": 0,
        "provider_usage": usage,
    }
    del terminal
    return write_new(out / "recovery-result.json", value)


def validate_export_result_bounded(ref, row):
    """Byte/provenance check for graders; never reparses the large world state."""
    value = load(ref)
    if (
        Path(ref["path"]).resolve() != OUTPUT / str(row["slot_index"]) / "recovery-result.json"
        or value.get("version") != VERSION
        or value.get("status") != "recovered_closed_export"
        or value.get("row") != row
        or value.get("completed_work_proven_before_export") is not True
        or value.get("original_status_preserved") is not True
        or value.get("model_resampling") is not False
        or any(
            value.get(k) != 0 for k in ("new_model_calls", "new_tool_calls", "new_grading_calls")
        )
    ):
        raise ValueError("Completed-export recovery identity changed")
    proof = load(value["closure_proof"])
    refs = proof["original_evidence"]
    records = {k: load(v) for k, v in refs.items()}
    validate_completed_work(
        row,
        records["original_result"],
        records["controller_result"],
        records["writer_quiescence"],
        records["quiescence"],
        records["controller_output_transfer"],
    )
    if (
        proof.get("row") != row
        or proof.get("state_before_sha256") != proof.get("state_after_sha256")
        or proof.get("world_state_changed") is not False
        or proof.get("whole_archive_verified") is not True
        or proof.get("recovery_implementation") != reference(__file__)
        or proof.get("closure_adapter") != reference(closure.__file__)
    ):
        raise ValueError("Offline export proof changed")
    for name, member in proof["frozen_selected_bytes"].items():
        if stream_reference(member["path"]) != member or proof["archive_members"][name] != {
            "member": name,
            "sha256": member["sha256"],
            "bytes": member["bytes"],
        }:
            raise ValueError("Recovered original bytes changed")
    for key in ("candidate_lock", "delivery_lock"):
        if value.get(key):
            lock = load(value[key])
            for field in ("candidate", "tree", "binding", "patch_receipt", "file_policy"):
                checked(lock[field])
            patch = load(lock["patch_receipt"])
            checked(patch["patch"])
            if (
                lock["task_id"] != row["instance_id"]
                or lock.get("lock_before_grading") is not True
                or patch.get("round_trip_verified") is not True
                or lock["tree_sha256"] != patch["candidate_tree_sha256"]
            ):
                raise ValueError("Frozen candidate or exact patch roundtrip identity changed")
    closure.validate_delivery_evidence(
        load(value["delivery_evidence"]),
        load(value["delivery_snapshot"]),
        load(value["baseline_snapshot"]),
    )
    return value
