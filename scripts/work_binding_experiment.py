"""P1: explicit work-edition adoption and reusable information routes.

Every scenario creates one real single-writer world with two projects. All
mutations go through ProjectSession. The driver knows the declared contracts;
this is a mechanism experiment, not a public-only worker or a model evaluation.
"""

import argparse
import copy
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core.adoption import binding_key
from proworksim.core.world import WorldSpec
from proworksim.storage import digest
from proworksim.world_core import WorldCore

CHECKS = {
    "publication_only": (
        "two_works_share_alias_but_have_separate_bindings",
        "publication_advances_only_following_target",
        "publication_does_not_change_adopted_versions_or_report_bytes",
        "historical_fixed_submission_and_evaluation_unchanged",
        "publication_does_not_replace_fixed_or_following_work",
    ),
    "replacement_fixed": (
        "replacement_does_not_inherit_or_mutate_old_binding",
        "new_work_can_explicitly_reuse_same_alias_and_fixed_old_version",
        "new_submission_has_new_work_context_and_old_exact_version",
        "both_historical_and_replacement_content_pass",
        "old_submission_binding_and_bytes_preserved",
    ),
    "replacement_current": (
        "contract_rejects_fixed_policy_escape_without_binding_effect",
        "new_work_can_bind_same_alias_under_required_current_policy",
        "stale_content_and_binding_rejected_by_declared_target",
        "explicit_new_work_adoption_update_does_not_edit_file",
        "updated_content_exact_dependency_and_submission_pass",
        "old_submission_payload_review_and_binding_unchanged",
    ),
    "late_information": (
        "route_reused_by_new_work_with_distinct_request_context",
        "old_reply_retained_and_old_condition_remains_superseded",
        "old_reply_does_not_resolve_new_condition_or_grant_new_owner",
        "new_reply_resolves_only_new_condition_and_grants_exact_version",
        "new_work_resumes_and_submits_after_actual_reply",
        "old_request_and_original_observation_preserved",
    ),
    "scope_controls": (
        "object_and_work_scoped_initial_binding_succeeds",
        "same_alias_two_work_binding_respects_each_work_grant",
        "wrong_object_work_project_and_empty_scope_rejected",
        "partial_multiwork_declaration_has_no_partial_effect",
        "superseded_work_binding_update_is_rejected",
    ),
}
PROTOCOL = {
    "suite": "work-bindings-P1-v0.8",
    "checks": CHECKS,
    "actions": "install_project/create_object/write_object/share/publish/adopt/adopt_version/submit/revise/request_information/wait/read_object; all via ProjectSession",
    "policy": "requirements.input_policy defaults, input_policies alias overrides; str requires policy, list permits listed choices; fixed with declared input_version must match; adopting stale current policy is a permitted content error, not a policy escape",
    "reference_values": {"v1": 6, "v2": 8},
    "legal_alternatives": "A fixed-old replacement may reuse exact v1; a current-published replacement must actually use v2; two works may share input alias with different versions/policies",
    "rejection_exits": "Wrong object/work/project, incomplete grant coverage, fixed policy escape, old work update and unknown routes remain rejected",
    "comparison": "Retain submission payloads/reviews/adoption snapshots, bindings, immutable byte hashes and original observations. Requirement revision may annotate old submission current_applicability=superseded_requirements; this exact change is required and is the only excluded submission field. Exclude subsequent clocks/call/event records from formal-effect negative checks.",
    "boundaries": [
        "One world, two projects, single writer per scenario; no concurrent writers",
        "JSON scalar interface and an installed same-project information route",
        "Driver knows the fixtures; public-only continuing worker is separate P4",
        "No model/API/GPU/training and no universal workflow correctness claim",
    ],
}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def contract():
    return {
        "min_files": 1,
        "max_files": 1,
        "allowed_kinds": ["json"],
        "allowed_roles": ["report"],
        "required_fields": ["margin", "source_ref"],
        "content_checks": [
            {
                "kind": "json_matches_source_field",
                "path": ["margin"],
                "reference_path": ["source_ref"],
                "adoption_alias": "input",
                "source_path": ["rate"],
            }
        ],
    }


