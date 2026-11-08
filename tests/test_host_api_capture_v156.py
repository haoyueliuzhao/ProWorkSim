"""CPU-only real v145 client/ledger flow with scripted transports."""

import json

import pytest

from proworksim import software_benchmark_host_api_v156 as host
from proworksim import software_input_provenance_v156 as provenance
from test_deepseek_resilience_v145 import Script, body, failure, setup


def test_physical_retry_captures_both_originals_and_authoritative_usage(tmp_path):
    view, _, wire, kw, _ = setup(tmp_path)
    returned = {**body(), "system_fingerprint": "synthetic-fingerprint"}
    script = Script([failure(), returned])
    client = view.DeepSeekClient(
        api_key="synthetic",
        allowed_tool_names=set(),
        transport=script,
        sleep=lambda _: None,
        jitter=lambda: 0,
    )

    def annotate(payload, context):
        origin = provenance.SourceFragment(
            "Task", "task-source", "task-event", context["member_id"]
        )
        payload["messages"][0]["content"] = provenance.AnnotatedText(
            (provenance.TextSegment(payload["messages"][0]["content"], origin),)
        )
        return {"payload": payload}

    host.instrument_client(client, capture_root=tmp_path / "captures", annotate_payload=annotate)
    assert client.complete(wire, **kw) == returned
    receipts = client.provenance_capture.receipts()
    assert len(receipts) == len(script.calls) == 2
    assert receipts[0]["request_id"].endswith(":http-1")
    assert receipts[1]["request_id"].endswith(":http-2")
    originals = [provenance.load_persisted_request(r["request_capture"]) for r in receipts]
    assert originals[0].payload_bytes == originals[1].payload_bytes
    assert originals[0].payload_bytes == host.transport_canonical(wire).encode()
    assert (
        originals[0].manifest["identity"]["attempt_id"]
        != originals[1].manifest["identity"]["attempt_id"]
    )
    assert receipts[0]["response_metadata"]["outcome"] == "http_error"
    assert (
        receipts[1]["response_metadata"]["provider_fingerprint"]["value"] == "synthetic-fingerprint"
    )
    assert json.loads(open(receipts[1]["response_original_ref"]["path"]).read()) == returned
    reconciled = provenance.reconcile_ledgers(
        [r["response_metadata"] for r in receipts],
        [r["ledger_entry_for_reconciliation"] for r in receipts],
    )
    assert reconciled["passed"] and reconciled["physical_request_count"] == 2
    assert reconciled["known_actual_total_tokens"] == 13
    assert not reconciled["usage_complete"]
    assert client.ledger.snapshot()["unknown_tokens_upper"] == 30
    assert client.provenance_capture.errors() == []


def test_success_capture_failure_does_not_replay_or_erase_settlement(tmp_path, monkeypatch):
    view, _, wire, kw, _ = setup(tmp_path)
    script = Script([body(), body("forbidden-second-call")])
    client = view.DeepSeekClient(api_key="synthetic", allowed_tool_names=set(), transport=script)
    host.instrument_client(client, capture_root=tmp_path / "captures")
    original_write = host._write

    def disk_failure(path, value):
        if path.name == "response-original.json":
            raise OSError("synthetic capture storage failure")
        return original_write(path, value)

    monkeypatch.setattr(host, "_write", disk_failure)
    assert client.complete(wire, **kw)["id"] == "response-1"
    assert len(script.calls) == 1
    assert client.ledger.snapshot()["known_actual_tokens"] == 13
    receipt = client.provenance_capture.receipts()[0]
    assert receipt["ledger_record"]["status"] == "settled"
    assert receipt["response_metadata"]["usage"]["total_tokens"] == 13
    assert receipt["observer_errors"][0]["phase"] == "response_original_capture"


def test_explicit_fork_preserves_capture_and_isolates_active_attempts(tmp_path):
    view, _, wire, kw, _ = setup(tmp_path)
    first_script = Script([TimeoutError("synthetic")])
    second_script = Script([body("child-response")])
    parent = view.DeepSeekClient(
        api_key="synthetic", allowed_tool_names=set(), transport=first_script
    )
    # Existing client owns fork creation; this zero-network factory supplies a
    # distinct scripted transport, just as the production fork owns DirectHTTPS.
    parent.fork_for_episode = lambda: view.DeepSeekClient(
        api_key="synthetic",
        allowed_tool_names=set(),
        transport=second_script,
    )
    host.instrument_client(parent, capture_root=tmp_path / "captures")
    child = parent.fork_for_episode()
    assert parent.provenance_capture is not child.provenance_capture
    assert parent.provenance_capture.store is child.provenance_capture.store
    assert child.complete(wire, **kw)["id"] == "child-response"
    another = {**kw, "request_id": kw["request_id"][:-4] + "0002"}
    with pytest.raises(TimeoutError):
        parent.complete(wire, **another)
    receipts = parent.provenance_capture.receipts()
    assert len(receipts) == 2 and [r["ledger_record"]["status"] for r in receipts] == [
        "settled",
        "unknown",
    ]
    assert receipts[1]["response_metadata"]["outcome"] == "transport_unknown"
    assert parent.provenance_capture.active is child.provenance_capture.active is None
    assert len(first_script.calls) == len(second_script.calls) == 1
