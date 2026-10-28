from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

FILE = Path(__file__).resolve().parents[1] / "tools/prepare_api_expansion_inventory_v069.py"
spec = importlib.util.spec_from_file_location("api_inventory_v069", FILE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_exact_old_pause_semantics_and_freshness():
    control = {"desired": 0, "since_unix": 10}
    progress = {"unix": 20, "effective_generation_limit": 0,
                "configured_generation_limit": None, "concurrency_control_error": module.PAUSE_ERROR}
    assert module.pause_evidence(control, progress, now=21)["existing_futures_cancelled"] is False
    for change in ({"effective_generation_limit": 1}, {"unix": 9},
                   {"concurrency_control_error": "different error"}):
        with pytest.raises(ValueError):
            module.pause_evidence(control, {**progress, **change}, now=21)
    with pytest.raises(ValueError):
        module.pause_evidence(control, progress, now=201)


def test_all_ever_scheduled_including_unclaimed_stays_owned():
    events = (b'{"kind":"generation_scheduled","slot_id":"a"}\n'
              b'{"kind":"generation_finished","slot_id":"a","status":"not_entered"}\n'
              b'{"kind":"generation_scheduled","slot_id":"b"}\n')
    assert module.scheduled_slots(events) == {"a", "b"}
    with pytest.raises(ValueError):
        module.scheduled_slots(events[:-1])


def test_actual_generation_and_every_possible_consumption_excluded_without_fabrication():
    rows = [{"slot_id": str(i), "slot_index": i, "condition_id": "DEEPSEEK_REF_B5000K",
             "instance_id": str(i)} for i in range(9)]
    generation = {"0": {"status": "closed"}}
    pending = {"1": {"state": "future_no_claim_yet"}}
    allowed, audit = module.classify_target_rows(rows, generation=generation,
        predecessor_allowed={str(i) for i in range(9) if i != 5},
        old_scheduled={"1", "2"}, old_owned_pending=pending,
        claims={3: [{"path": "actor-3.json"}]}, requests={"4": 1},
        qualifications={"6": {"status": "not_qualified"}})
    assert allowed == ["7", "8"]
    assert generation == {"0": {"status": "closed"}}
    assert audit[1]["reason"] == "owned_by_predecessor_unsettled_do_not_replay"
    assert audit[2]["reason"] == "ever_scheduled_by_predecessor_do_not_replay"
    assert audit[3]["reason"] == "physical_identity_consumed_without_imported_generation"
    assert audit[4]["reason"] == "provider_request_consumed_without_imported_generation"
    assert audit[6]["reason"] == "environment_not_qualified"
