"""M1/M2/M4: real World Core tools, independent expected values and raw checkpoints.

No business setup bypasses the runtime. Groups are isolated worlds and may run
in parallel. A construction failure preserves executed checks and explicitly
marks remaining protocol checks as not executed.
"""

import argparse
import copy
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core.world import WorldSpec
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.world_core import WorldCore

ACTORS = ("alice", "bob", "manager")


def bootstrap(root):
    return WorldCore.create(root, WorldSpec(
        world_id="world-core-witness", actors={actor: {} for actor in ACTORS},
        bootstrap_grants=[{"actor_id": "manager", "scope": "world", "power": power}
                          for power in ("install_project", "create_object", "publish", "share")],
    ))


def package(pid, owner="alice", reviewer="bob", policy="review"):
    grants = [
        {"actor_id": actor, "power": power, "subject": "artifact"}
        for actor in dict.fromkeys((owner, "manager"))
        for power in ("create_object", "share", "adopt")
    ]
    grants.extend([
        {"actor_id": "manager", "power": "confirm", "subject": "requirements",
         "work_nodes": ["work-1"]},
        {"actor_id": "manager", "power": "revise_requirement", "subject": "*",
         "work_nodes": ["work-1"]},
        {"actor_id": "manager", "power": "close_project"},
        {"actor_id": "manager", "power": "provide", "subject": "evidence",
         "work_nodes": ["work-1"]},
        {"actor_id": reviewer, "power": "approve", "subject": "deliverable",
         "work_nodes": ["work-1"]},
    ])
    return {
        "project_id": pid, "goal": "Deliver a finite synthetic JSON analysis",
        "participants": list(ACTORS), "objects": [],
        "works": [{
            "work_id": "work-1", "owner": owner, "goal": "Report revenue and cost",
            "approval_policy": policy, "purpose": "delivery",
            "requirement_dimension": "requirements",
            "deliverable_contract": {"min_files": 1, "max_files": 2,
                                     "allowed_roles": ["report"],
                                     "required_fields": ["revenue", "cost"]},
        }],
        "grants": grants,
        "provenance": {"kind": "synthetic", "source_evidence_refs": [],
                       "note": "Mechanism fixture, no real financial workflow claim"},
        "close_policy": {"pending_obligations": "retain"},
    }


def mustcall(session, tool, **arguments):
    result = session.call(tool, **arguments)
    if not result.get("ok"):
        raise AssertionError(f"{session.actor_id}/{session.project_id}/{tool}: {result}")
    return result["result"]


def exact_ref(created):
    return {"object_id": created["object_id"], "version_id": created["version_id"]}


