from copy import deepcopy
import json
import sys
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_scorer_v061 as scorer
from proworksim.software_benchmark_candidates_v054 import reference


def attributes():
    limits = scorer.LIMITS
    observation = {
        "image_id": "sha256:fixed",
        "cpuset_cpus": "0,1,2,3",
        "labels": {"owner": "ours"},
    }
    attrs = {
        "Image": observation["image_id"],
        "Mounts": [],
        "Config": {"Labels": observation["labels"]},
        "HostConfig": {
            "NetworkMode": "none",
            "CapAdd": [],
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "Privileged": False,
            "NanoCpus": limits["nano_cpus"],
            "Memory": limits["memory_bytes"],
            "MemorySwap": limits["memory_bytes"],
            "PidsLimit": limits["pids_limit"],
            "CpusetCpus": observation["cpuset_cpus"],
            "IpcMode": "private",
        },
    }
    return attrs, observation


@pytest.mark.parametrize(
    "field,value",
    [
        ("NetworkMode", "host"),
        ("CapAdd", ["SYS_ADMIN"]),
        ("MemorySwap", -1),
        ("PidMode", "host"),
        ("Binds", ["/host:/testbed"]),
        ("Devices", [{"PathOnHost": "/dev/nvidia0"}]),
        ("PortBindings", {"80/tcp": [{}]}),
    ],
)
def test_actual_docker_configuration_must_remain_bounded(field, value):
    attrs, observation = attributes()
    scorer.validate_attrs(attrs, observation)
    attrs["HostConfig"][field] = value
    with pytest.raises(ValueError):
        scorer.validate_attrs(attrs, observation)


def test_owned_labels_and_no_mounts_are_checked():
    attrs, observation = attributes()
    other = deepcopy(attrs)
    other["Config"]["Labels"] = {"owner": "foreign"}
    with pytest.raises(ValueError, match="ownership"):
        scorer.validate_attrs(other, observation)
    attrs["Mounts"] = [{"Type": "volume", "Source": "unapproved"}]
    with pytest.raises(ValueError, match="resource or isolation"):
        scorer.validate_attrs(attrs, observation)


def test_harness_ghost_cleanup_cannot_fetch_or_remove_existing_containers(monkeypatch):
    class NotFound(Exception):
        pass

    monkeypatch.setitem(
        sys.modules, "docker", SimpleNamespace(errors=SimpleNamespace(NotFound=NotFound))
    )
    delegate = SimpleNamespace(get=lambda name: pytest.fail("Foreign get must never be forwarded"))
    wrapper = scorer.Containers(delegate, "image", {}, {})
    with pytest.raises(NotFound):
        wrapper.get("somebody-elses-container")


def test_only_upstream_sys_admin_default_may_be_removed_before_creation():
    scorer.validate_options({"image": "image", "cap_add": ["SYS_ADMIN"]}, "image")
    with pytest.raises(ValueError, match="Unexpected added"):
        scorer.validate_options({"image": "image", "cap_add": ["NET_ADMIN"]}, "image")
    for key in ("volumes", "mounts", "dns", "extra_hosts", "device_requests"):
        with pytest.raises(ValueError, match="cannot receive"):
            scorer.validate_options({"image": "image", key: ["foreign"]}, "image")


def control_evidence(tmp_path, monkeypatch, mutate=lambda kind, receipt, quiet: None):
    monkeypatch.setattr(scorer, "BATCH_ROOT", tmp_path)

    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return reference(path)

    plan = write(tmp_path / "plan.json", {"frozen": "plan"})
    task = "original-task"
    config = {
        "instance_id": task,
        "scorer_request_base": {
            "dataset": {"fixed": "data"},
            "image": {"fixed": "image"},
            "baseline_mapping": {"fixed": "baseline"},
        },
    }
    controls = []
    for kind in ("gold", "empty"):
        key = "control-" + task + "-" + kind
        folder = tmp_path / "grading" / key
        identity = {"plan": plan, "resource_key": key, **config["scorer_request_base"]}
        identity_ref = write(folder / "official-output/identity.json", identity)
        receipt = {
            "version": scorer.VERSION,
            "status": "official_report",
            "resource_key": key,
            "instance_id": task,
            "identity": identity_ref,
            "resolved": kind == "gold",
            "official_result": [
                task,
                {
                    task: {
                        "resolved": kind == "gold",
                        "tests_status": {
                            "FAIL_TO_PASS": {"failure": ["target"] if kind == "empty" else []}
                        },
                    }
                },
            ],
        }
        quiet = {
            "resource_key": key,
            "quiescent": True,
            "cleanup_errors": [],
            "create_result_unknown": False,
            "deadline_reached": False,
        }
        mutate(kind, receipt, quiet)
        controls.append(
            {
                "patch_kind": kind,
                "receipt": write(folder / "receipt.json", receipt),
                "quiescence": write(folder / "quiescence.json", quiet),
                "completion": write(folder / "completion.json", {"returncode": 0}),
            }
        )
    value = {
        "version": scorer.VERSION,
        "instance_id": task,
        "passed": True,
        "plan": plan,
        "controls": controls,
    }
    return write(tmp_path / "qualification.json", value), config, plan


def test_independent_gold_empty_pair_qualifies(tmp_path, monkeypatch):
    ref, config, plan = control_evidence(tmp_path, monkeypatch)
    assert scorer.validate_qualification(ref, config, plan)["passed"] is True
    bad = deepcopy(config)
    bad["scorer_request_base"]["image"] = {"another": "image"}
    with pytest.raises(ValueError, match="identity"):
        scorer.validate_qualification(ref, bad, plan)


@pytest.mark.parametrize("kind", ["gold", "empty"])
def test_opposite_control_outcome_cannot_admit_task(tmp_path, monkeypatch, kind):
    def mutate(which, receipt, quiet):
        if which == kind:
            receipt["resolved"] = which != "gold"

    ref, config, plan = control_evidence(tmp_path, monkeypatch, mutate)
    with pytest.raises(ValueError, match="reference repair|Empty baseline"):
        scorer.validate_qualification(ref, config, plan)


@pytest.mark.parametrize(
    "field,value",
    [("quiescent", False), ("deadline_reached", True), ("create_result_unknown", True)],
)
def test_unproven_cleanup_or_deadline_is_not_control_success(tmp_path, monkeypatch, field, value):
    def mutate(kind, receipt, quiet):
        if kind == "gold":
            quiet[field] = value

    ref, config, plan = control_evidence(tmp_path, monkeypatch, mutate)
    with pytest.raises(ValueError, match="cleanup is invalid"):
        scorer.validate_qualification(ref, config, plan)
