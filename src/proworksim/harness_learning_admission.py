"""Bounded H2 prerequisites, separate from old S1 and H1 admission contracts."""

import copy
import importlib
import sys
from pathlib import Path

from .harness_admission import checked_ref, require, _guard
from .storage import digest, json_bytes, read_json


def _builder(revised=False):
    root = str(Path(__file__).resolve().parents[2])
    added = root not in sys.path
    if added:
        sys.path.insert(0, root)
    try:
        return importlib.import_module(
            "scripts.build_harness_learning_v018"
            if revised
            else "scripts.build_harness_learning_v017"
        )
    finally:
        if added:
            sys.path.remove(root)


def validate_h2_launch(protocol, *, model_path, weight_manifest, restore_checkpoint=None):
    if protocol.get("stage") == "ID_support_v018":
        return validate_support_launch(
            protocol,
            model_path=model_path,
            weight_manifest=weight_manifest,
            restore_checkpoint=restore_checkpoint,
        )
    if protocol.get("stage") not in {"H2", "H2_v018"}:
        return {"status": "not_H2"}
    revised = protocol.get("stage") == "H2_v018"
    suffix = "v018" if revised else "v017"
    gate_version = "h2-admission-v0.18" if revised else "h2-admission-v0.17"
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
    migration, pilot = _builder(revised).build_protocols(
        h1, choice["harness"], protocol["selection"]
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
    gate = protocol.get("launch_gate", {})
    require(
        gate.get("version") == "id-support-density-v0.18" and gate.get("state") == "admitted",
        "Support density waits for a completed pilot and its fixed final checkpoint; planning alone cannot launch",
    )
    report_path = checked_ref(gate.get("pilot_report"))
    root = report_path.parent.parent
    report, pilot = read_json(report_path), read_json(root / "launch-protocol.json")
    require(
        pilot.get("stage") == "H2_v018"
        and pilot.get("experiment_id") == "h2-pilot-v018"
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
    expected = _builder(True).support_protocol(h1, choice["harness"], protocol["selection"])
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
        "stage": "ID_support_v018",
        "pilot_report": gate["pilot_report"],
        "fixed_final_actor_identity": checkpoint["actor_identity"],
        "expected_optimizer_updates": 0,
        "scope": "One current-policy 16-episode support measurement. No composition intervention or O4 auto-start.",
    }