def write_json(path, value):
    atomic_write(path, json_bytes(value))
    return {"path": str(path), "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}


def file_hashes(world):
    state = world.store.load()
    result = {}
    for aid, artifact in state["artifacts"].items():
        for vid in artifact["versions"]:
            result[f"versions/{aid}/{vid}"] = digest(world.store.version_path(artifact, vid).read_bytes())
        result[f"mirrors/{aid}"] = digest(world.store.current_path(artifact).read_bytes())
    return result


BUSINESS_KEYS = (
    "projects", "workspaces", "artifacts", "work_items", "work_replacements",
    "organization", "shares", "adoptions", "attestations", "condition_specs",
    "raw_condition_responses", "requests", "messages", "events", "event_history",
    "project_history", "requirement_events", "episodes", "world_workspace",
)


def business_facts(state):
    """Declared business prefix; excludes clock, observations and rejected-command journal."""
    return {key: copy.deepcopy(state.get(key)) for key in BUSINESS_KEYS}


CHECKS = {
    "M1": (
        "zero_project_world_exists", "world_material_precedes_projects", "two_projects_loaded",
        "B_event_pending_before_A_close", "A_completed_without_erasing_B",
        "A_submission_and_share_survive", "B_progresses_after_A_end",
        "C_loaded_in_same_world", "world_identity_and_actors_continuous", "logical_time_increases",
        "invalid_package_explicitly_rejected", "invalid_package_business_prefix_unchanged",
        "invalid_package_files_unchanged",
    ),
    "M2": (
        "same_names_distinct_object_and_work_identity", "A_confirmation_applies_to_A",
        "A_confirmation_does_not_apply_to_B", "share_before_denied",
        "exact_shared_version_readable", "unshared_new_version_denied", "upstream_private_not_shared",
        "B_reviewer_cannot_approve_A", "B_reviewer_can_approve_B",
        "same_project_retry_same_result", "same_project_retry_no_formal_effect",
        "same_key_other_project_independent", "forged_project_argument_rejected",
        "actor_knowledge_survives_project_switch",
    ),
    "M4": (
        "package_does_not_precreate_outputs", "new_intermediate_draft_allowed",
        "single_file_delivery_needs_no_external_review", "single_file_content_contract_passes",
        "split_files_delivery_needs_no_external_review", "split_files_content_contract_passes",
        "different_layouts_have_same_required_fields", "incomplete_content_is_executable",
        "independent_evaluation_rejects_incomplete_content", "evaluation_preserves_formal_submission",
        "cross_project_write_rejected", "object_identity_spoof_rejected",
        "forged_confirmation_rejected", "unauthorized_attempts_preserve_objects_and_confirmations",
    ),
}


class Evidence:
    def __init__(self, group, output):
        self.group, self.output = group, output
        self.checks, self.snapshots = [], []
        self.world = None

    def check(self, name, observed, expected):
        if name not in CHECKS[self.group] or any(c["name"] == name for c in self.checks):
            raise AssertionError("Check not declared or repeated: " + name)
        self.checks.append({"name": name, "expected": expected, "observed": observed,
                            "passed": observed == expected, "not_executed": False})

    def snapshot(self, name):
        self.snapshots.append({"name": name,
                               "state": write_json(self.output / (name + "-state.json"),
                                                   self.world.store.load()),
                               "files": file_hashes(self.world)})


def install(world, *packages):
    for pkg in packages:
        mustcall(world.session("manager"), "install_project", package=pkg)


def create_report(session, alias="report", data=None, **kwargs):
    return mustcall(session, "create_object", alias=alias, filename="report.json",
                    data={"revenue": 10, "cost": 4} if data is None else data,
                    deliverable_role="report", **kwargs)


def group_m1(ev):
    world = ev.world = bootstrap(ev.output / "world")
    initial = world.store.load()
    ev.snapshot("zero-project")
    ev.check("zero_project_world_exists", [initial["projects"], world.session("manager").observe()["world_status"]], [{}, "idle"])
    material = mustcall(world.session("manager"), "create_object", alias="world-material",
                        filename="material.json", data={"reference": "world data"})
    ev.check("world_material_precedes_projects", [world.store.load()["projects"], material["object_id"] in world.store.load()["artifacts"]], [{}, True])
    install(world, package("A"), package("B", owner="bob", reviewer="alice"))
    ev.check("two_projects_loaded", sorted(world.store.load()["projects"]), ["A", "B"])
    a, b = world.session("alice", "A"), world.session("bob", "B")
    provider = world.session("manager", "B")
    evidence = mustcall(provider, "create_object", alias="evidence", filename="evidence.json", data={"evidence": 1})
    request = mustcall(b, "request", work_id="work-1", provider="manager",
                       reference=exact_ref(evidence), delay=100)
    report = create_report(a)
    sub = mustcall(a, "submit", work_id="work-1", artifacts=["report"])
    mustcall(world.session("bob", "A"), "approve", work_id="work-1", submission_id=sub["submission_id"])
    mustcall(a, "share", **exact_ref(report), target_project="B", actor_ids=["bob"])
    before_close = world.store.load()
    ev.snapshot("before-A-close")
    ev.check("B_event_pending_before_A_close", [before_close["requests"][request["request_id"]]["status"], len(before_close["events"])], ["pending", 1])
    mustcall(world.session("manager", "A"), "close_project", mode="completed", reason="A delivered")
    after_close = world.store.load()
    ev.check("A_completed_without_erasing_B", [after_close["projects"]["A"]["status"], after_close["work_items"]["B::work-1"] == before_close["work_items"]["B::work-1"], after_close["events"] == before_close["events"]], ["completed", True, True])
    shared = mustcall(b, "read_object", **exact_ref(report))
    ev.check("A_submission_and_share_survive", [after_close["work_items"]["A::work-1"]["submissions"] == before_close["work_items"]["A::work-1"]["submissions"], shared["data"]], [True, {"revenue": 10, "cost": 4}])
    mustcall(b, "wait", ticks=100)
    create_report(b)
    bsub = mustcall(b, "submit", work_id="work-1", artifacts=["report"])
    mustcall(world.session("alice", "B"), "approve", work_id="work-1", submission_id=bsub["submission_id"])
    ev.check("B_progresses_after_A_end", [world.store.load()["requests"][request["request_id"]]["status"], b.observe()["work_items"]["B::work-1"]["status"]], ["delivered", "accepted"])
    install(world, package("C", policy="delivery_only"))
    final = world.store.load()
    ev.check("C_loaded_in_same_world", [sorted(final["projects"]), final["projects"]["C"]["status"]], [["A", "B", "C"], "active"])
    ev.check("world_identity_and_actors_continuous", {key: final[key] for key in ("world_id", "instance_id", "branch_id", "actors")}, {key: initial[key] for key in ("world_id", "instance_id", "branch_id", "actors")})
    ev.check("logical_time_increases", 0 < before_close["clock"] < after_close["clock"] < final["clock"], True)
    bad = package("invalid")
    bad["objects"] = [{"alias": "partial", "filename": "partial.json", "owner": "alice", "data": {"must_not_exist": True}}]
    bad["grants"].append({"actor_id": "alice", "power": "install_project"})
    facts, files = business_facts(final), file_hashes(world)
    response = world.session("manager").call("install_project", package=bad)
    ev.check("invalid_package_explicitly_rejected", response["ok"], False)
    ev.check("invalid_package_business_prefix_unchanged", business_facts(world.store.load()), facts)
    ev.check("invalid_package_files_unchanged", file_hashes(world), files)
    ev.snapshot("final")


def group_m2(ev):
    world = ev.world = bootstrap(ev.output / "world")
    project_b = package("B", owner="bob", reviewer="alice")
    # Same actor and identical payload/key must still be distinct by project.
    # Creating a local scratch object is an explicit B grant, not inferred from A.
    project_b["grants"].append({"actor_id": "alice", "power": "create_object",
                                 "subject": "artifact"})
    install(world, package("A"), project_b)
    a, b = world.session("alice", "A"), world.session("bob", "B")
    secret = mustcall(a, "create_object", alias="private-source", filename="source.json", data={"private": "A only"})
    report_a = create_report(a, dependencies=[exact_ref(secret)])
    report_b = create_report(b)
    state = world.store.load()
    ev.check("same_names_distinct_object_and_work_identity", [report_a["object_id"] != report_b["object_id"], state["artifacts"][report_a["object_id"]]["filename"], state["artifacts"][report_b["object_id"]]["filename"], sorted(state["work_items"])], [True, "report.json", "report.json", ["A::work-1", "B::work-1"]])
    manager_a = world.session("manager", "A")
    policy = mustcall(manager_a, "create_object", alias="policy", filename="policy.json", data={"basis": 1})
    mustcall(manager_a, "confirm", work_id="work-1", alias="policy", dimension="requirements", purpose="delivery")
    ev.check("A_confirmation_applies_to_A", world.applicability("A", "work-1", exact_ref(policy), "requirements", "delivery")["status"], "PASS")
    mustcall(manager_a, "share", **exact_ref(policy), target_project="B", actor_ids=["manager", "bob"])
    mustcall(world.session("manager", "B"), "adopt", alias="A-policy", **exact_ref(policy), policy="fixed", work_ids=["work-1"])
    ev.check("A_confirmation_does_not_apply_to_B", world.applicability("B", "work-1", exact_ref(policy), "requirements", "delivery")["status"], "FAIL")
    ev.check("share_before_denied", b.call("read_object", **exact_ref(report_a))["ok"], False)
    mustcall(a, "share", **exact_ref(report_a), target_project="B", actor_ids=["bob"])
    ev.check("exact_shared_version_readable", mustcall(b, "read_object", **exact_ref(report_a))["data"], {"revenue": 10, "cost": 4})
    version2 = mustcall(a, "write_object", alias="report", data={"revenue": 12, "cost": 4})
    ev.check("unshared_new_version_denied", b.call("read_object", **exact_ref(version2))["ok"], False)
    ev.check("upstream_private_not_shared", b.call("read_object", **exact_ref(secret))["ok"], False)
    asub = mustcall(a, "submit", work_id="work-1", artifacts=["report"])
    bsub = mustcall(b, "submit", work_id="work-1", artifacts=["report"])
    ev.check("B_reviewer_cannot_approve_A", a.call("approve", work_id="work-1", submission_id=asub["submission_id"])["ok"], False)
    approved = world.session("alice", "B").call("approve", work_id="work-1", submission_id=bsub["submission_id"])
    ev.check("B_reviewer_can_approve_B", [approved["ok"], world.session("alice", "B").observe()["work_items"]["B::work-1"]["status"]], [True, "accepted"])
    command = {"alias": "retry-object", "filename": "retry.json", "data": {"marker": 1}, "request_key": "same-text-key"}
    first = a.call("create_object", **command)
    if not first["ok"]:
        raise AssertionError(first)
    committed, committed_files = world.store.load(), file_hashes(world)
    retry = a.call("create_object", **command)
    ev.check("same_project_retry_same_result", retry, first)
    ev.check("same_project_retry_no_formal_effect", [world.store.load() == committed, file_hashes(world) == committed_files], [True, True])
    second = world.session("alice", "B").call("create_object", **command)
    ev.check("same_key_other_project_independent", [second["ok"], second.get("result", {}).get("object_id") != first["result"]["object_id"], second.get("result", {}).get("object_id") == world.store.load()["workspaces"]["B"]["retry-object"]], [True, True, True])
    ev.check("forged_project_argument_rejected", a.call("write_object", project_id="B", object_id=report_b["object_id"], data={"bad": True})["ok"], False)
    mustcall(a, "read_object", **exact_ref(secret))
    previous = copy.deepcopy(world.store.load()["knowledge"]["alice"]["read_artifacts"])
    switched = world.session("alice", "B").observe()
    ev.check("actor_knowledge_survives_project_switch", [world.store.load()["knowledge"]["alice"]["read_artifacts"] == previous, secret["object_id"] not in switched["objects"], any(row["artifact_id"] == secret["object_id"] for row in previous)], [True, True, True])
    ev.snapshot("final")


def group_m4(ev):
    world = ev.world = bootstrap(ev.output / "world")
    project_a = package("A", policy="delivery_only")
    # Keep the two-project protocol: the executable-content error belongs to a
    # second independently deliverable work item in A, not a third project.
    second_work = copy.deepcopy(project_a["works"][0])
    second_work["work_id"] = "work-2"
    project_a["works"].append(second_work)
    install(world, project_a, package("B", owner="bob", reviewer="alice", policy="delivery_only"))
    ev.check("package_does_not_precreate_outputs", world.store.load()["artifacts"], {})
    a, b = world.session("alice", "A"), world.session("bob", "B")
    draft = mustcall(a, "create_object", alias="scratch-not-in-package", filename="scratch.json", data={"draft": "intermediate"})
    ev.check("new_intermediate_draft_allowed", world.store.load()["artifacts"][draft["object_id"]]["deliverable_role"], "draft")
    aggregate = create_report(a, alias="aggregated")
    one = mustcall(a, "submit", work_id="work-1", artifacts=["aggregated"])
    one_state = world.store.load()["work_items"]["A::work-1"]
    ev.check("single_file_delivery_needs_no_external_review", [a.observe()["work_items"]["A::work-1"]["status"], one_state["submissions"][-1]["review"]["decision_basis"], one_state["submissions"][-1]["review"]["actor_id"]], ["accepted", "delivery_only", "alice"])
    evaluation_one = world.evaluate_submission("A", "work-1", one["submission_id"])
    ev.check("single_file_content_contract_passes", evaluation_one["passed"], True)
    create_report(b, alias="revenue-part", data={"revenue": 10})
    create_report(b, alias="cost-part", data={"cost": 4})
    two = mustcall(b, "submit", work_id="work-1", artifacts=["revenue-part", "cost-part"])
    two_state = world.store.load()["work_items"]["B::work-1"]
    ev.check("split_files_delivery_needs_no_external_review", [b.observe()["work_items"]["B::work-1"]["status"], two_state["submissions"][-1]["review"]["decision_basis"], two_state["submissions"][-1]["review"]["actor_id"]], ["accepted", "delivery_only", "bob"])
    evaluation_two = world.evaluate_submission("B", "work-1", two["submission_id"])
    ev.check("split_files_content_contract_passes", evaluation_two["passed"], True)
    ev.check("different_layouts_have_same_required_fields", [len(one["artifact_versions"]), len(two["artifact_versions"]), evaluation_one["missing_fields"], evaluation_two["missing_fields"]], [1, 2, [], []])
    create_report(a, alias="incomplete", data={"revenue": "unchecked value"})
    incomplete = mustcall(a, "submit", work_id="work-2", artifacts=["incomplete"])
    formal = copy.deepcopy(world.store.load()["work_items"]["A::work-2"]["submissions"])
    ev.check("incomplete_content_is_executable", [a.observe()["work_items"]["A::work-2"]["status"], formal[-1]["review"]["decision_basis"], formal[-1]["review"]["actor_id"]], ["accepted", "delivery_only", "alice"])
    bad_eval = world.evaluate_submission("A", "work-2", incomplete["submission_id"])
    ev.check("independent_evaluation_rejects_incomplete_content", [bad_eval["passed"], bad_eval["missing_fields"]], [False, ["cost"]])
    ev.check("evaluation_preserves_formal_submission", world.store.load()["work_items"]["A::work-2"]["submissions"], formal)
    state, files = world.store.load(), file_hashes(world)
    ev.check("cross_project_write_rejected", b.call("write_object", object_id=aggregate["object_id"], data={"overwritten": True})["ok"], False)
    ev.check("object_identity_spoof_rejected", b.call("create_object", alias="forged", filename="report.json", object_id=aggregate["object_id"], data={"forged": True})["ok"], False)
    ev.check("forged_confirmation_rejected", a.call("confirm", work_id="work-1", alias="aggregated", dimension="requirements", purpose="delivery")["ok"], False)
    after = world.store.load()
    ev.check("unauthorized_attempts_preserve_objects_and_confirmations", [after["artifacts"] == state["artifacts"], after["attestations"] == state["attestations"], file_hashes(world) == files], [True, True, True])
    write_json(ev.output / "independent-evaluations.json", [evaluation_one, evaluation_two, bad_eval])
    ev.snapshot("final")


GROUP_RUNNERS = {"M1": group_m1, "M2": group_m2, "M4": group_m4}


def run_group(entry):
    group, output = entry
    output.mkdir(parents=True)
    ev = Evidence(group, output)
    error = None
    try:
        GROUP_RUNNERS[group](ev)
    except Exception as caught:
        error = {"error": f"{type(caught).__name__}: {caught}", "traceback": traceback.format_exc()}
    completed = {check["name"] for check in ev.checks}
    for name in CHECKS[group]:
        if name not in completed:
            ev.checks.append({"name": name, "expected": "declared group protocol",
                              "observed": None, "passed": False, "not_executed": True})
    if ev.world:
        ev.snapshot("end-of-run")
    result = {"group": group, "checks": ev.checks, "error": error, "snapshots": ev.snapshots,
              "check_count": len(ev.checks), "pass_count": sum(c["passed"] for c in ev.checks),
              "not_executed_count": sum(c["not_executed"] for c in ev.checks),
              "passed": error is None and all(c["passed"] for c in ev.checks)}
    write_json(output / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", nargs="+", choices=list(CHECKS), default=list(CHECKS))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if args.output.exists() or args.workers < 1 or len(set(args.groups)) != len(args.groups):
        parser.error("Use a new directory, distinct groups and a positive worker count")
    args.output.mkdir(parents=True)
    before = code_identity()
    script_before = digest(Path(__file__).read_bytes())
    started = datetime.now(timezone.utc).isoformat()
    protocol = {"suite": "world-core-M1-M2-M4-v0.6", "groups": args.groups,
                "declared_checks": {group: CHECKS[group] for group in args.groups},
                "business_atomicity_comparison_keys": BUSINESS_KEYS,
                "scope": "Finite synthetic JSON, one world per independent group, real runtime actions; no model or domain-quality claim.",
                "delivery_only": "Runtime stores an owner-attributed accepted decision with decision_basis=delivery_only in the review record; these trajectories execute no approve action or external reviewer."}
    write_json(args.output / "protocol.json", protocol)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run_group, [(g, args.output / g) for g in args.groups]))
    after = code_identity()
    report = {"suite": protocol["suite"], "protocol": protocol,
              "started_at": started, "ended_at": datetime.now(timezone.utc).isoformat(),
              "code_identity_before": before, "code_identity_after": after,
              "script_sha256_before": script_before, "script_sha256_after": digest(Path(__file__).read_bytes()),
              "source_tree_unchanged": before["source_tree_sha256"] == after["source_tree_sha256"],
              "workers": args.workers, "results": results,
              "group_count": len(results), "group_pass_count": sum(r["passed"] for r in results),
              "check_count": sum(r["check_count"] for r in results),
              "check_pass_count": sum(r["pass_count"] for r in results),
              "not_executed_count": sum(r["not_executed_count"] for r in results),
              "api_calls": 0, "gpu_used": False, "training_performed": False}
    write_json(args.output / "report.json", report)
    print(f"M1/M2/M4 {report['group_pass_count']}/{report['group_count']} groups; "
          f"{report['check_pass_count']}/{report['check_count']} checks; "
          f"{report['not_executed_count']} not executed")
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
