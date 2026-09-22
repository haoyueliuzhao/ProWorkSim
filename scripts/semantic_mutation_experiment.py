"""E5: seven predeclared semantic mutants, each in its own Python process.

These are purposeful negative controls of named checks, not a mutation-score
estimate or independent proof of recovery. No production file is modified.
"""

import argparse
import copy
import hashlib
import inspect
import json
import subprocess
import sys
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core import conditions, rules, transitions, visibility, work
from proworksim.core.references import ApplicabilityContext
from proworksim.core.types import CheckStatus
from proworksim.storage import atomic_write, json_bytes

from bounded_state_experiment import initial

MUTANTS = {
    "grant_v2_also_v3": {
        "must_fail": "grant_v2_does_not_reveal_v3",
        "injection": "Wrap core.visibility.grant_version: a v2 grant also executes the same grant for v3.",
    },
    "reply_resolves_other_work": {
        "must_fail": "reply_has_no_effect_on_other_work",
        "injection": "Wrap core.conditions.apply_response: a reply to A also fabricates and applies an evidence reply to B.",
    },
    "global_latest_applicability": {
        "must_fail": "old_context_uses_its_pinned_credential",
        "injection": "Wrap core.rules.registered_applicability to substitute the artifact current_version for the supplied version.",
    },
    "approval_ignores_predecessor": {
        "must_fail": "approval_requires_current_predecessor",
        "injection": "Wrap core.work.approve_submission: temporarily remove dependency edges during its checks, then restore them.",
    },
    "duplicate_event_formal_effect": {
        "must_fail": "duplicate_event_has_one_formal_effect",
        "injection": "Wrap PublicationWorld._drain_events: when the queued review event already has a committed operation, append another approved submission for that same reviewed artifact version after the normal runner, with a new submission ID; persist this extra effect while deliberately bypassing the normal commit boundary.",
    },
    "derive_writes_primary_fact": {
        "must_fail": "derive_cannot_change_primary_fact",
        "injection": "In an isolated process remove only execute_transition's Derive-primary-region guard, keeping frame and history checks.",
    },
    "revision_rewrites_old_answer": {
        "must_fail": "revision_preserves_historical_answer",
        "injection": "Wrap core.work.revise_requirement: rewrite an earlier submission answer after the real revision.",
    },
}


class CheckFailure(AssertionError):
    def __init__(self, name, evidence):
        super().__init__(name)
        self.name, self.evidence = name, evidence


def require(name, condition, evidence):
    if not condition:
        raise CheckFailure(name, evidence)
    return evidence


