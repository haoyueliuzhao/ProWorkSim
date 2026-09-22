"""Seeded structural synthesis; all financial materials are fictional."""

import hashlib
import random

from .schema import ProjectSpec, RoleSpec, OperatingTemplateSpec
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
    scenario: str = "standard",
) -> OperatingTemplateSpec:
    if delivery not in DELIVERIES or information not in INFORMATION_MODES:
        raise ValueError("Unsupported delivery or information mode")
    if pool not in ("representative", "stress"):
        raise ValueError("Pool must be representative or stress")
    if layout not in ("standard", "shifted"):
        raise ValueError("Unsupported layout")
    if topology == "coordination":
        information = "clarification"
    if scenario not in (
        "standard",
        "basis_only",
        "during_update",
        "waiting_reply",
        "during_review",
        "unavailable",
    ):
        raise ValueError("Unknown lifecycle scenario")
    if scenario != "standard" and (
        delivery != "continuous" or topology not in ("chain", "coordination")
    ):
        raise ValueError("Lifecycle scenarios currently use the continuous chain configuration")
    if scenario in ("waiting_reply", "unavailable"):
        information = "clarification"
    workflow = make_workflow(delivery, topology).public_spec()
    lifecycle_events = []
    if scenario == "basis_only":
        workflow["event_rules"][0]["effects"] = [{"kind": "publish_scope", "revision": 2}]
        workflow["nodes"][1].update(source_stage="current", source_version="v2")
    elif scenario in ("during_update", "waiting_reply", "during_review", "unavailable"):
        workflow["nodes"] = [workflow["nodes"][0]]
        workflow["event_rules"] = []
        if scenario != "unavailable":
            action = {
                "during_update": "sheet_update",
                "waiting_reply": "mail_send",
                "during_review": "submit",
            }[scenario]
            trigger = {"action": action, "actor_id": "analyst"}
            if action != "sheet_update":
                trigger["work_item_id"] = "work-1"
            if action == "mail_send":
                trigger["topic"] = "scope"
            lifecycle_events = [
                {
                    "event_id": f"{scenario}-basis-change",
                    "trigger": trigger,
                    "delay": 0,
                    "effect": {"kind": "revise_basis", "targets": ["work-1"], "growth_delta": 0.02},
                }
            ]

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
        RoleSpec(
            "manager", "分配工作、确认口径", "scoped-confirmation-v0.3", can_confirm_basis=True
        ),
        RoleSpec("analyst", "发现证据、修改模型并交付", "external-policy", trainable=True),
        RoleSpec(
            "reviewer", "审阅实际提交物并明确批准版本", "versioned-review-v0.3", can_approve=True
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
        topology_id="chain" if topology == "coordination" else topology,
        configuration_id=topology,
        work_graph_id="chain" if topology == "coordination" else topology,
        scenario_id=scenario,
        event_policy_id=scenario
        if scenario != "standard"
        else ("audience_only" if topology == "selective" else "disclosure_and_basis"),
        layout_id=layout,
        role_information_id=information,
        core_operations=("retrieve", "combine")
        if delivery == "short"
        else ("retrieve", "recalculate", "compare", "modify"),
    )
    return OperatingTemplateSpec(
        project=project,
        roles=roles,
        seed=seed,
        facts=facts,
        assumptions=assumptions,
        workflow=workflow,
        lifecycle_events=lifecycle_events,
        unavailable_topics=("scope",) if scenario == "unavailable" else (),
        layout=layout_map.public(),
    )
