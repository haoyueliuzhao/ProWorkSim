"""Check the process observer with isolated synthetic receipts; grades are not present."""

from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inventory_multitype_v242 import PLAN, save, read_json
from proworksim.software_successor_evidence_v242 import evaluate
from proworksim.software_benchmark_candidates_v054 import reference


def workspace(p, versions, outcomes, locked):
    target = "tests/test_public.py::test_target"
    save(
        p / "decision.json",
        dict(
            original_ordinal=3,
            menu={"evidence": {"E1": {}}},
            anomaly={
                "anomaly_type": "A1",
                "subject": target,
                "affected_work": ["pkg"],
                "evidence_refs": [{"opportunity": 1, "command_id": "command:member_001:1"}],
            },
        ),
    )
    save(p / "mechanism.json", dict(regression_targets=[]))
    src = lambda n: {"object_id": "obj1", "version_id": n}
    save(p / "tree.json", dict(source_reference=src(locked)))
    save(p / "lock.json", dict(terminal_code=reference(p / "tree.json")))
    save(p / "candidate-lock.json", reference(p / "lock.json"))
    events = []
    for i, (version, (actor, outcome, executed)) in enumerate(zip(versions, outcomes, strict=True)):
        selector = {"kind": "pytest", "targets": [target]}
        counts = {
            "tests_run": 1,
            "passed": int(outcome == "passed"),
            "failed": int(outcome == "failed"),
        }
        req = dict(
            hidden_evaluation=False,
            actor_id=actor,
            source_reference=src(version),
            public_test_selection=selector,
        )
        response = dict(
            validation_status="failed" if outcome == "failed" else "verified",
            counts=counts,
            passed=outcome == "passed",
            test_evidence={
                "sessions": [
                    {
                        "root": True,
                        "partial": False,
                        "collection_complete": True,
                        "test_reports": [{"nodeid": target, "phase": "call", "outcome": outcome}],
                    }
                ]
            },
        )
        base = p / "public-test-rpc" / str(i)
        save(base / "request.json", req)
        save(base / "response.json", response)
        events.append(
            dict(
                worker_id=actor,
                decision={"action": "run_tests", "arguments": {"selection": selector}},
                response={
                    "ok": True,
                    "command_id": f"command:{actor}:{4 + i}",
                    "result": {
                        "source_reference": src(version),
                        "passed": response["passed"],
                        "counts": counts,
                        "executed": executed,
                        "selection_normalization": {"executed": selector},
                    },
                },
            )
        )
    save(p / "boundary.json", dict(outcomes=events))


def main():
    a = "member_001"
    b = "member_002"
    results = {}
    cases = [
        ("target_pass", ["v2"], [(a, "passed", True)], "v2", "RESOLVED"),
        (
            "failed_again",
            ["v2", "v3"],
            [(a, "passed", True), (a, "failed", True)],
            "v3",
            "REOPENED",
        ),
        ("foreign_private_pass", ["v2"], [(b, "passed", True)], "v2", "UNKNOWN"),
        ("unexecuted_pass", ["v2"], [(a, "passed", False)], "v2", "UNKNOWN"),
        ("stale_positive", ["v2"], [(a, "passed", True)], "v3", "UNKNOWN"),
    ]
    with tempfile.TemporaryDirectory() as temp:
        for name, versions, observations, locked, expected in cases:
            p = Path(temp) / name
            workspace(p, versions, observations, locked)
            r = evaluate(p)
            assert r["endpoint"] == expected, (name, r["trace"])
            results[name] = [v["state"] for v in r["trace"]]
        p = Path(temp) / "review_retracted"
        workspace(p, [], [], "v2")
        decision = read_json(p / "decision.json")
        decision["anomaly"].update(anomaly_type="A4", subject="independent_current_review")
        save(p / "decision.json", decision)
        outcomes = []
        for i, verdict in enumerate(("accept", "request_changes")):
            review = dict(
                actor_id=a,
                author=b,
                patch_id="patch-4",
                decision=verdict,
                identity=dict(source_reference=dict(object_id="obj1", version_id="v2")),
                task_revisions={"pkg": 0},
            )
            outcomes.append(
                dict(
                    worker_id=a,
                    decision=dict(action="org_review_patch"),
                    response=dict(ok=True, command_id=f"command:{a}:{i + 4}", result=review),
                )
            )
        save(p / "boundary.json", dict(outcomes=outcomes))
        r = evaluate(p)
        assert r["endpoint"] == "REOPENED" and not r["reviews"]
        results[p.name] = [v["state"] for v in r["trace"]]

        p = Path(temp) / "dependency_rejection"
        workspace(p, [], [], "v2")
        decision = read_json(p / "decision.json")
        decision["anomaly"].update(anomaly_type="A2", subject="upstream")
        save(p / "decision.json", decision)
        readiness = dict(
            task_id="pkg", ready=False, gaps=[dict(kind="upstream_not_current", task_id="upstream")]
        )
        outcome = dict(
            worker_id=a,
            decision=dict(action="begin_work", arguments=dict(task_id="pkg")),
            response=dict(
                ok=False,
                command_id=f"command:{a}:4",
                error=dict(rejection=dict(context=dict(readiness=readiness))),
            ),
        )
        save(p / "boundary.json", dict(outcomes=[outcome]))
        r = evaluate(p)
        assert r["last_observed_state"] == "ACTIVE" and r["endpoint"] == "UNKNOWN"
        results[p.name] = [v["state"] for v in r["trace"]]
    save(
        PLAN / "observer-controls.json",
        dict(controls=results, official_scores_read=0, provider_calls=0),
    )


if __name__ == "__main__":
    main()
