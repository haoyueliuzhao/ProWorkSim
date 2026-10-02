"""Software ports on the existing managed SDK, with finite development collection.

The caller supplies an already-created owner/transport and a new explicit window.
Nothing here loads a model, allocates a GPU, selects a patch or calls an optimizer.
"""

import copy
from pathlib import Path
import time

from .audit import code_identity
from .episode import begin_episode, finish_episode
from .harness_collection import _runtime
from .online_collection import run_fragment
from .online_support import declare_window
from .software_collaboration_v027 import (
    MEMBERS, VERSION as INTERFACE_VERSION, SoftwareCollaborationPort,
    assess_software_collaboration, build_software_collaboration_case, case_spec,
)
from .storage import atomic_write, digest, json_bytes

VERSION = "software-runtime-v0.27"
MAPPER = "software-work-methods-v0.27"


def build_runtime(owner, prepared, folder, harness="openhands_v16"):
    """Return (runtime, raw_capture_by_member, interfaces), without sampling."""
    if harness != "openhands_v16":
        raise ValueError("The new software protocol fixes the existing OpenHands SDK harness")
    if prepared.case != case_spec(prepared.case["case_id"]):
        raise ValueError("Build only a declared software development case")
    before = prepared.world.store.load()
    runtime, captured, interfaces = _runtime(owner, prepared, Path(folder), harness,
                                             interface_factory=SoftwareCollaborationPort)
    if prepared.world.store.load() != before:
        close_runtime(runtime)
        raise ValueError("SDK construction must not change the software world")
    return runtime, captured, interfaces


def close_runtime(runtime):
    for worker in runtime.policies.values():
        worker.close()


def _validate_window(spec):
    if not isinstance(spec, dict) or spec.get("harness") != "openhands_v16":
        raise ValueError("Declare the software SDK harness explicitly")
    if not isinstance(spec.get("window_id"), str) or not spec["window_id"]:
        raise ValueError("Declare a new software window identity")
    if spec.get("usage") != "interface_dev" or spec.get("mode") != "frozen_development":
        raise ValueError("This reused software asset is only frozen interface development")
    slots = spec.get("slots")
    if not isinstance(slots, list) or not slots:
        raise ValueError("Predeclare every finite software slot")
    seen = set()
    requested_calls = 0
    for row in slots:
        if not isinstance(row, dict) or set(row) != {"slot_id", "case_id", "sampling_seed"}:
            raise ValueError("Each slot needs exactly slot_id, case_id and sampling_seed")
        if not isinstance(row["slot_id"], str) or not row["slot_id"] or row["slot_id"] in seen:
            raise ValueError("Slot IDs must be nonempty and unique")
        seen.add(row["slot_id"])
        if type(row["sampling_seed"]) is not int or row["sampling_seed"] < 0:
            raise ValueError("Predeclare an integer sampling seed per software slot")
        requested_calls += sum(case_spec(row["case_id"])["role_decision_limits"].values())
    budget = spec.get("budget")
    if (not isinstance(budget, dict) or set(budget) != {"max_slots", "max_model_calls"}
            or type(budget["max_slots"]) is not int or type(budget["max_model_calls"]) is not int
            or budget["max_slots"] != len(slots) or budget["max_model_calls"] != requested_calls):
        raise ValueError("Declare this window's exact finite slot and model-call caps; old GPU budgets are not inherited")
    if type(spec.get("min_class_count")) is not int or spec["min_class_count"] < 1:
        raise ValueError("Predeclare the development diagnostic frequency threshold")
    return slots


