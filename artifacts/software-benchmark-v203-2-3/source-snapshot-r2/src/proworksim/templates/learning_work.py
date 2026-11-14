"""Explicit finite learning situations in one existing synthetic SQL family.

Catalog facts are host initialization, never suggested actions or numeric answers.
All derived pools belong to one development source family. Locked usages only
measure within-family fact/rule/information changes; they are not new sources.
"""

import copy
from pathlib import Path

from ..audit import code_identity
from ..experience import ExperienceRecorder, capture_port
from ..scenarios import build_scenario, initial_business_state, save_deployment
from ..storage import digest, json_bytes
from .decision_team import ROLES, initial_code, package, scenario_spec
from .online_work import PreparedOnlineCase, ROLE_TASKS, TASKS, TERMS

VERSION = "learning-work-v0.14"
REWARD_VERSION = "online-work-reward-v0.14"
LIMITS = {"provider": 6, "implementer": 12, "reviewer": 14}
TASK_LIMITS = {"handoff": 4, "implement": 10, "review": 8}
# These are separate declared factors, never choices inferred from seed parity.
FACTS = {
    "train": [
        {"period": "2025-01", "allowed_statuses": ["completed"], "amount_factor": 1,
         "deduplication": "distinct_orders", "order_min_inclusive": 10, "order_max_exclusive": 50,
         "basis_provider": "provider", "audit_provider": "reviewer", "prepared_submission": "correct",
         "amounts": [110, 70, 90, 60, 120, 80, 40, 30], "old_versions": False},
        {"period": "2025-02", "allowed_statuses": ["completed", "returned"], "amount_factor": 2,
         "deduplication": "distinct_orders", "order_min_inclusive": 20, "order_max_exclusive": 60,
         "basis_provider": "provider", "audit_provider": "reviewer", "prepared_submission": "wrong_count",
         "amounts": [210, 60, 130, 90, 80, 150, 70, 20], "old_versions": False},
    ],
    "development": [
        {"period": "2025-03", "allowed_statuses": ["completed", "returned"], "amount_factor": 1,
         "deduplication": "distinct_orders", "order_min_inclusive": 30, "order_max_exclusive": 70,
         "basis_provider": "provider", "audit_provider": "reviewer", "prepared_submission": "wrong_count",
         "amounts": [160, 40, 110, 70, 130, 90, 50, 25], "old_versions": False},
        {"period": "2025-04", "allowed_statuses": ["completed"], "amount_factor": 2,
         "deduplication": "distinct_orders", "order_min_inclusive": 40, "order_max_exclusive": 80,
         "basis_provider": "provider", "audit_provider": "reviewer", "prepared_submission": "correct",
         "amounts": [250, 80, 120, 140, 180, 100, 60, 35], "old_versions": False},
    ],
    "locked_facts": [
        {"period": "2025-05", "allowed_statuses": ["returned"], "amount_factor": 2,
         "deduplication": "distinct_orders", "order_min_inclusive": 50, "order_max_exclusive": 90,
         "basis_provider": "provider", "audit_provider": "reviewer", "prepared_submission": "correct",
         "amounts": [175, 55, 95, 65, 155, 85, 45, 15], "old_versions": True},
        {"period": "2025-06", "allowed_statuses": ["completed", "returned"], "amount_factor": 1,
         "deduplication": "distinct_orders", "order_min_inclusive": 60, "order_max_exclusive": 100,
         "basis_provider": "provider", "audit_provider": "reviewer", "prepared_submission": "wrong_count",
         "amounts": [225, 75, 145, 105, 165, 115, 95, 55], "old_versions": False},
    ],
    "locked_information": [
        {"period": "2025-07", "allowed_statuses": ["completed"], "amount_factor": 1,
         "deduplication": "distinct_orders", "order_min_inclusive": 70, "order_max_exclusive": 110,
         "basis_provider": "reviewer", "audit_provider": "provider", "prepared_submission": "wrong_count",
         "amounts": [185, 65, 125, 85, 145, 95, 75, 45], "old_versions": False},
        {"period": "2025-08", "allowed_statuses": ["completed", "returned"], "amount_factor": 2,
         "deduplication": "distinct_orders", "order_min_inclusive": 80, "order_max_exclusive": 120,
         "basis_provider": "reviewer", "audit_provider": "provider", "prepared_submission": "correct",
         "amounts": [235, 95, 155, 115, 175, 125, 85, 65], "old_versions": True},
    ],
    "locked_rules": [
        {"period": "2025-09", "allowed_statuses": ["completed", "returned"], "amount_factor": 3,
         "deduplication": "transaction_rows", "order_min_inclusive": 90, "order_max_exclusive": 130,
         "basis_provider": "provider", "audit_provider": "reviewer", "prepared_submission": "correct",
         "amounts": [195, 85, 135, 95, 165, 105, 65, 35], "old_versions": False},
        {"period": "2025-10", "allowed_statuses": ["completed"], "amount_factor": 3,
         "deduplication": "transaction_rows", "order_min_inclusive": 100, "order_max_exclusive": 140,
         "basis_provider": "provider", "audit_provider": "reviewer", "prepared_submission": "wrong_count",
         "amounts": [245, 105, 165, 125, 195, 135, 95, 75], "old_versions": False},
    ],
}


