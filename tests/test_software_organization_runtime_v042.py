"""One actual SDK CPU collection checks page decisions and the default v042 path."""
import json

import pytest

from proworksim.software_organization_runtime_v042 import collect_episode
from proworksim.software_organization_v042 import CASE_IDS, MEMBERS, build_software_collaboration_case, case_spec
from test_software_organization_runtime_v038 import CPUOwner, action
from test_software_organization_runtime_v040 import SelectedCPUTransport, tokenize


def test_sdk_page_read_uses_new_opportunity_shared_tokens_and_no_extra_test(tmp_path):
    pytest.importorskip("openhands.sdk")
    owner = CPUOwner({MEMBERS[0]: [action("run_tests"),
        action("read_test_result", report_id="bound-after-first-real-return", cursor="bound-after-first-real-return")]})
    owner.prepare_request = lambda request: (json.dumps(request, ensure_ascii=False, sort_keys=True), None, None)
    owner.tokenizer = tokenize
    owner.transport = SelectedCPUTransport(owner)
    prepared = build_software_collaboration_case(case_spec(CASE_IDS[0], condition="PT"), tmp_path / "case")
    first_pages = []

    def checkpoint(outcome):
        value = (outcome.get("response") or {}).get("result", {})
        if value.get("page", {}).get("index") == 0:
            first_pages.append(value)
            # The explicitly synthetic CPU program uses its actual first tool
            # return to choose a later native call. No model output is repaired.
            owner.script[MEMBERS[0]][1] = action("read_test_result", report_id=value["report_id"], cursor=value["page"]["next_cursor"])

    folder = tmp_path / "collection"
    result = collect_episode(owner, prepared, folder, sampling_seed=42, slot_id="explicit-v042-sdk-cpu-control",
                             on_opportunity=checkpoint)
    assert first_pages and result["boundary"]["execution_integrity_failure"] is None
    assert result["version"] == "software-organization-runtime-v0.42"
    assert result["context_protocol"] == "software-context-v0.42"
    assert result["test_feedback_protocol"] == "paged-public-test-feedback-v0.42"
    assert result["usage"]["decisions"] == result["usage"]["attempts"] == len(owner.transport.requests) == 4
    assert result["usage"]["completion_tokens"] == 4
    assert prepared.world.test_budget.snapshot()["used"] == 1
    assert len(prepared.world._software()["test_reports"]) == 1
    names = [body["choices"][0]["message"]["tool_calls"][0]["function"]["name"] for body in owner.transport.responses]
    assert names == ["run_tests", "staff_done", "read_test_result", "staff_done"]
    first = first_pages[0]
    latest = json.loads((folder / "raw-transport/request-00004/selected-request.json").read_text())
    latest_tool = json.loads(next(message["content"] for message in reversed(latest["messages"]) if message["role"] == "tool"))["result"]
    assert latest_tool["report_id"] == first["report_id"] and latest_tool["page"]["index"] == 1
    assert "directory" not in latest_tool
    projection = json.loads((folder / "raw-transport/request-00004/projection.json").read_text())
    assert projection["version"] == "software-context-v0.42"
    assert projection["protected_prompt_tokens"] <= projection["selected_prompt_tokens"]
    assert projection["protected_headroom_after_margin"] == 16384 - 2048 - 1024 - projection["protected_prompt_tokens"]
    evidence = json.loads((folder / "organization-evidence.json").read_text())
    assert first["report_id"] in evidence["test_reports"]
    assert owner.phase == "idle" and owner.window_id == "organization-v042:explicit-v042-sdk-cpu-control"
