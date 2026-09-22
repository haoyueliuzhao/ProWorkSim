"""Seeded structural synthesis; all financial materials are fictional."""

import hashlib
import random

from .schema import ProjectSpec, RoleSpec, WorldSpec
from .layouts import LayoutMap
from .workflow import make_workflow

DELIVERIES = ("short", "file", "continuous")
INFORMATION_MODES = ("mail", "clarification")


def lineage_split(lineage_id: str) -> str:
    bucket = int(hashlib.sha256(lineage_id.encode()).hexdigest()[:8], 16) % 10
    return "train" if bucket < 7 else "dev" if bucket < 9 else "test"


def design(
    seed: int = 1,
    delivery: str = "continuous",
    information: str = "mail",
    pool: str = "representative",
    topology: str = "chain",
    layout: str = "standard",
) -> WorldSpec:
    if delivery not in DELIVERIES or information not in INFORMATION_MODES:
        raise ValueError("Unsupported delivery or information mode")
    if pool not in ("representative", "stress"):
        raise ValueError("Pool must be representative or stress")
    if layout not in ("standard", "shifted"):
        raise ValueError("Unsupported layout")
    if topology == "coordination":
        information = "clarification"
    workflow = make_workflow(delivery, topology)
    layout_map = (
        LayoutMap(layout)
        if layout == "standard"
        else LayoutMap(layout, "Parameters", "Valuation", "Cases", "D", "E", 2, 3)
    )
    rng = random.Random(seed)
    lineage = f"synthetic-operating-{seed}"
    revenue = rng.randrange(800, 2000, 10)
    margin = rng.randrange(12, 25) / 100
    facts = {
        "old": {
            "revenue": revenue,
            "operating_margin": margin,
            "diluted_eps": round(rng.uniform(1.2, 3), 2),
            "period": "FY2024",
        },
        "current": {
            "revenue": revenue + rng.randrange(50, 200, 10),
            "operating_margin": round(margin + 0.01, 4),
            "diluted_eps": round(rng.uniform(1.5, 3.5), 2),
            "period": "FY2025",
        },
        "future": {
            "revenue": revenue + rng.randrange(220, 350, 10),
            "operating_margin": round(margin + 0.02, 4),
            "diluted_eps": round(rng.uniform(2, 4), 2),
            "period": "FY2025-restated",
        },
    }
    assumptions = {
        "growth": rng.choice([0.03, 0.05, 0.07]),
        "margin_delta": 0.01,
        "tax_rate": 0.25,
        "earnings_multiple": rng.choice([12, 15, 18]),
        "net_debt": rng.randrange(50, 150, 10),
        "shares": 100,
        "growth_grid": [0.02, 0.08],
        "margin_delta_grid": [0, 0.02],
    }
    roles = (
        RoleSpec("client", "定义用途与需求变化", "client-events-v0.1"),
        RoleSpec("manager", "分配工作、确认口径", "conditional-scope-v0.1"),
        RoleSpec("analyst", "发现证据、修改模型并交付", "external-policy", trainable=True),
        RoleSpec(
            "reviewer", "审阅实际提交物并明确批准版本", "consistency-review-v0.1", can_approve=True
        ),
    )
    project = ProjectSpec(
        project_id=f"project-{seed}-{delivery}-{information}-{topology}-{layout}",
        lineage_id=lineage,
        split=lineage_split(lineage),
        company=f"合成企业-{seed:04d}",
        information_access=information,
        delivery=delivery,
        continuity=delivery == "continuous",
        pool=pool,
        topology_id=topology,
        layout_id=layout,
        role_information_id=information,
        core_operations=("retrieve", "combine")
        if delivery == "short"
        else ("retrieve", "recalculate", "compare", "modify"),
    )
    return WorldSpec(
        project=project,
        roles=roles,
        seed=seed,
        facts=facts,
        assumptions=assumptions,
        workflow=workflow.public_spec(),
        layout=layout_map.public(),
    )
