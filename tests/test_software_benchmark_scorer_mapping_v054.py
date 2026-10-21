"""The one changed scorer contract: task base and official setup are distinct."""
import pytest

from proworksim.software_benchmark_scorer_r4_v054 import validate_mapping


def test_mapping_accepts_identified_setup_tree_and_rejects_drift():
    instance = {"instance_id": "synthetic__repo-1", "base_commit": "1" * 40}
    image = {"image_id": "sha256:" + "2" * 64, "manifest_digest": "sha256:" + "3" * 64}
    mapping = {
        "schema": "proworksim.v054.actor-admission-r2", "status": "actor_baseline_admitted",
        "instance_id": instance["instance_id"], "dataset_base": instance["base_commit"],
        "official_image_id": image["image_id"], "official_manifest_digest": image["manifest_digest"],
        "official_grading_image_modified": False, "base_tree": "4" * 40,
        "official_head": "5" * 40, "official_tree": "6" * 40,
        "actor_head": "7" * 40, "actor_tree": "6" * 40,
        "actor_tree_equals_official_tree": True, "working_tree_clean": True,
        "old_git_object_database_removed": True, "git_commit_object_count": 1,
        "git_fsck_returncode": 0, "target_package_copy_paths": [],
        "official_setup_commit": {"parents": [instance["base_commit"]],
                                  "author": ["SWE-bench", "setup@swebench.com"], "subject": "SWE-bench"},
    }
    assert validate_mapping(mapping, instance=instance, image=image) is mapping
    for change in ({"official_image_id": "sha256:" + "0" * 64},
                   {"actor_tree": "8" * 40}, {"official_setup_commit": {}}):
        with pytest.raises(ValueError):
            validate_mapping({**mapping, **change}, instance=instance, image=image)
