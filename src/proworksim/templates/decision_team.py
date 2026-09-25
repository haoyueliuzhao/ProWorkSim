"""Small information-asymmetric three-member SQL team for D1 support diagnosis.

Scenario manifests define instances and information layouts. Role prompts are
invariant across proactive/requested program witnesses and natural model runs.
"""

import copy

from ..core.world import object_identity

PERIOD = "2018-01"
ROLES = ("provider", "implementer", "reviewer")
ROLE_TASKS = {
    "provider": "You are a member responsible for the information you hold. Read the visible work goal, your evidence and manual routes; choose applicable exact evidence and how to communicate it, or truthfully report unavailable requested material. Retain explicit sources. Coordinate through the public tools. No prescribed communication order is required.",
    "implementer": "You implement the assigned SQL work. Use actual accessible data and applicable business basis, choose and record exact adoptions, edit/build/query code, check the public structure with preflight_submission, submit code and result, and handle real review feedback. Read manual routes and messages when information is missing. Do not fabricate inaccessible facts.",
    "reviewer": "You independently review the exact submitted code and result using your applicable audit basis and public data. Read real submissions/evidence, raise located issues when justified, assess actual responses and approve only supported work. Coordinate through manual routes for information you hold or need. Do not infer correctness from submission labels.",
}


def _table(columns, rows):
    return {"columns": [{"name": name, "type": kind} for name, kind in columns], "rows": rows}


def data_fixture(instance):
    if instance not in {"orders_a", "orders_b"}:
        raise ValueError("Unknown team base instance")
    rows = [
        [1, 1, "completed", "2018-01", 1000],
        [1, 1, "completed", "2018-01", 500],
        [2, 2, "returned", "2018-01", 700],
        [3, 2, "completed", "2018-01", 400],
        [4, 3, "pending", "2018-01", 900],
        [5, 3, "completed", "2018-02", 300],
    ]
    if instance == "orders_b":
        rows = [
            [1, 1, "completed", "2018-01", 700],
            [1, 1, "completed", "2018-01", 300],
            [2, 2, "returned", "2018-01", 200],
            [3, 2, "completed", "2018-01", 600],
            [4, 3, "pending", "2018-01", 400],
            [5, 3, "completed", "2018-02", 800],
        ]
    return {
        "tables": {
            "customers": _table([("customer_id", "BIGINT")], [[1], [2], [3]]),
            "transactions": _table(
                [
                    ("order_id", "BIGINT"),
                    ("customer_id", "BIGINT"),
                    ("status", "VARCHAR"),
                    ("period", "VARCHAR"),
                    ("amount", "BIGINT"),
                ],
                rows,
            ),
        }
    }


def basis_fixture(instance, *, old=False):
    statuses = ["completed"] if instance == "orders_a" else ["completed", "returned"]
    return {
        "tables": {
            "basis_meta": _table(
                [("period", "VARCHAR"), ("edition", "VARCHAR"), ("amount_factor", "BIGINT")],
                [["2017-12" if old else PERIOD, "retired" if old else "approved", 1]],
            ),
            "allowed_statuses": _table([("status", "VARCHAR")], [[s] for s in statuses]),
        },
        "note": "Only an approved definition applicable to the public work period can support its delivery. The status list is the business filter, not a precomputed answer.",
    }


def audit_fixture(instance, *, old=False):
    return {
        "period": "2017-12" if old else PERIOD,
        "edition": "retired" if old else "approved",
        "allowed_statuses": ["completed"] if instance == "orders_a" else ["completed", "returned"],
        "amount_factor": 1,
        "release_checks": [
            "Exact submitted code and result were read.",
            "Every public customer remains, including zero amounts.",
            "Amounts include only the stated period and status scope.",
            "Multiple transaction rows for one order add their money but count as one order.",
            "Chosen data and basis references/dependencies match the actual SQL execution.",
        ],
        "note": "Independent review instructions and business source; no expected numeric output is supplied.",
    }


def initial_code():
    return {
        "models": [
            {
                "name": "metrics",
                "sql": "SELECT customer_id,SUM(amount)::BIGINT AS revenue_cents,COUNT(*) AS order_count FROM transactions GROUP BY customer_id",
            }
        ],
        "tests": [
            {
                "name": "unique_customer",
                "sql": "SELECT customer_id FROM metrics GROUP BY customer_id HAVING COUNT(*) <> 1",
            }
        ],
        "config": {
            "exports": ["metrics"],
            "description": "Edit the SQL to implement the public task using the selected approved basis.",
        },
    }


