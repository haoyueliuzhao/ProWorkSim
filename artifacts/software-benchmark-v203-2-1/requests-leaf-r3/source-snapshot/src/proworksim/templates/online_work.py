"""Short environment tasks for online RL, with real, excluded preparation.

The fixed mixture is an environment curriculum, not demonstration trajectories.
All facts are synthetic within the existing finite SQL family; split labels are
host registry metadata and do not assert independent-source generalization.
"""

import copy
from dataclasses import dataclass
from pathlib import Path
from random import Random

from ..audit import code_identity
from ..experience import ExperienceRecorder, capture_port
from ..scenarios import build_scenario, initial_business_state, save_deployment
from ..storage import digest, json_bytes
from .decision_team import PERIOD, ROLES, package, scenario_spec, witness_code

ONLINE_VERSION = "online-work-v0.13"
REWARD_VERSION = "online-work-reward-v0.13"
TASKS = ("handoff", "implement", "review", "chain")
ACTIVE = {
    "handoff": ["provider"],
    "implement": ["implementer"],
    "review": ["reviewer"],
    "chain": list(ROLES),
}
DECISIONS = {"provider": 4, "implementer": 8, "reviewer": 6}
TERMS = {
    "handoff": [
        (
            "read_applicable_basis",
            0.25,
            "During this episode actually read the exact approved business basis applicable to the public work period. Inherited or repeated reads add no extra credit.",
        ),
        (
            "deliver_applicable_basis",
            0.75,
            "Choose that actually read exact basis and deliver it through the manual route to the declared implementer for this exact work. One scoped delivery, not message count.",
        ),
    ],
    "implement": [
        (
            "read_exact_inputs",
            0.2,
            "During this episode read the exact data and applicable basis used by the work's adoption. Preparation's reads do not count as your new work.",
        ),
        (
            "correct_actual_build",
            0.3,
            "Create a new actual SQL build whose result independently satisfies the public business contract, using the exact approved adopted inputs.",
        ),
        (
            "correct_fixed_submission",
            0.5,
            "Submit this episode's independently correct actual code and result with exact source provenance. Review is outside this short episode's responsibility.",
        ),
    ],
    "review": [
        (
            "read_review_basis",
            0.25,
            "During this episode inspect the original pending submission and read its exact code/result, public data, and applicable independent audit basis before judgment.",
        ),
        (
            "correct_review_decision",
            0.75,
            "For the original fixed submission, approve only if independently correct, or raise a blocking issue located at a real wrong result cell/row with the relevant exact audit/data evidence. A made-up issue or approval alone earns no decision credit.",
        ),
    ],
    "chain": [
        (
            "deliver_applicable_basis",
            0.2,
            "Actually read, select and deliver the applicable exact basis through the manual route for this work.",
        ),
        (
            "correct_fixed_submission",
            0.3,
            "Read and adopt the exact inputs, produce a real independently correct SQL result, and fix it in a new code/result submission.",
        ),
        (
            "correct_review_decision",
            0.5,
            "Read the exact fixed submission and independent applicable audit/data evidence, then genuinely approve independently correct work. Full reward requires the delivery and implementation obligations too.",
        ),
    ],
}
ROLE_TASKS = {
    "handoff": {
        "provider": "Fulfill the public short responsibility of obtaining applicable business evidence and handing it to its declared recipient. Judge available versions yourself. The public online_scope states the exact reward outcomes; it does not select evidence or prescribe a communication order."
    },
    "implement": {
        "implementer": "Fulfill the public short implementation responsibility from the legally prepared work state. Choose your SQL edits and checks, retain exact adopted inputs, and submit actual code/result. Review belongs to a later responsibility; your task and outcome terms are in online_scope."
    },
    "review": {
        "reviewer": "Independently judge the original current pending submission using the public goal and your evidence. It may be correct or incorrect. Choose justified approval or a located blocking issue yourself. The public online_scope states the finite outcome contract, not the answer."
    },
    "chain": {
        "provider": "Fulfill your information-holder responsibility in the short team work. Read the visible goal, versions and manual routes, choose applicable evidence and how to coordinate. Read the public online_scope reward contract.",
        "implementer": "Fulfill your implementation responsibility in the short team work. Use the publicly declared goal and actually accessible evidence to produce and submit real SQL work. Coordinate as needed; read online_scope for the outcome contract.",
        "reviewer": "Independently review the short team's actual fixed submission against your applicable audit evidence and the public goal. Raise real located issues or approve supported work. Read online_scope for the outcome contract.",
    },
}


