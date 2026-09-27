"""Bounded SQLite-source P0 admission; host witnesses are never model experience."""

from collections import Counter
import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import unicodedata

from .storage import digest, json_bytes, read_json

VERSION = "sqlite-source-admission-v0.20"
PINS = {
    "six": {"repository": "birdsql/six-gym-sqlite", "revision": "d603cc8af5294bb75415b8137d362080dab01bfd",
            "file": "train.jsonl", "sha256": "7df6797d4b093fd9a34a24569a521f56d29b80dcfacdf567ee41b61dbd30e92c"},
    "critic": {"repository": "birdsql/bird-critic-1.0-sqlite", "revision": "af2b1c3e2f8b3480e5569212198761c770df06d0",
               "file": "sqlite-00000-of-00001.jsonl", "sha256": "4abb18afbc7c1f8e9c566d04707ebbdc8508247924ced01b927ef716393fd468"},
}
DB_PATH = "six/database/book_publishing_company/book_publishing_company_template.sqlite"
DB_SHA = "b493a54214d7b224a6f2b9b22b0f651c98f0c345a91cdec10b94825d4d897f4d"
CASES = ("TRAIN_86", "TRAIN_210", "TRAIN_303")
PROJECTION = {"authors": {"au_id": "VARCHAR", "au_fname": "VARCHAR", "au_lname": "VARCHAR"},
              "titleauthor": {"au_id": "VARCHAR", "title_id": "VARCHAR"},
              "titles": {"title_id": "VARCHAR", "type": "VARCHAR", "price": "DOUBLE"}}
# Host-authored feasibility programs, not actor prompts or training targets.
WITNESSES = {
    "TRAIN_86": "SELECT a.au_id, a.au_fname, a.au_lname FROM authors a WHERE NOT EXISTS (SELECT 1 FROM titleauthor t WHERE t.au_id=a.au_id AND t.title_id='BU1032')",
    "TRAIN_210": "SELECT a.au_id, a.au_fname, a.au_lname, t.type FROM authors a JOIN titleauthor x ON a.au_id=x.au_id JOIN titles t ON t.title_id=x.title_id WHERE t.type='business' AND t.price>15.0",
    "TRAIN_303": "SELECT type, COUNT(*) AS title_count FROM titles GROUP BY type",
}
WRONG_VALID = {
    "TRAIN_86": "SELECT au_id, au_fname, au_lname FROM authors WHERE 1=0",
    "TRAIN_210": "SELECT a.au_id, a.au_fname, a.au_lname, t.type FROM authors a JOIN titleauthor x ON a.au_id=x.au_id JOIN titles t ON t.title_id=x.title_id WHERE t.type='business' AND t.price>1000.0",
    "TRAIN_303": "SELECT type, COUNT(*)+1 AS title_count FROM titles GROUP BY type",
}
NATIVE_LIMITS = {"wall_seconds": 8, "cpu_seconds": 4, "address_space_mb": 512,
                 "vm_operations": 500000, "rows": 5000, "sql_characters": 20000}


def reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}


def _verified(path, expected):
    raw = Path(path).read_bytes()
    if digest(raw) != expected:
        raise ValueError("Pinned source bytes changed: " + str(path))
    return raw


def read_sources(assets):
    assets = Path(assets)
    data = {}
    for name, pin in PINS.items():
        declaration = read_json(assets / name / "source.json")
        if declaration["repository"] != pin["repository"] or declaration["revision"] != pin["revision"]:
            raise ValueError("Source repository/revision differs")
        for entry in declaration["files"]:
            _verified(assets / name / Path(entry["path"]).name, entry["sha256"])
        data[name] = [json.loads(line) for line in _verified(assets / name / pin["file"], pin["sha256"]).splitlines() if line.strip()]
    return data


def _normalized(value):
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


