"""The API output token envelope bounds explanatory text; it is never an execution input."""

import json

from jsonschema import Draft202012Validator
from . import software_organization_contract_v239 as contract


def request(row):
    wire = contract.request(row)
    fields = wire["tools"][0]["function"]["parameters"]["properties"]
    for key in ("reason", "reconsider_after"):
        del fields[key]["maxLength"]
    return wire


def parse(row, body):
    calls = body["choices"][0]["message"].get("tool_calls") or []
    if len(calls) != 1 or calls[0]["function"]["name"] != "activate_organization":
        raise ValueError("Expected one organization decision")
    proposal = json.loads(calls[0]["function"]["arguments"])
    Draft202012Validator(request(row)["tools"][0]["function"]["parameters"]).validate(proposal)
    return proposal
