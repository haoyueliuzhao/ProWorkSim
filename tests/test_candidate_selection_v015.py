"""Selection logic and saved-record binding fixtures; no model/world execution."""

import copy
import json
from pathlib import Path

import pytest

from scripts.run_candidate_screen_v015 import preflight_outcome, stage_commands
from scripts.select_candidate_v015 import choose, ref, validated_readiness


def guard():
    before = {
        k: "fixture-" + k
        for k in (
            "actor",
            "critic",
            "actor_optimizer",
            "critic_optimizer",
            "actor_steps",
            "critic_steps",
        )
    }
    return {
        "learning_unchanged": True,
        "rng_restored_exactly": True,
        "learning_before_sha256": before,
        "learning_after_sha256": copy.deepcopy(before),
        "rng_before_sha256": "fixture-rng",
        "rng_after_restore_sha256": "fixture-rng",
    }


def screen_fixture():
    runs, resources = [], []
    for index, candidate in enumerate(("qwen25-7b", "qwen35-9b", "qwen38-27b")):
        slots = [
            {
                "case_id": f"uci-development-f{fact}-{task}",
                "repeat": repeat,
                "task": task,
                "fact": fact,
                "sampling_seed": fact * 100 + position * 10 + repeat,
                "state": "closed_known",
                "record_validity": True,
                "reward": {"completed": task == "implement" and fact < index},
            }
            for position, task in enumerate(("implement", "review", "pair", "chain"))
            for fact in range(3)
            for repeat in range(3)
        ]
        name = "screen-" + candidate
        runs.append(
            {
                "candidate_id": candidate,
                "name": name,
                "condition": candidate,
                "runner_status": "complete",
                "issues": [],
                "saved_protocol_equals_declared": True,
                "source_comparison": {"unchanged": True},
                "root": "/not-executed/" + name,
                "protocol_ref": {"path": name + ".json", "sha256": "fixture"},
                "unknown_step_windows": [],
                "progress": {
                    "counts": {"planned": 36, "closed_known": 36},
                    "completed_work_measured_count": 36,
                    "mean_reward": 1 / (index + 1),
                },
                "declared_job": {"launch": name},
                "launch_record": {"exit_code": 0, "pid": 100 + index},
                "windows": [
                    {
                        "mode": "evaluate",
                        "stage": "screen",
                        "slots": slots,
                        "steps": {
                            "actor": 0,
                            "critic": 0,
                            "issues": [],
                            "recorded_increment_fields": {
                                "actor_optimizer_steps": 0,
                                "critic_optimizer_steps": 0,
                            },
                        },
                        "evaluation_guard": guard(),
                    }
                ],
            }
        )
        resources.append(
            {"name": name, "pid": 100 + index, "allocated_device_seconds": 100 * (index + 1)}
        )
    return (
        {
            "runs": runs,
            "unknown_step_runs": [],
            "observed_optimizer_step_increments": {"actor": 0, "critic": 0},
        },
        {"runs": resources},
        {"qwen35-9b": True, "qwen38-27b": True},
    )