def witness_code():
    """Private program witness only; never inserted in model tasks or output."""
    code = initial_code()
    code["models"][0]["sql"] = (
        "WITH eligible AS (SELECT t.customer_id,t.order_id,t.amount*b.amount_factor AS amount FROM transactions t JOIN allowed_statuses s ON t.status=s.status CROSS JOIN basis_meta b WHERE t.period=b.period AND b.edition='approved'),a AS (SELECT customer_id,SUM(amount)::BIGINT AS revenue_cents,COUNT(DISTINCT order_id)::BIGINT AS order_count FROM eligible GROUP BY customer_id) SELECT c.customer_id,COALESCE(a.revenue_cents,0)::BIGINT AS revenue_cents,COALESCE(a.order_count,0)::BIGINT AS order_count FROM customers c LEFT JOIN a ON c.customer_id=a.customer_id"
    )
    return code


def package(*, instance="orders_a", layout="split_a", control="base"):
    if layout not in {"split_a", "split_b"}:
        raise ValueError("Unknown information layout")
    if control not in {"base", "late", "old_versions", "unavailable", "all_info"}:
        raise ValueError("Unknown team control")
    holders = (
        {"basis": "provider", "audit_basis": "reviewer"}
        if layout == "split_a"
        else {"basis": "reviewer", "audit_basis": "provider"}
    )
    participants = [*ROLES, "operator"]

    def obj(alias, owner, data, role="draft", private=False):
        return {
            "alias": alias,
            "filename": alias + ".json",
            "kind": "json",
            "owner": owner,
            "readers": [owner] if private and control != "all_info" else list(participants),
            "deliverable_role": role,
            "data": data,
        }

    objects = [
        obj("data", "operator", data_fixture(instance)),
        obj("code", "implementer", initial_code(), "sql_code"),
        obj("result", "implementer", {}, "sql_result"),
        obj("query", "implementer", {}),
        obj(
            "basis",
            holders["basis"],
            basis_fixture(instance, old=control in {"old_versions", "unavailable"}),
            private=True,
        ),
        obj(
            "audit_basis",
            holders["audit_basis"],
            audit_fixture(instance, old=control == "old_versions"),
            private=True,
        ),
    ]
    # Evidence holders have delegated sharing rights, not authority to rewrite
    # the client's underlying business or audit rules.
    for artifact in objects:
        if artifact["alias"] in {"basis", "audit_basis"}:
            artifact["owner"] = "operator"
            artifact["writers"] = ["operator"]
            artifact["readers"] = sorted(set(artifact["readers"]) | {"operator"})
    requirements = {
        "input_policies": {"data": "fixed", "basis": "fixed"},
        "input_versions": {"data": "v1"},
        "source_objects": {
            "data": object_identity("TEAM", "data"),
            "basis": object_identity("TEAM", "basis"),
        },
        "sql_project": {
            "kind": "decision_team",
            "code_alias": "code",
            "result_alias": "result",
            "query_alias": "query",
        },
        "output_alias": "result",
        "reporting_period": PERIOD,
        "public_format": {
            "sources": "The result file has sources.data and sources.basis exact references, established by actual adoptions and sql_build input_aliases=[data,basis]. Merely reading is not adoption. The chosen basis version is not selected for you.",
            "output": "Exactly one metrics table with columns customer_id,revenue_cents,order_count, one row for every data.customers ID. Amounts are integer cents. Preserve zero rows. For the stated period include only basis.allowed_statuses; multiply amounts by basis_meta.amount_factor. Sum all qualifying transaction rows but count distinct order_id. Basis must be approved for the stated period.",
            "execution": "Submit exactly aliases code and result from the actual build. sql_build accepts existing typed table sources and records real inputs; editable tests are feedback only.",
            "preflight": "preflight_submission(work_id,artifacts=[code,result]) checks only public structure/references/dependencies. It never computes hidden business answers or supplies evidence.",
        },
        "review_contract": {
            "audit_alias": "audit_basis",
            "requirements": "Reviewer must actually read the exact submitted code/result and an approved audit_basis applicable to the reporting period; inspect data and check its independent release conditions. Use located issues and real response decisions, or approve justified first delivery.",
        },
    }
    grants = (
        [
            {
                "actor_id": "implementer",
                "power": power,
                "subject": "artifact",
                "work_nodes": ["build"],
            }
            for power in ["adopt", "execute_sql"]
        ]
        + [
            {
                "actor_id": "reviewer",
                "power": power,
                "subject": "deliverable",
                "work_nodes": ["build"],
            }
            for power in ["review", "approve"]
        ]
        + [
            {
                "actor_id": "operator",
                "power": "revise_requirement",
                "subject": "requirements",
                "work_nodes": ["build"],
            }
        ]
    )
    for alias, holder in holders.items():
        grants.append(
            {
                "actor_id": holder,
                "power": "provide",
                "subject": alias,
                "work_nodes": ["build"],
                "object_aliases": [alias],
            }
        )
    # grant normalization supports object_ids, not a new authority namespace.
    for grant in grants:
        if "object_aliases" in grant:
            grant["object_ids"] = grant.pop("object_aliases")
    routes = [
        {
            "route_id": alias,
            "mode": "manual",
            "work_id": "build",
            "provider": holder,
            "object_alias": alias,
            "recipients": ["implementer" if alias == "basis" else "reviewer"],
            "purpose": alias,
            "delay": 6 if control == "late" else 1,
        }
        for alias, holder in holders.items()
    ]
    return {
        "project_id": "TEAM",
        "goal": "Deliver and independently review customer metrics for the publicly stated period using applicable evidence held by different team members. Communicate as needed; no communication order is prescribed.",
        "participants": participants,
        "objects": objects,
        "works": [
            {
                "work_id": "build",
                "owner": "implementer",
                "approval_policy": "review",
                "goal": "Create the finite customer metrics table for "
                + PERIOD
                + " using actually adopted applicable business evidence, then resolve genuine review or obtain justified acceptance.",
                "visible_requirements": [
                    "Information holders, request recipients and exact communication semantics are in public manual routes. There is no automatic provider answer.",
                    "Use preflight_submission for the declared file/reference contract; business correctness still requires evidence and reasoning.",
                ],
                "requirements": requirements,
                "deliverable_contract": {
                    "min_files": 2,
                    "max_files": 2,
                    "allowed_roles": ["sql_code", "sql_result"],
                    "allowed_kinds": ["json"],
                    "required_fields": ["tables", "sources"],
                    "content_checks": [
                        {
                            "kind": "decision_team_sql",
                            "role": "sql_result",
                            "path": ["tables"],
                            "period": PERIOD,
                            "sources": [
                                {"alias": alias, "reference_path": ["sources", alias]}
                                for alias in ["data", "basis"]
                            ],
                        }
                    ],
                },
            }
        ],
        "grants": grants,
        "information_routes": routes,
        "provenance": {
            "kind": "synthetic",
            "source_evidence_refs": [
                "ProWorkSim finite team SQL mechanism derived from the pinned Jaffle Shop family conventions"
            ],
            "note": "Small explicitly synthetic transactions. Instance/layout labels remain in the host scenario manifest, not role prompts. No hidden numerical answer is supplied to members.",
        },
    }


