"""P2: one actual publication at five factual stages and four declared relations.

This is an informed mechanism driver, not a public worker. All business actions
use real sessions. The sole trusted test-controller mutation redelivers the exact
already committed event to the runner; it neither fabricates work nor changes
source bytes. Each isolated two-project world has its own initial prefix.
"""

import argparse
import copy
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core.world import WorldSpec
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.world_core import WorldCore

STAGES = ("before_read", "after_read", "output_ready", "pending", "accepted")
RELATIONS = ("notice", "revision", "maintenance", "fixed")
CHECKS = (
    "actual_source_version_and_declared_stage",
    "effect_matches_predeclared_relation",
    "obligation_count_and_lineage_match_policy",
    "downstream_bytes_and_adoption_history_unchanged",
    "original_submission_and_approval_history_preserved",
    "source_project_work_unaffected",
    "past_observations_preserved",
    "repeated_publish_has_no_second_formal_effect",
    "same_event_redelivery_has_no_second_formal_effect",
)
PROTOCOL = {
    "suite": "publication-maintenance-P2-v0.8",
    "measurement_version": "actual-observations-v2",
    "observation_evidence": "observe() is read-only and does not append state.observations. Capture its actual pre-event return and exact stage tool returns in files immediately, require nonempty current-work context, then compare the retained file bytes and hashes after the event. Earlier draft/draft2 empty-state-prefix checks do not provide this coverage.",
    "stages": STAGES,
    "relations": RELATIONS,
    "checks": CHECKS,
    "expected_effects": {
        "notice": {stage: "notice" for stage in STAGES},
        "revision": {stage: "revise" for stage in STAGES},
        "maintenance": {
            stage: "successor" if stage == "accepted" else "revise" for stage in STAGES
        },
        "fixed": {stage: "ignore" for stage in STAGES},
    },
    "source": "Project A JSON rate v1=6; one worker write creates draft v2=8; explicit scoped release triggers B rules",
    "stage_facts": {
        "before_read": "No exact-work read or output edit",
        "after_read": "Actual public read tagged with B work and requirement version",
        "output_ready": "Actual public write of independently expected JSON rate=6; no submission",
        "pending": "Real submitted fixed version without review",
        "accepted": "Real authorized acceptance of that fixed submission",
    },
    "legal_actions": [
        "install_project",
        "share",
        "adopt",
        "read_object",
        "write_object",
        "publish",
        "submit",
        "approve",
    ],
    "legal_alternatives": "Each relation is an explicit project policy, not a required universal response; no equality between final states of different stages or policies is demanded",
    "reject_or_wait": "Wrong scope/policy actions are unit-tested separately; any setup/action/event error here fails the case and leaves unexecuted checks explicit",
    "independent_expectations": {
        "old_rate": 6,
        "new_rate": 8,
        "new_obligations_for_notice_or_ignore": 0,
        "new_obligations_for_revision_or_successor": 1,
    },
    "comparison_scope": "B immutable/mirror bytes and work adoption history; original submission protected fields/review; A work facts; exact prior observations; formal event/journal effects on replay",
    "redelivery": "Trusted controller copies event_id/kind/at/payload from the real committed event history into the queue; shared runner recover performs actual idempotent delivery",
    "limitations": [
        "One world, two projects, single writer per isolated case; independent worlds are parallelized",
        "Output-ready names a declared edit stage, not a general content-quality certificate",
        "No new model/API/GPU/training, arbitrary event reasoning or controller-created second-round work",
        "Historical review stays fixed; revision may change only current_applicability/invalidation metadata on an older pending submission",
    ],
}