def test_complete_work_ordering_keeps_training_failure_and_reward_separate():
    report, resources, ready = screen_fixture()
    selected = choose(report, resources, ready)
    assert selected["selected"]["candidate_id"] == "qwen38-27b"
    assert selected["selected"]["primary_completed_implement_review"] == 6
    ready["qwen38-27b"] = False
    selected = choose(report, resources, ready)
    assert selected["all_capability_results_ranked"][0]["candidate_id"] == "qwen38-27b"
    assert selected["selected"]["candidate_id"] == "qwen35-9b"
    assert (
        selected["all_capability_results_ranked"][0]["eligibility"]
        == "training_integration_not_ready"
    )
    for run in report["runs"]:
        for slot in run["windows"][0]["slots"]:
            slot["reward"]["completed"] = False
    report["runs"][2]["windows"][0]["slots"][18]["reward"]["completed"] = True
    assert (
        choose(report, resources, {"qwen35-9b": True, "qwen38-27b": True})["selected"][
            "candidate_id"
        ]
        == "qwen38-27b"
    )
    report["runs"][2]["windows"][0]["slots"][18]["reward"]["completed"] = False
    resources["runs"][2]["allocated_device_seconds"] = 50
    assert (
        choose(report, resources, {"qwen35-9b": True, "qwen38-27b": True})["selected"][
            "candidate_id"
        ]
        == "qwen38-27b"
    )


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("missing", "Complete immutable"),
        ("seed", "same frozen"),
        ("pool", "development cases"),
        ("guard_missing", "guard"),
        ("guard_changed", "guard"),
        ("rng_changed", "guard"),
        ("step_issue", "guard"),
        ("nan_cost", "resource"),
        ("infinite_cost", "resource"),
        ("bool_cost", "resource"),
    ],
)
def test_missing_and_inconsistent_measurements_are_rejected(mutation, match):
    report, resources, ready = screen_fixture()
    run = report["runs"][1]
    window = run["windows"][0]
    if mutation == "missing":
        run["progress"]["counts"]["closed_known"] = 35
    elif mutation == "seed":
        window["slots"][0]["sampling_seed"] += 1
    elif mutation == "pool":
        window["slots"][0]["case_id"] = "uci-train-f0-implement"
    elif mutation == "guard_missing":
        window["evaluation_guard"].pop("learning_before_sha256")
    elif mutation == "guard_changed":
        window["evaluation_guard"]["learning_after_sha256"]["critic"] = "changed"
    elif mutation == "rng_changed":
        window["evaluation_guard"]["rng_after_restore_sha256"] = "not-restored"
    elif mutation == "step_issue":
        window["steps"]["issues"] = ["evaluation_record_reports_nonzero_optimizer_steps"]
    elif mutation == "nan_cost":
        resources["runs"][1]["allocated_device_seconds"] = float("nan")
    elif mutation == "infinite_cost":
        resources["runs"][1]["allocated_device_seconds"] = float("inf")
    elif mutation == "bool_cost":
        resources["runs"][1]["allocated_device_seconds"] = True
    with pytest.raises(ValueError, match=match):
        choose(report, resources, ready)


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def binding_fixture(tmp_path):
    report, resources, _ = screen_fixture()
    source = tmp_path / "source"
    configs, jobs, sources = [], [], {}
    for relative in (
        "scripts/candidate_preflight_v0151.py",
        "scripts/online_learning_v015.py",
        "src/proworksim/candidate_runtime_v015.py",
        "src/proworksim/candidate_runtime_v0151.py",
    ):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# never executed fixture source\n")
        sources[str(path)] = ref(path)["sha256"]
    config = {
        "source": str(source),
        "source_commit": "f" * 40,
        "python": "/fixture/model-python",
        "launcher_python": "/fixture/plain-python",
        "launcher": "/fixture/launcher.py",
    }
    for index, name in enumerate(("qwen35-9b", "qwen38-27b")):
        training_ready = (
            name == "qwen35-9b"
        )  # A measured S0 failure still has valid work measurement.
        candidate = "qwen3.5-9b" if index == 0 else "qwen3.8-27b"
        output = tmp_path / f"screen-{name}"
        preflight = tmp_path / f"preflight-{name}"
        model = tmp_path / f"model-{name}"
        manifest = model / "proworksim-manifest.json"
        save(
            manifest,
            {"repo_id": "explicit-offline-fixture", "declared_hf_revision": "fixture-" + name},
        )
        profile = {
            "version": "candidate-runtime-v0.15.1",
            "candidate_id": candidate,
            "dtype": "float32",
            "devices": 1 if index == 0 else 3,
        }
        recipe = {"seed": 123, "max_length": 16384, "max_output_tokens": 2048}
        protocol = {
            "candidate_id": name,
            "condition": name,
            "runtime": {"kind": "qwen_hybrid_chatstop", "profile": profile},
            "recipe": recipe,
        }
        protocol_path = source / f"{name}.json"
        save(protocol_path, protocol)
        sources[str(protocol_path)] = ref(protocol_path)["sha256"]
        job = {
            "name": name,
            "candidate": candidate,
            "gpus": [0] if index == 0 else [1, 2, 3],
            "devices": profile["devices"],
            "dtype": "float32",
            "model_path": str(model),
            "weight_manifest": str(manifest),
            "screen_output": str(output),
            "preflight_output": str(preflight),
            "screen_protocol": str(protocol_path),
            "screen_launch": str(tmp_path / f"launch/screen-{name}"),
            "preflight_launch": str(tmp_path / f"launch/preflight-{name}"),
            "preflight_script": str(source / "scripts/candidate_preflight_v0151.py"),
            "replay_calls": [],
        }
        configs.append(job)
        actor_identity = {
            "policy_version": "0",
            "adapter_sha256": "fixture-" + name,
            "base_manifest_sha256": ref(manifest)["sha256"],
            "inference_profile_sha256": "fixture-profile",
        }
        owner = {
            "version": "fixture-metadata-only",
            "base_identity": {
                "path": str(model),
                "manifest": ref(manifest),
                "revision": "fixture-" + name,
            },
            "inference_profile": {**profile, "torch": "fixture-not-loaded"},
            "recipe": recipe,
            "initial_actor_identity": actor_identity,
        }
        checkpoint = {
            "actor_identity": actor_identity,
            "actor_steps": 0,
            "critic_steps": 0,
            "serialized_reload_exact": True,
        }
        save(preflight / "owner/owner.json", owner)
        save(output / "resident/owner.json", owner)
        save(output / "online/protocol.json", protocol)
        save(output / "launch-protocol.json", protocol)
        if training_ready:
            save(preflight / "unchanged-checkpoint/checkpoint.json", checkpoint)
        raw_call = preflight / "owner/calls/calibration.json"
        save(
            raw_call,
            {
                "status": 200,
                "response": {
                    "id": "fixture-generation",
                    "choices": [{}],
                    "token_trace": {
                        "input_ids": [1],
                        "output_ids": [2, 248046],
                        "raw_output_ids": [2, 248046],
                        "behavior_logprobs": [-1.0, -2.0],
                        "raw_behavior_logprobs": [-1.0, -2.0],
                    },
                },
            },
        )
        calibration = {
            "candidate": candidate,
            "profile": owner["inference_profile"],
            "inference_ready": True,
            "training_ready": training_ready,
            "statuses": [200],
            "probability_checks": [{"passed": training_ready}],
            "backward": {"executed": training_ready, "gradient_finite_nonzero": training_ready},
            "checkpoint": checkpoint if training_ready else None,
            "checkpoint_restored": training_ready,
            "actor_steps": 0,
            "critic_steps": 0,
            "requested_replay_calls": 0,
            "replay_records": [],
            "errors": [],
        }
        save(preflight / "report.json", calibration)
        state = {"name": name, "status": "complete", "training_ready": training_ready}
        for stage in ("preflight", "screen"):
            _, command = stage_commands(config, job, stage)
            launch = {
                "command": command,
                "cwd": str(source),
                "exit_code": 0,
                "pid": 900 + index,
                "CUDA_VISIBLE_DEVICES": ",".join(map(str, job["gpus"])),
                "PYTHONPATH": str(source / "src"),
            }
            save(Path(job[stage + "_launch"]).with_suffix(".launch.json"), launch)
            state[stage] = {"status": "finished", "exit_code": 0, "launch_meta": launch}
        state["preflight"]["outcome"] = preflight_outcome(preflight, 0, job=job)
        jobs.append(state)
        run = report["runs"][index + 1]
        run.update(
            root=str(output),
            owner=owner,
            protocol_ref=ref(protocol_path),
            launch_record=state["screen"]["launch_meta"],
            source_before={
                "code_commit": "f" * 40,
                "code_dirty": False,
                "source_tree_sha256": "fixture-tree",
            },
            source_after={
                "code_commit": "f" * 40,
                "code_dirty": False,
                "source_tree_sha256": "fixture-tree",
            },
        )
    config["candidates"] = configs
    supervisor = {
        "status": "complete",
        "config": config,
        "source_identity": {"commit": "f" * 40, "files": sources},
        "jobs": jobs,
    }
    return supervisor, report, resources