def registry():
    situations = []
    for pool, declarations in FACTS.items():
        for position, facts in enumerate(declarations):
            for task in TASKS:
                active = ({"handoff": [facts["basis_provider"]], "implement": ["implementer"],
                           "review": ["reviewer"], "chain": list(ROLES)})[task]
                situations.append({
                    "version": VERSION, "case_id": f"{pool}-v14-f{position}-{task}",
                    "pool": pool, "split": "development", "task": task, "fact_position": position,
                    "family": "constructed-finite-team-sql", "case_share": 0.25,
                    "business_facts": copy.deepcopy(facts), "active_roles": active,
                    "role_decision_limits": {role: LIMITS[role] if task == "chain" else TASK_LIMITS[task] for role in active},
                    "prepared_submission": facts["prepared_submission"] if task == "review" else None,
                })
    return {
        "version": VERSION, "source_family_count": 1, "independent_test_source_families": [],
        "source_relationship": "All pools derive from the existing constructed Jaffle-style SQL family. New rules/holders/facts are within-family conditions, not independent source projects.",
        "split_rule": "The source family is development. train updates parameters; development diagnoses; locked_facts/locked_information/locked_rules are predeclared internal evaluation usages. Old eight v0.13 cases are historical only.",
        "fixed_tasks_per_window": list(TASKS), "fixed_case_shares": [0.25] * 4,
        "facts_are_explicit": True, "situations": situations,
    }


def controlled_pair():
    """Same public goal/data/layout, two privately different rule worlds."""
    base = registry()["situations"][3]
    result = []
    for label, statuses, factor in [("a", ["completed"], 1), ("b", ["completed", "returned"], 2)]:
        case = copy.deepcopy(base)
        case.update(case_id="controlled-v14-" + label + "-chain", pool="controlled_development")
        case["business_facts"].update(allowed_statuses=statuses, amount_factor=factor)
        result.append(case)
    return result


def case_spec(case_id, *, catalog=None):
    declared = registry() if catalog is None else catalog
    rows = [row for row in declared["situations"] + (controlled_pair() if catalog is None else [])
            if row["case_id"] == case_id]
    if len(rows) != 1:
        raise ValueError("Unknown or duplicate predeclared learning situation")
    return copy.deepcopy(rows[0])


def reward_spec(case):
    facts, task = case["business_facts"], case["task"]
    return {
        "version": REWARD_VERSION, "reward_id": f"online-{task}-v0.14", "task": task,
        "project_id": "TEAM", "work_id": "TEAM::build", "period": facts["period"],
        "basis_provider": facts["basis_provider"], "active_roles": list(case["active_roles"]),
        "terms": [{"term_id": name, "weight": weight, "public_requirement": text}
                  for name, weight, text in TERMS[task]],
        "credit_rule": "Each outcome earns credit once from exact current-episode receipts and independently checked business work. Repeated actions and approvals alone add nothing.",
        "unknown_rule": "Unavailable historical evidence or evaluator/service fault yields null; real tool refusals and unmet outcomes remain evaluable failures.",
        "preparation_credit": False,
    }


def _table(columns, rows):
    return {"columns": [{"name": name, "type": kind} for name, kind in columns], "rows": rows}


def _basis(facts, *, old=False):
    return {"tables": {
        "basis_meta": _table([
            ("period", "VARCHAR"), ("edition", "VARCHAR"), ("amount_factor", "BIGINT"),
            ("deduplication", "VARCHAR"), ("order_min_inclusive", "BIGINT"),
            ("order_max_exclusive", "BIGINT"),
        ], [["2024-12" if old else facts["period"], "retired" if old else "approved",
             facts["amount_factor"], facts["deduplication"], facts["order_min_inclusive"],
             facts["order_max_exclusive"]]]),
        "allowed_statuses": _table([("status", "VARCHAR")], [[s] for s in facts["allowed_statuses"]]),
    }, "note": "The applicable approved row defines the actual business rules; this file has no expected result or SQL solution."}


