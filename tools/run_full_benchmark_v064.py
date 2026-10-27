"""Execute the fixed new capability panel with bounded independent runtime lanes."""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from collections import Counter
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import resource
import shutil
import signal
import threading
import time
import traceback

from proworksim import software_benchmark_dispatch_v064 as policy
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.storage import atomic_write, json_bytes

ROOT, BATCH_ROOT = policy.ROOT, policy.BATCH_ROOT
RUN_ROOT = policy.COORDINATOR_RUN_ROOT
VERSION = "v064-full-paired-coordinator-r1"
DOCKER_CONFIG = ROOT / 'runs/software-panel-v053/docker/config/daemon.json'
DISK_FLOOR_BYTES = 128 * 1024**3

def coordinator_limits():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("The capability coordinator must run as the ordinary project user")
    rows = Path("/proc/self/cgroup").read_text().splitlines()
    paths = [line.split(":", 2)[2] for line in rows if line.startswith("0::")]
    if len(paths) != 1:
        raise ValueError("The coordinator requires its own unified cgroup")
    relative = PurePosixPath(paths[0])
    if relative.name != "proworksim-v064-full-verified.service" or ".." in relative.parts:
        raise ValueError("Run formal capability evaluation only in the newly owned bounded coordinator unit")
    folder = Path("/sys/fs/cgroup") / str(relative).lstrip("/")
    values = {name: (folder / name).read_text().strip()
              for name in ("memory.max", "memory.swap.max", "pids.max")}
    cpu_file = folder / "cpu.max"
    values["cpu.max"] = cpu_file.read_text().strip() if cpu_file.exists() else None
    cpu = values["cpu.max"].split() if values["cpu.max"] is not None else None
    expected_affinity = [int(value) for value in policy.cpu_set("coordinator", 0).split(",")]
    actual_affinity = sorted(os.sched_getaffinity(0))
    if (
        values["memory.max"] != str(16 * 1024**3)
        or values["memory.swap.max"] != "0"
        or values["pids.max"] != "512"
        or actual_affinity != expected_affinity
        or (cpu is not None and (len(cpu) != 2 or not all(value.isdigit() for value in cpu)
            or int(cpu[1]) <= 0 or int(cpu[0]) <= 0 or int(cpu[0]) > 4 * int(cpu[1])))
    ):
        raise ValueError("Actual coordinator CPU/RAM/PID/swap hard limits differ from the grant")
    return {
        "cgroup": paths[0],
        "actual_limits": values,
        "actual_cpu_affinity": actual_affinity,
        "cpu_hard_boundary": "fixed process affinity",
        "cpu_quota_controller_available": cpu is not None,
        "cpu_quota_enforced": cpu is not None,
        "uid": os.getuid(),
        "host_configuration_changed": False,
    }

def load(ref):
    return json.loads(checked(ref).read_bytes())

def _result_is_quiet(result):
    """A local failure may continue only when its owned runtime was cleaned."""
    proof = result.get("quiescence")
    if isinstance(proof, dict) and set(proof) == {"path", "bytes", "sha256"}:
        proof = load(proof)
    return (
        isinstance(proof, dict)
        and proof.get("quiescent") is True
        and not proof.get("cleanup_errors")
        and proof.get("create_result_unknown") is False
    )

def _handle_termination(event):
    if threading.current_thread() is not threading.main_thread():
        return {}
    return {
        sig: signal.signal(sig, lambda *_: event.set()) for sig in (signal.SIGTERM, signal.SIGINT)
    }

def _restore_termination(previous):
    for sig, handler in previous.items():
        signal.signal(sig, handler)

def diagnostic_host_limits():
    allowed = sorted(os.sched_getaffinity(0))
    if len(allowed) < 4:
        raise ValueError("The zero-model diagnostic requires four available logical CPUs")
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    cap = 16 * 1024**3 if hard == resource.RLIM_INFINITY else min(hard, 16 * 1024**3)
    if cap < 4 * 1024**3:
        raise ValueError("The inherited address-space limit cannot fit the private SDK diagnostic")
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    os.sched_setaffinity(0, set(allowed[:4]))
    return {
        "address_space_bytes": cap,
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "scope": "current ordinary diagnostic process and its children only",
    }


