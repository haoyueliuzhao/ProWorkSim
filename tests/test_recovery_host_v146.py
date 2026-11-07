"""New-identity host/physical-request attribution using CPU-only transports."""

import copy
import json
import sqlite3
import threading

import pytest

from proworksim import software_benchmark_deepseek_api_v146 as cash
from proworksim import software_benchmark_deepseek_api_v145 as established
from proworksim import software_benchmark_host_api_v146 as host
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_scope_v142 import PANEL_FILE
from proworksim.software_role_baseline_runtime_v141 import prepare_schema_inventory
from proworksim.storage import digest, json_bytes


def fixture(tmp_path, monkeypatch):
    originals = [
        r
        for r in json.loads(PANEL_FILE.read_text())["rows"]
        if r["organization_id"] in host.GROUP_IDS
    ][:21]
    rows = []
    for round_id in (1, 2):
        for i, old in enumerate(originals):
            rows.append(
                {
                    **old,
                    "original_slot_id": old["slot_id"],
                    "recovery_round": round_id,
                    "recovery_attempt": round_id,
                    "slot_id": f"v146:{old['slot_id']}:attempt{round_id}",
                    "slot_index": 10200 + i + (round_id - 1) * 21,
                }
            )
    plan = tmp_path / "panel.json"
    plan.write_text(json.dumps({"rows": rows}))
    prior = tmp_path / "prior.sqlite"
    with sqlite3.connect(prior) as db:
        db.execute("CREATE TABLE metadata(name TEXT PRIMARY KEY,value TEXT)")
        db.execute(
            "INSERT INTO metadata VALUES(?,?)",
            ("policy", json.dumps({"version": "v142-test", "cap_nanoyuan": 400 * 10**9})),
        )
        db.execute(
            "CREATE TABLE requests(status TEXT,reserved_nanoyuan INTEGER,settled_nanoyuan INTEGER)"
        )
        db.execute("INSERT INTO requests VALUES('settled',0,350813651800)")
    amend = tmp_path / "amend.json"
    amend.write_text(
        json.dumps(
            {
                "prior_total_cap_CNY": "400.00",
                "amended_total_cap_CNY": "450.00",
                "additional_CNY": "50.00",
                "authorization_kind": "derived_summary_of_current_user_instruction",
                "does_not_release_prior_uncertain_reservations": True,
            }
        )
    )
    ledger = tmp_path / "recovery.sqlite"
    authority = tmp_path / "authority.json"
    authority.write_text(
        json.dumps(
            {
                **cash.amended_prior_cash_snapshot(prior, reference(amend)),
                "child_ledger_path": str(ledger.resolve()),
            }
        )
    )
    views = {
        g: cash.group_api(
            g,
            ledger,
            max_concurrency=2,
            panel_ref=reference(plan),
            cash_authority_ref=reference(authority),
        )
        for g in host.GROUP_IDS
    }
    monkeypatch.setattr(host, "api_for", lambda g: views[g])
    monkeypatch.setattr(host.scope, "LEDGER_FILES", {g: ledger for g in host.GROUP_IDS})
    monkeypatch.setattr(host.scope, "MAX_GENERATIONS", 2)
    guards = []
    monkeypatch.setattr(host.scope, "require_allowed", lambda op, **kw: guards.append((op, kw)))
    runtime = host.DeepSeekRuntime()
    runtime.rows = {r["slot_id"]: r for r in rows}
    runtime.apis = views
    runtime.schemas = {
        g: v for g, v in prepare_schema_inventory()["schemas"].items() if g in host.GROUP_IDS
    }
    runtime.counter = lambda w: {"prompt_tokens": 10, "request_sha256": digest(json_bytes(w))}
    runtime.success_root = tmp_path / "success"
    runtime.http_slots = threading.BoundedSemaphore(2)
    return runtime, rows, views, ledger, prior, authority, guards


def response():
    return {
        "id": "synthetic-response",
        "model": "deepseek-flash",
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "CPU"}}],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 3,
            "total_tokens": 13,
            "prompt_cache_hit_tokens": 4,
            "prompt_cache_miss_tokens": 6,
        },
    }


class Script:
    def __init__(self, steps):
        self.steps = iter(steps)
        self.calls = []

    def request(self, *args):
        self.calls.append(copy.deepcopy(args))
        value = next(self.steps)
        if isinstance(value, Exception):
            raise value
        return value


def transient():
    return established.TransportFailure(
        "complete_http_error_response", phase="complete_http_response", status=503
    )


