"""M3 directed adoption changes and M5 interleaving plus two actual process cuts.

Fixtures use real WorldCore sessions. Expectations are declared independently of
pairwise equality; controls and faults share an identical persisted checkpoint.
"""

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core.journal import validate_committed_prefix
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.world_core import WorldCore
from world_core_experiment import bootstrap, mustcall, package

EXIT_CODE = 73
CUTS = ("after_apply", "after_command_commit")
M3_CHECKS = (
    "both_adoptions_initially_current_v1",
    "publication_changes_only_shared_object_bytes",
    "A_update_required_B_fixed_current",
    "publication_notifies_A_not_B",
    "follow_updates_grants_v2_to_A_only",
    "B_reads_fixed_v1_and_cannot_read_unshared_v2",
    "local_A_basis_revision_preserves_B_and_all_files",
    "local_A_audience_revision_preserves_B_and_all_files",
    "unshared_edit_has_no_B_fact_or_notification_effect",
    "explicit_worker_edit_alone_creates_A_delivery_version",
)
M5_CHECKS = (
    "A_waits_while_B_has_separate_pending_condition",
    "B_delivery_only_completed_without_manager_review",
    "A_revision_preserves_B_formal_history_and_bytes",
    "old_A_response_is_delivered_but_old_condition_superseded",
    "old_A_reply_does_not_resolve_new_A_or_B",
    "old_A_reply_preserves_B_submission_and_bytes",
    "end_A_episode_preserves_B_and_both_pending_replies",
    "same_actor_switches_to_B_with_bound_scope",
)
RECOVERY_CHECKS = (
    "copied_checkpoint_bytes_identical",
    "actual_process_cut_reached",
    "committed_prefix_matches_expected_cut",
    "full_state_matches_uninterrupted_control",
    "all_immutable_and_mirror_bytes_match_control",
    "public_result_matches_control",
    "world_relations_and_observed_history_preserved",
    "second_retry_has_no_effect",
)


def normalize(value):
    value = copy.deepcopy(value)
    if isinstance(value, dict):
        return {
            k: normalize(v) for k, v in value.items() if k not in {"wall_seconds", "state_digests"}
        }
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def files(world):
    result = {"versions": {}, "mirrors": {}}
    for aid, artifact in world.store.load()["artifacts"].items():
        for vid in artifact["versions"]:
            result["versions"][f"{aid}/{vid}"] = digest(
                world.store.version_path(artifact, vid).read_bytes()
            )
        result["mirrors"][aid] = digest(world.store.current_path(artifact).read_bytes())
    return result


def tree_files(root):
    return {
        str(p.relative_to(root)): digest(p.read_bytes())
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "world.lock"
    }


def capture(world, path):
    value = {"state": world.store.load(), "files": files(world)}
    atomic_write(path, json_bytes(value))
    return value


def project_facts(state, pid):
    return {
        "project": state["projects"][pid],
        "workspace": state["workspaces"][pid],
        "works": {
            key: value for key, value in state["work_items"].items() if value["project_id"] == pid
        },
        "conditions": {
            key: value
            for key, value in state["condition_specs"].items()
            if state["work_items"][value["work_item_id"]]["project_id"] == pid
        },
        "grants": [
            grant for grant in state["organization"]["grants"] if grant.get("project_id") == pid
        ],
    }


def relations(state):
    return {
        key: state.get(key)
        for key in (
            "projects",
            "organization",
            "workspaces",
            "world_workspace",
            "adoptions",
            "adoption_view",
            "shares",
            "knowledge",
            "observations",
            "messages",
            "interactions",
        )
    }


def save_observation(world, actor, pid, path):
    observation = world.session(actor, pid).observe()
    atomic_write(path, json_bytes(observation))
    return observation


