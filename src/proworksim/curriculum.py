"""Explainable development-only quotas, separate from frozen evaluation."""

from collections import Counter

from .contracts import CURRENT_EVALUATORS

AXES = ("source_selection", "inputs", "scenario", "dependency", "recalculability", "consistency")


def propose_quotas(records, total=24, representative_fraction=0.75):
    if total < 1 or not 0 <= representative_fraction <= 1:
        raise ValueError("Invalid curriculum budget")
    failures = Counter()
    excluded = Counter()
    grouped = {}
    for index, row in enumerate(records):
        key = (
            (row["episode_id"], row["work_item_id"])
            if "episode_id" in row and "work_item_id" in row
            else ("unidentified", index)
        )
        grouped[key] = row
    for row in grouped.values():
        if row.get("split") != "dev":
            excluded["non_development"] += 1
            continue
        if (
            row.get("evaluator_version") is not None
            and row["evaluator_version"] not in CURRENT_EVALUATORS
        ):
            excluded["obsolete_evaluator"] += 1
            continue
        if row.get("validity", "valid") != "valid":
            excluded["invalid_environment_or_evaluation"] += 1
            continue
        for category in {check["category"] for check in row["checks"] if not check["passed"]}:
            if category in AXES:
                failures[category] += 1
    representative = round(total * representative_fraction)
    stress = total - representative
    quotas = {axis: representative // len(AXES) for axis in AXES}
    for axis in AXES[: representative % len(AXES)]:
        quotas[axis] += 1
    weights = {axis: failures[axis] + 1 for axis in AXES}
    weight_sum = sum(weights.values())
    fractional = {axis: stress * weights[axis] / weight_sum for axis in AXES}
    stress_quotas = {axis: int(fractional[axis]) for axis in AXES}
    ranked = sorted(
        AXES,
        key=lambda axis: (
            -(fractional[axis] - stress_quotas[axis]),
            -failures[axis],
            AXES.index(axis),
        ),
    )
    for axis in ranked[: stress - sum(stress_quotas.values())]:
        stress_quotas[axis] += 1
    return {
        "controller_version": "quota-v0.1",
        "total": total,
        "representative_quotas": quotas,
        "stress_quotas": stress_quotas,
        "development_failure_counts": dict(failures),
        "excluded": dict(excluded),
        "explanation": "代表池均衡分配；压力池按开发集失败计数加一平滑、用最大余数法分配。测试集不参与配额反馈。",
        "applied": False,
        "limitations": "v0.1 quotas select existing structural profiles; they do not train parameters or alter held-out evaluation.",
    }


PROFILES = {
    "source_selection": ("short", "mail"),
    "inputs": ("file", "clarification"),
    "scenario": ("file", "mail"),
    "dependency": ("continuous", "mail"),
    "recalculability": ("file", "mail"),
    "consistency": ("continuous", "clarification"),
}


def synthesize_from_quotas(proposal, destination, seed_start=1000, workers=4):
    """Materialize train-only worlds; a focus label never implies a new task family."""
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    from .compiler import compile_world
    from .designer import design, lineage_split
    from .storage import atomic_write, json_bytes

    destination = Path(destination)
    if destination.exists():
        raise ValueError("Curriculum destination already exists")
    assignments = []
    next_seed = seed_start
    for pool, quotas in (
        ("representative", proposal["representative_quotas"]),
        ("stress", proposal["stress_quotas"]),
    ):
        for axis, count in quotas.items():
            if axis not in PROFILES or type(count) is not int or count < 0:
                raise ValueError("Invalid quota profile or count")
            for _ in range(count):
                while lineage_split(f"synthetic-operating-{next_seed}") != "train":
                    next_seed += 1
                assignments.append((next_seed, pool, axis))
                next_seed += 1
    if len(assignments) != proposal["total"] or workers < 1:
        raise ValueError("Quota totals or worker count are invalid")
    destination.mkdir(parents=True)

    def compile_one(assignment):
        seed, pool, axis = assignment
        delivery, information = PROFILES[axis]
        spec = design(seed, delivery, information, pool)
        path = compile_world(spec, destination / f"{seed}-{axis}")
        return {
            "path": str(path),
            "focus": axis,
            "pool": pool,
            "lineage_id": spec.project.lineage_id,
            "split": spec.project.split,
            "delivery": delivery,
            "information": information,
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        worlds = list(executor.map(compile_one, assignments))
    manifest = {
        "proposal": {**proposal, "applied": True},
        "worlds": worlds,
        "caveat": "Pressure labels allocate sampling focus; no additional noise is injected.",
    }
    atomic_write(destination / "curriculum.json", json_bytes(manifest))
    return manifest
