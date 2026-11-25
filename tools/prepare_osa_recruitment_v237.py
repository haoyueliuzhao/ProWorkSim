"""Pre-register first-wave candidate identities, and distinguish observation from SDK restore."""

from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_context_panel_v231 import ROOT
from proworksim.storage import read_json, json_bytes, atomic_write

PLAN = ROOT / "artifacts/software-benchmark-v237/recruitment-r1"


def main():
    panel = read_json(
        ROOT / "artifacts/software-benchmark-v236/decision-differentiation-r1/panel.json"
    )
    results = read_json(
        ROOT / "artifacts/software-benchmark-v236-1/compact-decisions-r1/results.json"
    )
    if not results["decision_gate"]:
        raise ValueError("Decision gate not passed")
    candidates = []
    selections = [
        ("s01", None),
        ("s02", "software-benchmark-v216/target-repair-r1"),
        ("s04", "software-benchmark-v217/protocol-r1"),
        ("s03", None),
    ]
    for sid, source_panel in selections:
        r = next(x for x in panel if x["id"] == sid)
        src = ROOT / r["provenance"]["source"]
        item = dict(
            case=r["instance"],
            type=r["reference_type"],
            decision_panel_state=sid,
            historical_boundary=str(src.relative_to(ROOT)),
            historical_ordinal=r["provenance"]["ordinals"][-1],
            historical_legal_menu=r["options"],
            decision_checkpoint=r["provenance"]["checkpoint"],
        )
        if source_panel:
            parent = src.parents[1] / "PREFIX/checkpoint/manifest.json"
            m = read_json(parent)
            (configrow,) = [
                v
                for v in read_json(ROOT / "artifacts" / source_panel / "candidate-tasks.json")[
                    "rows"
                ]
                if v["instance_id"] == r["instance"]
            ]
            checked(configrow["configuration"])
            item.update(
                status="missing_exact_restorable_live_anomaly",
                parent_checkpoint_not_at_anomaly=m["identity"],
                parent_prefix_tokens=m["prefix_tokens"],
                candidate_source=reference(
                    ROOT / "artifacts" / source_panel / "candidate-tasks.json"
                ),
                config=configrow["configuration"],
                requirements=configrow["requirements"],
            )
        else:
            m = read_json(src.parent / "checkpoint/manifest.json")
            if (
                m["identity"] != item["decision_checkpoint"]
                or 5_000_000 - m["prefix_tokens"] != r["available_tokens"]
            ):
                raise ValueError("Checkpoint or budget mismatch")
            item.update(
                status="matched_registered_checkpoint",
                remaining_per_arm=r["available_tokens"],
                pair_reserve_nanoyuan=2 * r["available_tokens"] * 8000,
            )
        candidates.append(item)
    ready = sum(c.get("pair_reserve_nanoyuan", 0) for c in candidates)
    target = PLAN / "first-wave.json"
    data = dict(
        candidates=candidates,
        decision_gate=True,
        official_pair_count=0,
        first_wave_target=4,
        ready_pair_reserve_nanoyuan=ready,
        current_funds_nanoyuan=results["balance_nanoyuan"],
        additional_to_reserve_two_existing_pairs_concurrently_nanoyuan=max(
            0, ready - results["balance_nanoyuan"]
        ),
        recruitment="For the two missing categories acquire a natural live checkpoint at a settled authorized receipt with a scoped executable alternative. Record singleton menus, terminal and absent anomalies without replacing cases. Do not turn the earlier parent checkpoint or a later terminal workspace into the decision state.",
        full_task_endpoints=[
            "accepted in-scope graph",
            "owner opportunity and observed action",
            "anomaly resolution and recurrence if observable",
            "same-version tests and independent review",
            "official code and legal delivery",
            "actual usage including OSA; stop at delivery",
        ],
        policy_learning="No C/N update. Keep mechanism evidence separate from realized utility. Future Q0/Q_C/Q_CN require a prospectively separated development and confirmation panel.",
    )
    if target.exists() and read_json(target) != data:
        raise ValueError("Registered intake differs")
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(target, json_bytes(data))


if __name__ == "__main__":
    main()