def install(runtime, views, row, script):
    group = row["organization_id"]
    view = views[group]
    names = {x["function"]["name"] for t in runtime.schemas[group].values() for x in t}
    client = view.DeepSeekClient(
        api_key="CPU-only",
        allowed_tool_names=names,
        transport=script,
        http_slots=runtime.http_slots,
        sleep=lambda _: None,
        jitter=lambda: 0,
    )
    client.fork_for_episode = lambda: client
    runtime.clients[group] = client
    wire = {
        "model": "deepseek-flash",
        "messages": [{"role": "user", "content": "CPU"}],
        "stream": False,
        "thinking": {"type": "disabled"},
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": 20,
        "tool_choice": "auto",
        "tools": runtime.schemas[group]["member_001"],
        "user_id": view.slot_user_id(row["slot_id"] + ":member_001", row["condition_id"]),
    }
    payload = {
        "wire": wire,
        "member_id": "member_001",
        "team_slot_id": row["slot_id"],
        "slot_id": row["slot_id"],
        "condition": row["condition_id"],
        "usage_id": "agent",
        "prompt_upper_bound": 10,
        "request_id": row["slot_id"] + ":member_001:0001",
    }
    return client, payload


def test_actual_new_host_recovers_http_and_reports_physical_unknown_without_requeue(
    tmp_path, monkeypatch
):
    runtime, rows, views, ledger, prior, authority, guards = fixture(tmp_path, monkeypatch)
    row = rows[0]
    script = Script([transient(), response()])
    client, payload = install(runtime, views, row, script)
    route = runtime.transport_factory(row, tmp_path / "route")
    # Fake only waiting; actual client/ledger/host schemas and attribution run.
    monkeypatch.setattr(route.cancelled, "wait", lambda _: False)
    assert route.post("/chat/completions", payload) == response()
    measured = runtime.usage_for_slot(row)
    assert measured["known_actual_tokens"] == 13 and measured["unknown_tokens_upper"] == 30
    assert measured["physical_http_attempt_count"] == 2 and measured["logical_request_count"] == 1
    assert measured["unresolved_calls"][0]["recovered_by_later_settled_attempt"]
    assert not measured["usage_capture_complete"]
    queued = runtime.recovery_queue_record(row)
    assert (
        queued["classification"] == "billing_unknown_after_transport_recovery"
        and not queued["retry_eligible"]
    )
    assert runtime.for_group(row["organization_id"]).settled_route_witnesses() == {
        "PROJECT": row["slot_id"]
    }
    assert guards == [
        ("v146.api.request", {"slot_id": row["slot_id"], "instance_id": row["instance_id"]})
    ]
    assert len(list(runtime.success_root.glob("*.json"))) == 1
    assert views[row["organization_id"]].CAP_NANOYUAN == 99186348200
    with sqlite3.connect(prior) as db:
        assert (
            json.loads(db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0])[
                "cap_nanoyuan"
            ]
            == 400 * 10**9
        )


def test_exhausted_transient_is_queued_but_cash_boundary_disables_retry(tmp_path, monkeypatch):
    runtime, rows, views, *_ = fixture(tmp_path, monkeypatch)
    row = rows[0]
    script = Script([transient(), transient(), transient()])
    client, payload = install(runtime, views, row, script)
    route = runtime.transport_factory(row, tmp_path / "route")
    monkeypatch.setattr(route.cancelled, "wait", lambda _: False)
    with pytest.raises(established.TransportFailure):
        route.post("/chat/completions", payload)
    queued = runtime.recovery_queue_record(row)
    assert queued["classification"] == "exhausted_transient_http" and queued["retry_eligible"]
    monkeypatch.setattr(host, "budget_status", lambda _: {"state": "cash_exhausted"})
    queued = runtime.recovery_queue_record(row)
    assert queued["classification"] == "cash_boundary" and not queued["retry_eligible"]


def test_new_authority_cannot_add_a_second_50_increment(tmp_path, monkeypatch):
    runtime, rows, views, ledger, prior, authority, _ = fixture(tmp_path, monkeypatch)
    forged = json.loads(authority.read_text())
    forged["available_nanoyuan"] += 50 * 10**9
    fake = tmp_path / "fake-authority.json"
    fake.write_text(json.dumps(forged))
    with pytest.raises(ValueError, match="committed cash"):
        cash.group_api(
            "FREE2",
            ledger,
            max_concurrency=2,
            panel_ref=views["FREE2"].POLICY["panel"],
            cash_authority_ref=reference(fake),
        )
    assert not ledger.exists()


def test_same_cash_snapshot_is_shared_by_both_groups(tmp_path, monkeypatch):
    runtime, rows, views, ledger, *_ = fixture(tmp_path, monkeypatch)
    views["FREE2"].BudgetLedger()
    a, b = host.budget_status("FREE2"), host.budget_status("REVIEW2")
    assert a["remaining_CNY"] == b["remaining_CNY"] == "99.1863482"
    assert a["ledger_path"] == b["ledger_path"] == str(ledger)
    assert a["original_total_cap_CNY"] == "450"
