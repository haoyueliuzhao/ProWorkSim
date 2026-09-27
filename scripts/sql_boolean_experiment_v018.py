"""Real public WorldCore boolean SQL controls and optional isolated H1 replay.

Run with PYTHONPATH pointing at the declared old/new source. Output must be new;
this script never writes a historical run, calculates a business reward, edits
an original SQL expression, or invokes any model.
"""

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path

from proworksim.core.world import WorldSpec
from proworksim.domains import executable_project as engine
from proworksim.world_core import WorldCore

PAIRS = [
    {
        "name": "invoice_not_like",
        "negated": "NOT (LOWER(TRIM(InvoiceNo)) LIKE 'c%')",
        "equivalent": "LOWER(TRIM(InvoiceNo)) NOT LIKE 'c%'",
    },
    {
        "name": "nested_combined_null",
        "negated": "(NOT ((LOWER(TRIM(InvoiceNo)) LIKE 'c%') OR (Quantity <= 0))) AND (UnitPrice > 0 OR UnitPrice IS NULL)",
        "equivalent": "((LOWER(TRIM(InvoiceNo)) NOT LIKE 'c%') AND (Quantity > 0)) AND (UnitPrice > 0 OR UnitPrice IS NULL)",
    },
]
TABLES = {
    "invoices": {
        "columns": [
            {"name": "id", "type": "BIGINT"},
            {"name": "InvoiceNo", "type": "VARCHAR"},
            {"name": "Quantity", "type": "BIGINT"},
            {"name": "UnitPrice", "type": "DECIMAL(18,2)"},
        ],
        "rows": [
            [1, " 100 ", 1, "2.00"],
            [2, "C200", -1, "2.00"],
            [3, " c300 ", 2, None],
            [4, None, 1, "1.00"],
            [5, "", 0, "1.00"],
            [6, "400", None, "1.00"],
            [7, "500", 2, "0.00"],
            [8, "600", 2, None],
        ],
    }
}


