"""D1 actual three-member rule witnesses; never evidence of model class support.

All member choices below use only their captured public ports. Host state is used
solely for episode snapshots, delivery-event recording and post-run checks.
"""

import argparse
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.episode import assess_historical_episode, begin_episode, finish_episode
from proworksim.experience import ExperienceRecorder, capture_port
from proworksim.scenarios import build_scenario, initial_business_state
from proworksim.storage import digest, json_bytes
from proworksim.templates.decision_team import (
    PERIOD,
    ROLES,
    ROLE_TASKS,
    scenario_spec,
    witness_code,
)

PROTOCOL = {
    "version": "decision-team-witness-v0.12",
    "origin": "rule_witness",
    "base_instances": ["orders_a", "orders_b"],
    "layouts": ["split_a", "split_b"],
    "methods": ["proactive", "requested"],
    "controls": ["late", "old_versions", "unavailable", "all_info", "review_repair"],
    "model_support": False,
    "data_origin": "Research-constructed six-transaction/three-customer instances reusing Jaffle-style SQL interfaces and the existing bounded DuckDB executor. These are not slices of the pinned upstream seeds and add no independent public source.",
    "method_location": "Only this explicitly labeled program schedule selects proactive/requested. Scenario package, same-xi initial business state and member tasks are identical across both witnesses; model tasks never select a class.",
    "information": "Manual provider must really read and select exact evidence; request_information never chooses it or schedules an automatic provider answer. Transport delay is environment behavior. Read-only evidence holders have scoped provide delegation.",
    "review": "Rule reviewer computes finite checks from its actually read independent audit basis and data; it never calls the independent evaluator. The optional repair control emits a real located issue and reassesses a new exact submission.",
    "blocked": "Only retired evidence leads to a real unavailable response and incomplete work. Validity remains unknown; this is not a completed positive trajectory or reallocation candidate.",
    "normalization": "initial_business_state removes only world instance/branch identities, wall durations, receipt/transition diagnostic digests. Logical clock, business versions, reads, messages, rights, ordering, calls and byte payloads remain.",
    "limits": [
        "No API, model generation, GPU or training",
        "One synthetic finite SQL task family",
        "Program feasibility does not establish any current model distribution support",
        "No full dbt, enterprise process or arbitrary SQL/shell capability",
    ],
}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def ref(value):
    return {
        "object_id": value.get("object_id", value.get("artifact_id")),
        "version_id": value["version_id"],
    }


def records(table):
    names = [c["name"] for c in table["columns"]]
    return [dict(zip(names, row)) for row in table["rows"]]


class PublicWitness:
    """Independent port capture plus retained experience; no policy state reads."""

    def __init__(self, world):
        self._world = world
        self.captured = {role: [] for role in ROLES}
        self.ports = {
            role: capture_port(world.session(role, "TEAM"), self.captured[role]) for role in ROLES
        }
        self.recorder = ExperienceRecorder()
        self.event_index = len(world.state["event_history"])

    def perform(self, role, operation, *args, **kwargs):
        value = getattr(self.ports[role], operation)(*args, **kwargs)
        event = self.captured[role][-1]
        self.recorder.record(event["kind"], event["payload"], role)
        for event in self._world.state["event_history"][self.event_index :]:
            self.recorder.record("environment_event", event)
        self.event_index = len(self._world.state["event_history"])
        return value

    def observe(self, role):
        return self.perform(role, "observe")

    def call(self, role, action, **kwargs):
        response = self.perform(role, "call", action, **kwargs)
        if not response["ok"]:
            raise ValueError(
                {"member": role, "action": action, "arguments": kwargs, "actual_response": response}
            )
        return response["result"]

    def read(self, role, alias, version_id=None):
        return self.call(
            role,
            "read_object",
            alias=alias,
            work_id="TEAM::build",
            **({"version_id": version_id} if version_id else {}),
        )

    def applicable(self, role, alias):
        # Holder considers each version it can actually see; no host truth/ref is
        # selected on its behalf, and reading a retired edition does not upgrade it.
        obs = self.observe(role)
        oid = obs["workspaces"]["TEAM"][alias]
        chosen = None
        for version in obs["objects"][oid]["versions"]:
            document = self.read(role, alias, version)
            data = document["data"]
            meta = records(data["tables"]["basis_meta"])[0] if alias == "basis" else data
            if meta.get("period") == PERIOD and meta.get("edition") == "approved":
                chosen = document
        return chosen


