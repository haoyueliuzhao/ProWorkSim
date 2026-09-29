"""One complete replay of the proven unstepped v025 baseline window.

Restore the original shared-before state, including persistent optimizer/RNG
state. The lost 266 partial backwards are not checkpoints: every admitted row
must be recomputed. This module neither schedules models nor grants a retry.
"""

from __future__ import annotations

import math
from pathlib import Path
import shutil
import subprocess

from .composition_training_v025 import validate_composition
from .online_support import bind_rollout
from .online_training import VERSION as TRAINER_VERSION, prepare_window, tensor_tree_digest
from .storage import atomic_write, digest, json_bytes, read_json

VERSION = "same-unstepped-composition-recovery-v0.25-R1"
OLD_COMMIT = "e37432483e430d366ea706efc307caf86451d2e3"
WINDOW_ID = "v025-window-1"
PRE_STEP_ARTIFACTS = (
    "gradient-probability-check.json",
    "losses.json",
    "signal-diagnostics.json",
    "gradients-before-clip.pt",
)
TRAINING_SOURCES = (
    "online_training.py",
    "composition_training_v025.py",
    "support_weights.py",
    "online_support.py",
    "member_views.py",
    "online_signals.py",
    "critic_features.py",
    "functional_qwen_v022.py",
)
ROOT = Path(__file__).resolve().parents[2]


def reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}


def checked(value):
    if not isinstance(value, dict) or set(value) not in (
        {"path", "sha256"},
        {"path", "sha256", "bytes"},
    ):
        raise ValueError("Exact original file reference schema required")
    actual = reference(value["path"])
    if actual["sha256"] != value["sha256"] or (
        "bytes" in value and actual["bytes"] != value["bytes"]
    ):
        raise ValueError("An immutable original recovery input changed: " + value["path"])
    return Path(actual["path"])


def original_process_alive(expected):
    """A recycled PID is not the old worker; no signal is ever sent here."""
    if not isinstance(expected, dict) or type(expected.get("pid")) is not int:
        raise ValueError("Original recorded process identity is required")
    p = Path("/proc") / str(expected["pid"])
    try:
        fields = (p / "stat").read_text().rsplit(")", 1)[1].split()
        return (
            int(fields[19]) == expected["start_ticks"]
            and p.stat().st_uid == expected["uid"]
            and fields[0] != "Z"
        )
    except (FileNotFoundError, ProcessLookupError):
        return False


def unchanged_training_sources():
    hashes = {}
    for name in TRAINING_SOURCES:
        relative = "src/proworksim/" + name
        old = subprocess.check_output(
            ["git", "show", OLD_COMMIT + ":" + relative], cwd=ROOT, timeout=15
        )
        if (ROOT / relative).read_bytes() != old:
            raise ValueError(
                "Original learner/normalization/composition source changed: " + relative
            )
        hashes[relative] = digest(old)
    return hashes


def prove_no_step(root, stage, guard, report, supervisor):
    root = Path(root)
    update = root / "train_base/actual/update"
    if (
        stage.get("stage") != "train_base"
        or stage.get("status") != "stopped"
        or stage.get("exit_code") != -15
        or not stage.get("ended_at")
        or supervisor.get("status") != "closed_with_incomplete_stages"
        or not supervisor.get("ended_at")
        or stage.get("source", {}).get("code_commit") != OLD_COMMIT
        or stage["source"].get("code_dirty") is not False
        or guard.get("last_stop_reason") != "resource_query_failed"
        or guard.get("worker_identity", {}).get("pid") != stage.get("pid")
        or original_process_alive(guard.get("worker_identity"))
        or original_process_alive(guard.get("original_supervisor_identity"))
    ):
        raise ValueError(
            "Only the closed resource-query interruption with dead original worker/observer is admitted"
        )
    if (
        stage.get("task", {}).get("kind") != "update"
        or report.get("window_id") != WINDOW_ID
        or report.get("stage") != "backward"
        or report.get("status") != "preparing"
        or report.get("scheduled_slots") != 16
        or report.get("admitted_decisions") != 283
        or report.get("backward_decisions_completed") != 266
        or report.get("actor_optimizer_steps") != 0
        or report.get("critic_optimizer_steps") != 0
        or report.get("training_happened") is not False
        or report.get("behavior_probability_passed") is not True
    ):
        raise ValueError("Original 266/283 probability-qualified but unstepped window required")
    if any((update / name).exists() for name in PRE_STEP_ARTIFACTS):
        raise ValueError("Mandatory pre-step artifact exists; no-step proof fails")
    if any(
        (root / name).exists()
        for name in (
            "train_base/actual/checkpoint-final",
            "checkpoints/base.json",
            "base-complete.json",
        )
    ):
        raise ValueError("An updated successor checkpoint already exists")
    return {
        "admitted": True,
        "worker_original_identity_dead": True,
        "missing_pre_step_artifacts": list(PRE_STEP_ARTIFACTS),
        "last_persisted_backward_completed": 266,
        "scheduled_decisions": 283,
        "optimizer_steps_this_attempt": 0,
        "terminal_live_tensor_read": False,
        "guard_trigger": "resource_query_failed",
        "legacy_supervisor_label": stage.get("stop_reason"),
        "proof": "Frozen updater must write all four named artifacts before either optimizer.step; all absent after the original processes ended.",
    }


