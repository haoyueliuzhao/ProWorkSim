"""Preserve and clean only exact orphaned API objects after the v076 owner OOM.

The tool never creates a Docker object, executes a model/test, rewrites an old
result, or changes the money ledger. Every archive is streamed with fixed bounds.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import resource
import shutil
import sqlite3
import subprocess
import tarfile
import time

from proworksim import software_benchmark_dispatch_v066 as original
from proworksim import software_benchmark_api_parent_v076 as parent
from proworksim import software_benchmark_docker_actor_v066 as owned
from proworksim.software_benchmark_archive_storage_v064 import (
    export_compressed_stream,
    open_verified_archive,
    stream_reference,
)
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

ROOT = original.ROOT
OUT = ROOT / "runs/software-benchmark-v080/dead-api-owner-r1"
PROPOSAL = ROOT / "artifacts/software-benchmark-v080/dead-owner-recovery-r1/proposal.json"
EXIT_EVIDENCE = ROOT / "artifacts/software-benchmark-v081/dead-owner-recovery-r1/exit-evidence.json"
API_ROOT = ROOT / "runs/software-benchmark-v076/adaptive-concurrency-r1/api-coordinator"
OLD_UNIT = "proworksim-v076-api.service"
VERSION = "v080-exact-dead-owner-artifact-recovery-r1"
GIB = 1024**3
ROLES = ("actor", "controller", "volume")
PAIR_LIMIT = 33
GRADE_KEY = "score-3536"
CLAIMS = original.BATCH_ROOT / "resource-claims"


def load(ref):
    return json.loads(checked(ref).read_bytes())


def dead_owner():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("Recovery runs as the existing ordinary project user")
    proof = load(reference(EXIT_EVIDENCE))
    if (
        proof.get("unit") != OLD_UNIT
        or proof.get("journal_explicit_oom_kill") is not True
        or proof.get("run_summary_exists") is not False
    ):
        raise PermissionError("The exact original OOM owner evidence is required")
    spec = load(proof["unit_specification"])
    if (
        spec.get("unit") != OLD_UNIT
        or spec.get("user_id") != os.getuid()
        or spec.get("reporting_root") != str(API_ROOT)
        or spec.get("entrypoint", {}).get("path") != str(ROOT / "tools/run_adaptive_v076.py")
    ):
        raise PermissionError("Original user-unit ownership differs")
    result = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            OLD_UNIT,
            "--no-pager",
            "--property=LoadState,ActiveState,SubState,MainPID,ControlGroup",
        ],
        env=user_manager_environment(),
        capture_output=True,
        text=True,
        timeout=20,
    )
    state = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if (
        result.returncode
        or state.get("MainPID") != "0"
        or state.get("ActiveState") not in {"inactive", "failed"}
    ):
        raise PermissionError("The old API owner is not conclusively dead")
    parent.require_qualified()
    return {"exit_evidence": reference(EXIT_EVIDENCE), "observed_unix": time.time(), "state": state}


def claim_refs(index):
    return {
        role: reference(path)
        for role in ROLES
        if (path := CLAIMS / f"{role}-{index}.json").exists()
    }


def prepare():
    owner = dead_owner()
    if PROPOSAL.exists():
        proposal()
        return reference(PROPOSAL)
    rows = {row["slot_id"]: row for row in load(reference(original.PLAN_FILE))["rows"]}
    entries = []
    for path in sorted(CLAIMS.glob("active-actor-*.json")):
        claim = load(reference(path))
        slot = claim.get("spec", {}).get("slot_id", "")
        if ":DEEPSEEK_" not in slot:
            continue
        row = rows[slot]
        if row["model_key"] != "DEEPSEEK" or row["input_plus_output_tokens"] != 5_000_000:
            raise PermissionError("Recovery may address only original 5M API objects")
        refs = claim_refs(row["slot_index"])
        if "actor" not in refs or path.read_bytes() != checked(refs["actor"]).read_bytes():
            raise PermissionError("Active actor is not the exact original claim")
        entries.append({"slot_index": row["slot_index"], "row": row, "claims": refs})
    if len(entries) != PAIR_LIMIT:
        raise ValueError("This scoped recovery expects the audited 33 orphaned API pairs")
    grader = reference(CLAIMS / (GRADE_KEY + ".json"))
    grade = load(grader)
    if (
        grade["spec"]["role"] != "score"
        or grade["key"] != GRADE_KEY
        or ":DEEPSEEK_" not in grade["spec"]["slot_id"]
    ):
        raise PermissionError("The single original orphaned grader differs")
    PROPOSAL.parent.mkdir(parents=True, exist_ok=True)
    return write_new(
        PROPOSAL,
        {
            "version": VERSION,
            "source": reference(__file__),
            "status": "prepared_for_authorized_existing_object_recovery",
            "dead_owner": owner,
            "rows": entries,
            "grader_claim": grader,
            "new_Docker_objects": 0,
            "new_model_or_test_calls": 0,
            "parent_slice_stopped_or_changed": False,
            "models_or_Qwen_touched": False,
            "maximum_parallel_pairs": 2,
            "maximum_address_space_bytes_per_process": 4 * GIB,
            "archive_raw_limit_bytes": 256 * GIB,
            "archive_compressed_limit_bytes": 16 * GIB,
            "shared_host_configuration_changed": False,
            "cash_ledger_modified": False,
        },
    )


def proposal():
    value = load(reference(PROPOSAL))
    if (
        value.get("version") != VERSION
        or value.get("source") != reference(__file__)
        or len(value.get("rows", [])) != PAIR_LIMIT
        or value.get("new_Docker_objects") != 0
    ):
        raise PermissionError("The recovery scope or source changed")
    return value


def client_for(row):
    import docker

    config = load(row["configuration"])
    socket = Path(config["scorer_request_base"]["docker_socket"]).resolve()
    expected = (ROOT / "runs/software-panel-v053/docker/docker.sock").resolve()
    if socket != expected:
        raise PermissionError("Only the existing project Docker interface may be used")
    return docker.DockerClient(base_url="unix://" + str(socket), timeout=60)


def restore_pair(client, entry):
    import docker

    row, refs = entry["row"], entry["claims"]
    pair = owned.OwnedActorPair(
        client, slot_index=row["slot_index"], slot_id=row["slot_id"], instance_id=row["instance_id"]
    )
    absent = []
    for role, ref in refs.items():
        claim = load(ref)
        if (
            claim.get("key") != f"{role}-{row['slot_index']}"
            or claim.get("spec", {}).get("role") != role
            or claim["spec"].get("slot_id") != row["slot_id"]
            or claim["spec"].get("instance_id") != row["instance_id"]
            or Path(ref["path"]).resolve() != CLAIMS / (claim["key"] + ".json")
        ):
            raise PermissionError("Object claim differs from its exact scoped task")
        pair.claims[role], pair.claim_bodies[role] = ref, claim
        try:
            obj = (
                client.volumes.get(claim["docker_name"])
                if role == "volume"
                else client.containers.get(claim["docker_name"])
            )
        except docker.errors.NotFound:
            absent.append({"role": role, "claim": ref, "status": 404, "observed_unix": time.time()})
            continue
        if role == "volume":
            owned.validate_volume(obj, ref, claim)
        else:
            if "volume" not in refs:
                raise PermissionError("An existing API container lacks its original volume claim")
            attrs = owned.validate_container(
                obj, role, ref, claim, load(refs["volume"])["docker_name"]
            )
            parent.validate_container_parent(attrs)
            host = attrs.get("HostConfig", {})
            if host.get("NetworkMode") != "none" or host.get("Privileged") or host.get("Binds"):
                raise PermissionError("Original API object isolation differs")
        pair.objects[role] = obj
    return pair, absent


def archive_summary(storage, *, controller=False):
    """Verify the complete raw stream without retaining a repository in RAM."""
    selected, members = {}, 0
    with open_verified_archive(storage) as source:
        with tarfile.open(fileobj=source, mode="r|") as archive:
            for item in archive:
                members += 1
                # This only reads bounded regular metadata, never extracts paths.
                name = item.name.removeprefix("./")
                if (
                    controller
                    and item.isfile()
                    and name
                    in {
                        "output/controller-result.json",
                        "output/ref-ledger/ledger.json",
                        "output/model-ledger/ledger.json",
                    }
                ):
                    if item.size > 16 * 1024**2:
                        selected[name] = {"metadata_not_loaded": True, "bytes": item.size}
                    else:
                        data = archive.extractfile(item).read()
                        try:
                            value = json.loads(data)
                            selected[name] = {
                                key: value.get(key)
                                for key in (
                                    "status",
                                    "reason",
                                    "model_calls",
                                    "known_actual_tokens",
                                    "complete_actual_tokens",
                                    "uncertain_reserved_tokens",
                                    "attempts",
                                    "decisions",
                                )
                                if key in value
                            }
                        except (ValueError, UnicodeError):
                            selected[name] = {"metadata_decode_unknown": True, "bytes": item.size}
    return {
        "round_trip_verified": True,
        "members": members,
        "selected_metadata": selected,
        "repository_decoded_into_memory": False,
    }


def preserve_archive(container, path, folder, name, *, controller=False):
    import docker

    receipt = folder / (name + ".json")
    if receipt.exists():
        value = load(reference(receipt))
        if value.get("container_id") != container.id or value.get("container_path") != path:
            raise PermissionError("Existing recovery archive belongs to another object")
        if (
            value.get("storage")
            and stream_reference(value["storage"]["blob"]["path"]) != value["storage"]["blob"]
        ):
            raise ValueError("Existing recovery archive bytes changed")
        return reference(receipt)
    if shutil.disk_usage(ROOT).free < 160 * GIB:
        raise RuntimeError("Physical disk safety floor prevents another lossless export")
    try:
        chunks, stat = container.get_archive(path)
    except docker.errors.NotFound:
        return write_new(
            receipt,
            {
                "container_id": container.id,
                "container_path": path,
                "source_path_absent": True,
                "status": 404,
                "observed_unix": time.time(),
            },
        )
    storage = export_compressed_stream(chunks, folder / (name + ".tar.zst"), allowed_root=OUT)
    verified = archive_summary(storage, controller=controller)
    return write_new(
        receipt,
        {
            "container_id": container.id,
            "container_path": path,
            "docker_path_stat": stat,
            "storage": {**storage, "round_trip_verified": True},
            "verification": verified,
            "observed_unix": time.time(),
        },
    )


def existing_controller_archive(entry, container_id):
    old = original.BATCH_ROOT / "episodes" / str(entry["slot_index"])
    for name in ("controller-output-transfer.json", "controller-failure-output-relocation.json"):
        path = old / name
        if not path.exists():
            continue
        value = load(reference(path))
        storage = value.get("archive_storage")
        if storage and storage.get("round_trip_verified") is True:
            transfer = value.get("transfer", {})
            if transfer.get("container_id") != container_id or transfer.get(
                "container_claim"
            ) != entry["claims"].get("controller"):
                raise PermissionError("Original controller archive identifies another owned object")
            if stream_reference(storage["blob"]["path"]) != storage["blob"]:
                raise ValueError("Original verified controller archive changed")
            return {
                "original_transfer": reference(path),
                "storage": storage,
                "existing_verified_archive_reused": True,
            }
    return None


def usage_observation(slot):
    ledger = original.PREDECESSOR_ROOT / "api-budget/ledger.sqlite3"
    with sqlite3.connect(ledger.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        requests = [
            dict(row)
            for row in db.execute(
                "select request_id,status,usage_json,reserved_nanoyuan,settled_nanoyuan from requests where slot_id=?",
                (slot,),
            )
        ]
    known, settled = 0, 0
    for request in requests:
        if request["status"] == "settled":
            settled += 1
            if request["usage_json"]:
                known += json.loads(request["usage_json"]).get("total_tokens", 0)
    return {
        "original_ledger": str(ledger),
        "request_count": len(requests),
        "settled_request_count": settled,
        "known_actual_tokens_lower_bound": known,
        "unknown_or_reserved_request_ids": [
            r["request_id"] for r in requests if r["status"] != "settled"
        ],
        "unknown_usage_is_zero": False,
        "ledger_modified": False,
    }


def retain_quiet_sources(pair, absent):
    """An export failure preserves the unique stopped source, not its CPU lease."""
    retained = []
    for role, obj in pair.objects.items():
        ref, claim = pair.claims[role], pair.claim_bodies[role]
        if role == "volume":
            owned.validate_volume(obj, ref, claim)
            retained.append(
                {
                    "role": role,
                    "name": claim["docker_name"],
                    "claim": ref,
                    "reason": "preserve_unique_source_after_export_failure",
                    "retained_size_bytes": None,
                }
            )
            continue
        attrs = owned.validate_container_identity(obj, ref, claim)
        if (
            attrs.get("State", {}).get("Running") is not False
            or attrs.get("State", {}).get("Pid") != 0
        ):
            raise RuntimeError("Cannot release execution capacity for a live retained source")
        cgroup = Path("/sys/fs/cgroup") / parent.SLICE / ("docker-" + obj.id + ".scope")
        if cgroup.exists():
            raise RuntimeError("The stopped retained source still has a parent child cgroup")
        retained.append(
            {
                "role": role,
                "container_id": obj.id,
                "name": claim["docker_name"],
                "claim": ref,
                "running": False,
                "pid": 0,
                "parent_child_cgroup_absent": True,
                "reason": "preserve_unique_source_after_export_failure",
                "retained_size_bytes": None,
            }
        )
    for ref in pair.claims.values():
        original.release_resource(ref, quiescent=True)
    return {
        "quiescent": True,
        "cleanup_errors": [],
        "all_owned_objects_removed": False,
        "retained_objects": retained,
        "absent_objects": absent,
        "claims": pair.claims,
        "create_result_unknown": False,
        "execution_capacity_released": True,
        "foreign_objects_modified": False,
    }


def recover_pair(index):
    dead = dead_owner()
    value = proposal()
    entry = next((item for item in value["rows"] if item["slot_index"] == index), None)
    if entry is None:
        raise PermissionError("Pair is outside the exact 33-task recovery scope")
    folder = OUT / "episodes" / str(index)
    folder.mkdir(parents=True, exist_ok=True)
    completed = folder / "completed.json"
    if completed.exists():
        return reference(completed)
    client = client_for(entry["row"])
    try:
        pair, absent = restore_pair(client, entry)
        stopped = pair.stop_writers()
        if stopped.get("all_quiet") is not True:
            raise RuntimeError("Exact original writers are not quiet")
        writer_path = folder / "writers.json"
        stop_ref = (
            reference(writer_path)
            if writer_path.exists()
            else write_new(writer_path, {"dead_owner": dead, "writers": stopped, "absent": absent})
        )
        captures = {}
        export_error = None
        try:
            if "actor" not in pair.objects and "volume" in pair.objects:
                raise RuntimeError(
                    "Actor missing but source volume remains; retain uncaptured workspace"
                )
            if "controller" in pair.objects:
                existing = existing_controller_archive(entry, pair.objects["controller"].id)
                if existing is not None:
                    existing_path = folder / "controller-existing.json"
                    captures["controller"] = (
                        reference(existing_path)
                        if existing_path.exists()
                        else write_new(existing_path, existing)
                    )
                else:
                    captures["controller"] = preserve_archive(
                        pair.objects["controller"],
                        "/pws/output",
                        folder,
                        "controller-output",
                        controller=True,
                    )
                    if (
                        load(captures["controller"]).get("source_path_absent")
                        and (
                            original.BATCH_ROOT
                            / "episodes"
                            / str(index)
                            / "model-dispatch-intent.json"
                        ).exists()
                    ):
                        raise RuntimeError(
                            "Dispatched controller output is absent; preserve exact stopped source"
                        )
            if "actor" in pair.objects:
                captures["worktree"] = preserve_archive(
                    pair.objects["actor"], "/testbed", folder, "worktree"
                )
                if load(captures["worktree"]).get("source_path_absent"):
                    raise RuntimeError(
                        "Original task workspace is absent; keep exact stopped objects"
                    )
        except Exception as error:
            export_error = {"type": type(error).__name__, "message": str(error)}
        old_result = original.BATCH_ROOT / "episodes" / str(index) / "result.json"
        usage = usage_observation(entry["row"]["slot_id"])
        evidence = write_new(
            folder / "retained-evidence.json",
            {
                "version": VERSION,
                "row": entry["row"],
                "claims": entry["claims"],
                "writer_boundary": stop_ref,
                "archives": captures,
                "usage_observation": usage,
                "original_result": reference(old_result) if old_result.exists() else None,
                "original_results_modified": False,
                "model_or_test_calls": 0,
                "export_error": export_error,
            },
        )
        cleanup = retain_quiet_sources(pair, absent) if export_error else pair.cleanup()
        if cleanup.get("quiescent") is not True:
            write_new(folder / "cleanup-pending.json", {"cleanup": cleanup, "evidence": evidence})
            raise RuntimeError("Exact original cleanup remains incomplete; evidence retained")
        return write_new(
            completed,
            {
                "version": VERSION,
                "slot_id": entry["row"]["slot_id"],
                "slot_index": index,
                "evidence": evidence,
                "quiescent": True,
                "cleanup_errors": [],
                "cleanup": cleanup,
                "original_result": reference(old_result) if old_result.exists() else None,
                "generation_status": load(reference(old_result)).get("status")
                if old_result.exists()
                else "technical_unknown",
                "technical_reason": None
                if old_result.exists()
                else "generation_owner_OOM_before_durable_result",
                "new_model_calls": 0,
                "replayed_episodes": 0,
                "foreign_objects_modified": False,
                "parent_slice_retained": True,
                "export_pending": export_error is not None,
                "retained_objects": cleanup.get("retained_objects", []),
                "finished_unix": time.time(),
            },
        )
    finally:
        client.close()


def recover_grader():
    import docker

    dead = dead_owner()
    value = proposal()
    claim_ref = value["grader_claim"]
    claim = load(claim_ref)
    folder = OUT / "grading" / GRADE_KEY
    folder.mkdir(parents=True, exist_ok=True)
    completed = folder / "completed.json"
    if completed.exists():
        return reference(completed)
    old = original.GRADING_ROOT / GRADE_KEY
    request_ref = reference(old / "request.json")
    request = load(request_ref)
    row = next(
        row
        for row in load(reference(original.PLAN_FILE))["rows"]
        if row["slot_id"] == request["slot_id"]
    )
    expected = {
        "proworksim.owner": "v066-offline-capability-official-scorer-r1",
        "proworksim.resource": GRADE_KEY,
        "proworksim.plan": claim["plan"]["sha256"],
    }
    client = client_for(row)
    try:
        try:
            container = client.containers.get(claim["docker_name"])
        except docker.errors.NotFound:
            container = None
        archives = {}
        if container is not None:
            attrs = container.attrs
            labels = attrs.get("Config", {}).get("Labels") or {}
            if (
                attrs.get("Image") != claim["spec"]["image_id"]
                or attrs.get("Name", "").lstrip("/") != claim["docker_name"]
                or any(labels.get(key) != value for key, value in expected.items())
                or attrs.get("HostConfig", {}).get("CgroupParent") not in ("", None)
            ):
                raise PermissionError("Orphaned grader ownership differs")
            original_observation = load(reference(old / "official-output/initial-container.json"))
            if original_observation.get("container_id") != container.id:
                raise PermissionError(
                    "Grader container differs from the original initial observation"
                )
            if attrs.get("State", {}).get("Running"):
                container.stop(timeout=10)
            container.reload()
            if (
                container.attrs.get("State", {}).get("Running")
                or container.attrs.get("State", {}).get("Pid") != 0
            ):
                raise RuntimeError("Original grader did not become quiet")
            archives["worktree"] = preserve_archive(container, "/testbed", folder, "worktree")
            archives["eval_script"] = preserve_archive(container, "/eval.sh", folder, "eval-script")
            archives["container_logs"] = write_new(
                folder / "container-logs.txt", container.logs(stdout=True, stderr=True)
            )
        # Existing official logs and original prediction remain exactly in place.
        original_files = [stream_reference(path) for path in old.rglob("*") if path.is_file()]
        retained = write_new(
            folder / "retained-evidence.json",
            {
                "dead_owner": dead,
                "claim": claim_ref,
                "request": request_ref,
                "original_files": original_files,
                "container_archives": archives,
                "new_official_test_calls": 0,
                "original_score_changed": False,
            },
        )
        if container is not None:
            container.remove(force=False)
        original.release_resource(claim_ref, quiescent=True)
        return write_new(
            completed,
            {
                "version": VERSION,
                "resource_key": GRADE_KEY,
                "evidence": retained,
                "quiescent": True,
                "cleanup_errors": [],
                "foreign_objects_modified": False,
                "new_model_calls": 0,
                "new_official_test_calls": 0,
                "original_score_changed": False,
                "official_score_state": "technical_unknown_without_completed_receipt",
                "finished_unix": time.time(),
            },
        )
    finally:
        client.close()


def summarize():
    value = proposal()
    completed = {}
    missing = []
    for item in value["rows"]:
        path = OUT / "episodes" / str(item["slot_index"]) / "completed.json"
        if path.exists():
            completed[item["row"]["slot_id"]] = reference(path)
        else:
            missing.append(item["slot_index"])
    grader = OUT / "grading" / GRADE_KEY / "completed.json"
    return {
        "version": VERSION,
        "completed_pairs": len(completed),
        "missing_pairs": missing,
        "episode_receipts": completed,
        "grader_receipt": reference(grader) if grader.exists() else None,
        "all_quiescent": not missing and grader.exists(),
        "new_model_calls": 0,
        "replayed_episodes": 0,
    }


@contextmanager
def bounded_worker():
    directory = OUT / "worker-locks"
    directory.mkdir(parents=True, exist_ok=True)
    stream = None
    for number in range(2):
        candidate = (directory / f"{number}.lock").open("a+b")
        try:
            fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
            stream = candidate
            break
        except BlockingIOError:
            candidate.close()
    if stream is None:
        raise RuntimeError("The two scoped recovery workers are already occupied")
    try:
        yield
    finally:
        stream.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--pair", type=int)
    mode.add_argument("--grader", action="store_true")
    mode.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    # Each independent process is bounded; caller may run at most two pairs.
    resource.setrlimit(resource.RLIMIT_AS, (4 * GIB, 4 * GIB))
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, set(original.host_cpu_pool()[164:168]))
    if args.prepare or args.summary:
        value = prepare() if args.prepare else summarize()
    else:
        with bounded_worker():
            value = recover_pair(args.pair) if args.pair is not None else recover_grader()
    print(json.dumps(value, ensure_ascii=False))


if __name__ == "__main__":
    main()
