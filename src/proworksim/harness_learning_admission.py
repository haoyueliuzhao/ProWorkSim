"""Bounded H2 prerequisites, separate from old S1 and H1 admission contracts."""

import copy
import importlib
import sys
from pathlib import Path

from .harness_admission import checked_ref, require, _guard
from .storage import digest, json_bytes, read_json


def _builder(revised=False, optimized=False):
    root = str(Path(__file__).resolve().parents[2])
    added = root not in sys.path
    if added:
        sys.path.insert(0, root)
    try:
        name = "v019" if optimized else "v018" if revised else "v017"
        return importlib.import_module("scripts.build_harness_learning_" + name)
    finally:
        if added:
            sys.path.remove(root)


OPTIMIZATION_VERSION = "harness-optimization-admission-v0.19"
OPTIMIZATION_CHECKS = (
    "prefix_probability", "full_recompute_probability", "backward", "two_replica", "throughput"
)


def validate_optimization_admission(reference, *, candidate_id, runtime_profile, weight_manifest,
                                    replicas=2):
    """Metadata-only actual numerical/performance gate; never read work scores."""
    from .audit import code_identity
    from .candidate_runtime_v019 import candidate_profile

    require(type(replicas) is int and replicas in (1, 2), "Declare one or two sampling replicas")
    report = read_json(checked_ref(reference))
    require(report.get("sampling_replicas") == replicas,
            "Optimization benchmark replica layout differs from the predeclared execution")
    require(report.get("version") == OPTIMIZATION_VERSION,
            "Actual v0.19 optimization admission report required")
    source = code_identity()
    require(source.get("code_dirty") is False and source.get("code_commit")
            and report.get("execution_source_commit") == source["code_commit"],
            "Optimization gate must bind this clean frozen execution source")
    candidates = report.get("candidates")
    require(isinstance(candidates, dict), "Optimization candidates absent")
    candidate = candidates.get(candidate_id)
    require(isinstance(candidate, dict) and candidate.get("passed") is True,
            "Selected candidate has not passed actual optimization gates; no profile fallback")
    names = {"qwen35-9b": "qwen3.5-9b", "qwen38-27b": "qwen3.8-27b"}
    require(candidate_id in names and isinstance(runtime_profile, dict),
            "Unknown optimized candidate/profile")
    expected = candidate_profile(names[candidate_id], dtype="float32",
                                 devices=runtime_profile.get("devices"))
    require(runtime_profile == expected and candidate.get("runtime_profile") == expected,
            "Optimization gate/runtime profile differs from declared FP32 optimized prefix execution")
    manifest = Path(weight_manifest)
    require(manifest.is_file() and candidate.get("weight_manifest_sha256") == digest(manifest.read_bytes()),
            "Optimization benchmark base weights differ from selected H1 manifest")
    initial = candidate.get("initial_actor_identity")
    require(isinstance(initial, dict) and initial.get("adapter_sha256")
            and initial.get("base_manifest_sha256") == candidate["weight_manifest_sha256"],
            "Optimization gate lacks actual fresh initial actor/weight identity")
    checks = candidate.get("checks")
    require(isinstance(checks, dict), "Actual optimization evidence checks absent")
    evidence = {}
    for name in OPTIMIZATION_CHECKS:
        if name == "two_replica" and replicas == 1:
            continue
        check = checks.get(name)
        require(isinstance(check, dict) and check.get("passed") is True,
                "Actual optimization check did not pass: " + name)
        checked_ref(check.get("evidence"))
        evidence[name] = copy.deepcopy(check["evidence"])
    return {"status": "admitted", "version": OPTIMIZATION_VERSION,
            "candidate_id": candidate_id, "optimization_admission": copy.deepcopy(reference),
            "execution_source_commit": source["code_commit"],
            "runtime_profile": copy.deepcopy(expected), "checks": evidence,
            "sampling_replicas": replicas, "initial_actor_identity": copy.deepcopy(initial),
            "scope": "Actual fixed-input numerical, backward, replica and throughput evidence; no work-grade-based replacement."}