def shared_setup(root, evidence):
    world = bootstrap(root)
    admin = world.session("manager")
    source = mustcall(
        admin,
        "create_object",
        alias="shared-material",
        filename="reference.json",
        data={"release": 1, "value": 10},
    )
    common = mustcall(
        admin,
        "create_object",
        alias="common-model",
        filename="model.json",
        data={"formula": "value * 2", "result": 20},
    )
    for pid in ("A", "B"):
        mustcall(admin, "install_project", package=package(pid))
        mustcall(
            admin,
            "share",
            object_id=source["object_id"],
            version_id="v1",
            target_project=pid,
            actor_ids=["alice", "bob", "manager"],
            follow_updates=pid == "A",
        )
        mustcall(
            admin,
            "share",
            object_id=common["object_id"],
            version_id="v1",
            target_project=pid,
            actor_ids=["alice", "bob", "manager"],
            follow_updates=False,
        )
        session = world.session("alice", pid)
        mustcall(
            session,
            "adopt",
            alias="common-model",
            object_id=common["object_id"],
            version_id="v1",
            policy="fixed",
            work_ids=["work-1"],
        )
        mustcall(
            session,
            "adopt",
            alias="shared",
            object_id=source["object_id"],
            version_id="v1",
            policy="current_applicable" if pid == "A" else "fixed",
            work_ids=["work-1"],
        )
        mustcall(
            session,
            "create_object",
            alias="report",
            filename="report.json",
            data={"revenue": 20, "cost": 5},
            deliverable_role="report",
            dependencies=[
                {"object_id": source["object_id"], "version_id": "v1"},
                {"object_id": common["object_id"], "version_id": "v1"},
            ],
        )
        mustcall(session, "read_object", alias="shared", version_id="v1")
        save_observation(world, "alice", pid, evidence / f"observed-{pid}.json")
    return world, source, common


def publish(world):
    return world.session("manager").call(
        "write_object",
        object_id=world.store.load()["world_workspace"]["shared-material"],
        data={"release": 2, "value": 12},
        request_key="publish-shared-v2-once",
    )