def communicate(witness, method, *, all_info=False):
    obs = witness.observe("implementer")
    routes = obs["information_routes"]
    if isinstance(routes, dict):
        routes = list(routes.values())
    for route in routes:
        alias, sender, recipients = route["route_id"], route["provider"], route["recipients"]
        if all_info or sender in recipients:
            continue
        recipient = recipients[0]
        request_id = None
        if method == "requested":
            request_id = witness.call(
                recipient, "request_information", route_id=alias, work_id="TEAM::build"
            )["request_id"]
            witness.call(sender, "read_messages")
        selected = witness.applicable(sender, alias)
        if selected is None and request_id is None:
            raise ValueError("Proactive positive witness requires actually available evidence")
        args = {
            "route_id": alias,
            "work_id": "TEAM::build",
            "handoff_key": "selected-" + alias,
            "body": "The selected evidence is approved for the public work period."
            if selected
            else "Only retired-period material is held; no applicable approved evidence can be provided.",
        }
        if request_id:
            args["request_id"] = request_id
        if selected:
            args["reference"] = ref(selected["reference"])
        else:
            args["status"] = "unavailable"
        sent = witness.call(sender, "handoff_information", **args)
        # A real public wait models delivery latency; no state injection or
        # alternate event pump is used. The same protocol handles each delay.
        for _ in range(18):
            if sent["handoff_id"] in witness.observe(recipient)["handoffs"]:
                break
            witness.call(recipient, "wait", ticks=1)
        else:
            raise ValueError("Declared witness transport budget exhausted")
        witness.call(recipient, "read_messages")
        if selected is None:
            return False
    return True


def expected_by_reviewer(data, audit):
    """Transparent finite colleague calculation, independent of domain evaluator."""
    if audit["period"] != PERIOD or audit["edition"] != "approved":
        raise ValueError("Reviewer has no applicable audit basis")
    totals = {
        row["customer_id"]: {"money": 0, "orders": set()}
        for row in records(data["tables"]["customers"])
    }
    for payment in records(data["tables"]["transactions"]):
        if payment["period"] == audit["period"] and payment["status"] in audit["allowed_statuses"]:
            customer = totals[payment["customer_id"]]
            customer["money"] += payment["amount"] * audit["amount_factor"]
            customer["orders"].add(payment["order_id"])
    return {key: (value["money"], len(value["orders"])) for key, value in totals.items()}


def reviewer_inspects(witness, sid):
    submission = witness.call(
        "reviewer", "inspect_submission", work_id="TEAM::build", submission_id=sid
    )
    obs = witness.observe("reviewer")
    by_oid = {oid: alias for alias, oid in obs["workspaces"]["TEAM"].items()}
    files = {}
    for oid, version in submission["artifact_versions"].items():
        alias = by_oid[oid]
        files[alias] = witness.read("reviewer", alias, version)
    return files


def build_and_submit(witness, source_refs, *, wrong=False):
    code = witness_code()
    if wrong:
        code["models"][0]["sql"] = code["models"][0]["sql"].replace(
            "COUNT(DISTINCT order_id)", "COUNT(order_id)"
        )
    witness.call(
        "implementer",
        "write_object",
        alias="code",
        data=code,
        dependencies=list(source_refs.values()),
        work_id="TEAM::build",
    )
    built = witness.call(
        "implementer",
        "sql_build",
        work_id="TEAM::build",
        code_alias="code",
        output_alias="result",
        input_aliases=["data", "basis"],
    )
    if built["execution_status"] != "success":
        raise ValueError(built)
    witness.read("implementer", "result")
    preflight = witness.call(
        "implementer", "preflight_submission", work_id="TEAM::build", artifacts=["code", "result"]
    )
    if preflight.get("structurally_ready") is not True:
        raise ValueError({"preflight": preflight})
    submitted = witness.call(
        "implementer", "submit", work_id="TEAM::build", artifacts=["code", "result"]
    )
    return submitted["submission_id"]


