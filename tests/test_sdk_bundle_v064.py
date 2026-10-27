import json

import pytest

from proworksim import software_benchmark_sdk_bundle_v064 as bundle
from proworksim.software_benchmark_candidates_v054 import write_new
from proworksim.software_benchmark_public_context_v062 import VERSION as CONTEXT_VERSION


def inputs(tmp_path, arm):
    row = {"slot_id": "v064:fixture:QWEN:1", "source_slot_id": "historical-lineage",
           "seed": 1, "condition_id": "QWEN_"+arm+"_B5000K", "execution_arm": arm,
           "arm": arm, "model_key": "QWEN", "instance_id": "fixture"}
    condition = write_new(tmp_path / "condition.json", {"arm": arm, "max_tokens": 32768})
    host = {**row, "configuration": condition, "dataset_revision": "b"*40,
            "public_task": {"instance_id": "fixture", "repo": "public/repo", "base_commit": "a"*40,
                            "problem_statement": "public issue", "gold_patch": "MUST NOT COPY"},
            "scorer_request_base": {"dataset": "HIDDEN"}, "ref_api_key_file": "HOST-ONLY"}
    public = {"kind": "official_image", "image_id": "sha256:"+"c"*64,
              "source_config_sha256": "c"*64, "public_python": "/opt/venv/bin/python",
              "environment": {"PATH": "/opt/venv/bin:/usr/bin:/bin", "SECRET_UNUSED": "MUST NOT COPY"}}
    context = {"version": CONTEXT_VERSION, "instance_id": "fixture", "visible_text": "public interpreter",
               "visible_facts": {}, "host_evidence": "HOST-ONLY"}
    entry = {"version": "v064-repository-public-test-entry-r1", "instance_id": "fixture",
             "argv": ["/opt/venv/bin/python", "-m", "pytest"], "cwd": "/testbed",
             "timeout_seconds": 1800, "hidden_material_used": False, "baseline_mapping": "HOST-ONLY"}
    return row, host, public, context, entry


@pytest.mark.parametrize("arm", ["REF", "PROJECT"])
def test_controller_packet_contains_only_public_condition_specific_fields(tmp_path, arm):
    row, host, public, context, entry = inputs(tmp_path, arm)
    result = bundle.controller_inputs(host, row, {}, {"model_revision": "known", "api_key": "MUST NOT COPY"},
        "http://127.0.0.1:18210", public_context=context, public_environment=public,
        public_test_entry=entry)
    raw = result["controller-config.json"]
    assert b"MUST NOT COPY" not in raw and b"HOST-ONLY" not in raw and b"HIDDEN" not in raw
    config = json.loads(raw)
    assert config["model_key"] == "QWEN" and config["execution_arm"] == arm
    assert config["measurement_kind"] == "full_verified_comparison"
    assert ("public_test_entry" in config) is (arm == "PROJECT")
    if arm == "PROJECT":
        assert set(config["public_test_entry"]) == {"version", "instance_id", "argv", "cwd", "timeout_seconds", "hidden_material_used"}
        assert config["public_test_entry"]["timeout_seconds"] == 1800


def test_project_public_entry_cannot_include_hidden_tests_or_change_interpreter(tmp_path):
    row, host, public, context, entry = inputs(tmp_path, "PROJECT")
    for edit in ({"hidden_material_used": True}, {"argv": ["/another/python", "-m", "pytest"]},
                 {"timeout_seconds": 1801}):
        with pytest.raises(ValueError, match="public-only"):
            bundle.controller_inputs(host, row, {}, {}, "http://127.0.0.1:18210",
                public_context=context, public_environment=public, public_test_entry={**entry, **edit})
