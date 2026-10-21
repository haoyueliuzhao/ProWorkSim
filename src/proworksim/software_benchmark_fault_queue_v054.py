"""Host-only deferred-fault overlay over the unchanged r11 scientific queue.

The original workers, claims, candidate rules, source seals, resource limits,
model residents and official scorer remain authoritative. Only scheduling after
a task-local exception changes. No entered generation or scoring attempt is
replayed by this coordinator.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import time

from . import software_benchmark_queue_v054 as base
from .software_benchmark_candidates_v054 import checked, reference, write_new

VERSION = "v054-deferred-fault-queue-r1"
BINDINGS_SHA256 = "43fb7dde14a7c7abf3a0dc97de8b0de119f41d4f4199f8482793b9b6c24bc3de"
TERMINAL = "primary_inventory_finished_with_deferred_exceptions"
GENERATION_TERMINAL = {"closed", "technical_unknown"}
SCORING_TERMINAL = {"official_report", "technical_unknown"}
LOCAL_FAILURES = {"generation_did_not_close", "generation_evidence_invalid",
                  "official_scoring_unknown", "scoring_evidence_invalid",
                  "worker_missing_without_completion", "ambiguous_unit_launch",
                  "model_accounting_or_execution_unknown"}
OVERLAY_FILES = ("src/proworksim/software_benchmark_fault_queue_v054.py",
                 "src/proworksim/software_benchmark_deferred_pool_v054.py",
                 "tools/run_deferred_fault_queue_v054.py")
DEFERRED_SCORING = {"enabled": True, "phase": "after_primary_inventory",
                    "maximum_additional_attempts_per_endpoint": 1,
                    "resources": "identical_to_original_request",
                    "model_retry": False, "patch_selection": False}


class SharedIntegrityError(RuntimeError):
    """An unscoped trusted identity or accounting failure is not a task result."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def create_policy(bindings_path, output, previous_controller_unit):
    bindings_ref = reference(bindings_path)
    if bindings_ref["sha256"] != BINDINGS_SHA256:
        raise ValueError("Overlay must bind the unchanged original r7 bindings")
    bindings = base.load_ref(bindings_ref)
    base.validate_frozen(bindings, initial=True)
    if not re.fullmatch(r"proworksim-v054-formal-queue-r[0-9]+\.service", previous_controller_unit):
        raise ValueError("Unknown prior controller unit")
    files = [reference(base.ROOT / path) for path in OVERLAY_FILES]
    frozen = {row["reference"]["path"] for row in bindings["frozen_files"]}
    if frozen.intersection(row["path"] for row in files):
        raise ValueError("Overlay must not replace any frozen scientific source")
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    return write_new(output, {"version": VERSION, "created_utc": base.now(),
        "original_bindings": bindings_ref, "queue_root": str(base.QUEUE),
        "previous_controller_unit": previous_controller_unit,
        "exception_root": str(base.QUEUE / "deferred-fault-overlay-r1"),
        "files": [{"reference": row, "stat": base.stat_id(row["path"])} for row in files],
        "task_local_failures_deferred": sorted(LOCAL_FAILURES),
        "immutable_integrity_failure_stops_dispatch": True,
        "unscoped_controller_failure_stops_dispatch": True,
        "automatic_generation_retry": False, "primary_score_retry": False,
        "model_reload": False, "resident_repair": False,
        "shared_accounting_fault_quarantines_resident": True,
        "adopt_running_original_workers": True,
        "deferred_scoring": DEFERRED_SCORING,
        "completion_status": TERMINAL, "completion_is_complete_benchmark_score": False})