class Evidence:
    def __init__(self, group, output):
        self.group, self.output = group, Path(output)
        self.calls, self.observations, self.checks, self.evaluations = [], [], [], []
        self.world = None

    def call(self, actor, project, action, *, require=True, **arguments):
        result = self.world.session(actor, project).call(action, **arguments)
        self.calls.append(
            {
                "actor": actor,
                "project": project,
                "action": action,
                "arguments": copy.deepcopy(arguments),
                "return": copy.deepcopy(result),
            }
        )
        if require and not result.get("ok"):
            raise AssertionError(f"{actor}/{project}/{action}: {result}")
        return result["result"] if require else result

    def check(self, name, observed, expected=True):
        if name not in CHECKS[self.group] or any(c["name"] == name for c in self.checks):
            raise AssertionError("Unknown or repeated check " + name)
        self.checks.append(
            {
                "name": name,
                "observed": copy.deepcopy(observed),
                "expected": copy.deepcopy(expected),
                "passed": observed == expected,
                "not_executed": False,
            }
        )

    def observe(self, actor="bob", project="B"):
        value = self.world.session(actor, project).observe()
        self.observations.append(copy.deepcopy(value))
        return value

    def state(self):
        return self.world.store.load()

    def evaluate(self, work_id, submission):
        value = self.world.evaluate_submission("B", work_id, submission["submission_id"])
        self.evaluations.append(copy.deepcopy(value))
        return value

    def files(self):
        state = self.state()
        return {
            aid + "/" + vid: digest(self.world.store.version_path(obj, vid).read_bytes())
            for aid, obj in state["artifacts"].items()
            for vid in obj["versions"]
        }


def base(ev, *, route=False, scoped=False):
    ev.world = WorldCore.create(
        ev.output / "world",
        WorldSpec(
            world_id="p1-" + ev.group,
            actors={actor: {} for actor in ("alice", "bob", "manager")},
            bootstrap_grants=[
                {"actor_id": "manager", "scope": "world", "power": "install_project"}
            ],
        ),
    )
    for pid, owner in (("A", "alice"), ("B", "bob")):
        objects = []
        if pid == "A":
            objects = [
                {
                    "alias": "source",
                    "filename": "source.json",
                    "owner": "alice",
                    "readers": ["alice"],
                    "writers": ["alice"],
                    "kind": "json",
                    "data": {"rate": 6},
                }
            ]
        if pid == "B":
            objects = [
                {
                    "alias": "evidence",
                    "filename": "evidence.json",
                    "owner": "alice",
                    "readers": ["alice"] if route else ["alice", "bob"],
                    "writers": ["alice"],
                    "kind": "json",
                    "data": {"rate": 6},
                },
                {
                    "alias": "other",
                    "filename": "other.json",
                    "owner": "bob",
                    "readers": ["bob"],
                    "writers": ["bob"],
                    "kind": "json",
                    "data": {"rate": 8},
                },
            ]
        works = [
            {
                "work_id": "work",
                "owner": owner,
                "goal": "Finite exact-source delivery",
                "approval_policy": "delivery_only",
                "deliverable_contract": contract(),
            }
        ]
        if pid == "B":
            works.append({**copy.deepcopy(works[0]), "work_id": "other-work"})
        grants = [
            {"actor_id": owner, "power": power, "subject": "artifact"}
            for power in ("create_object", "share", "publish")
        ]
        if scoped and pid == "B":
            grants.append(
                {
                    "actor_id": "bob",
                    "power": "adopt",
                    "subject": "artifact",
                    "work_nodes": ["work"],
                    "object_ids": ["evidence"],
                }
            )
        else:
            grants.append({"actor_id": owner, "power": "adopt", "subject": "artifact"})
        grants.append(
            {"actor_id": "manager", "power": "revise_requirement", "subject": "requirements"}
        )
        if route and pid == "B":
            grants.append(
                {
                    "actor_id": "alice",
                    "power": "provide",
                    "subject": "evidence",
                    "work_nodes": ["work"],
                    "object_ids": ["evidence"],
                }
            )
        package = {
            "project_id": pid,
            "goal": "P1 binding and route fixture",
            "participants": ["alice", "bob", "manager"],
            "objects": objects,
            "works": works,
            "grants": grants,
        }
        if route and pid == "B":
            package["information_routes"] = [
                {
                    "route_id": "data",
                    "work_id": "work",
                    "provider": "alice",
                    "object_alias": "evidence",
                    "purpose": "evidence",
                    "delay": 20,
                }
            ]
        ev.call("manager", None, "install_project", package=package)
    source = ev.observe("alice", "A")["workspaces"]["A"]["source"]
    ev.call(
        "alice",
        "A",
        "share",
        object_id=source,
        version_id="v1",
        target_project="B",
        actor_ids=["bob"],
        follow_updates=True,
    )
    ev.call("alice", "A", "publish", object_id=source, version_id="v1", target_projects=["B"])
    return source