def ref(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def create_world(path):
    world = WorldCore.create(
        path,
        WorldSpec(
            "bounded-boolean-e1",
            {"operator": {}, "worker": {}},
            applications=["files", "sql"],
            bootstrap_grants=[
                {"actor_id": "operator", "power": "install_project", "scope": "world"}
            ],
        ),
    )
    package = {
        "project_id": "E1",
        "goal": "Observe declared boolean SQL semantics over synthetic bounded rows",
        "participants": ["operator", "worker"],
        "objects": [
            {
                "alias": alias,
                "filename": alias + ".json",
                "kind": "json",
                "owner": "worker",
                "readers": ["worker", "operator"],
                "data": data,
            }
            for alias, data in [
                ("input", {"tables": copy.deepcopy(TABLES)}),
                ("code", {"models": [{"name": "flags", "sql": "SELECT id FROM invoices"}]}),
                ("result", {}),
                ("query", {}),
            ]
        ],
        "works": [
            {
                "work_id": "check",
                "owner": "worker",
                "goal": "Execute literal SQL without rewriting it",
                "deliverables": ["result"],
                "requirements": {
                    "input_policy": "fixed",
                    "input_version": "v1",
                    "sql_project": {
                        "code_alias": "code",
                        "result_alias": "result",
                        "query_alias": "query",
                    },
                },
            }
        ],
        "grants": [
            {"actor_id": "worker", "power": power, "subject": "artifact", "work_nodes": ["check"]}
            for power in ("adopt", "execute_sql")
        ],
    }
    installed = world.session("operator").call("install_project", package=package)
    assert installed["ok"], installed
    worker = world.session("worker", "E1")
    adopted = worker.call(
        "adopt",
        alias="input",
        object_id=world.state["workspaces"]["E1"]["input"],
        version_id="v1",
        policy="fixed",
        work_ids=["check"],
    )
    assert adopted["ok"], adopted
    return world, worker


def public_controls(output, *, negative=True):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    world, worker = create_world(output / "world")
    calls = []

    def call(action, **arguments):
        response = worker.call(action, **arguments)
        assert response["ok"], response  # A world command may succeed while bounded SQL fails.
        result = response["result"]
        evidence = None
        if isinstance(result, dict) and result.get("reference"):
            reference = result["reference"]
            artifact = world.state["artifacts"][reference["object_id"]]
            path = world.store.version_path(artifact, reference["version_id"])
            evidence = {**ref(path), "reference": reference}
        row = {
            "action": action,
            "arguments": arguments,
            "response": response,
            "immutable_result": evidence,
        }
        calls.append(row)
        return result, len(calls) - 1

    rows = []
    for pair in PAIRS:
        for variant in ("negated", "equivalent"):
            sql = "SELECT id, " + pair[variant] + " AS admitted FROM invoices ORDER BY id"
            # Query and build receive exactly the same SQL. The world only adds
            # the declared CREATE TABLE wrapper for model materialization.
            query, qi = call(
                "sql_query", work_id="check", source_alias="input", sql=sql, output_alias="query"
            )
            call(
                "write_object",
                alias="code",
                work_id="check",
                data={
                    "models": [{"name": "flags", "sql": sql}],
                    "tests": [],
                    "config": {"exports": ["flags"]},
                },
            )
            build, bi = call(
                "sql_build",
                work_id="check",
                code_alias="code",
                output_alias="result",
                input_aliases=["input"],
            )
            rows.append(
                {
                    "pair": pair["name"],
                    "variant": variant,
                    "sql": sql,
                    "query_call_index": qi,
                    "build_call_index": bi,
                    "query_status": query["execution_status"],
                    "build_status": build["execution_status"],
                    "query_rows": query.get("tables", {}).get("query_result", {}).get("rows"),
                    "build_rows": build.get("tables", {}).get("flags", {}).get("rows"),
                    "query_error": query.get("error"),
                    "build_error": build.get("error"),
                }
            )
    comparisons = []
    for pair in PAIRS:
        a, b = [row for row in rows if row["pair"] == pair["name"]]
        succeeded = all(
            row[k] == "success" for row in (a, b) for k in ("query_status", "build_status")
        )
        comparisons.append(
            {
                "pair": pair["name"],
                "all_four_executions_succeeded": succeeded,
                "exact_rows_equal": a["query_rows"]
                == b["query_rows"]
                == a["build_rows"]
                == b["build_rows"]
                if succeeded
                else None,
                "null_preserved": any(v is None for _, v in a["query_rows"]) if succeeded else None,
            }
        )
    negatives = []
    sentinel = output / "external-sentinel.csv"
    sentinel.write_text("private_sentinel\n123\n")
    initial_sentinel = ref(sentinel)
    escaped = output / "escaped.csv"
    if negative:
        statements = [
            ("external_file", "SELECT * FROM '" + str(sentinel.resolve()) + "'"),
            ("external_function", "SELECT * FROM read_csv('" + str(sentinel.resolve()) + "')"),
            ("extension", "LOAD httpfs"),
            ("write", "COPY (SELECT 1 AS x) TO '" + str(escaped.resolve()) + "'"),
            ("multiple_statements", "SELECT 1 AS x; SELECT 2 AS x"),
            ("unsupported_function", "SELECT regexp_matches(InvoiceNo, 'x') AS x FROM invoices"),
            ("character_limit", "SELECT 1 AS x " + " " * engine.LIMITS["sql_characters"]),
        ]
        for label, sql in statements:
            result, index = call(
                "sql_query", work_id="check", source_alias="input", sql=sql, output_alias="query"
            )
            negatives.append(
                {
                    "name": label,
                    "call_index": index,
                    "status": result["execution_status"],
                    "error": result.get("error"),
                    "no_output_tables": not result.get("tables"),
                }
            )
    write(output / "calls.json", calls)
    report = {
        "version": "sql-boolean-public-controls-v0.18",
        "engine": engine.ENGINE_VERSION,
        "duckdb": importlib.metadata.version("duckdb"),
        "limits": engine.LIMITS,
        "pairs": comparisons,
        "variants": rows,
        "negative_controls": negatives,
        "external_sentinel_unchanged": ref(sentinel) == initial_sentinel,
        "no_external_write": not escaped.exists(),
        "calls": ref(output / "calls.json"),
        "world_state": ref(output / "world/control/state.json"),
        "scope": "Real WorldCore session.call -> bounded DuckDB subprocess -> immutable result; synthetic rows, no model or business evaluator.",
    }
    write(output / "report.json", report)
    return report


def replay_h1(folder, output):
    """Replay exact immutable code/typed inputs, without invoking any work actor."""
    folder, output = Path(folder).resolve(), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    experience = json.loads((folder / "episode/experience.json").read_text())
    state = json.loads((folder / "world/control/state.json").read_text())
    old = next(
        e
        for e in experience["events"]
        if e["kind"] == "tool_call"
        and e["payload"].get("action") == "sql_build"
        and "allowlist: not" in str(e["payload"].get("response", {}).get("result", {}).get("error"))
    )
    reference = old["payload"]["response"]["result"]["reference"]
    originals = [ref(folder / "episode/experience.json"), ref(folder / "world/control/state.json")]

    def version(reference):
        artifact = state["artifacts"][reference["object_id"]]
        path = (
            folder
            / "world/control/versions"
            / reference["object_id"]
            / reference["version_id"]
            / artifact["filename"]
        )
        identity = ref(path)
        assert identity["sha256"] == artifact["versions"][reference["version_id"]]["sha256"]
        originals.append(identity)
        return json.loads(path.read_text())

    original_result = version(reference)
    code = version(original_result["execution"]["code_reference"])
    tables = {}
    for source in original_result["execution"]["source_references"].values():
        data = version(source)
        assert not set(tables) & set(data["tables"])
        tables.update(data["tables"])
    write(output / "original-input.json", {"code": code, "tables": tables})
    result = engine.execute(code=copy.deepcopy(code), tables=copy.deepcopy(tables))
    write(output / "replay-result.json", result)
    for original in originals:
        assert ref(original["path"]) == original
    report = {
        "version": "original-h1-sql-local-diagnostic-v0.18",
        "source_slot": str(folder),
        "original_action_sequence": old["sequence"],
        "original_execution_status": original_result["status"],
        "original_error": original_result.get("error"),
        "original_artifacts": originals,
        "new_engine": engine.ENGINE_VERSION,
        "replay_status": result["status"],
        "replay_error": result.get("error"),
        "exact_sql_and_inputs": ref(output / "original-input.json"),
        "replay_result": ref(output / "replay-result.json"),
        "original_files_unchanged": True,
        "SQL_rewritten": False,
        "business_correctness": "not_evaluated",
        "original_reward_changed": False,
        "scope": "Independent isolated DuckDB diagnostic only; not a model turn, WorldCore episode replay, replacement sample, restored success, or training data.",
    }
    write(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--replay-h1", action="append", type=Path, default=[])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = Path(engine.__file__).resolve()
    (args.output / "engine-source.py").write_bytes(source.read_bytes())
    report = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "label": args.label,
        "engine_source": ref(source),
        "engine_snapshot": ref(args.output / "engine-source.py"),
        "experiment_script": ref(__file__),
        "controls": public_controls(args.output / "public-world"),
        "original_h1_replays": [
            replay_h1(path, args.output / f"h1-replay-{index}")
            for index, path in enumerate(args.replay_h1)
        ],
    }
    write(args.output / "report.json", report)
    print(
        json.dumps(
            {
                "label": args.label,
                "engine": engine.ENGINE_VERSION,
                "comparisons": report["controls"]["pairs"],
                "replays": [r["replay_status"] for r in report["original_h1_replays"]],
            }
        )
    )


if __name__ == "__main__":
    main()
