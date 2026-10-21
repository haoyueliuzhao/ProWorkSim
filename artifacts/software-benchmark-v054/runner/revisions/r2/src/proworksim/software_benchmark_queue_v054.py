"""Durable fixed-panel dispatch and trusted official grading; no candidate replay.

The controller persists intent before asking systemd to start a uniquely named
worker. A controller restart observes those workers; it never relaunches an
ambiguous intent. The once-only episode claim remains owned by the slot runner.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from .software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = Path(__file__).resolve().parents[2]
HOST_PYTHON = ROOT / ".venv/bin/python"
VERSION = "software-benchmark-formal-queue-v054-r1"
SLOTS_SHA = "55899d0b83a5bab1082bccb50496fb6c1d7111ecb951fc4d61c222be19d88676"
QUEUE = ROOT / "runs/software-benchmark-v054/formal-queue-r1"
AUTH = ROOT / "config/v054-formal-authorization-r1.json"
PLAN = ROOT / "config/v054-formal-execution-plan-r1.json"
SOURCE = ROOT / "artifacts/software-benchmark-v054/runner/source-manifest.json"
BUSY = {"gpu_lease_busy", "ref_port_busy", "gpu_capacity_gate"}
ACTIVE = {"intent", "running"}


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text())


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".writing")
    with temp.open("w") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def load_ref(item):
    return read(checked(item))


def claim_path(slot_id):
    return (ROOT / "runs/software-benchmark-v054/episode-claims"
            / hashlib.sha256(slot_id.encode()).hexdigest() / "claim.json")


def stat_id(path):
    item = Path(path).stat()
    return [item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns]


def lock_file(path, *, nonblocking=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+")
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0))
    except BaseException:
        stream.close()
        raise
    return stream


def check_plan(authorization, plan, slots):
    rows = slots["slots"]
    if (authorization.get("execution_authorized") is not True
            or authorization.get("slots_sha256") != SLOTS_SHA
            or plan.get("slots_sha256") != SLOTS_SHA
            or len(rows) != 1500 or [x["slot_index"] for x in rows] != list(range(1, 1501))
            or authorization["slot_ids"] != [x["slot_id"] for x in rows]
            or len(set(authorization["slot_ids"])) != 1500
            or Counter(x["arm"] for x in rows) != {"REF": 500, "MATCH": 500, "PROJECT": 500}
            or len({x["instance_id"] for x in rows}) != 500
            or authorization["aggregate_input_output_token_upper_bound"] != 750000000
            or authorization["input_output_token_limit_per_episode"] != 500000
            or authorization["training_authorized"] is not False
            or plan["maximum_active_generation_episodes"] != 2
            or plan["maximum_active_official_graders"] != 2
            or plan["physical_gpu_by_arm"] != {"REF": 7, "MATCH": 6, "PROJECT": 6}):
        raise ValueError("Only the original authorized 1500-slot / 750M panel is supported")
    for task in {x["instance_id"] for x in rows}:
        group = [x for x in rows if x["instance_id"] == task]
        if len(group) != 3 or len({x["seed"] for x in group}) != 1:
            raise ValueError("Frozen same-task arm/seed assignment changed")


def freeze_bindings(*, ref_capacity, match_capacity, scorer_manifest, output):
    """Freeze only actual capacity and final source evidence; allocate no GPU."""
    slots_ref = reference(ROOT / "artifacts/software-benchmark-v054/manifests/slots.json")
    if slots_ref["sha256"] != SLOTS_SHA:
        raise ValueError("Frozen slots changed")
    authorization, plan = read(AUTH), read(PLAN)
    check_plan(authorization, plan, load_ref(slots_ref))
    source_ref, registry_ref = reference(SOURCE), reference(ROOT / "config/v054-public-test-registry.json")
    source = load_ref(source_ref)
    files = source["files"]
    required = {
        ROOT / "src/proworksim/software_benchmark_queue_v054.py",
        ROOT / "src/proworksim/software_benchmark_service_factory_v054.py",
        ROOT / "src/proworksim/software_benchmark_slot_factory_v054.py",
        ROOT / "src/proworksim/software_benchmark_runner_v054.py",
        ROOT / "src/proworksim/software_benchmark_scorer_r5_v054.py",
        ROOT / "tools/run_formal_queue_v054.py",
    }
    if not required.issubset({Path(item["path"]).resolve() for item in files}):
        raise ValueError("Final source manifest lacks queue, runner, factories or r5")
    for item in files:
        checked(item)
    registry = load_ref(registry_ref)
    if (registry.get("planned_tasks") != 500 or len(registry["entries"]) != 500
            or not all(x["admitted"] for x in registry["entries"])):
        raise ValueError("All 500 public frontends must be admitted before dispatch")
    capacities = {"REF": reference(ref_capacity), "MATCH": reference(match_capacity)}
    from .software_benchmark_service_factory_v054 import capacity_admission, condition_reference
    admission_refs = []
    for arm, item in capacities.items():
        admitted = capacity_admission(arm, item)
        admission_refs.extend([admitted, load_ref(admitted)["admitted_modes"][arm]["source_seal"]])
    scorer_ref = reference(scorer_manifest)
    if Path(scorer_ref["path"]).name != "installation-manifest-r5.json":
        raise ValueError("Use the mapped official r5 installation manifest")
    conditions = {arm: condition_reference(arm) for arm in ("REF", "MATCH", "PROJECT")}
    references = [reference(AUTH), reference(PLAN), slots_ref, source_ref, registry_ref,
                  scorer_ref, *capacities.values(), *admission_refs, *conditions.values(), *files]
    unique = {item["path"]: item for item in references}
    for item in unique.values():
        checked(item)
    value = {"version": VERSION, "created_utc": now(), "execution_authorized": True,
             "authorization": reference(AUTH), "plan": reference(PLAN), "slots": slots_ref,
             "source_manifest": source_ref, "registry": registry_ref, "scorer_manifest": scorer_ref,
             "capacities": capacities, "capacity_admission": admission_refs[0], "conditions": conditions,
             "frozen_files": [{"reference": item, "stat": stat_id(item["path"])}
                              for item in unique.values()],
             "model_loads": 0, "slot_claims": 0, "automatic_start": False}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    return write_new(output, value)


def validate_frozen(bindings, *, initial=False):
    for item in bindings["frozen_files"]:
        ref = item["reference"]
        if initial:
            checked(ref)
        if stat_id(ref["path"]) != item["stat"]:
            raise ValueError("Frozen source/configuration file changed: " + ref["path"])


def head_slot(rows):
    """Never jump over a pending or still-unclaimed predecessor."""
    for row in rows:
        generation = row["generation"]
        if generation["status"] == "pending":
            return row
        if generation["status"] in ACTIVE and not generation.get("claimed", False):
            return None
        if generation["status"] == "technical_unknown":
            return None
    return None


def generation_outcome(returncode, result, claimed):
    if (returncode == 75 and not claimed and result.get("status") == "resource_not_ready"
            and result.get("reason_code") in BUSY and result.get("slot_claimed") is False
            and result.get("entered") is False and result.get("model_calls") == 0
            and result.get("GPU_loads") == 0):
        return "resource_wait"
    if (returncode == 0 and claimed
            and result.get("status") == "closed_candidate_and_official_requests_ready"
            and result.get("hidden_feedback_to_actor") is False):
        return "closed"
    return "technical_unknown"


def scorer_argv(request_path):
    return [str(ROOT / "tools/run_benchmark_runtime_v054.sh"), "--write-project", "/usr/bin/env",
            "PYTHONPATH=" + str(ROOT / "src"), "HF_HUB_OFFLINE=1", "HF_DATASETS_OFFLINE=1",
            "TRANSFORMERS_OFFLINE=1", "NO_PROXY=*", "no_proxy=*", "HTTP_PROXY=", "HTTPS_PROXY=",
            "ALL_PROXY=", "http_proxy=", "https_proxy=", "all_proxy=",
            str(ROOT / "runs/software-benchmark-v054/scorer-venv/bin/python"), "-B", "-m",
            "proworksim.software_benchmark_scorer_r5_v054", "--request", str(request_path)]


def command_worker(job_ref):
    """A unique, non-restarting systemd unit owns this process and its child."""
    job = load_ref(job_ref)
    root = Path(job_ref["path"]).parent
    with lock_file(root / "worker.lock"):
        if (root / "completion.json").exists() or (root / "started.json").exists():
            raise ValueError("A completed worker may never be replayed")
        validate_frozen(load_ref(job["bindings"]))
        # Independent host lease is held across real grading, including a
        # controller restart. The scheduler count is an additional bound.
        grading_lease = None
        if job["kind"] == "score":
            for index in range(2):
                try:
                    grading_lease = lock_file(QUEUE / "locks" / ("grader-" + str(index) + ".lock"))
                    break
                except BlockingIOError:
                    continue
            if grading_lease is None:
                atomic(root / "completion.json", {"status": "technical_unknown",
                       "error": "Global two-grader lease unavailable; no scoring attempted", "returncode": None,
                       "job": job_ref, "completed_utc": now()})
                return 1
        value = {"job": job_ref, "started_utc": now(), "pid": os.getpid(), "status": "running"}
        write_new(root / "started.json", value)
        try:
            env = {**os.environ, "PYTHONPATH": str(ROOT / "src") + os.pathsep + str(ROOT),
                   "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_OFFLINE": "1",
                   "HF_DATASETS_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
                env[key] = ""
            env.update(NO_PROXY="*", no_proxy="*")
            with (root / "stdout.log").open("xb") as stdout, (root / "stderr.log").open("xb") as stderr:
                process = subprocess.Popen(job["argv"], cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
                atomic(root / "child.json", {"pid": process.pid, "started_utc": now()})
                value.update(returncode=process.wait(), status="exited", completed_utc=now())
        except BaseException as error:
            value.update(status="technical_unknown", returncode=None,
                         error={"type": type(error).__name__, "message": str(error)}, completed_utc=now())
        finally:
            atomic(root / "completion.json", value)
            if grading_lease is not None:
                grading_lease.close()
        return 0 if value.get("returncode") == 0 else 1


class Systemd:
    def launch(self, unit, job_ref):
        return subprocess.run([
            "systemd-run", "--user", "--quiet", "--collect", "--unit=" + unit,
            "--property=Type=exec", "--property=Restart=no", "--property=KillMode=control-group",
            "--property=WorkingDirectory=" + str(ROOT),
            "--setenv=PYTHONPATH=" + str(ROOT / "src") + os.pathsep + str(ROOT),
            str(HOST_PYTHON), str(ROOT / "tools/run_formal_queue_v054.py"), "worker",
            "--job", job_ref["path"], "--job-sha256", job_ref["sha256"],
        ], capture_output=True, text=True, timeout=30)

    def active(self, unit):
        result = subprocess.run(["systemctl", "--user", "show", unit,
                                 "--property=ActiveState", "--value"],
                                capture_output=True, text=True, timeout=20)
        return result.stdout.strip() in {"active", "activating", "deactivating", "reloading"}


class Coordinator:
    def __init__(self, bindings_ref, *, system=None):
        self.root = QUEUE
        self.bindings_ref = bindings_ref
        self.bindings = load_ref(bindings_ref)
        validate_frozen(self.bindings, initial=True)
        self.plan = load_ref(self.bindings["plan"])
        self.slots = load_ref(self.bindings["slots"])
        check_plan(load_ref(self.bindings["authorization"]), self.plan, self.slots)
        self.system = system or Systemd()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lease = lock_file(self.root / "controller.lock")
        path = self.root / "state.json"
        if path.exists():
            self.state = read(path)
            if self.state["bindings"] != bindings_ref:
                raise ValueError("Existing queue belongs to a different immutable binding")
        else:
            self.state = {"version": VERSION, "bindings": bindings_ref, "status": "running",
                          "created_utc": now(), "formal_execution_authorized": True,
                          "rows": [{"slot": row, "generation": {"status": "pending", "attempts": []},
                                    "scores": {}, "delivery": {"status": "pending" if row["arm"] == "PROJECT"
                                                               else "not_applicable"}}
                                   for row in self.slots["slots"]], "faults": []}
            self.save()

    def save(self):
        rows = self.state["rows"]
        active = sum(x["generation"]["status"] in ACTIVE for x in rows)
        graders = sum(y["status"] in ACTIVE for x in rows for y in x["scores"].values())
        self.state.update(updated_utc=now(), active_generation=active, active_graders=graders,
                          generation_counts=dict(Counter(x["generation"]["status"] for x in rows)),
                          scoring_counts=dict(Counter(y["status"] for x in rows for y in x["scores"].values())),
                          fully_closed_slots=sum(self.closed(x) for x in rows), planned_slots=1500,
                          planned_distinct_tasks=500, token_upper_bound=750000000)
        self.state["code_progress"] = {}
        for arm in ("REF", "MATCH", "PROJECT"):
            scores = [r["scores"].get("code", {}) for r in rows if r["slot"]["arm"] == arm]
            known = [s for s in scores if s.get("status") == "official_report"]
            success = sum(s["resolved"] for s in known)
            self.state["code_progress"][arm] = {
                "planned_denominator": 500, "determinate": len(known), "resolved": success,
                "not_yet_determinate": 500 - len(known),
                "full_panel_rate": success / 500 if len(known) == 500 else None,
                "success_rate_bounds": [success / 500, (success + 500 - len(known)) / 500]}
        atomic(self.root / "state.json", self.state)

    @staticmethod
    def closed(row):
        return (row["generation"]["status"] == "closed" and bool(row["scores"])
                and all(item["status"] == "official_report" for item in row["scores"].values())
                and row["delivery"]["status"] != "pending")

    def pause(self, kind, detail):
        self.state["status"] = "paused_technical_unknown"
        self.state["faults"].append({"utc": now(), "kind": kind, "detail": detail,
                                      "automatic_retry": False})
        self.save()

    def start_job(self, record, *, kind, directory, argv):
        directory.mkdir(parents=True, exist_ok=False)
        token = hashlib.sha256(str(directory).encode()).hexdigest()[:24]
        unit = "proworksim-v054-" + kind + "-" + token + ".service"
        job = write_new(directory / "job.json", {"kind": kind, "argv": argv,
                        "unit": unit, "bindings": self.bindings_ref, "created_utc": now()})
        record.update(status="intent", unit=unit, job=job, worker_directory=str(directory))
        self.save()  # Durable intent precedes launch; uncertain handoff is never retried.
        response = self.system.launch(unit, job)
        atomic(directory / "launch.json", {"returncode": response.returncode,
               "stdout": response.stdout, "stderr": response.stderr, "utc": now()})
        if response.returncode != 0:
            self.pause("ambiguous_unit_launch", {"unit": unit, "returncode": response.returncode})
            return
        record["status"] = "running"
        self.save()

    def completion(self, record):
        directory = Path(record["worker_directory"])
        if (directory / "completion.json").exists():
            body = read(directory / "completion.json")
            if body["job"] != record["job"]:
                raise ValueError("Worker completion has a different intent identity")
            return body
        if not self.system.active(record["unit"]):
            record["status"] = "technical_unknown"
            self.pause("worker_missing_without_completion", {"job": record["job"], "unit": record["unit"]})
        return None

    def complete_generation(self, row, completion):
        generation, slot = row["generation"], row["slot"]
        path = Path(generation["episode_output"]) / "result.json"
        result = read(path) if path.is_file() else {}
        claim = claim_path(slot["slot_id"])
        outcome = generation_outcome(completion.get("returncode"), result, claim.exists())
        generation["attempts"].append({"job": generation["job"], "outcome": outcome,
                                       "result": reference(path) if path.is_file() else None,
                                       "completion": reference(Path(generation["worker_directory"]) / "completion.json")})
        if outcome == "resource_wait":
            generation.update(status="pending", claimed=False, retry_not_before=time.time() + 30)
            return
        generation.update(status=outcome, claimed=claim.exists(), result=reference(path) if path.is_file() else None)
        if outcome != "closed" or result.get("slot_id") != slot["slot_id"]:
            generation["status"] = "technical_unknown"
            self.pause("generation_did_not_close", {"slot_id": slot["slot_id"], "result": generation["result"]})
            return
        lock = load_ref(result["candidate"])
        expected = {"code"}
        if slot["arm"] == "PROJECT":
            if lock["last_legal_delivery"]:
                expected.add("delivery")
                row["delivery"] = {"status": "awaiting_official_report"}
            else:
                row["delivery"] = {"status": "no_legal_submission", "R_delivery": 0,
                                   "official_score_performed": False}
        requests = result["official_requests"]
        if len(requests) != len(expected):
            raise ValueError("Closed slot lacks the required official endpoints")
        for item in requests:
            request = load_ref(item)
            endpoint = request["endpoint"]
            if (endpoint not in expected or endpoint in row["scores"]
                    or request["instance_id"] != slot["instance_id"] or request["arm"] != slot["arm"]
                    or request["preparation_only"] is not False or request["actor_feedback"] is not False
                    or request["scorer_manifest"] != self.bindings["scorer_manifest"]
                    or request["episode_candidate_lock"] != result["candidate"]):
                raise ValueError("Official request escaped its fixed closed slot")
            row["scores"][endpoint] = {"status": "pending", "request": item}
        generation["controller_result"] = result["controller_result"]
        controller = load_ref(result["controller_result"])
        ledger = controller["ledger"]
        model_ledger = ledger.get("model", ledger)
        generation["actual_cost_ledger"] = result["controller_result"]
        unknown = (controller.get("execution_integrity_failure") or model_ledger.get("integrity_failure")
                   or model_ledger.get("inflight") or model_ledger.get("held_tokens", 0)
                   or ("complete_actual_tokens" in model_ledger
                       and model_ledger["complete_actual_tokens"] is None))
        if unknown:
            self.pause("model_accounting_or_execution_unknown", {"slot_id": slot["slot_id"],
                       "controller_result": result["controller_result"], "actual_usage_is_not_zero": True})

    def complete_score(self, row, endpoint, completion):
        score = row["scores"][endpoint]
        request = load_ref(score["request"])
        directory = Path(score["worker_directory"])
        try:
            if completion.get("returncode") != 0:
                raise ValueError("Official scorer process did not exit successfully")
            lines = (directory / "stdout.log").read_text().splitlines()
            report = json.loads(next(line for line in reversed(lines) if line.strip()))
            run_id = report["run_id"]
            if not re.fullmatch("v054-" + row["slot"]["arm"] + "-" + endpoint + "-[0-9a-f]{40}", run_id):
                raise ValueError("Unexpected official run identity")
            root = Path(request["trusted_output_root"]) / run_id
            receipt, identity = read(root / "receipt.json"), read(root / "identity.json")
            if (receipt["status"] != "official_report" or type(receipt["resolved"]) is not bool
                    or receipt["preparation_only"] is not False or receipt["actor_feedback"] is not False
                    or receipt["run_id"] != run_id or identity["arm"] != row["slot"]["arm"]
                    or identity["endpoint"] != endpoint or identity["instance_id"] != row["slot"]["instance_id"]
                    or identity["candidate_tree_sha256"] != request["candidate_tree_sha256"]
                    or identity["patch_sha256"] != request["patch"]["sha256"]):
                raise ValueError("No determinate report for this unique locked candidate")
            score.update(status="official_report", resolved=receipt["resolved"],
                         receipt=reference(root / "receipt.json"), identity=reference(root / "identity.json"))
            if endpoint == "delivery":
                row["delivery"] = {"status": "official_report", "R_delivery": int(receipt["resolved"]),
                                   "receipt": score["receipt"]}
        except (OSError, ValueError, KeyError, StopIteration) as error:
            score.update(status="technical_unknown", error=str(error))
            self.pause("official_scoring_unknown", {"slot_id": row["slot"]["slot_id"],
                        "endpoint": endpoint, "worker": str(directory), "error": str(error)})

    def reconcile(self):
        for row in self.state["rows"]:
            generation = row["generation"]
            if generation["status"] in ACTIVE:
                try:
                    claim = claim_path(row["slot"]["slot_id"])
                    if claim.exists():
                        value = read(claim)
                        if (value["slot"] != row["slot"]
                                or value["slots"] != self.bindings["slots"]
                                or value["authorization"] != self.bindings["authorization"]):
                            raise ValueError("Global episode claim identity differs")
                        generation["claimed"] = True
                    completion = self.completion(generation)
                    if completion is not None:
                        self.complete_generation(row, completion)
                except (OSError, ValueError, KeyError) as error:
                    # A corrupt terminal result is not a reason to keep parsing
                    # it every poll or relaunch the original generation.
                    generation["status"] = "technical_unknown"
                    self.pause("generation_evidence_invalid", {"slot_id": row["slot"]["slot_id"],
                               "error": str(error), "worker": generation["worker_directory"]})
            for endpoint, score in row["scores"].items():
                if score["status"] in ACTIVE:
                    try:
                        completion = self.completion(score)
                        if completion is not None:
                            self.complete_score(row, endpoint, completion)
                    except (OSError, ValueError, KeyError) as error:
                        score["status"] = "technical_unknown"
                        self.pause("scoring_evidence_invalid", {"slot_id": row["slot"]["slot_id"],
                                   "endpoint": endpoint, "error": str(error)})

    def dispatch_scores(self):
        active = sum(y["status"] in ACTIVE for x in self.state["rows"] for y in x["scores"].values())
        for row in self.state["rows"]:
            for endpoint, score in row["scores"].items():
                if active >= 2:
                    return
                if score["status"] == "pending":
                    directory = self.root / "jobs" / str(row["slot"]["slot_index"]) / ("score-" + endpoint)
                    self.start_job(score, kind="score", directory=directory,
                                   argv=scorer_argv(checked(score["request"])))
                    active += 1

    def dispatch_generation(self):
        if self.state["status"] != "running":
            return
        rows = self.state["rows"]
        active = [x for x in rows if x["generation"]["status"] in ACTIVE]
        row = head_slot(rows)
        if row is None or len(active) >= 2:
            return
        slot, generation = row["slot"], row["generation"]
        gpu_index = self.plan["physical_gpu_by_arm"][slot["arm"]]
        if any(self.plan["physical_gpu_by_arm"][x["slot"]["arm"]] == gpu_index for x in active):
            return
        if time.time() < generation.get("retry_not_before", 0):
            return
        if claim_path(slot["slot_id"]).exists():
            raise ValueError("Pending slot already has a global once-only claim; never replay")
        from tools.prepare_model_capacity_v054 import eligible, gpu_rows
        arm = "REF" if slot["arm"] == "REF" else "MATCH"
        cards = eligible(gpu_rows(), arm)
        if not cards:
            self.state["waiting"] = {"slot_id": slot["slot_id"], "gpu_index": gpu_index,
                                     "reason": "gpu_capacity_gate", "slot_claimed": False}
            return
        card = cards[0]
        if card["index"] != gpu_index:
            raise ValueError("Capacity mode selected a GPU outside this frozen two-card plan")
        from .software_benchmark_service_factory_v054 import build_service
        from .software_benchmark_slot_factory_v054 import build_slot_config
        validate_frozen(self.bindings)
        attempt = len(generation["attempts"]) + 1
        root = self.root / "slots" / str(slot["slot_index"]) / ("preclaim-" + str(attempt))
        root.mkdir(parents=True, exist_ok=False)
        service_ref = build_service(arm=slot["arm"], capacity_reference=self.bindings["capacities"][arm],
                                    card=card, directory=root / "service")
        config = build_slot_config(slot_id=slot["slot_id"], condition_reference=self.bindings["conditions"][slot["arm"]],
                    model_service=load_ref(service_ref), registry_reference=self.bindings["registry"],
                    scorer_manifest_reference=self.bindings["scorer_manifest"], output=root / "config.json",
                    authorization=self.bindings["authorization"])
        generation.update(config=config, service=service_ref, episode_output=str(root / "episode"), claimed=False)
        self.state.pop("waiting", None)
        self.start_job(generation, kind="generation", directory=root / "worker",
                       argv=[str(HOST_PYTHON), str(ROOT / "tools/run_benchmark_episode_v054.py"),
                             "--config", config["path"], "--output", str(root / "episode")])

    def tick(self):
        try:
            source_valid = True
            try:
                validate_frozen(self.bindings)
            except (OSError, ValueError) as error:
                source_valid = False
                if not self.state.get("source_changed"):
                    self.state["source_changed"] = True
                    self.pause("frozen_source_changed", str(error))
            self.reconcile()
            # Trusted scoring can drain already locked work after a generation
            # fault. It is never exposed to a running or future actor.
            if source_valid:
                self.dispatch_scores()
                self.dispatch_generation()
            if self.state["status"] == "running" and all(self.closed(row) for row in self.state["rows"]):
                self.state["status"] = "completed_all_1500_with_official_reports"
            self.save()
        except Exception as error:
            self.pause("controller_fault", {"type": type(error).__name__, "message": str(error)})

    def run(self):
        while True:
            self.tick()
            active = self.state["active_generation"] + self.state["active_graders"]
            pending_scores = any(s["status"] == "pending" for r in self.state["rows"] for s in r["scores"].values())
            if self.state["status"].startswith("completed_"):
                return 0
            if (self.state["status"] != "running" and not active
                    and (not pending_scores or self.state.get("source_changed"))):
                return 1
            time.sleep(self.plan["resource_poll_seconds"])


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    for key in ("ref-capacity", "match-capacity", "scorer-manifest", "output"):
        freeze.add_argument("--" + key, required=True, type=Path)
    run = commands.add_parser("run")
    run.add_argument("--bindings", required=True, type=Path)
    run.add_argument("--bindings-sha256", required=True)
    worker = commands.add_parser("worker")
    worker.add_argument("--job", required=True, type=Path)
    worker.add_argument("--job-sha256", required=True)
    args = parser.parse_args(argv)
    if args.command == "freeze":
        print(json.dumps(freeze_bindings(ref_capacity=args.ref_capacity, match_capacity=args.match_capacity,
              scorer_manifest=args.scorer_manifest, output=args.output)))
        return 0
    if args.command == "worker":
        item = reference(args.job)
        if item["sha256"] != args.job_sha256:
            raise ValueError("Worker intent changed")
        return command_worker(item)
    item = reference(args.bindings)
    if item["sha256"] != args.bindings_sha256:
        raise ValueError("Formal bindings changed")
    return Coordinator(item).run()


if __name__ == "__main__":
    raise SystemExit(main())
