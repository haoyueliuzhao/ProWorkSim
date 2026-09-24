"""Bounded real DuckDB execution; no arbitrary shell, files, network or evaluator.

Only supplied public JSON tables enter a fresh database. Managed SQL/config is
projected to actual files in a disposable directory. The returned immutable
logical database, input references and source files are sufficient to rebuild;
no mutable database outside WorldCore survives the call.
"""

import datetime
import decimal
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ENGINE_VERSION = "managed-duckdb-v0.11"
LIMITS = {
    "wall_seconds": 8,
    "cpu_seconds": 4,
    "memory_mb": 128,
    "rows_per_table": 5000,
    "columns": 64,
    "models": 8,
    "tests": 12,
    "sql_characters": 20000,
}
IDENTIFIER = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,62}$")
FUNCTIONS = frozenset(
    {
        "as",
        "join",
        "from",
        "select",
        "where",
        "and",
        "or",
        "on",
        "exists",
        "in",
        "over",
        "filter",
        "cast",
        "try_cast",
        "sum",
        "count",
        "count_if",
        "coalesce",
        "round",
        "min",
        "max",
        "avg",
        "abs",
        "nullif",
        "date_trunc",
        "strftime",
        "year",
        "month",
        "lower",
        "upper",
        "length",
        "trim",
        "row_number",
        "dense_rank",
        "rank",
        "greatest",
        "least",
        "extract",
        "substr",
        "substring",
    }
)
FORBIDDEN = frozenset(
    {
        "attach",
        "detach",
        "copy",
        "install",
        "load",
        "pragma",
        "set",
        "reset",
        "call",
        "export",
        "import",
        "create",
        "alter",
        "drop",
        "insert",
        "update",
        "delete",
        "execute",
        "prepare",
        "vacuum",
    }
)
TYPES = frozenset(
    {
        "INTEGER",
        "BIGINT",
        "HUGEINT",
        "DOUBLE",
        "VARCHAR",
        "BOOLEAN",
        "DATE",
        "TIMESTAMP",
        "DECIMAL(18,2)",
    }
)