def validate_h2_launch(protocol, *, model_path, weight_manifest, restore_checkpoint=None):
    optimized = protocol.get("stage") in {"H2_v019", "ID_support_v019"}
    if optimized or protocol.get("runtime", {}).get("kind") == "qwen_hybrid_optimized":
        require(optimized and protocol.get("runtime", {}).get("kind") == "qwen_hybrid_optimized",
                "Optimized runtime requires the explicitly gated v0.19 stage")
    if protocol.get("stage") in {"ID_support_v018", "ID_support_v019"}:
        return validate_support_launch(
            protocol,
            model_path=model_path,
            weight_manifest=weight_manifest,
            restore_checkpoint=restore_checkpoint,
        )
    if protocol.get("stage") not in {"H2", "H2_v018", "H2_v019"}:
        return {"status": "not_H2"}
    revised = protocol.get("stage") in {"H2_v018", "H2_v019"}
    suffix = "v019" if optimized else "v018" if revised else "v017"
    gate_version = "h2-admission-" + {"v019": "v0.19", "v018": "v0.18", "v017": "v0.17"}[suffix]
    require(
        not restore_checkpoint,
        "H2 starts fresh after migration; checkpoint restoration is forbidden",
    )
    selection = read_json(checked_ref(protocol.get("selection")))
    comparison = read_json(checked_ref(selection.get("report_ref")))
    kept = {k: v for k, v in selection.items() if k != "report_ref"}
    require(kept == comparison.get("selection"), "H2 selection differs from its actual H1 report")
    require(
        len(comparison.get("models", [])) == 2
        and all(m.get("ended") for m in comparison["models"]),
        "H2 selection was made before both H1 model runs ended",
    )
    for model in comparison["models"]:
        actual_launch = read_json(checked_ref(model["references"]["launch"]))
        require(
            type(actual_launch.get("exit_code")) is int and actual_launch.get("end") is not None,
            "actual H1 launch has not ended",
        )
    choice = selection.get("selected")
    require(
        selection.get("status") == "selected" and isinstance(choice, dict),
        "H2 requires completed H1 combination selection",
    )
    h1 = read_json(checked_ref(choice.get("protocol_ref")))
    require(
        protocol.get("candidate_id") == choice.get("candidate_id")
        and protocol.get("harness") == choice.get("harness"),
        "H2 does not match actually selected model/harness",
    )
    h1root = Path(choice["run_root"])
    h1report = read_json(h1root / "online/report.json")
    require(
        h1report.get("status") == "complete"
        and h1report.get("actor_steps_total") == h1report.get("critic_steps_total") == 0,
        "H1 actual run is not complete pure evaluation",
    )
    for w in h1report["windows"]:
        _guard(w.get("evaluation_guard", {}))
    original_owner = read_json(h1root / "resident/owner.json")
    base = original_owner["base_identity"]
    require(
        Path(model_path).resolve() == Path(base["path"]).resolve()
        and Path(weight_manifest).resolve() == checked_ref(base["manifest"]),
        "H2 base weights differ from selected model",
    )
    optimization = None
    extra = {}
    if optimized:
        optimization = validate_optimization_admission(
            protocol.get("optimization_admission"), candidate_id=choice["candidate_id"],
            runtime_profile=protocol["runtime"]["profile"], weight_manifest=weight_manifest,
            replicas=protocol.get("sampling_replicas"))
        extra.update(optimization_admission=protocol["optimization_admission"],
                     replicas=protocol["sampling_replicas"],
                     optimized_devices=protocol["runtime"]["profile"]["devices"])
    migration, pilot = _builder(revised, optimized).build_protocols(
        h1, choice["harness"], protocol["selection"], **extra
    )
    candidate = copy.deepcopy(protocol)
    candidate.pop("launch_gate", None)
    expected = (
        migration
        if protocol.get("experiment_id") == "h2-migration-" + suffix
        else copy.deepcopy(pilot)
    )
    expected.pop("launch_gate", None)
    require(candidate == expected, "H2 frozen recipe, worlds or budgets differ")
    record = {
        "status": "admitted",
        "stage": protocol["experiment_id"],
        "selection": protocol["selection"],
        "worlds": "train only for updates; new frozen within-source locked evaluation for pilot",
        "expected_initial_adapter_sha256": choice.get("initial_actor_identity", {}).get(
            "adapter_sha256"
        ),
    }
    if optimization is not None:
        record["optimization"] = optimization
        actual_initial = optimization["initial_actor_identity"]["adapter_sha256"]
        record["old_H1_adapter_matches"] = record["expected_initial_adapter_sha256"] == actual_initial
        record["expected_initial_adapter_sha256"] = actual_initial
    if protocol.get("experiment_id") == "h2-pilot-" + suffix:
        gate = protocol.get("launch_gate", {})
        require(
            gate.get("version") == gate_version and gate.get("state") == "admitted",
            "H2 pilot waits for an actual bounded current-token update and new-policy interaction",
        )
        migrated = read_json(checked_ref(gate.get("migration_report")))
        require(
            migrated.get("status") == "complete"
            and migrated.get("actor_steps_total") == 1
            and migrated.get("critic_steps_total") == 1
            and len(migrated.get("windows", [])) == 2,
            "actual migration did not complete one shared update and its post-update probe",
        )
        train, probe = migrated["windows"]
        require(
            train.get("update", {}).get("status") == "updated"
            and train["update"].get("behavior_probability_passed") is True
            and train["update"].get("changed_actor_elements", 0) > 0
            and train["before_actor_identity"] != probe["before_actor_identity"]
            and train["after_actor_identity"] == probe["before_actor_identity"],
            "migration lacks original-probability/changed-parameter/new-identity evidence",
        )
        _guard(probe.get("evaluation_guard", {}))
        migration_root = Path(gate["migration_report"]["path"]).parent.parent
        actual_protocol = read_json(migration_root / "launch-protocol.json")
        require(
            actual_protocol == migration
            and migrated.get("protocol_sha256") == digest(json_bytes(migration)),
            "migration used a different declared combination/recipe",
        )
        require(
            read_json(migration_root / "source-comparison.json").get("unchanged") is True,
            "migration source changed",
        )
        from .member_views import member_view

        observed_roles = set()
        for index, spec in enumerate(migration["windows"][1]["slots"]):
            rollout = read_json(
                migration_root / f"online/window-1/collection/slot-{index}/team-rollout.json"
            )
            require(
                rollout["reward_eligibility"].get("eligible") is True,
                "post-update migration probe has unknown work reward",
            )
            for role in spec["role_decision_limits"]:
                view = member_view(rollout, role)
                require(
                    view["complete_actor_trajectory"],
                    "new-policy probe lacks complete original own-token history",
                )
                for decision in view["decisions"]:
                    response = decision.get("actual_response")
                    if response:
                        require(
                            response.get("actor_identity") == probe["before_actor_identity"],
                            "role continued with an old actor identity after migration",
                        )
                        observed_roles.add(role)
        require(
            observed_roles == {"provider", "implementer", "reviewer"},
            "all role types must really interact under the shared new identity",
        )
        record["actual_new_policy_roles"] = sorted(observed_roles)
        record["migration_report"] = gate["migration_report"]
    return record