def complete_work(witness, *, repair=False):
    source_refs = {}
    for alias in ("data", "basis"):
        document = (
            witness.read("implementer", alias)
            if alias == "data"
            else witness.applicable("implementer", alias)
        )
        if document is None:
            raise ValueError("Implementer lacks applicable actual evidence")
        source_refs[alias] = ref(document["reference"])
        witness.call(
            "implementer",
            "adopt",
            alias=alias,
            **source_refs[alias],
            policy="fixed",
            work_ids=["TEAM::build"],
        )
    audit = witness.applicable("reviewer", "audit_basis")
    public = witness.read("reviewer", "data")
    expected = expected_by_reviewer(public["data"], audit["data"])
    sid = build_and_submit(witness, source_refs, wrong=repair)
    files = reviewer_inspects(witness, sid)
    actual_rows = records(files["result"]["data"]["tables"]["metrics"])
    wrong_rows = [
        i
        for i, row in enumerate(actual_rows)
        if expected.get(row["customer_id"]) != (row["revenue_cents"], row["order_count"])
    ]
    issue = None
    if wrong_rows:
        if not repair:
            raise ValueError("Program witness reviewer found unexpected real business defect")
        issue = witness.call(
            "reviewer",
            "raise_issue",
            work_id="TEAM::build",
            submission_id=sid,
            issue_key="distinct-orders",
            **ref(files["result"]["reference"]),
            locator=["tables", "metrics", "rows", wrong_rows[0]],
            description="This customer count counts transaction rows instead of distinct qualifying orders under the independently read audit basis.",
            evidence=[ref(audit["reference"]), ref(public["reference"])],
        )
        witness.call(
            "implementer",
            "withdraw",
            work_id="TEAM::build",
            submission_id=sid,
            reason="Repair the actual located distinct-order review",
        )
        sid = build_and_submit(witness, source_refs)
        corrected = witness.read("implementer", "result")
        response = witness.call(
            "implementer",
            "respond_issue",
            issue_id=issue["issue_id"],
            response_key="distinct-orders-repaired",
            submission_id=sid,
            body="The new actual build counts distinct qualifying order IDs.",
            evidence=[ref(corrected["reference"])],
        )
        files = reviewer_inspects(witness, sid)
        rows = records(files["result"]["data"]["tables"]["metrics"])
        if {r["customer_id"]: (r["revenue_cents"], r["order_count"]) for r in rows} != expected:
            raise ValueError("Reviewer rejects incorrect repair")
        witness.call(
            "reviewer",
            "decide_issue",
            issue_id=issue["issue_id"],
            response_id=response["response_id"],
            decision_key="actual-repair-checked",
            decision="accept_fix",
            reason="Read new fixed code/result and checked distinct-order semantics against actual audit evidence.",
        )
    elif repair:
        raise ValueError("Declared count error failed to trigger actual reviewer finding")
    witness.call("reviewer", "approve", work_id="TEAM::build", submission_id=sid)
    return {"submission_id": sid, "issue_id": issue["issue_id"] if issue else None}


