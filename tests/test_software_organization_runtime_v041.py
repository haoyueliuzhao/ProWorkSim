"""One CPU SDK collection proves the new transport is the default real path."""
import json

import pytest

from proworksim.software_organization_runtime_v041 import collect_episode
from proworksim.software_organization_v040 import CASE_IDS, MEMBERS, build_software_collaboration_case, case_spec
from test_software_organization_runtime_v038 import CPUOwner, action
from test_software_organization_runtime_v040 import SelectedCPUTransport, tokenize


def test_default_collection_uses_v041_context_and_keeps_v040_business_and_error_policy(tmp_path):
    pytest.importorskip("openhands.sdk")
    owner = CPUOwner({MEMBERS[0]: [action("work_note", key="actual", text="CPU SDK action")]})
    owner.prepare_request = lambda request: (json.dumps(request, ensure_ascii=False, sort_keys=True), None, None)
    owner.tokenizer = tokenize
    owner.transport = SelectedCPUTransport(owner)
    prepared = build_software_collaboration_case(case_spec(CASE_IDS[0], condition="PT"), tmp_path / "case")
    folder = tmp_path / "collection"
    result = collect_episode(owner, prepared, folder, sampling_seed=41, slot_id="explicit-v041-cpu-control")
    assert result["version"] == "software-organization-runtime-v0.41"
    assert result["context_protocol"] == result["boundary"]["context_protocol"] == "software-context-v0.41"
    assert result["boundary"]["execution_integrity_failure"] is None
    assert result["actor_updates"] == result["critic_updates"] == result["new_backward_calls"] == 0
    assert prepared.case["version"] == "software-organization-v0.40"
    assert owner.phase == "idle" and owner.window_id == "organization-v041:explicit-v041-cpu-control"
    assert len(owner.transport.requests) == result["usage"]["attempts"] == 3
    projection = json.loads((folder / "raw-transport/request-00003/projection.json").read_text())
    assert projection["version"] == "software-context-v0.41"
    removed = projection["deduplication"]["removed_values"]
    assert any(row["path"].endswith("/initial_diagnostics") for row in removed)
    assert any(row["path"].endswith("/role_task") for row in removed)
    selected = json.loads((folder / "raw-transport/request-00003/selected-request.json").read_text())
    latest = json.loads(selected["messages"][-1]["content"])
    assert len(latest["observation"]["initial_diagnostics"]) == 1
    assert "shared team delivery" in latest["role_task"]
    assert any(message["role"] == "tool" for message in selected["messages"])
    runtime = json.loads((folder / "runtime.json").read_text())
    assert runtime["context_protocol"] == "software-context-v0.41"
    evidence = json.loads((folder / "organization-evidence.json").read_text())
    assert evidence["context_protocol"] == "software-context-v0.41"
    assert evidence["action_error_policy"]["version"] == "recoverable-preexecution-action-errors-v0.40"
