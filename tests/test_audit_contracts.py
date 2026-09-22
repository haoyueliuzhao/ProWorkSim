import copy
import io
import json
import urllib.error

import pytest

from proworksim.contracts import citation_contract
from proworksim.runtime import DeepSeekBackend, run_model
from proworksim.validation import evaluate
from test_learning_runtime import FixtureBackend, candidate, short_answer
from test_world import call, prepare


@pytest.mark.parametrize("field", ["values.revenue", "values.operating_margin"])
def test_public_any_of_and_grader_accept_both_citations(world_factory, field):
    world = world_factory()
    prepare(world)
    session = world.session()
    memo = json.loads(call(session, "read_file", artifact_id="memo")["content"])
    memo["citations"] = [{"artifact_id": "financials", "version_id": "v2", "location": field}]
    call(session, "write_file", artifact_id="memo", content=json.dumps(memo))
    call(session, "submit", work_item_id="work-1")
    call(session, "wait")
    assert evaluate(world.store.root, "work-1")[0]["passed"]
    guide = json.loads(call(session, "read_file", artifact_id="guide")["content"])
    assert ["financials", field] in guide["citation_requirements"]["memo"]["required_any_of"]


@pytest.mark.parametrize(
    "citation",
    [
        {"artifact_id": "financials", "version_id": "v1", "location": "values.revenue"},
        {"artifact_id": "unapproved", "version_id": "v2", "location": "values.revenue"},
        {"artifact_id": "financials", "version_id": "v2", "location": "values.missing"},
        {"artifact_id": "model", "version_id": "v2", "location": "Outputs!B6"},
    ],
)
def test_invalid_citation_variants_remain_rejected(citation):
    assert not citation_contract("memo").validate([citation], {"financials": "v2", "model": "v2"})


@pytest.mark.parametrize(
    "dependencies,freshness",
    [
        ([], "unknown"),
        (
            [
                {"artifact_id": "model", "version_id": "v1"},
                {"artifact_id": "financials", "version_id": "v1"},
            ],
            "stale",
        ),
    ],
)
def test_body_and_metadata_disagreement_is_not_valid(world_factory, dependencies, freshness):
    world = world_factory()
    prepare(world)
    session = world.session()
    memo = call(session, "read_file", artifact_id="memo")["content"]
    call(session, "write_file", artifact_id="memo", content=memo, dependencies=dependencies)
    assert world.store.load()["artifacts"]["memo"]["freshness"] == freshness
    call(session, "submit", work_item_id="work-1")
    call(session, "wait")
    result = evaluate(world.store.root, "work-1")[0]
    assert not result["artifact_valid"]
    assert "memo_required_dependencies" in [c["name"] for c in result["checks"] if not c["passed"]]
    assert result["business_accepted"]  # a separate, intentionally narrower check


@pytest.mark.parametrize(
    "formula,expected",
    [
        ("=2/50%", 4),
        ("=2/(50%)", 4),
        ("=10%^2", 0.01),
        ("=(10%)^2", 0.01),
        ("=2^3%", 2**0.03),
        ("=-2^2", 4),
        ("=-(2^2)", -4),
        ("=2^3^2", 64),
        ("=200%%", 0.02),
        ("=ROUND(-2.5,0)", -3),
        ("=SUM(1,2*3)/50%", 14),
    ],
)
def test_formula_precedence_against_fixed_numeric_oracles(world_factory, formula, expected):
    world = world_factory("file")
    session = world.session()
    call(session, "sheet_update", cells={"Probe!A1": formula})
    result = call(session, "sheet_read", sheet="Probe")["sheets"]["Probe"]["A1"]["value"]
    assert result == pytest.approx(expected)
    artifact = world.store.load()["artifacts"]["model"]
    from openpyxl import load_workbook

    assert load_workbook(io.BytesIO(world.store.content(artifact)), data_only=True)["Probe"][
        "A1"
    ].value == pytest.approx(expected)


def test_tool_ids_can_repeat_across_logical_model_calls(world_factory):
    world = world_factory("short")
    answer = short_answer(world)
    backend = FixtureBackend(
        [
            [candidate("repeat", "calculate", {"expression": "2+2"})],
            [candidate("repeat", "submit", {"work_item_id": "work-1", "answer": answer})],
            [candidate("repeat", "wait", {"ticks": 2})],
        ]
    )
    assert run_model(world, backend, 3)["complete"]
    calls = world.store.load()["calls"]
    assert all(len(c["action_ids"]) == 1 for c in calls)
    assert len({c["action_ids"][0] for c in calls}) == 3


def test_failed_http_attempts_are_recorded_separately(world_factory, monkeypatch):
    import proworksim.runtime as runtime

    world = world_factory("short")
    attempts = []
    backend = DeepSeekBackend(api_key="unit-test-credential")
    backend.attempt_sink = lambda row: attempts.append(copy.deepcopy(row))
    count = 0

    def request(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            raise urllib.error.HTTPError("https://unit.invalid", 429, "retry", {}, None)
        raise TimeoutError("unit timeout")

    monkeypatch.setattr(runtime.urllib.request, "urlopen", request)
    monkeypatch.setattr(runtime.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError):
        run_model(world, backend, 1)
    state = world.store.load()
    assert len(state["calls"]) == 1
    logical_call = state["calls"][0]
    assert logical_call["status"] == "failed"
    assert [a["status"] for a in logical_call["attempts"]] == ["http_error", "timeout", "timeout"]
    assert all(a["usage"] is None for a in logical_call["attempts"])
    assert "unit-test-credential" not in json.dumps(state)
