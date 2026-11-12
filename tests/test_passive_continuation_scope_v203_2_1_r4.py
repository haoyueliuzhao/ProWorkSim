"""CPU-only identity, closed predecessor, source-recovery and shared-ledger guards."""

import copy
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_scope_v203_2_1_r4 as scope
from proworksim import software_benchmark_episode_v203_2_1_r4 as episode
from proworksim import software_benchmark_host_api_v203_2_1_r4 as host
from proworksim import software_benchmark_alignment_contract_v203_2_1 as alignment
from proworksim.software_benchmark_candidates_v054 import reference


def test_exact_ten_identity_and_same_runtime_cash():
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    previous = scope.parent.load(reference(scope.parent.PLAN_FILE))
    assert [r["slot_id"] for r in plan["rows"]] == [r["slot_id"] for r in previous["rows"][2:]]
    assert host.api_for is host.initial_host.api_for
    assert scope.LEDGER_FILE == scope.parent.LEDGER_FILE
    value = episode.build_episode(
        scope=scope,
        guard=lambda *a, **k: {
            "status": "approved",
            "execution_alignment_version": alignment.VERSION,
            "source_index": {"CPU_only": True},
            "plan": reference(scope.PLAN_FILE),
        },
    )
    assert value._run.__globals__["runtime"].OUTPUT.name == "sdk-bundle-r2"
    assert value.allowed_organization_ids == alignment.GROUP_IDS
    assert value.actual_role_limits == {
        "actor": [4, 16 * 1024**3, 512],
        "controller": [2, 32 * 1024**3, 256],
    }
    bad = copy.deepcopy(plan)
    bad["rows"][0]["seed"] += 1
    with pytest.raises((PermissionError, ValueError)):
        scope.validate_plan(bad)


