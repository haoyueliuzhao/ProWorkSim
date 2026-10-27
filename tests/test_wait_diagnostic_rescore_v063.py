import importlib.util
from pathlib import Path
import threading

import pytest

from proworksim.software_benchmark_shared_server_hold_v057 import SharedServerHold

SPEC = importlib.util.spec_from_file_location(
    "v063_waiter_test", Path(__file__).resolve().parents[1] / "tools/wait_diagnostic_rescore_v063.py")
waiter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(waiter)


def fixture_options(progress):
    stopped = threading.Event()
    calls = []
    options = {
        "validate": lambda _: calls.append("binding"),
        "admit": lambda: calls.append("full_guard"),
        "read_progress": lambda: progress,
        "monotonic": lambda: 0,
        "wait": lambda seconds: (calls.append(("wait", seconds)), stopped.set()),
        "entered": lambda: False,
        "cancelled": lambda: False,
    }
    return stopped, calls, options


PLAN = {"poll_seconds": 30, "maximum_wait_seconds": 86400}


def test_running_parent_only_waits_then_cancellation_prevents_dispatch():
    stopped, calls, options = fixture_options({"phase": "running", "failure": None})
    result = waiter.poll_until_ready(PLAN, stopped, **options)
    assert result == {"status": "cancelled", "dispatch": False}
    assert calls == ["binding", ("wait", 30)]


def test_cancel_file_prevents_even_admission_check():
    stopped, calls, options = fixture_options({"phase": "closed", "failure": None})
    options["cancelled"] = lambda: True
    result = waiter.poll_until_ready(PLAN, stopped, **options)
    assert result["dispatch"] is False
    assert calls == []


def test_closed_parent_requires_full_guard_and_final_binding_check():
    stopped, calls, options = fixture_options({"phase": "closed", "failure": None})
    result = waiter.poll_until_ready(PLAN, stopped, **options)
    assert result["dispatch"] is True
    assert calls == ["binding", "full_guard", "binding"]


def test_revoked_or_changed_authorization_stops_before_dispatch():
    stopped, calls, options = fixture_options({"phase": "closed", "failure": None})

    def denied(_):
        raise SharedServerHold("revoked")

    options["validate"] = denied
    with pytest.raises(SharedServerHold, match="revoked"):
        waiter.poll_until_ready(PLAN, stopped, **options)
    assert calls == []


@pytest.mark.parametrize("progress,entered,expected", [
    ({"phase": "stopped", "failure": "fault"}, False, "parent_stopped"),
    ({"phase": "closed", "failure": None}, True, "already_entered"),
])
def test_parent_failure_or_existing_execution_never_replays(progress, entered, expected):
    stopped, calls, options = fixture_options(progress)
    options["entered"] = lambda: entered
    result = waiter.poll_until_ready(PLAN, stopped, **options)
    assert result["status"] == expected and result["dispatch"] is False
    assert calls == ["binding"]


def test_wait_is_bounded_by_twenty_four_hours():
    stopped, calls, options = fixture_options({"phase": "running", "failure": None})
    clock = iter([0, 86400])
    options["monotonic"] = lambda: next(clock)
    result = waiter.poll_until_ready(PLAN, stopped, **options)
    assert result["status"] == "wait_deadline" and result["dispatch"] is False
    assert calls == ["binding"]
