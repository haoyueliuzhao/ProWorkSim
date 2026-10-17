"""Only the new retained-checkpoint metadata gate; no weights or HOLD tasks."""
import copy
import json

import pytest

from proworksim.online_training import reference
from proworksim.software_calibration_runtime_v051 import validate_checkpoint_metadata


def saved_fixture(tmp_path):
    saved = {"actor_steps": 5, "critic_steps": 5,
             "actor_identity": {"adapter_sha256": "a" * 64},
             "state": {"path": str(tmp_path / "never-loaded.pt"), "sha256": "b" * 64}}
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps(saved))
    authorization = {"checkpoint": reference(path), "actor_identity": saved["actor_identity"],
                     "historical_steps": [5, 5], "state_file_reference_from_original_metadata": saved["state"]}
    return path, saved, authorization


def test_retained_55_requires_explicit_static_binding(tmp_path):
    path, saved, authorization = saved_fixture(tmp_path)
    with pytest.raises(ValueError, match="explicit frozen authorization"):
        validate_checkpoint_metadata(path, saved)
    assert validate_checkpoint_metadata(path, saved, authorization) == (5, 5)
    assert not (tmp_path / "never-loaded.pt").exists()


def test_retained_identity_cannot_be_substituted(tmp_path):
    path, saved, authorization = saved_fixture(tmp_path)
    changed = copy.deepcopy(authorization)
    changed["actor_identity"]["adapter_sha256"] = "c" * 64
    with pytest.raises(ValueError, match="exact statically authorized"):
        validate_checkpoint_metadata(path, saved, changed)


def test_complete_state_source_cannot_be_substituted(tmp_path):
    path, saved, authorization = saved_fixture(tmp_path)
    changed = copy.deepcopy(authorization)
    changed["state_file_reference_from_original_metadata"]["sha256"] = "d" * 64
    with pytest.raises(ValueError, match="exact statically authorized"):
        validate_checkpoint_metadata(path, saved, changed)