@pytest.fixture
def gate_fixture(tmp_path, monkeypatch):
    data = {}

    def ref(path):
        return {"path": str(Path(path)), "sha256": "a" * 64, "bytes": 1}

    def put(path, value):
        data[str(path)] = value
        return ref(path)

    monkeypatch.setattr(scope, "reference", ref)
    monkeypatch.setattr(scope, "load", lambda r: data[r["path"]])
    monkeypatch.setattr(scope, "checked", lambda r: Path(r["path"]))
    monkeypatch.setattr(scope, "_closed_predecessors", lambda: {})
    parent = SimpleNamespace(
        BATCH_ROOT=tmp_path / "parent",
        API_ROOT=tmp_path / "parent/api",
        PLAN_FILE=tmp_path / "parent/plan",
        load=lambda r: data[r["path"]],
    )
    monkeypatch.setattr(scope, "parent", parent)
    monkeypatch.setattr(scope, "ROOT", tmp_path)
    monkeypatch.setattr(scope, "REVALIDATION_FILE", tmp_path / "recovered/gate.json")
    dbpath = tmp_path / "ledger.sqlite"
    monkeypatch.setattr(scope, "LEDGER_FILE", dbpath)
    con = sqlite3.connect(dbpath)
    con.execute(
        "CREATE TABLE requests(request_id TEXT,slot_id TEXT,status TEXT,member_id TEXT,usage_id TEXT,usage_json TEXT,settled_nanoyuan INTEGER)"
    )
    rows = []
    results = []
    usages = []
    measurements = []
    oldmeasurements = []
    host_usage = []
    for i in (2032200, 2032201):
        slot = f"original-{i}"
        row = {
            "slot_index": i,
            "slot_id": slot,
            "instance_id": f"task-{i}",
            "configuration": ref(tmp_path / f"config-{i}"),
        }
        rows.append(row)
        quiet = put(
            tmp_path / f"quiet-{i}",
            {
                "quiescent": True,
                "all_owned_objects_removed": True,
                "cleanup_errors": [],
                "create_result_unknown": False,
            },
        )
        blob = ref(tmp_path / f"archive-{i}.tar.zst")
        transfer = put(
            tmp_path / f"transfer-{i}",
            {
                "transfer": {"stream_sha256": "b" * 64, "bytes": 20},
                "archive_storage": {
                    "blob": blob,
                    "decompressed_sha256": "b" * 64,
                    "decompressed_bytes": 20,
                },
            },
        )
        results.append(
            put(
                parent.BATCH_ROOT / "episodes" / str(i) / "result.json",
                {
                    "status": "closed",
                    "slot_id": slot,
                    "instance_id": row["instance_id"],
                    "configuration": row["configuration"],
                    "quiescence": quiet,
                    "controller_output_transfer": transfer,
                },
            )
        )
        raw = {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "prompt_cache_hit_tokens": 0,
            "prompt_cache_miss_tokens": 10,
        }
        call = {
            "call_id": f"call-{i}",
            "member_id": "member_001",
            "purpose": "agent",
            "accounted_cost_cny": "0.001",
            **raw,
        }
        con.execute(
            "INSERT INTO requests VALUES(?,?,?,?,?,?,?)",
            (call["call_id"], slot, "settled", "member_001", "agent", json.dumps(raw), 1000000),
        )
        usages.append(
            put(
                parent.API_ROOT / "usage-records" / f"{i}.json",
                {
                    "row": row,
                    "calls": [call],
                    "usage_capture_complete": True,
                    "unresolved_calls": [],
                },
            )
        )
        host_usage.append(
            {
                "slot_id": slot,
                "complete": True,
                "called": True,
                "unresolved_requests": 0,
                "record": usages[-1],
            }
        )
        oldmeasurements.append(
            put(
                tmp_path / f"old-measurement-{i}",
                {"integrity": {"required_dimensions": ["requests", "responses"]}},
            )
        )
        measurements.append(
            put(
                scope.REVALIDATION_FILE.parent / f"{i}-measurement.json",
                {
                    "schema": "passive-capture-analysis-v203.2.1-r4",
                    "episode_id": slot,
                    "execution_state": "CLOSED",
                    "new_model_requests": 0,
                    "integrity": {
                        "status": "COMPLETE",
                        "fatal_errors": [],
                        "required_dimensions": ["requests", "responses"],
                    },
                    "accepted_requests": [{"physical_id": call["call_id"]}],
                    "source_files": {
                        transfer["path"]: {k: transfer[k] for k in ("sha256", "bytes")},
                        blob["path"]: {
                            "sha256": blob["sha256"],
                            "bytes": 1,
                            "full_decompressed_stream_verified": True,
                            "decompressed_sha256": "b" * 64,
                            "decompressed_bytes": 20,
                        },
                        blob["path"] + "#output/managed-runtime/experience.jsonl": {
                            "sha256": "c" * 64,
                            "bytes": 5,
                            "source_kind": "original_archive_member",
                            "extracted_to_controller": False,
                        },
                    },
                },
            )
        )
    con.commit()
    con.close()
    put(parent.PLAN_FILE, {"rows": rows})
    oldgate = put(
        parent.API_ROOT / "engineering-gate.json",
        {
            "passed": False,
            "predeclared_indices": [2032200, 2032201],
            "scores_used_for_gate": False,
            "shared_host_usage_complete": True,
            "measurements": oldmeasurements,
            "host_usage": host_usage,
        },
    )
    value = {
        "version": "v203.2.1-first-two-archive-revalidation-gate-r4",
        "passed": True,
        "predeclared_indices": [2032200, 2032201],
        "scores_used_for_gate": False,
        "new_model_calls": 0,
        "original_gate": oldgate,
        "measurements": measurements,
        "generation_results": results,
        "usage_records": usages,
        "parser_source": ref(tmp_path / "tools/analyze_passive_capture_v203_2_1_r4.py"),
        "thresholds_changed": False,
        "original_model_attempts_replayed": False,
    }
    return value, data, dbpath


def test_complete_recovery_gate_and_cache(gate_fixture, monkeypatch):
    value, data, _ = gate_fixture
    assert scope.validate_revalidation(value) is value
    data[str(scope.REVALIDATION_FILE)] = value
    calls = []
    original = scope.validate_revalidation
    monkeypatch.setattr(scope, "validate_revalidation", lambda v: calls.append(1) or original(v))
    scope._validated_gate_once.cache_clear()
    assert scope.require_continuation_gate()["passed"]
    assert scope.require_continuation_gate()["passed"]
    assert calls == [1]
    scope._validated_gate_once.cache_clear()


