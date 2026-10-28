"""Admit the reduced-reservation REF deployment from actual startup evidence.

Log prefixes are copied and hashed because service logs keep growing. A single
bounded neutral probe per owned resident verifies tokenization and accounting;
it never retries or uses benchmark tasks as preparation material.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import stat

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_dispatch_v066 import BATCH_ROOT
from .software_benchmark_exact_transport_v054 import HTTPFailure, TEMPLATE_KEYS
from .software_benchmark_ref_deployment_v054 import AuthenticatedLoopbackHTTP
from .software_benchmark_ref_service_v056 import MANIFEST_SHA, MODEL_REVISION, MODEL_NAME, server_arguments
from .storage import digest

VERSION = "v066-model-capacity-neutral-r1"
CONTEXT = 131072
PORTS = tuple(range(18210, 18216))
MAX_PREFIX_BYTES = 32 * 1024**2
NEUTRAL_SEED = 20261028064
NEUTRAL_OUTPUT_TOKENS = 128
NEUTRAL_TOTAL_TOKENS = 2048
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
CAPACITY = re.compile(
    r"GPU KV cache size:\s*([0-9][0-9,]*)\s+tokens,\s*"
    r"Maximum concurrency for\s+([0-9][0-9,]*)\s+tokens per request:\s*([0-9]+(?:\.[0-9]+)?)x")


class ModelAdmissionFailure(RuntimeError):
    def __init__(self, message, receipt):
        super().__init__(message)
        self.receipt = receipt


def validate_spec(spec):
    index = spec.get("index")
    if type(index) is not int or index not in range(6):
        raise ValueError("Only the six owned full-evaluation residents may be admitted")
    root = (BATCH_ROOT / "residents" / f"model-{index}").resolve()
    expected = server_arguments(PORTS[index])
    expected[expected.index("--gpu-memory-utilization") + 1] = "0.6"
    if (Path(spec.get("root", "/")).resolve() != root
            or spec.get("port") != PORTS[index]
            or spec.get("endpoint") != f"http://127.0.0.1:{PORTS[index]}"
            or spec.get("api_key_file") != str(root / "api-key.private")
            or spec.get("model_revision") != MODEL_REVISION
            or spec.get("model_manifest", {}).get("sha256") != MANIFEST_SHA
            or spec.get("server_arguments") != expected):
        raise ValueError("Capacity qualification must bind the exact raw BF16/context131072/single-sequence 0.6 deployment")
    return root


def parse_capacity(stdout, stderr, *, expected_context=CONTEXT):
    """Pure parser: reject missing, insufficient or conflicting startup capacities."""
    values = []
    for name, raw in (("stdout", stdout), ("stderr", stderr)):
        text = ANSI.sub("", raw.decode("utf-8", "replace"))
        for match in CAPACITY.finditer(text):
            tokens, context, concurrency = match.groups()
            values.append({"stream": name, "kv_tokens": int(tokens.replace(",", "")),
                           "actual_context": int(context.replace(",", "")),
                           "maximum_concurrency": float(concurrency), "matched_line": match.group(0)})
    if not values:
        raise ValueError("Owned startup logs do not contain the actual GPU KV capacity line")
    shapes = {(v["kv_tokens"], v["actual_context"], v["maximum_concurrency"]) for v in values}
    if len(shapes) != 1:
        raise ValueError("Conflicting startup capacity records cannot qualify one resident")
    result = values[-1]
    if (result["actual_context"] != expected_context or result["kv_tokens"] < expected_context
            or not math.isfinite(result["maximum_concurrency"]) or result["maximum_concurrency"] < 1.0):
        raise ValueError("Actual cache cannot retain one complete declared context")
    return {**result, "matching_log_records": len(values), "single_full_context_capacity_passed": True}


def _prefix(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        information = os.fstat(handle.fileno())
        if not stat.S_ISREG(information.st_mode) or information.st_size > MAX_PREFIX_BYTES:
            raise ValueError("Expected bounded owned startup log file")
        data = handle.read(information.st_size)
        if len(data) != information.st_size:
            raise ValueError("Owned startup log shrank while its prefix was being captured")
    return data, {"path": str(Path(path).resolve()), "prefix_bytes": len(data),
                  "prefix_sha256": digest(data), "source_size_at_open": information.st_size,
                  "file_may_continue_growing": True}


def qualify_capacity(spec, output_dir=None):
    """Read/copy two log prefixes once. Return only a successful immutable receipt."""
    root = validate_spec(spec)
    output = Path(output_dir or root / "capacity-admission").resolve()
    if not output.is_relative_to(root) or output == root:
        raise ValueError("Capacity evidence must stay in this owned resident directory")
    output.mkdir(parents=True, exist_ok=False)
    record = {"version": VERSION, "utc": datetime.now(timezone.utc).isoformat(),
        "index": spec["index"], "endpoint": spec["endpoint"], "model_revision": MODEL_REVISION,
        "model_manifest": spec["model_manifest"], "server_arguments": spec["server_arguments"],
        "requested_context": CONTEXT, "gpu_memory_utilization": .6, "passed": False,
        "model_calls": 0, "adapter": reference(__file__), "prefixes": {}}
    captured = {}
    try:
        for name in ("stdout", "stderr"):
            data, original = _prefix(root / f"service.{name}.log")
            captured[name] = data
            record["prefixes"][name] = {"original": original,
                "frozen_prefix": write_new(output / f"service.{name}.prefix.log", data)}
        record["actual_capacity"] = parse_capacity(captured["stdout"], captured["stderr"])
        record.update(passed=True, status="actual_startup_capacity_admitted")
    except Exception as error:
        record.update(status="capacity_not_admitted", error={"type": type(error).__name__, "message": str(error)})
        receipt = write_new(output / "receipt.json", record)
        raise ModelAdmissionFailure(str(error), receipt) from error
    return write_new(output / "receipt.json", record)


def neutral_request():
    return {"model": MODEL_NAME, "messages": [{"role": "user", "content": "Reply with the single word READY."}],
        "max_tokens": NEUTRAL_OUTPUT_TOKENS, "temperature": .6, "top_p": .95, "top_k": 20,
        "min_p": 0., "presence_penalty": 0., "repetition_penalty": 1., "stream": False,
        "seed": NEUTRAL_SEED, "chat_template_kwargs": {"enable_thinking": True},
        "add_generation_prompt": True, "continue_final_message": False, "add_special_tokens": False}


def validate_tokenization(value):
    tokens, count = value.get("tokens"), value.get("count")
    if (not isinstance(tokens, list) or not tokens or type(count) is not int or count != len(tokens)
            or any(type(token) is not int or token < 0 for token in tokens)
            or value.get("max_model_len") != CONTEXT
            or count + NEUTRAL_OUTPUT_TOKENS > NEUTRAL_TOTAL_TOKENS):
        raise ValueError("Neutral exact count/context differs or exceeds the approved 2048-token envelope")
    return count


def validate_probe_response(response, prompt_count):
    usage, choices = response.get("usage", {}), response.get("choices")
    output = usage.get("completion_tokens")
    if (response.get("model") != MODEL_NAME
            or usage.get("prompt_tokens") != prompt_count or type(output) is not int
            or not 0 < output <= NEUTRAL_OUTPUT_TOKENS
            or usage.get("total_tokens") != prompt_count + output
            or type(usage.get("prompt_tokens")) is not int or type(usage.get("total_tokens")) is not int
            or usage["total_tokens"] > NEUTRAL_TOTAL_TOKENS
            or not isinstance(choices, list) or len(choices) != 1
            or not isinstance(choices[0], dict) or not isinstance(choices[0].get("message"), dict)
            or choices[0].get("finish_reason") not in {"stop", "length"}):
        raise ValueError("Neutral completion lacks a complete response with exact bounded usage")
    details = usage.get("completion_tokens_details") or {}
    if "reasoning_tokens" in details and (type(details["reasoning_tokens"]) is not int
                                          or not 0 <= details["reasoning_tokens"] <= output):
        raise ValueError("Neutral reasoning token accounting is inconsistent")
    return usage


def run_neutral_probe(spec, capacity_ref, output_dir=None, *, transport=None):
    """One preparation generation per resident; failure is preserved, never retried."""
    from .software_benchmark_dispatch_v066 import require_v066_allowed
    require_v066_allowed("v066.model.start")
    root = validate_spec(spec)
    capacity = json.loads(checked(capacity_ref).read_bytes())
    if (capacity.get("version") != VERSION or capacity.get("passed") is not True
            or capacity.get("endpoint") != spec["endpoint"] or capacity.get("index") != spec["index"]
            or capacity.get("server_arguments") != spec["server_arguments"]
            or capacity.get("model_revision") != MODEL_REVISION
            or capacity.get("adapter") != reference(__file__)):
        raise ValueError("Neutral probe requires this exact deployment's admitted capacity")
    output = Path(output_dir or root / "neutral-probe").resolve()
    if not output.is_relative_to(root) or output == root:
        raise ValueError("Neutral evidence must stay in this owned resident directory")
    output.mkdir(parents=True, exist_ok=False)
    write_new(root / "neutral-probe-once.json", {"version": VERSION, "output": str(output),
        "endpoint": spec["endpoint"], "maximum_generation_calls": 1, "maximum_total_tokens": NEUTRAL_TOTAL_TOKENS})
    request = neutral_request()
    request_ref = write_new(output / "request.json", request)
    record = {"version": VERSION, "utc": datetime.now(timezone.utc).isoformat(), "index": spec["index"],
        "endpoint": spec["endpoint"], "model_revision": MODEL_REVISION, "model_manifest": spec["model_manifest"],
        "capacity": capacity_ref, "request": request_ref, "seed": NEUTRAL_SEED,
        "preparation_only": True, "benchmark_task_used": False, "automatic_retry": False,
        "tokenize_requests": 0, "generation_requests": 0, "passed": False,
        "known_actual_tokens": 0, "uncertain_reserved_tokens": 0, "adapter": reference(__file__)}
    try:
        client = transport or AuthenticatedLoopbackHTTP(spec["endpoint"], spec["api_key_file"])
        if client.port != spec["port"] or client.timeout_seconds != 1800:
            raise ValueError("Neutral probe transport differs from the admitted direct loopback service")
        token_request = {key: request[key] for key in TEMPLATE_KEYS if key in request}
        write_new(output / "tokenize-request.json", token_request)
        record["tokenize_requests"] = 1
        tokenized = client.post("/tokenize", token_request)
        record["tokenization"] = write_new(output / "tokenization.json", tokenized)
        prompt_count = validate_tokenization(tokenized)
        record["uncertain_reserved_tokens"] = prompt_count + NEUTRAL_OUTPUT_TOKENS
        # Freeze the pre-dispatch reservation before sending the sole completion.
        write_new(output / "generation-intent.json", {"request": request_ref,
                  "reserved_input_plus_output_tokens": record["uncertain_reserved_tokens"]})
        record["generation_requests"] = 1
        response = client.post("/v1/chat/completions", request)
        record["response"] = write_new(output / "response.json", response)
        usage = validate_probe_response(response, prompt_count)
        record.update(passed=True, status="neutral_exact_accounting_admitted", usage=usage,
                      known_actual_tokens=usage["total_tokens"], uncertain_reserved_tokens=0)
    except Exception as error:
        record.update(status="neutral_probe_technical_unknown", error={"type": type(error).__name__, "message": str(error)})
        if isinstance(error, HTTPFailure):
            record["http_failure"] = error.evidence
        receipt = write_new(output / "receipt.json", record)
        raise ModelAdmissionFailure(str(error), receipt) from error
    return write_new(output / "receipt.json", record)