def adopt(
    ev,
    source,
    work="B::work",
    *,
    version="v1",
    policy="fixed",
    require=True,
    actor="bob",
    project="B",
    alias="input",
):
    return ev.call(
        actor,
        project,
        "adopt",
        require=require,
        alias=alias,
        object_id=source,
        version_id=version,
        policy=policy,
        work_ids=[work],
    )


def report(ev, source, version="v1", value=6, *, alias="report", create=True, actor="bob"):
    reference = {"object_id": source, "version_id": version}
    arguments = {
        "alias": alias,
        "data": {"margin": value, "source_ref": reference},
        "dependencies": [reference],
    }
    if create:
        arguments.update(filename=alias + ".json", kind="json", deliverable_role="report")
    return ev.call(actor, "B", "create_object" if create else "write_object", **arguments)


def publish_v2(ev):
    ev.call("alice", "A", "write_object", alias="source", data={"rate": 8})
    ev.call("alice", "A", "publish", alias="source", version_id="v2", target_projects=["B"])


def revise(ev, requirements=None, **other):
    updates = {"goal": "New explicitly declared delivery", **other}
    if requirements is not None:
        updates["requirements"] = requirements
    return ev.call(
        "manager",
        "B",
        "revise",
        work_id="B::work",
        updates=updates,
        reason="Declared P1 requirement replacement",
    )["replacements"]["B::work"]


def publication_only(ev):
    source = base(ev)
    adopt(ev, source)
    adopt(ev, source, "B::other-work", policy="current_published")
    report(ev, source)
    sub = ev.call("bob", "B", "submit", work_id="B::work", artifacts=["report"])
    old = ev.state()
    evaluation = ev.evaluate("B::work", sub)
    files = ev.files()
    ev.check(
        "two_works_share_alias_but_have_separate_bindings",
        sorted(old["adoptions"]),
        [binding_key("B::other-work", "input"), binding_key("B::work", "input")],
    )
    publish_v2(ev)
    current = ev.state()
    ev.check(
        "publication_advances_only_following_target",
        [
            current["adoption_view"][binding_key(w, "input")]["target_version"]
            for w in ("B::work", "B::other-work")
        ],
        ["v1", "v2"],
    )
    ev.check(
        "publication_does_not_change_adopted_versions_or_report_bytes",
        old["adoptions"] == current["adoptions"]
        and all(ev.files()[key] == value for key, value in files.items()),
    )
    ev.check(
        "historical_fixed_submission_and_evaluation_unchanged",
        current["work_items"]["B::work"]["submissions"]
        == old["work_items"]["B::work"]["submissions"]
        and ev.evaluate("B::work", sub) == evaluation
        and evaluation["passed"],
    )
    ev.check(
        "publication_does_not_replace_fixed_or_following_work", current["work_replacements"], {}
    )


def replaced_submission_history(before, after):
    if len(before) != len(after):
        return False
    return all(
        {k: v for k, v in old.items() if k != "current_applicability"}
        == {k: v for k, v in new.items() if k != "current_applicability"}
        and old.get("current_applicability") == "current"
        and new.get("current_applicability") == "superseded_requirements"
        for old, new in zip(before, after, strict=True)
    )


