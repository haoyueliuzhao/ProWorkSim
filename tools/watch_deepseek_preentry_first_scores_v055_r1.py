"""Finite asynchronous first-score driver for six independent pre-entry recoveries.

No generation replay and no attempt-2 scoring. Each original request is consumed
once, after its recovery result and unique candidate have closed. Existing four
DeepSeek grader leases are shared with reconciliation workers.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "runs/software-benchmark-v055/pre-entry-recovery-r1"
OUT = RECOVERY / "first-scoring"
GRADERS = ROOT / "runs/software-benchmark-v055/exception-reconciliation-r1/deepseek-scoring-r1/grader-slots"
SCORER = ROOT / "src/proworksim/software_benchmark_scorer_v055.py"
PLAN_SHA = "b5be9b6a9fa502b3c3606520495a15f491bcefc8982074026e2d8543704b8013"


def now():
    return datetime.now(timezone.utc).isoformat()


def reference(path):
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def checked(item):
    raw = Path(item["path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != item["sha256"]:
        raise ValueError("First-score input identity changed")
    return json.loads(raw)


def write_new(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def lock_file(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        stream.close()
        raise
    return stream


def source_plan():
    OUT.mkdir(parents=True, exist_ok=True)
    plan = {"version": "v055-preentry-first-score-driver-r1", "created_utc": now(),
        "recovery_plan": {"path": str(RECOVERY / "plan.json"), "sha256": PLAN_SHA},
        "driver_source": reference(Path(__file__).resolve()), "original_scorer": reference(SCORER),
        "maximum_graders": 4, "shared_grader_locks": [str(GRADERS / f"{i}.lock") for i in range(4)],
        "only_attempt": 1, "original_request_bytes_preserved": True, "generation_replay": False,
        "maximum_observation_seconds": 10800, "maximum_lease_wait_seconds": 7200,
        "maximum_new_endpoints": 8, "GPU_or_model_calls_by_driver": 0}
    checked(plan["recovery_plan"])
    path = OUT / "plan.json"
    write_new(path, plan)
    print(json.dumps(reference(path)))


def validate_request(request, slot, output):
    if (request.get("attempt") != 1 or request.get("slot_id") != slot["slot_id"]
            or request.get("condition_id") != slot["condition_id"]
            or request.get("instance_id") != slot["instance_id"]
            or request.get("actor_feedback") is not False or request.get("preparation_only") is not False
            or request.get("endpoint") not in ("code", "delivery")
            or request.get("endpoint") == "delivery" and not slot["condition_id"].startswith("PROJECT-")):
        raise ValueError("Only the exact recovered slot's first closed-candidate request is allowed")
    if not Path(request["receipt_output"]).resolve().is_relative_to(output):
        raise ValueError("First-score pointer is outside the recovery episode")


def scorer_command(path):
    return [str(ROOT / "tools/run_benchmark_runtime_v054.sh"), "--write-project", "/usr/bin/env",
        "PYTHONPATH=" + str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE=1", "HF_HUB_OFFLINE=1",
        "HF_DATASETS_OFFLINE=1", "TRANSFORMERS_OFFLINE=1", "HTTP_PROXY=", "HTTPS_PROXY=", "ALL_PROXY=",
        "http_proxy=", "https_proxy=", "all_proxy=", "NO_PROXY=*", "no_proxy=*", "CUDA_VISIBLE_DEVICES=",
        "NVIDIA_VISIBLE_DEVICES=void", str(ROOT / "runs/software-benchmark-v054/scorer-venv/bin/python"),
        "-B", "-m", "proworksim.software_benchmark_scorer_v055", "--request", str(path)]


def grade(item, driver_lease, plan):
    folder = OUT / "endpoints" / item["request"]["sha256"][:24]
    folder.mkdir(parents=True, exist_ok=True)
    final = folder / "result.json"
    if final.is_file():
        return json.loads(final.read_bytes())
    result = {"slot_id": item["slot_id"], "endpoint": item["endpoint"], "attempt": 1,
              "request": item["request"], "status": "technical_unknown", "new_model_calls": 0}
    try:
        request = checked(item["request"])
        with lock_file(folder / "attempt.lock") as endpoint_lease:
            if (folder / "started.json").exists() or Path(request["receipt_output"]).exists():
                raise ValueError("Existing score intent/pointer is never blindly replayed")
            wait_started = time.monotonic()
            lease = None
            while lease is None:
                if time.monotonic() - wait_started > plan["maximum_lease_wait_seconds"]:
                    raise TimeoutError("No shared grader capacity within finite observation")
                memory = {key: int(value.split()[0]) * 1024 for key, value in
                          (line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())}
                if memory["MemAvailable"] >= 144 * 1024**3 and os.getloadavg()[0] < 140:
                    for lane in range(4):
                        try:
                            lease = lock_file(GRADERS / f"{lane}.lock")
                            break
                        except BlockingIOError:
                            continue
                if lease is None:
                    time.sleep(5)
            with lease:
                write_new(folder / "started.json", {"started_utc": now(), "request": item["request"],
                    "original_request_unchanged": True, "shared_grader_lane": lane,
                    "scientific_attempt": 1, "source_plan": reference(OUT / "plan.json")})
                with (folder / "stdout.log").open("xb") as stdout, (folder / "stderr.log").open("xb") as stderr:
                    child = subprocess.Popen(scorer_command(Path(item["request"]["path"])), cwd=ROOT,
                        stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                        pass_fds=(driver_lease.fileno(), endpoint_lease.fileno(), lease.fileno()))
                    write_new(folder / "child.json", {"pid": child.pid, "observed_utc": now(),
                        "driver_endpoint_and_shared_grader_leases_inherited": True})
                    returncode = child.wait()
                result["returncode"] = returncode
                pointer = Path(request["receipt_output"])
                if returncode != 0 or not pointer.is_file():
                    raise RuntimeError("First official scorer exited without a determinate pointer")
                linked = json.loads(pointer.read_bytes())
                receipt, identity = checked(linked["receipt"]), checked(linked["identity"])
                if (identity.get("slot_id") != request["slot_id"]
                        or identity.get("condition_id") != request["condition_id"]
                        or identity.get("attempt") != 1
                        or identity.get("patch_sha256") != request["patch"]["sha256"]):
                    raise ValueError("Official receipt crossed slot/condition/locked patch/first attempt")
                result["official_pointer"] = reference(pointer)
                if receipt.get("status") == "official_report" and type(receipt.get("resolved")) is bool:
                    result.update(status="official_report", resolved=receipt["resolved"])
                else:
                    result["reason"] = "Original scorer retained technical_unknown; no additional attempt started"
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)}
    result["finished_utc"] = now()
    write_new(final, result)
    return result


def observe_generation(slot):
    sid, output = slot["slot_id"], Path(slot["output_directory"])
    completion = output.parent / "recovery-completion.json"
    if completion.is_file():
        done = json.loads(completion.read_bytes())
        result = checked(done["recovery_result"])
        if done.get("plan_sha256") != PLAN_SHA or done.get("original_slot_id") != sid or result.get("slot_id") != sid:
            raise ValueError("Recovery completion crosses the frozen slot or plan")
        record = {"slot_id": sid, "condition_id": slot["condition_id"],
                  "result": done["recovery_result"], "status": result["status"]}
        requests = []
        if result["status"] == "closed" and done["returncode"] == 0:
            record["candidate"] = result["candidate"]
            for request_ref in result["scoring_requests"]:
                request = checked(request_ref)
                validate_request(request, slot, output)
                requests.append({"slot_id": sid, "endpoint": request["endpoint"], "request": request_ref})
        else:
            record["error"] = result.get("error")
        return record, requests
    unit = "proworksim-v055-preentry-recovery-r1-" + str(slot["slot_index"]) + ".service"
    observed = subprocess.run(["systemctl", "show", unit, "-p", "ActiveState", "-p", "MainPID", "-p", "Result"],
                              text=True, capture_output=True, timeout=15, check=True)
    props = dict(line.split("=", 1) for line in observed.stdout.splitlines() if "=" in line)
    if props.get("MainPID") == "0" and props.get("ActiveState") in ("inactive", "failed"):
        return {"slot_id": sid, "condition_id": slot["condition_id"], "status": "technical_unknown",
                "reason": "Recovery service ended without its bound completion; never replay", "unit": props}, []
    return None, []


def run(sha):
    plan = checked({"path": str(OUT / "plan.json"), "sha256": sha})
    for item in (plan["driver_source"], plan["original_scorer"]):
        if reference(Path(item["path"])) != item:
            raise ValueError("First-score frozen source changed")
    recovery = checked(plan["recovery_plan"])
    started = time.monotonic()
    generations, scores, futures = {}, {}, {}
    with lock_file(OUT / "driver.lock") as driver_lease, ThreadPoolExecutor(max_workers=4) as pool:
        write_new(OUT / "started.json", {"started_utc": now(), "plan_sha256": sha,
            "six_slots": [row["slot_id"] for row in recovery["slots"]], "model_calls": 0})
        while True:
            for slot in recovery["slots"]:
                sid = slot["slot_id"]
                if sid in generations:
                    continue
                try:
                    record, requests = observe_generation(slot)
                    if record is not None:
                        for item in requests:
                            identity = item["request"]["sha256"]
                            if identity in futures or len(futures) >= plan["maximum_new_endpoints"]:
                                raise ValueError("Duplicate or excessive first-score endpoints")
                            futures[identity] = pool.submit(grade, item, driver_lease, plan)
                        generations[sid] = record
                except json.JSONDecodeError:
                    # A newly written small receipt may not have finished yet.
                    continue
                except Exception as error:
                    generations[sid] = {"slot_id": sid, "condition_id": slot["condition_id"],
                        "status": "technical_unknown", "observation_error": str(error), "automatic_replay": False}
            for identity, future in futures.items():
                if future.done() and identity not in scores:
                    try:
                        scores[identity] = future.result()
                    except Exception as error:
                        scores[identity] = {"status": "technical_unknown", "error": str(error)}
            current = {"version": plan["version"], "updated_utc": now(), "generation_terminal": len(generations),
                "generation_rows": list(generations.values()), "scoring_endpoints_created": len(futures),
                "scoring_endpoints_terminal": len(scores), "score_rows": list(scores.values()),
                "original_unknowns_and_claims_preserved": True, "driver_model_calls": 0}
            temporary = OUT / "state.tmp"
            temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n")
            temporary.replace(OUT / "state.json")
            if len(generations) == 6 and len(scores) == len(futures):
                break
            if time.monotonic() - started > plan["maximum_observation_seconds"]:
                current["observation_bound_reached"] = True
                break
            time.sleep(15)
        with sqlite3.connect(Path(recovery["shared_ledger"]).as_uri() + "?mode=ro", uri=True) as db:
            marks = ",".join("?" for _ in recovery["slots"])
            query = f"SELECT slot_id,status,COUNT(*),COALESCE(SUM(settled_nanoyuan),0),COALESCE(SUM(reserved_nanoyuan),0) FROM requests WHERE slot_id IN ({marks}) GROUP BY slot_id,status"
            current["recovery_API_accounting_rows"] = list(db.execute(query, [row["slot_id"] for row in recovery["slots"]]))
        current.update(finished_utc=now(), primary_queue_updated=False, old_unknown_status_changed=False,
                       first_scoring_attempts_only=True)
        write_new(OUT / "summary.json", current)
        write_new(RECOVERY / "summary.json", {"version": plan["version"], "finished_utc": current["finished_utc"],
            "summary": reference(OUT / "summary.json"), "generation_terminal": len(generations),
            "scoring_endpoints_terminal": len(scores), "original_unknowns_and_claims_preserved": True})
        print(json.dumps({"generation_terminal": len(generations), "scores_terminal": len(scores), "summary": str(OUT / "summary.json")}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    parser.add_argument("--plan-sha256")
    args = parser.parse_args()
    if args.operation == "prepare":
        source_plan()
    else:
        run(args.plan_sha256)


if __name__ == "__main__":
    main()
