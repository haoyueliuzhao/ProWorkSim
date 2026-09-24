"""Real-session diagnostic scope: selected P, unrelated Q, no-condition N."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core.projections import derive_condition_view
from proworksim.core.world import WorldSpec
from proworksim.evaluation import assess_episode
from proworksim.experience import ExperienceRecorder, capture_port
from proworksim.templates.reconciliation import package
from proworksim.world_core import WorldCore

CHECKS = (
    "two_real_unavailable_conditions",
    "canonical_field_only",
    "selected_condition_present",
    "unrelated_condition_excluded",
    "no_condition_stays_empty",
    "repeated_evaluation_equal",
    "world_unchanged",
)
PROTOCOL = {
    "suite": "condition-diagnostic-scope-v0.11",
    "checks": CHECKS,
    "scope": "One real world, three installed projects, two actual unavailable requests; no injected conditions or duplicated work_id field.",
}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    identity = code_identity()
    world = WorldCore.create(
        output / "world",
        WorldSpec(
            world_id="condition-scope",
            actors={"analyst": {}, "reviewer": {}},
            bootstrap_grants=[
                {"actor_id": "reviewer", "scope": "world", "power": "install_project"}
            ],
        ),
    )
    captured, controller = {}, []
    recorder = ExperienceRecorder()
    for pid in ("P", "Q", "N"):
        config = package(project_id=pid, hidden_right=pid != "N", unavailable=pid != "N")
        response = world.session("reviewer", None).call("install_project", package=config)
        controller.append({"project": pid, "response": copy.deepcopy(response)})
        assert response["ok"], response
        captured[pid] = []
        port = capture_port(world.session("analyst", pid), captured[pid])
        if pid != "N":
            observation = port.observe()
            route = (
                next(iter(observation["information_routes"].values()))
                if isinstance(observation["information_routes"], dict)
                else observation["information_routes"][0]
            )
            response = port.call(
                "request_information", route_id=route["route_id"], work_id=pid + "::reconcile"
            )
            assert response["ok"], response
            response = port.call("wait", ticks=1)
            assert response["ok"], response
        for event in captured[pid]:
            recorder.record(event["kind"], event["payload"], worker_id=pid)
    state = copy.deepcopy(world.store.load())
    conditions = state["condition_specs"]
    views = derive_condition_view(state)
    evaluations = {
        pid: assess_episode(world.store, state, recorder.snapshot(), work_ids=[pid + "::reconcile"])
        for pid in ("P", "Q", "N")
    }
    selected = evaluations["P"]["institutional_progress"]["conditions"]
    expected = {
        cid: view
        for cid, view in views.items()
        if conditions[cid]["work_item_id"] == "P::reconcile"
    }
    actuals = {
        "two_real_unavailable_conditions": len(conditions) == 2
        and all(view["status"] == "unavailable" for view in views.values()),
        "canonical_field_only": all(
            "work_item_id" in row and "work_id" not in row for row in conditions.values()
        ),
        "selected_condition_present": selected == expected and len(selected) == 1,
        "unrelated_condition_excluded": not any(
            conditions[cid]["work_item_id"] == "Q::reconcile" for cid in selected
        ),
        "no_condition_stays_empty": evaluations["N"]["institutional_progress"]["conditions"] == {},
        "repeated_evaluation_equal": evaluations["P"]
        == assess_episode(world.store, state, recorder.snapshot(), work_ids=["P::reconcile"]),
        "world_unchanged": state == world.store.load(),
    }
    report = {
        "protocol": PROTOCOL,
        "source_before": identity,
        "source_after": code_identity(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "checks": [
            {"name": name, "actual": actuals[name], "expected": True, "passed": actuals[name]}
            for name in CHECKS
        ],
        "evaluations": evaluations,
        "condition_specs": conditions,
        "condition_views": views,
        "independent_expected_selected": expected,
        "passed": all(actuals.values()),
        "passed_checks": sum(actuals.values()),
        "total_checks": len(CHECKS),
    }
    write(output / "capture.json", captured)
    write(output / "controller.json", controller)
    write(output / "experience.json", recorder.snapshot())
    write(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({key: result[key] for key in ("passed", "passed_checks", "total_checks")}))
    raise SystemExit(0 if result["passed"] else 1)
