"""Real OpenHands machinery, programmed CPU responses and no provider calls."""
import pytest

pytest.importorskip("openhands.sdk")

from openhands.sdk.event import AgentErrorEvent  # noqa: E402
from proworksim.harness_sdk import HarnessWorker  # noqa: E402
from proworksim.software_benchmark_managed_worker_v056 import (  # noqa: E402
    _ExecutionFailureBoundaryMixin, worker_type,
)
from proworksim.staff_runtime import PolicyBoundaryError  # noqa: E402
from test_harness_sdk_v016 import CONFIG, TOOLS, FixtureTransport, call  # noqa: E402


class ProgrammedWorker(_ExecutionFailureBoundaryMixin, HarnessWorker):
    """The production boundary on real SDK; deadline transport is not under test."""


def test_actual_sdk_tool_exception_retains_first_failure_without_second_call(tmp_path):
    transport = FixtureTransport([call("write_note", {"text": "first"})])
    effects, events = [], []

    def execute(*args):
        effects.append(args)
        raise ValueError("Managed world port raised: timed out")

    worker = ProgrammedWorker("A", TOOLS, CONFIG, transport, execute,
        event_sink=lambda kind, value: events.append((kind, value)), directory=tmp_path / "sdk")
    try:
        with pytest.raises(PolicyBoundaryError, match="timed out") as caught:
            worker.step({}, {"run_id": "cpu", "opportunity_id": "1"})
        assert caught.value.status == "execution_integrity_error"
        assert len(transport.requests) == len(effects) == 1
        assert worker._completions == worker._executions == 1
        assert worker.meter["reported_total_tokens"] == 20
        assert worker.meter["http_attempts"] == worker.meter["decisions"] == 1
        error = caught.value.details["managed_execution_failure"]
        assert error["matches_admitted_action"] is True
        assert error["world_result_known"] is False and error["automatic_retry"] is False
        assert error["original_sdk_error"]["kind"] == "AgentErrorEvent"
        assert "timed out" in error["original_sdk_error"]["error"]
        assert any(kind == "managed_execution_error_v056" for kind, _ in events)
        assert not any(kind == "model_format_feedback" for kind, _ in events)
        with pytest.raises(PolicyBoundaryError, match="reuse is forbidden"):
            worker.step({}, {"run_id": "cpu", "opportunity_id": "2"})
        assert len(transport.requests) == len(effects) == 1
        assert worker.meter["decisions"] == 1
    finally:
        worker.close()


def test_returned_business_rejection_remains_one_action_per_later_opportunity(tmp_path):
    transport = FixtureTransport([call("write_note", {"text": "first"}),
                                  call("write_note", {"text": "later"}, "second")])
    effects = []
    worker = ProgrammedWorker("A", TOOLS, CONFIG, transport,
        lambda *args: effects.append(args) or {"ok": False, "error": "known fixture rejection"},
        directory=tmp_path / "sdk")
    try:
        for index in (1, 2):
            result = worker.step({}, {"run_id": "cpu", "opportunity_id": str(index)})
            assert result["executed"] is True and result["result"]["ok"] is False
            assert len(transport.requests) == len(effects) == index
            assert worker.snapshot()["managed_execution_failure"] is None
        with pytest.raises(RuntimeError, match="second model decision"):
            worker._complete([], [])
        assert len(transport.requests) == len(effects) == 2
    finally:
        worker.close()


def test_unmatched_sdk_error_is_integrity_failure_and_default_factory_uses_boundary(tmp_path):
    from proworksim.software_calibration_collector_v051 import worker_type as previous

    assert issubclass(worker_type(), previous())
    assert issubclass(worker_type(), _ExecutionFailureBoundaryMixin)
    transport = FixtureTransport([])
    worker = ProgrammedWorker("A", TOOLS, CONFIG, transport, lambda *_: {"ok": True},
                              directory=tmp_path / "sdk")
    try:
        worker._in_step = True
        worker._completions = 1
        worker._association = {"call_id": "expected", "opportunity_id": "1"}
        worker._pending = {"name": "write_note", "tool_call_id": "expected-tool"}
        with pytest.raises(PolicyBoundaryError, match="does not match") as caught:
            worker._on_sdk_event(AgentErrorEvent(tool_name="write_note", tool_call_id="wrong-tool",
                                                 error="Unassociated SDK event"))
        assert caught.value.status == "execution_integrity_error"
        assert caught.value.details["managed_execution_failure"]["matches_admitted_action"] is False
        assert transport.requests == []
    finally:
        worker.close()