def scenario_spec(*, instance="orders_a", layout="split_a", control="base"):
    from ..scenarios import SCENARIO_VERSION

    pkg = package(instance=instance, layout=layout, control=control)
    routes = pkg["information_routes"]
    required_handoffs = [
        r["route_id"]
        for r in routes
        if r["provider"] not in r["recipients"] and control != "all_info"
    ]
    spec = {
        "version": SCENARIO_VERSION,
        "scenario_id": "decision-team-" + instance + "-" + layout + "-" + control,
        "world": {
            "world_id": "decision-team",
            "actors": {actor: {} for actor in [*ROLES, "operator"]},
            "applications": ["files", "sql"],
            "publication_policy": "explicit",
            "bootstrap_grants": [
                {"actor_id": "operator", "power": "install_project", "scope": "world"}
            ],
        },
        "installer": "operator",
        "projects": [{"package": pkg}],
        "roles": [
            {
                "role_id": role,
                "actor": role,
                "project": "TEAM",
                "policy": "model",
                "config": {"task": ROLE_TASKS[role]},
            }
            for role in ROLES
        ],
        "setup": [],
        "events": [],
        "start": {"kind": "initial"},
        "boundary": {"max_opportunities": 180},
        "variation": {
            "kind": "structure",
            "xi": {"instance": instance, "layout": layout, "control": control},
            "validity_spec": {
                "spec_id": "decision-team-validity-v0.12",
                "project_id": "TEAM",
                "work_node": "TEAM::build",
                "implementer": "implementer",
                "reviewer": "reviewer",
                "required_handoff_routes": required_handoffs,
                "required_direct_reads": [{"member_id": "reviewer", "alias": "audit_basis"}],
                "allow_rejected_actions": True,
                "allow_repair": True,
                "blocked_outcome": "unknown",
            },
        },
    }
    if control == "old_versions":
        for route in routes:
            alias = route["object_alias"]
            current = basis_fixture(instance) if alias == "basis" else audit_fixture(instance)
            spec["setup"].append(
                {
                    "actor": "operator",
                    "project": "TEAM",
                    "tool": "write_object",
                    "arguments": {"alias": alias, "data": current},
                }
            )
    return copy.deepcopy(spec)
