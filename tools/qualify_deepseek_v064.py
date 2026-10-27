"""Prepare or execute two bounded neutral Flash tool turns under the new cash cap."""
from __future__ import annotations

import argparse
import copy
from decimal import Decimal
import json
import time

from proworksim import software_benchmark_dispatch_v064 as policy
from proworksim import software_benchmark_deepseek_api_v064 as api
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = policy.ROOT
RUN_ROOT = policy.BATCH_ROOT / "api-qualification"
LEDGER = policy.BATCH_ROOT / "api-budget/ledger.sqlite3"
TOKENIZER_MANIFEST = ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
VERSION = "v064-neutral-thinking-tools-qualification-r1"
MAX_CALLS, MAX_TOTAL_TOKENS, MAX_OUTPUT = 2, 8192, 1024
SLOT, CONDITION = "v064:neutral:thinking-tools:r1", "v064-API-PREPARATION"


def first_request():
    return {"model": api.MODEL, "stream": False, "thinking": {"type": "enabled"},
        "reasoning_effort": "high", "top_p": 0.95, "max_tokens": MAX_OUTPUT,
        "user_id": api.slot_user_id(SLOT, CONDITION), "tool_choice": "auto",
        "messages": [{"role": "user", "content":
            'This is a neutral transport check, not a benchmark task. Call probe_echo exactly once with '
            'text "pws-v064-ok". After its result arrives, reply with that same text and do not call more tools.'}],
        "tools": [{"type": "function", "function": {"name": "probe_echo", "description": "Return the supplied neutral text.",
            "parameters": {"type": "object", "properties": {"text": {"type": "string"}},
                           "required": ["text"], "additionalProperties": False}}}]}


def model_admission(models):
    selected = [row for row in models.get("data", []) if row.get("id") == api.MODEL]
    if len(selected) != 1:
        raise ValueError("Expected the unique official deepseek-flash model")
    model = selected[0]
    if (model.get("context_window") != api.PROVIDER_CONTEXT_TOKENS
            or model.get("max_output_tokens") != api.PROVIDER_MAX_OUTPUT_TOKENS):
        raise ValueError("Provider capacities differ from the absolute cash-reservation basis")
    effort = model.get("effort")
    if effort is not None and "high" not in effort.get("supported_levels", []):
        raise ValueError("Provider no longer advertises the frozen thinking effort")
    return {"model_alias": api.MODEL, "name": model.get("name"),
            "context_window": model["context_window"], "max_output_tokens": model["max_output_tokens"],
            "effort": effort, "alias_not_immutable_weights": True}


def followup(original, response):
    choices = response.get("choices", [])
    if len(choices) != 1 or choices[0].get("finish_reason") != "tool_calls":
        raise ValueError("The neutral first response did not complete its requested tool turn")
    message = choices[0]["message"]
    calls = message.get("tool_calls", [])
    if (message.get("role") != "assistant" or not isinstance(message.get("reasoning_content"), str)
            or len(calls) != 1 or calls[0].get("type") != "function"
            or calls[0]["function"].get("name") != "probe_echo"
            or json.loads(calls[0]["function"]["arguments"]) != {"text": "pws-v064-ok"}):
        raise ValueError("The neutral tool or its original reasoning/arguments changed")
    request = copy.deepcopy(original)
    request["messages"].extend([copy.deepcopy(message), {"role": "tool", "tool_call_id": calls[0]["id"],
                                                       "content": '{"echo":"pws-v064-ok"}'}])
    return request


def prepare():
    request = first_request()
    api.validate_payload(request, {"probe_echo"})
    value = {"version": VERSION, "first_request": request, "ledger": str(LEDGER),
             "tokenizer_manifest": reference(TOKENIZER_MANIFEST), "counter_margin_tokens": 128,
             "free_metadata_gets": ["/models", "/user/balance"], "maximum_model_calls": MAX_CALLS,
             "maximum_total_input_output_tokens": MAX_TOTAL_TOKENS, "max_output_tokens": MAX_OUTPUT,
             "sources": [reference(path) for path in (
                 __file__, api.__file__, ROOT / "src/proworksim/software_benchmark_deepseek_contract_v064.py",
                 ROOT / "src/proworksim/software_benchmark_deepseek_tokenizer_v055.py")],
             "benchmark_material_used": False, "cash_cap_CNY": "1500.00", "automatic_retry": False}
    return policy.retain(RUN_ROOT / "plan.json", value)


