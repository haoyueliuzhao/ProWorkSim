"""Only new capacity preparation guards and partial-accounting failure paths."""
import importlib.util
import json
import os
from pathlib import Path

import pytest

from proworksim.software_benchmark_capacity_guards_v054 import (
    SmokeLedger, check_monitor, check_seal, reference,
)


def test_seal_and_exact_monitor_registration_reject_drift(tmp_path):
    path = tmp_path / "frozen-config.json"
    path.write_text('{"fixed": true}\n')
    seal = {"files": [reference(path)]}
    assert check_seal(seal) is seal
    path.write_text('{"fixed": false}\n')
    with pytest.raises(ValueError, match="changed after sealing"):
        check_seal(seal)
    unit = "proworksim-v054-model-capacity-preparation-r1.service"
    state = {"Id": unit, "ActiveState": "active", "MainPID": "123", "InvocationID": "a" * 32,
             "ControlGroup": "/user.slice/user-1021.slice/user@1021.service/app.slice/" + unit}
    assert check_monitor(state, unit, pid=123)["main_pid"] == 123
    with pytest.raises(ValueError, match="MainPID"):
        check_monitor(state, unit, pid=456)
    with pytest.raises(ValueError, match="invocation changed"):
        check_monitor(state, unit, invocation="b" * 32)


def test_second_partial_request_retains_first_actual_and_unsettled_reservation(tmp_path):
    ledger = SmokeLedger(tmp_path / "ledger.json")
    ledger.prepare(1, 12, 2048)
    ledger.dispatched()
    ledger.settle({"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20})
    ledger.prepare(2, 16384, 2048)
    ledger.dispatched()  # A partial send or model timeout occurs here.
    result = json.loads(ledger.path.read_bytes())
    assert result["generation_calls"] == 2
    assert result["known_actual_tokens"] == 20
    assert result["actual_tokens"] is None
    assert result["unsettled_reserved_tokens"] == 18432
    assert result["uncertain_attempts"] == [2]
    with pytest.raises(ValueError, match="accounting"):
        ledger.settle({"prompt_tokens": 16384, "completion_tokens": 4, "total_tokens": 4})
    assert ledger.summary()["known_actual_tokens"] == 20
    with pytest.raises(ValueError, match="without replay"):
        ledger.prepare(2, 16384, 2048)


def test_ref_api_key_is_injected_after_runtime_without_argv_or_model_loading(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "tools/start_ref_capacity_server_v054.py"
    spec = importlib.util.spec_from_file_location("capacity_secret_bootstrap", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    key = "synthetic-private-key-for-cpu-control-only"
    key_path = tmp_path / "key.private"
    key_path.write_text(key + "\n")
    key_path.chmod(0o600)
    monkeypatch.setenv("VLLM_API_KEY", "unchanged-outside-test")
    monkeypatch.setattr(module.sys, "argv", [str(path), "--api-key-file", str(key_path),
                                            "--", "serve", "synthetic-no-model"])
    observed = {}

    def fake_entry(name, run_name):
        observed.update(name=name, run_name=run_name, key=os.environ["VLLM_API_KEY"],
                        argv=list(module.sys.argv))

    monkeypatch.setattr(module.runpy, "run_module", fake_entry)
    module.main()
    assert observed["key"] == key
    assert key not in json.dumps(observed["argv"])
    assert observed["name"] == "vllm.entrypoints.cli.main"
