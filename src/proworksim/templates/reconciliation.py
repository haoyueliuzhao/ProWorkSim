"""Synthetic finite financial reconciliation package and independent literal truth.

All workflow setup is explicit package data. Fixture truth is hand specified; it
is not computed by the worker or domain validator. Amounts are illustrative.
"""

import copy

ALIASES = ("ledger", "statement", "definitions")


def fixtures(*, corrected=False, variant=False):
    def row(rid, metric, value, **changes):
        result = {
            "record_id": rid,
            "entity": "Acme",
            "metric": metric,
            "period": "2026H1",
            "definition": "net",
            "currency": "CNY",
            "unit": "ones",
            "value": value,
            "location": "records/" + rid,
        }
        result.update(changes)
        return result

    left = [
        row("L1", "cash", 100),
        row("L2", "sales", 2, unit="thousands"),
        row("L3", "cost", 80),
        row("L4", "prior", 5, period="2025H1"),
        row("L5", "scope", 9, definition="gross"),
        row("L6", "fx", 6, currency="USD"),
        row("L7", "unknown", None),
        row("L8", "absent", 4),
        row("L9a", "duplicate", 7),
        row("L9b", "duplicate", 7),
    ]
    right = [
        row("R1", "cash", 100),
        row("R2", "sales", 2000),
        row("R3", "cost", 80 if corrected else 90),
        row("R4", "prior", 5),
        row("R5", "scope", 9),
        row("R6", "fx", 6),
        row("R7", "unknown", 8),
        row("R9", "duplicate", 7),
    ]
    policy = {
        "key_fields": ["entity", "metric"],
        "reporting_period": "2026H1",
        "base_unit": "ones",
        "unit_factors": {"ones": 1, "thousands": 1000},
    }
    if variant:
        left.reverse()
        right = right[3:] + right[:3]
    for side in (left, right):
        for index, record in enumerate(side):
            record["location"] = ("appendix/" if variant else "") + "records/" + str(index)
    if variant:
        return {
            "left": {"appendix": {"records": left}},
            "right": {"appendix": {"records": right}},
            "policy": {"basis": policy},
        }
    return {"left": {"records": left}, "right": {"records": right}, "policy": policy}


def literal_truth(corrected=False):
    return {
        "absent": {"status": "missing", "left_value": None, "right_value": None, "delta": None},
        "cash": {"status": "matched", "left_value": 100, "right_value": 100, "delta": 0},
        "cost": {
            "status": "matched" if corrected else "conflict",
            "left_value": 80,
            "right_value": 80 if corrected else 90,
            "delta": 0 if corrected else -10,
        },
        "duplicate": {
            "status": "ambiguous",
            "left_value": None,
            "right_value": None,
            "delta": None,
        },
        "fx": {"status": "incomparable", "left_value": None, "right_value": None, "delta": None},
        "prior": {"status": "incomparable", "left_value": None, "right_value": None, "delta": None},
        "sales": {"status": "converted", "left_value": 2000, "right_value": 2000, "delta": 0},
        "scope": {"status": "incomparable", "left_value": None, "right_value": None, "delta": None},
        "unknown": {"status": "missing", "left_value": None, "right_value": None, "delta": None},
    }


def content_contract(aliases=ALIASES, *, nested=False):
    left, right, policy = aliases
    return {
        "min_files": 1,
        "max_files": 2,
        "allowed_roles": ["reconciliation"],
        "allowed_kinds": ["json"],
        "required_fields": ["reconciliation", "sources"],
        "content_checks": [
            {
                "kind": "reconciliation_table",
                "path": ["reconciliation"],
                "left_alias": left,
                "right_alias": right,
                "policy_alias": policy,
                "sources": [
                    {
                        "alias": a,
                        "reference_path": ["sources", a],
                        "data_path": (["basis"] if a == policy else ["appendix"]) if nested else [],
                    }
                    for a in aliases
                ],
            }
        ],
    }


def package(
    project_id="A",
    owner="analyst",
    reviewer="reviewer",
    *,
    variant=False,
    unavailable=False,
    hidden_right=False,
    corrected=False,
    review=False,
):
    aliases = ("trial_balance", "external_schedule", "basis_note") if variant else ALIASES
    data = fixtures(corrected=corrected, variant=variant)
    objects = []
    for alias, kind in zip(aliases, ("left", "right", "policy")):
        obj = {
            "alias": alias,
            "filename": ("appendix-" if variant else "") + alias + ".json",
            "owner": owner,
            "readers": [owner, reviewer],
            "kind": "json",
            "data": data[kind],
        }
        if hidden_right and kind == "right":
            obj.update(owner=reviewer, readers=[reviewer])
        objects.append(obj)
    result = {
        "project_id": project_id,
        "goal": "Reconcile the complete finite record set, preserving conflicts and unknowns",
        "participants": [owner, reviewer],
        "objects": objects,
        "works": [
            {
                "work_id": "reconcile",
                "owner": owner,
                "goal": "Read both tables and the public basis; deliver every key once with exact evidence",
                "approval_policy": "review" if review else "delivery_only",
                "deliverable_contract": content_contract(aliases, nested=variant),
                "requirements": {
                    "input_policies": {a: "fixed" for a in aliases},
                    "input_versions": {a: "v1" for a in aliases},
                },
            }
        ],
        "grants": [
            {"actor_id": owner, "power": p, "subject": "artifact", "work_nodes": ["reconcile"]}
            for p in ("adopt", "create_object")
        ]
        + [{"actor_id": owner, "power": p, "subject": "artifact"} for p in ("publish", "share")]
        + [
            {
                "actor_id": reviewer,
                "power": p,
                "subject": "deliverable",
                "work_nodes": ["reconcile"],
            }
            for p in ("approve", "review")
        ]
        + [
            {
                "actor_id": reviewer,
                "power": "provide",
                "subject": "evidence",
                "work_nodes": ["reconcile"],
            }
        ],
    }
    if hidden_right:
        result["information_routes"] = [
            {
                "route_id": "right-material",
                "work_id": "reconcile",
                "object_alias": aliases[1],
                "provider": reviewer,
                "availability": "unavailable" if unavailable else "available",
                "delay": 1,
                "version_policy": "fixed",
                "version_id": "v1",
            }
        ]
    return copy.deepcopy(result)
