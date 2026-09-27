"""Narrow NOT/function-boundary regression via real WorldCore/DuckDB tools."""

import json

from proworksim.domains.executable_project import execute
from scripts.sql_boolean_experiment_v018 import public_controls


def test_equivalent_boolean_queries_and_builds_preserve_nulls_and_sql(tmp_path):
    report = public_controls(tmp_path / "public-controls")
    assert all(
        row["all_four_executions_succeeded"] and row["exact_rows_equal"] and row["null_preserved"]
        for row in report["pairs"]
    )
    expected = {
        "invoice_not_like": [True, False, False, None, True, True, True, True],
        "nested_combined_null": [True, False, False, None, False, None, False, True],
    }
    calls = json.loads((tmp_path / "public-controls/calls.json").read_text())
    for row in report["variants"]:
        assert row["query_rows"] == [
            [i + 1, value] for i, value in enumerate(expected[row["pair"]])
        ]
        for index, filename in [
            (row["query_call_index"], "query.sql"),
            (row["build_call_index"], "models/flags.sql"),
        ]:
            record = calls[index]
            artifact = json.loads(open(record["immutable_result"]["path"]).read())
            assert artifact["files"][filename] == row["sql"]
            assert artifact["execution"]["engine"] == "managed-duckdb-v0.18"
            assert record["response"]["command_committed"] is True
    assert all(
        row["status"] == "execution_error" and row["no_output_tables"]
        for row in report["negative_controls"]
    )
    assert report["external_sentinel_unchanged"] and report["no_external_write"]


def test_boolean_group_does_not_hide_inner_or_quoted_function_calls():
    nested = execute(
        tables={}, query="SELECT NOT (read_csv('/tmp/proworksim-e1-never-read.csv')) AS x"
    )
    quoted = execute(tables={}, query='SELECT "not"(true) AS x')
    assert nested["status"] == quoted["status"] == "execution_error"
    assert "allowlist: read_csv" in nested["error"]["message"]
    assert "Quoted SQL function identifiers" in quoted["error"]["message"]