def grading_module():
    spec = importlib.util.spec_from_file_location("v064_capability_grading", ROOT / "tools/run_capability_grading_v064.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare():
    """Materialize plans only after the new executable configurations are final."""
    dispatch = policy.create_plan()
    rows = dispatch["rows"]
    if (len(rows) != 6000 or len({row["slot_id"] for row in rows}) != 6000
            or [row["slot_index"] for row in rows] != list(range(6000))
            or any(row["replicate"] != 0 for row in rows)):
        raise ValueError("Require the complete new 500 x 12 matrix without repeats")
    grading = grading_module()
    grading.prepare_manifest()
    controls = grading.prepare_controls()
    from proworksim.software_benchmark_deepseek_runtime_v064 import prepare_schema_inventory
    api_schemas = prepare_schema_inventory()
    value = {"version": VERSION, "plan": reference(policy.PLAN_FILE), "controls": controls,
             "reused_qualifications": {}, "sources": policy.sources(),
             "disk_boundary": prepare_disk_boundary(),
             "new_generation_rows": [row["slot_index"] for row in rows],
             "new_generation_token_upper_bound": sum(row["generation_token_upper_bound"] for row in rows),
             "maximum_generation_futures": 12, "maximum_grading_futures": 4,
             "api_tool_schema_inventory": api_schemas,
             "api_total_budget_cny": "1500.00", "automatic_replay": False,
             "prepared_without_runtime_operations": True}
    path = RUN_ROOT / "coordinator-plan.json"
    return policy.retain(path, value)


def prepare_disk_boundary():
    """Read local daemon config and filesystem identities; never contact Docker."""
    source = reference(DOCKER_CONFIG)
    config = load(source)
    data_root = Path(config['data-root']).resolve()
    expected = ROOT / 'runs/software-panel-v053/docker/data'
    if data_root != expected.resolve():
        raise ValueError('The dedicated Docker data-root differs from the reviewed project daemon')
    paths = [ROOT.resolve(), data_root]
    devices = {str(path): path.stat().st_dev for path in paths}
    return {'daemon_configuration': source, 'paths_and_devices': devices,
            'same_filesystem': len(set(devices.values())) == 1, 'minimum_free_bytes': DISK_FLOOR_BYTES,
            'poll_seconds': 5, 'disk_hard_quota': False,
            'scope': 'admission and early cancellation only; shared filesystem is unchanged'}


def check_disk_boundary(boundary):
    checked(boundary['daemon_configuration'])
    if boundary['minimum_free_bytes'] != DISK_FLOOR_BYTES or boundary.get('disk_hard_quota') is not False:
        raise ValueError('The disk guard is a fixed free-space floor, not a hard quota')
    observed = {}
    for path, device in boundary['paths_and_devices'].items():
        if Path(path).stat().st_dev != device:
            raise ValueError('A guarded filesystem changed since local preparation')
        if device not in observed:
            observed[device] = {'path': path, 'device': device, 'free_bytes': shutil.disk_usage(path).free}
    return {'passed': bool(observed) and all(row['free_bytes'] >= DISK_FLOOR_BYTES for row in observed.values()),
            'filesystems': list(observed.values()), 'minimum_free_bytes': DISK_FLOOR_BYTES,
            'disk_hard_quota': False}


def _event(kind, **values):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    with (RUN_ROOT / 'events.jsonl').open('a') as stream:
        stream.write(json.dumps({'unix': time.time(), 'kind': kind, **values}, ensure_ascii=False) + '\n')


def _progress(value):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_write(RUN_ROOT / 'progress.json', json_bytes({'version': VERSION, 'unix': time.time(), **value}))


def model_admission_exhausted(ready):
    if ready:
        return False
    folders = [BATCH_ROOT / 'residents' / f'model-{index}' for index in range(6)]
    return all((folder / 'spec.json').exists() and (folder / 'closed.json').exists() for folder in folders)


def _diagnostic_arm(index):
    if type(index) is not int or index not in (1, 2, 3, 4):
        raise ValueError('Use one of the four explicitly reserved diagnostic identities')
    return 'REF' if index % 2 else 'PROJECT'


def diagnostic_admission(index):
    arm = _diagnostic_arm(index)
    if (RUN_ROOT / 'execution-started.json').exists():
        raise ValueError('Diagnostics cannot run after this panel has entered execution')
    qualifications = BATCH_ROOT / 'diagnostic-qualifications' / arm
    for path in qualifications.glob('*.json'):
        if load(reference(path)).get('sources') == policy.sources():
            raise ValueError('This protocol has already passed for current sources; do not repeat it')
    attempts = BATCH_ROOT / 'diagnostic-attempts'
    if (attempts / f'{index}-intent.json').exists() or (attempts / f'{index}.json').exists():
        raise ValueError('An entered diagnostic identity cannot be retried')
    if index > 2:
        prior = load(reference(attempts / f'{index - 2}.json'))
        result = load(prior['result']) if prior.get('result') else None
        if (not isinstance(result, dict) or result.get('model_calls') != 0 or not _result_is_quiet(result)
                or prior.get('sources') == policy.sources()):
            raise ValueError('A reserved diagnostic requires a cleaned zero-model prior attempt and revised sources')
    return arm


def diagnose(index=1):
    policy.require_v064_allowed('v064.run')
    arm = diagnostic_admission(index)
    sources = policy.sources()
    limits = diagnostic_host_limits()
    attempts = BATCH_ROOT / 'diagnostic-attempts'
    attempts.mkdir(parents=True, exist_ok=True)
    write_new(attempts / f'{index}-intent.json', {'version': VERSION, 'arm': arm, 'index': index,
              'sources': sources, 'actual_host_limits': limits})
    from proworksim.software_benchmark_episode_v064 import run_diagnostic

    stopped = threading.Event()
    handlers = _handle_termination(stopped)
    record = {'version': VERSION, 'arm': arm, 'diagnostic_index': index,
              'sources': sources, 'actual_host_limits': limits, 'result': None}
    try:
        record['result'] = run_diagnostic(index=index, stop_event=stopped)
    except BaseException as error:
        record.update(status='runtime_exception', error={'type': type(error).__name__, 'message': str(error)},
                      traceback=traceback.format_exc(), cleanup_not_inferred_without_result=True)
        raise
    finally:
        write_new(attempts / f'{index}.json', record)
        _restore_termination(handlers)
    result = load(record['result'])
    if (result.get('passed') is not True or result.get('model_calls') != 0
            or not _result_is_quiet(result) or sources != policy.sources()):
        raise ValueError('Zero-model protocol diagnostic must pass, be cleaned and bind the current sources')
    directory = BATCH_ROOT / 'diagnostic-qualifications' / arm
    directory.mkdir(parents=True, exist_ok=True)
    return write_new(directory / f'{index}.json', record)


def diagnostic_qualifications():
    results = {}
    for arm in ('REF', 'PROJECT'):
        matches = [load(reference(path)) for path in (BATCH_ROOT / 'diagnostic-qualifications' / arm).glob('*.json')
                   if load(reference(path)).get('sources') == policy.sources()]
        if len(matches) != 1:
            raise ValueError('Each native protocol needs exactly one current-source qualification')
        record = matches[0]
        result = load(record['result'])
        if (record.get('version') != VERSION or record.get('arm') != arm
                or record.get('sources') != policy.sources() or result.get('passed') is not True
                or not _result_is_quiet(result) or result.get('model_calls') != 0):
            raise ValueError('Both native protocols need current, clean zero-model qualifications')
        results[arm] = record['result']
    return results


def _slot_entered(row):
    return (BATCH_ROOT / "resource-claims" / f"actor-{row['slot_index']}.json").exists()


def generation_lane_limit():
    """Leave room for two graders so generation cannot starve its own queue."""
    models = len(list((BATCH_ROOT / "resource-claims").glob("active-model-*.json")))
    by_memory = (832 - 16 - 96 * models - 2 * 16) // 20
    by_cpu = (152 - 4 - 12 * models - 2 * 4) // 6
    return max(0, min(12, by_memory, by_cpu))


def _child_result(result):
    ref = result.get("controller_result")
    return load(ref) if isinstance(ref, dict) else {}


def administrative_truncation(result):
    if result.get("api_administrative_truncation") is True:
        return True
    child = _child_result(result)
    values = [result.get("adapter_halted"), child.get("adapter_halted"),
              result.get("terminal_boundary"), child.get("terminal_boundary"),
              result.get("closure_reason"), child.get("closure_reason")]
    # Only control-plane termination fields are inspected, never issue/model text.
    for value in values:
        if isinstance(value, dict):
            value = value.get("classification") or value.get("reason") or value.get("message")
        if isinstance(value, str) and any(marker in value for marker in (
                "global_cny_budget_reservation_insufficient", "ledger_halted:")):
            return True
    return False


def generation_stop_reason(result, row, api_status=None):
    if not _result_is_quiet(result):
        return "unproven_generation_cleanup"
    if (result.get("batch_stop_required") is True or result.get("response_projection_fault")
            or result.get("shared_integrity_failure") is True):
        return "shared_generation_integrity_failure"
    if row["model_key"] == "DEEPSEEK" and api_status is not None:
        if api_status.get("state") == "shared_halted":
            return "unbounded_or_invalid_api_money_authority"
        # Authoritative shared API money is fully reserved even if one episode
        # lost its response. Its token usage remains unknown in the report.
        return None
    ledger = result.get("ledger")
    if not isinstance(ledger, dict):
        return None if result.get("model_calls") == 0 and result.get("model_dispatch_started") is not True else "missing_qwen_usage_reservation"
    known, reserved = ledger.get("known_actual_tokens"), ledger.get("uncertain_reserved_tokens", 0)
    if (type(known) is not int or known < 0 or type(reserved) is not int or reserved < 0
            or known + reserved > row["generation_token_upper_bound"]):
        return "unbounded_qwen_episode_accounting"
    complete = ledger.get("complete_actual_tokens")
    if complete is not None and (complete != known or reserved or ledger.get("inflight") is not None):
        return "inconsistent_qwen_episode_accounting"
    if complete is None and not reserved and result.get("model_calls") != 0:
        return "missing_qwen_unknown_usage_bound"
    return None


@contextmanager
def _executor_pair(stop):
    with ThreadPoolExecutor(max_workers=12) as generation, ThreadPoolExecutor(max_workers=4) as grading:
        try:
            yield generation, grading
        finally:
            stop.set()


def execute_queue(rows, *, controls, qualifications, grading, runtime, run_episode,
                  api_runtime=None, stop_event=None, progress_sink=_progress, event_sink=_event,
                  disk_check=None, result_sink=None, entered_probe=_slot_entered,
                  model_exhausted=model_admission_exhausted, generation_limit=generation_lane_limit):
    """Twelve independent generation pairs, four asynchronous grading lanes."""
    stop = stop_event if stop_event is not None else threading.Event()
    pending, control_queue, score_queue = list(rows), list(controls), []
    qualified = dict(qualifications)
    generations, scores, deliveries, controls_done, exceptions = {}, {}, {}, {}, []
    generation_futures, grade_futures = {}, {}
    scheduled, entered = set(), set()
    failure, closure, disk_observation, api_status = None, [], None, None
    residents = []
    progress_cache = {"signature": None}
    if len({row["slot_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate new slot identity")

    def fail(kind, **values):
        nonlocal failure
        failure = failure or {"kind": kind, **values}
        stop.set()

    def record_unentered(row, reason, **values):
        pending.remove(row)
        generations[row["slot_id"]] = {"status": "not_started", "entered": False,
            "not_started_reason": reason, **values}
        if result_sink is not None:
            try:
                result_sink(row, generations[row["slot_id"]], None, scores.get(row["slot_id"]),
                            deliveries.get(row["slot_id"]))
            except Exception as error:
                isolated_exception("usage_measurement", row, error=str(error))
        event_sink("generation_not_started", slot_id=row["slot_id"], reason=reason)

    def isolated_exception(kind, row=None, **values):
        item = {"kind": kind, **({"slot_id": row["slot_id"]} if row else {}), **values}
        exceptions.append(item)
        event_sink("isolated_exception", exception=item)

    def report():
        for row, _ in generation_futures.values():
            if entered_probe(row):
                entered.add(row["slot_id"])
        if result_sink is not None and hasattr(result_sink, "refresh_active"):
            try:
                result_sink.refresh_active([row for row, _ in generation_futures.values()
                                            if row["slot_id"] in entered])
            except Exception as error:
                isolated_exception("live_usage_reporting", error=str(error))
        signature = len(entered), len(generations)
        if progress_cache["signature"] != signature:
            status_counts = Counter(value["status"] for value in generations.values())
            groups = {}
            for row in rows:
                group = groups.setdefault(row["group_id"], {"planned": 0, "entered": 0,
                    "generation_closed": 0, "not_started": 0, "technical_unknown": 0})
                group["planned"] += 1
                group["entered"] += row["slot_id"] in entered
                result = generations.get(row["slot_id"], {})
                if result.get("status") in {"closed", "not_started", "technical_unknown"}:
                    field = "generation_closed" if result["status"] == "closed" else result["status"]
                    group[field] += 1
            progress_cache.update(signature=signature, groups=groups, status_counts=dict(status_counts),
                finished=sum(value.get("entered") is True for value in generations.values()),
                unentered=sum(value.get("entered") is False for value in generations.values()))
        progress_sink({"phase": "stopping" if stop.is_set() else "running",
            "planned_generation": len(rows), "scheduled_generation": len(scheduled),
            "entered_generation": len(entered),
            "finished_generation": progress_cache["finished"],
            "accounted_unentered_generation": progress_cache["unentered"],
            "pending_generation": len(pending), "active_generation": len(generation_futures),
            "active_grading": len(grade_futures), "pending_controls": len(control_queue),
            "pending_scores": len(score_queue), "finished_code_scores": len(scores),
            "finished_delivery_endpoints": sum(value.get("status") != "waiting_for_own_code_score" for value in deliveries.values()),
            "generation_status_counts": progress_cache["status_counts"], "groups": progress_cache["groups"],
            "isolated_exception_count": len(exceptions), "failure": failure,
            "disk_guard": disk_observation, "api_status": api_status})

    def update_result(row):
        entry = generations[row["slot_id"]]
        if result_sink is not None:
            try:
                result_sink(row, entry, load(entry["result"]) if entry.get("result") else None,
                            scores.get(row["slot_id"]), deliveries.get(row["slot_id"]))
            except Exception as error:
                isolated_exception("usage_measurement", row, error=str(error))
                if hasattr(result_sink, "mark_unknown"):
                    result_sink.mark_unknown(row, entry, str(error))

    def delivery_after_code(row, result_ref, request_ref):
        if row["arm"] != "PROJECT":
            return
        try:
            value = grading.delivery_disposition(result_ref, request_ref)
            deliveries[row["slot_id"]] = value
            if value.get("scoring_request") is not None:
                score_queue.append(("delivery", row, value["scoring_request"], True))
        except Exception as error:
            deliveries[row["slot_id"]] = {"status": "technical_unknown", "resolved": None,
                                           "error": {"type": type(error).__name__, "message": str(error)}}
            isolated_exception("delivery_evidence_or_preparation", row, error=str(error))

    try:
        if disk_check is not None:
            disk_observation = disk_check()
            if disk_observation.get("passed") is not True:
                fail("disk_free_space_floor", observation=disk_observation)
                raise RuntimeError("The fixed disk floor did not pass admission")
        residents = runtime.start_residents()
        last_capacity = last_disk = 0.0
        with _executor_pair(stop) as (generation_pool, grade_pool):
            while pending or control_queue or score_queue or generation_futures or grade_futures:
                if stop.is_set() and failure is None:
                    fail("coordinator_cancellation_requested")
                if disk_check is not None and time.monotonic() - last_disk >= 5:
                    disk_observation = disk_check()
                    last_disk = time.monotonic()
                    if disk_observation.get("passed") is not True:
                        fail("disk_free_space_floor", observation=disk_observation)
                if not stop.is_set() and time.monotonic() - last_capacity >= 60:
                    residents = runtime.start_residents()
                    last_capacity = time.monotonic()
                if api_runtime is not None:
                    api_status = api_runtime.budget_status()
                    if api_status.get("state") == "shared_halted":
                        fail("unbounded_or_invalid_api_money_authority", observation=api_status)
                for row in list(pending):
                    if qualified.get(row["instance_id"], {}).get("status") == "not_qualified":
                        record_unentered(row, "environment_not_qualified", qualification=qualified[row["instance_id"]])
                    elif row["model_key"] == "DEEPSEEK" and api_status and api_status.get("state") in {
                            "cash_exhausted", "qualification_failed"}:
                        reason = "api_monetary_budget_exhausted" if api_status["state"] == "cash_exhausted" else "api_qualification_failed"
                        record_unentered(row, reason)
                while not stop.is_set() and len(grade_futures) < 4 and (score_queue or control_queue):
                    row = None
                    if score_queue:
                        kind, row, item, prepared = score_queue.pop(0)
                        try:
                            request_ref = item if prepared else grading.prepare_score(item, endpoint="code")
                        except Exception as error:
                            isolated_exception("score_preparation", row, endpoint=kind, error=str(error))
                            if kind == "code":
                                scores[row["slot_id"]] = {"status": "technical_unknown", "error": str(error)}
                                delivery_after_code(row, item, None)
                            else:
                                deliveries[row["slot_id"]] = {"status": "technical_unknown", "resolved": None, "error": str(error)}
                            update_result(row)
                            continue
                    else:
                        kind, request_ref = "control", control_queue.pop(0)
                    future = grade_pool.submit(grading.run_request, request_ref, stop_event=stop)
                    grade_futures[future] = kind, request_ref, row
                generation_ceiling = generation_limit()
                if not stop.is_set() and pending and len(generation_futures) < generation_ceiling:
                    residents = runtime.ready_residents()
                    if any(row["model_key"] == "QWEN" for row in pending) and model_exhausted(residents):
                        # Known exhausted deployment identities are coverage gaps,
                        # not a reason to cancel independent API runs or graders.
                        for row in list(pending):
                            if row["model_key"] == "QWEN":
                                record_unentered(row, "local_model_admission_exhausted")
                while not stop.is_set() and len(generation_futures) < generation_ceiling:
                    counts = Counter(resident["root"] for row, resident in generation_futures.values()
                                     if row["model_key"] == "QWEN")
                    eligible_residents = [value for value in residents if counts[value["root"]] < 2]
                    api_ready = api_runtime is not None and api_status and api_status.get("can_start_generation") is True
                    row = next((row for row in pending
                        if qualified.get(row["instance_id"], {}).get("status") == "qualified"
                        and ((row["model_key"] == "QWEN" and eligible_residents)
                             or (row["model_key"] == "DEEPSEEK" and api_ready))), None)
                    if row is None:
                        break
                    if row["slot_id"] in scheduled:
                        raise RuntimeError("An already scheduled slot was placed back in the pending queue")
                    if row["model_key"] == "QWEN":
                        resident = min(eligible_residents, key=lambda value: (counts[value["root"]], value["root"]))
                        kwargs = {"stop_event": stop}
                    else:
                        resident = api_runtime.logical_resident()
                        kwargs = {"stop_event": stop, "api_transport_factory": api_runtime.transport_factory}
                    pending.remove(row)
                    scheduled.add(row["slot_id"])
                    event_sink("generation_scheduled", slot_id=row["slot_id"], model_key=row["model_key"],
                               resident=resident.get("root", "deepseek-direct-api"))
                    future = generation_pool.submit(run_episode, row, resident, **kwargs)
                    generation_futures[future] = row, resident
                report()
                futures = list(grade_futures) + list(generation_futures)
                if not futures:
                    if stop.is_set() or not (pending or control_queue or score_queue):
                        break
                    if pending and not control_queue and any(
                            qualified.get(row["instance_id"], {}).get("status") not in {"qualified", "not_qualified"}
                            for row in pending):
                        fail("missing_environment_qualification")
                        continue
                    stop.wait(1)
                    continue
                completed, _ = wait(futures, timeout=1, return_when=FIRST_COMPLETED)
                for future in completed:
                    if future in grade_futures:
                        kind, request_ref, row = grade_futures.pop(future)
                        request = load(request_ref)
                        try:
                            completion = future.result()
                        except Exception as error:
                            completion = {"status": "technical_unknown", "error": str(error)}
                        if not grading.trustworthy_cleanup(request_ref):
                            fail("unproven_grader_cleanup", request=request_ref)
                        if kind == "control":
                            task = request["instance_id"]
                            controls_done.setdefault(task, {})[request["patch_kind"]] = completion
                            if set(controls_done[task]) == {"empty", "gold"}:
                                try:
                                    qualified[task] = {"status": "qualified", "qualification": grading.qualify(task)}
                                except Exception as error:
                                    qualified[task] = {"status": "not_qualified", "reason": str(error)}
                                    isolated_exception("environment_not_qualified", error=str(error), instance_id=task)
                        elif kind == "code":
                            scores[row["slot_id"]] = {"request": request_ref, "completion": completion}
                            delivery_after_code(row, generations[row["slot_id"]]["result"], request_ref)
                            update_result(row)
                        else:
                            deliveries[row["slot_id"]] = {"status": "official_attempt_completed",
                                "request": request_ref, "completion": completion}
                            update_result(row)
                        event_sink("grading_finished", job_kind=kind, request=request_ref, status=completion.get("status"))
                    else:
                        row, resident = generation_futures.pop(future)
                        try:
                            result_ref = future.result()
                            result = load(result_ref)
                            if (result.get("slot_id") != row["slot_id"]
                                    or result.get("configuration") != row["configuration"]):
                                raise ValueError("Generation returned another slot/configuration")
                            entered.add(row["slot_id"])
                            administrative = row["model_key"] == "DEEPSEEK" and administrative_truncation(result)
                            generations[row["slot_id"]] = {"result": result_ref, "status": result.get("status"),
                                "entered": True, "administrative_truncation": administrative,
                                "retained_objects": result.get("retained_objects", [])}
                            reason = generation_stop_reason(result, row, api_status)
                            if reason:
                                fail(reason, result=result_ref)
                            elif result.get("status") == "closed":
                                score_queue.append(("code", row, result_ref, False))
                            else:
                                isolated_exception("generation_technical_unknown", row, result=result_ref)
                            if administrative:
                                isolated_exception("api_administrative_truncation", row, result=result_ref,
                                                   normal_model_failure=False)
                            update_result(row)
                        except policy.ResourceBusy:
                            if entered_probe(row):
                                fail("capacity_exception_after_consumed_identity", slot_id=row["slot_id"])
                            else:
                                scheduled.remove(row["slot_id"])
                                pending.append(row)
                                pending.sort(key=lambda value: value["slot_index"])
                        except InterruptedError as error:
                            if entered_probe(row):
                                fail("generation_cancelled_without_cleanup", slot_id=row["slot_id"], error=str(error))
                            else:
                                pending.append(row)
                                pending.sort(key=lambda value: value["slot_index"])
                        except Exception as error:
                            generations[row["slot_id"]] = {"status": "technical_unknown",
                                "entered": entered_probe(row), "error": str(error)}
                            fail("generation_failed_without_trusted_result", slot_id=row["slot_id"])
                        event_sink("generation_finished", slot_id=row["slot_id"],
                                   status=generations.get(row["slot_id"], {}).get("status", "not_entered"))
                if stop.is_set() and not grade_futures and not generation_futures:
                    break
    except Exception as error:
        fail("coordinator_error", error={"type": type(error).__name__, "message": str(error)})
    finally:
        stop.set()
        try:
            closure = runtime.stop_residents()
        except Exception as error:
            closure = [{"owned_unit_stopped": False, "error": str(error)}]
        if any(value.get("owned_unit_stopped") is not True for value in closure):
            failure = failure or {"kind": "resident_cleanup_unconfirmed"}
        report()
    return {"version": VERSION, "generation": generations, "scores": scores, "deliveries": deliveries,
            "qualifications": qualified, "exceptions": exceptions,
            "unentered_generation": [row["slot_id"] for row in pending],
            "unentered_controls": control_queue, "unentered_scores": score_queue,
            "resident_closure": closure, "failure": failure, "last_disk_guard": disk_observation,
            "last_api_status": api_status, "automatic_replay": False, "historical_results_overwritten": False,
            "retained_objects": [{"slot_id": slot, **obj} for slot, value in generations.items()
                                 for obj in value.get("retained_objects", [])]}


def qwen_usage(row, result):
    from proworksim.software_benchmark_usage_metrics_v064 import normalize_usage_call
    ledger = result.get("ledger") or {}
    calls, by_id = [], {}
    for index, item in enumerate(ledger.get("calls", []), 1):
        if not isinstance(item.get("usage"), dict):
            continue
        identity = item.get("native_attempt_id") or f"{row['slot_id']}:attempt:{item.get('attempt', index)}"
        value = normalize_usage_call(identity, item.get("usage_id", "unclassified"), item["usage"])
        calls.append(value)
        by_id[identity] = value
    complete = (type(ledger.get("complete_actual_tokens")) is int
                and ledger["complete_actual_tokens"] == ledger.get("known_actual_tokens")
                and ledger.get("inflight") is None and ledger.get("uncertain_reserved_tokens", 0) == 0)
    if complete:
        actual = sum(call["prompt_tokens"] + call["completion_tokens"] for call in calls)
        if actual != ledger["known_actual_tokens"]:
            raise ValueError("Complete Qwen usage ledger and per-call receipts disagree")
    else:
        folder = BATCH_ROOT / "episodes" / str(row["slot_index"]) / "host-model-usage"
        for path in sorted(folder.glob("*.json")):
            item = load(reference(path))
            if item.get("slot_id") != row["slot_id"] or item.get("usage_valid") is not True:
                continue
            identity = item["call_id"]
            value = normalize_usage_call(identity, item.get("purpose", "host_unclassified"), item["usage"])
            if identity in by_id:
                if any(by_id[identity][key] != value[key] for key in ("prompt_tokens", "completion_tokens")):
                    raise ValueError("Qwen controller and host disagree on an actual response")
            else:
                calls.append(value)
                by_id[identity] = value
    unresolved = []
    reserved = ledger.get("uncertain_reserved_tokens", 0)
    if type(reserved) is int and reserved > 0:
        unresolved.append({"call_id": row["slot_id"] + ":unresolved-ledger",
                           "reserved_tokens": reserved, "reserved_cost_cny": None})
    if not ledger and result.get("model_calls") == 0 and result.get("model_dispatch_started") is not True:
        complete = True
    return {"calls": calls, "unresolved_calls": unresolved,
            "usage_capture_complete": complete, "usage_source": "controller_ledger_with_known_host_receipt_recovery"}


def code_receipt(entry):
    if not entry or not entry.get("request"):
        return None
    request = load(entry["request"])
    path = Path(request["directory"]) / "receipt.json"
    return load(reference(path)) if path.exists() else None


class UsageRecorder:
    """Keep the actual twelve-group mean up to date without rereading old runs."""

    def __init__(self, matrix, api_runtime):
        self.matrix, self.api_runtime = matrix, api_runtime
        self.records, self.last_write, self.last_active_refresh = {}, 0.0, 0.0

    def save_record(self, row, record):
        path = RUN_ROOT / "usage-records" / (str(row["slot_index"]) + ".json")
        atomic_write(path, json_bytes(record))
        # Retain only counters and a file reference in the coordinator, not the
        # raw controller ledger or thousands of full source-version records.
        self.records[row["slot_id"]] = {
            "record": reference(path), "group_id": row["group_id"],
            "entered": record["entered"], "generation_state": record["generation_state"],
            "code_result": record["code_result"], "administrative_truncation": record.get("administrative_truncation", False),
            "usage_capture_complete": record["usage_capture_complete"],
            "prompt_tokens_known": sum(call["prompt_tokens"] for call in record["calls"]),
            "completion_tokens_known": sum(call["completion_tokens"] for call in record["calls"]),
            "uncertain_reserved_tokens": sum(call["reserved_tokens"] for call in record["unresolved_calls"])}

    def mark_unknown(self, row, entry, error):
        record = {"slot_id": row["slot_id"], "group_id": row["group_id"],
            "entered": entry.get("entered") is True, "generation_state": "technical_unknown" if entry.get("entered") else "not_started",
            "not_started_reason": entry.get("not_started_reason"), "code_result": None,
            "code_status": "technical_unknown", "delivery_result": None, "calls": [],
            "unresolved_calls": [], "usage_capture_complete": False, "measurement_error": error}
        self.save_record(row, record)

    def refresh_active(self, rows):
        if time.monotonic() - self.last_active_refresh < 60:
            return
        for row in rows:
            try:
                usage = (self.api_runtime.usage_for_slot(row) if row["model_key"] == "DEEPSEEK"
                         else qwen_usage(row, {}))
                record = {"slot_id": row["slot_id"], "group_id": row["group_id"],
                    "entered": True, "generation_state": "running", "code_result": None,
                    "code_status": "pending", "delivery_result": None, **usage}
                self.save_record(row, record)
            except Exception as error:
                self.mark_unknown(row, {"entered": True}, str(error))
        self.last_active_refresh = time.monotonic()
        self.flush()

    def __call__(self, row, entry, result, score, delivery):
        entered = entry.get("entered") is True
        state = entry.get("status") if entered else "not_started"
        state = state if state in {"closed", "technical_unknown", "not_started"} else "technical_unknown"
        if entered:
            usage = (self.api_runtime.usage_for_slot(row) if row["model_key"] == "DEEPSEEK"
                     else qwen_usage(row, result or {}))
        else:
            usage = {"calls": [], "unresolved_calls": [], "usage_capture_complete": False}
        official = code_receipt(score)
        known = official is not None and official.get("status") == "official_report" and type(official.get("resolved")) is bool
        administrative = entry.get("administrative_truncation") is True
        code = official["resolved"] if known and not administrative else None
        code_status = "scored" if code is not None else "technical_unknown" if (
            official or administrative or state == "technical_unknown" or (score and score.get("status") == "technical_unknown")) else "pending"
        delivered = None
        if row["arm"] == "PROJECT" and delivery:
            if type(delivery.get("resolved")) is bool:
                delivered = delivery["resolved"]
            elif delivery.get("request"):
                receipt = code_receipt(delivery)
                if receipt and receipt.get("status") == "official_report":
                    delivered = receipt.get("resolved")
        diagnostic_delivery = delivered
        if administrative:
            delivered = None
        record = {
            "slot_id": row["slot_id"], "group_id": row["group_id"], "instance_id": row["instance_id"],
            "model_key": row["model_key"], "arm": row["arm"], "entered": entered,
            "generation_state": state, "not_started_reason": entry.get("not_started_reason"),
            "code_result": code, "code_status": code_status, "delivery_result": delivered,
            "administrative_truncation": administrative,
            "diagnostic_official_code_result": official.get("resolved") if official else None,
            "diagnostic_delivery_result": diagnostic_delivery,
            "generation_result": entry.get("result"), **usage}
        self.save_record(row, record)
        self.flush()

    def flush(self, *, final=False):
        if not final and time.monotonic() - self.last_write < 60:
            return
        if final:
            from proworksim.software_benchmark_usage_metrics_v064 import summarize
            preparation = self.api_runtime.preparation_usage() if self.api_runtime is not None else {}
            # Read per-episode compact receipts sequentially only at finalization.
            report = summarize(self.matrix, (load(value["record"]) for value in self.records.values()),
                preparation_calls=preparation.get("calls", []),
                preparation_unresolved_calls=preparation.get("unresolved_calls", []))
            atomic_write(RUN_ROOT / "actual-usage-records.json", json_bytes({
                "record_files": {key: value["record"] for key, value in self.records.items()},
                "preparation_calls": preparation.get("calls", []),
                "preparation_unresolved_calls": preparation.get("unresolved_calls", [])}))
        else:
            groups = {}
            for group_id in self.matrix["groups"]:
                selected = [value for value in self.records.values() if value["group_id"] == group_id]
                final_usage = [value for value in selected if value["entered"]
                               and value["generation_state"] in {"closed", "technical_unknown"}
                               and value["usage_capture_complete"] and not value["uncertain_reserved_tokens"]]
                known = sum(value["prompt_tokens_known"] + value["completion_tokens_known"] for value in selected)
                final_total = sum(value["prompt_tokens_known"] + value["completion_tokens_known"] for value in final_usage)
                groups[group_id] = {"planned": 500, "entered": sum(value["entered"] for value in selected),
                    "known_actual_tokens_lower_bound": known, "usage_final_episodes": len(final_usage),
                    "actual_mean_complete_usage_subset": final_total / len(final_usage) if final_usage else None,
                    "actual_mean_full_500": final_total / 500 if len(final_usage) == 500 else None}
            report = {"groups": groups, "live_compact_counters_only": True}
        report.update(version_runtime=VERSION, unix=time.time(), final=final,
            matrix=reference(policy.MATRIX_FILE), non_model_preparation_is_separate=True,
            api_budget_authority=self.api_runtime.budget_status() if self.api_runtime is not None else None,
            usage_report_is_not_budget_admission_authority=True)
        atomic_write(RUN_ROOT / "actual-usage-summary.json", json_bytes(report))
        self.last_write = time.monotonic()


def run():
    authorization = policy.require_v064_allowed("v064.run")
    host_limits = coordinator_limits()
    if (RUN_ROOT / "execution-started.json").exists():
        raise ValueError("An entered full experiment is not automatically replayed")
    plan_ref = prepare()
    plan = load(plan_ref)
    diagnostics = diagnostic_qualifications()
    dispatch = load(plan["plan"])
    from proworksim import software_benchmark_ref_resident_v064 as runtime
    from proworksim.software_benchmark_episode_v064 import run_episode
    from proworksim.software_benchmark_deepseek_runtime_v064 import DeepSeekRuntime
    api_runtime = DeepSeekRuntime()
    api_identity = api_runtime.initialize_for_run()
    recorder = UsageRecorder(load(reference(policy.MATRIX_FILE)), api_runtime)
    write_new(RUN_ROOT / "execution-started.json", {"version": VERSION, "unix": time.time(),
        "authorization": authorization, "plan": plan_ref, "actual_host_limits": host_limits,
        "diagnostics": diagnostics, "api_identity": api_identity["identity"]})
    stopped = threading.Event()
    handlers = _handle_termination(stopped)
    try:
        result = execute_queue(dispatch["rows"], controls=plan["controls"],
            qualifications=plan["reused_qualifications"], grading=grading_module(), runtime=runtime,
            run_episode=run_episode, api_runtime=api_runtime, stop_event=stopped,
            disk_check=lambda: check_disk_boundary(plan["disk_boundary"]), result_sink=recorder)
        recorder.flush(final=True)
    finally:
        _restore_termination(handlers)
    all_entered = len(result["generation"]) == 6000 and all(value.get("entered") is True for value in result["generation"].values())
    result.update(plan=plan_ref, diagnostics=diagnostics, finished_unix=time.time(),
                  all_6000_generations_entered=all_entered,
                  actual_usage_summary=reference(RUN_ROOT / "actual-usage-summary.json"),
                  actual_usage_records=reference(RUN_ROOT / "actual-usage-records.json"))
    write_new(RUN_ROOT / "run-summary.json", result)
    _progress({"phase": "closed" if result["failure"] is None else "stopped",
        "planned_generation": 6000,
        "finished_generation": sum(value.get("entered") is True for value in result["generation"].values()),
        "unentered_generation": sum(value.get("entered") is False for value in result["generation"].values()) + len(result["unentered_generation"]),
        "finished_code_scores": len(result["scores"]), "delivery_endpoints": len(result["deliveries"]),
        "all_6000_generations_entered": all_entered, "failure": result["failure"],
        "summary": reference(RUN_ROOT / "run-summary.json")})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--execute", action="store_true")
    group.add_argument("--diagnostic", type=int, choices=(1, 2, 3, 4))
    args = parser.parse_args()
    result = prepare() if args.prepare else diagnose(args.diagnostic) if args.diagnostic else run()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