def run_witness(
    folder,
    *,
    instance="orders_a",
    layout="split_a",
    method="proactive",
    control="base",
    repair=False,
):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    if method not in PROTOCOL["methods"]:
        raise ValueError("Unknown program witness schedule")
    source_before = code_identity()
    spec = scenario_spec(instance=instance, layout=layout, control=control)
    write(folder / "scenario.json", spec)
    deployment = build_scenario(spec, folder / "world")
    if deployment.status != "ready":
        raise ValueError(deployment.diagnostics)
    world = deployment.world
    initial = digest(json_bytes(initial_business_state(world)))
    witness = PublicWitness(world)
    members = {
        role: {
            "actor_id": role,
            "project_id": "TEAM",
            "origin": "rule",
            "policy_id": "finite-decision-team-witness-v0.12",
        }
        for role in ROLES
    }
    policies = {
        role: {
            "implementation": "scripts.decision_team_experiment.PublicWitness",
            "config": {"origin": "rule", "method": method, "repair": repair},
        }
        for role in ROLES
    }
    begin_episode(
        world,
        folder / "episode",
        experience=witness.recorder.snapshot(),
        work_ids=["TEAM::build"],
        work_nodes=["TEAM::build"],
        scenario=spec,
        policies=policies,
    )
    completion, failure = {}, None
    try:
        for role in ROLES:
            witness.perform(role, "tools")
            witness.observe(role)
        available = communicate(witness, method, all_info=control == "all_info")
        completion = complete_work(witness, repair=repair) if available else {}
        status = "completed" if available else "information_unavailable"
    except Exception as error:
        status = "witness_error"
        failure = {"type": type(error).__name__, "message": str(error)}
    finish_episode(
        world,
        folder / "episode",
        experience=witness.recorder.snapshot(),
        termination={"status": status, "program_witness": True, "model_support": False},
    )
    write(folder / "experience.json", witness.recorder.snapshot())
    write(folder / "independent-capture.json", witness.captured)
    assessment = assess_historical_episode(folder / "episode")
    write(folder / "assessment.json", assessment)
    from proworksim.team_validity import assess_team_validity

    validity = assess_team_validity(
        folder / "episode",
        members=members,
        independent_capture=witness.captured,
        spec=spec["variation"]["validity_spec"],
    )
    write(folder / "validity.json", validity)
    captures_match = all(
        witness.captured[role]
        == [
            {"kind": event["kind"], "payload": event["payload"]}
            for event in witness.recorder.events
            if event.get("worker_id") == role
            and event["kind"] in {"tool_call", "public_tools", "public_observation"}
        ]
        for role in ROLES
    )
    report = {
        "protocol": PROTOCOL["version"],
        "origin": "rule_witness",
        "model_support": False,
        "xi": spec["variation"]["xi"],
        "private_program_schedule": method,
        "repair": repair,
        "scenario_sha256": digest(json_bytes(spec)),
        "role_tasks_sha256": digest(json_bytes(ROLE_TASKS)),
        "initial_business_state_sha256": initial,
        "status": status,
        "failure": failure,
        **completion,
        "capture_matches_retained": captures_match,
        "assessment": assessment,
        "validity": validity,
        "actual_member_actions": {
            role: sum(
                e["kind"] == "tool_call" and e.get("worker_id") == role
                for e in witness.recorder.events
            )
            for role in ROLES
        },
        "handoffs": copy.deepcopy(world.state["handoffs"]),
        "environment_events": copy.deepcopy(world.state["event_history"]),
        "source_before": source_before,
        "source_after": code_identity(),
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": {
            name: {"path": name, "sha256": digest((folder / name).read_bytes())}
            for name in (
                "scenario.json",
                "experience.json",
                "independent-capture.json",
                "assessment.json",
                "validity.json",
                "episode/manifest.json",
            )
        },
    }
    expected_status = "information_unavailable" if control == "unavailable" else "completed"
    expected_handoffs = spec["variation"]["validity_spec"]["required_handoff_routes"]
    report["checks"] = {
        "public_port_capture_equals_retained": captures_match,
        "expected_actual_termination": status == expected_status,
        "independent_validity_or_declared_unknown": validity["value"]
        is (None if control == "unavailable" else True),
        "real_manual_choice_for_each_required_route": all(
            any(
                h["route_id"] == route
                and h["origin"] == "member_action"
                and (bool(h["request_id"]) == (method == "requested"))
                for h in world.state["handoffs"].values()
            )
            for route in expected_handoffs
        ),
        "no_automatic_provider_reply_or_model_claim": not any(
            e["kind"] == "project_reply" for e in world.state["event_history"]
        )
        and report["model_support"] is False,
    }
    write(folder / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    write(args.output / "protocol.json", PROTOCOL)
    cases = [
        {"instance": instance, "layout": layout, "method": method}
        for instance in PROTOCOL["base_instances"]
        for layout in PROTOCOL["layouts"]
        for method in PROTOCOL["methods"]
    ]
    cases.extend(
        {"control": control, "method": "requested" if control == "unavailable" else "proactive"}
        for control in ["late", "old_versions", "unavailable", "all_info"]
    )
    cases.append({"repair": True, "method": "requested"})

    def run(index_case):
        index, case = index_case
        return run_witness(args.output / f"case-{index:02d}", **case)

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        reports = list(pool.map(run, enumerate(cases)))
    pairs = []
    for instance in PROTOCOL["base_instances"]:
        for layout in PROTOCOL["layouts"]:
            pair = [
                r
                for r in reports
                if r["xi"] == {"instance": instance, "layout": layout, "control": "base"}
                and not r["repair"]
            ]
            pairs.append(
                {
                    "instance": instance,
                    "layout": layout,
                    "identical_initial_business_state": len(
                        {r["initial_business_state_sha256"] for r in pair}
                    )
                    == 1,
                    "identical_scenario_and_role_tasks": len(
                        {(r["scenario_sha256"], r["role_tasks_sha256"]) for r in pair}
                    )
                    == 1,
                }
            )
    checks = [value for report in reports for value in report["checks"].values()]
    checks.extend(
        pair[key]
        for pair in pairs
        for key in ["identical_initial_business_state", "identical_scenario_and_role_tasks"]
    )
    summary = {
        "protocol": PROTOCOL,
        "cases": reports,
        "same_xi_pairs": pairs,
        "checks_passed": sum(checks),
        "checks_total": len(checks),
        "positive_rule_completed": sum(r["status"] == "completed" for r in reports),
        "current_model_class_support": "not measured by these program witnesses",
    }
    write(args.output / "report.json", summary)
    print(
        json.dumps(
            {
                "cases": len(reports),
                "completed": summary["positive_rule_completed"],
                "checks_passed": sum(checks),
                "checks_total": len(checks),
                "pairs": pairs,
            },
            ensure_ascii=False,
        )
    )
    if not all(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