def test_readiness_binds_real_saved_records_and_keeps_measured_false(tmp_path):
    supervisor, report, _ = binding_fixture(tmp_path)
    assert validated_readiness(supervisor, report) == {"qwen35-9b": True, "qwen38-27b": False}


@pytest.mark.parametrize(
    "mutation",
    [
        "queue_not_complete",
        "foreign_output",
        "foreign_protocol",
        "foreign_protocol_path",
        "foreign_source",
        "foreign_profile",
        "foreign_manifest",
        "foreign_owner",
        "foreign_launch",
        "fake_readiness",
        "changed_s0_call",
        "missing_s0_report",
    ],
)
def test_readiness_rejects_foreign_missing_or_contradictory_s0_s1(mutation, tmp_path):
    supervisor, report, _ = binding_fixture(tmp_path)
    job = supervisor["config"]["candidates"][0]
    if mutation == "queue_not_complete":
        supervisor["status"] = "running"
    elif mutation == "foreign_output":
        report["runs"][1]["root"] = str(tmp_path / "different-run")
    elif mutation == "foreign_protocol":
        report["runs"][1]["protocol_ref"]["sha256"] = "different"
    elif mutation == "foreign_protocol_path":
        report["runs"][1]["protocol_ref"]["path"] = str(tmp_path / "same-bytes-foreign-protocol.json")
    elif mutation == "foreign_source":
        report["runs"][1]["source_before"]["code_commit"] = "different"
    elif mutation == "foreign_profile":
        path = Path(job["preflight_output"]) / "report.json"
        data = json.loads(path.read_text())
        data["profile"]["dtype"] = "bfloat16"
        save(path, data)
    elif mutation == "foreign_manifest":
        save(Path(job["weight_manifest"]), {"changed": "asset identity"})
    elif mutation == "foreign_owner":
        report["runs"][1]["owner"] = {"different": "owner"}
    elif mutation == "foreign_launch":
        supervisor["jobs"][0]["screen"]["launch_meta"] = {"pid": 0}
    elif mutation == "fake_readiness":
        supervisor["jobs"][0]["training_ready"] = False
    elif mutation == "changed_s0_call":
        path = Path(job["preflight_output"]) / "owner/calls/calibration.json"
        data = json.loads(path.read_text())
        data["response"]["id"] = "not-original-response"
        save(path, data)
    elif mutation == "missing_s0_report":
        (Path(job["preflight_output"]) / "report.json").unlink()
    with pytest.raises(ValueError):
        validated_readiness(supervisor, report)
