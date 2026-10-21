"""Only the changed pre-dispatch cooldown boundary; no network or model."""
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_deepseek_interfaces_v055 as seam
from proworksim.software_benchmark_deepseek_api_v055 import ConcurrencyBusy


@pytest.mark.parametrize("outcome", ["available", "soft_deadline", "hard_halt"])
def test_cooldown_without_inflight_never_replays_an_entered_request(tmp_path, monkeypatch, outcome):
    clock = SimpleNamespace(now=0.0, sleeps=[])
    monkeypatch.setattr(seam.time, "monotonic", lambda: clock.now)

    def sleep(seconds):
        clock.sleeps.append(seconds)
        clock.now += seconds

    monkeypatch.setattr(seam.time, "sleep", sleep)

    class Client:
        def __init__(self):
            self.admissions = []
            self.actual_http_requests = 0
            self.ledger = SimpleNamespace(snapshot=lambda: {
                "inflight_count": 0, "admission_wait_seconds": 30.0,
                "halted": "credential_hard_halt" if outcome == "hard_halt" else None})

        def complete(self, request, *, request_id, **kwargs):
            self.admissions.append(request_id)
            if len(self.admissions) == 1 or outcome != "available":
                raise ConcurrencyBusy("provider_cooldown_before_reservation")
            self.actual_http_requests += 1
            return {"id": "one-actual-response", "model": "deepseek-flash",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": "fixture"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}

    client = Client()
    adapter = seam.DeepSeekAdapter(client=client, arm="PROJECT", thinking=False,
        slot_id="synthetic-cooldown", condition_id="PROJECT-nonthinking", folder=tmp_path / "ledger",
        allowed_tool_names=set(), soft_at=6.0, hard_at=10.0)
    request = adapter.request([{"role": "user", "content": "Neutral fixture"}], [])
    if outcome == "available":
        adapter.complete(request)
        assert client.actual_http_requests == 1 and len(client.admissions) == 2
        assert adapter.ledger.attempts == 1 and adapter.ledger.actual == 120
        assert adapter.halted is None and clock.sleeps == [5.0]
    else:
        with pytest.raises(seam.RemoteEpisodeBoundary) as stopped:
            adapter.complete(request)
        assert client.actual_http_requests == 0
        assert adapter.ledger.attempts == 0 and adapter.ledger.actual == 0
        assert adapter.ledger.inflight is None
        if outcome == "soft_deadline":
            assert str(stopped.value) == "soft_deadline_during_provider_admission_wait"
            assert clock.sleeps == [5.0, 1.0] and len(client.admissions) == 2
        else:
            assert str(stopped.value) == "global_cny_budget_pre_dispatch_stop"
            assert clock.sleeps == [] and len(client.admissions) == 1
    assert len(set(client.admissions)) == 1