def build_recovery_binding(old_run):
    """Freeze immutable original inputs and no-step proof, without tensor loading."""
    root = Path(old_run).resolve()
    supervisor = read_json(root / "supervisor.json")
    stage = read_json(root / "train_base/state.json")
    guard = read_json(root / "budget-extension/state.json")
    report = read_json(root / "train_base/actual/update/report.json")
    proof = prove_no_step(root, stage, guard, report, supervisor)
    source_files = unchanged_training_sources()
    marker = read_json(root / "support-complete.json")
    consumption = read_json(root / "train_base/actual/consumption.json")
    original_source = supervisor["source"]
    worker_report = read_json(root / "train_base/actual/report.json")
    if (
        marker.get("source") != original_source
        or stage["source"] != original_source
        or worker_report.get("source_before") != original_source
        or marker.get("selected_block") is not None
        or marker.get("actual_new_episodes") != 16
        or consumption.get("branch") != "base"
        or consumption.get("same_complete_origin") is not True
        or consumption.get("raw_entries") != marker["entries"]
        or consumption.get("declaration") != marker["declaration"]
    ):
        raise ValueError("Only the original no-supported-block F0 collection may be replayed")
    inputs = {
        name: reference(path)
        for name, path in {
            "supervisor": root / "supervisor.json",
            "stage": root / "train_base/state.json",
            "guard": root / "budget-extension/state.json",
            "worker_report": root / "train_base/actual/report.json",
            "update_report": root / "train_base/actual/update/report.json",
            "shared_before": root / "train_base/actual/update/shared-before.pt",
            "admission": root / "train_base/actual/update/admission.json",
            "entries": checked(marker["entries"]),
            "declaration": checked(marker["declaration"]),
            "composition": checked(consumption["composition"]),
            "composition_admission": root / "train_base/actual/update/composition-admission.json",
            "behavior_checks": root / "train_base/actual/update/behavior-probability-check.json",
            "consumption": root / "train_base/actual/consumption.json",
            "support_marker": root / "support-complete.json",
            "support": checked(marker["support"]),
            "training_admission": checked(marker["admission"]),
            "original_plan": checked(supervisor["plan"]),
        }.items()
    }
    if read_json(checked(inputs["composition"])) != read_json(
        root / "train_base/actual/update/composition.json"
    ):
        raise ValueError("Original update materialization differs from its declared consumption")
    cost = supervisor.get("terminated_gpu_seconds")
    if type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0:
        raise ValueError("The entire original failed attempt cost must remain recorded")
    return {
        "version": VERSION,
        "original_run": str(root),
        "original_source": original_source,
        "inputs": inputs,
        "training_source_files": source_files,
        "no_step_proof": proof,
        "original_total_gpu_seconds": cost,
        "new_training_model_calls": 0,
        "partial_gradients_reused": False,
        "original_window_id": WINDOW_ID,
        "required_actor_steps_before": 2,
        "required_critic_steps_before": 2,
        "maximum_new_actor_steps": 1,
        "maximum_new_critic_steps": 1,
        "scheduled_slots": 16,
        "admitted_decisions": 283,
        "scope": "Explicit one-time R1 recomputation, not continuation at decision267. No new support sampling, altered loss or resampling.",
    }


