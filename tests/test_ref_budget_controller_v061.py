"""New endpoint admission and PID1 deadline controls; no model or container."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_ref_budget_v056 import BudgetRefAdapter
from proworksim.software_benchmark_ref_budget_v061 import RecoveryBudgetRefAdapter

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("controller_v061", ROOT / "tools/run_ref_budget_controller_v061.py")
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def identity(port):
    return {"model_revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a", "vllm_version": "0.32.0",
        "raw_release": True, "adapter_sha256": None,
        "model_manifest_sha256": "030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6",
        "context_limit": 131072, "max_output_tokens": 32768, "service_admission_complete": True, "port": port}


@pytest.mark.parametrize("port", [18161, 18162])
def test_owned_port_binding_preserves_original_numerical_and_budget_algorithm(tmp_path, port):
    condition = json.loads((ROOT / "config/v056-condition-REF_B5000K.json").read_text())
    original = BudgetRefAdapter(transport=SimpleNamespace(port=18056), folder=tmp_path / "before",
        slot_id="old", seed=7, service_identity=identity(18056), condition=condition)
    current = RecoveryBudgetRefAdapter(transport=SimpleNamespace(port=port), folder=tmp_path / "after",
        slot_id="old:v061-r1", seed=7, service_identity=identity(port), condition=condition)
    assert current.request_defaults == original.request_defaults
    assert current.limits == original.limits and current.ledger.snapshot() == original.ledger.snapshot()
    assert RecoveryBudgetRefAdapter.complete is BudgetRefAdapter.complete
    assert RecoveryBudgetRefAdapter.count is BudgetRefAdapter.count
    assert current.service_identity["port"] == port
    wrong = copy.deepcopy(identity(port))
    wrong["port"] = 18056
    with pytest.raises(ValueError, match="owned port"):
        RecoveryBudgetRefAdapter(transport=SimpleNamespace(port=port), folder=tmp_path / "bad",
            slot_id="bad", seed=7, service_identity=wrong, condition=condition)


def test_internal_lifetime_uses_hard_pid1_exit_and_rejects_missing_or_expired(monkeypatch):
    registered, timers, exits = [], [], []
    monkeypatch.setattr(controller.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(controller.signal, "signal", lambda sig, handler: registered.append((sig, handler)))
    monkeypatch.setattr(controller.signal, "setitimer", lambda kind, delay: timers.append((kind, delay)))
    monkeypatch.setattr(controller.os, "_exit", exits.append)
    controller.install_lifecycle_deadline({"diagnostic": True, "maximum_lifecycle_seconds": 180, "lifecycle_deadline": 250.0})
    assert timers == [(controller.signal.ITIMER_REAL, 150.0)]
    registered[0][1](controller.signal.SIGALRM, None)
    assert exits == [124]
    for bad in ({"diagnostic": False},
                {"diagnostic": False, "maximum_lifecycle_seconds": 24000, "lifecycle_deadline": 99},
                {"diagnostic": True, "maximum_lifecycle_seconds": 24000, "lifecycle_deadline": 200}):
        with pytest.raises(ValueError):
            controller.install_lifecycle_deadline(bad)
