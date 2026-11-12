"""Zero-call operational reentry controls: tmp SQLite and fake launch only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/activate_passive_pilot_v203_2_1_r2.py"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    old_root, new_root = tmp_path / "old", tmp_path / "new"
    old_api, new_api = old_root / "api", new_root / "api"
    for folder in (old_api, new_api, old_root / "resource-claims"):
        folder.mkdir(parents=True)
    ledger = tmp_path / "cpu-ledger.sqlite"
    calls = {"launch": [], "initialize": [], "retained": []}

    def reference(path):
        path = Path(path).resolve()
        assert path.is_relative_to(tmp_path), "Only CPU temporary sources are authorized"
        raw = path.read_bytes()
        return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True))
        return reference(path)

    def load(ref):
        assert reference(ref["path"]) == ref
        return json.loads(Path(ref["path"]).read_bytes())

    def retain(path, value):
        calls["retained"].append(str(path))
        if path.exists():
            assert json.loads(path.read_bytes()) == value
            return reference(path)
        return write(path, value)

    rows = [{"slot_index": index, "slot_id": f"cpu-slot-{index}"} for index in (2032100, 2032101, 2032102)]
    write(old_root / "plan.json", {"rows": rows})
    write(new_root / "plan.json", {"rows": rows})
    release = write(old_api / "release.json", {"released": True})
    write(old_api / "coordinator-finalization.json", {"cleanup_errors": [], "coordinator_release": release})
    for row in rows[:2]:
        episode = old_root / "episodes" / str(row["slot_index"])
        quiet = write(episode / "quiescence.json", {
            "quiescent": True, "create_result_unknown": False, "retained_objects": [],
            "all_owned_objects_removed": True, "cleanup_errors": [],
        })
        write(episode / "result.json", {"slot_id": row["slot_id"], "model_calls": 0,
            "model_dispatch_started": False, "quiescence": quiet, "status": "technical_unknown"})
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TABLE requests (request_id TEXT PRIMARY KEY,status TEXT NOT NULL)")
        db.execute("CREATE TABLE team_admissions (slot_id TEXT PRIMARY KEY,state TEXT NOT NULL)")
        db.executemany("INSERT INTO team_admissions VALUES (?, 'closed')", [(row["slot_id"],) for row in rows])

    scope = ModuleType("proworksim.software_benchmark_scope_v203_2_1_r2")
    scope.API_ROOT, scope.PLAN_FILE, scope.LEDGER_FILE = new_api, new_root / "plan.json", ledger
    scope.load, scope.retain = load, retain
    scope.require_allowed = lambda value: None if value == "v203.2.1.run" else pytest.fail("unexpected authority")
    scope.dispatch_view = lambda: SimpleNamespace(physical_capacity=lambda: {"passed": True, "cpu_fixture": True})
    old_scope = ModuleType("proworksim.software_benchmark_scope_v203_2_1")
    old_scope.API_ROOT, old_scope.BATCH_ROOT, old_scope.PLAN_FILE = old_api, old_root, old_root / "plan.json"
    host = ModuleType("proworksim.software_benchmark_host_api_v203_2_1_r2")

    def initialize():
        calls["initialize"].append(True)
        return {"REVIEW2": {"known_actual_tokens": 0, "reserved_or_unknown_nanoyuan": 0}}

    host.initialize_ledger = initialize
    candidates = ModuleType("proworksim.software_benchmark_candidates_v054")
    candidates.reference = reference
    package = ModuleType("proworksim")
    package.__path__ = []
    for module in (scope, old_scope, host, candidates):
        setattr(package, module.__name__.split(".")[-1], module)
        monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setitem(sys.modules, "proworksim", package)
    launcher = ModuleType("launch_passive_pilot_v203_2_1_r2")

    def launch():
        calls["launch"].append({"fake": True})
        return {"fake_launch": True, "service_started": False}

    launcher.launch = launch
    monkeypatch.setitem(sys.modules, launcher.__name__, launcher)
    monkeypatch.setattr(sys, "argv", [str(TOOL), "--execute"])
    spec = importlib.util.spec_from_file_location("cpu_only_reentry_activation", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return SimpleNamespace(module=module, ledger=ledger, old=old_root, new=new_root, rows=rows,
                           write=write, load=load, reference=reference, calls=calls)


def snapshot(ledger):
    with sqlite3.connect(ledger) as db:
        names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: db.execute('SELECT * FROM "' + name + '" ORDER BY 1').fetchall() for name in names}


def test_zero_call_closed_admissions_reenter_with_exact_audit_witnesses(setup):
    setup.module.main()
    saved = snapshot(setup.ledger)
    assert saved["requests"] == []
    assert saved["team_admissions"] == [(setup.rows[2]["slot_id"], "closed")]
    assert len(saved["zero_call_reentry_v20321"]) == 2
    for slot, prior, encoded, timestamp in saved["zero_call_reentry_v20321"]:
        witness = json.loads(encoded)
        assert prior == "closed" and timestamp > 0 and witness["slot_id"] == slot
        result = setup.load(witness["result"])
        assert result["slot_id"] == slot and result["model_calls"] == 0
        assert setup.load(witness["quiescence"])["quiescent"]
    assert len(setup.calls["initialize"]) == len(setup.calls["launch"]) == 1


def test_any_existing_request_rejects_without_ledger_or_launch_mutation(setup):
    with sqlite3.connect(setup.ledger) as db:
        db.execute("INSERT INTO requests VALUES ('already-paid','settled')")
    before = snapshot(setup.ledger)
    before_bytes = setup.ledger.read_bytes()
    with pytest.raises(ValueError, match="paid attempt"):
        setup.module.main()
    assert snapshot(setup.ledger) == before and setup.ledger.read_bytes() == before_bytes
    assert not setup.calls["initialize"] and not setup.calls["launch"] and not setup.calls["retained"]


@pytest.mark.parametrize("fault", ["wrong_slot", "invalid_quiet", "cross_slot_quiet"])
def test_wrong_slot_or_unqualified_or_other_slot_quiescence_is_rejected(setup, fault):
    path = setup.old / "episodes/2032100/result.json"
    value = json.loads(path.read_bytes())
    if fault == "wrong_slot":
        value["slot_id"] = "different-slot"
    elif fault == "invalid_quiet":
        quiet = setup.load(value["quiescence"])
        quiet["all_owned_objects_removed"] = False
        value["quiescence"] = setup.write(Path(value["quiescence"]["path"]), quiet)
    else:
        value["quiescence"] = setup.reference(setup.old / "episodes/2032101/quiescence.json")
    setup.write(path, value)
    before = snapshot(setup.ledger)
    with pytest.raises(ValueError):
        setup.module.main()
    assert snapshot(setup.ledger) == before
    assert not setup.calls["initialize"] and not setup.calls["launch"]


def test_unreleased_previous_coordinator_rejects_before_ledger_mutation(setup):
    release = setup.write(setup.old / "api/release.json", {"released": False})
    setup.write(setup.old / "api/coordinator-finalization.json", {"cleanup_errors": [], "coordinator_release": release})
    before = snapshot(setup.ledger)
    with pytest.raises(ValueError, match="not released"):
        setup.module.main()
    assert snapshot(setup.ledger) == before and not setup.calls["launch"]


def test_deleted_admissions_are_idempotent_only_with_identical_reentry_proof(setup):
    setup.module.main()
    first = snapshot(setup.ledger)
    setup.module.main()
    assert snapshot(setup.ledger) == first
    assert len(setup.calls["launch"]) == 2  # Both are fake calls; no execution marker is written.
    path = setup.old / "episodes/2032100/result.json"
    value = json.loads(path.read_bytes())
    setup.write(path, {**value, "different_original_evidence": True})
    with pytest.raises(ValueError, match="identical zero-call"):
        setup.module.main()
    assert snapshot(setup.ledger) == first and len(setup.calls["launch"]) == 2


def test_second_unclosed_admission_rolls_back_first_row_transition(setup):
    with sqlite3.connect(setup.ledger) as db:
        db.execute("UPDATE team_admissions SET state='active' WHERE slot_id=?", (setup.rows[1]["slot_id"],))
    before = snapshot(setup.ledger)
    with pytest.raises(ValueError, match="not closed"):
        setup.module.main()
    assert snapshot(setup.ledger) == before and not setup.calls["launch"]


def test_missing_admission_without_prior_proof_is_not_treated_as_unused(setup):
    with sqlite3.connect(setup.ledger) as db:
        db.execute("DELETE FROM team_admissions WHERE slot_id=?", (setup.rows[0]["slot_id"],))
    before = snapshot(setup.ledger)
    with pytest.raises(ValueError, match="identical zero-call"):
        setup.module.main()
    assert snapshot(setup.ledger) == before and not setup.calls["initialize"] and not setup.calls["launch"]