def collect_software_window(owner, window_spec, output_dir):
    """Finite current-owner work, archived before any optional later study.

    Existing per-role SDK budgets enforce the declared model-call cap. GPU and
    process lifetime remain the caller's newly authorized resource supervisor;
    this function cannot inherit or extend an earlier experiment's resource cap.
    Every world/policy/seed binding is frozen before the first opportunity.
    """
    rows = _validate_window(window_spec)
    if owner.window_id != window_spec["window_id"]:
        raise ValueError("Current owner must enter this exact software window before collection")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    atomic_write(output / "window-spec.json", json_bytes(window_spec))
    identity = owner.freeze_identity()
    prepared_slots = []
    try:
        for index, row in enumerate(rows):
            folder = output / f"slot-{index}"
            prepared = build_software_collaboration_case(row["case_id"], folder)
            runtime, captured, interfaces = build_runtime(owner, prepared, folder)
            scenario = copy.deepcopy(prepared.scenario)
            scenario.setdefault("variation", {})["software_case"] = copy.deepcopy(prepared.case)
            scenario["variation"]["software_runtime"] = {
                "version": VERSION, "harness": "openhands_v16", "source_usage": "interface_dev",
                "profile_bindings": {role: interface.profile for role, interface in interfaces.items()},
                "external_tick_per_sweep": 0}
            initial = {"case": prepared.case, "reward_spec": prepared.reward_spec,
                       "initial_business_sha256": prepared.prefix["prepared_business_state_sha256"]}
            slot_spec = {"slot_id": row["slot_id"], "xi_id": prepared.case["case_id"],
                         "xi_fingerprint": digest(json_bytes(initial)), "active_members": list(MEMBERS),
                         "policies": runtime.policy_identities, "mapping_spec_id": MAPPER}
            prepared_slots.append({"row": row, "folder": folder, "prepared": prepared,
                                   "runtime": runtime, "captured": captured, "scenario": scenario,
                                   "slot_spec": slot_spec, "closed": False})
            atomic_write(folder / "model-scenario.json", json_bytes(scenario))
        gamma = {"collection_version": VERSION, "harness": "openhands_v16", "interface": INTERFACE_VERSION,
                 "source": code_identity(), "source_usage": "interface_dev", "recipe": copy.deepcopy(owner.recipe),
                 "context_projection": "latest_observation_last4_tool_rounds", "external_tick_per_sweep": 0,
                 "budget": copy.deepcopy(window_spec["budget"]),
                 "slot_sampling_seeds": {row["slot_id"]: row["sampling_seed"] for row in rows},
                 "fixed_slot_cases": [item["slot_spec"]["xi_fingerprint"] for item in prepared_slots]}
        declaration = declare_window(window_spec["window_id"], actor_identity=identity, gamma_identity=gamma,
                                     slot_specs=[item["slot_spec"] for item in prepared_slots],
                                     min_class_count=window_spec["min_class_count"])
        atomic_write(output / "declaration.json", json_bytes(declaration))
        entries, summaries = [], []
        for item in prepared_slots:
            row, prepared, folder = item["row"], item["prepared"], item["folder"]
            runtime, captured = item["runtime"], item["captured"]
            if owner.freeze_identity() != identity:
                raise ValueError("Software development window cannot change the actor between slots")
            owner.reseed(row["sampling_seed"], label=row["slot_id"])
            episode = folder / "episode"
            begin_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), work_ids=[],
                          scenario=item["scenario"], policies=runtime.policy_identities)
            started = time.time()
            try:
                boundary = run_fragment(prepared, runtime, external_tick_per_sweep=0)
                finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination=boundary)
                close_runtime(runtime)
                item["closed"] = True
                # Private acceptance never supplies a later policy observation.
                assessment = assess_software_collaboration(prepared, run_root=folder / "private-assessment")
                from .software_training_v027 import export_software_episode
                entry, evidence = export_software_episode(prepared, episode, assessment,
                    declaration=declaration, slot_id=row["slot_id"], captured=captured)
                entries.append(entry)
                atomic_write(folder / "software-evidence.json", json_bytes(evidence))
                atomic_write(folder / "entry.json", json_bytes(entry))
                atomic_write(folder / "assessment.json", json_bytes(assessment))
                summary = {"slot_id": row["slot_id"], "case_id": row["case_id"], "status": "closed",
                           "boundary": boundary, "R": assessment["R"], "started_at": started,
                           "ended_at": time.time(), "training_eligible": False}
            except Exception as error:
                atomic_write(folder / "interruption.json", json_bytes({"type": type(error).__name__,
                             "message": str(error), "runtime_closed": item["closed"]}))
                raise
            finally:
                atomic_write(folder / "public-capture.json", json_bytes(captured))
                atomic_write(folder / "runtime.json", json_bytes(runtime.snapshot()))
            summaries.append(summary)
            atomic_write(output / "progress.json", json_bytes(summaries))
        if owner.freeze_identity() != identity:
            raise ValueError("Software development collection changed the actor identity")
        atomic_write(output / "summary.json", json_bytes({"version": VERSION, "usage": "interface_dev",
                     "actor_identity": identity, "slots": summaries, "training_eligible": False,
                     "scope": "Frozen development collection only; no optimizer, allocation gain or held-out source claim."}))
        return entries
    finally:
        for item in prepared_slots:
            if not item["closed"]:
                close_runtime(item["runtime"])
                item["closed"] = True
