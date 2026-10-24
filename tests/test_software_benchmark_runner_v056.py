"""Synthetic admission, once-only, deadlines and scorer-identity controls."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_runner_v056 as runner
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.storage import digest, json_bytes


def config_fixture(tmp_path, monkeypatch):
    task = {"instance_id": "fixture__ref-budget-1", "repo": "fixture/budget",
            "base_commit": "a" * 40, "problem_statement": "A synthetic host-control task"}
    public = write_new(tmp_path / "public.json", [task])
    monkeypatch.setattr(runner, "PUBLIC_SHA256", public["sha256"])
    condition = json.loads((runner.ROOT / "config/v056-condition-REF_B0500K.json").read_bytes())
    condition_ref = write_new(tmp_path / "condition.json", condition)
    slot = {"slot_id": "v056:fixture__ref-budget-1:REF_B0500K:1", "instance_id": task["instance_id"],
            "arm": "REF", "condition_id": "REF_B0500K", "seed": 1,
            "input_plus_output_tokens": 500000}
    slots = write_new(tmp_path / "slots.json", {"version": "v056-ref-budget-slots-r1", "slots": [slot]})
    auth = write_new(tmp_path / "authorization.json", {"version": "v056-ref-budget-authorization-r1",
        "execution_authorized": True, "slots_sha256": slots["sha256"], "slot_ids": [slot["slot_id"]]})
    mapping = write_new(tmp_path / "mapping.json", {"synthetic": True})
    entry = {"instance_id": task["instance_id"], "admitted": True, "baseline_mapping": mapping}
    registry = write_new(tmp_path / "registry.json", {"planned_tasks": 500, "entries": [entry]})
    environment = write_new(tmp_path / "environment.json", {"image": {"image_id": "sha256:" + "b" * 64}})
    key = tmp_path / "synthetic-api-key"
    key.write_text("not-a-live-credential")
    config = {"version": runner.CONFIG_VERSION, "arm": "REF", "model": runner.MODEL,
        "thinking": True, "condition_id": slot["condition_id"], "slot_id": slot["slot_id"],
        "seed": slot["seed"], "public_task": task, "public_tasks": public,
        "dataset_revision": condition["dataset_revision"], "configuration": condition_ref,
        "slots": slots, "authorization": auth, "public_test_registry": registry,
        "public_test_entry": entry, "environment": environment,
        "scorer_request_base": {"baseline_mapping": mapping},
        "frozen_sources": [reference(Path(runner.__file__))], "preparation_only": False,
        "all_solver_admissions_passed": True, "ref_endpoint": "http://127.0.0.1:18056",
        "ref_api_key_file": str(key), "model_identity_value": {"port": 18056, "service_admission_complete": True}}
    monkeypatch.setattr(runner, "RUN_ROOT", tmp_path / "runs/software-benchmark-v056")
    return config


def test_formal_identity_rejects_preparation_fake_arm_and_changed_budget(tmp_path, monkeypatch):
    config = config_fixture(tmp_path, monkeypatch)
    condition, slot = runner.validate_config(config)
    assert slot["seed"] == 1 and condition["episode_limits"]["all_model_attempts"] == 512
    for key, value in (("preparation_only", True), ("all_solver_admissions_passed", False),
                       ("arm", "PROJECT"), ("seed", 2), ("ref_endpoint", "http://192.0.2.1:18056")):
        with pytest.raises(ValueError):
            runner.validate_config({**config, key: value})
    condition["episode_limits"]["input_plus_output_tokens"] = 600000
    changed = write_new(tmp_path / "changed-condition.json", condition)
    with pytest.raises(ValueError, match="Unknown predeclared"):
        runner.validate_config({**config, "configuration": changed})


def test_once_only_claim_and_long_deadlines_never_own_the_resident(tmp_path, monkeypatch):
    config = config_fixture(tmp_path, monkeypatch)
    episode = runner.RefBudgetEpisode(config)
    with pytest.raises(FileExistsError):
        runner.RefBudgetEpisode(config)
    registered = []
    monkeypatch.setattr(runner, "start_watchdog", lambda spec, root: (
        registered.append(copy.deepcopy(spec)) or SimpleNamespace(), root / "quiet.json"))
    episode.clock = lambda: 100.
    for role in ("actor", "controller"):
        episode.register_scope({"claim_id": episode.claim_id, "role": role, "unit": role})
    start = episode.enter_ref()
    assert start["soft_at"] == 21700 and start["hard_at"] == 23500
    assert registered[0]["hard_at"] == start["hard_at"]
    assert {row["role"] for row in registered[0]["scopes"]} == {"actor", "controller"}
    assert json.loads((episode.root / "state.json").read_text())["version"] == runner.VERSION
    with pytest.raises(ValueError):
        episode.enter_ref()


def test_scorer_key_binds_condition_slot_configuration_and_candidate(tmp_path, monkeypatch):
    config = config_fixture(tmp_path, monkeypatch)
    slot = runner.planned_slot(config)
    patch = {"patch": reference(tmp_path / "synthetic-api-key"),
             "base_tree_sha256": "c" * 64, "candidate_tree_sha256": "d" * 64}
    lock = {"endpoint": "terminal_code", "lock_before_grading": True,
            "slot": slot, "patch_receipt": patch}
    lock_ref = write_new(tmp_path / "candidate.json", lock)
    first = json.loads(Path(runner.score_requests(config, lock_ref, tmp_path)[0]["path"]).read_bytes())
    other = tmp_path / "different-candidate"
    other.mkdir()
    lock["patch_receipt"]["candidate_tree_sha256"] = "e" * 64
    changed = write_new(other / "candidate.json", lock)
    second = json.loads(Path(runner.score_requests(config, changed, other)[0]["path"]).read_bytes())
    assert first["run_id"] != second["run_id"]
    assert first["arm"] == "REF" and first["thinking"] is True
    assert first["preparation_only"] is False and first["actor_feedback"] is False
    assert first["config_sha256"] == config["configuration"]["sha256"]
    lock["slot"]["condition_id"] = "REF_B2000K"
    wrong = write_new(other / "wrong-condition.json", lock)
    with pytest.raises(ValueError, match="this slot"):
        runner.score_requests(config, wrong, other)


def test_episode_fault_is_retained_without_resampling_or_launching_a_model(tmp_path, monkeypatch):
    config = config_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "prepared_paths", lambda _: {
        "environment": config["environment"]["path"], "rootfs_environment": "synthetic-rootfs.json"})
    clones = []

    def unavailable(*args):
        clones.append(args)
        raise RuntimeError("synthetic clone I/O fault")

    monkeypatch.setattr(runner, "clone_prepared_rootfs", unavailable)
    result = runner.run(config, runner.RUN_ROOT / "one")
    assert result["status"] == "technical_unknown" and result["entered_model"] is False
    assert result["slot_claimed"] is True and result["GPU_loads"] == 0
    assert result["automatic_retry"] is False
    again = runner.run(config, runner.RUN_ROOT / "two")
    assert again["status"] == "technical_unknown" and again["error"]["type"] == "FileExistsError"
    assert len(clones) == 1
    assert (runner.RUN_ROOT / "one/result.json").is_file()


def test_namespace_helper_reads_only_declared_template_roots(tmp_path, monkeypatch):
    path = runner.ROOT / "tools/native_uid_bootstrap_v056.py"
    spec = importlib.util.spec_from_file_location("v056_bootstrap_control", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    monkeypatch.setattr(helper, "ROOT", tmp_path)
    allowed = tmp_path / "runs/software-benchmark-v054/v056-budget-cache-r1/task"
    allowed.mkdir(parents=True)
    rootfs = allowed / "rootfs"
    rootfs.mkdir()
    manifest = allowed / "manifest.json"
    manifest.write_bytes(json_bytes({"prepared_root": str(rootfs)}))
    assert helper.checked_manifest(manifest, reference(manifest)["sha256"])[1] == rootfs
    outside = tmp_path / "other-project"
    outside.mkdir()
    raw = json_bytes({"prepared_root": str(rootfs)})
    (outside / "manifest.json").write_bytes(raw)
    with pytest.raises(ValueError, match="only accepts"):
        helper.checked_manifest(outside / "manifest.json", digest(raw))