def replacement(ev, current):
    source = base(ev)
    adopt(ev, source)
    report(ev, source)
    first = ev.call("bob", "B", "submit", work_id="B::work", artifacts=["report"])
    old = ev.state()
    files = ev.files()
    old_eval = ev.evaluate("B::work", first)
    publish_v2(ev)
    policy = "current_published" if current else ["fixed", "current_published"]
    new = revise(ev, {"input_policy": policy, "input_version": "v2" if current else "v1"})
    if not current:
        ev.check(
            "replacement_does_not_inherit_or_mutate_old_binding",
            ev.state()["adoptions"] == old["adoptions"]
            and binding_key(new, "input") not in ev.state()["adoptions"],
        )
        adopt(ev, source, new)
        ev.check(
            "new_work_can_explicitly_reuse_same_alias_and_fixed_old_version",
            ev.state()["adoptions"][binding_key(new, "input")]["version_id"],
            "v1",
        )
        latest = ev.call("bob", "B", "submit", work_id=new, artifacts=["report"])
        snapshot = latest["adoption_snapshot"][binding_key(new, "input")]
        ev.check(
            "new_submission_has_new_work_context_and_old_exact_version",
            [snapshot["work_id"], snapshot["requirement_version"], snapshot["version_id"]],
            [new, 2, "v1"],
        )
        ev.check(
            "both_historical_and_replacement_content_pass",
            [old_eval["passed"], ev.evaluate(new, latest)["passed"]],
            [True, True],
        )
        ev.check(
            "old_submission_binding_and_bytes_preserved",
            replaced_submission_history(
                old["work_items"]["B::work"]["submissions"],
                ev.state()["work_items"]["B::work"]["submissions"],
            )
            and old["adoptions"][binding_key("B::work", "input")]
            == ev.state()["adoptions"][binding_key("B::work", "input")]
            and all(ev.files()[key] == value for key, value in files.items()),
        )
        return
    before = copy.deepcopy(ev.state()["adoptions"])
    denied = adopt(ev, source, new, require=False)
    ev.check(
        "contract_rejects_fixed_policy_escape_without_binding_effect",
        not denied["ok"] and before == ev.state()["adoptions"],
    )
    adopt(ev, source, new, policy="current_published")
    ev.check(
        "new_work_can_bind_same_alias_under_required_current_policy",
        ev.state()["adoptions"][binding_key(new, "input")]["policy"],
        "current_published",
    )
    stale = ev.call("bob", "B", "submit", work_id=new, artifacts=["report"])
    ev.check(
        "stale_content_and_binding_rejected_by_declared_target",
        ev.evaluate(new, stale)["passed"],
        False,
    )
    # A new formal requirement creates the next open obligation; a delivery-only
    # accepted submission is history even when independent content evaluation fails.
    latest_work = ev.call(
        "manager",
        "B",
        "revise",
        work_id=new,
        updates={"goal": "Correct the declared current-source delivery"},
        reason="Explicit correction requirement",
    )["replacements"][new]
    adopt(ev, source, latest_work, policy="current_published")
    before_files = ev.files()
    ev.call("bob", "B", "adopt_version", alias="input", version_id="v2", work_id=latest_work)
    ev.check("explicit_new_work_adoption_update_does_not_edit_file", ev.files(), before_files)
    report(ev, source, "v2", 8, create=False)
    updated = ev.call("bob", "B", "submit", work_id=latest_work, artifacts=["report"])
    ev.check(
        "updated_content_exact_dependency_and_submission_pass",
        ev.evaluate(latest_work, updated)["passed"],
    )
    ev.check(
        "old_submission_payload_review_and_binding_unchanged",
        replaced_submission_history(
            old["work_items"]["B::work"]["submissions"],
            ev.state()["work_items"]["B::work"]["submissions"],
        )
        and old["adoptions"][binding_key("B::work", "input")]
        == ev.state()["adoptions"][binding_key("B::work", "input")]
        and old_eval == ev.evaluate("B::work", first),
    )


def late_information(ev):
    source = base(ev, route=True)
    adopt(ev, source)
    report(ev, source)
    observed = ev.observe()
    frozen_observation = copy.deepcopy(observed)
    old = ev.call("bob", "B", "request_information", route_id="data", work_id="B::work")
    new = revise(ev)
    request = ev.call("bob", "B", "request_information", route_id="data", work_id=new)
    state = ev.state()
    ev.check(
        "route_reused_by_new_work_with_distinct_request_context",
        [
            state["requests"][rid]["work_item_id"]
            for rid in (old["request_id"], request["request_id"])
        ],
        ["B::work", new],
    )
    due = next(
        e["at"] for e in state["events"] if e["payload"].get("request_id") == old["request_id"]
    )
    ev.call("bob", "B", "wait", ticks=max(1, due - state["clock"]))
    state = ev.state()
    raw = [
        r for r in state["raw_condition_responses"].values() if r["request_id"] == old["request_id"]
    ]
    ev.check(
        "old_reply_retained_and_old_condition_remains_superseded",
        bool(raw) and state["condition_specs"][old["condition_id"]]["status"] == "superseded",
    )
    old_read = ev.call("bob", "B", "read_object", alias="evidence", version_id="v1", require=False)
    state = ev.state()
    ev.check(
        "old_reply_does_not_resolve_new_condition_or_grant_new_owner",
        not old_read["ok"]
        and state["condition_specs"][request["condition_id"]]["status"] == "open",
    )
    due = next(
        e["at"] for e in state["events"] if e["payload"].get("request_id") == request["request_id"]
    )
    ev.call("bob", "B", "wait", ticks=max(1, due - state["clock"]))
    state = ev.state()
    read = ev.call("bob", "B", "read_object", alias="evidence", version_id="v1")
    ev.check(
        "new_reply_resolves_only_new_condition_and_grants_exact_version",
        [
            state["condition_specs"][request["condition_id"]]["status"],
            state["condition_specs"][old["condition_id"]]["status"],
            read["data"],
        ],
        ["resolved", "superseded", {"rate": 6}],
    )
    adopt(ev, source, new)
    submitted = ev.call("bob", "B", "submit", work_id=new, artifacts=["report"])
    ev.check(
        "new_work_resumes_and_submits_after_actual_reply", ev.evaluate(new, submitted)["passed"]
    )
    ev.check(
        "old_request_and_original_observation_preserved",
        observed == frozen_observation
        and state["requests"][old["request_id"]]["work_item_id"] == "B::work",
    )


