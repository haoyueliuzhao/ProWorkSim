import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("v068_inventory_test", ROOT / "tools/prepare_recovery_inventory_v068.py")
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


@pytest.mark.parametrize("claims,requests,eligible", [([], 0, True), ([{"actor": "consumed"}], 0, False), ([], 1, False)])
def test_scope_guard_failure_needs_both_unused_identity_and_zero_requests(claims, requests, eligible):
    row = {"model_key": "DEEPSEEK"}
    entry = {"status": "technical_unknown"}
    result = {"error": {"type": "RuntimeError", "message": "The primary queue reports a shared safety stop"},
        "traceback": "software_benchmark_api_scope_v067.py in primary_cursor",
        "model_dispatch_started": False, "model_calls": 0}
    actual, _ = inventory.classify(row, entry, result, claims, requests, "qualified")
    assert actual is eligible


def test_unsupported_error_or_failed_environment_cannot_be_requeued_by_zero_count():
    row = {"model_key": "DEEPSEEK"}
    entry = {"status": "technical_unknown"}
    result = {"error": {"type": "RuntimeError", "message": "unknown"}, "model_calls": 0,
              "model_dispatch_started": False}
    assert inventory.classify(row, entry, result, [], 0, "qualified")[0] is False
    assert inventory.classify(row, None, None, [], 0, "not_qualified")[0] is False