@pytest.mark.parametrize(
    "defect", ["archive", "usage", "identity", "requirements", "unsettled", "capture"]
)
def test_revalidation_rejects_incomplete_original_evidence(gate_fixture, defect):
    value, data, dbpath = gate_fixture
    report = data[value["measurements"][0]["path"]]
    if defect == "archive":
        next(v for k, v in report["source_files"].items() if k.endswith(".tar.zst"))[
            "full_decompressed_stream_verified"
        ] = False
    elif defect == "usage":
        data[value["usage_records"][0]["path"]]["unresolved_calls"] = [{"call_id": "unknown"}]
    elif defect == "identity":
        report["episode_id"] = "different-task"
    elif defect == "requirements":
        report["integrity"]["required_dimensions"] = []
    elif defect == "capture":
        report["accepted_requests"] = []
    else:
        with sqlite3.connect(dbpath) as con:
            con.execute("UPDATE requests SET status='reserved'")
    with pytest.raises(PermissionError):
        scope.validate_revalidation(value)


def test_initial_ten_admission_allows_other_paid_but_rejects_own_consumption(tmp_path, monkeypatch):
    dbpath = tmp_path / "ledger.sqlite"
    with sqlite3.connect(dbpath) as db:
        db.execute("CREATE TABLE requests(slot_id TEXT)")
        db.execute("CREATE TABLE team_admissions(slot_id TEXT,state TEXT)")
        db.execute("INSERT INTO requests VALUES('first-two-paid')")
    rows = [{"slot_id": f"remaining-{i}"} for i in range(10)]
    monkeypatch.setattr(scope, "LEDGER_FILE", dbpath)
    monkeypatch.setattr(scope, "require_continuation_gate", lambda: {"passed": True})
    monkeypatch.setattr(scope, "validate_plan", lambda p: {"rows": rows})
    monkeypatch.setattr(scope, "never_consumed", lambda row: True)
    assert scope.validate_first_model_admission()["existing_first_two_requests"] == 1
    with sqlite3.connect(dbpath) as db:
        db.execute("INSERT INTO team_admissions VALUES('remaining-7','started')")
    with pytest.raises(PermissionError):
        scope.validate_first_model_admission()
    with sqlite3.connect(dbpath) as db:
        db.execute("DELETE FROM team_admissions")
        db.execute("INSERT INTO requests VALUES('remaining-7')")
    with pytest.raises(PermissionError):
        scope.validate_first_model_admission()


def test_closed_predecessors_require_release_and_no_active_claim(tmp_path, monkeypatch):
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return reference(path)

    predecessors = []
    for name in ("parent", "leaf"):
        root = tmp_path / name
        previous = SimpleNamespace(
            BATCH_ROOT=root,
            API_ROOT=root / "api",
            API_UNIT=name,
            CLAIM_FILE=root / "api/claim.json",
        )
        claim = write(previous.CLAIM_FILE, {"owner": name})
        released = write(
            previous.API_ROOT / "coordinator-capacity-released.json",
            {"released": True, "claim": claim},
        )
        write(
            previous.API_ROOT / "coordinator-finalization.json",
            {"cleanup_errors": [], "coordinator_release": released},
        )
        predecessors.append(previous)
    monkeypatch.setattr(scope, "parent", predecessors[0])
    monkeypatch.setattr(scope, "leaf", predecessors[1])
    write(predecessors[0].API_ROOT / "progress.json", {"phase": "closed"})
    write(
        predecessors[1].API_ROOT / "held-before-model.json",
        {"status": "not_started_held", "model_calls": 0},
    )
    assert set(scope._closed_predecessors()) == {"parent", "leaf"}
    write(predecessors[1].BATCH_ROOT / "resource-claims/active-worker.json", {"owner": "leaf"})
    with pytest.raises(PermissionError, match="terminal state"):
        scope._closed_predecessors()
