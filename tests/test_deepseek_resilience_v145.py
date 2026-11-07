"""No network/containers: real new ledger, direct parser and managed host path."""

import copy
import hashlib
import json
import sqlite3
import threading
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_deepseek_api_v145 as api
from proworksim import software_benchmark_host_api_v145 as host
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_scope_v142 import PANEL_FILE
from proworksim.software_role_baseline_runtime_v141 import prepare_schema_inventory
from proworksim.storage import digest, json_bytes


def setup(tmp_path, *, remaining=10, group="FREE2", concurrency=2):
    prior = tmp_path / "old.sqlite"
    with sqlite3.connect(prior) as db:
        db.execute("CREATE TABLE metadata(name TEXT PRIMARY KEY,value TEXT)")
        db.execute(
            "INSERT INTO metadata VALUES(?,?)",
            ("policy", json.dumps({"version": "v142-test", "cap_nanoyuan": 400 * 10**9})),
        )
        db.execute(
            "CREATE TABLE requests(status TEXT,reserved_nanoyuan INTEGER,settled_nanoyuan INTEGER)"
        )
        db.execute(
            "INSERT INTO requests VALUES(?,?,?)",
            ("settled", 0, int(round((400 - remaining) * 10**9))),
        )
    authority = tmp_path / "authority.json"
    authority.write_text(
        json.dumps(
            {
                **api.prior_cash_snapshot(prior),
                "child_ledger_path": str((tmp_path / "new.sqlite").resolve()),
            }
        )
    )
    view = api.group_api(
        group,
        tmp_path / "new.sqlite",
        max_concurrency=concurrency,
        panel_ref=reference(PANEL_FILE),
        cash_authority_ref=reference(authority),
    )
    row = next(
        r for r in json.loads(PANEL_FILE.read_text())["rows"] if r["organization_id"] == group
    )
    member = "member_001"
    wire = {
        "model": "deepseek-flash",
        "messages": [{"role": "user", "content": "Synthetic CPU"}],
        "stream": False,
        "thinking": {"type": "disabled"},
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": 20,
        "tool_choice": "none",
        "user_id": view.slot_user_id(row["slot_id"] + ":" + member, row["condition_id"]),
    }
    kw = {
        "request_id": row["slot_id"] + ":" + member + ":0001",
        "slot_id": row["slot_id"],
        "member_id": member,
        "condition": row["condition_id"],
        "usage_id": "condenser",
        "prompt_upper_bound": 10,
    }
    return view, row, wire, kw, prior


def body(name="response-1"):
    return {
        "id": name,
        "model": "deepseek-flash",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "CPU"},
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 3,
            "total_tokens": 13,
            "prompt_cache_hit_tokens": 4,
            "prompt_cache_miss_tokens": 6,
        },
    }


class Script:
    def __init__(self, items):
        self.items = iter(items)
        self.calls = []

    def request(self, *args):
        self.calls.append(copy.deepcopy(args))
        value = next(self.items)
        if isinstance(value, Exception):
            raise value
        return value


def failure(status=503):
    return api.TransportFailure(
        "complete_http_error_response",
        phase="complete_http_response",
        status=status,
        body=b'{"error":{"code":"overloaded","message":"secret ignored"}}',
    )


