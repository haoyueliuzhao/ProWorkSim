"""Public native CPU controls, local query use, and honest qualification gates."""

import copy

import pytest

from proworksim.reciprocal_interface_v026 import SINGLE_PACKET_BODY
from scripts.reciprocal_carrier_controls_v026 import (
    CarrierProgramOwner,
    business_tools,
    first_requests,
    run_control,
)
from test_reciprocal_data_v026 import catalog as catalog


@pytest.mark.parametrize("condition", ["normal", "single_pass"])
def test_actual_public_native_route_and_no_tokenizer_is_not_qualification(
    tmp_path, catalog, condition
):
    row = run_control(catalog["cases"][0], tmp_path / condition, condition=condition)
    assert row["assessment"]["eligible"] and row["assessment"]["completed"]
    assert row["within_role_budgets"]
    assert row["tool_refusals"] == []
    assert row["passed"] is False  # Official tokenizer proof is mandatory.
    assert row["model_calls"] == row["parameter_updates"] == 0
    if condition == "single_pass":
        (packet,) = row["communication_actions"]
        assert packet["worker_id"] == "consumer"
        assert packet["payload"]["arguments"]["body"] == SINGLE_PACKET_BODY


def test_query_result_changes_actual_normal_demand_explanation():
    owner = CarrierProgramOwner(route="query_first")
    demand = {
        "tables": {
            "demand_meta": {
                "columns": [{"name": "invoice_mode", "type": "VARCHAR"}],
                "rows": [["net_signed"]],
            }
        }
    }
    sample = {
        "reference": {"object_id": "query", "version_id": "v2"},
        "tables": {
            "query_result": {
                "columns": [
                    {"name": "InvoiceNo", "type": "VARCHAR"},
                    {"name": "Quantity", "type": "BIGINT"},
                ],
                "rows": [["C100", -1], ["101", 2]],
            }
        },
    }
    state = {
        "phase": 1,
        "queried": True,
        "materials": {
            "demand-object": {
                "data": demand,
                "reference": {"object_id": "demand-object", "version_id": "v1"},
            }
        },
        "raw_sample_query": sample,
    }
    obs = {"workspaces": {"TEAM": {"demand": "demand-object"}}}
    name, args = owner.choose("consumer", obs, copy.deepcopy(state))
    assert name == "handoff_information"
    assert "1 cancellation/negative rows in 2 rows" in args["body"]
    assert "Retain their signed quantities" in args["body"]
    state["raw_sample_query"]["tables"]["query_result"]["rows"] = [["100", 1], ["101", 2]]
    _, changed = owner.choose("consumer", obs, copy.deepcopy(state))
    assert "0 cancellation/negative rows" in changed["body"]
    assert args["body"] != changed["body"]
    assert owner.visible_choices[0]["actual_query_reference"] == sample["reference"]


def test_request_identity_retains_hidden_identifier_leaks_and_business_definitions():
    left = {
        "messages": [
            {"role": "user", "content": '{"observation":{"actor_id":"maintainer","case_id":"one"}}'}
        ],
        "tools": [],
    }
    right = copy.deepcopy(left)
    right["messages"][0]["content"] = right["messages"][0]["content"].replace("one", "two")
    assert first_requests([left]) != first_requests([right])
    defs = [
        {"function": {"name": "sql_build", "parameters": {"required": ["code_alias"]}}},
        {"function": {"name": "handoff_information", "parameters": {}}},
    ]
    changed = copy.deepcopy(defs)
    changed[0]["function"]["parameters"]["required"] = []
    assert business_tools(defs) != business_tools(changed)
