"""Prepare/verify one explicitly authorized API-only systemd memory boundary.

Preparation and inspection are read-only or project-local. Creating/stopping the
new system-manager slice requires a separate exact approved grant. No existing
unit, Docker daemon configuration, mount, namespace or other cgroup is changed.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

from . import software_benchmark_dispatch_v066 as original
from .software_benchmark_candidates_v054 import checked, reference, write_new

VERSION = "v076-new-api-only-aggregate-parent-r1"
ROOT = original.ROOT
SLICE = "proworksimv076api.slice"
CGROUP = "/" + SLICE
MEMORY_BYTES = 224 * 1024**3
SWAP_BYTES = 0
TASKS_MAX = 32768
OUT = ROOT / "artifacts/software-benchmark-v076/aggregate-parent-authorization-r1"
PROPOSAL = OUT / "proposal.json"
AUTHORIZATION = OUT / "authorization.json"
RUN = ROOT / "runs/software-benchmark-v076/api-aggregate-parent-r1"
CREATED = RUN / "created.json"
RELEASED = RUN / "released.json"
CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")
PROPERTIES = ("LoadState", "ActiveState", "SubState", "Transient", "ControlGroup", "Description",
              "MemoryMax", "MemorySwapMax", "TasksMax", "MemoryAccounting", "StopWhenUnneeded", "CollectMode")


def creation_command(description):
    properties = [("Description", "s", description), ("MemoryAccounting", "b", "true"),
        ("MemoryMax", "t", str(MEMORY_BYTES)), ("MemorySwapMax", "t", "0"),
        ("TasksMax", "t", str(TASKS_MAX)), ("StopWhenUnneeded", "b", "false"),
        ("CollectMode", "s", "inactive")]
    return ["sudo", "-n", "busctl", "--system", "call", "org.freedesktop.systemd1",
        "/org/freedesktop/systemd1", "org.freedesktop.systemd1.Manager", "StartTransientUnit",
        "ssa(sv)a(sa(sv))", SLICE, "fail", str(len(properties)),
        *[field for row in properties for field in row], "0"]


def stopping_command():
    return ["sudo", "-n", "systemctl", "--system", "stop", SLICE]


def prepare_proposal():
    if PROPOSAL.exists():
        return reference(PROPOSAL)
    token = uuid.uuid4().hex
    description = "ProWorkSim v076 API aggregate boundary " + token
    value = {"version": VERSION, "status": "proposed_not_authorized", "prepared_unix": time.time(),
        "source": reference(__file__), "ordinary_user_id": os.getuid(),
        "slice": SLICE, "cgroup_path": CGROUP, "ownership_token": token, "description": description,
        "new_system_manager_objects": 1, "implicit_parent_slices": [],
        "observed_Docker_cgroup_driver": "systemd", "observed_Docker_cgroup_version": "2",
        "memory_max_bytes": MEMORY_BYTES, "memory_swap_max_bytes": SWAP_BYTES, "tasks_max": TASKS_MAX,
        "CPUQuota_set": False, "per_container_memory_and_CPU_limits_changed": False,
        "applies_only_to_new_API_actor_and_controller_containers": True,
        "Qwen_models_Qwen_containers_and_graders_reparented": False,
        "original_aggregate_hard_max_GiB": {"four_models": 384, "four_Qwen_pairs": 128,
            "two_coordinators": 32, "four_graders": 64, "API_parent": 224, "total": 832},
        "create_command": creation_command(description), "stop_command": stopping_command(),
        "create_requires_exact_name_not_found": True,
        "cleanup_requires_exact_ownership_and_no_child_cgroups_or_processes": True,
        "host_configuration_files_written": [], "existing_units_modified": [],
        "daemon_configuration_or_restart": False, "host_mount_or_network_operations": False,
        "existing_container_or_process_migrations": False, "new_privileged_containers": 0,
        "new_sentinel_or_keeper_processes": 0,
        "operator_approval_required": "Explicit approval for creating and later stopping only this new system-manager slice",
        "official_sources": ["https://docs.docker.com/reference/cli/dockerd/#default-cgroup-parent",
            "https://www.freedesktop.org/software/systemd/man/latest/systemd.slice.html",
            "https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html"]}
    OUT.mkdir(parents=True, exist_ok=True)
    return write_new(PROPOSAL, value)


def approved():
    if not AUTHORIZATION.exists():
        raise PermissionError("The new system-manager API slice has no specific user approval")
    authority = json.loads(checked(reference(AUTHORIZATION)).read_bytes())
    proposal = json.loads(checked(reference(PROPOSAL)).read_bytes())
    if (authority.get("version") != VERSION or authority.get("status") != "approved"
            or authority.get("proposal") != reference(PROPOSAL)
            or authority.get("slice") != SLICE
            or authority.get("allowed_operations") != ["create_new_exact_slice", "inspect_exact_slice", "stop_empty_owned_slice"]
            or not isinstance(authority.get("explicit_user_approval"), str)
            or not authority["explicit_user_approval"].strip()
            or proposal.get("source") != reference(__file__)
            or proposal.get("create_command") != creation_command(proposal["description"])
            or proposal.get("stop_command") != stopping_command()
            or proposal.get("slice") != SLICE or proposal.get("cgroup_path") != CGROUP
            or proposal.get("memory_max_bytes") != MEMORY_BYTES
            or proposal.get("memory_swap_max_bytes") != SWAP_BYTES
            or proposal.get("tasks_max") != TASKS_MAX):
        raise PermissionError("The exact new-object slice grant or immutable proposal differs")
    return authority, proposal


def inspect_systemd(*, runner=subprocess.run, timeout=20):
    # `systemctl show name.slice` calls LoadUnit and can synthesize an inactive
    # empty slice. GetUnit only inspects already loaded state and has no such
    # side effect; this distinction matters before StartTransientUnit("fail").
    deadline = time.monotonic() + timeout
    prefix = ["busctl", "--system", "--json=short", "call", "org.freedesktop.systemd1"]

    def call(arguments):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(prefix + arguments, timeout)
        return runner(prefix + arguments, capture_output=True, text=True,
                      timeout=remaining, env={**os.environ, "LC_ALL": "C"})

    result = call(["/org/freedesktop/systemd1", "org.freedesktop.systemd1.Manager", "GetUnit", "s", SLICE])
    if result.returncode != 0:
        if "Unit " + SLICE + " not loaded." in result.stderr:
            return {"LoadState": "not-found", "ActiveState": "inactive", "SubState": "dead",
                    "Transient": "no", "ControlGroup": ""}
        raise RuntimeError("Cannot inspect the exact system-manager slice via GetUnit")
    response = json.loads(result.stdout)
    expected = "/org/freedesktop/systemd1/unit/" + SLICE.replace(".", "_2e")
    if response.get("type") != "o" or response.get("data") != [expected]:
        raise RuntimeError("GetUnit returned another object identity")
    value = {}
    for interface in ("org.freedesktop.systemd1.Unit", "org.freedesktop.systemd1.Slice"):
        result = call([expected, "org.freedesktop.DBus.Properties", "GetAll", "s", interface])
        if result.returncode != 0:
            raise RuntimeError("The exact slice disappeared or its properties are unreadable")
        fields = json.loads(result.stdout)
        if fields.get("type") != "a{sv}" or len(fields.get("data", [])) != 1:
            raise RuntimeError("The system-manager property reply is malformed")
        for key, variant in fields["data"][0].items():
            if key in PROPERTIES:
                item = variant["data"]
                value[key] = ("yes" if item else "no") if type(item) is bool else str(item)
    if not value.get("LoadState"):
        raise RuntimeError("The exact unit lacks its load state")
    return value


def validate_properties(value, proposal):
    expected = {"LoadState": "loaded", "ActiveState": "active", "Transient": "yes",
        "ControlGroup": CGROUP, "Description": proposal["description"],
        "MemoryMax": str(MEMORY_BYTES), "MemorySwapMax": "0", "TasksMax": str(TASKS_MAX),
        "MemoryAccounting": "yes", "StopWhenUnneeded": "no", "CollectMode": "inactive"}
    if any(value.get(key) != wanted for key, wanted in expected.items()):
        raise PermissionError("The API slice is absent, foreign, inactive, or lacks its exact limits")
    return value


def kernel_boundary(*, cgroup_root=Path("/sys/fs/cgroup")):
    root = Path(cgroup_root).resolve()
    folder = root / SLICE
    if folder.is_symlink() or folder.resolve() != root / SLICE:
        raise PermissionError("Aggregate cgroup path is not the exact new root-level slice")
    values = {name: (folder / name).read_text().strip()
              for name in ("memory.max", "memory.swap.max", "pids.max", "cgroup.procs")}
    if (values["memory.max"] != str(MEMORY_BYTES) or values["memory.swap.max"] != "0"
            or values["pids.max"] != str(TASKS_MAX) or values["cgroup.procs"]):
        raise PermissionError("The aggregate kernel limits differ or direct foreign processes exist")
    return {"cgroup_path": CGROUP, "kernel_limits": values,
            "memory_max_bytes": MEMORY_BYTES, "memory_swap_max_bytes": 0, "tasks_max": TASKS_MAX}


class ParentQualificationUnknown(RuntimeError):
    def __init__(self, observation):
        self.observation = observation
        super().__init__("The single asynchronous slice-start job did not reach proven qualification within 15 seconds")


def wait_qualified(proposal, *, runner=subprocess.run, clock=time.monotonic, sleeper=time.sleep):
    """Wait for the one returned systemd job, never submit a second start."""
    started = clock()
    deadline = started + 15.0
    observed = {"slice": SLICE, "start_commands_resent": 0, "polls": 0}
    while clock() < deadline:
        remaining = deadline - clock()
        if remaining <= 0:
            break
        observed["polls"] += 1
        try:
            properties = inspect_systemd(runner=runner, timeout=min(3.0, remaining))
            observed["last_properties"] = properties
            validate_properties(properties, proposal)
            boundary = kernel_boundary()
            return {"properties": properties, "boundary": boundary,
                    "elapsed_seconds": clock() - started, "polls": observed["polls"],
                    "start_commands_resent": 0}
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
            observed["last_error"] = {"type": type(error).__name__, "message": str(error)}
        remaining = deadline - clock()
        if remaining > 0:
            sleeper(min(.1, remaining))
    observed["elapsed_seconds"] = clock() - started
    raise ParentQualificationUnknown(observed)


def create(*, runner=subprocess.run):
    _, proposal = approved()
    if CREATED.exists() or RELEASED.exists() or (RUN / "create-intent.json").exists():
        raise PermissionError("A consumed parent-creation identity cannot be retried or adopted")
    before = inspect_systemd(runner=runner)
    if before.get("LoadState") != "not-found" or (Path("/sys/fs/cgroup") / SLICE).exists():
        raise PermissionError("Refuse to alter or adopt an existing system-manager object")
    RUN.mkdir(parents=True, exist_ok=True)
    intent = write_new(RUN / "create-intent.json", {"version": VERSION,
        "authorization": reference(AUTHORIZATION), "proposal": reference(PROPOSAL),
        "observed_absence": before, "command": proposal["create_command"], "unix": time.time()})
    result = runner(proposal["create_command"], capture_output=True, text=True, timeout=30)
    outcome = write_new(RUN / "create-result.json", {"intent": intent, "returncode": result.returncode,
        "stdout": result.stdout, "stderr": result.stderr, "unix": time.time()})
    if result.returncode != 0:
        raise RuntimeError("The approved slice creation did not complete; no automatic retry")
    try:
        qualified = wait_qualified(proposal, runner=runner)
    except ParentQualificationUnknown as error:
        write_new(RUN / "qualification-unknown.json", {"version": VERSION,
            "creation_result": outcome, "status": "technical_unknown",
            "reason": "asynchronous_start_not_yet_proven", "observation": error.observation,
            "new_start_commands": 1, "automatic_retry": False, "unix": time.time()})
        raise
    return write_new(CREATED, {"version": VERSION, "authorization": reference(AUTHORIZATION),
        "proposal": reference(PROPOSAL), "creation_result": outcome,
        "properties": qualified["properties"], "boundary": qualified["boundary"],
        "asynchronous_start_qualification": qualified, "unix": time.time()})


def require_qualified():
    _, proposal = approved()
    if not CREATED.exists() or RELEASED.exists():
        raise PermissionError("The approved aggregate slice is not qualified and live")
    created = json.loads(checked(reference(CREATED)).read_bytes())
    if (created.get("version") != VERSION or created.get("authorization") != reference(AUTHORIZATION)
            or created.get("proposal") != reference(PROPOSAL)):
        raise PermissionError("Parent qualification does not match this specific grant")
    validate_properties(created["properties"], proposal)
    boundary = kernel_boundary()
    return {"qualification": reference(CREATED), "slice": SLICE, **boundary}


def pressure_probe():
    proof = require_qualified()
    current = int((Path("/sys/fs/cgroup") / SLICE / "memory.current").read_text().strip())
    if current < 0:
        raise ValueError("Aggregate memory accounting is malformed")
    return {"qualified": True, "current_bytes": current, "max_bytes": MEMORY_BYTES,
            "qualification": proof["qualification"], "slice": SLICE}


def container_options(options):
    require_qualified()
    if options.get("cgroup_parent") not in (None, SLICE):
        raise PermissionError("A foreign aggregate parent cannot be replaced")
    return {**options, "cgroup_parent": SLICE}


def validate_container_parent(attrs, *, require_running=False, proc_root=Path("/proc")):
    proof = require_qualified()
    if attrs.get("HostConfig", {}).get("CgroupParent") != SLICE:
        raise PermissionError("The API container was not created under its aggregate slice")
    running, pid, identity = attrs.get("State", {}).get("Running"), attrs.get("State", {}).get("Pid"), attrs.get("Id")
    if require_running and running is not True:
        raise PermissionError("A started API container lacks a running kernel identity")
    if running:
        if type(pid) is not int or pid <= 0 or not isinstance(identity, str) or not CONTAINER_ID.fullmatch(identity):
            raise PermissionError("API container process identity is malformed")
        expected = "0::" + CGROUP + "/docker-" + identity + ".scope"
        if (Path(proc_root) / str(pid) / "cgroup").read_text().splitlines() != [expected]:
            raise PermissionError("The API process is outside the exact aggregate cgroup subtree")
    return proof


def _stop_empty_locked(*, runner):
    _, proposal = approved()
    require_qualified()
    validate_properties(inspect_systemd(runner=runner), proposal)
    active = [json.loads(path.read_bytes()) for path in
              (original.BATCH_ROOT / "resource-claims").glob("active-actor-*.json")]
    if any(":DEEPSEEK_" in item.get("spec", {}).get("slot_id", "") for item in active):
        raise PermissionError("API actor claims remain active, including not-yet-created children")
    folder = Path("/sys/fs/cgroup") / SLICE
    children = [path.name for path in folder.iterdir() if path.is_dir()]
    if children or (folder / "cgroup.procs").read_text().strip():
        raise PermissionError("The parent still contains child cgroups or processes; leave it running")
    if (RUN / "stop-intent.json").exists():
        raise PermissionError("An existing parent-stop attempt must be inspected, not blindly repeated")
    intent = write_new(RUN / "stop-intent.json", {"version": VERSION,
        "qualification": reference(CREATED), "empty_children": children,
        "command": proposal["stop_command"], "unix": time.time()})
    result = runner(proposal["stop_command"], capture_output=True, text=True, timeout=30)
    after = inspect_systemd(runner=runner)
    if result.returncode != 0 or after.get("ActiveState") not in {"inactive", "failed"} or folder.exists():
        raise RuntimeError("Parent stop completion is not proven; original ownership records retained")
    return write_new(RELEASED, {"version": VERSION, "stop_intent": intent,
        "returncode": result.returncode, "after": after, "other_objects_modified": False,
        "unix": time.time()})


def stop_empty(*, runner=subprocess.run):
    # Closing must exclude a concurrent new API claim between empty observation
    # and slice stop, including actors whose containers are not created yet.
    with (original.BATCH_ROOT / "resource-claims/allocation.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _stop_empty_locked(runner=runner)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--inspect", action="store_true")
    group.add_argument("--create-approved", action="store_true")
    group.add_argument("--stop-empty-approved", action="store_true")
    arguments = parser.parse_args()
    value = (prepare_proposal() if arguments.prepare else inspect_systemd() if arguments.inspect
             else create() if arguments.create_approved else stop_empty())
    print(json.dumps(value, ensure_ascii=False))
