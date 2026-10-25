"""Memory-profile admission and neutral accounting, using only CPU mock transport."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_model_capacity_v061 as capacity
from proworksim.software_benchmark_exact_transport_v054 import HTTPFailure


LINE = b"[kv_cache_utils.py] GPU KV cache size: 850,000 tokens, Maximum concurrency for 131,072 tokens per request: 6.49x\n"


def spec(tmp_path, monkeypatch, index=0):
    monkeypatch.setattr(capacity, "BATCH_ROOT", tmp_path / "batch")
    root = capacity.BATCH_ROOT / "residents-compiler-r4" / f"model-{index}"
    root.mkdir(parents=True)
    args = capacity.server_arguments(capacity.PORTS[index])
    args[args.index("--gpu-memory-utilization") + 1] = "0.6"
    return {"index": index, "root": str(root), "port": capacity.PORTS[index],
            "endpoint": f"http://127.0.0.1:{capacity.PORTS[index]}", "api_key_file": str(root / "api-key.private"),
            "model_revision": capacity.MODEL_REVISION, "model_manifest": {"sha256": capacity.MANIFEST_SHA},
            "server_arguments": args}


def admitted(tmp_path, monkeypatch):
    value = spec(tmp_path, monkeypatch)
    root = Path(value["root"])
    (root / "service.stdout.log").write_bytes(LINE)
    (root / "service.stderr.log").write_bytes(b"")
    return value, capacity.qualify_capacity(value)


@pytest.mark.parametrize("line", [b"no actual capacity", LINE.replace(b"850,000", b"130,000"),
    LINE.replace(b"131,072", b"65,536"), LINE.replace(b"6.49x", b"0.99x"),
    LINE + LINE.replace(b"850,000", b"900,000")])
def test_missing_smaller_or_conflicting_actual_capacity_is_rejected(line):
    with pytest.raises(ValueError):
        capacity.parse_capacity(line, b"")


def test_ansi_and_matching_duplicate_logs_parse_one_capacity():
    result = capacity.parse_capacity(b"\x1b[32m" + LINE + b"\x1b[0m", LINE)
    assert result["kv_tokens"] == 850000 and result["actual_context"] == 131072
    assert result["matching_log_records"] == 2 and result["single_full_context_capacity_passed"]


def test_log_prefix_is_frozen_even_when_service_keeps_appending(tmp_path, monkeypatch):
    value, ref = admitted(tmp_path, monkeypatch)
    receipt = json.loads(Path(ref["path"]).read_bytes())
    log = Path(value["root"]) / "service.stdout.log"
    log.write_bytes(LINE + b"later formal output\n")
    prefix = receipt["prefixes"]["stdout"]
    assert prefix["original"]["prefix_bytes"] == len(LINE)
    assert Path(prefix["frozen_prefix"]["path"]).read_bytes() == LINE
    assert receipt["passed"] is True and receipt["requested_context"] == 131072


def test_invalid_capacity_keeps_prefix_and_failure_receipt(tmp_path, monkeypatch):
    value = spec(tmp_path, monkeypatch)
    root = Path(value["root"])
    (root / "service.stdout.log").write_bytes(LINE.replace(b"6.49x", b"0.40x"))
    (root / "service.stderr.log").write_bytes(b"retained service output")
    with pytest.raises(capacity.ModelAdmissionFailure) as caught:
        capacity.qualify_capacity(value)
    result = json.loads(Path(caught.value.receipt["path"]).read_bytes())
    assert result["passed"] is False and len(result["prefixes"]) == 2


def test_context_or_model_settings_cannot_change_with_memory_reservation(tmp_path, monkeypatch):
    value = spec(tmp_path, monkeypatch)
    value["server_arguments"][value["server_arguments"].index("--max-model-len") + 1] = "65536"
    with pytest.raises(ValueError, match="exact raw"):
        capacity.validate_spec(value)


def test_neutral_probe_has_one_fixed_generation_and_complete_exact_usage(tmp_path, monkeypatch):
    from proworksim import software_benchmark_dispatch_v061 as policy
    monkeypatch.setattr(policy, "require_v061_allowed", lambda *_: {})
    value, qualified = admitted(tmp_path, monkeypatch)
    calls = []
    def post(path, body):
        calls.append((path, body))
        if path == "/tokenize":
            return {"tokens": [1, 2, 3], "count": 3, "max_model_len": 131072}
        assert body == capacity.neutral_request()
        return {"model": capacity.MODEL_NAME, "choices": [{"message": {"content": "READY"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}
    transport = SimpleNamespace(port=value["port"], timeout_seconds=1800, post=post)
    receipt = capacity.run_neutral_probe(value, qualified, transport=transport)
    result = json.loads(Path(receipt["path"]).read_bytes())
    assert result["passed"] is True and result["known_actual_tokens"] == 5
    assert result["uncertain_reserved_tokens"] == 0 and result["generation_requests"] == 1
    assert [item[0] for item in calls] == ["/tokenize", "/v1/chat/completions"]
    assert "tools" not in calls[0][1] and "max_tokens" not in calls[0][1]
    with pytest.raises(FileExistsError):
        capacity.run_neutral_probe(value, qualified, Path(value["root"]) / "another-probe", transport=transport)
    assert len(calls) == 2


def test_http_failure_retains_raw_error_and_uncertain_reservation_no_retry(tmp_path, monkeypatch):
    from proworksim import software_benchmark_dispatch_v061 as policy
    monkeypatch.setattr(policy, "require_v061_allowed", lambda *_: {})
    value, qualified = admitted(tmp_path, monkeypatch)
    paths = []
    def post(path, body):
        paths.append(path)
        if path == "/tokenize":
            return {"tokens": [1, 2], "count": 2, "max_model_len": 131072}
        raise HTTPFailure("Non-200; no redirect or retry", status=500, raw_body="original failure")
    transport = SimpleNamespace(port=value["port"], timeout_seconds=1800, post=post)
    with pytest.raises(capacity.ModelAdmissionFailure) as caught:
        capacity.run_neutral_probe(value, qualified, transport=transport)
    result = json.loads(Path(caught.value.receipt["path"]).read_bytes())
    assert paths == ["/tokenize", "/v1/chat/completions"]
    assert result["passed"] is False and result["uncertain_reserved_tokens"] == 130
    assert result["http_failure"]["raw_response_body"] == "original failure"
    assert result["known_actual_tokens"] == 0


@pytest.mark.parametrize("tokenized", [
    {"tokens": [1], "count": 2, "max_model_len": 131072},
    {"tokens": [1], "count": 1, "max_model_len": 65536},
    {"tokens": [1] * 2000, "count": 2000, "max_model_len": 131072},
])
def test_count_or_context_mismatch_is_rejected_before_generation(tokenized):
    with pytest.raises(ValueError):
        capacity.validate_tokenization(tokenized)


def test_completion_accounting_must_match_tokenize():
    response = {"model": capacity.MODEL_NAME, "choices": [{"message": {}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 128, "total_tokens": 135}}
    assert capacity.validate_probe_response(response, 7)["total_tokens"] == 135
    with pytest.raises(ValueError):
        capacity.validate_probe_response(response, 6)
