"""Explicit situation, public-path and real outcome-timing controls."""

import copy
import json
import uuid
from unittest.mock import patch

from proworksim.domains.decision_team import expected_metrics
from proworksim.model_policy import ModelPolicy
from proworksim.staff_runtime import StaffRuntime
from proworksim.storage import digest, json_bytes
from proworksim.templates.learning_work import build_learning_case, controlled_pair, registry
from proworksim.work_interface import WorkInterface
from scripts.learning_work_experiment_v014 import records, run_case


def test_catalog_declares_all_business_decisions_and_one_source_family():
    catalog = registry()
    assert len(catalog["situations"]) == 40
    assert catalog["independent_test_source_families"] == []
    assert len({row["family"] for row in catalog["situations"]}) == 1
    for row in catalog["situations"]:
        assert row["split"] == "development" and row["case_share"] == 0.25
        assert {"period", "allowed_statuses", "amount_factor", "deduplication", "order_min_inclusive",
                "order_max_exclusive", "basis_provider", "audit_provider", "prepared_submission"} <= set(row["business_facts"])
        assert "facts_seed" not in row
    for pool in {row["pool"] for row in catalog["situations"]}:
        for position in (0, 1):
            assert {row["task"] for row in catalog["situations"] if row["pool"] == pool and row["fact_position"] == position} == {"handoff", "implement", "review", "chain"}


def test_same_exact_case_has_identical_actual_prepared_business_state(tmp_path):
    # Includes SQL build, wrong submission, swapped holders and old versions.
    for case_id in ["train-v14-f1-review", "locked_information-v14-f1-review"]:
        first, second = [build_learning_case(case_id, tmp_path / (case_id + str(index))) for index in range(2)]
        assert first.prefix["prepared_business_state_sha256"] == second.prefix["prepared_business_state_sha256"]
        assert first.prefix["experience"]["events"]
        assert first.prefix["credited_to_current_actor"] is False


def test_actual_chain_waits_fit_declared_limits_and_reward_to_go_excludes_past_handoff(tmp_path):
    result = run_case("development-v14-f0-chain", tmp_path / "case", communication="requested", control="wrong_sql")
    reward = result["reward"]
    assert reward["eligible"] and reward["reward"] == 0.2
    assert result["waits"]["reviewer"] > 0
    assert all(count <= result["role_limits"][role] for role, count in result["decisions_including_wait_done"].items())
    ledger = reward["ledger"]
    assert sum(event["amount"] for event in ledger["events"]) == reward["reward"]
    early = [event for event in ledger["events"] if event["settlement"] == "event"]
    assert len(early) == 1 and early[0]["term_id"] == "deliver_applicable_basis"
    assert early[0]["sequence"] < ledger["terminal_sequence"]
    assert sum(event["amount"] for event in ledger["events"] if event["sequence"] > early[0]["sequence"]) == 0


class InputCapture:
    """Offline transport fixture. No real model tokens or learning claim."""

    def __init__(self):
        self.requests = []

    def complete(self, request, *, timeout_seconds):
        self.requests.append(copy.deepcopy(request))
        index = len(self.requests)
        action = "read_alias" if index <= 2 else "staff_wait"
        arguments = {"alias": "data" if index == 1 else "basis", "work_id": "TEAM::build"} if index <= 2 else {"reason": "input contract captured"}
        body = {"id": "fixture-" + str(index), "model": "offline-input-capture",
                "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "fixture-tool-" + str(index), "type": "function",
                     "function": {"name": action, "arguments": json.dumps(arguments)}}]}, "finish_reason": "tool_calls"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        return {"http_status": 200, "body": body, "raw_body": json.dumps(body)}


def test_receiver_actual_request_equal_before_information_and_differs_after(tmp_path):
    runs = []
    for index, case in enumerate(controlled_pair()):
        # Controlled noninterference fixture only: same public identity in two
        # isolated directories, not independent live production worlds. No
        # normalization is applied to actual captured model request bytes.
        with patch("proworksim.core.world.uuid.uuid4", return_value=uuid.UUID(int=101)):
            prepared = build_learning_case(case, tmp_path / str(index))
        transport = InputCapture()
        policy = ModelPolicy({"model": "offline-input-capture", "base_url": "http://127.0.0.1:1/v1",
                              "api_key_env": None, "action_protocol": "native_tools",
                              "context_policy": "latest_observation", "max_output_tokens": 64,
                              "budget": {"max_decisions": 3, "max_http_attempts": 3}}, transport=transport)
        runtime = StaffRuntime({"implementer": WorkInterface(prepared.world.session("implementer", "TEAM"), "implementer")},
                               {"implementer": policy}, run_id="controlled-public-identity")
        runtime.step()  # actual input before the first public data read
        provider = prepared.world.session("provider", "TEAM")
        basis = provider.call("read_alias", alias="basis", work_id="TEAM::build", request_key="pair-read")
        provider.call("handoff_information", route_id="basis", work_id="TEAM::build", handoff_key="pair-supply",
                      reference=basis["result"]["reference"], body="Selected exact applicable basis.", request_key="pair-handoff")
        runtime.step()  # actual read of now accessible private basis
        runtime.step()  # actual subsequent request must contain that body
        assert len(transport.requests) == 3
        (tmp_path / f"actual-requests-{index}.json").write_bytes(json_bytes(transport.requests))
        runs.append((prepared, transport.requests, basis["result"]["data"]))
    assert json_bytes(runs[0][1][0]) == json_bytes(runs[1][1][0])
    assert json_bytes(runs[0][1][2]) != json_bytes(runs[1][1][2])
    assert runs[0][2] != runs[1][2]
    products = []
    for prepared, _, basis in runs:
        data = prepared.world.session("implementer", "TEAM").call("read_alias", alias="data", work_id="TEAM::build")["result"]["data"]
        rules = records(basis["tables"]["basis_meta"])[0]
        rules["allowed_statuses"] = [row[0] for row in basis["tables"]["allowed_statuses"]["rows"]]
        products.append(expected_metrics(records(data["tables"]["transactions"]), records(data["tables"]["customers"]), rules))
    assert products[0] != products[1]
    (tmp_path / "information-pair-report.json").write_bytes(json_bytes({
        "version": "controlled-information-input-v0.14", "model_execution": False,
        "construction": "Two isolated CPU fixture directories constructed with the same public UUID. This isolates private-fact changes; it is not independent-world evidence.",
        "normalization_applied_to_requests": False,
        "actual_request_files": ["actual-requests-0.json", "actual-requests-1.json"],
        "first_request_sha256": [digest(json_bytes(row[1][0])) for row in runs],
        "after_read_request_sha256": [digest(json_bytes(row[1][2])) for row in runs],
        "actual_initial_input_equal": True, "actual_after_evidence_input_different": True,
        "independent_expected_products": products, "expected_products_different": True,
    }))