def validate_policy(policy_ref, *, initial=False):
    policy = base.load_ref(policy_ref)
    if (policy.get("version") != VERSION
            or policy["original_bindings"]["sha256"] != BINDINGS_SHA256
            or policy["queue_root"] != str(base.QUEUE)
            or policy["exception_root"] != str(base.QUEUE / "deferred-fault-overlay-r1")
            or policy.get("task_local_failures_deferred") != sorted(LOCAL_FAILURES)
            or policy.get("immutable_integrity_failure_stops_dispatch") is not True
            or policy.get("unscoped_controller_failure_stops_dispatch") is not True
            or policy.get("shared_accounting_fault_quarantines_resident") is not True
            or policy.get("adopt_running_original_workers") is not True
            or any(policy.get(key) is not False for key in
                   ("automatic_generation_retry", "primary_score_retry", "model_reload", "resident_repair"))
            or policy.get("deferred_scoring") != DEFERRED_SCORING
            or policy.get("completion_status") != TERMINAL
            or policy.get("completion_is_complete_benchmark_score") is not False):
        raise ValueError("Unsupported deferred-fault policy")
    files = policy["files"]
    if {item["reference"]["path"] for item in files} != {str(base.ROOT / x) for x in OVERLAY_FILES}:
        raise ValueError("Overlay source set changed")
    for item in files:
        if initial:
            checked(item["reference"])
        if base.stat_id(item["reference"]["path"]) != item["stat"]:
            raise ValueError("Deferred overlay source changed")
    return policy


def primary_terminal(rows):
    return (len(rows) == 1500 and all(
        row["generation"]["status"] in GENERATION_TERMINAL
        and all(score["status"] in SCORING_TERMINAL for score in row["scores"].values())
        and (row["generation"]["status"] != "closed" or "code" in row["scores"])
        for row in rows))


