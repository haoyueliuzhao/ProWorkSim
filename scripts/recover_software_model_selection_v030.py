"""One explicitly authorized recovery of two pre-inference v030 loading failures.

The completed 9B episode inventory is referenced, never executed again. All
model, numerical, eligibility and screening rules come from the unchanged
canonical worker. Only the evidence-serialization defect and this recovery
controller are new. GPU5 reservation ownership is verified before pidfd release.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import csv
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.storage import digest, read_json
from scripts import software_model_selection_v030 as canonical
from scripts.report_software_model_selection_v030 import report as write_report
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import checked, lock, read, reference, resources, stop_owned, write
from scripts.software_development_v028 import _release_reservation_pid, available_cards

VERSION = "software-model-selection-recovery-v0.30-r1"
RETAINED = canonical.CANDIDATES[0]
REOPENED = canonical.CANDIDATES[1:]
GPU_ORDER = [5, 0, 1, 2, 3, 4, 6, 7]
FAILURE = {"type": "TypeError", "message": "Object of type set is not JSON serializable"}
SOURCE = Path(__file__).resolve().parents[1]
REPORT_PATHS = ["docs/experiments/software-model-selection-v030.md", "docs/experiments/software-model-selection-v030.json"]


def implementation_files():
    return {**canonical._implementation_reference(),
            "scripts/recover_software_model_selection_v030.py": digest(Path(__file__).read_bytes()),
            "scripts/report_software_model_selection_v030.py": digest((SOURCE / "scripts/report_software_model_selection_v030.py").read_bytes())}


def prior_snapshot(prior_root):
    root = Path(prior_root).resolve()
    plan, state = read_json(root / "plan.json"), read_json(root / "supervisor.json")
    if (plan.get("version") != canonical.VERSION or plan.get("candidates") != list(canonical.CANDIDATES)
            or plan.get("inventories") != {candidate: canonical.inventory() for candidate in canonical.CANDIDATES}
            or state.get("status") != "finite_batch_no_qualified_candidate" or not state.get("ended_at")):
        raise ValueError("Recovery is limited to the terminal original three-candidate v030 attempt")
    records = {}
    for candidate in canonical.CANDIDATES:
        actual = root / candidate / "actual"
        record = read_json(actual / "report.json")
        if record.get("source_before") != plan["source"] or record.get("source_after") != plan["source"]:
            raise ValueError("Previous worker source changed or is not completely closed")
        if candidate == RETAINED:
            result = canonical.candidate_result(plan, candidate, record, state["states"][candidate])
            if (state["states"][candidate]["status"] != "complete" or record.get("status") != "complete"
                    or not result["all_12_known"] or not result["qualification_complete"]):
                raise ValueError("Retain the complete original 9B 12-slot inventory, including every failure")
            for row in record["rows"]:
                for key in ("entry", "assessment", "evaluation_guard"):
                    checked(row[key])
        elif (state["states"][candidate]["status"] != "stopped" or record.get("status") != "interrupted_or_error"
              or record.get("error") != FAILURE or record.get("rows") != []
              or (actual / "qualification").exists() or list((actual / "resident/calls").glob("*.json"))):
            raise ValueError("Reopen only the two exact serialization failures before any real model sampling")
        records[candidate] = {"report": reference(actual / "report.json"),
                              "worker_log": reference(root / candidate / "worker.log"),
                              "state": copy.deepcopy(state["states"][candidate]),
                              "actual_directory": str(actual)}
    return {"prior_run_root": str(root), "plan": reference(root / "plan.json"),
            "supervisor": reference(root / "supervisor.json"), "source": plan["source"], "workers": records,
            "prior_artifact_bytes": artifact_bytes(root)}


def make_plan(data_root, qualification, prior_root, reservation_dir=None):
    fresh = canonical.make_plan(data_root, qualification)
    previous = prior_snapshot(prior_root)
    old = read_json(checked(previous["plan"]))
    for key in ("candidates", "inventories", "candidate_profiles", "limits", "selection_rule", "qualification_limits",
                "owner_recipe", "prior_model_plan", "checkpoint_marker", "source_metadata", "download_manifests"):
        if fresh[key] != old[key]:
            raise ValueError("Recovery cannot change the original model/screening/selection protocol: " + key)
    return {"version": VERSION, "attempt_index": 1, "created_at": time.time(), "source": code_identity(),
            "implementation_files_sha256": implementation_files(), "canonical_plan": fresh, "prior": previous,
            "retained_candidates": [RETAINED], "execution_candidates": list(REOPENED),
            "gpu_preference": GPU_ORDER, "max_new_model_instances": 2,
            "new_screening_episodes_max": 24, "cumulative_screening_episodes_max": 36,
            "automatic_additional_recovery": False,
            "authorization": "Explicit user request to reserve free GPU5 and continue the already authorized experiment after the two pre-inference loading failures.",
            "reservation_directory": str(Path(reservation_dir).resolve()) if reservation_dir else None,
            "statistics_scope": "Retained original 9B and two explicitly recovered new-model attempts; logging-only backend repair does not replace outcomes or numerical profiles."}


def validate_plan(plan, *, check_files=True):
    if (plan.get("version") != VERSION or plan.get("attempt_index") != 1
            or plan.get("retained_candidates") != [RETAINED] or plan.get("execution_candidates") != list(REOPENED)
            or plan.get("gpu_preference") != GPU_ORDER or plan.get("max_new_model_instances") != 2
            or plan.get("new_screening_episodes_max") != 24 or plan.get("cumulative_screening_episodes_max") != 36
            or plan.get("automatic_additional_recovery") is not False or not plan.get("authorization")):
        raise ValueError("Only one explicit two-carrier recovery with all original gates is admitted")
    canonical.validate_plan(plan["canonical_plan"], check_files=check_files)
    if check_files:
        if (plan.get("source") != code_identity() or plan.get("implementation_files_sha256") != implementation_files()
                or plan["canonical_plan"]["source"] != plan["source"]):
            raise ValueError("Recovery source must be the exact clean frozen implementation")
        if prior_snapshot(plan["prior"]["prior_run_root"]) != plan["prior"]:
            raise ValueError("Previous original attempts changed after recovery declaration")
        qualification = read_json(checked(plan["canonical_plan"]["qualification"]))
        if qualification.get("passed") is not True or qualification.get("source") != plan["source"]:
            raise ValueError("Require the same-source logging-only repair qualification")
    return plan


def _reservation_records(directory):
    directory = Path(directory)
    launch, state = read(directory / "launch.json"), read(directory / "state.json")
    if not launch or not state or state.get("status") != "reserved":
        return None
    fields = ("pid", "start_ticks", "physical_gpu", "gpu_uuid")
    if (any(launch.get(key) != state.get(key) for key in fields) or state.get("physical_gpu") != 5
            or type(state.get("pid")) is not int or type(state.get("start_ticks")) is not int
            or not launch.get("user_authorization") or state.get("model_calls") != 0):
        raise ValueError("Reservation launch and child state do not bind the same authorized GPU5 process")
    return launch, state


def reservation_ready(directory, *, now=None):
    """The reservation's continuously observed exclusive occupancy supplies 60s."""
    records = _reservation_records(directory)
    if records is None:
        return None
    launch, state = records
    now = time.time() if now is None else now
    identity = worker_identity(launch["pid"])
    if not identity.get("alive") or identity.get("start_ticks") != launch["start_ticks"]:
        return None
    if (now - state.get("ready_at", now) < canonical.LIMITS["gpu_capacity_stability_seconds"]
            or not 0 <= now - state.get("heartbeat_at", 0) <= 15):
        return None
    rows = [json.loads(line) for line in (Path(directory) / "observations.jsonl").read_text().splitlines() if line.strip()]
    rows = [row for row in rows if state["ready_at"] <= row["observed_at"] <= now]
    previous = state["ready_at"]
    for row in rows:
        if (row.get("uuid") != launch["gpu_uuid"] or row.get("pids") != [launch["pid"]]
                or not 0 <= row["observed_at"] - previous <= 15):
            return None
        previous = row["observed_at"]
    if not rows or now - previous > 15:
        return None
    return {"launch": launch, "state": state, "identity": identity,
            "launch_reference": reference(Path(directory) / "launch.json"),
            "observations_reference": reference(Path(directory) / "observations.jsonl"),
            "continuous_exclusive_seconds": now - state["ready_at"]}


