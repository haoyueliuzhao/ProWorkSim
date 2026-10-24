"""Durable Qwen REF budget queue; resident engines are never restarted per task."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_supervision_v054 import process_identity
from .storage import atomic_write, digest, json_bytes

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs/software-benchmark-v056"
DEFAULT_QUEUE = RUNS / "queue-r1"
VERSION = "v056-ref-budget-queue-r1"
GIB = 1024 ** 3
GEN_TERMINAL = {"closed", "deferred"}
SCORE_TERMINAL = {"official_report", "deferred", "not_applicable"}


def now():
    return datetime.now(timezone.utc).isoformat()


def load(ref):
    return json.loads(checked(ref).read_bytes())


def alive(identity):
    if not identity:
        return False
    try:
        if process_identity(identity["pid"]) != identity:
            return False
        raw = Path(f"/proc/{identity['pid']}/stat").read_text()
        return raw[raw.rfind(")") + 2:].split()[0] != "Z"
    except (FileNotFoundError, ProcessLookupError):
        return False


@contextmanager
def lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield stream


def initial_state(binding_ref, slots):
    if len({row["slot_id"] for row in slots}) != len(slots):
        raise ValueError("Slots must be unique")
    return {"version": VERSION, "binding": binding_ref, "created_utc": now(),
            "rows": [{"slot": row, "generation": {"status": "pending"},
                      "score": {"status": "not_ready"}} for row in slots],
            "jobs": {}, "preparation": {}, "reclamation": {},
            "quarantined_residents": {}, "quarantined_graders": {},
            "deferred": [], "resident_releases": {}, "complete": False}


def summary(state):
    generations = Counter(row["generation"]["status"] for row in state["rows"])
    scoring = Counter(row["score"]["status"] for row in state["rows"])
    by_condition = {}
    for row in state["rows"]:
        item = by_condition.setdefault(row["slot"]["condition_id"],
            {"planned": 0, "generation_closed": 0, "generation_deferred": 0,
             "official_reports": 0, "resolved": 0, "scoring_deferred": 0})
        item["planned"] += 1
        item["generation_closed"] += row["generation"]["status"] == "closed"
        item["generation_deferred"] += row["generation"]["status"] == "deferred"
        item["official_reports"] += row["score"]["status"] == "official_report"
        item["resolved"] += row["score"].get("resolved") is True
        item["scoring_deferred"] += row["score"]["status"] == "deferred"
    return {"version": VERSION, "utc": now(), "planned": len(state["rows"]),
            "generation": dict(generations), "scoring": dict(scoring), "conditions": by_condition,
            "active_jobs": sum(job["status"] in {"launch_intent", "running"} for job in state["jobs"].values()),
            "deferred_count": len(state["deferred"]), "complete": state["complete"],
            "backpressure": state.get("backpressure"),
            "quarantined_residents": list(state["quarantined_residents"]),
            "quarantined_graders": list(state["quarantined_graders"]),
            "reclamation": state["reclamation"],
            "analysis_finalization": state.get("analysis_finalization")}


def selected_pending(rows, qualified, resident_ids, maximum):
    """Frozen slot order among already qualified tasks; scores never influence selection."""
    result = []
    residents = iter(resident_ids)
    for row in rows:
        if len(result) >= maximum:
            break
        if row["generation"]["status"] != "pending" or row["slot"]["instance_id"] not in qualified:
            continue
        resident = next(residents, None)
        if resident is None:
            break
        result.append((row, resident))
    return result


def resource_gate(*, free_bytes, reserved_bytes, requested_bytes, floor_bytes,
                  available_memory, memory_reservation, load_one, cpu_count):
    return {"admitted": free_bytes - reserved_bytes - requested_bytes >= floor_bytes
            and available_memory - memory_reservation >= 128 * GIB
            and load_one < max(1, cpu_count * .85),
            "free_bytes": free_bytes, "reserved_bytes": reserved_bytes,
            "requested_bytes": requested_bytes, "floor_bytes": floor_bytes,
            "memory_available_bytes": available_memory, "memory_reservation_bytes": memory_reservation,
            "load_1m": load_one, "cpu_count": cpu_count}


def scorer_argv(request):
    return [str(ROOT / "tools/run_benchmark_runtime_v054.sh"), "--write-project", "/usr/bin/env",
            "PYTHONPATH=" + str(ROOT / "src"), "HF_HUB_OFFLINE=1", "HF_DATASETS_OFFLINE=1",
            "TRANSFORMERS_OFFLINE=1", "NO_PROXY=*", "no_proxy=*", "HTTP_PROXY=", "HTTPS_PROXY=",
            "ALL_PROXY=", "http_proxy=", "https_proxy=", "all_proxy=",
            str(ROOT / "runs/software-benchmark-v054/scorer-venv/bin/python"), "-B", "-m",
            "proworksim.software_benchmark_scorer_v056", "--request", str(request)]


def command_worker(job_ref):
    job = load(job_ref)
    folder = Path(job_ref["path"]).parent.resolve()
    if job.get("version") != VERSION or not folder.is_relative_to(RUNS):
        raise ValueError("Worker requires an independent v056 intent")
    with lock(folder / "worker.lock"), lock(job["resource_lock"]) as resource:
        if (folder / "started.json").exists() or (folder / "completion.json").exists():
            raise ValueError("An entered worker is never replayed")
        binding = load(job["binding"])
        for source in load(binding["frozen_sources"])["files"]:
            checked(source)
        write_new(folder / "started.json", {"job": job_ref, "utc": now(),
                                           "host_process": process_identity(os.getpid())})
        result, child = {"job": job_ref, "started_utc": now()}, None
        try:
            with (folder / "stdout.log").open("xb") as stdout, (folder / "stderr.log").open("xb") as stderr:
                child = subprocess.Popen(job["argv"], cwd=ROOT, stdout=stdout, stderr=stderr,
                                         stdin=subprocess.DEVNULL, start_new_session=True,
                                         pass_fds=(resource.fileno(),))
                result["child_process"] = process_identity(child.pid)
                result["returncode"] = child.wait(timeout=job["timeout_seconds"])
                result["status"] = "process_exited"
        except Exception as error:
            result.update(status="technical_unknown", returncode=None,
                          error={"type": type(error).__name__, "message": str(error)})
            if child is not None and child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=20)
        result["finished_utc"] = now()
        write_new(folder / "completion.json", result)


class Queue:
    def __init__(self, binding_ref, directory=DEFAULT_QUEUE):
        self.root = Path(directory).resolve()
        if not self.root.is_relative_to(RUNS) or self.root == RUNS:
            raise ValueError("Queue state must be inside its own v056 directory")
        self.binding_ref, self.binding = binding_ref, load(binding_ref)
        if self.binding.get("version") != "v056-ref-budget-bindings-r1":
            raise ValueError("Unknown queue binding")
        if self.root != Path(self.binding.get("queue_root", DEFAULT_QUEUE)).resolve():
            raise ValueError("Queue root differs from its frozen binding")
        self.plan = load(self.binding["plan"])
        if (self.plan.get("version") != "v056-ref-budget-plan-r1"
                or self.binding.get("max_generation") != 6 or self.binding.get("max_scoring") != 2
                or self.binding.get("disk_floor_bytes") != 128 * GIB):
            raise ValueError("Frozen panel or queue resource limits differ")
        self.sources = load(self.binding["frozen_sources"])["files"]
        if not self.sources:
            raise ValueError("No runtime source seal supplied")
        for source in self.sources:
            checked(source)
        self.source_stats = {item["path"]: self._stat(item["path"]) for item in self.sources}
        load(self.binding["scorer_manifest"])
        self.slots = load(self.plan["slots"])["slots"]
        authorization = load(self.plan["authorization"])
        if (len(self.slots) != self.plan["planned_episodes"]
                or authorization.get("execution_authorized") is not True
                or authorization.get("slots_sha256") != self.plan["slots"]["sha256"]
                or set(authorization.get("slot_ids", [])) != {row["slot_id"] for row in self.slots}):
            raise ValueError("No complete matching slot authorization")
        self.tasks = {row["instance_id"]: row for row in load(self.plan["public_tasks"])}
        self.registry = {row["instance_id"]: row for row in load(self.plan["public_test_registry"])["entries"]}
        self.images = {row["instance_id"]: row for row in load(self.binding["images"])["images"]}
        self.mappings = {key: row["baseline_mapping"] for key, row in self.registry.items()}
        spec = importlib.util.spec_from_file_location("v056_preparer", ROOT / "tools/prepare_ref_budget_cache_v056.py")
        self.preparer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.preparer)
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "state.json"
        self.state = json.loads(path.read_bytes()) if path.exists() else initial_state(binding_ref, self.slots)
        if (self.state.get("version") != VERSION or self.state.get("binding") != binding_ref
                or [row["slot"] for row in self.state["rows"]] != self.slots):
            raise ValueError("Do not replace the binding or panel of a running queue")
        self.children = {}
        self.rows = {row["slot"]["slot_id"]: row for row in self.state["rows"]}
        self.cpus = sorted(os.sched_getaffinity(0))
        if len(self.cpus) < 8:
            raise ValueError("Two graders require two disjoint four-CPU sets")

    @staticmethod
    def _stat(path):
        stat = Path(path).stat()
        return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]

    def save(self):
        self.state["updated_utc"] = now()
        atomic_write(self.root / "state.json", json_bytes(self.state))
        atomic_write(self.root / "status.json", json_bytes(summary(self.state)))

    def event(self, kind, **values):
        with (self.root / "events.jsonl").open("a") as stream:
            stream.write(json.dumps({"utc": now(), "kind": kind, **values}, ensure_ascii=False) + "\n")

    def defer(self, row, reason, *, generation=True):
        key = "generation" if generation else "score"
        row[key].update(status="deferred", reason=reason)
        if generation and row["score"]["status"] == "not_ready":
            row["score"].update(status="not_applicable", reason="No admitted scoring candidate")
        self.state["deferred"].append({"slot_id": row["slot"]["slot_id"], "phase": key,
                                       "reason": reason, "utc": now()})
        self.event("slot_deferred", slot_id=row["slot"]["slot_id"], phase=key, reason=reason)

    def start_job(self, kind, key, argv, *, row=None, instance_id=None, resident=None,
                  reservation=0, grader=None, payload=None):
        job_id = kind + "-" + digest(str(key).encode())[:28]
        folder = self.root / "jobs" / job_id
        folder.mkdir(parents=True, exist_ok=False)
        resource = ("resident-" + digest(resident.encode())[:24] if resident else
                    "grader-" + str(grader) if kind == "score" else "cache-prepare")
        timeout = self.plan["common_limits"]["hard_seconds"] + 900 if kind == "generation" else 3600 if kind == "score" else 14400
        job = {"version": VERSION, "kind": kind, "argv": argv, "timeout_seconds": timeout,
               "binding": self.binding_ref, "resource_lock": str(RUNS / "queue-resource-locks" / (resource + ".lock"))}
        job_ref = write_new(folder / "job.json", job)
        entry = {"kind": kind, "status": "launch_intent", "directory": str(folder), "job": job_ref,
                 "instance_id": instance_id, "slot_id": row["slot"]["slot_id"] if row else None,
                 "resident": resident, "grader": grader, "reservation_bytes": reservation,
                 "intent_unix": time.time(), "payload": payload or {}}
        self.state["jobs"][job_id] = entry
        if row:
            row["generation" if kind == "generation" else "score"].update(status="running", job_id=job_id)
        self.save()  # Intent reaches disk before any subprocess can run.
        try:
            worker = subprocess.Popen([str(ROOT / ".venv/bin/python"),
                str(ROOT / "tools/run_ref_budget_queue_v056.py"), "--worker-job", str(folder / "job.json"),
                "--worker-sha256", job_ref["sha256"]], cwd=ROOT, stdin=subprocess.DEVNULL,
                stdout=(folder / "worker.stdout.log").open("xb"),
                stderr=(folder / "worker.stderr.log").open("xb"), start_new_session=True)
            self.children[job_id] = worker
            entry["host_process"] = process_identity(worker.pid)
            write_new(folder / "launch-process.json", {"host_process": entry["host_process"], "job": job_ref})
            entry["status"] = "running"
        except Exception as error:
            entry["launch_error"] = {"type": type(error).__name__, "message": str(error)}
        self.event("job_launch", job_id=job_id, kind_name=kind, instance_id=instance_id)
        self.save()
        return job_id

    def refresh_jobs(self):
        for job_id, process in list(self.children.items()):
            if process.poll() is not None:
                self.children.pop(job_id)
        for job_id, job in self.state["jobs"].items():
            if job["status"] not in {"launch_intent", "running"}:
                continue
            try:
                folder = Path(job["directory"])
                started = folder / "started.json"
                if started.exists():
                    body = json.loads(started.read_bytes())
                    if body["job"] != job["job"]:
                        raise ValueError("Worker start identity differs")
                    job["host_process"] = body["host_process"]
                if alive(job.get("host_process")):
                    continue
                if not job.get("host_process") and time.time() - job["intent_unix"] < 60:
                    continue
                completion = folder / "completion.json"
                if completion.exists():
                    body = json.loads(completion.read_bytes())
                    if body["job"] != job["job"]:
                        raise ValueError("Worker completion identity differs")
                    job["completion"] = reference(completion)
                else:
                    body = {"returncode": None, "status": "technical_unknown", "error": "Worker disappeared without completion"}
                job["status"], job["finished_utc"] = "completed", now()
                if job["kind"] == "generation":
                    row = self.rows[job["slot_id"]]
                    result_path = Path(job["payload"]["output"]) / "result.json"
                    result = json.loads(result_path.read_bytes()) if result_path.exists() else {}
                    if result and (result.get("slot_id") != row["slot"]["slot_id"]
                                   or result.get("condition_id") != row["slot"]["condition_id"]):
                        raise ValueError("Generation result belongs to another slot or condition")
                    quiet = result.get("resource_release", {}).get("released") is True and not result.get("cleanup_errors")
                    # Before resource creation, a clean failure cannot have running episode descendants.
                    quiet = quiet or (result.get("entered") is False and not result.get("cleanup_errors")
                                       and result.get("finally_stopped_scopes") == [] and not result.get("slot_claimed"))
                    row["generation"]["quiescent"] = quiet
                    if result_path.exists():
                        row["generation"]["result"] = reference(result_path)
                    if not quiet:
                        self.state["quarantined_residents"][job["resident"]] = {"job_id": job_id, "reason": "Episode quiescence not proved"}
                    requests = result.get("scoring_requests", [])
                    if (body.get("returncode") == 0 and result.get("status") == "closed"
                            and result.get("candidate_locked") is True and quiet and len(requests) == 1):
                        scoring_request = load(requests[0])
                        if (scoring_request.get("slot_id") != row["slot"]["slot_id"]
                                or scoring_request.get("condition_id") != row["slot"]["condition_id"]):
                            raise ValueError("Scoring request belongs to another slot")
                        row["generation"]["status"] = "closed"
                        row["score"].update(status="pending", request=requests[0])
                    else:
                        self.defer(row, {"worker": body.get("status"), "result": result.get("status"),
                                         "error": result.get("error", body.get("error"))})
                elif job["kind"] == "score":
                    row = self.rows[job["slot_id"]]
                    pointer = Path(job["payload"]["receipt_output"])
                    quiet = False
                    proof_path = Path(job["payload"]["quiescence_output"])
                    if proof_path.exists():
                        proof = json.loads(proof_path.read_bytes())
                        quiet = (proof.get("slot_id") == row["slot"]["slot_id"]
                                 and proof.get("condition_id") == row["slot"]["condition_id"]
                                 and proof.get("quiescent") is True and not proof.get("cleanup_errors"))
                        row["score"]["quiescence"] = reference(proof_path)
                    row["score"]["quiescent"] = quiet
                    if pointer.exists():
                        pointer_ref = reference(pointer)
                        receipt = load(json.loads(pointer.read_bytes())["receipt"])
                        if (receipt.get("slot_id") != row["slot"]["slot_id"]
                                or receipt.get("condition_id") != row["slot"]["condition_id"]):
                            raise ValueError("Official receipt belongs to another slot")
                        row["score"]["receipt"] = pointer_ref
                        if (quiet and body.get("returncode") == 0 and receipt.get("status") == "official_report"
                                and type(receipt.get("resolved")) is bool):
                            row["score"].update(status="official_report", resolved=receipt["resolved"])
                        else:
                            self.defer(row, {"scorer": receipt.get("status"), "worker": body.get("status")}, generation=False)
                    else:
                        self.defer(row, {"missing_official_receipt": True, "worker": body.get("status")}, generation=False)
                    if not quiet:
                        self.state["quarantined_graders"][str(job["grader"])] = {"job_id": job_id, "reason": "Grader completion not proved"}
                elif job["kind"] == "reclaim":
                    lines = (folder / "stdout.log").read_text().splitlines()
                    record = json.loads(lines[-1]) if lines else {"status": "deferred", "reason": "Reclaimer emitted no receipt"}
                    self.state["reclamation"][job["instance_id"]] = {**record, "job_id": job_id}
                else:
                    self.state["preparation"].setdefault(job["instance_id"], {})["last_job"] = job_id
                    self.state["preparation"][job["instance_id"]]["retry_not_before"] = time.time() + 30
                self.event("job_completed", job_id=job_id, kind_name=job["kind"], returncode=body.get("returncode"))
            except Exception as error:
                job["status"] = "deferred"
                job["error"] = {"type": type(error).__name__, "message": str(error)}
                if job["slot_id"] in self.rows:
                    row = self.rows[job["slot_id"]]
                    phase = "generation" if job["kind"] == "generation" else "score"
                    row[phase]["quiescent"] = False
                    self.defer(row, {"invalid_completion_evidence": job["error"]}, generation=phase == "generation")
                    if phase == "generation":
                        self.state["quarantined_residents"][job["resident"]] = {"job_id": job_id, "reason": "Invalid completion evidence"}
                    else:
                        self.state["quarantined_graders"][str(job["grader"])] = {"job_id": job_id, "reason": "Invalid completion evidence"}
                elif job["kind"] == "reclaim":
                    self.state["reclamation"][job["instance_id"]] = {"status": "deferred", "job_id": job_id, "error": job["error"]}
                else:
                    self.state["preparation"].setdefault(job["instance_id"], {})["error"] = job["error"]
                self.event("job_evidence_deferred", job_id=job_id, error=job["error"])
        self.save()

    def residents(self):
        occupied = {job["resident"] for job in self.state["jobs"].values()
                    if job["kind"] == "generation" and job["status"] in {"launch_intent", "running"}}
        result = {}
        for path in sorted((RUNS / "residents").glob("*/ready.json")):
            name = str(path.parent)
            if name in occupied or name in self.state["quarantined_residents"] or (path.parent / "closed.json").exists():
                continue
            try:
                body = json.loads(path.read_bytes())
                if (body.get("ready") is not True or body.get("models_resident") is not True
                        or not alive(body.get("host_process"))):
                    continue
                if load(body["identity"]) != body["identity_value"]:
                    raise ValueError("Resident public identity changed")
                result[name] = body
            except Exception as error:
                self.state["quarantined_residents"][name] = {"job_id": None,
                    "reason": "Resident readiness identity is invalid", "error": str(error)}
                self.event("resident_isolated", resident=name, error=str(error))
        return result

    def reserved(self):
        quarantined = {value["job_id"] for value in (
            *self.state["quarantined_residents"].values(), *self.state["quarantined_graders"].values())}
        jobs = [job for job_id, job in self.state["jobs"].items()
                if job["status"] in {"launch_intent", "running"} or job_id in quarantined]
        reserved = sum(job["reservation_bytes"] for job in jobs)
        prep = RUNS / "cache-preparation-r1/active-reservation.json"
        if prep.exists() and not any(job["kind"] == "prepare" for job in jobs):
            value = json.loads(prep.read_bytes())
            if value.get("active"):
                reserved += value["peak_bytes"]
        return reserved, len(jobs)

    def gate(self, requested):
        reserved, jobs = self.reserved()
        memory = next(int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()
                      if line.startswith("MemAvailable:"))
        value = resource_gate(free_bytes=shutil.disk_usage(ROOT).free, reserved_bytes=reserved,
            requested_bytes=requested, floor_bytes=self.binding["disk_floor_bytes"], available_memory=memory,
            memory_reservation=(jobs + 1) * 16 * GIB, load_one=os.getloadavg()[0], cpu_count=len(self.cpus))
        self.state["backpressure"] = value
        return value["admitted"]

    def cache_statuses(self):
        tasks = []
        for row in self.state["rows"]:
            if row["generation"]["status"] == "pending" and row["slot"]["instance_id"] not in tasks:
                tasks.append(row["slot"]["instance_id"])
        states = {}
        for instance in tasks:
            try:
                value = self.preparer.status_for(self.binding["plan"], self.plan, self.mappings, instance)
                if value["status"] == "preparing_or_interrupted":
                    owner = load(value["started"]).get("host_process")
                    if alive(owner):
                        value["status"] = "preparing"
            except Exception as error:
                value = {"status": "failed", "error_type": type(error).__name__, "error": str(error)}
            states[instance] = value
            if value["status"] in {"failed", "evicted", "preparing_or_interrupted"}:
                for row in self.state["rows"]:
                    if row["slot"]["instance_id"] == instance and row["generation"]["status"] == "pending":
                        self.defer(row, {"environment": value})
        return states

    def materialize_config(self, row, resident):
        slot = row["slot"]
        condition = load(self.plan["conditions"][slot["condition_id"]])
        entry = self.registry[slot["instance_id"]]
        scorer = {**self.binding["scorer_request_base"], "scorer_manifest": self.binding["scorer_manifest"],
                  "image": self.images[slot["instance_id"]], "baseline_mapping": entry["baseline_mapping"],
                  "scoring_cpuset_cpus": ",".join(map(str, self.cpus[:4]))}
        value = {"version": "v056-ref-budget-slot-config-r1", **slot,
            "model": "Qwen/Qwen3.5-9B", "thinking": True, "preparation_only": False,
            "all_solver_admissions_passed": True, "configuration": self.plan["conditions"][slot["condition_id"]],
            "slots": self.plan["slots"], "authorization": self.plan["authorization"],
            "public_tasks": self.plan["public_tasks"], "public_test_registry": self.plan["public_test_registry"],
            "frozen_sources": self.sources, "public_task": self.tasks[slot["instance_id"]],
            "dataset_revision": condition["dataset_revision"], "public_test_entry": entry,
            "scorer_request_base": scorer, "lazy_native_preparation": {"cache_root": self.plan["cache_root"]},
            "stdlib": self.plan["stdlib"], "sdk_runtime": self.plan["sdk_runtime"],
            "ref_endpoint": resident["endpoint"], "ref_api_key_file": resident["api_key_file"],
            "model_identity_value": resident["identity_value"]}
        directory = self.root / "configs"
        directory.mkdir(exist_ok=True)
        return write_new(directory / (digest(slot["slot_id"].encode()) + ".json"), value)

    def dispatch(self):
        for path, identity in self.source_stats.items():
            if self._stat(path) != identity:
                raise ValueError("Frozen runtime source changed; no further dispatch allowed")
        states = self.cache_statuses()
        qualified = {key for key, value in states.items() if value["status"] == "qualified"}
        free = self.residents()
        active_gen = sum(job["kind"] == "generation" and job["status"] in {"launch_intent", "running"}
                         for job in self.state["jobs"].values())
        for row, resident_key in selected_pending(self.state["rows"], qualified, free, self.binding["max_generation"] - active_gen):
            reservation = self.binding["generation_reservation_bytes"]
            if not self.gate(reservation):
                break
            config = self.materialize_config(row, free[resident_key])
            output = RUNS / "episodes" / digest(row["slot"]["slot_id"].encode())
            self.start_job("generation", row["slot"]["slot_id"], [str(ROOT / ".venv/bin/python"),
                str(ROOT / "tools/run_ref_budget_episode_v056.py"), "--config", config["path"], "--output", str(output)],
                row=row, instance_id=row["slot"]["instance_id"], resident=resident_key,
                reservation=reservation, payload={"output": str(output), "config": config})
        occupied = {job["grader"] for job in self.state["jobs"].values()
                    if job["kind"] == "score" and job["status"] in {"launch_intent", "running"}}
        for grader in range(self.binding["max_scoring"]):
            if grader in occupied or str(grader) in self.state["quarantined_graders"]:
                continue
            row = next((row for row in self.state["rows"] if row["score"]["status"] == "pending"), None)
            if row is None or not self.gate(self.binding["scoring_reservation_bytes"]):
                break
            request = load(row["score"]["request"])
            request["scoring_cpuset_cpus"] = ",".join(map(str, self.cpus[grader * 4:(grader + 1) * 4]))
            directory = self.root / "score-requests"
            directory.mkdir(exist_ok=True)
            request["quiescence_output"] = str(directory / (digest(row["slot"]["slot_id"].encode()) + "-quiescence.json"))
            request_ref = write_new(directory / (digest(row["slot"]["slot_id"].encode()) + ".json"), request)
            row["score"]["dispatched_request"] = request_ref
            self.start_job("score", row["slot"]["slot_id"], scorer_argv(request_ref["path"]),
                row=row, instance_id=row["slot"]["instance_id"], grader=grader,
                reservation=self.binding["scoring_reservation_bytes"],
                payload={"receipt_output": request["receipt_output"], "quiescence_output": request["quiescence_output"]})
        if any(job["kind"] in {"prepare", "reclaim"} and job["status"] in {"launch_intent", "running"}
               for job in self.state["jobs"].values()):
            return
        # Two task identities ahead, not two full copies per budget arm.
        ahead = [key for key, value in states.items() if value["status"] in {"qualified", "pending", "preparing"}][:2]
        for instance in ahead:
            if states[instance]["status"] != "pending":
                continue
            previous = self.state["preparation"].setdefault(instance, {})
            if time.time() < previous.get("retry_not_before", 0):
                continue
            if not self.gate(self.binding["cold_preparation_reservation_bytes"]):
                return
            reserved, _ = self.reserved()
            attempt = previous.get("attempts", 0) + 1
            previous["attempts"] = attempt
            self.start_job("prepare", instance + ":" + str(attempt), [str(ROOT / ".venv/bin/python"),
                str(ROOT / "tools/prepare_ref_budget_cache_v056.py"), "--plan", self.binding["plan"]["path"],
                "--plan-sha256", self.binding["plan"]["sha256"], "--instance-id", instance,
                "--active-reserved-bytes", str(reserved)], instance_id=instance,
                reservation=self.binding["cold_preparation_reservation_bytes"])
            break

    def reclaim_completed(self):
        # Reclaimer independently proves exact four-arm terminal state and real quiescence.
        if not hasattr(self.preparer, "reclaim_one") or any(
                job["kind"] in {"prepare", "reclaim"} and job["status"] in {"launch_intent", "running"}
                for job in self.state["jobs"].values()):
            return
        for instance in self.plan["task_ids"]:
            rows = [row for row in self.state["rows"] if row["slot"]["instance_id"] == instance]
            if (instance in self.state["reclamation"] or not rows
                    or any(row["generation"]["status"] not in GEN_TERMINAL
                           or row["score"]["status"] not in SCORE_TERMINAL for row in rows)):
                continue
            directory = self.root / "reclaim-requests" / instance
            directory.mkdir(parents=True, exist_ok=False)
            snapshot = write_new(directory / "state.json", self.state)
            self.state["reclamation"][instance] = {"status": "running", "state_snapshot": snapshot}
            self.start_job("reclaim", instance, [str(ROOT / ".venv/bin/python"),
                str(ROOT / "tools/prepare_ref_budget_cache_v056.py"), "--plan", self.binding["plan"]["path"],
                "--plan-sha256", self.binding["plan"]["sha256"], "--instance-id", instance,
                "--reclaim", "--state", snapshot["path"], "--state-sha256", snapshot["sha256"]],
                instance_id=instance, payload={"snapshot": snapshot})
            break

    def release_owned_residents(self):
        for ready in sorted((RUNS / "residents").glob("*/ready.json")):
            folder = ready.parent
            if (str(folder) in self.state["resident_releases"] or str(folder) in self.state["quarantined_residents"]
                    or (folder / "closed.json").exists()):
                continue
            try:
                body = json.loads(ready.read_bytes())
                unit_path = folder / "service-unit.json"
                if not unit_path.exists() or not alive(body.get("host_process")):
                    continue
                unit = json.loads(unit_path.read_bytes())
                if "--user" not in unit.get("command", []) or not unit.get("unit", "").startswith("proworksim-v056-"):
                    raise ValueError("Resident service is not an owned v056 user unit")
                code = subprocess.run(["systemctl", "--user", "stop", unit["unit"]],
                                      capture_output=True, text=True, timeout=45)
                self.state["resident_releases"][str(folder)] = {"unit": unit["unit"], "returncode": code.returncode,
                    "utc": now(), "ownership": reference(unit_path), "ready": reference(ready)}
                self.save()
            except Exception as error:
                self.state["resident_releases"][str(folder)] = {
                    "status": "deferred", "utc": now(), "error": str(error)}
                self.save()

    def finalize_analysis(self):
        if "analysis_finalization" in self.state:
            return
        folder = self.root / "final-analysis"
        folder.mkdir(exist_ok=True)
        command = [str(ROOT / ".venv/bin/python"), str(ROOT / "tools/analyze_ref_budget_results_v056.py"),
                   "--state", str(self.root / "state.json")]
        self.state["analysis_finalization"] = {"status": "running", "started_utc": now(), "command": command}
        self.save()
        try:
            with (folder / "stdout.log").open("xb") as stdout, (folder / "stderr.log").open("xb") as stderr:
                result = subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                        stdout=stdout, stderr=stderr, timeout=180)
            value = {"status": "complete" if result.returncode == 0 else "deferred",
                     "returncode": result.returncode}
        except Exception as error:
            value = {"status": "deferred", "returncode": None,
                     "error": {"type": type(error).__name__, "message": str(error)}}
        self.state["analysis_finalization"].update(value, finished_utc=now(),
            stdout=str(folder / "stdout.log"), stderr=str(folder / "stderr.log"),
            generation_restarted=False, resident_release_preceded_analysis=True)
        self.save()

    def tick(self):
        self.refresh_jobs()
        self.reclaim_completed()
        self.dispatch()
        self.state["complete"] = all(row["generation"]["status"] in GEN_TERMINAL
            and row["score"]["status"] in SCORE_TERMINAL for row in self.state["rows"]) and not any(
                job["status"] in {"launch_intent", "running"} for job in self.state["jobs"].values())
        self.save()
        if self.state["complete"]:
            self.release_owned_residents()
            self.finalize_analysis()
        return summary(self.state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--binding-sha256")
    parser.add_argument("--root", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--worker-job", type=Path)
    parser.add_argument("--worker-sha256")
    args = parser.parse_args()
    if args.worker_job:
        item = reference(args.worker_job)
        if item["sha256"] != args.worker_sha256:
            raise ValueError("Worker intent identity changed")
        command_worker(item)
        return 0
    if args.status:
        path = args.root / "state.json"
        print(json.dumps(summary(json.loads(path.read_bytes())) if path.exists() else
                         {"version": VERSION, "status": "not_started"}, ensure_ascii=False))
        return 0
    if not args.binding or not args.binding_sha256 or not 1 <= args.interval <= 60:
        parser.error("Execution requires frozen --binding/--binding-sha256 and a 1..60 second interval")
    item = reference(args.binding)
    if item["sha256"] != args.binding_sha256:
        raise ValueError("Queue binding identity changed")
    with lock(args.root / "coordinator.lock"):
        queue = Queue(item, args.root)
        stop = threading.Event()
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: stop.set())
        previous = None
        while not stop.is_set():
            value = queue.tick()
            compact = {key: value[key] for key in ("generation", "scoring", "active_jobs", "complete")}
            if compact != previous:
                print(json.dumps(value, ensure_ascii=False), flush=True)
                previous = compact
            if args.once or value["complete"]:
                return 0
            stop.wait(args.interval)
        queue.event("coordinator_stopped", inflight_workers_preserved=True)
        queue.save()
    return 0