def write_json(path, value):
    atomic_write(path, json_bytes(value))
    return {"path": str(path), "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}


def must(session, tool, **arguments):
    value = session.call(tool, **arguments)
    if (
        not value.get("ok")
        or value.get("pending_event_errors")
        or value.get("event_delivery_errors")
    ):
        raise AssertionError({"tool": tool, "arguments": arguments, "response": value})
    return value["result"]


def rules(relation, source):
    base = {
        "source": {"object_id": source, "source_project": "A"},
        "work_nodes": ["analysis"],
        "actor": "manager",
    }
    effects = [
        (list(STAGES), {"notice": "notice", "revision": "revise", "fixed": "ignore"}.get(relation))
    ]
    if relation == "maintenance":
        effects = [(list(STAGES[:-1]), "revise"), (["accepted"], "successor")]
    return [
        {
            **base,
            "rule_id": relation + "-" + effect,
            "when": stages,
            "effect": effect,
            **(
                {
                    "updates": {
                        "requirements": {"source_change": "Reassess the newly released source"}
                    }
                }
                if effect in {"revise", "successor"}
                else {}
            ),
        }
        for stages, effect in effects
    ]


def setup(path, stage, relation):
    world = WorldCore.create(
        path,
        WorldSpec(
            world_id="maintenance-p2",
            actors={actor: {} for actor in ("alice", "bob", "manager")},
            publication_policy="explicit",
            bootstrap_grants=[
                {"actor_id": "manager", "scope": "world", "power": "install_project"}
            ],
        ),
    )
    a = {
        "project_id": "A",
        "goal": "Publish one finite source",
        "participants": ["alice", "manager"],
        "objects": [
            {"alias": "source", "filename": "source.json", "owner": "alice", "data": {"rate": 6}}
        ],
        "works": [
            {
                "work_id": "unrelated",
                "owner": "alice",
                "deliverable_contract": {"min_files": 1, "max_files": 1},
            }
        ],
        "grants": [
            {"actor_id": "alice", "power": power, "subject": "artifact"}
            for power in ("share", "publish")
        ],
    }
    must(world.session("manager"), "install_project", package=a)
    source = world.store.load()["workspaces"]["A"]["source"]
    b = {
        "project_id": "B",
        "goal": "Consume declared source",
        "participants": ["bob", "manager"],
        "objects": [
            {
                "alias": "report",
                "filename": "report.json",
                "owner": "bob",
                "data": {},
                "deliverable_role": "report",
            }
        ],
        "works": [
            {
                "work_id": "analysis",
                "owner": "bob",
                "deliverables": ["report"],
                "approval_policy": "review",
                "requirements": {"source_change": "Original fixed task"},
            }
        ],
        "grants": [
            {
                "actor_id": "bob",
                "power": "adopt",
                "subject": "artifact",
                "work_nodes": ["analysis"],
            },
            {
                "actor_id": "manager",
                "power": "approve",
                "subject": "deliverable",
                "work_nodes": ["analysis"],
            },
            {
                "actor_id": "manager",
                "power": "revise_requirement",
                "subject": "requirements",
                "work_nodes": ["analysis"],
            },
        ],
        "maintenance_rules": rules(relation, source),
    }
    must(world.session("manager"), "install_project", package=b)
    alice, bob = world.session("alice", "A"), world.session("bob", "B")
    stage_calls = []

    def stage_call(session, tool, **arguments):
        response = session.call(tool, **arguments)
        stage_calls.append(
            {
                "actor_id": session.actor_id,
                "project_id": session.project_id,
                "tool": tool,
                "arguments": copy.deepcopy(arguments),
                "response": copy.deepcopy(response),
            }
        )
        if not response.get("ok") or response.get("pending_event_errors"):
            raise AssertionError(stage_calls[-1])
        return response["result"]

    must(
        alice,
        "share",
        object_id=source,
        version_id="v1",
        target_project="B",
        actor_ids=["bob"],
        follow_updates=True,
    )
    must(
        bob,
        "adopt",
        alias="input",
        object_id=source,
        version_id="v1",
        policy="fixed",
        work_ids=["analysis"],
    )
    if stage != "before_read":
        stage_call(bob, "read_object", alias="input", version_id="v1", work_id="analysis")
    if stage in {"output_ready", "pending", "accepted"}:
        ref = {"object_id": source, "version_id": "v1"}
        stage_call(
            bob,
            "write_object",
            alias="report",
            data={"rate": 6, "source_ref": ref},
            dependencies=[ref],
            work_id="analysis",
        )
    if stage in {"pending", "accepted"}:
        sub = stage_call(bob, "submit", work_id="analysis", artifacts=["report"])
        if stage == "accepted":
            stage_call(
                world.session("manager", "B"),
                "approve",
                work_id="analysis",
                submission_id=sub["submission_id"],
            )
    write_json(path.parent / "initial-observation.json", bob.observe())
    write_json(path.parent / "stage-calls.json", stage_calls)
    must(alice, "write_object", alias="source", data={"rate": 8})
    return world, source


def downstream_files(world):
    result = {}
    for oid, artifact in world.store.load()["artifacts"].items():
        if artifact["project_id"] == "B":
            for vid in artifact["versions"]:
                result[f"{oid}/{vid}"] = digest(
                    world.store.version_path(artifact, vid).read_bytes()
                )
            result[oid + "/mirror"] = digest(world.store.current_path(artifact).read_bytes())
    return result


def formal(state):
    return {
        key: copy.deepcopy(state.get(key))
        for key in (
            "work_items",
            "work_replacements",
            "projects",
            "artifacts",
            "adoptions",
            "maintenance_impacts",
            "messages",
            "releases",
            "shares",
            "requirement_events",
            "event_history",
        )
    }


def run_case(output, stage, relation):
    path = output / f"{stage}-{relation}"
    path.mkdir(parents=True)
    checks, evidence, error = [], {}, None

    def check(name, observed, expected=True):
        checks.append(
            {
                "name": name,
                "observed": observed,
                "expected": expected,
                "passed": observed == expected,
                "not_executed": False,
            }
        )

    try:
        world, source = setup(path / "world", stage, relation)
        before, before_files = world.store.load(), downstream_files(world)
        observation_path = path / "initial-observation.json"
        stage_calls_path = path / "stage-calls.json"
        observation_bytes, call_bytes = observation_path.read_bytes(), stage_calls_path.read_bytes()
        captured_observation = json.loads(observation_bytes)
        captured_calls = json.loads(call_bytes)
        evidence["actual_pre_event_observation"] = {
            "path": str(observation_path),
            "sha256": digest(observation_bytes),
            "bytes": len(observation_bytes),
        }
        evidence["actual_stage_calls"] = {
            "path": str(stage_calls_path),
            "sha256": digest(call_bytes),
            "bytes": len(call_bytes),
        }
        evidence["before"] = write_json(path / "before.json", before)
        release_result = must(
            world.session("alice", "A"),
            "publish",
            alias="source",
            version_id="v2",
            target_projects=["A", "B"],
        )
        after = world.store.load()
        evidence["after"] = write_json(path / "after.json", after)
        impacts = list(after.get("maintenance_impacts", {}).values())
        if len(impacts) != 1:
            raise AssertionError({"expected_impacts": 1, "observed_impacts": impacts})
        impact, effect = impacts[0], PROTOCOL["expected_effects"][relation][stage]
        check(
            "actual_source_version_and_declared_stage",
            [impact["payload"]["source"], impact["payload"]["stage"]],
            [{"object_id": source, "version_id": "v2"}, stage],
        )
        notifications = [
            message
            for message in after["messages"][len(before["messages"]) :]
            if isinstance(message.get("body"), dict)
            and message["body"].get("impact_id") == impact["payload"]["impact_id"]
        ]
        check(
            "effect_matches_predeclared_relation",
            [
                impact["result"]["effect"],
                impact["result"]["outcome"],
                len(notifications),
                all(
                    message["sender"] == "manager"
                    and message["recipients"] == ["bob"]
                    and message["project_id"] == "B"
                    and message["body"]["effect"] == effect
                    for message in notifications
                ),
            ],
            [
                effect,
                "ignored" if effect == "ignore" else "applied",
                0 if effect == "ignore" else 1,
                True,
            ],
        )
        new = set(after["work_items"]) - set(before["work_items"])
        lineage = (
            len(new) == (effect in {"revise", "successor"})
            and all(after["work_items"][wid]["node_id"] == "B::analysis" for wid in new)
            and (("B::analysis" in after["work_replacements"]) == (effect == "revise"))
        )
        check("obligation_count_and_lineage_match_policy", lineage)
        check(
            "downstream_bytes_and_adoption_history_unchanged",
            downstream_files(world) == before_files and after["adoptions"] == before["adoptions"],
        )
        expected_subs = copy.deepcopy(before["work_items"]["B::analysis"]["submissions"])
        if effect == "revise":
            for submission in expected_subs:
                submission["current_applicability"] = "superseded_requirements"
                if submission.get("review") is None:
                    submission["invalidated"] = True
                    submission["invalidation_reason"] = impact["payload"]["impact_id"]
        check(
            "original_submission_and_approval_history_preserved",
            after["work_items"]["B::analysis"]["submissions"],
            expected_subs,
        )
        check(
            "source_project_work_unaffected",
            after["work_items"]["A::unrelated"],
            before["work_items"]["A::unrelated"],
        )
        captured_work = captured_observation.get("work_items", {}).get("B::analysis", {})
        expected_status = {
            "before_read": "open",
            "after_read": "open",
            "output_ready": "in_progress",
            "pending": "in_review",
            "accepted": "accepted",
        }[stage]
        expected_actions = {
            "before_read": [],
            "after_read": ["read_object"],
            "output_ready": ["read_object", "write_object"],
            "pending": ["read_object", "write_object", "submit"],
            "accepted": ["read_object", "write_object", "submit", "approve"],
        }[stage]
        check(
            "past_observations_preserved",
            {
                "nonempty_actual_work_observation": bool(captured_work),
                "captured_work_context": [
                    captured_work.get("work_item_id"),
                    captured_work.get("requirement_version"),
                    captured_work.get("status"),
                ],
                "captured_successful_stage_actions": [
                    row["tool"] for row in captured_calls if row["response"].get("ok")
                ],
                "old_source_versions_in_captured_observation": captured_observation.get(
                    "objects", {}
                )
                .get(source, {})
                .get("versions"),
                "captured_bytes_retained": observation_path.read_bytes() == observation_bytes
                and stage_calls_path.read_bytes() == call_bytes,
                "captured_hashes_retained": digest(observation_path.read_bytes())
                == evidence["actual_pre_event_observation"]["sha256"]
                and digest(stage_calls_path.read_bytes())
                == evidence["actual_stage_calls"]["sha256"],
            },
            {
                "nonempty_actual_work_observation": True,
                "captured_work_context": ["B::analysis", 1, expected_status],
                "captured_successful_stage_actions": expected_actions,
                "old_source_versions_in_captured_observation": ["v1"],
                "captured_bytes_retained": True,
                "captured_hashes_retained": True,
            },
        )
        old_formal = formal(after)
        again = must(
            world.session("alice", "A"),
            "publish",
            alias="source",
            version_id="v2",
            target_projects=["A", "B"],
        )
        check(
            "repeated_publish_has_no_second_formal_effect",
            not again["created"]
            and again["release"] == release_result["release"]
            and formal(world.store.load()) == old_formal,
        )
        history = next(
            event
            for event in world.store.load()["event_history"]
            if event.get("payload", {}).get("impact_id") == impact["payload"]["impact_id"]
        )
        duplicate = {
            key: copy.deepcopy(history[key]) for key in ("event_id", "kind", "at", "payload")
        }
        with world.store.lock():
            replay = world.store.load()
            replay["events"].append(duplicate)
            world.store.save(replay)
        before_replay = world.store.load()
        resumed = world.recover()
        end = world.store.load()
        check(
            "same_event_redelivery_has_no_second_formal_effect",
            not resumed["pending_event_errors"]
            and not resumed["event_delivery_errors"]
            and end["events"] == []
            and formal(end) == old_formal
            and end["state_revision"] == before_replay["state_revision"]
            and end["operation_commits"] == before_replay["operation_commits"],
        )
        evidence["replayed_event"] = duplicate
        evidence["final"] = write_json(path / "final.json", end)
        evidence["file_hashes"] = downstream_files(world)
    except Exception:
        error = traceback.format_exc()
    names = {check["name"] for check in checks}
    checks.extend(
        {"name": name, "passed": False, "not_executed": True}
        for name in CHECKS
        if name not in names
    )
    result = {
        "stage": stage,
        "relation": relation,
        "checks": checks,
        "evidence": evidence,
        "error": error,
        "passed": error is None and all(check["passed"] for check in checks),
    }
    write_json(path / "result.json", result)
    return result


def run(output, workers=4):
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "protocol.json", PROTOCOL)
    before = code_identity()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(
            pool.map(
                lambda pair: run_case(output, *pair),
                [(stage, relation) for stage in STAGES for relation in RELATIONS],
            )
        )
    report = {
        "protocol": PROTOCOL,
        "source_before": before,
        "source_after": code_identity(),
        "script_sha256": digest(Path(__file__).read_bytes()),
        "cases": rows,
        "case_count": len(rows),
        "passed_cases": sum(row["passed"] for row in rows),
        "check_count": sum(len(row["checks"]) for row in rows),
        "passed_checks": sum(check["passed"] for row in rows for check in row["checks"]),
        "not_executed": sum(check["not_executed"] for row in rows for check in row["checks"]),
        "model_calls": 0,
        "gpu_used": False,
        "training_performed": False,
    }
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", default=4, type=int)
    args = parser.parse_args()
    report = run(args.output, args.workers)
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "case_count",
                    "passed_cases",
                    "check_count",
                    "passed_checks",
                    "not_executed",
                )
            }
        )
    )
    raise SystemExit(0 if report["passed_cases"] == report["case_count"] else 1)