def scope_controls(ev):
    source = base(ev, scoped=True)
    local = ev.observe()["workspaces"]["B"]["evidence"]
    adopt(ev, local, policy="current_applicable")
    ev.check(
        "object_and_work_scoped_initial_binding_succeeds",
        ev.state()["adoptions"][binding_key("B::work", "input")]["object_id"],
        local,
    )
    other = adopt(ev, local, "B::other-work", require=False, policy="current_applicable")
    ev.check("same_alias_two_work_binding_respects_each_work_grant", not other["ok"])
    before = {k: copy.deepcopy(ev.state()[k]) for k in ("workspaces", "adoptions")}
    responses = [
        adopt(ev, source, require=False, alias="foreign-object"),
        adopt(ev, local, "A::work", require=False, alias="wrong-project-work"),
        adopt(ev, local, "B::other-work", require=False, alias="wrong-work"),
        adopt(ev, local, "A::work", project="A", require=False, alias="wrong-project"),
        ev.call(
            "bob",
            "B",
            "adopt",
            require=False,
            alias="empty",
            object_id=local,
            version_id="v1",
            policy="fixed",
            work_ids=[],
        ),
    ]
    ev.check(
        "wrong_object_work_project_and_empty_scope_rejected",
        [r["ok"] for r in responses],
        [False] * len(responses),
    )
    partial = ev.call(
        "bob",
        "B",
        "adopt",
        require=False,
        alias="partial",
        object_id=local,
        version_id="v1",
        policy="fixed",
        work_ids=["B::work", "B::other-work"],
    )
    ev.check(
        "partial_multiwork_declaration_has_no_partial_effect",
        not partial["ok"] and before == {k: ev.state()[k] for k in before},
    )
    revise(ev)
    denied = ev.call(
        "bob",
        "B",
        "adopt_version",
        require=False,
        alias="input",
        work_id="B::work",
        version_id="v1",
    )
    ev.check("superseded_work_binding_update_is_rejected", denied["ok"], False)


RUNNERS = {
    "publication_only": publication_only,
    "replacement_fixed": lambda ev: replacement(ev, False),
    "replacement_current": lambda ev: replacement(ev, True),
    "late_information": late_information,
    "scope_controls": scope_controls,
}


def run_group(group, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    ev = Evidence(group, output)
    error = None
    try:
        RUNNERS[group](ev)
    except Exception:
        error = traceback.format_exc()
    for name in CHECKS[group]:
        if not any(c["name"] == name for c in ev.checks):
            ev.checks.append({"name": name, "passed": False, "not_executed": True})
    result = {
        "group": group,
        "construction_error": error,
        "checks": ev.checks,
        "calls": ev.calls,
        "observations": ev.observations,
        "evaluations": ev.evaluations,
        "passed": error is None and all(c["passed"] for c in ev.checks),
    }
    if ev.world:
        write_json(output / "final-state.json", ev.state())
        result["immutable_file_sha256"] = ev.files()
    write_json(output / "report.json", result)
    return result


def run(output, workers=4):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    identity = code_identity()
    started = datetime.now(timezone.utc).isoformat()
    write_json(output / "protocol.json", PROTOCOL)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda group: run_group(group, output / group), CHECKS))
    summary = {
        "source_before": identity,
        "source_after": code_identity(),
        "script_sha256": __import__("hashlib").sha256(Path(__file__).read_bytes()).hexdigest(),
        "protocol": PROTOCOL,
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "groups": results,
        "passed_groups": sum(r["passed"] for r in results),
        "passed_checks": sum(c["passed"] for r in results for c in r["checks"]),
        "total_checks": sum(len(r["checks"]) for r in results),
        "not_executed": sum(c["not_executed"] for r in results for c in r["checks"]),
    }
    write_json(output / "report.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    arguments = parser.parse_args()
    result = run(arguments.output, arguments.workers)
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("passed_groups", "passed_checks", "total_checks", "not_executed")
            },
            ensure_ascii=False,
        )
    )
    raise SystemExit(0 if result["passed_groups"] == len(CHECKS) else 1)