def _await_gone(pid, ticks):
    deadline = time.monotonic() + 30
    while True:
        observed = worker_identity(pid)
        if not observed.get("alive") or observed.get("start_ticks") != ticks:
            return observed
        if time.monotonic() >= deadline:
            raise RuntimeError("Owned reservation process did not stop after pidfd SIGTERM")
        time.sleep(0.1)


def consume_reservation(plan, root):
    directory = plan.get("reservation_directory")
    if not directory:
        return None
    proof = reservation_ready(directory)
    if proof is None:
        return None
    launch = proof["launch"]
    sample = resources()
    if any(sample.get(key, {}).get("returncode") != 0 for key in ("gpus", "processes")):
        return None
    gpu_rows = list(csv.reader(io.StringIO(sample["gpus"]["stdout"]), strict=True))
    process_rows = list(csv.reader(io.StringIO(sample["processes"]["stdout"]), strict=True))
    target = [row for row in gpu_rows if len(row) == 6 and row[0].strip() == "5"]
    if (len(target) != 1 or target[0][1].strip() != launch["gpu_uuid"] or "A100" not in target[0][2]
            or float(target[0][4]) < 81920 or any(len(row) != 4 for row in process_rows)
            or [int(row[1]) for row in process_rows if row[0].strip() == launch["gpu_uuid"]] != [launch["pid"]]):
        return None  # A competing process is never signalled or evicted.
    proof.update(status="verified_before_release", resources_before=sample, verified_at=time.time())
    receipt = Path(root) / "reservation-handoff.json"
    write(receipt, proof)
    _release_reservation_pid(launch["pid"], launch["start_ticks"])
    proof.update(identity_after=_await_gone(launch["pid"], launch["start_ticks"]), released_at=time.time(), status="released")
    sample = resources()
    resource_plan = {**plan["canonical_plan"], "gpu_preference": GPU_ORDER}
    card = next((card for card in available_cards(resource_plan, sample) if card["index"] == 5), None)
    proof.update(resources_after=sample, immediate_capacity_available=card is not None,
                 second_empty_card_stability_wait_required=False)
    write(receipt, proof)
    return card