def m3(root, check):
    world, source, common = shared_setup(root / "world", root)
    before = capture(world, root / "before-publication.json")
    check(
        M3_CHECKS[0],
        all(
            before["state"]["adoption_view"][f"{p}::shared"]["status"] == "current"
            and before["state"]["adoptions"][f"{p}::shared"]["version_id"] == "v1"
            for p in ("A", "B")
        ),
    )
    response = publish(world)
    if not response["ok"]:
        raise AssertionError(response)
    after = capture(world, root / "after-publication.json")
    preserved = {
        aid: sha for aid, sha in before["files"]["mirrors"].items() if aid != source["object_id"]
    }
    check(
        M3_CHECKS[1],
        all(after["files"]["mirrors"][aid] == sha for aid, sha in preserved.items())
        and after["state"]["artifacts"][source["object_id"]]["current_version"] == "v2"
        and all(
            after["files"]["versions"][key] == sha
            for key, sha in before["files"]["versions"].items()
        ),
    )
    av = after["state"]["adoption_view"]
    check(
        M3_CHECKS[2],
        av["A::shared"]
        == {
            "adopted_version": "v1",
            "target_version": "v2",
            "status": "update_required",
            "policy": "current_applicable",
        }
        and av["B::shared"]
        == {
            "adopted_version": "v1",
            "target_version": "v1",
            "status": "current",
            "policy": "fixed",
        },
    )
    notices = after["state"]["messages"][len(before["state"]["messages"]) :]
    check(
        M3_CHECKS[3],
        len(notices) == 1
        and notices[0]["project_id"] == "A"
        and notices[0]["body"]["effect"] == "review_required",
    )
    new_shares = [s for s in after["state"]["shares"] if s["version_id"] == "v2"]
    check(M3_CHECKS[4], len(new_shares) == 1 and new_shares[0]["project_id"] == "A")
    b = world.session("alice", "B")
    read = mustcall(b, "read_object", alias="shared", version_id="v1")
    rejected = b.call("read_object", alias="shared", version_id="v2")
    check(M3_CHECKS[5], read["data"]["release"] == 1 and not rejected["ok"])
    admin = world.session("manager", "A")
    baseline = capture(world, root / "before-local-revisions.json")
    basis = {
        "basis_reference": {"object_id": source["object_id"], "version_id": "v2"},
        "audience": "internal",
    }
    change = mustcall(
        admin,
        "revise",
        work_id="work-1",
        updates={"requirements": basis},
        reason="A explicitly adopts revised basis requirements",
    )
    current = next(iter(change["replacements"].values()))
    revised = capture(world, root / "after-basis-revision.json")
    check(
        M3_CHECKS[6],
        project_facts(revised["state"], "B") == project_facts(baseline["state"], "B")
        and revised["files"] == baseline["files"]
        and revised["state"]["work_items"][current]["requirements"] == basis,
    )
    audience = {**basis, "audience": "external-reviewers"}
    change = mustcall(
        admin,
        "revise",
        work_id=current,
        updates={"requirements": audience, "requirement_dimension": "audience"},
        reason="Only A delivery audience changes",
    )
    latest = next(iter(change["replacements"].values()))
    revised_again = capture(world, root / "after-audience-revision.json")
    check(
        M3_CHECKS[7],
        project_facts(revised_again["state"], "B") == project_facts(baseline["state"], "B")
        and revised_again["files"] == baseline["files"]
        and revised_again["state"]["work_items"][latest]["requirements"] == audience,
    )
    a = world.session("alice", "A")
    mustcall(a, "create_object", alias="private-draft", filename="private.json", data={"draft": 1})
    private_before = capture(world, root / "before-unshared-edit.json")
    mustcall(a, "write_object", alias="private-draft", data={"draft": 2})
    private_after = capture(world, root / "after-unshared-edit.json")
    check(
        M3_CHECKS[8],
        project_facts(private_after["state"], "B") == project_facts(private_before["state"], "B")
        and private_after["state"]["messages"] == private_before["state"]["messages"]
        and private_after["files"]["mirrors"][common["object_id"]]
        == before["files"]["mirrors"][common["object_id"]],
    )
    mustcall(
        a,
        "write_object",
        alias="report",
        data={"revenue": 24, "cost": 5},
        dependencies=[
            {"object_id": source["object_id"], "version_id": "v2"},
            {"object_id": common["object_id"], "version_id": "v1"},
        ],
    )
    final = capture(world, root / "after-worker-edit.json")
    added = set(final["files"]["versions"]) - set(private_after["files"]["versions"])
    check(
        M3_CHECKS[9],
        added == {before["state"]["workspaces"]["A"]["report"] + "/v2"}
        and final["files"]["mirrors"][world.store.load()["workspaces"]["B"]["report"]]
        == before["files"]["mirrors"][world.store.load()["workspaces"]["B"]["report"]]
        and final["files"]["mirrors"][common["object_id"]]
        == before["files"]["mirrors"][common["object_id"]],
    )
    return {
        "world": str(world.store.root),
        "publication_result": response,
        "final_work_A": latest,
        "basis_revision_semantics": "explicit project requirement reference; no invented formal credential or content correctness claim",
    }


