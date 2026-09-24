"""Real SQL capability, immutable results and independent admission counterexamples."""

import copy

import pytest

from proworksim.core.world import WorldSpec
from proworksim.domains.executable_project import execute
from proworksim.templates.executable_project import package, sql_project
from proworksim.world_core import WorldCore


def fixture_world(tmp_path):
    world = WorldCore.create(
        tmp_path / "world",
        WorldSpec(
            "executable-tests",
            {"operator": {}, "data_engineer": {}},
            applications=["files", "sql"],
            bootstrap_grants=[
                {"actor_id": "operator", "power": "install_project", "scope": "world"}
            ],
        ),
    )
    assert world.session("operator").call("install_project", package=package("P0"))["ok"]
    worker = world.session("data_engineer", "P0")
    oid = world.state["workspaces"]["P0"]["raw"]
    assert worker.call(
        "adopt", alias="raw", object_id=oid, version_id="v1", policy="fixed", work_ids=["build"]
    )["ok"]
    return world, worker


def build(worker):
    response = worker.call(
        "sql_build",
        work_id="build",
        code_alias="code",
        output_alias="result",
        input_aliases=["raw"],
    )
    assert response["ok"], response
    return response["result"]


def submit_evaluate(world, worker):
    sub = worker.call("submit", work_id="build", artifacts=["code", "result"])
    assert sub["ok"], sub
    return world.evaluate_submission("P0", "build", sub["result"]["submission_id"])


def test_real_build_query_and_submission(tmp_path):
    world, worker = fixture_world(tmp_path)
    result = build(worker)
    assert result["execution_status"] == "success"
    assert len(result["tables"]["customers"]["rows"]) == 100
    query = worker.call(
        "sql_query",
        work_id="build",
        source_alias="result",
        sql="SELECT COUNT(*) AS n FROM orders",
        output_alias="query",
    )
    assert query["result"]["tables"]["query_result"]["rows"] == [[99]]
    assert query["result"]["reference"]["version_id"] == "v2"
    assert submit_evaluate(world, worker)["passed"]


def test_actual_binder_error_is_a_version_then_code_is_repaired(tmp_path):
    world, worker = fixture_world(tmp_path)
    bad = sql_project("P0")
    bad["models"][0]["sql"] = "SELECT no_such_column FROM raw_customers"
    assert worker.call("write_object", alias="code", data=bad, work_id="build")["ok"]
    result = build(worker)
    assert result["execution_status"] == "execution_error"
    assert result["error"]["type"] == "BinderException"
    artifact = world.state["artifacts"][result["reference"]["object_id"]]
    old = world.store.version_path(artifact, result["reference"]["version_id"]).read_bytes()
    assert worker.call("write_object", alias="code", data=sql_project("P0"), work_id="build")["ok"]
    assert build(worker)["execution_status"] == "success"
    assert submit_evaluate(world, worker)["passed"]
    assert world.store.version_path(artifact, result["reference"]["version_id"]).read_bytes() == old


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM '/etc/passwd'",
        "SELECT getenv('DEEPSEEK_API_KEY')",
        "ATTACH '/tmp/foreign.db' AS x",
        "COPY (SELECT 1) TO '/tmp/escaped.csv'",
        "INSTALL httpfs",
        "LOAD httpfs",
        "PRAGMA version",
        "SELECT * FROM read_json_auto('https://example.com/data.json')",
        "SELECT 1; SELECT 2",
        "SELECT * FROM \"read_csv\"('/etc/passwd')",
        "SELECT \"getenv\"('DEEPSEEK_API_KEY')",
    ],
)
def test_sql_cannot_read_host_files_or_mutate_external_world(sql):
    result = execute(tables={}, query=sql)
    assert result["status"] == "execution_error"
    assert not result["tables"]


def test_same_semantics_allows_different_sql_row_order(tmp_path):
    world, worker = fixture_world(tmp_path)
    code = sql_project("P0")
    code["models"][0]["sql"] = (
        "WITH source AS (SELECT * FROM raw_customers) SELECT last_name, id AS customer_id, first_name FROM source ORDER BY id DESC"
    )
    assert worker.call("write_object", alias="code", data=code, work_id="build")["ok"]
    assert build(worker)["execution_status"] == "success"
    assert submit_evaluate(world, worker)["passed"]


def test_wrong_sql_and_forged_green_tests_do_not_pass_independent_check(tmp_path):
    world, worker = fixture_world(tmp_path)
    code = sql_project("P0", tampered_tests=True)
    code["models"][0]["sql"] += " WHERE id <> 1"
    assert worker.call("write_object", alias="code", data=code, work_id="build")["ok"]
    result = build(worker)
    assert result["execution_status"] == "success" and all(t["passed"] for t in result["tests"])
    evaluated = submit_evaluate(world, worker)
    assert not evaluated["passed"] and evaluated["status"] == "content_failure"


def test_rewriting_result_cannot_forge_core_execution_provenance(tmp_path):
    world, worker = fixture_world(tmp_path)
    assert build(worker)["execution_status"] == "success"
    result = worker.call("read_object", alias="result")["result"]["data"]
    assert worker.call("write_object", alias="result", data=copy.deepcopy(result), work_id="build")[
        "ok"
    ]
    evaluated = submit_evaluate(world, worker)
    assert not evaluated["passed"] and evaluated["status"] == "structure_failure"
    assert "actual completed SQL build" in str(evaluated)


def test_sql_requires_exact_adoption_and_owned_declared_output(tmp_path):
    world, worker = fixture_world(tmp_path)
    for changes in [{"output_alias": "raw"}, {"input_aliases": ["missing"]}, {"code_alias": "raw"}]:
        args = {
            "work_id": "build",
            "code_alias": "code",
            "output_alias": "result",
            "input_aliases": ["raw"],
        } | changes
        assert worker.call("sql_build", **args)["ok"] is False
    assert (
        world.session("operator", "P0").call(
            "sql_build",
            work_id="build",
            code_alias="code",
            output_alias="result",
            input_aliases=["raw"],
        )["ok"]
        is False
    )
    assert (
        world.state["artifacts"][world.state["workspaces"]["P0"]["result"]]["current_version"]
        == "v1"
    )