def registry():
    """Predeclared train/development/locked-test split before any outcomes."""
    situations = []
    for label, usage, base in [
        ("train", "online_train", 1300),
        ("development", "dev_check", 2300),
        ("locked_within_family", "locked_within_family_check", 3300),
    ]:
        for window in range(2):
            for position, task in enumerate(TASKS):
                situations.append(
                    {
                        "case_id": f"{label}-w{window}-{task}",
                        "split": "development",
                        "usage": usage,
                        "window": window,
                        "position": position,
                        "task": task,
                        "facts_seed": base + window * 20 + position,
                        "layout": "split_a",
                        "family": "constructed-short-team-sql-v0.13",
                        "case_share": 0.25,
                        "active_roles": list(ACTIVE[task]),
                        "role_decision_limits": {r: DECISIONS[r] for r in ACTIVE[task]},
                        # Host-only initialization specification, never put in role prompts.
                        "prepared_submission": ("correct" if window == 0 else "wrong_count")
                        if task == "review"
                        else None,
                    }
                )
    return {
        "version": ONLINE_VERSION,
        "source_family_count": 1,
        "source_relationship": "New synthetic facts within the earlier Jaffle-style finite SQL interface family; not independent public data sources.",
        "split_rule": "This entire source/world family belongs to development. Predeclared internal usages online_train, dev_check and locked_within_family_check do not create independent source splits; locked checks remain untouched until declared evaluation.",
        "independent_test_source_families": [],
        "windows": 2,
        "fixed_tasks_per_window": list(TASKS),
        "fixed_case_shares": [0.25] * 4,
        "situations": situations,
    }


def case_spec(case_id, *, catalog=None):
    catalog = registry() if catalog is None else catalog
    rows = [r for r in catalog["situations"] if r["case_id"] == case_id]
    if len(rows) != 1:
        raise ValueError("Unknown or duplicate predeclared online situation")
    return copy.deepcopy(rows[0])


def reward_spec(case):
    task = case["task"]
    if task not in TASKS:
        raise ValueError("Unknown short work responsibility")
    return {
        "version": REWARD_VERSION,
        # Public reward names identify responsibility only. Window/split labels
        # could otherwise reveal the predeclared review preparation control.
        "reward_id": "online-" + task + "-v0.13",
        "task": task,
        "project_id": "TEAM",
        "work_id": "TEAM::build",
        "period": PERIOD,
        "active_roles": list(ACTIVE[task]),
        "terms": [
            {"term_id": name, "weight": weight, "public_requirement": text}
            for name, weight, text in TERMS[task]
        ],
        "credit_rule": "Each declared outcome is Boolean and awarded at most once for this episode's responsibility and exact versions. Counts, repeated delivery/build/submit/approve and self-created errors never create additive credit.",
        "unknown_rule": "Unavailable or changed evidence, evaluator faults or unmeasured service failure yield reward null; real tool refusals and unmet work outcomes remain evaluable failure.",
        "preparation_credit": False,
    }


def _package(case):
    pkg = package(instance="orders_a", layout=case["layout"], control="base")
    rng = Random(case["facts_seed"])
    by_alias = {a["alias"]: a for a in pkg["objects"]}
    data = by_alias["data"]["data"]
    for row in data["tables"]["transactions"]["rows"]:
        row[-1] = rng.randint(2, 19) * 100
    statuses = ["completed", "returned"] if case["facts_seed"] % 2 else ["completed"]
    factor = 1 + case["facts_seed"] % 2
    basis = by_alias["basis"]["data"]
    basis["tables"]["allowed_statuses"]["rows"] = [[s] for s in statuses]
    basis["tables"]["basis_meta"]["rows"][0][2] = factor
    audit = by_alias["audit_basis"]["data"]
    audit.update(allowed_statuses=statuses, amount_factor=factor)
    pkg["goal"] = {
        "handoff": "Obtain and deliver the applicable exact business basis for this work to its declared implementer.",
        "implement": "From the legally prepared exact inputs, implement and submit the public customer metrics contract.",
        "review": "Independently judge the original pending customer metrics submission and take a justified scoped review decision.",
        "chain": "Complete the customer metrics work, including actual evidence handoff, implementation and independent review.",
    }[case["task"]]
    spec = reward_spec(case)
    pkg["works"][0]["requirements"]["online_scope"] = copy.deepcopy(spec)
    pkg["provenance"] = {
        "kind": "synthetic",
        "source_evidence_refs": ["constructed-short-team-sql-v0.13"],
        "note": "Research-constructed short-work facts in one existing SQL family. No standard trajectory or precomputed numeric answer is supplied to the current actor.",
    }
    return pkg


