"""Four gold and four unchanged-baseline controls for corrected offline fixtures.

Never attaches gold material to an actor, resumes a model, or changes benchmark
scores. Uses the original pinned image/harness/offline resources in fresh runs.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

from proworksim import software_benchmark_queue_v056 as queue
from proworksim import software_benchmark_grading_environment_v058 as environment
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_dispatch_v058 import require_v058_dispatch_allowed
from proworksim.storage import digest

ROOT = Path(__file__).resolve().parents[1]
OLD_RUNS = ROOT / "runs/software-benchmark-v056"
RUNS = ROOT / "runs/software-benchmark-v058"
DEFAULT_ROOT = RUNS / "environment-admission-r1"
STATE = OLD_RUNS / "score-encoding-repair-r1/analysis-r2/source-state.json"
TASKS = ("psf__requests-2931", "psf__requests-1921", "psf__requests-5414", "psf__requests-1766")
VERSION = "v058-offline-requests-fixture-admission-r1"


def load(ref):
    return json.loads(checked(ref).read_bytes())


def validate_plan(plan):
    if (plan.get("version") != VERSION or plan.get("tasks") != list(TASKS)
            or plan.get("model_calls") != 0 or plan.get("preparation_only") is not True
            or plan.get("actor_feedback") is not False or plan.get("concurrency") != 2
            or len(plan.get("rows", [])) != 8 or plan.get("source") != reference(__file__)):
        raise ValueError("Only the fixed four gold and four unchanged controls may run")
    checked(plan["state_source"])
    for source in plan["hold_sources"]:
        checked(source)
    if {(r["instance_id"], r["patch_kind"]) for r in plan["rows"]} != {(task, kind) for task in TASKS for kind in ("gold", "empty")}:
        raise ValueError("Control plan must preserve the complete fixed task panel")
    environment.validate_environment(plan["environment_revision"])
    return plan


def prepare(root):
    require_v058_dispatch_allowed("v058.admission.prepare")
    root = Path(root).resolve()
    if not root.is_relative_to(RUNS) or root == RUNS:
        raise ValueError("Use a fresh independent v058 control directory")
    root.mkdir(parents=True, exist_ok=True)
    path = root / "plan.json"
    if path.exists():
        return validate_plan(load(reference(path)))
    state = json.loads(STATE.read_bytes())
    cpus = sorted(os.sched_getaffinity(0))
    if len(cpus) < 8:
        raise ValueError("Two controls require eight distinct host CPUs")
    rows = []
    for index, (task, kind) in enumerate((task, kind) for task in TASKS for kind in ("gold", "empty")):
        candidates = [row for row in state["rows"] if row["slot"]["instance_id"] == task
                      and row["score"].get("status") == "official_report"]
        original = min(candidates, key=lambda row: row["slot"]["slot_index"])
        request_ref = original["score"]["dispatched_request"]
        request = load(request_ref)
        if request["image"]["instance_id"] != task or request["limits"]["network_mode"] != "none":
            raise ValueError("Original control image/network identity differs")
        lane = index % 2
        rows.append({"instance_id": task, "patch_kind": kind, "original_request": request_ref, "lane": lane,
            "directory": str(root / (task + "-" + kind)),
            "scoring_cpuset_cpus": ",".join(map(str, cpus[lane * 4:(lane + 1) * 4]))})
    plan = {"version": VERSION, "created_utc": queue.now(), "source": reference(__file__),
        "state_source": reference(STATE), "tasks": list(TASKS), "rows": rows,
        "hold_sources": [reference(ROOT / "config/v057-shared-server-hold.json"),
                         reference(ROOT / "src/proworksim/software_benchmark_shared_server_hold_v057.py"),
                         reference(ROOT / "src/proworksim/software_benchmark_dispatch_v058.py"),
                         reference(ROOT / "config/v058-offline-rescore-authorization.json")],
        "environment_revision": environment.freeze_environment(root / "environment-manifest.json"),
        "preparation_only": True, "actor_feedback": False, "model_calls": 0,
        "official_candidate_scores_changed": False, "concurrency": 2,
        "per_score_cpu": 4, "per_score_memory_gib": 16, "network": "none; container-loopback services only",
        "official_test_timeout_seconds": 1800, "outer_timeout_seconds": 3600,
        "positive_control": "fixed dataset official reference patch applied only inside grader"}
    write_new(path, plan)
    return validate_plan(plan)


def worker(plan_ref, index):
    require_v058_dispatch_allowed("v058.admission.worker", instance_id=lambda: load(plan_ref)["rows"][index]["instance_id"])
    # This function runs only inside the installed, frozen official scorer venv.
    from proworksim import software_benchmark_scorer_v054 as base
    from proworksim import software_benchmark_scorer_v056 as scorer
    from proworksim.software_benchmark_baseline_v054 import validate_mapping

    plan = validate_plan(load(plan_ref))
    row = plan["rows"][index]
    if not environment.PROFILES[row["instance_id"]]["admission_enabled"]:
        raise ValueError("This task has unresolved fixed-test TLS requirements")
    original = load(row["original_request"])
    from proworksim.software_benchmark_scorer_v058 import validate_original_request
    original_manifest = validate_original_request(original)
    instance = base.read_local_dataset(original["dataset"])[row["instance_id"]]
    mapping = validate_mapping(load(original["baseline_mapping"]),
                               instance=instance, image=original["image"])
    patch = instance["patch"] if row["patch_kind"] == "gold" else ""
    if not isinstance(patch, str) or (row["patch_kind"] == "gold" and not patch.strip()):
        raise ValueError("Expected the fixed official reference patch")
    patch_bytes = patch.encode("utf-8")
    selected = scorer.resources.cpus(row["scoring_cpuset_cpus"])
    if not set(selected) <= os.sched_getaffinity(0):
        raise ValueError("Control CPUs exceed host affinity")
    folder = Path(row["directory"])
    output = folder / "official-output"
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    identity = {"version": VERSION, "instance_id": row["instance_id"],
        "original_request": row["original_request"], "plan": plan_ref,
        "source": plan["source"], "dataset": original["dataset"], "image": original["image"],
        "baseline_mapping": original["baseline_mapping"], "scorer_manifest": original["scorer_manifest"],
        "limits": original["limits"], "scoring_cpuset_cpus": row["scoring_cpuset_cpus"],
        "gold_patch_sha256": digest(patch_bytes), "gold_patch_bytes": len(patch_bytes),
        "gold_patch_source": "trusted fixed dataset row.patch; grader only",
        "candidate_kind": row["patch_kind"], "environment_revision": plan["environment_revision"], "candidate_tree_identity_claimed": False,
        "preparation_only": True, "actor_feedback": False, "model_calls": 0,
        "official_candidate_scores_changed": False}
    run_id = "v058-env-admission-" + row["patch_kind"] + "-" + digest(base.canonical(identity))[:40]
    write_new(output / "identity.json", identity)
    proof_request = {"slot_id": "environment-control:" + row["instance_id"],
                     "condition_id": "GOLD_ENVIRONMENT_CONTROL"}
    tracking = {"phase": "before_admission", "owned_container_ids": [],
                "create_result_unknown": False, "client": None}
    try:
        socket = Path(original["docker_socket"]).resolve()
        if not socket.is_socket():
            raise ValueError("Private Docker socket is unavailable")
        base.install_offline_guard(socket)
        import docker
        from swebench.harness.run_evaluation import run_instance
        from swebench.harness.utils import make_test_spec
        spec = make_test_spec(instance)
        if any(spec.image_assets.values()):
            raise ValueError("Control cannot download external grading assets")
        os.umask(0o077)
        os.chdir(output)
        for key in ("DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
            os.environ.pop(key, None)
        os.environ["DOCKER_HOST"] = "unix://" + str(socket)
        cli = base.checked_file(original["docker_cli"])
        os.environ["PATH"] = str(cli.parent) + os.pathsep + "/usr/bin:/bin"
        spec.image = original["image"]["image_id"]
        client = docker.DockerClient(base_url=os.environ["DOCKER_HOST"], timeout=1800)
        tracking.update(client=client, phase="official_scoring")
        observation = {"path": str(output / "initial-container.json"),
            "base_commit": mapping["official_head"], "mapping": mapping,
            "mapping_reference": original["baseline_mapping"], "image_id": spec.image,
            "revision": original_manifest, "revision_reference": original["scorer_manifest"],
            "cpuset_cpus": row["scoring_cpuset_cpus"], "environment_revision": plan["environment_revision"]}
        restricted = base.LocalDocker(client, spec.image, scorer.LIMITS)
        restricted.containers = environment.EnvironmentContainers(client.containers, spec.image, scorer.LIMITS,
                                                         observation, tracking=tracking)
        restricted.images.get(spec.image)
        prediction = {"instance_id": row["instance_id"], "model_name_or_path": "GOLD_ENVIRONMENT_CONTROL",
                      "model_patch": patch}
        result = run_instance(spec, prediction, restricted, run_id, timeout=1800,
                              rewrite_reports=False, skip_patch=not patch, task_repo=None)
        report = result[1].get(row["instance_id"], {}) if result else {}
        known = (result is not None and report.get("patch_successfully_applied") is True
                 and not report.get("infra_failure", False) and type(report.get("resolved")) is bool)
        receipt = {"version": VERSION, "run_id": run_id, "instance_id": row["instance_id"],
            "status": "official_report" if known else "technical_unknown",
            "resolved": report["resolved"] if known else None,
            "positive_control_passed": known and report["resolved"] if row["patch_kind"] == "gold" else None,
            "negative_control_passed": known and not report["resolved"] and bool(report.get("tests_status", {}).get("FAIL_TO_PASS", {}).get("failure")) if row["patch_kind"] == "empty" else None,
            "patch_kind": row["patch_kind"], "official_result": result,
            "identity": reference(output / "identity.json"), "preparation_only": True,
            "actor_feedback": False, "model_calls": 0, "official_candidate_scores_changed": False}
        write_new(folder / "receipt.json", receipt)
        tracking["phase"] = "official_scoring_returned"
        return receipt
    finally:
        write_new(folder / "quiescence.json", scorer.cleanup_scoring(proof_request, tracking))


def run_one(root, plan, index):
    rows = plan.get("rows", [])
    row = rows[index] if isinstance(index, int) and 0 <= index < len(rows) else {}
    profile = environment.PROFILES.get(row.get("instance_id"), {})
    # Reporting a known blocker starts no resources and needs no task permission.
    if profile.get("admission_enabled") is False:
        return {"instance_id": row["instance_id"], "patch_kind": row["patch_kind"],
                "status": "blocked_environment", "blockers": profile["blockers"]}
    require_v058_dispatch_allowed("v058.admission.run_one", instance_id=lambda: row.get("instance_id"))
    folder = Path(row["directory"])
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    if (folder / "completion.json").exists():
        return load(reference(folder / "completion.json"))
    if (folder / "started.json").exists():
        return {"instance_id": row["instance_id"], "status": "deferred", "reason": "No automatic replay"}
    validate_plan(plan)
    argv = [str(ROOT / ".venv/bin/python"), "-B", str(ROOT / "tools/run_offline_scorer_v058.py"),
        str(Path(__file__).resolve()), "--worker",
        str(root / "plan.json"), "--worker-index", str(index)]
    started = {"version": VERSION, "instance_id": row["instance_id"], "started_utc": queue.now(),
               "command": argv, "model_calls": 0, "preparation_only": True}
    write_new(folder / "started.json", started)
    start = time.monotonic()
    process = None
    result = dict(started)
    try:
        with (folder / "stdout.log").open("xb") as stdout, (folder / "stderr.log").open("xb") as stderr:
            process = subprocess.Popen(argv, cwd=ROOT, stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            result["returncode"] = process.wait(timeout=3600)
        result["status"] = "process_exited"
    except Exception as error:
        result.update(status="technical_unknown", error=str(error))
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=20)
    result.update(finished_utc=queue.now(), elapsed_seconds=time.monotonic() - start)
    write_new(folder / "completion.json", result)
    return result


def execute(root):
    require_v058_dispatch_allowed("v058.admission.execute")
    root = Path(root).resolve()
    plan = prepare(root)
    if shutil.disk_usage(ROOT).free < 256 * queue.GIB:
        raise RuntimeError("Preserve the 128 GiB floor plus two 64 GiB reservations")
    available = next(int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()
                     if line.startswith("MemAvailable:"))
    if available < 160 * queue.GIB:
        raise RuntimeError("Preserve 128 GiB available memory beyond two 16 GiB controls")

    def lane(number):
        results = []
        with queue.lock(OLD_RUNS / "queue-resource-locks" / f"grader-{number}.lock"):
            for index, row in enumerate(plan["rows"]):
                if row["lane"] != number:
                    continue
                outcome = run_one(root, plan, index)
                results.append(outcome)
                if outcome.get("status") == "blocked_environment":
                    continue
                proof = Path(row["directory"]) / "quiescence.json"
                try:
                    quiet = json.loads(proof.read_bytes()) if proof.exists() else {}
                except (OSError, ValueError):
                    quiet = {}
                if quiet.get("quiescent") is not True or quiet.get("cleanup_errors"):
                    break
                # A failed but quiescent control does not cancel other task controls.
        return results

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(lane, index) for index in (0, 1)]
        results = []
        for index, future in enumerate(futures):
            try:
                results.extend(future.result())
            except Exception as error:
                results.append({"lane": index, "status": "technical_unknown", "error": str(error)})
    record = {"version": VERSION, "finished_utc": queue.now(), "results": results,
              "preparation_only": True, "model_calls": 0, "official_candidate_scores_changed": False}
    path = root / "summary.json"
    if not path.exists():
        write_new(path, record)
    collect_qualifications(root)
    return record


def collect_qualifications(root):
    """No resource starts. Evaluate each fixed task's two original control receipts."""
    from proworksim import software_benchmark_grading_qualification_v058 as qualification
    root = Path(root).resolve()
    plan_ref = reference(root / "plan.json")
    plan = validate_plan(load(plan_ref))
    results = {}
    for task in TASKS:
        if not environment.PROFILES[task]["admission_enabled"]:
            results[task] = {"status": "not_qualified",
                             "reason": "; ".join(environment.PROFILES[task]["blockers"])}
            continue
        directory = root / "task-qualifications" / task
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "qualification.json"
        try:
            rows = [row for row in plan["rows"] if row["instance_id"] == task]
            controls = []
            for row in rows:
                folder = Path(row["directory"])
                controls.append({"instance_id": task, "patch_kind": row["patch_kind"],
                    "original_request": row["original_request"],
                    "receipt": reference(folder / "receipt.json"),
                    "identity": reference(folder / "official-output/identity.json"),
                    "quiescence": reference(folder / "quiescence.json"),
                    "completion": reference(folder / "completion.json"),
                    "initial_container": reference(folder / "official-output/initial-container.json")})
            value = {"version": qualification.VERSION, "instance_id": task,
                "tasks": list(TASKS), "passed": True, "controls": controls,
                "plan": plan_ref, "environment_revision": plan["environment_revision"],
                "model_calls": 0, "official_scores_changed": False}
            candidate = directory / "qualification-proposal.json"
            if not candidate.exists():
                write_new(candidate, value)
            elif load(reference(candidate)) != value:
                raise ValueError("Existing qualification proposal differs; use a new admission root")
            qualification.validate_qualification(reference(candidate), load(rows[0]["original_request"]))
            if not target.exists():
                write_new(target, value)
            elif load(reference(target)) != value:
                raise ValueError("Published task qualification differs")
            results[task] = {"status": "qualified", "qualification": reference(target)}
        except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
            results[task] = {"status": "not_qualified", "reason": str(error)}
    summary = {"version": VERSION, "plan": plan_ref, "tasks": results,
               "planned_tasks": len(TASKS), "qualified_tasks": sum(r["status"] == "qualified" for r in results.values()),
               "model_calls": 0, "resources_started_by_collection": 0}
    write_new(root / f"task-qualification-summary-{time.time_ns()}.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--collect", action="store_true", help="Read completed controls and emit task qualifications without launching resources")
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--worker-index", type=int)
    args = parser.parse_args()
    if args.collect and not args.execute and args.worker is None:
        result = collect_qualifications(args.root)
    elif args.execute and not args.collect and args.worker is None:
        result = execute(args.root)
    elif args.worker is not None and not args.execute and not args.collect and args.worker_index in range(8):
        result = worker(reference(args.worker), args.worker_index)
    else:
        parser.error("Use --execute, --collect, or internal --worker PLAN --worker-index N")
    print(json.dumps({key: value for key, value in result.items() if key not in ("official_result", "results")}), flush=True)


if __name__ == "__main__":
    main()
