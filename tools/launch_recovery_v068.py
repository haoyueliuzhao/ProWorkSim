"""Prepare and launch the two bounded recovery coordinators as ordinary user units."""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time

from proworksim import software_benchmark_dispatch_v066 as primary
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

VERSION = "v068-owned-recovery-coordinator-units-r1"
ROLES = ("primary", "api")
UNITS = {"primary": "proworksim-v066-continuation.service", "api": "proworksim-v068-api-continuation.service"}
ENTRYPOINTS = {"primary": "run_full_benchmark_v068.py", "api": "run_api_continuation_v068.py"}


def recovery_scope():
    return importlib.import_module("proworksim.software_benchmark_recovery_scope_v068")


def ordinary_user():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("Recovery launch requires the existing ordinary user manager")


def locations(scope, role):
    if role not in ROLES:
        raise ValueError("Only the primary and API recovery coordinators are launchable")
    folder = Path(scope.PRIMARY_ROOT if role == "primary" else scope.API_ROOT)
    expected_unit = scope.PRIMARY_UNIT if role == "primary" else scope.API_UNIT
    if expected_unit != UNITS[role] or not folder.resolve().is_relative_to(Path(scope.BATCH_ROOT).resolve()):
        raise ValueError("Recovery coordinator scope or unit identity changed")
    return folder, folder / "coordinator-unit.json"


def fixed_spec(scope, role):
    folder, _ = locations(scope, role)
    affinity = ([int(value) for value in primary.cpu_set("coordinator").split(",")]
                if role == "primary" else scope.cpu_affinity())
    if len(affinity) != 4 or len(set(affinity)) != 4:
        raise ValueError("Each recovery coordinator requires its four exact owned CPU lanes")
    return {"version": VERSION, "role": role, "unit": UNITS[role], "user_id": os.getuid(),
        "source": reference(__file__), "entrypoint": reference(Path(scope.ROOT) / "tools" / ENTRYPOINTS[role]),
        "recovery_root": str(scope.BATCH_ROOT), "reporting_root": str(folder),
        "cpu_affinity": affinity, "cpu_quota_percent": 400, "memory_max_bytes": 16 * 1024**3,
        "memory_swap_max_bytes": 0, "tasks_max": 512, "restart": "no",
        "timeout_stop_seconds": 420, "kill_mode": "mixed",
        "existing_user_manager_changed": False, "shared_host_configuration_changed": False}


def validate_spec(scope, spec):
    ordinary_user()
    role = spec.get("role")
    fixed = fixed_spec(scope, role)
    if (set(spec) != set(fixed) | {"ownership_token"}
            or any(spec.get(key) != value for key, value in fixed.items())
            or re.fullmatch(r"[0-9a-f]{32}", spec.get("ownership_token", "")) is None):
        raise ValueError("The prepared owned recovery unit specification changed")
    checked(spec["source"])
    checked(spec["entrypoint"])
    return role


def command(spec, *, scope=None):
    scope = scope or recovery_scope()
    role = validate_spec(scope, spec)
    folder, _ = locations(scope, role)
    return ["systemd-run", "--user", "--collect", "--no-block", "--unit=" + UNITS[role],
        "--description=ProWorkSim v068 " + role + " coordinator " + spec["ownership_token"],
        "--setenv=PYTHONHOME=", "--setenv=PYTHONPATH=", "--setenv=LD_LIBRARY_PATH=", "--setenv=LD_PRELOAD=",
        "--property=Restart=no", "--property=KillMode=mixed", "--property=CPUQuota=400%",
        "--property=CPUAffinity=" + " ".join(map(str, spec["cpu_affinity"])),
        "--property=MemoryMax=16G", "--property=MemorySwapMax=0", "--property=TasksMax=512",
        "--property=OOMPolicy=stop", "--property=TimeoutStopSec=420",
        "--property=WorkingDirectory=" + str(scope.ROOT),
        "--property=StandardOutput=append:" + str(folder / "coordinator.stdout.log"),
        "--property=StandardError=append:" + str(folder / "coordinator.stderr.log"),
        str(Path(scope.ROOT) / ".venv/bin/python"), "-B",
        str(Path(scope.ROOT) / "tools/run_offline_scorer_v058.py"),
        spec["entrypoint"]["path"], "--execute"]


