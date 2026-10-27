"""New, pending, three-container scope for one v062 diagnostic-decode exception."""
from __future__ import annotations

import fcntl
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path

from . import software_benchmark_dispatch_v062 as parent
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_shared_server_hold_v057 import SharedServerHold, read_hold

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v063-scoped-diagnostic-rescore-r1"
TASK = "astropy__astropy-14995"
SCORE_KEY = "score-29"
BATCH_ROOT = ROOT / "runs/software-benchmark-v063/diagnostic-rescore-r1"
PLAN_FILE = BATCH_ROOT / "plan.json"
COORDINATOR_RUN_ROOT = BATCH_ROOT / "coordinator"
GRADING_ROOT = BATCH_ROOT / "grading"
AUTHORIZATION_FILE = ROOT / "config/v063-diagnostic-rescore-authorization.json"
PROPOSAL_FILE = ROOT / "artifacts/software-benchmark-v063/rescore-authorization-r1/proposal.json"
OPERATIONS = frozenset("v063." + name for name in (
    "run", "score", "control", "grader.create", "grader.start"))
CONSTRAINTS = {
    "maximum_containers": 3,
    "maximum_control_containers": 2,
    "maximum_score_containers": 1,
    "maximum_named_volumes": 0,
    "active_grader_limit": 1,
    "grader_cpu": 4,
    "grader_memory_bytes": 16 * 1024**3,
    "pids_limit": 512,
    "grader_test_seconds": 1800,
    "grader_lifecycle_seconds": 3600,
    "swap_bytes": 0,
    "network_mode": "none",
    "cap_add": [],
    "cap_drop": ["ALL"],
    "no_new_privileges": True,
    "host_bind_mounts": False,
    "host_devices_or_gpu": False,
    "published_ports": False,
    "public_network": False,
    "new_model_calls": 0,
    "new_model_tokens": 0,
    "candidate_changed": False,
    "official_tests_changed": False,
    "host_configuration_changed": False,
    "old_results_overwritten": False,
    "automatic_replay": False,
    "requires_v062_completed_and_quiescent": True,
    "host_process_address_space_bytes": 4 * 1024**3,
    "host_and_container_share_four_cpu_affinity": True,
}
NEW_SOURCES = (
    "src/proworksim/software_benchmark_rescore_policy_v063.py",
    "src/proworksim/software_benchmark_scorer_v063.py",
    "src/proworksim/software_benchmark_diff_diagnostics_v063.py",
    "tools/run_diagnostic_rescore_v063.py",
)


def load(ref):
    return json.loads(checked(ref).read_bytes())