def _rebuild_original(binding):
    refs = binding["inputs"]
    entries = read_json(checked(refs["entries"]))
    declaration = read_json(checked(refs["declaration"]))
    composition = read_json(checked(refs["composition"]))
    original = read_json(checked(refs["admission"]))
    update = read_json(checked(refs["update_report"]))
    if (
        len(entries) != binding["scheduled_slots"]
        or len(declaration["slots"]) != len(entries)
        or declaration["window_id"] != binding["original_window_id"]
        or original["window_id"] != declaration["window_id"]
        or declaration["actor_identity"] != original["actor_identity"]
        or update["before_actor_identity"] != original["actor_identity"]
        or [e["slot_id"] for e in entries] != [s["slot_id"] for s in declaration["slots"]]
        or composition.get("Q_equals_B") is not True
        or composition.get("selected_block") is not None
        or composition.get("changed_blocks") != []
    ):
        raise ValueError("All exact original slots and unit F0 composition must be retained")
    for entry in entries:
        bind_rollout(declaration, entry["slot_id"], entry["rollout"], mapping=entry["mapping"])
    checks = read_json(checked(refs["behavior_checks"]))
    if (
        len(original["decisions"]) != binding["admitted_decisions"]
        or len(checks) != len(original["decisions"])
        or [c["call_id"] for c in checks] != [r["call_id"] for r in original["decisions"]]
        or any(c.get("passed") is not True for c in checks)
    ):
        raise ValueError("Original full admission and probability-check inventory differ")
    weights, material = validate_composition(entries, original, composition)
    old_material = read_json(checked(refs["composition_admission"]))
    if material != old_material or any(w != 1 for w in weights):
        raise ValueError("Original member/token weight materialization is not exact all-unit F0")
    return entries, declaration, composition, original, material