def lineage(assets):
    assets = Path(assets)
    data = read_sources(assets)
    databases, published_hashes = {}, {}
    for name in PINS:
        tree = read_json(assets / name / "tree.json")
        files = [f for f in tree if f["type"] == "file" and f["path"].endswith(".sqlite")]
        databases[name] = {f["path"].split("/")[1] for f in files}
        published_hashes[name] = {f["lfs"]["oid"] for f in files}
        if databases[name] != {r["db_id"] for r in data[name]}:
            raise ValueError("Task/database inventory mismatch")
    def fingerprints(rows, keys):
        return {_normalized([r[k] for k in keys]) for r in rows}
    overlap = {"database_ids": sorted(databases["six"] & databases["critic"]),
               "published_sqlite_sha256": sorted(published_hashes["six"] & published_hashes["critic"])}
    for label, keys in [("query", ["query"]), ("issue_sql", ["issue_sql"]), ("query_and_issue", ["query", "issue_sql"])]:
        overlap[label + "_normalized_exact_matches"] = len(fingerprints(data["six"], keys) & fingerprints(data["critic"], keys))
    groups = {}
    for row in data["six"]:
        groups.setdefault(_normalized([row["query"], row["issue_sql"]]), []).append(row)
    overlap["query_and_issue_pairs"] = [
        {"six": {"instance_id": s["instance_id"], "db_id": s["db_id"]},
         "critic": {"instance_id": c["instance_id"], "db_id": c["db_id"]},
         "normalized_pair_sha256": digest(_normalized([c["query"], c["issue_sql"]]).encode())}
        for c in data["critic"] for s in groups.get(_normalized([c["query"], c["issue_sql"]]), [])
    ]
    return {"version": VERSION, "sources": {n: {**p, "task_count": len(data[n]),
               "database_ids": sorted(databases[n]), "fields": sorted(set().union(*(r.keys() for r in data[n]))),
               "categories": dict(Counter(r.get("category") for r in data[n])),
               "task_file_ref": reference(assets / n / p["file"]),
               "inventory_ref": reference(assets / n / "tree.json"), "card_ref": reference(assets / n / "card.md")}
               for n, p in PINS.items()}, "overlap": overlap,
            "upstream_family": "BIRD/SWE-SQL: official Six card explicitly calls Six the BIRD-Critic-SQLite training split",
            "limits": "Published database IDs/hashes and normalized exact task text only. Original user-issue IDs and semantic near-duplicate lineage are not supplied; no proof of independent underlying issues or template families.",
            "usage": {"six_book_database_and_all_derivatives": "interface_development_only",
                      "remaining_six": "unassigned_pending_database_and_template_usage_partition",
                      "critic": "external_individual_SQL_control_candidate; public metadata inspected for lineage, full official solutions/tests unavailable; not admitted for scored evaluation"},
            "upstream_split_is_project_usage": False,
            "official_python_tests_executed": False, "model_calls": 0, "training_examples": 0}


def task(assets, instance_id):
    if instance_id not in CASES:
        raise ValueError("Only the three predeclared development cases are admitted")
    row = next(r for r in read_sources(assets)["six"] if r["instance_id"] == instance_id)
    if (row["db_id"] != "book_publishing_company" or row["preprocess_sql"] or row["clean_up_sql"]
            or len(row["issue_sql"]) != 1 or len(row["sol_sql"]) != 1 or row["category"] != "Query"):
        raise ValueError("Case exceeds this source-initialization/SELECT-only boundary")
    return row


def public_task(row):
    return {key: copy.deepcopy(row[key]) for key in ("instance_id", "db_id", "dialect", "version", "category", "query", "issue_sql")}


