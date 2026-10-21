"""Explicit, stopped-controller migration of proven zero-execution preclaim faults.

This utility neither starts workers nor clears a claim. Existing closed results
keep their original configuration and grading references. It is intentionally
separate from the frozen queue's automatic resource-wait policy.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

VERSION = "v054-explicit-preclaim-recovery-v1"
FIXED_SHA = "55899d0b83a5bab1082bccb50496fb6c1d7111ecb951fc4d61c222be19d88676"
UNCHANGED_BINDINGS = ("slots", "authorization", "plan", "registry", "scorer_manifest",
                      "capacities", "capacity_admission")


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def reference(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def read_ref(item):
    if reference(item["path"]) != item:
        raise ValueError("Immutable evidence changed: " + item["path"])
    return json.loads(Path(item["path"]).read_bytes())


def write_new(path, value):
    raw = value if isinstance(value, bytes) else encoded(value)
    with Path(path).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return reference(path)


def stopped_unit(unit):
    if not re.fullmatch(r"proworksim-v054-[a-zA-Z0-9_.-]+\.service", unit):
        raise ValueError("Expected a named v054 unit")
    command = ["systemctl", "--user", "show", unit, "--property=LoadState",
               "--property=ActiveState", "--property=SubState", "--property=MainPID"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if (fields.get("ActiveState") not in {"inactive", "failed"}
            or fields.get("MainPID", "0") != "0"
            or result.returncode not in {0, 1}):
        raise ValueError("Unit is not proven stopped: " + unit + " " + str(fields))
    return {"unit": unit, "properties": fields, "returncode": result.returncode}


def claim_directory(repository, slot_id):
    return (repository / "runs/software-benchmark-v054/episode-claims"
            / hashlib.sha256(slot_id.encode()).hexdigest())


def verify_transition(old_bindings, new_bindings, previous_condition_root, previous_source, *, allow_residency_revision=False):
    for key in UNCHANGED_BINDINGS:
        if old_bindings[key] != new_bindings[key]:
            raise ValueError("Recovery cannot silently change " + key)
    if (new_bindings.get("execution_authorized") is not True
            or new_bindings["slots"]["sha256"] != FIXED_SHA):
        raise ValueError("The original authorized panel is required")
    old_source_ref = reference(previous_source)
    expected = old_bindings["source_manifest"]
    if any(old_source_ref[key] != expected[key] for key in ("sha256", "bytes")):
        raise ValueError("Previous source snapshot does not match the actual old binding")
    old_source = json.loads(Path(previous_source).read_bytes())
    new_source = read_ref(new_bindings["source_manifest"])
    conditions = {}
    for arm in ("REF", "MATCH", "PROJECT"):
        snapshot = Path(previous_condition_root) / ("v054-condition-" + arm + ".json")
        previous_ref = reference(snapshot)
        if any(previous_ref[key] != old_bindings["conditions"][arm][key] for key in ("sha256", "bytes")):
            raise ValueError("Previous condition snapshot differs: " + arm)
        before, after = json.loads(snapshot.read_bytes()), read_ref(new_bindings["conditions"][arm])
        residency_change = None
        if allow_residency_revision:
            prior_protocol, new_protocol = before.pop("residency_protocol", None), after.pop("residency_protocol", None)
            if not new_protocol:
                raise ValueError("Explicit resident revision must bind a residency_protocol")
            residency_change = {"before": prior_protocol, "after": new_protocol,
                                "runtime_lifecycle_changed": prior_protocol != new_protocol,
                                "previous_results_not_pooled_as_same_runtime_revision": True}
        if (before.pop("source_manifest") != old_bindings["source_manifest"]
                or after.pop("source_manifest") != new_bindings["source_manifest"] or before != after):
            raise ValueError("Only the explicit source revision may change in condition " + arm)
        conditions[arm] = {"previous_snapshot": previous_ref,
                           "new_condition": new_bindings["conditions"][arm],
                           "non_source_non_residency_condition_fields_equal": True,
                           "explicit_residency_protocol_revision": residency_change}
    old_files = {x["path"]: x for x in old_source["files"]}
    new_files = {x["path"]: x for x in new_source["files"]}
    delta = [{"path": path, "before": old_files.get(path), "after": new_files.get(path)}
             for path in sorted(set(old_files) | set(new_files)) if old_files.get(path) != new_files.get(path)]
    return {"previous_source_snapshot": old_source_ref, "conditions": conditions, "source_delta": delta}


def verify_state(state, *, repository, slot_ids, unit_check=stopped_unit):
    """Read only proofs; never reinterpret a claimed or entered episode as unused."""
    if state["status"] != "paused_technical_unknown" or state["planned_slots"] != 1500:
        raise ValueError("Expected the stopped, complete-panel paused queue")
    rows = state["rows"]
    if len(rows) != 1500 or len({x["slot"]["slot_id"] for x in rows}) != 1500:
        raise ValueError("The full unique panel must remain present")
    selected = set(slot_ids)
    unknown = {x["slot"]["slot_id"] for x in rows if x["generation"]["status"] == "technical_unknown"}
    if not selected or selected != unknown:
        raise ValueError("Every technical unknown must be explicitly addressed, without selecting by score")
    proofs = []
    for row in rows:
        slot_id, generation = row["slot"]["slot_id"], row["generation"]
        status = generation["status"]
        if status not in {"pending", "closed", "technical_unknown"}:
            raise ValueError("A generation worker is still in flight: " + slot_id)
        if any(s["status"] != "official_report" for s in row["scores"].values()):
            raise ValueError("An existing official endpoint has not closed: " + slot_id)
        claim = claim_directory(repository, slot_id)
        if status == "closed":
            if not (claim / "claim.json").is_file() or not row["scores"] or row["delivery"]["status"] == "pending":
                raise ValueError("Closed result lacks its original claim or scoring closure")
            continue
        if claim.exists():
            raise ValueError("An allegedly unused slot has a global claim directory: " + slot_id)
        if row["scores"]:
            raise ValueError("An unused slot already has official scoring state")
        if status == "pending":
            continue
        result = read_ref(generation["result"])
        if (result.get("slot_id") != slot_id or result.get("status") != "preparation_not_ready"
                or result.get("slot_claimed") is not False or result.get("entered") is not False
                or type(result.get("model_calls")) is not int or result["model_calls"] != 0
                or type(result.get("GPU_loads")) is not int or result["GPU_loads"] != 0
                or generation.get("claimed") is not False):
            raise ValueError("Not an exact zero-execution preparation fault: " + slot_id)
        attempts = generation["attempts"]
        if not attempts or attempts[-1]["result"] != generation["result"]:
            raise ValueError("Failed preparation history is missing")
        completion = read_ref(attempts[-1]["completion"])
        if completion.get("returncode") != 75 or completion.get("job") != generation["job"]:
            raise ValueError("Original preclaim worker did not terminate in the expected state")
        config = read_ref(generation["config"])
        for key in ("model_ready", "model_identity"):
            if Path(config[key]).exists():
                raise ValueError("Model readiness/identity exists despite zero-load assertion")
        worker = unit_check(generation["unit"])
        proofs.append({"slot_id": slot_id, "result": generation["result"],
                       "completion": attempts[-1]["completion"], "worker_stopped": worker,
                       "global_claim_directory_absent": True, "previous_generation": copy.deepcopy(generation)})
    return proofs


def resumed_state(state, new_bindings_ref, selected_slots, transition_ref):
    """Preserve old attempts/faults/results; only unused slots can be dispatched."""
    result = copy.deepcopy(state)
    old_bindings = state["bindings"]
    for row in result["rows"]:
        generation = row["generation"]
        if generation["status"] == "closed":
            row.setdefault("original_execution_bindings", old_bindings)
            continue
        if row["slot"]["slot_id"] in selected_slots:
            row["generation"] = {"status": "pending", "claimed": False,
                                 "attempts": generation["attempts"], "explicit_preclaim_recovery": transition_ref}
        row["next_execution_bindings"] = new_bindings_ref
    result["bindings"] = new_bindings_ref
    result["status"] = "running"
    result.pop("source_changed", None)
    result.pop("waiting", None)
    result.setdefault("explicit_recoveries", []).append(transition_ref)
    result["updated_utc"] = datetime.now(timezone.utc).isoformat()
    result["generation_counts"] = {kind: sum(x["generation"]["status"] == kind for x in result["rows"])
                                   for kind in ("pending", "closed", "technical_unknown")}
    result["active_generation"] = result["active_graders"] = 0
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("repository", "queue", "new-bindings", "previous-conditions", "previous-source", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--controller-unit", required=True)
    parser.add_argument("--slot-id", action="append", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-residency-protocol-revision", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    queue = args.queue.resolve()
    with (queue / "controller.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        controller = stopped_unit(args.controller_unit)
        state_ref = reference(queue / "state.json")
        state = read_ref(state_ref)
        new_ref = reference(args.new_bindings)
        old_bindings, new_bindings = read_ref(state["bindings"]), read_ref(new_ref)
        transition = verify_transition(old_bindings, new_bindings, args.previous_conditions, args.previous_source,
                                       allow_residency_revision=args.allow_residency_protocol_revision)
        proofs = verify_state(state, repository=args.repository.resolve(), slot_ids=args.slot_id)
        transition.update(version=VERSION, created_utc=datetime.now(timezone.utc).isoformat(),
                          reason=args.reason, previous_state=state_ref, previous_bindings=state["bindings"],
                          new_bindings=new_ref, controller_stopped=controller, zero_execution_faults=proofs,
                          original_claims_deleted=0, previously_entered_episodes_replayed=0,
                          automatic_start=False, model_calls=0)
        if not args.apply:
            print(json.dumps({"status": "eligible_for_explicit_preclaim_recovery", "slots": args.slot_id,
                              "source_delta_count": len(transition["source_delta"]), "state_modified": False}))
            return 0
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=False)
        old_snapshot = write_new(output / "state-before.json", Path(state_ref["path"]).read_bytes())
        transition["previous_state_snapshot"] = old_snapshot
        transition_ref = write_new(output / "transition.json", transition)
        new_state = resumed_state(state, new_ref, set(args.slot_id), transition_ref)
        after = write_new(output / "state-after.json", new_state)
        write_new(output / "commit-intent.json", {"previous": state_ref, "snapshot": old_snapshot,
                  "next": after, "transition": transition_ref, "automatic_start": False})
        if reference(queue / "state.json") != state_ref:
            raise ValueError("Queue state changed despite the stopped-controller lock")
        staged = queue / "state.explicit-recovery-writing"
        write_new(staged, Path(after["path"]).read_bytes())
        staged.replace(queue / "state.json")
        descriptor = os.open(queue, os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        applied = {"status": "explicit_preclaim_recovery_applied", "transition": transition_ref,
                   "state": reference(queue / "state.json"), "automatic_start": False}
        write_new(output / "applied.json", applied)
        print(json.dumps(applied))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