def _name(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("Managed SQL identifiers must be simple bounded names")
    return value


def _sql(connection, text):
    if not isinstance(text, str) or not text.strip() or len(text) > LIMITS["sql_characters"]:
        raise ValueError("SQL must be nonempty and within the declared character limit")
    quoted_check = re.sub(r"'(?:''|[^'])*'|--[^\n]*|/\*[\s\S]*?\*/", " ", text)
    if re.search(r'"(?:""|[^"])*"\s*\(', quoted_check):
        raise ValueError("Quoted SQL function identifiers are outside the function allowlist")
    # Remove literals/comments before lexical policy checks; DuckDB independently
    # parses the original SQL and enforces disabled external access.
    tokens = re.sub(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*|/\*[\s\S]*?\*/", " ", text)
    words = {word.lower() for word in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", tokens)}
    if words & FORBIDDEN:
        raise ValueError("SQL capability permits SELECT/CTE only; prohibited keyword")
    calls = {word.lower() for word in re.findall(r"\b([A-Za-z_][A-Za-z_0-9]*)\s*\(", tokens)}
    if calls - FUNCTIONS:
        raise ValueError(
            "SQL function is outside the declared allowlist: " + ",".join(sorted(calls - FUNCTIONS))
        )
    statements = connection.extract_statements(text)
    if len(statements) != 1 or str(statements[0].type) != "StatementType.SELECT":
        raise ValueError("Exactly one SELECT/CTE statement is supported")
    return text.rstrip().rstrip(";")


def _json_value(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite query output is outside the JSON table contract")
    if type(value) not in (str, int, float, bool, type(None)):
        raise ValueError("Only finite scalar SQL columns are supported")
    return value


def _table(connection, query):
    cursor = connection.execute(query)
    if len(cursor.description) > LIMITS["columns"]:
        raise ValueError("Query exceeds column limit")
    columns = [{"name": entry[0], "type": str(entry[1])} for entry in cursor.description]
    if len({c["name"] for c in columns}) != len(columns):
        raise ValueError("Output column names must be unique")
    rows = cursor.fetchmany(LIMITS["rows_per_table"] + 1)
    if len(rows) > LIMITS["rows_per_table"]:
        raise ValueError("Query exceeds row limit; results are not silently truncated")
    return {"columns": columns, "rows": [[_json_value(v) for v in row] for row in rows]}


def _load(connection, tables):
    if not isinstance(tables, dict) or len(tables) > 24:
        raise ValueError("Inputs need at most24 named tables")
    for name, table in tables.items():
        _name(name)
        if not isinstance(table, dict) or set(table) != {"columns", "rows"}:
            raise ValueError("A public table declares columns and rows")
        columns, rows = table["columns"], table["rows"]
        if not isinstance(columns, list) or not 1 <= len(columns) <= LIMITS["columns"]:
            raise ValueError("Invalid source columns")
        if not isinstance(rows, list) or len(rows) > LIMITS["rows_per_table"]:
            raise ValueError("Invalid source row limit")
        for column in columns:
            _name(column["name"])
            if column["type"] not in TYPES:
                raise ValueError("Unsupported finite SQL column type")
        if len({c["name"] for c in columns}) != len(columns):
            raise ValueError("Duplicate source column")
        for row in rows:
            if not isinstance(row, list) or len(row) != len(columns):
                raise ValueError("Malformed source row")
            for value in row:
                _json_value(value)
        definition = ",".join('"' + c["name"] + '" ' + c["type"] for c in columns)
        connection.execute('CREATE TABLE "' + name + '" (' + definition + ")")
        if rows:
            connection.executemany(
                'INSERT INTO "' + name + '" VALUES (' + ",".join("?" for _ in columns) + ")", rows
            )


def _run_child(payload, directory):
    import duckdb
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (LIMITS["cpu_seconds"], LIMITS["cpu_seconds"] + 1))
    config = {
        "enable_external_access": "false",
        "autoload_known_extensions": "false",
        "autoinstall_known_extensions": "false",
        "allow_unsigned_extensions": "false",
        "threads": "1",
        "memory_limit": str(LIMITS["memory_mb"]) + "MB",
        "temp_directory": "",
    }
    connection = duckdb.connect(str(directory / "project.duckdb"), config=config)
    result = {
        "engine": ENGINE_VERSION,
        "duckdb_version": duckdb.__version__,
        "limits": LIMITS,
        "tables": {},
        "tests": [],
        "files": {},
        "status": "success",
    }
    phase = "load_inputs"
    try:
        _load(connection, payload["tables"])
        if payload["mode"] == "query":
            phase = "query"
            sql = _sql(connection, payload["sql"])
            (directory / "query.sql").write_text(sql)
            result["files"]["query.sql"] = sql
            result["tables"]["query_result"] = _table(connection, sql)
        else:
            code = payload["code"]
            if not isinstance(code, dict) or set(code) - {"models", "tests", "config"}:
                raise ValueError("Code declares only models/tests/config")
            models, tests, configuration = (
                code.get("models"),
                code.get("tests", []),
                code.get("config", {}),
            )
            if not isinstance(models, list) or not 1 <= len(models) <= LIMITS["models"]:
                raise ValueError("Code needs one to eight models")
            if not isinstance(tests, list) or len(tests) > LIMITS["tests"]:
                raise ValueError("Invalid tests list")
            if not isinstance(configuration, dict) or set(configuration) - {
                "exports",
                "description",
            }:
                raise ValueError("Only exports/description configuration is supported")
            names = []
            for model in models:
                if not isinstance(model, dict) or set(model) != {"name", "sql"}:
                    raise ValueError("Model requires name and sql")
                name = _name(model["name"])
                phase = "model:" + name
                if name in names or name in payload["tables"]:
                    raise ValueError("Model name duplicates an input or model")
                names.append(name)
                sql = _sql(connection, model["sql"])
                filename = "models/" + name + ".sql"
                (directory / "models").mkdir(exist_ok=True)
                (directory / filename).write_text(sql)
                result["files"][filename] = sql
                connection.execute('CREATE TABLE "' + name + '" AS ' + sql)
                _table(connection, 'SELECT * FROM "' + name + '"')
            exports = configuration.get("exports", names)
            if (
                not isinstance(exports, list)
                or not exports
                or len(exports) != len(set(exports))
                or set(exports) - set(names)
            ):
                raise ValueError("Exports must select actual model names")
            for name in exports:
                result["tables"][name] = _table(connection, 'SELECT * FROM "' + name + '"')
            result["files"]["config.json"] = json.dumps(configuration, sort_keys=True)
            (directory / "config.json").write_text(result["files"]["config.json"])
            test_names = set()
            for test in tests:
                if not isinstance(test, dict) or set(test) != {"name", "sql"}:
                    raise ValueError("Test requires name and SQL returning failing rows")
                name = _name(test["name"])
                phase = "test:" + name
                if name in test_names:
                    raise ValueError("Test names must be unique")
                test_names.add(name)
                sql = _sql(connection, test["sql"])
                filename = "tests/" + name + ".sql"
                (directory / "tests").mkdir(exist_ok=True)
                (directory / filename).write_text(sql)
                result["files"][filename] = sql
                failed = _table(connection, sql)
                result["tests"].append(
                    {"name": name, "passed": not failed["rows"], "failure_rows": failed}
                )
            if any(not t["passed"] for t in result["tests"]):
                result["status"] = "tests_failed"
    except Exception as error:
        result.update(
            status="execution_error",
            error={
                "phase": phase,
                "type": type(error).__name__,
                "message": str(error).replace(str(directory), "$execution"),
            },
        )
    finally:
        connection.close()
    result["database"] = {
        "representation": "managed-logical-tables-v1",
        "derived": True,
        "file_created": (directory / "project.duckdb").exists(),
        "rebuild": "Create a fresh DuckDB from committed exact input tables and committed SQL/config files; no mutable external database is authoritative.",
    }
    return result


def execute(code=None, tables=None, *, query=None):
    """Run fixed subprocess entrypoint; caller data cannot name files or commands."""
    payload = {
        "mode": "query" if query is not None else "build",
        "tables": tables or {},
        "code": code,
        "sql": query,
    }
    content = json.dumps(payload, allow_nan=False)
    if len(content) > 2_000_000:
        raise ValueError("Executable input exceeds2MB JSON limit")
    with tempfile.TemporaryDirectory(prefix="proworksim-sql-") as temp:
        command = [sys.executable, str(Path(__file__).resolve()), temp]
        try:
            process = subprocess.run(
                command,
                input=content,
                text=True,
                capture_output=True,
                cwd=temp,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                timeout=LIMITS["wall_seconds"],
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "engine": ENGINE_VERSION,
                "status": "resource_limit",
                "error": {
                    "type": "TimeoutExpired",
                    "message": "Declared execution wall-clock limit reached",
                },
                "limits": LIMITS,
                "tables": {},
                "tests": [],
                "files": {},
            }
        if process.returncode:
            return {
                "engine": ENGINE_VERSION,
                "status": "executor_error",
                "error": {
                    "type": "ChildProcessExit",
                    "returncode": process.returncode,
                    "stderr": process.stderr[-4000:],
                },
                "limits": LIMITS,
                "tables": {},
                "tests": [],
                "files": {},
            }
        return json.loads(process.stdout)


if __name__ == "__main__":
    print(json.dumps(_run_child(json.load(sys.stdin), Path(sys.argv[1])), allow_nan=False))

# Independent finite business contract. It never imports worker SQL generation.
CHECK_KIND = "executable_sql_project"


def validate_check(check):
    import copy

    result = copy.deepcopy(check)
    if set(result) - {"kind", "path", "sources", "project_kind", "role"} or result.get(
        "project_kind"
    ) not in {"P0", "P1", "P2", "P3"}:
        raise ValueError("Unknown finite executable project contract")
    if result.get("path") != ["tables"]:
        raise ValueError("Executable outputs declare the tables root")
    sources = result.get("sources")
    if not isinstance(sources, list) or not sources or len(sources) > 4:
        raise ValueError("Executable contract needs explicit source bindings")
    for source in sources:
        if (
            not isinstance(source, dict)
            or set(source) != {"alias", "reference_path"}
            or source["reference_path"] != ["sources", source["alias"]]
        ):
            raise ValueError("Executable source reference path must identify its exact alias")
    return result


def _records(table):
    if (
        not isinstance(table, dict)
        or not isinstance(table.get("columns"), list)
        or not isinstance(table.get("rows"), list)
    ):
        raise ValueError("Execution table has invalid structure")
    columns = [column["name"] for column in table["columns"]]
    if len(set(columns)) != len(columns):
        raise ValueError("Duplicate table column")
    rows = []
    for row in table["rows"]:
        if not isinstance(row, list) or len(row) != len(columns):
            raise ValueError("Malformed execution row")
        rows.append(dict(zip(columns, row)))
    return rows


def _canonical(value):
    if isinstance(value, dict):
        return tuple((k, _canonical(v)) for k, v in sorted(value.items()))
    if isinstance(value, list):
        return tuple(_canonical(v) for v in value)
    if type(value) in (int, float):
        return ("number", value)
    return (type(value).__name__, value)


def independent_expected(kind, sources):
    """Finite Python truth, separate from SQL and its editable local tests."""
    if kind == "P0":
        raw = sources["raw"]["tables"]
        return {
            "customers": [
                {"customer_id": r["id"], "first_name": r["first_name"], "last_name": r["last_name"]}
                for r in _records(raw["raw_customers"])
            ],
            "orders": [
                {
                    "order_id": r["id"],
                    "customer_id": r["user_id"],
                    "order_date": r["order_date"],
                    "status": r["status"],
                }
                for r in _records(raw["raw_orders"])
            ],
            "payments": [
                {
                    "payment_id": r["id"],
                    "order_id": r["order_id"],
                    "payment_method": r["payment_method"],
                    "amount_cents": r["amount"],
                }
                for r in _records(raw["raw_payments"])
            ],
        }
    request = _records(sources["request"]["tables"]["interface_request"])
    if len(request) != 1 or request[0]["grain"] not in {"customer", "customer_month"}:
        raise ValueError("Unsupported declared interface grain")
    monthly = request[0]["grain"] == "customer_month"
    if kind == "P1":
        tables = sources["data"]["tables"]
        customers = _records(tables["customers"])
        orders = _records(tables["orders"])
        payments = _records(tables["payments"])
        periods = sorted({r["order_date"][:7] for r in orders}) if monthly else [None]
        money = {}
        for payment in payments:
            money[payment["order_id"]] = money.get(payment["order_id"], 0) + payment["amount_cents"]
        expected = []
        for customer in customers:
            for period in periods:
                selected = [
                    r
                    for r in orders
                    if r["customer_id"] == customer["customer_id"]
                    and r["status"] == "completed"
                    and (not monthly or r["order_date"].startswith(period))
                ]
                row = {
                    "customer_id": customer["customer_id"],
                    "revenue_cents": sum(money.get(r["order_id"], 0) for r in selected),
                    "order_count": len(selected),
                }
                if monthly:
                    row["period"] = period
                expected.append(row)
        return {"metrics": expected}
    if kind == "P2":
        customers = {r["customer_id"]: r for r in _records(sources["data"]["tables"]["customers"])}
        metrics = _records(sources["metrics"]["tables"]["metrics"])
        expected = []
        seen = set()
        for row in metrics:
            if monthly != ("period" in row):
                raise ValueError(
                    "Published metrics do not have the requested customer/period grain"
                )
            key = (row["customer_id"], row.get("period"))
            if key in seen:
                raise ValueError("Published metrics duplicate the customer/period key")
            seen.add(key)
            customer = customers[row["customer_id"]]
            result = {
                "customer_id": row["customer_id"],
                "customer_name": customer["first_name"] + " " + customer["last_name"],
                "revenue_cents": row["revenue_cents"],
                "segment": "active" if row["revenue_cents"] > 0 else "no_completed_revenue",
            }
            if monthly:
                result["period"] = row["period"]
            expected.append(result)
        return {"customer_analysis": expected}
    metric_rows = _records(sources["metrics"]["tables"]["metrics"])
    customer_rows = _records(sources["analysis"]["tables"]["customer_analysis"])
    if any(monthly != ("period" in row) for row in metric_rows + customer_rows):
        raise ValueError("Integration inputs have inconsistent requested grain")
    periods = sorted({r["period"] for r in metric_rows}) if monthly else ["ALL"]
    expected = []
    for period in periods:
        left = [r for r in metric_rows if not monthly or r["period"] == period]
        right = [r for r in customer_rows if not monthly or r["period"] == period]
        a = sum(r["revenue_cents"] for r in left)
        b = sum(r["revenue_cents"] for r in right)
        expected.append(
            {
                "period": period,
                "metrics_cents": a,
                "analysis_cents": b,
                "difference_cents": a - b,
                "customer_rows": len(right),
            }
        )
    return {"integration": expected}


def evaluate_check(spec, data, source):
    from collections import Counter

    sources = {item["alias"]: source(item["alias"]) for item in spec["sources"]}
    try:
        expected = independent_expected(spec["project_kind"], sources)
        if not isinstance(data.get("tables"), dict):
            raise ValueError("Output lacks typed tables")
        actual = {name: _records(table) for name, table in data["tables"].items()}
        matches = set(actual) == set(expected) and all(
            Counter(_canonical(r) for r in actual[name])
            == Counter(_canonical(r) for r in expected[name])
            for name in expected
        )
        return {
            "passed": matches,
            "reason": "independent_source_derived_relational_result"
            if matches
            else "relational_business_result_differs",
            "table_counts": {
                name: {"actual": len(actual.get(name, [])), "expected": len(rows)}
                for name, rows in expected.items()
            },
            "editable_tests_not_used_as_truth": True,
        }
    except (KeyError, TypeError, ValueError) as error:
        return {
            "passed": False,
            "reason": "invalid_executable_product_or_source",
            "diagnostic": str(error),
            "editable_tests_not_used_as_truth": True,
        }


def validate_execution_evidence(state, item, submission, selected, spec):
    """Only core-created result versions certify execution, never JSON labels."""
    results = [
        entry for entry in selected if entry["data"] is not None and "tables" in entry["data"]
    ]
    if len(results) != 1:
        raise ValueError("Exactly one executed result is required")
    result = results[0]
    artifact = result["artifact"]
    vid = submission["artifact_versions"][artifact["artifact_id"]]
    proof = artifact["versions"][vid].get("execution_provenance")
    if (
        not proof
        or proof.get("kind") != "sql_build"
        or proof.get("status") not in {"success", "tests_failed"}
    ):
        raise ValueError("Submitted result lacks an actual completed SQL build")
    if (
        proof != result["data"].get("execution")
        or proof["work_id"] != item["work_item_id"]
        or proof["requirement_version"] != submission["requirement_version"]
    ):
        raise ValueError("SQL execution proof does not match the submitted work edition")
    code = proof["code_reference"]
    if submission["artifact_versions"].get(code["object_id"]) != code["version_id"]:
        raise ValueError("Submit the exact executed SQL code version with its result")
    if proof["source_references"] != result["data"].get("sources"):
        raise ValueError("SQL result source references differ from the actual build")