def scenario(case):
    spec = scenario_spec()
    full_validity = copy.deepcopy(spec["variation"]["validity_spec"])
    full_validity["read_operations"] = ["read_object", "read_alias", "read_version"]
    spec["scenario_id"] = "online-" + case["case_id"]
    spec["projects"] = [{"package": _package(case)}]
    spec["roles"] = [
        {
            "role_id": r,
            "actor": r,
            "project": "TEAM",
            "policy": "model",
            "config": {"task": ROLE_TASKS[case["task"]][r]},
        }
        for r in ACTIVE[case["task"]]
    ]
    spec["boundary"] = {"max_opportunities": sum(DECISIONS[r] + 1 for r in ACTIVE[case["task"]])}
    spec["variation"] = {
        "kind": "structure",
        "online_case": copy.deepcopy(case),
        "online_reward": reward_spec(case),
        "support_scope": "Exact case, actor version, protocol and collection window remain distinct; no cross-window support pooling.",
    }
    if case["task"] == "chain":
        spec["variation"]["validity_spec"] = full_validity
    return spec


@dataclass
class PreparedOnlineCase:
    deployment: object
    case: dict
    reward_spec: dict
    prefix: dict

    @property
    def world(self):
        return self.deployment.world

    @property
    def scenario(self):
        return self.deployment.spec

    @property
    def active_roles(self):
        return list(self.case["active_roles"])


def build_online_case(case, root):
    """Install facts and execute the declared real prefix before begin_episode.

    ``root`` is a NEW case directory, containing world/ and preparation.json.
    The caller creates a separate episode only after this function returns and
    starts a fresh target recorder; preparation must not be copied as actor data.
    """
    if isinstance(case, str):
        case = case_spec(case)
    case = copy.deepcopy(case)
    if case != case_spec(case["case_id"]):
        raise ValueError("Online case must match the fixed registry declaration")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(scenario(case), root / "world")
    if deployment.status != "ready":
        raise ValueError(deployment.diagnostics)
    world = deployment.world
    captured = {r: [] for r in ROLES}
    ports = {r: capture_port(world.session(r, "TEAM"), captured[r]) for r in ROLES}
    recorder = ExperienceRecorder()
    before = digest(json_bytes(initial_business_state(world)))
    source_before = code_identity()
    event_index = len(world.state["event_history"])

    def call(actor, tool, **arguments):
        nonlocal event_index
        result = ports[actor].call(tool, **arguments)
        recorder.record(
            "preparation_tool_call",
            {"origin": "preparation", **captured[actor][-1]["payload"]},
            actor,
        )
        for event in world.state["event_history"][event_index:]:
            recorder.record("preparation_environment_event", event)
        event_index = len(world.state["event_history"])
        if not result["ok"]:
            raise ValueError({"preparation_rejected": tool, "actual_response": result})
        return result["result"]

    def read(actor, alias):
        return call(actor, "read_object", alias=alias, work_id="TEAM::build")

    if case["task"] in {"implement", "review"}:
        basis = read("provider", "basis")["reference"]
        call(
            "provider",
            "handoff_information",
            route_id="basis",
            work_id="TEAM::build",
            handoff_key="initial-legitimate-supply",
            body="Applicable material supplied as recorded preparation; current episode credit excludes this action.",
            reference={
                "object_id": basis.get("object_id", basis.get("artifact_id")),
                "version_id": basis["version_id"],
            },
        )
        for alias in ["data", "basis"]:
            ref = read("implementer", alias)["reference"]
            call(
                "implementer",
                "adopt",
                alias=alias,
                object_id=ref["artifact_id"],
                version_id=ref["version_id"],
                policy="fixed",
                work_ids=["TEAM::build"],
            )
    if case["task"] == "review":
        code = witness_code()
        if case["prepared_submission"] == "wrong_count":
            code["models"][0]["sql"] = code["models"][0]["sql"].replace(
                "COUNT(DISTINCT order_id)", "COUNT(order_id)"
            )
        refs = [
            {"object_id": b["object_id"], "version_id": b["version_id"]}
            for b in world.state["adoptions"].values()
        ]
        call(
            "implementer",
            "write_object",
            alias="code",
            data=code,
            work_id="TEAM::build",
            dependencies=refs,
        )
        built = call(
            "implementer",
            "sql_build",
            work_id="TEAM::build",
            code_alias="code",
            output_alias="result",
            input_aliases=["data", "basis"],
        )
        if built["execution_status"] != "success":
            raise ValueError("Declared preparation SQL execution failed")
        call("implementer", "submit", work_id="TEAM::build", artifacts=["code", "result"])
    prefix = {
        "version": ONLINE_VERSION,
        "origin": "preparation",
        "credited_to_current_actor": False,
        "case_id": case["case_id"],
        "executed": bool(recorder.events),
        "initial_business_state_sha256": before,
        "prepared_business_state_sha256": digest(json_bytes(initial_business_state(world))),
        "experience": recorder.snapshot(),
        "independent_capture": captured,
        "source_before": source_before,
        "source_after": code_identity(),
    }
    (root / "preparation.json").write_bytes(json_bytes(prefix))
    (root / "scenario.json").write_bytes(json_bytes(deployment.spec))
    save_deployment(deployment)
    return PreparedOnlineCase(deployment, case, reward_spec(case), prefix)