def _restore_bound_state(owner, binding, output, *, feature_function=None):
    """Internal exact restore, also exercised by a small CPU state fixture."""
    if owner.phase != "idle" or owner.busy or owner.sampling_only:
        raise ValueError("Restoration requires an idle full learner")
    output = Path(output).resolve()
    if output == Path(binding["original_run"]).resolve() or output.is_relative_to(
        Path(binding["original_run"]).resolve()
    ):
        raise ValueError("Recovery output must be outside the original failed run")
    entries, declaration, composition, original, material = _rebuild_original(binding)
    torch = owner.torch
    before_path = checked(binding["inputs"]["shared_before"])
    state = torch.load(before_path, map_location="cpu", weights_only=True)
    if (
        state.get("version") != TRAINER_VERSION
        or state.get("recipe") != owner.recipe
        or state["recipe"]["credit_assignment"] != "terminal_mc"
        or state.get("base_identity") != owner.base_identity
        or state.get("inference_profile") != owner.inference_profile
        or state.get("actor_identity") != original["actor_identity"]
        or state.get("actor_steps") != binding["required_actor_steps_before"]
        or state.get("critic_steps") != binding["required_critic_steps_before"]
        or state.get("policy_revision") != binding["required_actor_steps_before"]
        or state.get("last_window_id") != binding["original_window_id"]
        or not state.get("used_window_ids")
        or state["used_window_ids"][-1] != binding["original_window_id"]
        or state["used_window_ids"].count(binding["original_window_id"]) != 1
        or set(state["actor"]) != set(owner.actor_parameters)
    ):
        raise ValueError(
            "Raw shared-before state differs from the exact prior actor/critic/window recipe"
        )
    for name, parameter in owner.actor_parameters.items():
        if (
            state["actor"][name].shape != parameter.shape
            or state["actor"][name].dtype != parameter.dtype
        ):
            raise ValueError("Original adapter shape or precision differs")
    expected_digest = tensor_tree_digest(state, torch)
    # Make a new legal checkpoint wrapper around byte-identical original state;
    # the old file and directory are never modified, renamed or forged.
    checkpoint = output / "recovery-checkpoint"
    checkpoint.mkdir(parents=True, exist_ok=False)
    copied = checkpoint / "shared-state.pt"
    shutil.copyfile(before_path, copied)
    if reference(copied)["sha256"] != binding["inputs"]["shared_before"]["sha256"]:
        raise ValueError("Copied original complete state bytes changed")
    metadata = {
        "version": TRAINER_VERSION,
        "state": reference(copied),
        "actor_identity": state["actor_identity"],
        "actor_steps": state["actor_steps"],
        "critic_steps": state["critic_steps"],
        "state_tensor_digest": expected_digest,
        "scope": "New R1 wrapper around exact original shared-before bytes; not a completed failed-run checkpoint.",
    }
    atomic_write(checkpoint / "checkpoint.json", json_bytes(metadata))
    owner.restore_checkpoint(checkpoint)
    owner.actor_optimizer.zero_grad(set_to_none=True)
    owner.critic_optimizer.zero_grad(set_to_none=True)
    restored_digest = tensor_tree_digest(owner._state_bundle(), torch)
    if restored_digest != expected_digest or owner.freeze_identity() != original["actor_identity"]:
        raise ValueError("Actor/critic/two optimizer/RNG complete state did not restore exactly")
    rebuilt = prepare_window(
        entries, owner.freeze_identity(), owner.window_id, owner.recipe, feature_function
    )
    rebuilt_sha = digest(json_bytes(rebuilt))
    if rebuilt != original or rebuilt_sha != binding["inputs"]["admission"]["sha256"]:
        raise ValueError(
            "The recomputed original full admission differs in fields or exact JSON bytes"
        )
    weights, reconstructed_material = validate_composition(entries, rebuilt, composition)
    if reconstructed_material != material or any(w != 1 for w in weights):
        raise ValueError("Restored original unit composition weights differ")
    owner.phase = "collecting"  # Do not begin a new window or duplicate used IDs.
    proof = {
        "version": VERSION,
        "original_run": binding["original_run"],
        "inputs": binding["inputs"],
        "original_source": binding.get("original_source"),
        "no_step_proof": binding["no_step_proof"],
        "original_total_gpu_seconds": binding["original_total_gpu_seconds"],
        "restoration": {
            "exact_state_restored": True,
            "state_tensor_digest": expected_digest,
            "restored_state_tensor_digest": restored_digest,
            "raw_shared_before": binding["inputs"]["shared_before"],
            "new_checkpoint": reference(checkpoint / "checkpoint.json"),
            "actor_steps_before_window": owner.actor_steps,
            "critic_steps_before_window": owner.critic_steps,
            "actor_identity": owner.freeze_identity(),
            "window_id": owner.window_id,
            "used_window_ids": list(owner.used_window_ids),
            "restored_components": [
                "actor",
                "critic",
                "actor_optimizer",
                "critic_optimizer",
                "CPU/CUDA RNG",
            ],
            "partial_gradients_reused": False,
            "new_training_model_calls": 0,
            "begin_window_called": False,
        },
        "admission_reconstruction": {
            "exactly_equal": True,
            "sha256": rebuilt_sha,
            "original": binding["inputs"]["admission"],
            "scheduled_slots": len(entries),
            "admitted_decisions": len(rebuilt["decisions"]),
        },
        "composition_reconstruction": {
            "exactly_equal": True,
            "all_unit_weights": True,
            "composition_reference": binding["inputs"]["composition"],
            "composition_admission_reference": binding["inputs"]["composition_admission"],
            "sha256": digest(json_bytes(reconstructed_material)),
        },
    }
    atomic_write(output / "restoration-proof.json", json_bytes(proof))
    return entries, composition, proof


def restore_failed_window(owner, old_run, plan_refs, output):
    """Production R1 entry: exact frozen failed window, no new sampling."""
    rebuilt_binding = build_recovery_binding(old_run)
    if rebuilt_binding != plan_refs:
        raise ValueError("Predeclared R1 source, failed-window evidence or accounting changed")
    return _restore_bound_state(owner, plan_refs, output)