def inject(name, capture):
    """Process-local monkeypatches; frozen definitions run before any scenario."""

    def activated():
        capture["injection_activated"] = True

    if name == "grant_v2_also_v3":
        original = visibility.grant_version

        def grant(state, aid, vid, actor, reason):
            result = original(state, aid, vid, actor, reason)
            if vid == "v2":
                activated()
                original(state, aid, "v3", actor, reason)
            return result

        visibility.grant_version = grant
    elif name == "reply_resolves_other_work":
        original = conditions.apply_response

        def response(state, payload):
            result = original(state, payload)
            if payload["work_item_id"] == "A":
                activated()
                fabricated = {
                    **payload,
                    "response_id": "mutant-extra-B",
                    "request_id": "request-B",
                    "work_item_id": "B",
                    "reference": {"artifact_id": "doc-B", "version_id": "v1"},
                }
                original(state, fabricated)
            return result

        conditions.apply_response = response
    elif name == "global_latest_applicability":
        original = rules.registered_applicability

        def latest(state, reference, context):
            activated()
            aid = reference.get("artifact_id", reference.get("object_id"))
            return original(
                state,
                {"artifact_id": aid, "version_id": state["artifacts"][aid]["current_version"]},
                context,
            )

        rules.registered_applicability = latest
    elif name == "approval_ignores_predecessor":
        original = work.approve_submission

        def approve(state, actor, wid, sid):
            item = state["work_items"][wid]
            saved = item.get("dependencies", [])
            if saved:
                activated()
            item["dependencies"] = []
            try:
                return original(state, actor, wid, sid)
            finally:
                item["dependencies"] = saved

        work.approve_submission = approve
    elif name == "duplicate_event_formal_effect":
        from proworksim.domains.publication import PublicationWorld

        original = PublicationWorld._drain_events

        def drain(self):
            repeated = [
                copy.deepcopy(e)
                for e in self.state["events"]
                if e["kind"] == "review"
                and f"event:{e['event_id']}" in self.state.get("operation_commits", {})
            ]
            result = original(self)
            for event in repeated:
                activated()
                item = self.state["work_items"][event["payload"]["work_item_id"]]
                prior = next(
                    x
                    for x in item["submissions"]
                    if x["submission_id"] == event["payload"]["submission_id"]
                )
                duplicate = copy.deepcopy(prior)
                duplicate["submission_id"] += "-mutant-duplicate"
                item["submissions"].append(duplicate)
                self.store.save(self.state)
            return result

        PublicationWorld._drain_events = drain
    elif name == "derive_writes_primary_fact":
        source = inspect.getsource(transitions.execute_transition)
        guard = '        if any(not within(path, frame.derived_paths) for path in changed_paths(applied, state)):\n            raise ValueError("Derive changed a primary fact outside its projection scope")\n'
        if source.count(guard) != 1:
            raise RuntimeError("Frozen mutation target no longer matches the derive guard")
        namespace = dict(transitions.__dict__)
        exec(compile(source.replace(guard, ""), "<isolated-E5-derive-mutant>", "exec"), namespace)
        modified = namespace["execute_transition"]

        def derive(*args, **kwargs):
            activated()
            return modified(*args, **kwargs)

        transitions.execute_transition = derive
    elif name == "revision_rewrites_old_answer":
        original = work.revise_requirement

        def revise(state, *args, **kwargs):
            result = original(state, *args, **kwargs)
            for old in result:
                for submission in state["work_items"][old]["submissions"]:
                    activated()
                    submission["answer"] = "silently rewritten by requirement revision"
            return result

        work.revise_requirement = revise
    else:
        raise ValueError(name)


def submit(state, node):
    return work.submit_work(state, "owner", node, {f"doc-{node}": "v1"}, answer=f"original-{node}")