def _audit(facts, *, old=False):
    return {key: copy.deepcopy(facts[key]) for key in (
        "period", "allowed_statuses", "amount_factor", "deduplication",
        "order_min_inclusive", "order_max_exclusive"
    )} | {"period": "2024-12" if old else facts["period"],
          "edition": "retired" if old else "approved",
          "release_checks": ["Read the exact fixed code/result, data and applicable independent audit basis.",
                             "Keep every public customer, including zero rows; apply period, statuses and half-open order bounds before aggregation.",
                             "Multiply eligible amounts by amount_factor; count according to the stated deduplication rule."],
          "note": "Independent business conditions; no numeric answer or executable solution."}


def _package(case):
    facts = case["business_facts"]
    layout = "split_a" if facts["basis_provider"] == "provider" else "split_b"
    pkg = package(layout=layout)
    objects = {obj["alias"]: obj for obj in pkg["objects"]}
    lo, hi, period = facts["order_min_inclusive"], facts["order_max_exclusive"], facts["period"]
    # Exact boundary rows, duplicates, alternate statuses, another period, and
    # a customer with no qualifying rows are present in each declared world.
    descriptors = [
        [lo, 1, "completed", period], [lo, 1, "completed", period],
        [lo + 1, 2, "returned", period], [hi - 1, 2, "completed", period],
        [lo - 1, 1, "completed", period], [hi, 3, "completed", period],
        [lo + 2, 3, "pending", period], [lo + 3, 3, "completed", "2024-11"],
    ]
    data = objects["data"]["data"]
    data["tables"]["customers"]["rows"] = [[1], [2], [3], [4]]
    data["tables"]["transactions"]["rows"] = [row + [amount] for row, amount in zip(descriptors, facts["amounts"])]
    objects["basis"]["data"] = _basis(facts, old=facts["old_versions"])
    objects["audit_basis"]["data"] = _audit(facts, old=facts["old_versions"])
    work = pkg["works"][0]
    work["goal"] = f"Implement and independently review the declared customer metrics contract for {period}."
    req = work["requirements"]
    req["reporting_period"] = period
    req["online_scope"] = reward_spec(case)
    req["public_format"]["output"] = (
        "Exactly one metrics table (customer_id,revenue_cents,order_count), one row per data.customers ID, including zeros. "
        "Use the approved basis for the reporting period. Include only transactions of that period and allowed_statuses, "
        "with order_min_inclusive <= order_id < order_max_exclusive. Sum every eligible amount times amount_factor. "
        "deduplication='distinct_orders' counts distinct eligible order_id; 'transaction_rows' counts eligible transaction rows. "
        "Do not infer the rule values without actually obtaining the applicable basis."
    )
    work["deliverable_contract"]["content_checks"][0]["period"] = period
    pkg["provenance"] = {"kind": "synthetic", "source_evidence_refs": ["constructed-finite-team-sql"],
                         "note": "Explicit new within-family learning facts; no worker receives a solution or expected numeric table."}
    return pkg


def scenario(case):
    facts, task = case["business_facts"], case["task"]
    spec = scenario_spec(layout="split_a" if facts["basis_provider"] == "provider" else "split_b")
    spec["scenario_id"] = case["case_id"]
    spec["projects"] = [{"package": _package(case)}]
    spec["roles"] = []
    for role in case["active_roles"]:
        description = ROLE_TASKS[task].get(role, ROLE_TASKS["handoff"]["provider"])
        spec["roles"].append({"role_id": role, "actor": role, "project": "TEAM", "policy": "model",
                              "config": {"task": description}})
    spec["boundary"] = {"max_opportunities": sum(case["role_decision_limits"].values()) + len(case["active_roles"])}
    validity = spec["variation"]["validity_spec"]
    validity["read_operations"] = ["read_object", "read_alias", "read_version"]
    spec["variation"] = {"kind": "structure", "online_case": copy.deepcopy(case),
                         "online_reward": reward_spec(case),
                         "support_scope": "Exact scenario, shared actor identity, collection window and protocol; no cross-window or cross-layout pooling."}
    if task == "chain":
        spec["variation"]["validity_spec"] = validity
    if facts["old_versions"]:
        spec["setup"] = [{"actor": "operator", "project": "TEAM", "tool": "write_object",
                          "arguments": {"alias": alias, "data": data}}
                         for alias, data in [("basis", _basis(facts)), ("audit_basis", _audit(facts))]]
    return spec