class ResilientCoordinator(base.Coordinator):
    """Keep original worker semantics; defer only explicit task-local faults."""

    def __init__(self, policy_ref, *, system=None, adopting=False):
        self.policy_ref = policy_ref
        self.policy = validate_policy(policy_ref, initial=True)
        self._context = None
        self.exception_root = Path(self.policy["exception_root"])
        # This invokes the original full SHA/stat check and original durable
        # controller lock. The original bindings and state identity stay exact.
        super().__init__(self.policy["original_bindings"], system=system)
        self.validate_state()
        adopted = self.state.get("deferred_fault_queue")
        if not adopting and (not adopted or adopted.get("policy") != policy_ref):
            self.lease.close()
            raise ValueError("Explicit stopped-controller adoption is required")
        if adopted and adopted.get("policy") != policy_ref:
            self.lease.close()
            raise ValueError("Another immutable overlay is already adopted")

    def validate_state(self):
        rows = self.state["rows"]
        if ([row["slot"] for row in rows] != self.slots["slots"]
                or self.state["bindings"] != self.bindings_ref):
            raise SharedIntegrityError("Queue state no longer matches all 1500 frozen slots")
        for row in rows:
            if row["generation"]["status"] not in {"pending", *base.ACTIVE, *GENERATION_TERMINAL}:
                raise SharedIntegrityError("Unknown generation lifecycle schema")
            if any(score["status"] not in {"pending", *base.ACTIVE, *SCORING_TERMINAL}
                   for score in row["scores"].values()):
                raise SharedIntegrityError("Unknown scoring lifecycle schema")

    def adopt(self):
        """One-off adoption, with old workers left running and no new claim."""
        with base.lock_file(self.exception_root / "adoption.lock"):
            if self.state.get("deferred_fault_queue"):
                raise ValueError("This overlay was already adopted; use run, never adopt twice")
            if self.system.active(self.policy["previous_controller_unit"]):
                raise ValueError("Prior controller must be stopped; independent workers may remain active")
            base.validate_frozen(self.bindings)
            active = []
            for row in self.state["rows"]:
                for endpoint, record in [(None, row["generation"]), *row["scores"].items()]:
                    if record["status"] not in base.ACTIVE:
                        continue
                    job = base.load_ref(record["job"])
                    directory = Path(record["worker_directory"])
                    expected = "generation" if endpoint is None else "score"
                    if (job.get("bindings") != self.bindings_ref or job.get("kind") != expected
                            or job.get("unit") != record["unit"]
                            or Path(record["job"]["path"]) != directory / "job.json"
                            or not directory.resolve().is_relative_to(self.root)
                            or not re.fullmatch("proworksim-v054-" + expected + r"-[a-f0-9]{24}\.service", record["unit"])):
                        raise SharedIntegrityError("Active worker is not an original immutable job")
                    active.append({"slot_id": row["slot"]["slot_id"], "endpoint": endpoint,
                                   "job": record["job"], "unit": record["unit"],
                                   "observed_active": self.system.active(record["unit"]),
                                   "intent_never_relaunched": True})
            prior = write_new(self.exception_root / "state-before-adoption.json", self.state)
            adoption = write_new(self.exception_root / "adoption.json", {
                "version": VERSION, "utc": base.now(), "policy": self.policy_ref,
                "original_bindings": self.bindings_ref, "state_before": prior,
                "prior_controller_stopped": True, "controller_lock_owned": True,
                "inherited_original_workers": active, "model_requests": 0,
                "model_reloads": 0, "formal_claims": 0, "old_fault_history_preserved": True})
            self.state["deferred_fault_queue"] = {"version": VERSION, "policy": self.policy_ref,
                                                   "adoption": adoption}
            self.state.setdefault("operator_policy_adoptions", []).append(adoption)
            self.state.setdefault("deferred_exceptions", [])
            self.state.setdefault("quarantined_residents", {})
            for row in self.state["rows"]:
                if row["generation"]["status"] == "technical_unknown":
                    self.defer(row, None, "inherited_generation_unknown", {"historical": True})
                for endpoint, score in row["scores"].items():
                    if score["status"] == "technical_unknown":
                        self.defer(row, endpoint, "inherited_scoring_unknown", {"historical": True})
            self.state["status"] = "running"
            self.save()
            return adoption

    @contextmanager
    def context(self, row, endpoint=None):
        previous, self._context = self._context, (row, endpoint)
        try:
            yield
        finally:
            self._context = previous

    def defer(self, row, endpoint, kind, detail):
        record = row["generation"] if endpoint is None else row["scores"][endpoint]
        key = digest({"slot_id": row["slot"]["slot_id"], "endpoint": endpoint,
                      "kind": kind, "job": record.get("job")})
        events = self.state.setdefault("deferred_exceptions", [])
        known = next((item for item in events if item.get("exception_id") == key), None)
        if known:
            return known["evidence"]
        value = {"version": VERSION, "exception_id": key, "utc": base.now(),
                 "policy": self.policy_ref, "original_bindings": self.bindings_ref,
                 "slot_id": row["slot"]["slot_id"], "endpoint": endpoint, "kind": kind,
                 "detail": detail, "row_snapshot": deepcopy(row), "no_model_retry": True,
                 "unknown_usage_is_not_zero": True, "candidate_selection_unchanged": True}
        path = self.exception_root / "exceptions" / (key + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            old = base.read(path)
            if any(old.get(name) != value[name] for name in
                   ("exception_id", "policy", "original_bindings", "slot_id", "endpoint", "kind")):
                raise SharedIntegrityError("Conflicting durable deferred exception")
            evidence = reference(path)
        else:
            evidence = write_new(path, value)
        events.append({"exception_id": key, "slot_id": value["slot_id"], "endpoint": endpoint,
                       "kind": kind, "status": "deferred", "evidence": evidence,
                       "resolved": None, "no_model_retry": True})
        return evidence

    def _locate(self, detail):
        if self._context is not None:
            return self._context
        if isinstance(detail, dict):
            for row in self.state["rows"]:
                if detail.get("slot_id") == row["slot"]["slot_id"]:
                    return row, detail.get("endpoint")
                for endpoint, record in [(None, row["generation"]), *row["scores"].items()]:
                    if detail.get("unit") and detail["unit"] == record.get("unit"):
                        return row, endpoint
        return None

    def pause(self, kind, detail):
        target = self._locate(detail)
        if kind not in LOCAL_FAILURES or target is None:
            return super().pause(kind, detail)
        row, endpoint = target
        record = row["generation"] if endpoint is None else row["scores"][endpoint]
        # An uncertain launch is observed, never repeated. If the registered
        # service actually exists, keep reconciling its original durable intent.
        if kind == "ambiguous_unit_launch" and self.system.active(record["unit"]):
            record["status"] = "running"
        else:
            record["status"] = "technical_unknown"
        evidence = self.defer(row, endpoint, kind, detail)
        if kind == "model_accounting_or_execution_unknown":
            resident_id = row["generation"].get("resident_id")
            if not resident_id:
                return super().pause("unscoped_accounting_integrity_failure", detail)
            self.state.setdefault("quarantined_residents", {}).setdefault(resident_id, {
                "kind": kind, "evidence": evidence, "utc": base.now(),
                "automatic_restart": False, "other_residents_cancelled": False})
        self.state.setdefault("faults", []).append({"utc": base.now(), "kind": kind,
            "detail": detail, "automatic_retry": False, "deferred": True, "evidence": evidence})
        self.save()

    def complete_generation(self, row, completion):
        with self.context(row):
            return super().complete_generation(row, completion)

    def complete_score(self, row, endpoint, completion):
        with self.context(row, endpoint):
            return super().complete_score(row, endpoint, completion)

    def reconcile(self):
        # A corrupted global claim is a shared identity fault, not a failed
        # patch. Keep it outside the original catch for task-local result IO.
        for row in self.state["rows"]:
            if row["generation"]["status"] not in base.ACTIVE:
                continue
            path = base.claim_path(row["slot"]["slot_id"])
            if path.exists():
                try:
                    value = base.read(path)
                    if (value["slot"] != row["slot"] or value["slots"] != self.bindings["slots"]
                            or value["authorization"] != self.bindings["authorization"]):
                        raise ValueError("Claim mismatch")
                except (OSError, ValueError, KeyError) as error:
                    raise SharedIntegrityError("Global claim identity differs: " + str(error)) from error
        super().reconcile()

    def dispatch_generation(self):
        if self.state["status"] != "running":
            return
        from .software_benchmark_deferred_pool_v054 import healthy_residents
        from .software_benchmark_prewarm_v054 import preparation_state, prewarm_health
        health = prewarm_health(self.bindings["prewarm_policy"])
        if health["status"] == "failed":
            raise SharedIntegrityError("CPU prewarm shared lifecycle failed: " + json.dumps(health))
        observed_pool = healthy_residents(self.bindings["resident_pool_policy"])
        quarantined = self.state.get("quarantined_residents", {})
        residents = {key: item for key, item in observed_pool["available"].items() if key not in quarantined}
        # Small bounded current health view; raw immutable registrations stay
        # pinned in each job and all persistent task exceptions stay above.
        self.state["resident_health"] = {"utc": base.now(), "status": "ready" if residents else "waiting",
            "healthy": sorted(observed_pool["healthy"]), "available": sorted(residents),
            "deferred": observed_pool["deferred"], "quarantined": sorted(quarantined)}
        qualifications = {}

        def is_prepared(row):
            instance = row["slot"]["instance_id"]
            if instance not in qualifications:
                qualifications[instance] = preparation_state(instance,
                    mapping_reference=self.public_entries[instance]["baseline_mapping"],
                    cache_root=base.ROOT / "runs/software-benchmark-v054/native-lazy-cache")
            proof = qualifications[instance]
            if proof["status"] == "failed":
                raise SharedIntegrityError("Fixed CPU preparation failed: " + instance + " " + json.dumps(proof))
            return proof["status"] == "qualified"

        while self.state["status"] == "running":
            selected = base.select_pool_slot(self.state["rows"], residents,
                maximum_active=self.plan["maximum_active_generation_episodes"], is_prepared=is_prepared)
            if selected is None:
                self.state["waiting"] = {"reason": "no_healthy_prepared_resident_session",
                                        "slot_claimed": False, "observed_residents": sorted(residents)}
                return
            row, resident_id, observed = selected
            slot, generation = row["slot"], row["generation"]
            declaration = observed["declaration"]
            gpu_index = declaration["gpu_index"]
            if base.claim_path(slot["slot_id"]).parent.exists():
                raise SharedIntegrityError("Pending slot already has a claim directory; never replay")
            arm = "REF" if slot["arm"] == "REF" else "MATCH"
            card = {"index": gpu_index, "uuid": declaration["gpu_uuid"],
                    "admission": "immutable_pool_registration_and_live_resident"}
            from .software_benchmark_service_factory_v054 import build_service
            from .software_benchmark_slot_factory_v054 import build_slot_config
            base.validate_frozen(self.bindings)
            attempt = len(generation["attempts"]) + 1
            root = self.root / "slots" / str(slot["slot_index"]) / ("preclaim-" + str(attempt))
            root.mkdir(parents=True, exist_ok=False)
            service_ref = build_service(arm=slot["arm"], capacity_reference=self.bindings["capacities"][arm],
                card=card, directory=root / "service", resident_reference=observed["declaration_reference"],
                registration_reference=observed["registration"],
                pool_policy_reference=self.bindings["resident_pool_policy"])
            config = build_slot_config(slot_id=slot["slot_id"], condition_reference=self.bindings["conditions"][slot["arm"]],
                model_service=base.load_ref(service_ref), registry_reference=self.bindings["registry"],
                scorer_manifest_reference=self.bindings["scorer_manifest"], output=root / "config.json",
                authorization=self.bindings["authorization"], prewarm_policy_reference=self.bindings["prewarm_policy"])
            generation.update(config=config, service=service_ref, episode_output=str(root / "episode"), claimed=False,
                slot_id=slot["slot_id"], slot_index=slot["slot_index"], physical_gpu=gpu_index,
                resident_id=resident_id, resident_registration=observed["registration"],
                resident_pool_policy=self.bindings["resident_pool_policy"])
            self.state.pop("waiting", None)
            with self.context(row):
                self.start_job(generation, kind="generation", directory=root / "worker",
                    argv=[str(base.HOST_PYTHON), str(base.ROOT / "tools/run_benchmark_episode_v054.py"),
                          "--config", config["path"], "--output", str(root / "episode")])

    def finish_primary(self):
        if not primary_terminal(self.state["rows"]):
            raise ValueError("Primary inventory still has unattempted or active work")
        self.state["status"] = TERMINAL
        self.save()
        path = self.exception_root / "primary-completion.json"
        if path.exists():
            return reference(path)
        snapshot = write_new(self.exception_root / "primary-state.json", self.state)
        return write_new(path, {"version": "v054-deferred-primary-completion-v1", "utc": base.now(),
            "status": TERMINAL, "queue_state_snapshot": snapshot, "bindings": self.bindings_ref,
            "overlay_policy": self.policy_ref, "planned_slots": 1500,
            "active_generation": 0, "active_graders": 0,
            "generation_terminal_statuses": sorted(GENERATION_TERMINAL),
            "score_terminal_statuses": sorted(SCORING_TERMINAL),
            "deferred_exceptions": self.state.get("deferred_exceptions", []),
            "primary_only": True, "no_generation_retry": True,
            "complete_benchmark_point_estimate": False})

    def tick(self):
        try:
            source_valid = True
            try:
                base.validate_frozen(self.bindings)
                validate_policy(self.policy_ref)
                self.validate_state()
            except (OSError, ValueError, KeyError, SharedIntegrityError) as error:
                source_valid = False
                if not self.state.get("source_changed"):
                    self.state["source_changed"] = True
                    super().pause("frozen_source_or_overlay_integrity_changed", str(error))
            self.reconcile()
            if source_valid:
                self.dispatch_scores()
                self.dispatch_generation()
            if self.state["status"] == "running" and primary_terminal(self.state["rows"]):
                marker = self.finish_primary()
                self.state["primary_completion"] = marker
            self.save()
        except Exception as error:
            # Unknown scope/schema/policy failures retain the old hard stop.
            super().pause("controller_fault", {"type": type(error).__name__, "message": str(error)})

    def run(self):
        while True:
            self.tick()
            if self.state["status"] == TERMINAL:
                return 0
            active = self.state["active_generation"] + self.state["active_graders"]
            pending = any(s["status"] == "pending" for row in self.state["rows"] for s in row["scores"].values())
            if self.state["status"] != "running" and not active and (not pending or self.state.get("source_changed")):
                return 1
            time.sleep(self.plan["resource_poll_seconds"])


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--bindings", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.add_argument("--previous-controller-unit", required=True)
    for name in ("adopt", "run"):
        command = commands.add_parser(name)
        command.add_argument("--policy", type=Path, required=True)
        command.add_argument("--policy-sha256", required=True)
    args = parser.parse_args(argv)
    if args.command == "freeze":
        print(json.dumps(create_policy(args.bindings, args.output, args.previous_controller_unit)))
        return 0
    policy_ref = reference(args.policy)
    if policy_ref["sha256"] != args.policy_sha256:
        raise ValueError("Overlay policy identity changed")
    coordinator = ResilientCoordinator(policy_ref, adopting=args.command == "adopt")
    try:
        if args.command == "adopt":
            print(json.dumps(coordinator.adopt()))
            return 0
        return coordinator.run()
    finally:
        coordinator.lease.close()


if __name__ == "__main__":
    raise SystemExit(main())