def independent_expected(instance_id, tables):
    """Read projected source facts, never reference SQL, hidden tests or results."""
    records = {name: [dict(zip([c["name"] for c in t["columns"]], row)) for row in t["rows"]] for name, t in tables.items()}
    if instance_id == "TRAIN_86":
        excluded = {r["au_id"] for r in records["titleauthor"] if r["title_id"] == "BU1032"}
        return [[a[k] for k in ("au_id", "au_fname", "au_lname")] for a in records["authors"] if a["au_id"] not in excluded]
    if instance_id == "TRAIN_210":
        titles = {r["title_id"]: r for r in records["titles"]}
        authors = {r["au_id"]: r for r in records["authors"]}
        answer = []
        for link in records["titleauthor"]:
            title, author = titles.get(link["title_id"]), authors.get(link["au_id"])
            if title and author and title["type"] == "business" and title["price"] is not None and title["price"] > 15.0:
                answer.append([author["au_id"], author["au_fname"], author["au_lname"], title["type"]])
        return answer
    if instance_id == "TRAIN_303":
        return [[k, v] for k, v in Counter(t["type"] for t in records["titles"]).items()]
    raise ValueError("No undeclared oracle")


def rows_equal(left, right):
    return Counter(json_bytes(row) for row in left) == Counter(json_bytes(row) for row in right)


def _sqlite_child(payload):
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (4, 5))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    path = Path(payload["database"]).resolve()
    _verified(path, DB_SHA)
    source = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    source.enable_load_extension(False)
    source.execute("PRAGMA trusted_schema=OFF")
    connection = sqlite3.connect(":memory:")
    source.backup(connection)
    source.close()
    connection.enable_load_extension(False)
    connection.execute("PRAGMA trusted_schema=OFF")
    connection.execute("PRAGMA query_only=ON")
    steps = [0]
    def progress():
        steps[0] += 1000
        return int(steps[0] > NATIVE_LIMITS["vm_operations"])
    connection.set_progress_handler(progress, 1000)
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    def authorize(action, arg1, arg2, database, trigger):
        if action not in allowed or (action == sqlite3.SQLITE_READ and database not in (None, "main")):
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION and str(arg2).casefold() not in {"count", "min", "max", "sum", "avg", "round"}:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    connection.set_authorizer(authorize)
    tables = {}
    for name, columns in PROJECTION.items():
        query = 'SELECT ' + ','.join('"' + c + '"' for c in columns) + ' FROM "' + name + '"'
        rows = connection.execute(query).fetchmany(NATIVE_LIMITS["rows"] + 1)
        if len(rows) > NATIVE_LIMITS["rows"]:
            raise ValueError("Source projection exceeds managed row boundary")
        tables[name] = {"columns": [{"name": n, "type": t} for n, t in columns.items()], "rows": rows}
    results = {}
    for label, query in payload["queries"].items():
        steps[0] = 0
        try:
            if not isinstance(query, str) or len(query) > NATIVE_LIMITS["sql_characters"]:
                raise ValueError("Query exceeds boundary")
            cursor = connection.execute(query)
            rows = cursor.fetchmany(NATIVE_LIMITS["rows"] + 1)
            if len(rows) > NATIVE_LIMITS["rows"]:
                raise ValueError("Result exceeds row boundary")
            results[label] = {"status": "success", "columns": [c[0] for c in cursor.description], "rows": rows}
        except (sqlite3.Error, ValueError) as error:
            results[label] = {"status": "rejected_or_error", "error_type": type(error).__name__, "message": str(error)}
    connection.close()
    return {"sqlite_version": sqlite3.sqlite_version, "initialization": "Verified immutable original DB copied to fresh in-memory SQLite; admitted cases require empty preprocess/cleanup.",
            "tables": tables, "queries": results, "limits": NATIVE_LIMITS}