def witness_code(*, wrong=False, old_rules=False):
    """CPU feasibility witness only; never passed to the learning actor."""
    code = initial_code()
    bounds = "" if old_rules else " AND t.order_id>=b.order_min_inclusive AND t.order_id<b.order_max_exclusive"
    count = "COUNT(DISTINCT order_id)" if old_rules else (
        "CASE WHEN MAX(deduplication)='transaction_rows' THEN COUNT(*) ELSE COUNT(DISTINCT order_id) END"
    )
    if wrong:
        count = "(" + count + ")+1"
    code["models"][0]["sql"] = (
        "WITH eligible AS (SELECT t.customer_id,t.order_id,t.amount*b.amount_factor AS amount,b.deduplication "
        "FROM transactions t JOIN allowed_statuses s ON t.status=s.status CROSS JOIN basis_meta b "
        "WHERE t.period=b.period AND b.edition='approved'" + bounds + "),a AS (SELECT customer_id,"
        "SUM(amount)::BIGINT AS revenue_cents,(" + count + ")::BIGINT AS order_count FROM eligible GROUP BY customer_id) "
        "SELECT c.customer_id,COALESCE(a.revenue_cents,0)::BIGINT AS revenue_cents,COALESCE(a.order_count,0)::BIGINT AS order_count "
        "FROM customers c LEFT JOIN a ON c.customer_id=a.customer_id"
    )
    return code


def build_learning_case(case, root):
    if isinstance(case, str):
        case = case_spec(case)
    case = copy.deepcopy(case)
    if case != case_spec(case["case_id"]):
        raise ValueError("Learning case must match its predeclared catalog")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(scenario(case), root / "world")
    if deployment.status != "ready":
        raise ValueError(deployment.diagnostics)
    world = deployment.world
    captured = {role: [] for role in ROLES}
    ports = {role: capture_port(world.session(role, "TEAM"), captured[role]) for role in ROLES}
    recorder = ExperienceRecorder()
    before = digest(json_bytes(initial_business_state(world)))
    event_offset = len(world.state["event_history"])
    source = code_identity()

    def call(actor, tool, **arguments):
        nonlocal event_offset
        response = ports[actor].call(tool, request_key=f"learning-preparation-{case['case_id']}-{actor}-{len(recorder.events)}", **arguments)
        recorder.record("preparation_tool_call", {"origin": "preparation", **captured[actor][-1]["payload"]}, actor)
        for event in world.state["event_history"][event_offset:]:
            recorder.record("preparation_environment_event", event)
        event_offset = len(world.state["event_history"])
        if not response["ok"]:
            raise ValueError({"preparation_rejected": tool, "actual_response": response})
        return response["result"]

    def read(actor, alias):
        return call(actor, "read_alias", alias=alias, work_id="TEAM::build")["reference"]

    def supply(alias, holder):
        reference = read(holder, alias)
        call(holder, "handoff_information", route_id=alias, work_id="TEAM::build",
             handoff_key="prepared-" + alias, reference=reference,
             body="Actual prepared source delivery; excluded from current actor credit.")

    facts = case["business_facts"]
    if case["task"] in {"implement", "review"}:
        supply("basis", facts["basis_provider"])
        for alias in ("data", "basis"):
            reference = read("implementer", alias)
            call("implementer", "adopt", alias=alias, **reference, policy="fixed", work_ids=["TEAM::build"])
    if case["task"] == "review":
        if facts["audit_provider"] != "reviewer":
            supply("audit_basis", facts["audit_provider"])
        refs = [{"object_id": row["object_id"], "version_id": row["version_id"]}
                for row in world.state["adoptions"].values()]
        call("implementer", "write_object", alias="code", work_id="TEAM::build", dependencies=refs,
             data=witness_code(wrong=case["prepared_submission"] == "wrong_count"))
        built = call("implementer", "sql_build", work_id="TEAM::build", code_alias="code",
                     output_alias="result", input_aliases=["data", "basis"])
        if built["execution_status"] != "success":
            raise ValueError("Declared prepared SQL did not execute")
        call("implementer", "submit", work_id="TEAM::build", artifacts=["code", "result"])
    prefix = {"version": VERSION, "origin": "preparation", "credited_to_current_actor": False,
              "case_id": case["case_id"], "executed": bool(recorder.events),
              "initial_business_state_sha256": before,
              "prepared_business_state_sha256": digest(json_bytes(initial_business_state(world))),
              "experience": recorder.snapshot(), "independent_capture": captured,
              "source_before": source, "source_after": code_identity()}
    (root / "preparation.json").write_bytes(json_bytes(prefix))
    (root / "scenario.json").write_bytes(json_bytes(deployment.spec))
    save_deployment(deployment)
    return PreparedOnlineCase(deployment, case, reward_spec(case), prefix)
