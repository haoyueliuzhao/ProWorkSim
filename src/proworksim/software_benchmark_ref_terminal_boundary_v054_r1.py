"""Read-only REF generation boundary for the independently revised GPU handoff.

Official CPU scoring and historical unknown accounting are deliberately not a
GPU occupancy test. This module never signals processes or changes those records.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_queue_v054 import claim_path, now
from .software_benchmark_resident_session_v054 import admitted_resident
from .software_benchmark_supervision_v054 import (
    _populated, assert_outer_launcher_exited, assert_quiet,
)

VERSION = "v054-ref-generation-terminal-boundary-r1"
TERMINAL = frozenset({"closed", "technical_unknown"})
KNOWN = TERMINAL | {"pending", "intent", "running"}
WORKER = re.compile(r"proworksim-v054-generation-[a-f0-9]{24}\.service")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def _read_ref(item):
    return json.loads(checked(item).read_text())


def _ref_rows(state, slots):
    expected = slots.get("slots", [])
    actual = state.get("rows", [])
    if len(expected) != 1500 or len(actual) != 1500:
        raise ValueError("The original complete 1500-slot inventory is required")
    # Exact ordered identity rejects duplicate IDs, changed seeds and substitution
    # in any arm; no scoring outcome can influence this boundary.
    if (len({x["slot_id"] for x in expected}) != 1500
            or [x["slot"] for x in actual] != expected):
        raise ValueError("Queue slot identities differ from the original frozen panel")
    rows = [x for x in actual if x["slot"]["arm"] == "REF"]
    if len(rows) != 500:
        raise ValueError("The original complete 500 REF slots are required")
    return rows


def ref_generation_evidence(state, slots):
    """Cheap pure qualification; never opens claims, ledgers, scores or services."""
    rows = _ref_rows(state, slots)
    counts = Counter(row["generation"]["status"] for row in rows)
    if set(counts) - KNOWN:
        raise ValueError("An unrecognized REF generation state cannot authorize handoff")
    return {"version": VERSION, "eligible": set(counts) <= TERMINAL,
            "expected_ref_slots": 500,
            "closed_ref_generations": counts["closed"],
            "technical_unknown_ref_generations": counts["technical_unknown"],
            "generation_counts": dict(sorted(counts.items())),
            "ref_slot_ids_sha256": hashlib.sha256("\n".join(sorted(
                row["slot"]["slot_id"] for row in rows)).encode()).hexdigest(),
            "ref_generation_sha256": _digest([
                {"slot": row["slot"], "generation": row["generation"]} for row in rows]),
            "score_completion_required": False, "selection_used_scores": False,
            "old_unknowns_preserved": True, "actual_cost_ledger_mutations": 0,
            "model_token_mutations": 0, "generation_replays": 0}


def _worker_quiet(unit):
    if not isinstance(unit, str) or not WORKER.fullmatch(unit):
        raise ValueError("Unknown REF generation worker unit")
    result = subprocess.run(["systemctl", "--user", "show", unit,
        "--property=Id,LoadState,ActiveState,MainPID,ControlGroup,InvocationID"],
        capture_output=True, text=True, timeout=10, check=True)
    status = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if (status.get("Id") != unit or status.get("ActiveState") not in {"inactive", "failed"}
            or int(status.get("MainPID", "-1")) != 0):
        raise RuntimeError("A REF generation worker has not exited: " + unit)
    group = status.get("ControlGroup", "")
    if group and (not group.endswith("/" + unit) or _populated(group)):
        raise RuntimeError("A REF generation worker cgroup is still occupied: " + unit)
    return {"unit": unit, "active_state": status["ActiveState"], "main_pid": 0,
            "cgroup": group, "populated": False,
            "unit_garbage_collected": status.get("LoadState") == "not-found"}


def _idle_ref(observed):
    if observed is None:
        raise RuntimeError("REF resident is missing at the terminal boundary")
    declaration, status = observed["declaration"], observed["status"]
    if (declaration.get("mode") != "REF" or declaration.get("gpu_index") != 7
            or observed.get("session_capacity") != 1
            or observed.get("active_claims") != []
            or status.get("active_claim") is not None
            or status.get("inflight") != 0 or status.get("poisoned") is not False):
        raise RuntimeError("The exact GPU7 REF resident is not idle and healthy")
    return {"declaration": observed["declaration_reference"],
            "ready": observed["ready_reference"], "status": status,
            "unit_state": observed["unit_state"],
            "host_process": observed["ready"]["host_process"],
            "gpu_index": 7, "gpu_uuid": declaration["gpu_uuid"]}


def _preclaim_failure(slot, generation, job_refs):
    """Missing claims require explicit pre-entry results and exited job receipts."""
    if generation["status"] != "technical_unknown" or generation.get("claimed") is True:
        raise ValueError("A claimed or successful REF generation lost its claim")
    proofs = []
    for job_ref in job_refs.values():
        attempts = [x for x in generation.get("attempts", []) if x.get("job") == job_ref]
        if len(attempts) != 1:
            raise ValueError("Missing claim has no unique retained preclaim attempt")
        attempt = attempts[0]
        completion, result = _read_ref(attempt["completion"]), _read_ref(attempt["result"])
        if (completion.get("job") != job_ref or completion.get("status") != "exited"
                or type(completion.get("returncode")) is not int
                or result.get("slot_id") != slot["slot_id"]
                or result.get("slot_claimed") is not False or result.get("entered") is not False
                or result.get("model_calls") != 0):
            raise ValueError("Missing REF claim is not proven to be an unentered failure")
        proofs.append({"completion": attempt["completion"], "result": attempt["result"]})
    return {"claim_never_created": True, "no_generation_entered": True, "attempts": proofs}


def collect_runtime_boundary(state, slots, observed_ref, *, slots_reference,
                             queue_state_path=None):
    """Inspect exact old generation owners only after all REF slots are terminal.

    The caller owns conversion serialization and writes the returned evidence to
    a new path. CPU scoring may continue while this observation takes place.
    """
    evidence = ref_generation_evidence(state, slots)
    if not evidence["eligible"]:
        raise ValueError("REF generation is not terminal; runtime inventory was not opened")
    if _read_ref(slots_reference) != slots:
        raise ValueError("Terminal boundary is not bound to the supplied frozen slots")
    initial_resident = _idle_ref(observed_ref)
    inventories, workers, scopes = [], {}, []
    for row in _ref_rows(state, slots):
        slot, generation = row["slot"], row["generation"]
        path = claim_path(slot["slot_id"])
        jobs = [item["job"] for item in generation.get("attempts", []) if "job" in item]
        if generation.get("job") is not None:
            jobs.append(generation["job"])
        if not jobs:
            raise ValueError("REF terminal row has no generation worker provenance")
        job_refs = {item["path"]: item for item in jobs}
        job_units = set()
        for job_ref in job_refs.values():
            job = _read_ref(job_ref)
            if job.get("kind") != "generation":
                raise ValueError("CPU scoring cannot serve as generation-worker provenance")
            unit = job["unit"]
            job_units.add(unit)
            if unit not in workers:
                workers[unit] = _worker_quiet(unit)
        if generation.get("unit") not in job_units:
            raise ValueError("REF terminal worker differs from its retained job")
        if not path.exists():
            failure = _preclaim_failure(slot, generation, job_refs)
            if path.with_name("scope-registry.json").exists():
                raise ValueError("Missing REF claim nevertheless has retained episode scopes")
            inventories.append({"slot_id": slot["slot_id"], "claim": None,
                                "scope_registry": None, "jobs": list(job_refs.values()),
                                "preclaim_failure": failure})
            continue
        claim_ref = reference(path)
        claim = _read_ref(claim_ref)
        claim_id = claim.get("claim_id", "")
        if (claim.get("slot") != slot or claim.get("slots") != slots_reference
                or not re.fullmatch(r"[a-f0-9]{32}", claim_id)):
            raise ValueError("REF retained claim differs from the frozen slot")
        registry = path.with_name("scope-registry.json")
        registry_ref = reference(registry)
        registered = _read_ref(registry_ref)
        if not isinstance(registered, list) or not registered:
            raise ValueError("REF claim has no trustworthy retained scope inventory")
        if len({(x.get("manager", "user"), x["unit"]) for x in registered}) != len(registered):
            raise ValueError("REF retained scope inventory contains duplicates")
        for scope in registered:
            if (scope.get("claim_id") != claim_id
                    or not scope["unit"].startswith("proworksim-v054-episode-" + claim_id + "-")
                    or scope.get("manager", "user") not in {"user", "system"}
                    or not scope["cgroup"].endswith("/" + scope["unit"])):
                raise ValueError("A retained REF scope crossed its exact claim")
            quiet = assert_quiet(scope)
            assert_outer_launcher_exited(scope)
            scopes.append({**quiet, "outer_launcher_exited": True})
        # The dedicated claim slice includes descendants that may have appeared
        # immediately before a failed scope-registry write.
        for parent in (Path("/sys/fs/cgroup"), Path("/sys/fs/cgroup/system.slice")):
            events = parent / ("proworksimv054ep" + claim_id + ".slice") / "cgroup.events"
            if events.exists() and dict(line.split() for line in events.read_text().splitlines()).get("populated") != "0":
                raise RuntimeError("A REF claim resource slice is still populated")
        if reference(path) != claim_ref or reference(registry) != registry_ref:
            raise ValueError("REF claim/scope inventory changed during boundary observation")
        inventories.append({"slot_id": slot["slot_id"], "claim": claim_ref,
                            "scope_registry": registry_ref, "jobs": list(job_refs.values())})
    # Reuse the resident's existing process/GPU/InvocationID checks. No generation
    # method or lifecycle operation is called; status is the only owner request.
    final_observed = admitted_resident(observed_ref["declaration_reference"])
    final_resident = _idle_ref(final_observed)
    for key in ("declaration", "ready", "host_process", "gpu_index", "gpu_uuid", "unit_state"):
        if initial_resident[key] != final_resident[key]:
            raise ValueError("REF resident identity changed during boundary observation")
    if queue_state_path is not None:
        fresh = json.loads(Path(queue_state_path).read_text())
        if ref_generation_evidence(fresh, slots) != evidence:
            raise ValueError("REF generation changed during its terminal boundary observation")
    return {"version": VERSION, "observed_utc": now(), "completion": evidence,
            "generation_evidence": evidence, "registration": observed_ref["registration"],
            "slots": slots_reference, "resident": final_resident,
            "all_500_ref_generations_terminal": True, "resident_session_idle": True,
            "all_ref_generation_quiescent": True, "resident_inflight": 0,
            "all_ref_generation_workers_quiet": True, "all_ref_registered_scopes_quiet": True,
            "claim_inventories": inventories, "generation_workers": list(workers.values()),
            "registered_scopes": scopes, "CPU_scoring_excluded_from_GPU_occupancy": True,
            "all_ref_scores_claimed_complete": False, "processes_signalled": 0,
            "model_calls": 0, "queue_writes": 0, "ledger_writes": 0,
            "source": reference(__file__)}
