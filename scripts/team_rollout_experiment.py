"""Read-only D2 materialization over a frozen raw-slot inventory; no model calls."""

import argparse
import copy
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.episode import assess_historical_episode
from proworksim.information_mapper import information_graph, map_joint_method
from proworksim.member_views import member_view
from proworksim.rewards import episode_reward, validate_reward_spec
from proworksim.storage import atomic_write, digest, json_bytes, read_json
from proworksim.support_weights import build_support, materialize_weights
from proworksim.team_rollout import export_team_rollout, validate_window
from proworksim.team_validity import assess_team_validity

INVENTORY_VERSION = "team-materialization-inventory-v0.12"


def _write(root, name, value):
    path = root / name
    atomic_write(path, json_bytes(value))
    return {"path": str(path.resolve()), "sha256": digest(path.read_bytes())}


def _resolve(base, path):
    value = Path(path)
    return (value if value.is_absolute() else base / value).resolve()


def _pinned_json(base, reference):
    if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
        raise ValueError("Evidence must declare an exact file path and byte SHA256")
    path = _resolve(base, reference["path"])
    if digest(path.read_bytes()) != reference["sha256"]:
        raise ValueError("Pinned evidence SHA256 mismatch: " + str(path))
    return read_json(path)


def materialize_inventory(inventory_path, output):
    inventory_path = Path(inventory_path).resolve()
    inventory = read_json(inventory_path)
    if inventory.get("version") != INVENTORY_VERSION or not inventory.get("windows"):
        raise ValueError("A versioned nonempty frozen window inventory is required")
    windows = inventory["windows"]
    identities = [validate_window(row["window"])["window_id"] for row in windows]
    if len(identities) != len(set(identities)):
        raise ValueError("Each collection window must occur once")
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Materialization output must be a new directory")
    # Refuse a destination within an input episode to keep this operation read-only.
    for declaration in windows:
        for slot in declaration["slots"]:
            episode = _resolve(inventory_path.parent, slot["episode"])
            episode = episode.parent if episode.name == "manifest.json" else episode
            if output == episode or episode in output.parents:
                raise ValueError("Output cannot modify an input episode")
    output.mkdir(parents=True)
    source_before = code_identity()
    inventory_ref = _write(output, "inventory.json", inventory)
    reports = []
    for wi, declaration in enumerate(windows):
        window = validate_window(declaration["window"])
        members = declaration["members"]
        reward_spec = validate_reward_spec(declaration["reward_spec"])
        assessment_spec = declaration.get("assessment_spec", {})
        protocol = _pinned_json(inventory_path.parent, declaration["protocol_ref"])
        if not isinstance(protocol, dict):
            raise ValueError("Frozen execution protocol must be an object")
        mapper = declaration["mapper"]
        if set(mapper) != {"route_id", "spec_id"}:
            raise ValueError("Mapper route and equivalence identity must be fixed")
        destination = output / ("window-" + str(wi))
        destination.mkdir()
        slots, details = [], []
        for si, incoming in enumerate(declaration["slots"]):
            slot = {"slot_id": incoming["slot_id"], "window": window, "rollout": None}
            detail = {
                "slot_id": incoming["slot_id"],
                "input": copy.deepcopy(incoming),
                "status": "unusable",
                "refs": {},
            }
            folder = destination / ("slot-" + str(si))
            folder.mkdir()
            try:
                episode = _resolve(inventory_path.parent, incoming["episode"])
                episode = episode.parent if episode.name == "manifest.json" else episode
                manifest = read_json(episode / "manifest.json")
                scenario = _pinned_json(inventory_path.parent, incoming["scenario_ref"])
                fixed_scenario = manifest["scenario"].get("spec", manifest["scenario"])
                if scenario != fixed_scenario:
                    raise ValueError("Scenario differs from the one fixed at episode start")
                capture = _pinned_json(inventory_path.parent, incoming["capture_ref"])
                if incoming.get("record_ref"):
                    # The raw runner record is provenance only, never a score.
                    _pinned_json(inventory_path.parent, incoming["record_ref"])
                validity = assess_team_validity(
                    episode,
                    members=members,
                    independent_capture=capture,
                    spec=scenario["variation"]["validity_spec"],
                    assessment_spec=assessment_spec,
                )
                assessment = assess_historical_episode(episode, **assessment_spec)
                reward = episode_reward(assessment, reward_spec)
                rollout = export_team_rollout(
                    episode,
                    window=window,
                    members=members,
                    validity=validity,
                    reward=reward,
                    assessment_spec=assessment_spec,
                )
                graph = information_graph(rollout)
                mapping = map_joint_method(graph, **mapper)
                views = {member: member_view(rollout, member) for member in members}
                slot.update(rollout=rollout, mapping=mapping, member_views=views)
                for name, value in {
                    "validity": validity,
                    "assessment": assessment,
                    "reward": reward,
                    "team-rollout": rollout,
                    "information-graph": graph,
                    "mapping": mapping,
                    "member-views": views,
                }.items():
                    detail["refs"][name] = _write(folder, name + ".json", value)
                detail.update(
                    status="materialized",
                    rollout_id=rollout["rollout_id"],
                    manifest_sha256=rollout["manifest_sha256"],
                    reward_eligible=reward["eligible"],
                    reward=reward["reward"],
                    validity=validity["value"],
                    validity_components={
                        key: value["value"] for key, value in validity["components"].items()
                    },
                    mapping_status=mapping["status"],
                    class_id=mapping["class_id"],
                    origins={key: value["origin"] for key, value in members.items()},
                    members={
                        key: {
                            field: view[field]
                            for field in (
                                "own_action_count",
                                "own_action_tokens",
                                "complete_actor_trajectory",
                                "complete_semantic_trajectory",
                                "no_own_actions",
                            )
                        }
                        for key, view in views.items()
                    },
                )
            except Exception as error:
                # This is a materializer boundary failure, not worker reward 0
                # and not V=false. Preserve the raw slot and explicit exception.
                slot = {"slot_id": incoming["slot_id"], "window": window, "rollout": None}
                detail.update(
                    error={"type": type(error).__name__, "message": str(error)},
                    reward_eligible=None,
                    reward=None,
                    validity=None,
                    failure_boundary="read_only_materialization",
                )
            slots.append(slot)
            details.append(detail)
        support = build_support(
            slots,
            window=window,
            member_ids=list(members),
            min_class_count=declaration["min_class_count"],
        )
        baseline_q = {member: block["b"] for member, block in support["blocks"].items()}
        baseline = materialize_weights(support, baseline_q)
        support_ref = _write(destination, "support.json", support)
        baseline_ref = _write(destination, "q-equals-b.json", baseline)
        present = [row for row in details if row["status"] == "materialized"]
        counts = {
            "M": len(details),
            "materialized": len(present),
            "unusable": len(details) - len(present),
            "reward_eligible": sum(row["reward_eligible"] is True for row in present),
            "reward_zero": sum(
                row["reward_eligible"] is True and row["reward"] == 0 for row in present
            ),
            "valid_true": sum(row["validity"] is True for row in present),
            "valid_false": sum(row["validity"] is False for row in present),
            "valid_unknown": sum(row["validity"] is None for row in present),
            "mapped": sum(row["mapping_status"] == "mapped" for row in present),
            "ambiguous": sum(row["mapping_status"] == "ambiguous" for row in present),
            "unmapped": sum(row["mapping_status"] == "unmapped" for row in present),
            "current_target_joint_valid": sum(
                row["validity"] is True
                and all(origin == "target_model" for origin in row["origins"].values())
                for row in present
            ),
        }
        report = {
            "window": window,
            "protocol_ref": declaration["protocol_ref"],
            "counts": counts,
            "raw_joint_valid_yield": {
                "n": counts["current_target_joint_valid"],
                "M": len(details),
                "rate": counts["current_target_joint_valid"] / len(details),
            },
            "member_support": {
                member: {
                    key: block[key]
                    for key in (
                        "M",
                        "n_positive",
                        "v",
                        "b",
                        "n_by_class",
                        "semantic_work_support",
                        "composition_degrees_of_freedom",
                    )
                }
                for member, block in support["blocks"].items()
            },
            "slots": details,
            "support_ref": support_ref,
            "q_equals_b_ref": baseline_ref,
            "q_equals_b_all_original_weights_one": all(
                weight == 1
                for block in baseline["members"].values()
                for weight in block["weights"].values()
            ),
            "q_equals_b_scope": "Weight materialization only; full PPO loss/gradient/update equality is a separate D3 acceptance",
        }
        report["report_ref"] = _write(destination, "report.json", report)
        reports.append(report)
    total_keys = reports[0]["counts"]
    summary = {
        "version": "team-materialization-report-v0.12",
        "inventory_ref": inventory_ref,
        "input_inventory": {
            "path": str(inventory_path),
            "sha256": digest(inventory_path.read_bytes()),
        },
        "source_before": source_before,
        "source_after": code_identity(),
        "counts_across_windows_only": {
            key: sum(row["counts"][key] for row in reports) for key in total_keys
        },
        "windows": reports,
        "scope": "Counts may be summed for reporting, but no class distribution, support, q, policy or information layout is pooled across windows. Program witnesses and semantic-only API records never create target actor support.",
    }
    _write(output, "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = materialize_inventory(args.inventory, args.output)
    print(
        json_bytes(
            {
                "counts": result["counts_across_windows_only"],
                "summary": str(args.output / "summary.json"),
            }
        ).decode()
    )


if __name__ == "__main__":
    main()