def prepare():
    """Write immutable unit specifications and return commands; contact no manager."""
    ordinary_user()
    scope = recovery_scope()
    prepared = {}
    for role in ROLES:
        folder, path = locations(scope, role)
        if path.exists():
            spec = json.loads(path.read_bytes())
            validate_spec(scope, spec)
        else:
            if (folder / "execution-started.json").exists() or (folder / "launch-intent.json").exists():
                raise ValueError("An entered coordinator cannot acquire a replacement specification")
            spec = {**fixed_spec(scope, role), "ownership_token": secrets.token_hex(16)}
            folder.mkdir(parents=True, exist_ok=True)
            write_new(path, spec)
        prepared[role] = {"specification": reference(path), "command": command(spec, scope=scope)}
    return {"version": VERSION, "units": prepared, "runtime_operations": 0,
        "authorization_required_at_launch": str(scope.AUTHORIZATION_FILE)}


def commands():
    """Inspect existing specifications without creating or changing any artifact."""
    ordinary_user()
    scope = recovery_scope()
    return {role: command(json.loads(locations(scope, role)[1].read_bytes()), scope=scope) for role in ROLES}


def inactive_unit(unit, environment):
    """Prove the exact target is inactive; never stop, replace or reset a unit."""
    result = subprocess.run(["systemctl", "--user", "show", unit,
        "--property=LoadState,ActiveState,SubState,MainPID", "--no-pager"],
        env=environment, capture_output=True, text=True, timeout=15)
    properties = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    inactive = (result.returncode == 0 and properties.get("ActiveState") == "inactive"
                and properties.get("MainPID") == "0")
    if not inactive:
        raise RuntimeError("Recovery target is not proved inactive: " + unit)
    return {"unit": unit, "properties": properties, "observed_unix": time.time()}


def primary_cursor_ready(scope, *, wait_seconds=45):
    deadline = time.monotonic() + wait_seconds
    path = Path(scope.PRIMARY_CURSOR)
    while True:
        if path.is_file():
            cursor = json.loads(path.read_bytes())
            if cursor.get("failure") is not None:
                raise RuntimeError("Recovery primary reported a shared safety failure")
            if (cursor.get("phase") in {"starting", "running", "waiting"}
                    and isinstance(cursor.get("qualifications"), dict)):
                return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(.2)


def launch(role="all"):
    """Start primary first; an API launch error never rolls back the primary."""
    ordinary_user()
    if role not in (*ROLES, "all"):
        raise ValueError("Choose primary, api or all")
    scope = recovery_scope()
    environment = user_manager_environment()
    selected = ROLES if role == "all" else (role,)
    # Validate every requested immutable specification before starting any unit.
    specifications = {}
    for selected_role in selected:
        folder, path = locations(scope, selected_role)
        if (folder / "launch-intent.json").exists() or (folder / "execution-started.json").exists():
            raise ValueError("An entered recovery coordinator is not automatically replayed")
        spec = json.loads(path.read_bytes())
        validate_spec(scope, spec)
        specifications[selected_role] = spec
    records = {}
    for selected_role in selected:
        scope.require_allowed("v068.run" if selected_role == "primary" else "v068.api.run")
        if selected_role == "api" and not primary_cursor_ready(scope):
            return {"version": VERSION, "launched": records,
                "api_status": "waiting_for_primary_cursor", "api_launch_attempted": False,
                "resume_command": "tools/launch_recovery_v068.py --launch --role api"}
        folder, path = locations(scope, selected_role)
        observed = inactive_unit(UNITS[selected_role], environment)
        reservation = scope.reserve_api_coordinator() if selected_role == "api" else None
        argv = command(specifications[selected_role], scope=scope)
        write_new(folder / "launch-intent.json", {"version": VERSION, "specification": reference(path),
            "authorization": reference(scope.AUTHORIZATION_FILE), "inactive_unit_observation": observed,
            "api_coordinator_reservation": reservation, "command": argv})
        # A timeout or failed launch may have created the service. Its reservation
        # stays owned until that exact unit's state and cleanup can be established.
        result = subprocess.run(argv, env=environment, capture_output=True, text=True, timeout=30)
        record = {"version": VERSION, "role": selected_role, "unit": UNITS[selected_role],
            "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
            "specification": reference(path), "api_coordinator_reservation": reservation}
        write_new(folder / "launch-result.json", record)
        records[selected_role] = record
        if result.returncode != 0:
            raise RuntimeError("Owned recovery unit launch failed; inspect its retained launch record: " + UNITS[selected_role])
    return {"version": VERSION, "launched": records, "other_units_stopped_or_restarted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--prepare", action="store_true")
    actions.add_argument("--commands", action="store_true")
    actions.add_argument("--launch", action="store_true")
    parser.add_argument("--role", choices=(*ROLES, "all"), default="all")
    args = parser.parse_args()
    result = prepare() if args.prepare else commands() if args.commands else launch(args.role)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