def m5_trace(root, check):
    world = bootstrap(root / "world")
    admin = world.session("manager")
    for pid in ("A", "B"):
        payload = package(pid, policy="delivery_only" if pid == "B" else "review")
        if pid == "B":
            pending = copy.deepcopy(payload["works"][0])
            pending.update(work_id="work-2", approval_policy="review")
            payload["works"].append(pending)
            payload["grants"].append(
                {
                    "actor_id": "manager",
                    "power": "provide",
                    "subject": "evidence",
                    "work_nodes": ["work-2"],
                }
            )
        mustcall(admin, "install_project", package=payload)
        mustcall(
            world.session("manager", pid),
            "create_object",
            alias="evidence",
            filename="evidence.json",
            data={"source": pid},
        )
    a, b = world.session("alice", "A"), world.session("alice", "B")
    mustcall(a, "start_episode", episode_id="episode-A")
    old = mustcall(
        a,
        "request",
        work_id="work-1",
        provider="manager",
        reference={
            "object_id": world.store.load()["workspaces"]["A"]["evidence"],
            "version_id": "v1",
        },
        delay=20,
    )
    other = mustcall(
        b,
        "request",
        work_id="work-2",
        provider="manager",
        reference={
            "object_id": world.store.load()["workspaces"]["B"]["evidence"],
            "version_id": "v1",
        },
        delay=100,
    )
    waiting = capture(world, root / "both-projects-waiting.json")
    check(
        M5_CHECKS[0],
        all(
            waiting["state"]["condition_specs"][item["condition_id"]]["status"] == "open"
            for item in (old, other)
        ),
    )
    mustcall(
        b,
        "create_object",
        alias="report",
        filename="report.json",
        data={"revenue": 30, "cost": 7},
        deliverable_role="report",
    )
    submitted = mustcall(b, "submit", work_id="work-1", artifacts=["report"])
    delivered = capture(world, root / "B-delivery-completed.json")
    sub = delivered["state"]["work_items"]["B::work-1"]["submissions"][-1]
    check(
        M5_CHECKS[1],
        delivered["state"]["work_items"]["B::work-1"]["status"] == "accepted"
        and sub["review"]["decision_basis"] == "delivery_only"
        and sub["review"]["actor_id"] == sub["actor_id"] == "alice"
        and not any(event["kind"] == "review" for event in delivered["state"]["event_history"])
        and sub["submission_id"] == submitted["submission_id"],
    )
    change = mustcall(
        world.session("manager", "A"),
        "revise",
        work_id="work-1",
        updates={"requirements": {"audience": "new-A-audience"}},
        reason="A requirement changed before old reply",
    )
    new_id = next(iter(change["replacements"].values()))
    revised = capture(world, root / "A-revised-B-preserved.json")
    check(
        M5_CHECKS[2],
        project_facts(revised["state"], "B") == project_facts(delivered["state"], "B")
        and revised["files"] == delivered["files"],
    )
    new = mustcall(
        a,
        "request",
        work_id=new_id,
        provider="manager",
        reference={
            "object_id": world.store.load()["workspaces"]["A"]["evidence"],
            "version_id": "v1",
        },
        delay=100,
    )
    due = next(
        e["at"]
        for e in world.store.load()["events"]
        if e["payload"]["request_id"] == old["request_id"]
    )
    mustcall(a, "wait", ticks=due - world.store.load()["clock"])
    received = capture(world, root / "old-A-reply-arrived.json")
    state = received["state"]
    check(
        M5_CHECKS[3],
        state["requests"][old["request_id"]]["status"] == "delivered"
        and state["condition_specs"][old["condition_id"]]["status"] == "superseded"
        and any(
            r["request_id"] == old["request_id"] for r in state["raw_condition_responses"].values()
        ),
    )
    check(
        M5_CHECKS[4],
        all(
            state["condition_specs"][item["condition_id"]]["status"] == "open"
            for item in (new, other)
        ),
    )
    check(
        M5_CHECKS[5],
        state["work_items"]["B::work-1"]["submissions"]
        == delivered["state"]["work_items"]["B::work-1"]["submissions"]
        and received["files"]["mirrors"][world.store.load()["workspaces"]["B"]["report"]]
        == delivered["files"]["mirrors"][world.store.load()["workspaces"]["B"]["report"]],
    )
    mustcall(a, "end_episode", episode_id="episode-A")
    ended = capture(world, root / "A-episode-ended.json")
    check(
        M5_CHECKS[6],
        project_facts(ended["state"], "B") == project_facts(state, "B")
        and ended["state"]["events"] == state["events"]
        and len(state["events"]) == 2
        and ended["state"]["episodes"]["episode-A"]["ended_at"] is not None,
    )
    denied = b.call(
        "read_object", object_id=world.store.load()["workspaces"]["A"]["evidence"], version_id="v1"
    )
    read = mustcall(b, "read_object", alias="evidence", version_id="v1")
    final = capture(world, root / "after-scope-switch.json")
    check(
        M5_CHECKS[7],
        not denied["ok"]
        and read["data"]["source"] == "B"
        and final["state"]["knowledge"]["alice"]["read_artifacts"][-1]["project_id"] == "B"
        and final["state"]["interactions"][-1]["inputs"]["project_id"] == "B",
    )
    return {
        "world": str(world.store.root),
        "old_request": old,
        "new_request": new,
        "other_project_request": other,
        "B_submission": submitted,
    }