def scenario(name, root):
    assertion = MUTANTS[name]["must_fail"]
    if name == "grant_v2_also_v3":
        state, _ = initial()
        artifact = state["artifacts"]["doc-A"]
        artifact.update(readers=[], version_readers={})
        for version in ("v2", "v3"):
            artifact["versions"][version] = {"logical_time": 0}
        visibility.grant_version(state, "doc-A", "v2", "owner", "grant-exactly-v2")
        seen = {vid: visibility.visible_version(artifact, "owner", 10, vid) for vid in ("v2", "v3")}
        return require(assertion, seen == {"v2": "v2", "v3": None}, seen)
    if name == "reply_resolves_other_work":
        state, _ = initial(True)
        from proworksim.core.projections import rebuild_projections

        rebuild_projections(state)
        before = copy.deepcopy(state["condition_specs"]["condition-B"])
        result = conditions.apply_response(
            state,
            {
                "response_id": "reply-A",
                "request_id": "request-A",
                "work_item_id": "A",
                "requirement_version": 1,
                "responder": "reviewer",
                "purpose": "support",
                "status": "delivered",
                "reference": {"artifact_id": "doc-A", "version_id": "v1"},
            },
        )
        after = state["condition_specs"]["condition-B"]
        return require(
            assertion,
            before == after,
            {
                "other_condition_before": before,
                "other_condition_after": after,
                "reply_result": result,
            },
        )
    if name == "global_latest_applicability":
        state, _ = initial()
        state["organization"]["grants"].append(
            {"actor_id": "reviewer", "power": "confirm", "subject": "policy"}
        )
        artifact = state["artifacts"]["doc-A"]
        for number in (1, 2, 3):
            vid = f"v{number}"
            artifact["versions"].setdefault(vid, {"logical_time": 0})
            record = {
                "kind": "credential",
                "reference": {"artifact_id": "doc-A", "version_id": vid},
                "project_id": "bounded",
                "requirement_dimension": "policy",
                "requirement_version": number,
                "work_nodes": ["A"],
                "period": None,
                "purpose": "support",
                "effective_at": 0,
                "status": "confirmed",
                "confirmed_by": "reviewer",
                "attestation_ref": f"approval-{number}",
            }
            rules.confirm_credential(state, "reviewer", record["reference"], record)
        artifact["current_version"] = "v3"
        context = ApplicabilityContext("bounded", "A", "policy", 1, "A", None, "support", 10)
        result = rules.registered_applicability(
            state, {"artifact_id": "doc-A", "version_id": "v1"}, context
        )
        return require(assertion, result.status == CheckStatus.PASS, result.to_dict())
    if name == "approval_ignores_predecessor":
        state, _ = initial()
        first = submit(state, "A")
        work.approve_submission(state, "reviewer", "A", first["submission_id"])
        second = submit(state, "B")
        work.revise_requirement(
            state,
            ["A"],
            {"requirements": {"edition": 2}},
            "reviewer",
            "Revise current prerequisite",
        )
        error = None
        try:
            work.approve_submission(state, "reviewer", "B", second["submission_id"])
        except ValueError as exc:
            error = str(exc)
        decision = state["work_items"]["B"]["submissions"][-1]["review"]
        return require(
            assertion,
            error is not None and decision is None,
            {"error": error, "decision": decision},
        )
    if name == "duplicate_event_formal_effect":
        from proworksim.domains.publication import PublicationWorld, SOURCE_REF, compile_publication

        world = PublicationWorld(compile_publication(root / "publication"))

        def act(actor, tool, **arguments):
            output = world.act(actor, tool, arguments)
            if not output["ok"]:
                raise RuntimeError(f"Fixture action {tool} failed: {output}")
            return output["result"]

        act(
            "author",
            "write_file",
            artifact_id="draft",
            content=json.dumps(
                {
                    "title": "Fixture",
                    "body": "READY. Finite mutation witness",
                    "source_ref": SOURCE_REF,
                }
            ),
            dependencies=[SOURCE_REF, {"artifact_id": "editorial_policy", "version_id": "v1"}],
        )
        act("author", "submit", work_item_id="publish-note")
        event = copy.deepcopy(
            next(e for e in world.store.load()["events"] if e["kind"] == "review")
        )
        act("author", "wait", ticks=2)

        def formal(state):
            return {
                key: copy.deepcopy(state.get(key))
                for key in ("work_items", "messages", "access_grants", "attestations", "knowledge")
            }

        before = formal(world.store.load())
        with world.store.lock():
            state = world.store.load()
            state["events"].append(event)
            world.store.save(state)
        act("author", "wait", ticks=1)
        after = formal(world.store.load())

        def count(projection):
            return sum(
                (s.get("review") or {}).get("decision") == "accepted"
                for item in projection["work_items"].values()
                for s in item["submissions"]
            )

        return require(
            assertion,
            before == after and count(after) == 1,
            {
                "formal_projection_equal": before == after,
                "approvals_before": count(before),
                "approvals_after": count(after),
                "event_id": event["event_id"],
            },
        )
    if name == "derive_writes_primary_fact":
        state = {"base": 0, "view": 0}
        before = copy.deepcopy(state)
        frame = transitions.ActionFrame("derive-primary-probe", (("base",),), (("view",),))
        error = None
        try:
            transitions.execute_transition(
                state, frame, lambda: None, lambda value: value.update(base=1)
            )
        except ValueError as exc:
            error = str(exc)
        return require(
            assertion,
            state == before and error is not None,
            {"before": before, "after": state, "error": error},
        )
    if name == "revision_rewrites_old_answer":
        state, _ = initial()
        first = submit(state, "A")
        before = copy.deepcopy(first["answer"])
        work.revise_requirement(
            state,
            ["A"],
            {"requirements": {"edition": 2}},
            "reviewer",
            "Revision must not edit submitted answers",
        )
        answer = state["work_items"]["A"]["submissions"][0]["answer"]
        return require(
            assertion, before == answer, {"answer_before": before, "answer_after": answer}
        )
    raise ValueError(name)


