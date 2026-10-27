"""Ordinary-user, single-use wait and exec for the approved v063 supplement."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import threading
import time

from proworksim import software_benchmark_rescore_policy_v063 as policy
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_shared_server_hold_v057 import SharedServerHold

VERSION = "v063-bounded-supplement-waiter-r1"
ROOT = policy.ROOT
WAIT_ROOT = policy.BATCH_ROOT / "waiter"
LAUNCH_PLAN = WAIT_ROOT / "launch-plan.json"
RUNNER = ROOT / "tools/run_diagnostic_rescore_v063.py"
PYTHON = ROOT / ".venv/bin/python"
POLL_SECONDS = 30
MAXIMUM_WAIT_SECONDS = 24 * 60 * 60


def approved_binding():
    """Check frozen scope without prematurely requiring the parent to finish."""
    if os.getuid() == 0 or os.geteuid() == 0:
        raise SharedServerHold("The supplementary waiter must run as the ordinary user")
    ref = reference(policy.AUTHORIZATION_FILE)
    auth = policy.load(ref)
    if (auth.get("version") != policy.VERSION or auth.get("status") != "approved"
            or not isinstance(auth.get("explicit_rootful_authorization"), str)
            or not auth["explicit_rootful_authorization"].strip()
            or auth.get("automatic_release") is not False or auth.get("constraints") != policy.CONSTRAINTS
            or auth.get("plan") != reference(policy.PLAN_FILE)
            or auth.get("proposal") != reference(policy.PROPOSAL_FILE)
            or auth.get("sources") != policy.sources()):
        raise SharedServerHold("Supplementary approval is pending, revoked, closed or source bindings changed")
    return ref


def command():
    return [str(PYTHON), str(RUNNER), "--execute"]


def prepare():
    authorization = approved_binding()
    plan = {
        "version": VERSION, "authorization": authorization,
        "proposal": reference(policy.PROPOSAL_FILE), "waiter": reference(__file__),
        "runner": reference(RUNNER), "python_binary": reference(PYTHON),
        "command": command(), "poll_seconds": POLL_SECONDS,
        "maximum_wait_seconds": MAXIMUM_WAIT_SECONDS,
        "address_space_bytes": policy.CONSTRAINTS["host_process_address_space_bytes"],
        "cpu_affinity": [int(value) for value in policy.cpu_set("grader").split(",")],
        "parent_progress": str(policy.parent.COORDINATOR_RUN_ROOT / "progress.json"),
        "final_admission": "software_benchmark_rescore_policy_v063.require_v063_allowed('v063.run')",
        "existing_services_changed": False, "new_service": False, "new_resource_scope": False,
        "waiter_process_replaced_by_runner": True,
    }
    plan_ref = policy.retain(LAUNCH_PLAN, plan)
    policy.retain(WAIT_ROOT / "intent.json", {
        "version": VERSION, "launch_plan": plan_ref,
        "waiter_command": [str(PYTHON), str(Path(__file__).resolve()), "--wait"],
        "single_use": True,
    })
    return {"launch_plan": plan_ref, "runtime_operations": 0, "waiter_started": False}


def validate_plan(plan):
    if (policy.load(reference(LAUNCH_PLAN)) != plan
            or plan.get("version") != VERSION or plan.get("authorization") != approved_binding()
            or plan.get("proposal") != reference(policy.PROPOSAL_FILE)
            or plan.get("waiter") != reference(__file__) or plan.get("runner") != reference(RUNNER)
            or plan.get("python_binary") != reference(PYTHON) or plan.get("command") != command()
            or plan.get("poll_seconds") != POLL_SECONDS
            or plan.get("maximum_wait_seconds") != MAXIMUM_WAIT_SECONDS
            or plan.get("address_space_bytes") != policy.CONSTRAINTS["host_process_address_space_bytes"]
            or plan.get("cpu_affinity") != [int(value) for value in policy.cpu_set("grader").split(",")]
            or plan.get("parent_progress") != str(policy.parent.COORDINATOR_RUN_ROOT / "progress.json")):
        raise SharedServerHold("The approved waiter launch binding changed")
    return plan


def parent_decision(progress, *, cancelled=False, entered=False):
    """Small pure state decision; closed still needs the complete existing guard."""
    if cancelled:
        return "cancelled"
    if entered:
        return "already_entered"
    if progress.get("failure") is not None or progress.get("phase") == "stopped":
        return "parent_stopped"
    if progress.get("phase") == "closed":
        return "check_admission"
    if progress.get("phase") == "running":
        return "wait"
    return "unrecognized_parent_state"


def bounded_process(plan):
    maximum = plan["address_space_bytes"]
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    finite = [value for value in (soft, hard, maximum) if value != resource.RLIM_INFINITY]
    limit = min(finite)
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    affinity = set(plan["cpu_affinity"])
    if len(affinity) != 4 or not affinity <= os.sched_getaffinity(0):
        raise ValueError("The waiter's four-CPU affinity is unavailable")
    os.sched_setaffinity(0, affinity)
    stat = Path("/proc/self/stat").read_text().rsplit(") ", 1)[1].split()
    return {
        "pid": os.getpid(), "ppid": os.getppid(), "uid": os.getuid(), "euid": os.geteuid(),
        "process_start_ticks": int(stat[19]),
        "boot_id_sha256": hashlib.sha256(Path("/proc/sys/kernel/random/boot_id").read_bytes()).hexdigest(),
        "address_space_bytes": limit, "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "host_configuration_changed": False,
    }


def poll_until_ready(plan, stopped, *, validate=validate_plan, admit=None, read_progress=None,
                     monotonic=time.monotonic, wait=None, entered=None, cancelled=None):
    """Wait at most 24 hours; no Docker, services, GPU or shared-server operations."""
    admit = admit or (lambda: policy.require_v063_allowed("v063.run"))
    read_progress = read_progress or (lambda: json.loads(Path(plan["parent_progress"]).read_bytes()))
    wait = wait or stopped.wait
    entered = entered or (lambda: (policy.COORDINATOR_RUN_ROOT / "execution-started.json").exists())
    cancelled = cancelled or (lambda: (WAIT_ROOT / "cancel.json").exists())
    began = monotonic()
    while True:
        if stopped.is_set() or cancelled():
            return {"status": "cancelled", "dispatch": False}
        validate(plan)
        elapsed = monotonic() - began
        if elapsed >= plan["maximum_wait_seconds"]:
            return {"status": "wait_deadline", "dispatch": False, "elapsed_seconds": elapsed}
        progress = read_progress()
        state = parent_decision(progress, entered=entered())
        if state == "check_admission":
            # This is the original full resource/candidate/source/cleanup gate,
            # not a shortcut based solely on the visible progress counter.
            admit()
            if stopped.is_set() or cancelled() or entered():
                return {"status": "cancelled_or_already_entered", "dispatch": False}
            validate(plan)
            return {"status": "admitted_for_exec", "dispatch": True, "elapsed_seconds": elapsed}
        if state != "wait":
            return {"status": state, "dispatch": False, "elapsed_seconds": elapsed}
        wait(min(plan["poll_seconds"], plan["maximum_wait_seconds"] - elapsed))


def wait_and_exec():
    plan_ref = reference(LAUNCH_PLAN)
    plan = validate_plan(policy.load(plan_ref))
    intent = policy.load(reference(WAIT_ROOT / "intent.json"))
    if intent.get("launch_plan") != plan_ref or intent.get("single_use") is not True:
        raise ValueError("Missing exact single-use waiter intent")
    identity = bounded_process(plan)
    write_new(WAIT_ROOT / "started.json", {
        "version": VERSION, "launch_plan": plan_ref, "started_unix": time.time(), **identity,
    })
    stopped = threading.Event()
    previous = {sig: signal.signal(sig, lambda *_: stopped.set()) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        result = poll_until_ready(plan, stopped)
    except Exception as error:
        result = {"status": "stopped_on_guard", "dispatch": False,
                  "error": {"type": type(error).__name__, "message": str(error)}}
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    result.update(version=VERSION, launch_plan=plan_ref, pid=os.getpid(), finished_wait_unix=time.time(),
                  result_is_scoring_completion=False)
    write_new(WAIT_ROOT / "result.json", result)
    if result["dispatch"] is not True:
        return result
    # Do not spawn a second permanent process: the bounded waiter becomes the
    # already-approved runner, preserving PID/affinity/address-space limits.
    for ref in (plan["runner"], plan["python_binary"]):
        checked(ref)
    env = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE"):
        env.pop(key, None)
    try:
        os.chdir(ROOT)
        os.execve(plan["command"][0], plan["command"], env)
    except Exception as error:
        write_new(WAIT_ROOT / "exec-error.json", {
            "version": VERSION, "pid": os.getpid(), "type": type(error).__name__, "message": str(error),
            "scoring_started": False,
        })
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else wait_and_exec(), ensure_ascii=False))


if __name__ == "__main__":
    main()
