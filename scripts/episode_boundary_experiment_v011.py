"""Readable E0/no delivery, E1/S1 wrong, E2/S2 correct boundaries in one world."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.episode import begin_episode, finish_episode, assess_historical_episode
from proworksim.evaluation import assess_episode
from proworksim.experience import capture_port
from proworksim.scenarios import build_scenario, load_scenario, bind_runtime
from proworksim.workers.team_policies import ReportAuthorPolicy
from proworksim.workers.research_review import PublicReportWorker

CHECKS = (
    "empty_episode_unassessed_before",
    "bad_s1_content_failure_before",
    "same_work_actual_s2_passes_now",
    "empty_episode_not_retroactively_successful",
    "s1_not_replaced_by_later_s2",
    "end_state_and_all_versions_readable",
    "independent_bytes_not_hardlinked",
    "exact_experience_intervals",
    "source_instance_and_policy_facts_pinned",
    "termination_not_confused_with_acceptance",
    "historical_repeat_equal",
    "assessment_preserves_live_world",
    "assessment_works_without_live_world",
    "out_of_episode_submission_rejected",
)
PROTOCOL = {
    "suite": "historical-episode-boundary-v0.11",
    "checks": CHECKS,
    "scope": "One real report world with empty E0, wrong S1/E1 and later correct S2/E2 under the same work. Public tool deliveries, independent copied snapshot bytes. No historical reconstruction from the live world's latest submission.",
}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    identity = code_identity()
    spec = load_scenario(
        Path(__file__).resolve().parents[1] / "examples/scenarios-v10/report-direct.json"
    )
    spec["roles"] = [role for role in spec["roles"] if role["policy"] == "report_author"]
    spec["roles"][0]["config"] = {"initial_defects": {"revenue": "body_number"}}
    deployment = build_scenario(spec, output / "world")
    assert deployment.status == "ready", deployment.diagnostics
    captured = {}
    runtime = bind_runtime(deployment, captured=captured)
    world = deployment.world
    kwargs = {
        "work_ids": ["REPORT::research"],
        "work_nodes": ["REPORT::research"],
        "scenario": {"version": spec["version"], "spec": spec},
        "policies": {
            "author": {"class": ReportAuthorPolicy.__name__, "config": spec["roles"][0]["config"]}
        },
    }
    e0 = output / "E0"
    begin_episode(world, e0, experience=runtime.recorder.snapshot(), **kwargs)
    finish_episode(
        world,
        e0,
        experience=runtime.recorder.snapshot(),
        termination={"status": "budget_exhausted", "actions": 0},
    )
    empty_before = assess_historical_episode(e0)
    e1 = output / "E1"
    begin_episode(world, e1, experience=runtime.recorder.snapshot(), **kwargs)
    for _ in range(80):
        result = runtime.step()
        if world.store.load()["work_items"]["REPORT::research"]["submissions"]:
            break
    else:
        raise AssertionError("Declared author failed to produce actual S1")
    runtime.recorder.record(
        "run_boundary", {"status": "boundary_reached", "reason": "First actual submission"}
    )
    one = finish_episode(
        world,
        e1,
        experience=runtime.recorder.snapshot(),
        termination={"status": "boundary_reached", "last_opportunity": result["status"]},
    )
    bad_before = assess_historical_episode(e1)
    e2 = output / "E2"
    kwargs["policies"] = {
        "author": {
            "class": "PublicReportWorker",
            "reason": "Declared subsequent repair policy; not rescue counted for E0 or E1",
        }
    }
    begin_episode(
        world,
        e2,
        experience=runtime.recorder.snapshot(),
        parent_episode_id=one["episode_id"],
        **kwargs,
    )
    direct = []
    port = capture_port(world.session("author", "REPORT"), direct)
    sub = world.store.load()["work_items"]["REPORT::research"]["submissions"][-1]
    response = port.call(
        "withdraw",
        work_id="REPORT::research",
        submission_id=sub["submission_id"],
        reason="Later separately attributed repair episode",
    )
    assert response["ok"], response
    worker = PublicReportWorker(port)
    prepared = worker.prepare("REPORT::research")
    delivered = worker.deliver("REPORT::research", *prepared)
    # The later program uses only its public port. This is a separate episode,
    # and must never improve the earlier model/worker episode's attribution.
    for event in direct:
        runtime.recorder.record(event["kind"], event["payload"], worker_id="later-author")
    runtime.recorder.record(
        "run_boundary", {"status": "boundary_reached", "reason": "Later correct submission"}
    )
    two = finish_episode(
        world,
        e2,
        experience=runtime.recorder.snapshot(),
        termination={"status": "boundary_reached", "provider": "later-public-program"},
    )
    before = copy.deepcopy(world.store.load())
    current = assess_episode(
        world.store, before, runtime.recorder.snapshot(), work_ids=["REPORT::research"]
    )
    empty_after = assess_historical_episode(e0)
    bad_after = assess_historical_episode(e1)
    good = assess_historical_episode(e2)

    def evaluation(value):
        return value["content_quality"]["submissions"][0]["evaluation"]

    fixed_one = one["fixed_deliveries"]["REPORT::research"]
    fixed_two = two["fixed_deliveries"]["REPORT::research"]
    state_path = e1 / "end" / "control" / "state.json"
    state = json.loads(state_path.read_text())
    files = [entry for entry in one["end"]["files"] if entry["availability"] == "available"]
    readable = all((e1 / "end" / entry["path"]).read_bytes() for entry in files)
    independent = all(
        (e1 / "end" / entry["path"]).stat().st_ino
        != world.store.version_path(before["artifacts"][entry["object_id"]], entry["version_id"])
        .stat()
        .st_ino
        for entry in files
    )
    invalid = assess_historical_episode(
        e1,
        independent_targets=[
            {
                "target_id": "attempt-later-S2",
                "work_id": "REPORT::research",
                "submission_id": fixed_two["submission_id"],
                "path": ["report"],
                "expected": None,
            }
        ],
    )
    # Rename the live directory only after all actual actions, then restore it;
    # historical assessment never receives or consults its location.
    detached = output / "live-world-temporarily-unavailable"
    (output / "world").rename(detached)
    try:
        without_live = assess_historical_episode(e1)
    finally:
        detached.rename(output / "world")
    actuals = {
        "empty_episode_unassessed_before": evaluation(empty_before)["status"] == "unassessed",
        "bad_s1_content_failure_before": evaluation(bad_before)["status"] == "content_failure",
        "same_work_actual_s2_passes_now": evaluation(current)["status"] == "pass"
        and evaluation(good)["status"] == "pass"
        and fixed_one["submission_id"] != fixed_two["submission_id"],
        "empty_episode_not_retroactively_successful": empty_before == empty_after
        and evaluation(empty_after)["status"] == "unassessed",
        "s1_not_replaced_by_later_s2": bad_before == bad_after
        and evaluation(bad_after)["submission_id"] == fixed_one["submission_id"],
        "end_state_and_all_versions_readable": bool(readable)
        and state["work_items"]["REPORT::research"]["submissions"][-1]["submission_id"]
        == fixed_one["submission_id"],
        "independent_bytes_not_hardlinked": independent,
        "exact_experience_intervals": one["experience"]["end"] == two["experience"]["start"]
        and bad_after["historical_episode"]["experience_interval"]
        == {"start": one["experience"]["start"], "end": one["experience"]["end"]},
        "source_instance_and_policy_facts_pinned": one["identity"] == two["identity"]
        and one["policies"] != two["policies"]
        and one["scenario"] == two["scenario"],
        "termination_not_confused_with_acceptance": one["termination"]["status"]
        == "boundary_reached"
        and fixed_one["review"] is None
        and evaluation(bad_after)["status"] == "content_failure",
        "historical_repeat_equal": bad_after == assess_historical_episode(e1),
        "assessment_preserves_live_world": world.store.load() == before,
        "assessment_works_without_live_world": without_live == bad_after,
        "out_of_episode_submission_rejected": invalid["assessment_execution"]["status"]
        == "source_unavailable",
    }
    report = {
        "protocol": PROTOCOL,
        "source_before": identity,
        "source_after": code_identity(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "checks": [
            {"name": key, "actual": actuals[key], "expected": True, "passed": actuals[key]}
            for key in CHECKS
        ],
        "assessments": {
            "E0_before": empty_before,
            "E0_after": empty_after,
            "E1_before": bad_before,
            "E1_after": bad_after,
            "E2": good,
            "current_progress": current,
            "out_of_scope_attempt": invalid,
        },
        "fixed_submissions": {"E1": fixed_one, "E2": fixed_two},
        "passed": all(actuals.values()),
        "passed_checks": sum(actuals.values()),
        "total_checks": len(CHECKS),
        "later_delivery": delivered,
    }
    write(output / "capture.json", {"first": captured, "later": direct})
    write(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({key: result[key] for key in ("passed", "passed_checks", "total_checks")}))
    raise SystemExit(0 if result["passed"] else 1)