def child(world_path, phase, evidence):
    world = WorldCore(world_path)

    def fault(reached, context):
        if reached == phase:
            atomic_write(
                Path(evidence),
                json_bytes(
                    {
                        "phase": phase,
                        "context": context,
                        "pid": os.getpid(),
                        "in_memory_state": world.state,
                        "persisted_state": world.store.load(),
                        "registered_files": files(world),
                        "physical_versions": tree_files(world.store.control / "versions"),
                    }
                ),
            )
            os._exit(EXIT_CODE)

    world.fault_hook = fault
    result = publish(world)
    raise AssertionError({"unreached_cut": phase, "result": result})


def recover_case(root, checkpoint, control, phase):
    target = root / phase
    shutil.copytree(checkpoint, target, ignore=shutil.ignore_patterns("world.lock"))
    checks = []

    def check(name, value):
        checks.append({"name": name, "passed": bool(value)})
        if not value:
            raise AssertionError(name)

    error, execution, before_resume = None, None, None
    try:
        check(RECOVERY_CHECKS[0], tree_files(target) == tree_files(checkpoint))
        evidence = target / "fault-reached.json"
        execution = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--child",
                str(target),
                "--phase",
                phase,
                "--evidence",
                str(evidence),
            ],
            capture_output=True,
            text=True,
        )
        check(RECOVERY_CHECKS[1], execution.returncode == EXIT_CODE and evidence.exists())
        before_resume = json.loads((target / "control/state.json").read_text())
        atomic_write(target / "before-resume-state.json", json_bytes(before_resume))
        expected = control["state"]["state_revision"] - (1 if phase == "after_apply" else 0)
        validate_committed_prefix(before_resume)
        check(RECOVERY_CHECKS[2], before_resume["state_revision"] == expected)
        world = WorldCore(target)
        result = publish(world)
        resumed = capture(world, target / "after-resume.json")
        validate_committed_prefix(resumed["state"])
        check(RECOVERY_CHECKS[3], normalize(resumed["state"]) == normalize(control["state"]))
        check(RECOVERY_CHECKS[4], resumed["files"] == control["files"])
        check(RECOVERY_CHECKS[5], result == control["result"])
        check(
            RECOVERY_CHECKS[6],
            normalize(relations(resumed["state"])) == normalize(relations(control["state"]))
            and bool(resumed["state"]["knowledge"]["alice"]["read_artifacts"]),
        )
        retried = publish(world)
        check(
            RECOVERY_CHECKS[7],
            retried == result
            and world.store.load() == resumed["state"]
            and files(world) == resumed["files"],
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    report = {
        "phase": phase,
        "world": str(target),
        "passed": error is None,
        "checks": checks,
        "not_executed": [n for n in RECOVERY_CHECKS if n not in {c["name"] for c in checks}],
        "error": error,
        "process": {
            "returncode": execution.returncode,
            "stdout": execution.stdout,
            "stderr": execution.stderr,
        }
        if execution
        else None,
        "committed_revision_before_resume": (before_resume or {}).get("state_revision"),
    }
    atomic_write(target / "result.json", json_bytes(report))
    return report


def recovery(root, workers):
    root.mkdir()
    world, _, _ = shared_setup(root / "checkpoint", root)
    before = capture(world, root / "checkpoint-evidence.json")
    target = root / "control"
    shutil.copytree(world.store.root, target, ignore=shutil.ignore_patterns("world.lock"))
    controlled = WorldCore(target)
    response = publish(controlled)
    if not response["ok"]:
        raise AssertionError(response)
    control = capture(controlled, root / "control-evidence.json")
    control["result"] = response
    atomic_write(root / "control-evidence.json", json_bytes(control))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(
            pool.map(lambda phase: recover_case(root, world.store.root, control, phase), CUTS)
        )
    return {
        "cases": results,
        "checkpoint_revision": before["state"]["state_revision"],
        "checkpoint": str(world.store.root),
        "control": str(target),
        "expected_cases": 2,
        "expected_checks_per_case": len(RECOVERY_CHECKS),
        "passed": sum(case["passed"] for case in results),
        "checks_passed": sum(c["passed"] for case in results for c in case["checks"]),
        "observation_coverage": "persisted object reads in knowledge and command interactions; observe responses archived externally; empty observations registry is not counted as populated history",
    }


def run_group(root, group, workers):
    path = root / group
    path.mkdir()
    expected = M3_CHECKS if group == "M3" else M5_CHECKS
    checks, evidence, error = [], {}, None

    def check(name, value):
        checks.append({"name": name, "passed": bool(value)})

    try:
        evidence = m3(path, check) if group == "M3" else m5_trace(path, check)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    record = {
        "group": group,
        "checks": checks,
        "not_executed": [n for n in expected if n not in {c["name"] for c in checks}],
        "passed": error is None and all(c["passed"] for c in checks),
        "error": error,
        "evidence": evidence,
    }
    if group == "M5":
        try:
            record["recovery"] = recovery(path / "recovery", workers)
            record["passed"] &= record["recovery"]["passed"] == len(CUTS)
        except Exception as exc:
            record["recovery"] = {
                "error": f"{type(exc).__name__}: {exc}",
                "expected_cases": 2,
                "cases": [],
                "passed": 0,
                "not_executed": list(CUTS),
            }
            record["passed"] = False
    atomic_write(path / "report.json", json_bytes(record))
    return record


def run(output, groups, workers):
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    before = code_identity()
    protocol = {
        "groups": groups,
        "M3_assertions": list(M3_CHECKS),
        "M5_assertions": list(M5_CHECKS),
        "recovery_cuts": list(CUTS),
        "recovery_assertions_per_cut": list(RECOVERY_CHECKS),
        "process_exit_code": EXIT_CODE,
        "normalization": ["wall_seconds", "state_digests"],
        "coverage": "finite explicit project relations, two real process cuts on shared world publication; no distributed, power-loss or arbitrary-operation guarantee",
        "source_boundary": "new WorldCore runtime sharing the extracted commit/recovery runner with the existing single-project adapters; no old evidence is rewritten",
        "initial_materials": "synthetic; world release is informational input, not a fabricated approval",
        "workers": workers,
        "model_calls": 0,
        "gpu_used": False,
    }
    atomic_write(root / "protocol.json", json_bytes(protocol))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda group: run_group(root, group, workers), groups))
    report = {
        "experiment": "world-core-relations-v0.6",
        "protocol": protocol,
        "code_before": before,
        "code_after": code_identity(),
        "script_sha256": digest(Path(__file__).read_bytes()),
        "helper_script_sha256": digest(
            Path(__file__).with_name("world_core_experiment.py").read_bytes()
        ),
        "results": results,
        "groups_passed": sum(r["passed"] for r in results),
        "check_count": sum(len(r["checks"]) for r in results),
        "checks_passed": sum(c["passed"] for r in results for c in r["checks"]),
        "not_executed": sum(len(r["not_executed"]) for r in results),
    }
    atomic_write(root / "report.json", json_bytes(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--groups", nargs="+", choices=("M3", "M5"), default=["M3", "M5"])
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--child")
    parser.add_argument("--phase", choices=CUTS)
    parser.add_argument("--evidence")
    args = parser.parse_args()
    if args.child:
        child(args.child, args.phase, args.evidence)
    else:
        report = run(args.output, args.groups, args.workers)
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in ("groups_passed", "check_count", "checks_passed", "not_executed")
                }
            )
        )
        raise SystemExit(0 if report["groups_passed"] == len(args.groups) else 1)