def test_retry_keeps_exact_request_reserves_each_and_releases_permit(tmp_path):
    view, _, wire, kw, _ = setup(tmp_path)
    slots = threading.BoundedSemaphore(1)
    script = Script([failure(), body()])
    waits = []

    def wait(seconds):
        assert slots.acquire(blocking=False)
        slots.release()
        waits.append(seconds)

    client = view.DeepSeekClient(
        api_key="synthetic",
        allowed_tool_names=set(),
        transport=script,
        http_slots=slots,
        sleep=wait,
        jitter=lambda: 0,
    )
    assert client.complete(wire, **kw)["id"] == "response-1"
    assert script.calls[0] == script.calls[1] and waits == [2]
    with client.ledger.transaction() as db:
        records = [dict(r) for r in db.execute("SELECT * FROM requests ORDER BY attempt_index")]
    assert [r["status"] for r in records] == ["http_error_uncertain", "settled"]
    snap = client.ledger.snapshot()
    assert snap["known_actual_tokens"] == 13 and snap["unknown_tokens_upper"] == 30
    assert not snap["actual_usage_complete"] and snap["reserved_or_unknown_nanoyuan"] == 180000
    assert json.loads(records[0]["evidence_json"])["provider_error_code"] == "overloaded"
    assert "secret ignored" not in records[0]["evidence_json"]
    with pytest.raises(api.PreDispatchBudgetStopped):
        client.complete(wire, **kw)
    assert len(script.calls) == 2


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("secret"),
        ValueError("secret"),
        failure(400),
        api.TransportFailure("response_json_decode", phase="json_decode", status=200),
    ],
)
def test_unknown_or_nontransient_does_not_replay(tmp_path, error):
    view, _, wire, kw, _ = setup(tmp_path)
    script = Script([error, body()])
    client = view.DeepSeekClient(api_key="synthetic", allowed_tool_names=set(), transport=script)
    with pytest.raises(Exception):
        client.complete(wire, **kw)
    assert len(script.calls) == 1
    with client.ledger.transaction() as db:
        record = dict(db.execute("SELECT * FROM requests").fetchone())
    assert record["status"] == "unknown" and record["settled_nanoyuan"] is None
    assert "secret" not in record["evidence_json"]


def test_three_attempt_cap_and_all_costs_preserved(tmp_path):
    view, _, wire, kw, _ = setup(tmp_path)
    script = Script([failure(), failure(), failure(), body()])
    client = view.DeepSeekClient(
        api_key="synthetic",
        allowed_tool_names=set(),
        transport=script,
        sleep=lambda _: None,
        jitter=lambda: 0,
    )
    with pytest.raises(api.TransportFailure):
        client.complete(wire, **kw)
    assert len(script.calls) == 3 and client.ledger.snapshot()["unknown_tokens_upper"] == 90


def test_budget_and_team_token_upper_gate_before_retry(tmp_path, monkeypatch):
    view, _, wire, kw, _ = setup(tmp_path)
    monkeypatch.setattr(api, "TEAM_TOKEN_LIMIT", 45)
    script = Script([failure(), body()])
    client = view.DeepSeekClient(
        api_key="synthetic", allowed_tool_names=set(), transport=script, sleep=lambda _: None
    )
    with pytest.raises(api.APIUncertainFailure, match="shared_team") as failure_info:
        client.complete(wire, **kw)
    assert getattr(failure_info.value, "before_dispatch_proven", False) is False
    assert len(script.calls) == 1


def test_unknown_cash_reservation_prevents_retry_exceeding_remaining_cash(tmp_path):
    view, _, wire, kw, _ = setup(tmp_path, remaining=0.0002)
    script = Script([failure(), body()])
    client = view.DeepSeekClient(
        api_key="synthetic", allowed_tool_names=set(), transport=script, sleep=lambda _: None
    )
    with pytest.raises(api.APIUncertainFailure, match="remaining_cash"):
        client.complete(wire, **kw)
    assert len(script.calls) == 1
    assert client.ledger.snapshot()["remaining_nanoyuan"] == 20000


def test_settlement_failure_preserves_structural_validation_reason(tmp_path):
    view, _, wire, kw, _ = setup(tmp_path)
    response = body()
    response["usage"]["total_tokens"] = 100
    script = Script([response, body("second-must-not-be-called")])
    client = view.DeepSeekClient(api_key="synthetic", allowed_tool_names=set(), transport=script)
    with pytest.raises(api.TransportFailure) as info:
        client.complete(wire, **kw)
    assert info.value.evidence["detail"]["validation_code"] == "usage_partitions_disagree"
    assert len(script.calls) == 1
    with client.ledger.transaction() as db:
        record = dict(db.execute("SELECT * FROM requests").fetchone())
    assert record["status"] == "unknown"
    assert json.loads(record["evidence_json"])["phase"] == "settlement"


def test_prior_cash_changes_block_before_dispatch(tmp_path):
    view, _, wire, kw, prior = setup(tmp_path)
    script = Script([body()])
    client = view.DeepSeekClient(api_key="synthetic", allowed_tool_names=set(), transport=script)
    with sqlite3.connect(prior) as db:
        db.execute("INSERT INTO requests VALUES('uncertain',1000,NULL)")
    with pytest.raises(api.PreDispatchBudgetStopped, match="historical_cash"):
        client.complete(wire, **kw)
    assert not script.calls


