"""Finite scorer identity and local-only Docker boundary controls."""
import copy
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_scorer_v054 import LocalDocker, make_identity


def identity_arguments():
    return {
        "instance": {"instance_id": "fixture__fixture-1", "base_commit": "a" * 40,
                     "image": "fixture/image:latest"},
        "arm": "MATCH", "endpoint": "code", "patch": b"synthetic patch\n",
        "candidate_tree_sha256": "1" * 64, "baseline_tree_sha256": "2" * 64,
        "dataset_reference": {"sha256": "3" * 64, "bytes": 5, "path": "/trusted/data.json"},
        "scorer_manifest": {"official_version": "5.0.2", "code": "fixture"},
        "image_record": {
            "instance_id": "fixture__fixture-1", "image_name": "fixture/image", "tag": "latest",
            "manifest_digest": "sha256:" + "4" * 64, "config_digest": "sha256:" + "5" * 64,
            "image_id": "sha256:" + "5" * 64,
            "platform": {"os": "linux", "architecture": "amd64"}, "status": "loaded",
        },
        "config_sha256": "6" * 64,
        "limits": {"timeout_seconds": 1800, "nano_cpus": 4_000_000_000,
                   "memory_bytes": 16 * 1024**3, "pids_limit": 16384,
                   "network_mode": "none"},
    }


def test_cache_identity_separates_arm_endpoint_patch_tree_environment_and_retry():
    base = identity_arguments()
    ids = {make_identity(**base)[1]}
    changes = [
        {"arm": "REF"}, {"arm": "PROJECT"},
        {"arm": "PROJECT", "endpoint": "delivery"},
        {"patch": b"a different patch\n"}, {"candidate_tree_sha256": "a" * 64},
        {"baseline_tree_sha256": "b" * 64}, {"config_sha256": "c" * 64},
        {"scorer_manifest": {"official_version": "5.0.2", "code": "changed"}},
        {"dataset_reference": {**base["dataset_reference"], "sha256": "d" * 64}},
        {"image_record": {**base["image_record"], "manifest_digest": "sha256:" + "e" * 64}},
        {"attempt": 2}, {"preparation_only": True},
    ]
    for change in changes:
        ids.add(make_identity(**{**base, **change})[1])
    assert len(ids) == 1 + len(changes)
    assert make_identity(**base)[1] == make_identity(**copy.deepcopy(base))[1]
    with pytest.raises(ValueError, match="endpoint"):
        make_identity(**{**base, "endpoint": "delivery"})
    with pytest.raises(ValueError, match="immutable"):
        make_identity(**{**base, "image_record": {**base["image_record"], "image_id": None}})
    with pytest.raises(ValueError, match="local loading"):
        make_identity(**{**base, "image_record": {**base["image_record"], "status": "pending"}})


def test_docker_boundary_pins_platform_and_limits_and_cannot_pull_or_mount():
    calls = []
    image_id = "sha256:" + "5" * 64
    real_image = SimpleNamespace(id=image_id, attrs={"Os": "linux", "Architecture": "amd64"})
    delegate = SimpleNamespace(
        images=SimpleNamespace(get=lambda value: real_image),
        containers=SimpleNamespace(
            get=lambda name: name, create=lambda **kwargs: calls.append(kwargs)))
    client = LocalDocker(delegate, image_id, identity_arguments()["limits"])
    assert client.images.get(image_id) is real_image
    with pytest.raises(RuntimeError, match="pull"):
        client.images.pull("fixture/image:latest")
    with pytest.raises(ValueError, match="admitted"):
        client.images.get("fixture/image:latest")
    with pytest.raises(ValueError, match="mount"):
        client.containers.create(image=image_id, volumes={"/trusted": {}})
    client.containers.create(image=image_id, name="fixture", cap_add=["SYS_ADMIN"])
    assert calls[0]["network_mode"] == "none"
    assert calls[0]["nano_cpus"] == 4_000_000_000
    assert calls[0]["mem_limit"] == 16 * 1024**3
    assert calls[0]["pids_limit"] == 16384
    assert calls[0]["cap_add"] == ["SYS_ADMIN"]  # Preserve official container semantics.
    real_image.attrs["Architecture"] = "arm64"
    with pytest.raises(ValueError, match="admission"):
        client.images.get(image_id)