def validate_support_launch(protocol, *, model_path, weight_manifest, restore_checkpoint):
    optimized = protocol.get("stage") == "ID_support_v019"
    suffix = "v019" if optimized else "v018"
    gate = protocol.get("launch_gate", {})
    require(
        gate.get("version") == ("id-support-density-v0.19" if optimized else "id-support-density-v0.18") and gate.get("state") == "admitted",
        "Support density waits for a completed pilot and its fixed final checkpoint; planning alone cannot launch",
    )
    report_path = checked_ref(gate.get("pilot_report"))
    root = report_path.parent.parent
    report, pilot = read_json(report_path), read_json(root / "launch-protocol.json")
    require(
        pilot.get("stage") == "H2_" + suffix
        and pilot.get("experiment_id") == "h2-pilot-" + suffix
        and report.get("status") == "complete"
        and len(report.get("windows", [])) == len(pilot.get("windows", [])) == 6,
        "Support diagnosis requires the completed predeclared pilot, not an intermediate/best checkpoint",
    )
    validate_h2_launch(pilot, model_path=model_path, weight_manifest=weight_manifest)
    require(
        read_json(root / "source-comparison.json").get("unchanged") is True,
        "Completed pilot source changed",
    )
    from .audit import code_identity

    require(
        code_identity() == read_json(root / "source-before.json"),
        "Support diagnosis must use the same frozen environment/harness source as the pilot",
    )
    final = root / "online/window-5/checkpoint"
    require(
        restore_checkpoint and Path(restore_checkpoint).resolve() == final.resolve(),
        "Support must restore exactly the predetermined completed final checkpoint",
    )
    checkpoint = read_json(final / "checkpoint.json")
    require(
        checkpoint.get("actor_identity") == report.get("final_actor_identity")
        and checkpoint.get("serialized_reload_exact") is True,
        "Support checkpoint identity differs from final actual pilot actor",
    )
    selection = read_json(checked_ref(protocol.get("selection")))
    choice = selection.get("selected") or {}
    h1 = read_json(checked_ref(choice.get("protocol_ref")))
    extra = {"optimization_admission": protocol.get("optimization_admission"),
             "replicas": pilot["sampling_replicas"],
             "optimized_devices": pilot["runtime"]["profile"]["devices"]} if optimized else {}
    expected = _builder(True, optimized).support_protocol(
        h1, choice["harness"], protocol["selection"], **extra)
    if optimized:
        require(protocol.get("optimization_admission") == pilot.get("optimization_admission"),
                "Support optimization evidence differs from completed pilot")
    actual = copy.deepcopy(protocol)
    actual.pop("launch_gate", None)
    expected.pop("launch_gate", None)
    require(
        actual == expected
        and protocol["candidate_id"] == pilot["candidate_id"]
        and protocol["harness"] == pilot["harness"],
        "Support cases, density or candidate changed",
    )
    return {
        "status": "admitted",
        "stage": "ID_support_" + suffix,
        "pilot_report": gate["pilot_report"],
        "fixed_final_actor_identity": checkpoint["actor_identity"],
        "expected_optimizer_updates": 0,
        "scope": "One current-policy 16-episode support measurement. No composition intervention or O4 auto-start.",
    }
