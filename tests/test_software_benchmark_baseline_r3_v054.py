"""Only the new ancestry/version mapping gate, using an actual prepared mapping."""
import copy
import json
from pathlib import Path

import pytest

from proworksim.software_benchmark_baseline_v054 import (
    FORMAT_POLICY_SHA256, _fsck, format_policy, validate_mapping,
)


def test_actual_r3_ancestry_mapping_and_version_drift_rejection():
    root = Path(__file__).resolve().parents[1]
    path = root / "runs/software-benchmark-v054/images/actor-admission-r3/instances/astropy__astropy-12907.json"
    if not path.is_file():
        pytest.skip("Requires the locally prepared r3 integration mapping")
    mapping = json.loads(path.read_bytes())
    instance = {"instance_id": mapping["instance_id"], "base_commit": mapping["dataset_base"]}
    image = {"image_id": mapping["official_image_id"], "manifest_digest": mapping["official_manifest_digest"]}
    assert validate_mapping(mapping, instance=instance, image=image) is mapping
    for kind in ("runtime", "future", "head"):
        changed = copy.deepcopy(mapping)
        if kind == "runtime":
            changed["runtime_version"]["actor"]["version"] = "0.post1+changed"
        elif kind == "future":
            changed["git_ancestry"]["all_refs_within_allowed_ancestry"] = False
        else:
            changed["actor_head"] = "0" * 40
        with pytest.raises(ValueError):
            validate_mapping(changed, instance=instance, image=image)


def test_only_exact_known_historical_format_error_is_accepted():
    policy = format_policy()["repos"]["psf/requests"]
    image = policy["official_source_audit"]["official_image_id"]
    exception = {**policy["objects"][0], "source_official_image_id": image,
                 "source_same_diagnostic": True, "source_in_allowed_closure": True,
                 "target_object_hash_verified": True}
    value = {"fsck_returncode": 4, "fsck_structural_validation_passed": True,
             "fsck_connectivity_returncode": 0,
             "historical_format_exception_policy_sha256": FORMAT_POLICY_SHA256,
             "historical_format_exceptions": [exception],
             "fsck_diagnostic_lines": [exception["diagnostic_line"]]}
    options = {"schema": "proworksim.v054.actor-admission-r3.1", "repo": "psf/requests",
               "official_image_id": image}
    _fsck(value, **options)
    for kind in ("extra_line", "different_object", "connectivity_error"):
        bad = copy.deepcopy(value)
        if kind == "extra_line":
            bad["fsck_diagnostic_lines"].append("unapproved diagnostic")
        elif kind == "different_object":
            bad["historical_format_exceptions"][0]["raw_sha256"] = "0" * 64
        else:
            bad["fsck_returncode"] = 6
        with pytest.raises(ValueError):
            _fsck(bad, **options)
