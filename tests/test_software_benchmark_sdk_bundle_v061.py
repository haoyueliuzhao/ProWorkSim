"""Narrow private runtime/config boundaries; no image or model is launched."""
import json

import pytest

from proworksim import software_benchmark_sdk_bundle_v061 as bundle
from proworksim.software_benchmark_candidates_v054 import reference


def test_controller_inputs_keep_budget_seed_but_omit_scoring_and_secret_data(tmp_path):
    condition = tmp_path / "condition.json"
    condition.write_text('{"condition_id":"REF_B5000K"}')
    original = {"slot_id": "old", "condition_id": "REF_B5000K", "seed": 7,
        "configuration": reference(condition), "public_task": {"instance_id": "task", "repo": "repo",
            "base_commit": "base", "problem_statement": "public", "hidden_unused_field": "omit"},
        "ref_api_key_file": "/secret/path", "scorer_request_base": {"gold": "hidden"}}
    files = bundle.controller_inputs(original, "old:v061-r1", {"ready": True},
        {"port": 18161, "api_key": "secret"}, "http://127.0.0.1:18161")
    value = json.loads(files["controller-config.json"])
    assert value["seed"] == 7 and value["original_slot_id"] == "old"
    assert value["configuration"]["sha256"] == reference(condition)["sha256"]
    assert files["condition.json"] == condition.read_bytes()
    assert "secret" not in str(value) and "gold" not in str(value) and "hidden_unused" not in str(value)
    assert value["model_identity_value"] == {"port": 18161}
    with pytest.raises(ValueError, match="lineage"):
        bundle.controller_inputs(original, "another", {}, {}, "http://127.0.0.1:18161")


@pytest.mark.parametrize("name", ["/etc/passwd", "opt/pws-runtime/../../escape", "data0/host", "pws/other"])
def test_bundle_archive_paths_are_private(name):
    assert bundle._member_ok(name) is False


def test_private_launcher_keeps_loader_scope_and_disables_site_processing():
    text = bundle.wrapper_text()
    assert "--argv0" in text and "-B -S -P" in text
    assert "LD_LIBRARY_PATH" not in text and "chroot" not in text and "mount" not in text
    env = bundle.runtime_environment()
    assert env["PYTHONPATH"].split(":")[0] == "/opt/pws-runtime/project/src"
    assert env["CUDA_VISIBLE_DEVICES"] == "" and env["PYTHON_DOTENV_DISABLED"] == "1"
