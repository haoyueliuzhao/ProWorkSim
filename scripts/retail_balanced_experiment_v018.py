"""Bounded actual-world crossed-review controls, never model trajectories."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.domains.work_product import evaluate_submission
from proworksim.storage import digest, json_bytes
from proworksim.templates.retail_balanced import QUALITIES, build_balanced_case, registry, resolve
from proworksim.work_interface import WorkInterface
from scripts.build_harness_learning_v018 import REVIEW_TRAIN


def check_one(case, root):
    prepared = build_balanced_case(case, root)
    state = prepared.world.state
    item = state["work_items"]["TEAM::build"]
    sub = item["submissions"][-1]
    grade = evaluate_submission(prepared.world.store, state, item, sub)
    observed = WorkInterface(
        prepared.world.session("reviewer", "TEAM"), "reviewer", variant="v14"
    ).observe()

    def keys(value):
        if isinstance(value, dict):
            for k, v in value.items():
                yield k
                yield from keys(v)
        elif isinstance(value, list):
            for v in value:
                yield from keys(v)

    no_labels = not set(keys(observed)) & {
        "prepared_submission",
        "review_quality",
        "original_source_case",
        "review_design",
    }
    public = str(json_bytes(observed))
    no_labels &= all(q not in public for q in ("wrong_count", "wrong_amount"))
    oids = state["workspaces"]["TEAM"]
    products = {}
    for alias in ("data", "basis", "audit_basis", "code", "result"):
        oid = oids[alias]
        vid = (
            sub["artifact_versions"].get(oid)
            if alias in ("code", "result")
            else list(state["artifacts"][oid]["versions"])[-1]
        )
        path = prepared.world.store.version_path(state["artifacts"][oid], vid)
        products[alias] = {"object_id": oid, "version_id": vid, "sha256": digest(path.read_bytes())}
    result = {
        "case_id": case["case_id"],
        "pool": case["pool"],
        "fact": case["fact_position"],
        "host_preparation_control": case["prepared_submission"],
        "independent_content_passed": grade["passed"],
        "matches_control": grade["passed"] is (case["prepared_submission"] == "correct"),
        "actor_observation_has_no_quality_metadata": bool(no_labels),
        "products": products,
        "preparation_ref": {
            "path": str((root / "preparation.json").resolve()),
            "sha256": digest((root / "preparation.json").read_bytes()),
        },
        "evaluation": grade,
        "model_execution": False,
    }
    (root / "crossed-control.json").write_bytes(json_bytes(result))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    # Both learning and evaluation source pools, each with the full 3x3 cross.
    cases = [
        resolve(pool, fact, "review", quality)
        for pool in ("train", "locked")
        for fact in range(3)
        for quality in QUALITIES
    ]
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        rows = list(ex.map(lambda c: check_one(c, a.output / c["case_id"]), cases))
    source_same = []
    for pool in ("train", "locked"):
        for fact in range(3):
            own = [r for r in rows if r["pool"] == pool and r["fact"] == fact]
            source_same.append(
                {
                    "pool": pool,
                    "fact": fact,
                    "equal_source_and_policy_bytes": all(
                        len({r["products"][k]["sha256"] for r in own}) == 1
                        for k in ("data", "basis", "audit_basis")
                    ),
                }
            )
    train = defaultdict(Counter)
    for row in REVIEW_TRAIN:
        for fact, quality in row:
            train[fact][quality] += 1
    predicted = {
        fact: sorted(counts, key=lambda q: (-counts[q], QUALITIES.index(q)))[0]
        for fact, counts in train.items()
    }
    matched = sum(predicted[fact] == quality for fact in range(3) for quality in QUALITIES)
    report = {
        "version": "crossed-review-world-controls-v0.18",
        "rows": rows,
        "source_policy_controls": source_same,
        "catalog_cases": len(registry()["situations"]),
        "real_prepared_worlds": len(rows),
        "real_model_calls": 0,
        "policy_label_proxy": {
            "uses": "Host-only training schedule, policy/date/source fact lookup; not a model or reward-passing strategy.",
            "train_counts": {str(k): dict(v) for k, v in train.items()},
            "predicted_quality": predicted,
            "locked_preparation_type_matches": matched,
            "locked_preparation_types": 9,
            "accuracy": matched / 9,
            "old_deterministic_catalog_accuracy": 1,
            "does_not_measure_full_review_reward": True,
        },
        "scope": "Real write/build/fixed-submit construction and independent content check. No model tuning on locked outcomes; no complete review-model reward or generalization claim.",
        "passed": all(
            r["matches_control"] and r["actor_observation_has_no_quality_metadata"] for r in rows
        )
        and all(r["equal_source_and_policy_bytes"] for r in source_same)
        and matched == 3,
    }
    (a.output / "report.json").write_bytes(json_bytes(report))
    print({"passed": report["passed"], "prepared_worlds": len(rows), "proxy_matches": matched})
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