def native_control(assets, row):
    path = Path(assets) / DB_PATH
    _verified(path, DB_SHA)
    queries = {"original_issue": row["issue_sql"][0], "private_reference": row["sol_sql"][0],
               "host_witness": WITNESSES[row["instance_id"]], "wrong_valid": WRONG_VALID[row["instance_id"]],
               "write_negative": "DELETE FROM authors", "attach_negative": "ATTACH DATABASE '/etc/passwd' AS other",
               "extension_negative": "SELECT load_extension('/tmp/absent')"}
    process = subprocess.run([sys.executable, "-m", "proworksim.sql_source_v020", "--sqlite-child"],
        input=json.dumps({"database": str(path.resolve()), "queries": queries}), text=True,
        capture_output=True, timeout=NATIVE_LIMITS["wall_seconds"],
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
    if process.returncode:
        raise ValueError({"native_child_failed": process.returncode, "stderr": process.stderr[-2000:]})
    return json.loads(process.stdout)


def build_world(row, tables, root):
    from .scenarios import build_scenario
    from .templates.decision_team import package, scenario_spec
    from .core.world import object_identity

    pkg, spec = package(), scenario_spec()
    pkg["objects"] = [o for o in pkg["objects"] if o["alias"] in {"data", "code", "result", "query"}]
    for obj in pkg["objects"]:
        obj["readers"] = ["implementer", "operator"]
        if obj["alias"] == "data":
            obj["data"] = {"tables": tables, "source": {"family": "bird-swe-sql", "dataset": PINS["six"]["repository"],
                          "revision": PINS["six"]["revision"], "database_sha256": DB_SHA,
                          "usage": "interface_development", "projection": "All rows of declared columns; not a complete database clone or official evaluator."}}
        elif obj["alias"] == "code":
            obj["data"] = {"models": [{"name": "repair", "sql": row["issue_sql"][0]}], "tests": [], "config": {"exports": ["repair"]}}
    pkg["participants"] = ["implementer", "operator"]
    pkg["information_routes"] = []
    pkg["grants"] = [g for g in pkg["grants"] if g["actor_id"] == "implementer" and g["power"] in {"adopt", "execute_sql"}]
    work = pkg["works"][0]
    pkg["goal"] = work["goal"] = row["query"]
    work["approval_policy"] = "delivery_only"
    work["visible_requirements"] = ["Repair the public SQL against the exact adopted source. P0 is an interface feasibility control; no model or training score is supplied."]
    work["requirements"] = {"input_policies": {"data": "fixed"}, "input_versions": {"data": "v1"},
                            "source_objects": {"data": object_identity("TEAM", "data")},
                            "sql_project": {"kind": "p0_source_repair", "code_alias": "code", "result_alias": "result", "query_alias": "query"},
                            "public_source_task": public_task(row)}
    work["deliverable_contract"]["content_checks"] = []
    pkg["provenance"] = {"kind": "reconstructed", "source_evidence_refs": [PINS["six"]["repository"], PINS["six"]["revision"], DB_SHA],
                         "note": "Official database source with declared column projection; local source-admission witness only, not official scoring or collaboration evidence."}
    spec.update(scenario_id="six-p0-" + row["instance_id"], projects=[{"package": pkg}],
                roles=[], variation={"kind": "structure", "source_usage": "interface_development", "model_eligible": False})
    spec["world"]["world_id"] = "six-source-p0"
    spec["world"]["actors"] = {"implementer": {}, "operator": {}}
    deployment = build_scenario(spec, Path(root) / "world")
    if deployment.status != "ready":
        raise ValueError(deployment.diagnostics)
    return deployment.world


def assess_build(world, reference_, expected):
    artifact = world.state["artifacts"][reference_["object_id"]]
    metadata = artifact["versions"][reference_["version_id"]]
    provenance = metadata.get("execution_provenance") or {}
    product = read_json(world.store.version_path(artifact, reference_["version_id"]))
    table = product.get("tables", {}).get("repair", {})
    return {"real_sql_build": provenance.get("kind") == "sql_build" and provenance.get("status") == "success",
            "independent_rows_match": rows_equal(table.get("rows", []), expected),
            "expected_rows": len(expected), "actual_rows": len(table.get("rows", [])),
            "passed": provenance.get("kind") == "sql_build" and provenance.get("status") == "success" and rows_equal(table.get("rows", []), expected),
            "reference": reference_, "scope": "Host-only P0 independent relational/count oracle and actual build provenance. Not official Six/BIRD score, training reward or fixed-work delivery admission."}


if __name__ == "__main__":
    if sys.argv[1:] != ["--sqlite-child"]:
        raise SystemExit("Only the bounded native child entrypoint is exposed")
    print(json.dumps(_sqlite_child(json.load(sys.stdin)), allow_nan=False))