def execute():
    policy.require_v064_allowed("v064.api.request")
    if (policy.CONSTRAINTS.get("api_neutral_preparation_calls") != MAX_CALLS
            or policy.CONSTRAINTS.get("api_neutral_preparation_total_tokens") != MAX_TOTAL_TOKENS
            or policy.CONSTRAINTS.get("free_api_metadata_requests") != 2):
        raise ValueError("The full grant must separately bind the two neutral API calls and metadata GETs")
    plan_ref = prepare()
    plan = policy.load(plan_ref)
    for ref in plan["sources"]:
        checked(ref)
    write_new(RUN_ROOT / "started.json", {"version": VERSION, "unix": time.time(), "plan": plan_ref,
                                          "authorization": reference(policy.AUTHORIZATION_FILE)})
    actual = 0
    calls, model = [], None
    client = None
    try:
        client = api.DeepSeekClient(ledger_path=LEDGER, api_key=api.load_api_key(ROOT / ".env"),
                                   allowed_tool_names={"probe_echo"}, max_concurrency=64)
        models = client.metadata("models")
        balance = client.metadata("balance")
        model = model_admission(models)
        cny = api.transport.cny_balance(balance)
        metadata = {"version": VERSION, "model": model, "metadata_requests": 2,
                    "provider_is_available": balance.get("is_available"),
                    "positive_CNY_balance": cny is not None and cny > Decimal(0),
                    "cash_cap_is_not_account_balance": True, "API_key_archived": False}
        write_new(RUN_ROOT / "metadata.json", metadata)
        if balance.get("is_available") is False or cny is None or cny <= 0:
            raise ValueError("Provider funds unavailable; stop without changing the CNY1500 cap")
        counter = OfficialDeepSeekCounter(plan["tokenizer_manifest"]["path"],
            manifest_sha256=plan["tokenizer_manifest"]["sha256"], reservation_margin_tokens=128)
        wire = plan["first_request"]
        for number in (1, 2):
            policy.require_v064_allowed("v064.api.request")
            measurement = counter(wire)
            if actual+measurement["prompt_tokens"]+MAX_OUTPUT > MAX_TOTAL_TOKENS:
                raise ValueError("Neutral API preparation cannot exceed its separate token bound")
            request_ref = write_new(RUN_ROOT / f"request-{number}.json", {"wire": wire, "measurement": measurement})
            response = client.complete(wire, request_id=SLOT+":"+str(number), slot_id=SLOT,
                condition=CONDITION, usage_id="preparation", prompt_upper_bound=measurement["prompt_tokens"])
            response_ref = write_new(RUN_ROOT / f"response-{number}.json", response)
            usage = api.normalize_usage(response)
            actual += usage["total_tokens"]
            calls.append({"request": request_ref, "response": response_ref, "usage": usage,
                          "local_counter_reservation": measurement["prompt_tokens"]})
            if number == 1:
                wire = followup(wire, response)
            else:
                choice = response["choices"][0]
                if choice.get("finish_reason") != "stop" or choice["message"].get("tool_calls"):
                    raise ValueError("Neutral tool continuation did not close without another tool")
        result = {"version": VERSION, "passed": True, "actual_input_output_tokens": actual,
                  "model": model, "calls": calls, "model_calls": len(calls), "plan": plan_ref}
    except BaseException as error:
        result = {"version": VERSION, "passed": False, "actual_known_input_output_tokens": actual,
                  "model": model, "calls": calls, "plan": plan_ref,
                  "error": {"type": type(error).__name__, "message": str(error)}}
        if isinstance(error, api.ProviderOutputBoundViolation) and error.authoritative_response is not None:
            result["withheld_response"] = write_new(RUN_ROOT / "withheld-response.json", error.authoritative_response)
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            write_new(RUN_ROOT / "result.json", result)
            raise
    if client is not None:
        result["cash_snapshot"] = client.ledger.snapshot()
        rows = [client.ledger.request_status(SLOT+":"+str(number)) for number in (1, 2)]
        rows = [row for row in rows if row is not None]
        known = [json.loads(row["usage_json"]) for row in rows if row["usage_json"] is not None]
        result["model_calls"] = len(rows)
        result["actual_known_input_output_tokens"] = sum(usage["total_tokens"] for usage in known)
        result["unknown_usage_calls"] = len(rows)-len(known)
        result["complete_actual_input_output_tokens"] = (
            result["actual_known_input_output_tokens"] if len(rows) == len(known) else None)
    write_new(RUN_ROOT / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else execute(), ensure_ascii=False))