def retain(path, value):
    path = Path(path)
    if path.exists():
        if json.loads(path.read_bytes()) != value:
            raise ValueError("Immutable v063 preparation changed")
        return reference(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return write_new(path, value)


def sources():
    return parent.sources() + [reference(ROOT / name) for name in NEW_SOURCES]


def expected_plan():
    original = load(reference(parent.PLAN_FILE))
    row = original["rows"][29]
    if row["slot_index"] != 29 or row["instance_id"] != TASK or row["execution_arm"] != "FIX10M":
        raise ValueError("Original exception slot identity differs")
    resources = {key: original["resources"][key] for key in (
        "control-" + TASK + "-gold", "control-" + TASK + "-empty", SCORE_KEY)}
    return {
        "version": VERSION, "root": str(BATCH_ROOT), "constraints": CONSTRAINTS,
        "rows": [row], "resources": resources,
        "environments": {TASK: original["environments"][TASK]},
        "parent_plan": reference(parent.PLAN_FILE),
        "original_score_request": reference(parent.GRADING_ROOT / SCORE_KEY / "request.json"),
        "original_score_receipt": reference(parent.GRADING_ROOT / SCORE_KEY / "receipt.json"),
        "original_score_quiescence": reference(parent.GRADING_ROOT / SCORE_KEY / "quiescence.json"),
        "cpu_set": parent.cpu_set("grader", 0),
        "new_generation": False,
    }


def create_plan():
    value = expected_plan()
    retain(PLAN_FILE, value)
    return value


def cpu_set(role, index=0):
    if role != "grader" or type(index) is not int or index != 0:
        raise ValueError("Only one fixed four-CPU grading lane exists")
    value = load(reference(PLAN_FILE))["cpu_set"]
    cpus = [int(part) for part in value.split(",")]
    if len(set(cpus)) != 4 or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("The fixed four-CPU lane is unavailable")
    return value


def require_parent_quiescent():
    """Read receipts only; never stop, wait on or inspect a shared host service."""
    progress = json.loads((parent.COORDINATOR_RUN_ROOT / "progress.json").read_bytes())
    summary_ref = reference(parent.COORDINATOR_RUN_ROOT / "run-summary.json")
    if (progress.get("phase") != "closed" or progress.get("failure") is not None
            or progress.get("summary") != summary_ref):
        raise SharedServerHold("Wait for the original v062 queue and residents to close normally")
    _validate_parent_cleanup(summary_ref["sha256"])
    return summary_ref


@lru_cache(maxsize=1)
def _validate_parent_cleanup(summary_sha256):
    summary_ref = reference(parent.COORDINATOR_RUN_ROOT / "run-summary.json")
    if summary_ref["sha256"] != summary_sha256:
        raise SharedServerHold("The v062 closure identity changed")
    summary = load(summary_ref)
    if (summary.get("failure") is not None
            or len(summary.get("generation", {})) != 174 or len(summary.get("scores", {})) != 174
            or summary.get("unentered_generation") or summary.get("unentered_controls")
            or summary.get("unentered_scores") or not summary.get("resident_closure")
            or any(item.get("owned_unit_stopped") is not True for item in summary["resident_closure"])):
        raise SharedServerHold("Wait for the original v062 queue and residents to close normally")
    for item in summary["generation"].values():
        result = load(item["result"])
        quiet = load(result["quiescence"])
        if (quiet.get("quiescent") is not True or quiet.get("cleanup_errors")
                or quiet.get("create_result_unknown") is not False):
            raise SharedServerHold("A v062 generation cleanup is unproven")
    quiet_files = list(parent.GRADING_ROOT.glob("*/quiescence.json"))
    if len(quiet_files) != 274:
        raise SharedServerHold("The original 100 controls and 174 scores must all close")
    for path in quiet_files:
        quiet = json.loads(path.read_bytes())
        if (quiet.get("quiescent") is not True or quiet.get("cleanup_errors")
                or quiet.get("create_result_unknown") is not False):
            raise SharedServerHold("A v062 grading cleanup is unproven")
    return True


def require_v063_allowed(operation, *, slot_id=None, instance_id=None):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise SharedServerHold("The host scorer must remain an ordinary-user process")
    if operation not in OPERATIONS or instance_id not in (None, TASK):
        raise SharedServerHold("Operation outside the single-task v063 grading scope")
    try:
        auth = json.loads(AUTHORIZATION_FILE.read_bytes())
    except (OSError, ValueError) as error:
        raise SharedServerHold("The new three-container authorization is unavailable") from error
    if (auth.get("version") != VERSION or auth.get("status") != "approved"
            or not isinstance(auth.get("explicit_rootful_authorization"), str)
            or not auth["explicit_rootful_authorization"].strip()
            or auth.get("automatic_release") is not False or auth.get("constraints") != CONSTRAINTS
            or auth.get("plan") != reference(PLAN_FILE) or auth.get("sources") != sources()
            or auth.get("proposal") != reference(PROPOSAL_FILE)):
        raise SharedServerHold("The exact new v063 grant is pending, closed or changed")
    if read_hold().get("hold") is not True or read_hold().get("release_authorization") is not None:
        raise SharedServerHold("The global incident hold must remain unchanged")
    plan = load(auth["plan"])
    proposal = load(auth["proposal"])
    if (plan != expected_plan() or proposal.get("plan") != auth["plan"]
            or proposal.get("constraints") != CONSTRAINTS or proposal.get("sources") != auth["sources"]
            or proposal.get("operations") != sorted(OPERATIONS)
            or slot_id not in (None, plan["rows"][0]["slot_id"])):
        raise SharedServerHold("Reviewed original candidate or supplementary proposal differs")
    original = load(plan["original_score_receipt"])
    quiet = load(plan["original_score_quiescence"])
    if (original.get("status") != "technical_unknown" or original.get("resolved") is not None
            or original.get("instance_id") != TASK or original.get("resource_key") != SCORE_KEY
            or quiet.get("quiescent") is not True or quiet.get("cleanup_errors")
            or quiet.get("create_result_unknown") is not False):
        raise SharedServerHold("Only the known, cleaned original score-29 exception can be retried")
    cpu_set("grader")
    require_parent_quiescent()
    return auth


def claim_resource(key):
    auth = require_v063_allowed("v063.run")
    plan = load(auth["plan"])
    if key not in plan["resources"]:
        raise ValueError("Only the two controls and score-29 are planned")
    directory = BATCH_ROOT / "resource-claims"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / "allocation.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        claim, lease = directory / (key + ".json"), directory / "active-grader-0.json"
        if claim.exists() or lease.exists():
            raise ValueError("Attempt consumed or the single grading lane remains occupied")
        value = {
            "version": VERSION, "key": key, "spec": plan["resources"][key],
            "authorization": reference(AUTHORIZATION_FILE), "plan": auth["plan"],
            "lease": str(lease), "docker_name": "pws-v063-" + hashlib.sha256(
                (str(BATCH_ROOT) + ":" + key).encode()).hexdigest()[:24],
        }
        data = json.dumps(value, sort_keys=True).encode() + b"\n"
        for path in (claim, lease):
            with path.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return reference(claim)


def release_resource(claim_ref, *, quiescent):
    if quiescent is not True:
        return False
    value = load(claim_ref)
    directory = (BATCH_ROOT / "resource-claims").resolve()
    lease = directory / "active-grader-0.json"
    if (Path(claim_ref["path"]).resolve() != directory / (value.get("key", "") + ".json")
            or value.get("version") != VERSION or value.get("lease") != str(lease)):
        raise ValueError("Foreign resource claim")
    with (directory / "allocation.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if lease.exists():
            if lease.read_bytes() != checked(claim_ref).read_bytes():
                raise ValueError("Another resource owns the lease")
            lease.unlink()
    return True