def test_new_cap_is_only_old_remaining_and_old_database_refused(tmp_path):
    view, _, _, _, prior = setup(tmp_path, remaining=2)
    assert view.CAP_NANOYUAN == 2 * 10**9
    with pytest.raises(ValueError):
        view.BudgetLedger(prior)


def test_rolling_breaker_survives_success(tmp_path):
    view, _, wire, kw, _ = setup(tmp_path)
    ledger = view.BudgetLedger()
    with ledger.transaction() as db:
        for i in range(3):
            db.execute("INSERT INTO breaker_events VALUES(?,?,1)", (str(i), api.time.time()))
    assert ledger.breaker_wait() > 29
    attempt = ledger.reserve(
        logical_id=kw["request_id"],
        attempt_index=1,
        slot_id=kw["slot_id"],
        member_id=kw["member_id"],
        condition=kw["condition"],
        usage_id=kw["usage_id"],
        request_sha256=api.sha(wire),
        prompt_upper_bound=10,
        max_output_tokens=20,
    )
    ledger.settle(attempt, body())
    assert ledger.breaker_wait() > 29


@pytest.mark.parametrize(
    "raw,status,expected",
    [
        (b"\r\n\n " + json.dumps(body()).encode(), 200, None),
        (b"not-json", 200, "response_json_decode"),
        (b"[]", 200, "response_not_json_object"),
        (b'{"error":{"code":"overloaded"}}', 503, "complete_http_error_response"),
    ],
)
def test_direct_parser_errors_and_blank_keepalive(monkeypatch, raw, status, expected):
    class Response:
        def __init__(self):
            self.status = status
            self.parts = iter([raw, b""])

        def read1(self, _):
            return next(self.parts)

        def getheader(self, key):
            return "4"

    class Connection:
        def __init__(self, *a, **k):
            self.sock = SimpleNamespace(settimeout=lambda *_: None)

        def connect(self):
            pass

        def request(self, *a, **k):
            assert k["headers"]["Authorization"] == "Bearer synthetic"

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(api.http.client, "HTTPSConnection", Connection)
    direct = api.DirectHTTPS("synthetic")
    if expected:
        with pytest.raises(api.TransportFailure) as info:
            direct.request("POST", "/chat/completions", {})
        assert info.value.evidence["error_code"] == expected and info.value.http_status == status
        assert info.value.evidence["response_sha256"] == hashlib.sha256(raw).hexdigest()
    else:
        assert direct.request("POST", "/chat/completions", {}) == body()


def test_actual_managed_host_schema_member_and_count_binding(tmp_path):
    view, row, wire, kw, _ = setup(tmp_path)
    schemas = prepare_schema_inventory()["schemas"]
    slots = threading.BoundedSemaphore(1)
    script = Script([failure(), body()])
    client = view.DeepSeekClient(
        api_key="synthetic",
        allowed_tool_names={
            t["function"]["name"] for tools in schemas["FREE2"].values() for t in tools
        },
        transport=script,
        http_slots=slots,
        sleep=lambda _: None,
        jitter=lambda: 0,
    )
    client.fork_for_episode = lambda: client
    guards = []
    runtime = SimpleNamespace(
        apis={"FREE2": view},
        clients={"FREE2": client},
        schemas=schemas,
        http_slots=slots,
        counter=lambda w: {"prompt_tokens": 10, "request_sha256": digest(json_bytes(w))},
        authorize=lambda op, **identity: guards.append((op, identity)),
    )
    route = host.HostTeamTransport(runtime, row, tmp_path / "route")
    wire.update(tools=schemas["FREE2"]["member_001"], tool_choice="auto")
    kw["usage_id"] = "agent"
    payload = {"wire": wire, "team_slot_id": row["slot_id"], **kw}
    assert (
        route.post("/tokenize", {k: payload[k] for k in ["wire", "member_id", "team_slot_id"]})[
            "prompt_tokens"
        ]
        == 10
    )
    assert route.post("/chat/completions", payload) == body()
    assert len(script.calls) == 2 and guards == [
        ("v145.api.request", {"slot_id": row["slot_id"], "instance_id": row["instance_id"]})
    ]
    altered = copy.deepcopy(payload)
    altered["wire"]["tools"][0]["function"]["description"] += " altered"
    with pytest.raises(ValueError, match="schema"):
        route.post("/chat/completions", altered)
    assert len(script.calls) == 2


