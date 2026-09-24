"""Finite reward abuse controls; no model training or model-attack claim."""

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.episode import begin_episode, finish_episode, assess_historical_episode
from proworksim.experience import ExperienceRecorder, capture_port
from proworksim.rewards import REWARD_VERSION, episode_reward
from proworksim.scenarios import build_scenario, load_scenario
from proworksim.staff_runtime import StaffRuntime
from proworksim.templates.research_review import package
from proworksim.workers.research_review import PublicReportWorker

GROUPS = {
    "positive": ("real_good_delivery", "eligible_reward_one", "diagnostic_unchanged"),
    "empty": (
        "actual_empty_submission_refused",
        "no_submission_fabricated",
        "failure_kept_with_zero",
    ),
    "label_only": (
        "wrong_delivery_authorized_approval",
        "independent_content_still_fails",
        "label_does_not_create_reward",
    ),
    "repeat_publish": ("three_real_publication_calls", "one_formal_release", "no_extra_reward"),
    "always_wait": (
        "real_worker_waits_without_actions",
        "obligation_still_unfinished",
        "waiting_failure_kept_with_zero",
    ),
    "later_success": (
        "later_real_success_exists",
        "earlier_failure_not_rewritten",
        "earlier_reward_stays_zero",
    ),
    "tests_tampered": (
        "actual_editable_tests_pass",
        "independent_business_check_fails",
        "tampering_failure_kept_with_zero",
    ),
}
PROTOCOL = {
    "suite": "reward-contract-v0.11",
    "groups": GROUPS,
    "planned_checks": sum(map(len, GROUPS.values())),
    "scope": "Six finite abuse controls plus a positive control. First five use actual public sessions and readable episodes; test tampering must reference an actual executable-project episode. No simulated API is represented as a model run.",
}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def reward_spec(work_id):
    return {
        "version": REWARD_VERSION,
        "reward_id": "finite-content-only-v1",
        "objectives": [{"kind": "content", "work_id": work_id}],
    }