def cancel_reservation(plan, root):
    """Stop only the bound watcher, then its bound child; never other GPU jobs."""
    directory = plan.get("reservation_directory")
    if not directory:
        return
    directory = Path(directory)
    (directory / "cancel").touch()
    receipt = {"reason": "No remaining new candidate needs a reserved GPU", "at": time.time(), "signals": []}
    watcher = read(directory / "watcher-launch.json")
    if watcher:
        current = worker_identity(watcher["pid"])
        if current.get("alive") and current.get("start_ticks") == watcher["start_ticks"]:
            _release_reservation_pid(watcher["pid"], watcher["start_ticks"])
            receipt["signals"].append({"kind": "watcher", "launch": watcher, "after": _await_gone(watcher["pid"], watcher["start_ticks"])})
    child = read(directory / "launch.json")
    if child and child.get("physical_gpu") == 5 and child.get("user_authorization"):
        current = worker_identity(child["pid"])
        if current.get("alive") and current.get("start_ticks") == child["start_ticks"]:
            _release_reservation_pid(child["pid"], child["start_ticks"])
            receipt["signals"].append({"kind": "reservation_child", "launch": child, "after": _await_gone(child["pid"], child["start_ticks"])})
    write(Path(root) / "reservation-cancel.json", receipt)


def supervise(plan_path, root):
    plan = validate_plan(read_json(plan_path))
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    write(root / "recovery-plan.json", plan)
    # These additions are audit metadata; canonical.validate_plan remains strict
    # about every original operational field and accepts neither a new model nor a new slot.
    effective = {**copy.deepcopy(plan["canonical_plan"]), "recovery": {"version": VERSION, "prior": plan["prior"],
                 "retained_candidates": [RETAINED], "execution_candidates": list(REOPENED), "statistics_scope": plan["statistics_scope"]}}
    write(root / "plan.json", effective)
    (root / RETAINED).symlink_to(Path(plan["prior"]["prior_run_root"]) / RETAINED, target_is_directory=True)
    states = {RETAINED: {**copy.deepcopy(plan["prior"]["workers"][RETAINED]["state"]), "retained_original": True}}
    for candidate in REOPENED:
        prior = plan["prior"]["workers"][candidate]["state"]
        states[candidate] = {"candidate_id": candidate, "status": "not_started", "attempted": False,
                             "prior_failed_attempt": copy.deepcopy(prior),
                             "prior_failed_worker_gpu_seconds": prior["elapsed_gpu_seconds"],
                             "elapsed_gpu_seconds": prior["elapsed_gpu_seconds"]}
    summary = {"version": VERSION, "status": "waiting", "started_at": time.time(), "observer_pid": os.getpid(),
               "source": code_identity(), "states": states, "retained_original_source": plan["prior"]["source"],
               "retained_screening_episodes": 12, "max_new_screening_episodes": 24}
    active, logs, guards, stable = {}, {}, {}, {}
    reservation_done = False
    resource_plan = {**effective, "gpu_preference": GPU_ORDER}

    def publish():
        summary["observed_at"] = time.time()
        summary["worker_gpu_seconds"] = sum(state.get("elapsed_gpu_seconds", 0) for state in states.values())
        summary["new_completed_worker_gpu_seconds"] = sum(states[candidate].get("recovery_worker_gpu_seconds", 0) for candidate in REOPENED)
        summary["running_gpu_seconds"] = sum(time.time() - states[candidate]["started_at"] for candidate in active)
        write(root / "supervisor.json", summary)

    def finish(candidate, reason):
        process = active.pop(candidate)
        if process.poll() is None:
            stop_owned(process)
        process.wait(timeout=15)
        result = read(root / candidate / "actual/report.json") or {}
        okay = process.returncode == 0 and reason is None and result.get("status") in {"complete", "qualification_failed"}
        current = states[candidate]
        current.update(status=result["status"] if okay else "stopped", ended_at=time.time(),
                       exit_code=process.returncode, stop_reason=reason)
        current["recovery_worker_gpu_seconds"] = current["ended_at"] - current["started_at"]
        current["elapsed_gpu_seconds"] = current["prior_failed_worker_gpu_seconds"] + current["recovery_worker_gpu_seconds"]
        logs.pop(candidate).close()
        write(root / candidate / "state.json", current)

    def launch(candidate, card, *, reserved=False):
        if code_identity() != plan["source"] or implementation_files() != plan["implementation_files_sha256"]:
            raise ValueError("Frozen recovery implementation changed while queued")
        folder = root / candidate
        folder.mkdir(exist_ok=False)
        argv = [sys.executable, "-m", "scripts.software_model_selection_v030", "worker", "--plan", str(root / "plan.json"),
                "--run-root", str(root), "--output", str(folder / "actual"), "--worker", candidate]
        logs[candidate] = (folder / "worker.log").open("x")
        process = subprocess.Popen(argv, cwd=SOURCE, env=canonical.worker_env(effective, root, candidate, card["index"]),
            stdin=subprocess.DEVNULL, stdout=logs[candidate], stderr=subprocess.STDOUT, start_new_session=True)
        identity = worker_identity(process.pid)
        states[candidate].update(status="running", attempted=True, gpu=card["index"], gpu_uuid=card["uuid"],
            pid=process.pid, process_identity=identity, started_at=time.time(), command=argv, reservation_handoff=reserved)
        active[candidate] = process
        guards[candidate] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
        write(folder / "state.json", states[candidate])
        publish()

    with lock(root):
        try:
            while True:
                now = time.time()
                for candidate, process in list(active.items()):
                    if process.poll() is not None:
                        finish(candidate, None if process.returncode == 0 else "worker_exit_error")
                if all(states[candidate]["status"] in canonical.TERMINAL for candidate in REOPENED):
                    reports = {candidate: read(root / candidate / "actual/report.json") or {} for candidate in canonical.CANDIDATES}
                    selection = canonical.select_candidate(effective, states, reports)
                    selection["recovery"] = {"version": VERSION, "retained_original_source": plan["prior"]["source"], "new_source": plan["source"]}
                    write(root / "selection.json", selection)
                    summary.update(status=selection["status"], selected_candidate=selection["selected_candidate"])
                    break
                waiting = [candidate for candidate in REOPENED if states[candidate]["status"] == "not_started"]
                if waiting and len(active) < 2:
                    if (shutil.disk_usage(root).free < canonical.LIMITS["minimum_volume_free_bytes"]
                            or plan["prior"]["prior_artifact_bytes"] + artifact_bytes(root) > canonical.LIMITS["artifact_bytes"]):
                        raise RuntimeError("Original plus recovery artifacts exceed the unchanged storage gate")
                    if not reservation_done and plan.get("reservation_directory"):
                        card = consume_reservation(plan, root)
                        if (root / "reservation-handoff.json").exists():
                            receipt = read_json(root / "reservation-handoff.json")
                            reservation_done = receipt.get("status") == "released"
                        if card is not None:
                            launch(waiting.pop(0), card, reserved=True)
                    if waiting and len(active) < 2:
                        sample = resources()
                        with (root / "waiting-resources.jsonl").open("a") as stream:
                            stream.write(json.dumps(sample) + "\n")
                        cards = available_cards(resource_plan, sample, [states[candidate]["gpu"] for candidate in active])
                        stable = {card["index"]: stable.get(card["index"], now) for card in cards}
                        for card in cards:
                            if not waiting or len(active) >= 2:
                                break
                            if now - stable[card["index"]] >= canonical.LIMITS["gpu_capacity_stability_seconds"]:
                                launch(waiting.pop(0), card)
                if not waiting and not reservation_done:
                    cancel_reservation(plan, root)
                    reservation_done = True
                if active:
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = {candidate: pool.submit(target_resources, states[candidate]["gpu"], worker_pid=process.pid)
                                   for candidate, process in active.items()}
                        samples = {candidate: future.result() for candidate, future in futures.items()}
                    size = plan["prior"]["prior_artifact_bytes"] + artifact_bytes(root)
                    free = shutil.disk_usage(root).free
                    for candidate, process in list(active.items()):
                        if process.poll() is not None:
                            finish(candidate, None if process.returncode == 0 else "worker_exit_error")
                            continue
                        current = states[candidate]
                        guard = guards[candidate].observe(samples[candidate], time.time(), process.pid, current["gpu"],
                            own_memory_limit_mib=canonical.LIMITS["own_gpu_memory_mib"])
                        running_task = read(root / candidate / "actual/task.json") or {"kind": "loading", "started_at": current["started_at"]}
                        own_rss, reason = rss(process.pid), guard.get("stop_reason")
                        cap = canonical.LIMITS["task_seconds"].get(running_task.get("kind"))
                        if running_task.get("kind") not in canonical.LIMITS["task_seconds"]:
                            reason = "unknown_task_kind"
                        elif cap is not None and time.time() - running_task["started_at"] >= cap:
                            reason = "single_task_budget"
                        elif own_rss > canonical.LIMITS["host_rss_per_worker_bytes"]:
                            reason = "host_memory_budget"
                        elif size > canonical.LIMITS["artifact_bytes"] or free < canonical.LIMITS["minimum_volume_free_bytes"]:
                            reason = "trajectory_storage_reserve"
                        with (root / candidate / "resources.jsonl").open("a") as stream:
                            stream.write(json.dumps({"sample": samples[candidate], "guard": guard, "task": running_task,
                                "rss_bytes": own_rss, "artifact_bytes": size}) + "\n")
                        if reason:
                            finish(candidate, reason)
                summary["status"] = "running" if active else "waiting"
                publish()
                time.sleep(canonical.LIMITS["poll_seconds"])
        except BaseException as error:
            summary.update(status="supervisor_interrupted", error={"type": type(error).__name__, "message": str(error)})
            for candidate in list(active):
                finish(candidate, "supervisor_interrupted")
            raise
        finally:
            if not reservation_done:
                cancel_reservation(plan, root)
            summary["ended_at"] = time.time()
            publish()
    return summary


