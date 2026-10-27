"""Prepare or execute the separately authorized three-container score-29 repair."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import time

from proworksim import software_benchmark_rescore_policy_v063 as policy
from proworksim import software_benchmark_scorer_v063 as scorer
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = policy.ROOT
RUN_ROOT = policy.COORDINATOR_RUN_ROOT
VERSION = "v063-serial-diagnostic-rescore-runner-r1"


def fixed_python(arguments):
    return [str(ROOT / ".venv/bin/python"), "-B", str(ROOT / "tools/run_offline_scorer_v058.py"), *arguments]


def bootstrap_environment():
    value = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE"):
        value.pop(key, None)
    return value


def prepare_manifest():
    target = RUN_ROOT / "scorer-manifest.json"
    command = fixed_python(["-c", "import json; from proworksim.software_benchmark_scorer_v063 "
                            "import installation_manifest; print(json.dumps(installation_manifest()))"])
    result = subprocess.run(command, cwd=ROOT, capture_output=True, check=True, timeout=60,
                            env=bootstrap_environment())
    return policy.retain(target, json.loads(result.stdout))


def control_request(kind, manifest):
    if kind not in {"gold", "empty"}:
        raise ValueError("Unexpected control")
    plan = policy.load(reference(policy.PLAN_FILE))
    key = "control-" + policy.TASK + "-" + kind
    folder = policy.GRADING_ROOT / key
    return policy.retain(folder / "request.json", {
        "version": scorer.VERSION, "resource_key": key, "instance_id": policy.TASK,
        "slot_id": None, "plan": reference(policy.PLAN_FILE),
        "configuration": plan["environments"][policy.TASK]["configuration"],
        "patch_kind": kind, "candidate_lock": None, "limits": scorer.LIMITS,
        "scorer_manifest": manifest, "cpuset_cpus": policy.cpu_set("grader"),
        "directory": str(folder), "environment_revision": None, "network_resolution": None,
    })


def prepare():
    plan = policy.create_plan()
    manifest = prepare_manifest()
    controls = [control_request(kind, manifest) for kind in ("gold", "empty")]
    proposal = {
        "version": policy.VERSION, "status": "pending_specific_three_container_authorization",
        "plan": reference(policy.PLAN_FILE), "constraints": policy.CONSTRAINTS,
        "operations": sorted(policy.OPERATIONS), "sources": policy.sources(),
        "scorer_manifest": manifest, "control_requests": controls,
        "original_score_request": plan["original_score_request"],
        "original_candidate_lock": policy.load(plan["original_score_request"])["candidate_lock"],
        "rootful_scope": "Existing project Docker API; exactly two control identities plus one score identity; no replay",
        "order": ["gold", "empty", "original_candidate_if_both_controls_qualified"],
        "start_condition": "v062 all 174 episodes and 274 graders closed with proven cleanup and residents stopped",
        "prior_grant_reused_or_expanded": False,
        "new_generations": 0, "new_model_tokens": 0,
        "official_test_and_score_logic_changed": False,
        "change": "Two diagnostic git-diff decoders only; preserve raw bytes and escape invalid UTF-8 for logging",
        "global_hold_changed": False,
        "shared_host_mount_network_service_driver_changes": False,
    }
    proposal_ref = policy.retain(policy.PROPOSAL_FILE, proposal)
    pending = {
        "version": policy.VERSION, "status": "pending", "explicit_rootful_authorization": None,
        "automatic_release": False, "constraints": policy.CONSTRAINTS,
        "plan": reference(policy.PLAN_FILE), "sources": policy.sources(), "proposal": proposal_ref,
    }
    pending_ref = policy.retain(policy.PROPOSAL_FILE.parent / "pending-authorization.json", pending)
    if not policy.AUTHORIZATION_FILE.exists():
        policy.retain(policy.AUTHORIZATION_FILE, pending)
    return {"proposal": proposal_ref, "pending_authorization": pending_ref, "controls": controls,
            "runtime_operations": 0, "model_calls": 0}


def run_request(ref):
    request = policy.load(ref)
    policy.require_v063_allowed("v063.run", instance_id=policy.TASK)
    folder = Path(request["directory"])
    if (folder / "started.json").exists():
        raise ValueError("An entered grading identity may never be replayed")
    command = fixed_python(["-m", "proworksim.software_benchmark_scorer_v063", "--request", ref["path"]])
    started = {"version": VERSION, "request": ref, "resource_key": request["resource_key"],
               "started_unix": time.time(), "command": command}
    write_new(folder / "started.json", started)
    process = None
    result = dict(started)
    previous = {}

    def interrupt(signum, frame):
        raise InterruptedError("Stop requested for this owned supplementary grading process")

    try:
        previous = {sig: signal.signal(sig, interrupt) for sig in (signal.SIGTERM, signal.SIGINT)}
        with (folder / "stdout.log").open("xb") as stdout, (folder / "stderr.log").open("xb") as stderr:
            process = subprocess.Popen(command, cwd=ROOT, env=bootstrap_environment(),
                                       stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       start_new_session=True)
            result["returncode"] = process.wait(timeout=3900)
            result["status"] = "process_exited"
    except Exception as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)})
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=20)
        result["returncode"] = process.returncode if process is not None else None
    finally:
        for sig, previous_handler in previous.items():
            signal.signal(sig, previous_handler)
    result["finished_unix"] = time.time()
    write_new(folder / "completion.json", result)
    quiet = policy.load(reference(folder / "quiescence.json"))
    if (quiet.get("quiescent") is not True or quiet.get("cleanup_errors")
            or quiet.get("create_result_unknown") is not False):
        raise RuntimeError("Owned cleanup is unproven; do not dispatch another supplementary grader")
    return reference(folder / "completion.json")


def qualify():
    controls = []
    for kind in ("gold", "empty"):
        folder = policy.GRADING_ROOT / ("control-" + policy.TASK + "-" + kind)
        controls.append({"patch_kind": kind,
                         **{name: reference(folder / (name + ".json"))
                            for name in ("receipt", "quiescence", "completion")},
                         "initial_container": reference(folder / "official-output/initial-container.json")})
    value = {"version": scorer.VERSION, "instance_id": policy.TASK, "plan": reference(policy.PLAN_FILE),
             "controls": controls, "passed": True, "model_calls": 0}
    proposal = policy.retain(RUN_ROOT / "qualification-proposal.json", value)
    config = policy.load(policy.load(reference(policy.PLAN_FILE))["rows"][0]["configuration"])
    scorer.validate_qualification(proposal, config, reference(policy.PLAN_FILE))
    return policy.retain(RUN_ROOT / "qualification.json", value)


def candidate_request(qualification):
    plan = policy.load(reference(policy.PLAN_FILE))
    old = policy.load(plan["original_score_request"])
    value = dict(old)
    value.update(version=scorer.VERSION, plan=reference(policy.PLAN_FILE),
                 directory=str(policy.GRADING_ROOT / policy.SCORE_KEY), qualification=qualification,
                 scorer_manifest=reference(RUN_ROOT / "scorer-manifest.json"), cpuset_cpus=policy.cpu_set("grader"))
    return policy.retain(policy.GRADING_ROOT / policy.SCORE_KEY / "request.json", value)


def execute():
    auth = policy.require_v063_allowed("v063.run")
    closure = policy.require_parent_quiescent()
    cap = policy.CONSTRAINTS["host_process_address_space_bytes"]
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    cap = cap if hard == resource.RLIM_INFINITY else min(cap, hard)
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    os.sched_setaffinity(0, {int(value) for value in policy.cpu_set("grader").split(",")})
    write_new(RUN_ROOT / "execution-started.json", {
        "version": VERSION, "authorization": reference(policy.AUTHORIZATION_FILE),
        "plan": auth["plan"], "parent_closure": closure, "started_unix": time.time(),
        "host_address_space_limit": cap, "host_cpu_affinity": sorted(os.sched_getaffinity(0)),
    })
    proposal = policy.load(auth["proposal"])
    completions = []
    try:
        for ref in proposal["control_requests"]:
            completions.append(run_request(ref))
        qualification = qualify()
        request = candidate_request(qualification)
        completions.append(run_request(request))
        result = {"status": "closed", "qualification": qualification,
                  "receipt": reference(policy.GRADING_ROOT / policy.SCORE_KEY / "receipt.json")}
    except Exception as error:
        result = {"status": "stopped", "error": {"type": type(error).__name__, "message": str(error)}}
    result.update(version=VERSION, completions=completions, finished_unix=time.time(),
                  model_calls=0, historical_results_overwritten=False, automatic_replay=False)
    write_new(RUN_ROOT / "run-summary.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else execute(), ensure_ascii=False))


if __name__ == "__main__":
    main()