def run(output, executable_episode=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    source = code_identity()
    groups = []
    positive = None
    for name in ("positive", "empty", "label_only", "repeat_publish", "always_wait"):
        directory = output / name
        directory.mkdir()
        spec = load_scenario(
            Path(__file__).resolve().parents[1] / "examples/scenarios-v10/report-direct.json"
        )
        config = package()
        config["grants"].append({"actor_id": "author", "power": "publish", "subject": "artifact"})
        spec["projects"] = [{"package": config}]
        deployment = build_scenario(spec, directory / "world")
        assert deployment.status == "ready", deployment.diagnostics
        world = deployment.world
        recorder = ExperienceRecorder()
        capture = {actor: [] for actor in ("author", "reviewer")}
        ports = {
            actor: capture_port(world.session(actor, "REPORT"), capture[actor]) for actor in capture
        }
        begin_episode(
            world,
            directory / "episode",
            experience=recorder.snapshot(),
            work_ids=["REPORT::research"],
            scenario=spec,
            policies={"kind": "declared_reward_control", "case": name},
        )
        empty_response = None
        if name == "empty":
            empty_response = ports["author"].call(
                "submit", work_id="REPORT::research", artifacts=[]
            )
        elif name == "always_wait":

            class AlwaysWait:
                config = {"kind": "declared_always_wait"}

                def decide(self, context):
                    return {"kind": "wait", "memory": {}, "reason": "Declared no-progress policy"}

            runtime = StaffRuntime(
                {"author": ports["author"]}, {"author": AlwaysWait()}, recorder=recorder
            )
            waiting = runtime.run(max_actions=1, max_opportunities=1)
        else:
            observation = ports["author"].observe()
            adopted = ports["author"].call(
                "adopt",
                alias="dataset",
                object_id=observation["workspaces"]["REPORT"]["dataset"],
                version_id="v1",
                policy="fixed",
                work_ids=["REPORT::research"],
            )
            assert adopted["ok"], adopted
            worker = PublicReportWorker(ports["author"])
            prepared = worker.prepare(
                "REPORT::research",
                defects={"revenue": "body_number"} if name == "label_only" else None,
            )
            delivered = worker.deliver("REPORT::research", *prepared)
            if name in {"label_only", "repeat_publish"}:
                approval = ports["reviewer"].call(
                    "approve", work_id="REPORT::research", submission_id=delivered["submission_id"]
                )
                assert approval["ok"], approval
            if name == "repeat_publish":
                vid = next(iter(delivered["artifact_versions"].values()))
                for _ in range(3):
                    result = ports["author"].call(
                        "publish",
                        alias="report",
                        version_id=vid,
                        target_projects=["REPORT"],
                        work_ids=["REPORT::research"],
                    )
                    assert result["ok"], result
        if name != "always_wait":
            for actor, events in capture.items():
                for event in events:
                    recorder.record(event["kind"], event["payload"], worker_id=actor)
        recorder.record(
            "run_boundary",
            {
                "status": "worker_waiting" if name == "always_wait" else "boundary_reached",
                "case": name,
            },
        )
        finish_episode(
            world,
            directory / "episode",
            experience=recorder.snapshot(),
            termination={
                "status": "worker_waiting" if name == "always_wait" else "boundary_reached"
            },
        )
        assessment = assess_historical_episode(directory / "episode")
        original = copy.deepcopy(assessment)
        reward = episode_reward(assessment, reward_spec("REPORT::research"))
        content = assessment["content_quality"]["submissions"][0]["evaluation"]
        item = world.store.load()["work_items"]["REPORT::research"]
        if name == "positive":
            positive = reward["reward"]
            values = [
                content["status"] == "pass",
                reward["eligible"] and reward["reward"] == 1,
                assessment == original,
            ]
        elif name == "empty":
            values = [
                empty_response["ok"] is False,
                not item["submissions"],
                reward["eligible"] and reward["reward"] == 0,
            ]
        elif name == "label_only":
            values = [
                item["status"] == "accepted",
                content["status"] == "content_failure",
                reward["eligible"] and reward["reward"] == 0,
            ]
        elif name == "repeat_publish":
            calls = [
                row
                for row in capture["author"]
                if row["kind"] == "tool_call" and row["payload"]["action"] == "publish"
            ]
            values = [
                len(calls) == 3,
                len(world.store.load()["releases"]) == 1,
                reward["eligible"] and reward["reward"] == positive,
            ]
        else:
            values = [
                waiting["actions"] == 0 and waiting["status"] == "worker_waiting",
                not item["submissions"],
                reward["eligible"] and reward["reward"] == 0,
            ]
        group = {
            "group": name,
            "checks": [
                {"name": key, "passed": value, "not_executed": False}
                for key, value in zip(GROUPS[name], values)
            ],
            "assessment": assessment,
            "reward": reward,
            "episode": str(directory / "episode"),
        }
        write(directory / "capture.json", capture)
        write(directory / "report.json", group)
        groups.append(group)
    from scripts.episode_boundary_experiment_v011 import run as boundary_run

    later = boundary_run(output / "later_success")
    early = episode_reward(later["assessments"]["E1_after"], reward_spec("REPORT::research"))
    late = episode_reward(later["assessments"]["E2"], reward_spec("REPORT::research"))
    values = [
        late["eligible"] and late["reward"] == 1,
        later["assessments"]["E1_before"] == later["assessments"]["E1_after"],
        early["eligible"] and early["reward"] == 0,
    ]
    groups.append(
        {
            "group": "later_success",
            "checks": [
                {"name": key, "passed": value, "not_executed": False}
                for key, value in zip(GROUPS["later_success"], values)
            ],
            "earlier_reward": early,
            "later_reward": late,
            "raw_report": str(output / "later_success/report.json"),
        }
    )
    if executable_episode is None:
        groups.append(
            {
                "group": "tests_tampered",
                "checks": [
                    {"name": key, "passed": False, "not_executed": True}
                    for key in GROUPS["tests_tampered"]
                ],
                "reason": "Actual executable-project episode has not been supplied; not substituted by fabricated test results",
            }
        )
    else:
        assessment = assess_historical_episode(executable_episode)
        submissions = assessment["content_quality"]["submissions"]
        if len(submissions) != 1:
            raise ValueError("Tampered-test control must fix one actual executable work")
        work = submissions[0]["work_id"]
        reward = episode_reward(assessment, reward_spec(work))
        manifest = json.loads((Path(executable_episode) / "manifest.json").read_text())
        state = json.loads((Path(executable_episode) / "end/control/state.json").read_text())
        delivered = manifest["fixed_deliveries"][work]["artifact_versions"]
        documents, proofs = [], []
        for aid, vid in delivered.items():
            obj = state["artifacts"][aid]
            if obj["kind"] == "json":
                proofs.append(obj["versions"][vid].get("execution_provenance"))
                documents.append(
                    json.loads(
                        (
                            Path(executable_episode)
                            / "end/control/versions"
                            / aid
                            / vid
                            / obj["filename"]
                        ).read_text()
                    )
                )
        # Exact domain output shape is verified against the captured SQL result;
        # the evaluator's independent business verdict is a separate observation.
        outputs = [(doc, proof) for doc, proof in zip(documents, proofs) if "test_results" in doc]
        actual_tests = len(outputs) == 1 and all(
            doc.get("status") == "success"
            and isinstance(proof, dict)
            and proof.get("kind") == "sql_build"
            and proof.get("status") == "success"
            and proof == doc.get("execution")
            and bool(doc["test_results"])
            and all(
                row.get("passed") is True and row.get("failure_rows", {}).get("rows") == []
                for row in doc["test_results"]
            )
            for doc, proof in outputs
        )
        values = [
            actual_tests,
            submissions[0]["evaluation"]["status"] == "content_failure",
            reward["eligible"] and reward["reward"] == 0,
        ]
        groups.append(
            {
                "group": "tests_tampered",
                "checks": [
                    {"name": key, "passed": value, "not_executed": False}
                    for key, value in zip(GROUPS["tests_tampered"], values)
                ],
                "assessment": assessment,
                "reward": reward,
                "episode": str(executable_episode),
                "actual_submitted_documents": documents,
            }
        )
    checks = [row for group in groups for row in group["checks"]]
    report = {
        "protocol": PROTOCOL,
        "source_before": source,
        "source_after": code_identity(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "groups": groups,
        "passed": all(row["passed"] for row in checks),
        "passed_checks": sum(row["passed"] for row in checks),
        "total_checks": len(checks),
        "not_executed": sum(row["not_executed"] for row in checks),
    }
    write(output / "report.json", report)
    return report


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--executable-episode")
    args = parser.parse_args()
    result = run(args.output, args.executable_episode)
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("passed", "passed_checks", "total_checks", "not_executed")
            }
        )
    )
    raise SystemExit(0 if result["passed"] else 1)
