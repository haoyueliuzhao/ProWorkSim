"""Only the r2 tariff boundary and shared-service circuit breaker controls."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from proworksim.software_benchmark_deepseek_api_v055 import (
    APIUncertainFailure, BudgetLedger, BudgetStopped, ConcurrencyBusy, DeepSeekClient, MODEL,
    settlement_tariff,
)


def _body(identity="success"):
    return {"id": identity, "model": MODEL,
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                      "prompt_cache_hit_tokens": 80, "prompt_cache_miss_tokens": 20}}


def _request():
    return {"model": MODEL, "messages": [{"role": "user", "content": "neutral"}],
            "stream": False, "thinking": {"type": "disabled"}, "max_tokens": 64}


def test_guarded_tariff_boundaries_and_unknown_clock():
    cases = [
        ("2026-10-21T15:00:00+00:00", "2026-10-21T15:03:00+00:00", 2),
        ("2026-10-21T00:54:00+00:00", "2026-10-21T00:54:59+00:00", 2),
        ("2026-10-21T00:54:00+00:00", "2026-10-21T00:55:00+00:00", 1),
        ("2026-10-21T04:05:00+00:00", "2026-10-21T04:06:00+00:00", 1),
        ("2026-10-21T04:05:01+00:00", "2026-10-21T04:06:00+00:00", 2),
        ("2026-10-21T04:30:00+00:00", "2026-10-21T05:30:00+00:00", 2),
        ("2026-10-21T04:30:00+00:00", "2026-10-21T06:01:00+00:00", 1),
        ("2026-10-21T10:05:01+00:00", "2026-10-21T10:06:00+00:00", 2),
        ("2026-10-24T01:00:00+00:00", "2026-10-24T10:00:00+00:00", 2),
        ("2026-10-25T23:00:00+00:00", "2026-10-26T00:55:00+00:00", 1),
        ("2026-10-01T01:00:00+00:00", "2026-10-01T02:00:00+00:00", 1),
        ("2026-10-21T15:00:00", "2026-10-21T15:03:00", 1),
        ("2026-10-21T15:03:00+00:00", "2026-10-21T15:00:00+00:00", 1),
        ("bad-time", "2026-10-21T15:00:00+00:00", 1),
    ]
    for start, end, divisor in cases:
        assert settlement_tariff(start, end)["divisor"] == divisor, (start, end)


def test_peak_reservation_idle_settlement_and_peak_equivalent(tmp_path, monkeypatch):
    times = iter(["2026-10-21T15:00:00+00:00", "2026-10-21T15:03:00+00:00"])
    monkeypatch.setattr("proworksim.software_benchmark_deepseek_api_v055._now", lambda: next(times))
    ledger = BudgetLedger(tmp_path / "tariff.sqlite3")
    ledger.reserve(request_id="idle", slot_id="slot", condition="REF-nonthinking", usage_id="agent",
                   request_sha256="cpu", max_output_tokens=64)
    assert ledger.snapshot()["committed_upper_cny"] == 2.097664
    ledger.settle("idle", _body())
    snapshot = ledger.snapshot()
    assert snapshot["settled_peak_equivalent_cny"] == (80 * 40 + 20 * 2000 + 20 * 8000) / 1e9
    assert snapshot["settled_upper_cny"] == snapshot["settled_peak_equivalent_cny"] / 2
    row = ledger.request_status("idle")
    assert json.loads(row["tariff_basis_json"])["basis"] == "entire_guarded_interval_off_peak"
    assert row["settled_peak_nanoyuan"] == 2 * row["settled_nanoyuan"]


class _SequenceTransport:
    def __init__(self, sequence):
        self.sequence = iter(sequence)
        self.calls = 0

    def request(self, *args):
        value = next(self.sequence)
        self.calls += 1
        if value == "success":
            return _body(f"success-{self.calls}")
        if value is None:
            raise TimeoutError("fixture")
        error = APIUncertainFailure("fixture")
        error.http_status = value
        raise error


@pytest.mark.parametrize("status", [401, 402, 403])
def test_authentication_account_error_immediately_halts_new_calls(tmp_path, status):
    transport = _SequenceTransport([status])
    client = DeepSeekClient(ledger_path=tmp_path / "auth.sqlite3", api_key="fixture",
                           allowed_tool_names=set(), transport=transport)
    with pytest.raises(APIUncertainFailure):
        client.complete(_request(), request_id="first", slot_id="slot", condition="MATCH-thinking")
    snapshot = client.ledger.snapshot()
    assert str(status) in snapshot["halted"]
    assert snapshot["uncertain_reserved_cny"] == 2.097664
    with pytest.raises(BudgetStopped, match="halted"):
        client.complete(_request(), request_id="second", slot_id="slot", condition="MATCH-thinking")
    assert transport.calls == 1


def test_mixed_system_errors_bounded_cooldown_without_replay_and_success_reset(tmp_path, monkeypatch):
    clock = [datetime(2026, 10, 22, 15, 0, tzinfo=timezone.utc)]
    monkeypatch.setattr("proworksim.software_benchmark_deepseek_api_v055._now", lambda: clock[0].isoformat())
    sequence = [None, 400, "success", 429, 503, None, 400, 429, 503, None, "success"]
    transport = _SequenceTransport(sequence)
    client = DeepSeekClient(ledger_path=tmp_path / "streak.sqlite3", api_key="fixture",
                           allowed_tool_names=set(), transport=transport)
    delays = []
    for index, expected in enumerate(sequence):
        if expected == "success":
            client.complete(_request(), request_id=str(index), slot_id="slot", condition="PROJECT-thinking")
            assert client.ledger.snapshot()["consecutive_system_failures"] == 0
            assert client.ledger.snapshot()["cooldown_until_utc"] is None
        else:
            with pytest.raises(APIUncertainFailure):
                client.complete(_request(), request_id=str(index), slot_id="slot", condition="PROJECT-thinking")
        snapshot = client.ledger.snapshot()
        assert snapshot["halted"] is None
        wait = snapshot["admission_wait_seconds"]
        if wait:
            delays.append(wait)
            assert snapshot["inflight_count"] == 0
            with pytest.raises(ConcurrencyBusy, match="cooldown"):
                client.complete(_request(), request_id=f"not-dispatched-{index}",
                                slot_id="slot", condition="PROJECT-thinking")
            assert client.ledger.request_status(f"not-dispatched-{index}") is None
            assert transport.calls == index + 1
            clock[0] += timedelta(seconds=wait + 1)
    assert delays == [30, 60, 120, 240, 300]
    assert snapshot["statuses"] == {"settled": 2, "uncertain": 9}
    assert transport.calls == 11
    assert snapshot["uncertain_reserved_cny"] == 9 * 2.097664


def test_inflight_completion_settles_without_clearing_global_halt(tmp_path):
    ledger = BudgetLedger(tmp_path / "inflight.sqlite3")
    for identity in ("inflight", "failure"):
        ledger.reserve(request_id=identity, slot_id="slot", condition="REF-thinking", usage_id="agent",
                       request_sha256="cpu", max_output_tokens=64)
    ledger.uncertain("failure", {"http_status": 402, "shared_system_failure": True})
    ledger.settle("inflight", _body())
    snapshot = ledger.snapshot()
    assert snapshot["halted"] and snapshot["statuses"] == {"settled": 1, "uncertain": 1}
    assert snapshot["inflight_count"] == 0