def finish(plan, run_root, report_repo, *, publish=False):
    state_path = run_root.parent / (run_root.name + "-finish.json")
    state = {"version": VERSION, "status": "supervising", "started_at": time.time(), "run_root": str(run_root)}
    write(state_path, state)
    process = subprocess.run([sys.executable, "-m", "scripts.recover_software_model_selection_v030", "supervise",
                              "--plan", str(plan), "--output", str(run_root)], cwd=SOURCE, check=False)
    state["supervisor_exit_code"] = process.returncode
    if not (run_root / "supervisor.json").exists():
        state.update(status="failed_before_run_archive", ended_at=time.time())
        write(state_path, state)
        return state
    result = write_report(run_root, report_repo / "docs/experiments")
    recovery = read_json(plan)
    result["recovery"] = recovery
    write(report_repo / REPORT_PATHS[1], result)
    markdown = report_repo / REPORT_PATHS[0]
    text = markdown.read_text()
    text = text.replace("# v0.30 O1与代码模型选型运行记录\n", "# v0.30 O1与代码模型选型运行记录\n\n"
        "本记录按本次抢占并接续实验要求进行一次加载故障恢复：9B 的原始 12 槽完整保留，未重跑；仅两新候选在加载证据序列化修复后重新进入资格与原定筛选。旧两次失败原件不改，完整引用见 JSON 的 recovery.prior。\n"
        "9B 来源为 `" + recovery["prior"]["source"]["code_commit"] + "`；恢复来源为 `" + recovery["source"]["code_commit"] + "`。GPU成本包含旧失败尝试及新尝试；预约占用单独留痕。\n")
    markdown.write_text(text)
    state["status"] = "reported"
    write(state_path, state)
    if publish:
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=report_repo, text=True).strip()
        if branch != "main":
            state["publish_status"] = "not_published_repository_branch_changed"
        else:
            subprocess.run(["git", "add", "--", *REPORT_PATHS], cwd=report_repo, check=True)
            changed = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *REPORT_PATHS], cwd=report_repo).returncode
            if changed == 1:
                subprocess.run(["git", "commit", "--only", "-m", "docs: archive explicit v0.30 loading recovery", "--", *REPORT_PATHS], cwd=report_repo, check=True)
            elif changed != 0:
                raise RuntimeError("Cannot determine the fixed recovery report change set")
            state["report_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=report_repo, text=True).strip()
            env = {key: value for key, value in os.environ.items() if key.lower() not in {"http_proxy", "https_proxy", "all_proxy"}}
            attempts = []
            for attempt in range(3):
                pushed = subprocess.run(["git", "push", "origin", "main"], cwd=report_repo, env=env, text=True, capture_output=True, timeout=90)
                attempts.append({"returncode": pushed.returncode, "stdout": pushed.stdout, "stderr": pushed.stderr})
                if pushed.returncode == 0:
                    break
                if attempt < 2:
                    time.sleep(10)
            state.update(publish_status="pushed" if attempts[-1]["returncode"] == 0 else "push_failed", push_attempts=attempts)
    state["ended_at"] = time.time()
    write(state_path, state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "supervise", "finish"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--prior-run-root", type=Path)
    parser.add_argument("--reservation-directory", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--report-repo", type=Path)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if args.mode == "prepare":
        if not all((args.data_root, args.qualification, args.prior_run_root, args.output)):
            parser.error("prepare requires --data-root --qualification --prior-run-root --output")
        write(args.output, validate_plan(make_plan(args.data_root, args.qualification, args.prior_run_root, args.reservation_directory)))
    elif args.mode == "supervise":
        if not args.plan or not args.output:
            parser.error("supervise requires --plan --output")
        supervise(args.plan, args.output)
    else:
        if not all((args.plan, args.run_root, args.report_repo)):
            parser.error("finish requires --plan --run-root --report-repo")
        finish(args.plan.resolve(), args.run_root.resolve(), args.report_repo.resolve(), publish=args.publish)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt("owned recovery supervisor stop")))
    main()