def test_authority_rejects_another_group_ledger_path_before_creation(tmp_path):
    view, _, _, _, _ = setup(tmp_path)
    wrong = tmp_path / "duplicate-remaining.sqlite"
    with pytest.raises(ValueError, match="one exact child ledger"):
        api.group_api(
            "REVIEW2",
            wrong,
            max_concurrency=2,
            panel_ref=reference(PANEL_FILE),
            cash_authority_ref=view.POLICY["cash_authority"],
        )
    assert not wrong.exists()


def test_host_rejects_group_ledger_or_authority_disagreement_before_clients(tmp_path):
    view, _, _, _, _ = setup(tmp_path)
    bad_policy = {**view.POLICY, "child_ledger_path": str(tmp_path / "duplicate.sqlite")}
    bad = SimpleNamespace(
        POLICY=bad_policy,
        group_id="REVIEW2",
        DeepSeekClient=lambda **_: pytest.fail("No client should be created"),
    )
    with pytest.raises(ValueError, match="one exact ledger"):
        host.runtime_for(
            apis={"FREE2": view, "REVIEW2": bad},
            schemas={},
            counter=None,
            authorize=None,
            api_key="synthetic",
            max_concurrency=2,
        )


@pytest.mark.parametrize("chunked", [False, True])
def test_truncated_503_is_unknown_and_never_retryable(monkeypatch, chunked):
    class Response:
        status = 503
        length = 10 if not chunked else None
        chunk_left = 4 if chunked else None

        def __init__(self):
            self.chunked = chunked
            self.calls = 0

        def read1(self, _):
            self.calls += 1
            if self.calls == 1:
                return b"partial"
            if chunked:
                raise api.http.client.IncompleteRead(b"partial", 4)
            return b""

        def getheader(self, _):
            return None

    class Connection:
        def __init__(self, *a, **k):
            self.sock = SimpleNamespace(settimeout=lambda *_: None)

        def connect(self):
            pass

        def request(self, *a, **k):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(api.http.client, "HTTPSConnection", Connection)
    with pytest.raises(api.TransportFailure) as info:
        api.DirectHTTPS("synthetic").request("POST", "/chat/completions", {})
    assert not info.value.retryable and info.value.http_status == 503
    assert info.value.evidence["error_code"] in {"incomplete_response_body", "transport_exception"}


def test_deadline_expiring_during_immediate_permit_acquisition_sends_nothing(tmp_path, monkeypatch):
    view, _, wire, kw, _ = setup(tmp_path)
    tick = [0.0]

    class Slots:
        released = False

        def acquire(self, **_):
            tick[0] = 2.0
            return True

        def release(self):
            self.released = True

    slots = Slots()
    monkeypatch.setattr(api.time, "monotonic", lambda: tick[0])
    script = Script([body()])
    client = view.DeepSeekClient(
        api_key="synthetic",
        allowed_tool_names=set(),
        transport=script,
        timeout_seconds=1,
        http_slots=slots,
    )
    with pytest.raises(api.PreDispatchConcurrencyBusy, match="deadline"):
        client.complete(wire, **kw)
    assert not script.calls and slots.released
    with client.ledger.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM requests").fetchone()[0] == 0


def test_unknown_finish_reason_settles_usage_without_returning_or_retrying_body(tmp_path):
    view, _, wire, kw, _ = setup(tmp_path)
    response = body()
    response["choices"][0]["finish_reason"] = "unexpected-provider-reason"
    script = Script([response, body("not-called")])
    client = view.DeepSeekClient(api_key="synthetic", allowed_tool_names=set(), transport=script)
    with pytest.raises(
        api.old.ProviderOutputBoundViolation, match="provider_generation_interrupted"
    ):
        client.complete(wire, **kw)
    assert len(script.calls) == 1
    snap = client.ledger.snapshot()
    assert snap["known_actual_tokens"] == 13 and snap["actual_usage_complete"]