def child(name, mutated, output):
    capture = {
        "case": name,
        "mutated": mutated,
        "injection_activated": False,
        "must_fail": MUTANTS[name]["must_fail"],
    }
    try:
        if mutated:
            inject(name, capture)
        with tempfile.TemporaryDirectory(prefix="proworksim-e5-") as tmp:
            evidence = scenario(name, Path(tmp))
        capture.update(outcome="PASS", evidence=evidence)
    except CheckFailure as exc:
        capture.update(outcome="NAMED_ASSERTION_FAILED", assertion=exc.name, evidence=exc.evidence)
    except Exception as exc:
        capture.update(
            outcome="ERROR", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc()
        )
    atomic_write(output, json_bytes(capture))
    print(json.dumps(capture, ensure_ascii=False))


def run_pair(name, output):
    results = {}
    for mode in ("control", "mutant"):
        path = output / f"{name}-{mode}.json"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--child",
            name,
            "--child-output",
            str(path),
        ]
        if mode == "mutant":
            command.append("--mutated")
        try:
            process = subprocess.run(command, capture_output=True, text=True, timeout=120)
            log = {
                "exit_code": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
            }
        except subprocess.TimeoutExpired as error:
            log = {
                "exit_code": None,
                "stdout": str(error.stdout or ""),
                "stderr": str(error.stderr or ""),
                "timeout_seconds": 120,
            }
        atomic_write(output / f"{name}-{mode}-process.json", json_bytes(log))
        results[mode] = (
            json.loads(path.read_text()) if path.exists() else {"outcome": "PROCESS_ERROR", **log}
        )
        if mode == "control" and results[mode]["outcome"] != "PASS":
            results["mutant"] = {"outcome": "NOT_RUN_CONTROL_FAILED"}
            break
    control, mutant = results["control"], results["mutant"]
    killed = (
        control["outcome"] == "PASS"
        and mutant["outcome"] == "NAMED_ASSERTION_FAILED"
        and mutant.get("assertion") == MUTANTS[name]["must_fail"]
        and mutant.get("injection_activated")
    )
    return {
        "name": name,
        **MUTANTS[name],
        **results,
        "verdict": "killed"
        if killed
        else "survivor"
        if control["outcome"] == mutant["outcome"] == "PASS"
        else "harness_error",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--child", choices=list(MUTANTS))
    parser.add_argument("--child-output", type=Path)
    parser.add_argument("--mutated", action="store_true")
    args = parser.parse_args()
    if args.child:
        child(args.child, args.mutated, args.child_output)
        return
    if args.output is None:
        parser.error("--output is required")
    args.output.mkdir(parents=True, exist_ok=False)
    protocol = {
        "experiment": "E5-seven-semantic-negative-controls-v05",
        "mutants": MUTANTS,
        "planned_denominator": 7,
        "isolation": "one fresh subprocess per control or mutant; no source-tree writes",
        "interpretation": "sensitivity of seven predeclared checks, not arbitrary-bug coverage or a recovery proof",
        "code_before": code_identity(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture_script_sha256": hashlib.sha256(
            Path(__file__).with_name("bounded_state_experiment.py").read_bytes()
        ).hexdigest(),
    }
    atomic_write(args.output / "protocol.json", json_bytes(protocol))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda name: run_pair(name, args.output), MUTANTS))
    report = {
        **protocol,
        "code_after": code_identity(),
        "cases": rows,
        "controls_passed": sum(r["control"]["outcome"] == "PASS" for r in rows),
        "killed": sum(r["verdict"] == "killed" for r in rows),
        "survivors": [r["name"] for r in rows if r["verdict"] == "survivor"],
        "harness_errors": [r["name"] for r in rows if r["verdict"] == "harness_error"],
        "model_calls": 0,
        "gpu_used": False,
    }
    atomic_write(args.output / "report.json", json_bytes(report))
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("controls_passed", "killed", "survivors", "harness_errors")
            },
            ensure_ascii=False,
        )
    )
    raise SystemExit(0 if report["controls_passed"] == report["killed"] == 7 else 1)


if __name__ == "__main__":
    main()
