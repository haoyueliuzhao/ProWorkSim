"""Transparent finite SQL/coordinator colleagues using only public contexts.

The SQL generator is an explicit rule policy, never invoked by a model adapter.
Editable tests and execution feedback do not import the independent evaluator.
"""

import json

from ..templates.executable_project import sql_project
from .team_policies import ReconciliationPolicy, _act, _cache, _source_step, _start, _wait


class ExecutableWorkerPolicy(ReconciliationPolicy):
    kind = "executable_sql_project"

    def __init__(self, *, equivalent=False, business_wrong=False, tampered_tests=False):
        super().__init__()
        self.equivalent, self.business_wrong, self.tampered_tests = (
            equivalent,
            business_wrong,
            tampered_tests,
        )
        self.config = {
            "equivalent": equivalent,
            "business_wrong": business_wrong,
            "tampered_tests": tampered_tests,
        }

    def _work(self, memory, task, obs, item, wid, spec):
        decision, sources, refs = _source_step(memory, task, obs, item, wid, spec)
        if decision:
            return decision
        config = item["requirements"]["sql_project"]
        pid = item["project_id"]
        code_oid = obs["workspaces"][pid][config["code_alias"]]
        code_version = obs["objects"][code_oid]["versions"][-1]
        key = "code:" + code_version
        decision = _cache(
            memory,
            task,
            wid,
            key,
            "read_object",
            alias=config["code_alias"],
            version_id=code_version,
            work_id=wid,
        )
        if decision:
            return decision
        existing = task["cache"][key]["data"]
        grain = (
            sources["request"]["tables"]["interface_request"]["rows"][0][0]
            if "request" in sources
            else "customer"
        )
        desired = sql_project(
            spec["project_kind"],
            grain,
            equivalent=self.equivalent,
            business_wrong=self.business_wrong,
            tampered_tests=self.tampered_tests,
        )
        # Initial P1 deliberately attempts its supplied starter SQL once, sees a
        # real BinderException, then repairs. Requirement changes proactively edit
        # to the newly visible grain; they do not reuse an old task's build cache.
        if existing != desired and (
            item["requirement_version"] > 1
            or task.get("saw_execution_error")
            or self.business_wrong
            or self.tampered_tests
            or self.equivalent
        ):
            return _act(
                memory,
                "write_object",
                {"alias": config["code_alias"], "data": desired, "work_id": wid},
            )
        signature = json.dumps({"code": code_version, "refs": refs}, sort_keys=True)
        build_key = "build:" + signature
        decision = _cache(
            memory,
            task,
            wid,
            build_key,
            "sql_build",
            work_id=wid,
            code_alias=config["code_alias"],
            output_alias=config["result_alias"],
            input_aliases=list(refs),
        )
        if decision:
            return decision
        built = task["cache"][build_key]
        if built["execution_status"] != "success":
            task["saw_execution_error"] = True
            if existing != desired:
                return _act(
                    memory,
                    "write_object",
                    {"alias": config["code_alias"], "data": desired, "work_id": wid},
                )
            return _wait(
                memory,
                "Actual SQL execution/test error retained; waiting for changed public inputs or requirements",
            )
        model = next(iter(built["tables"]))
        query_key = "query:" + signature
        decision = _cache(
            memory,
            task,
            wid,
            query_key,
            "sql_query",
            work_id=wid,
            source_alias=config["result_alias"],
            sql="SELECT COUNT(*) AS row_count FROM " + model,
            output_alias=config["query_alias"],
        )
        if decision:
            return decision
        if task["cache"][query_key]["execution_status"] != "success":
            return _wait(memory, "Actual inspection query did not execute successfully")
        return _act(
            memory,
            "submit",
            {"work_id": wid, "artifacts": [config["code_alias"], config["result_alias"]]},
            {"kind": "submit", "work": wid},
        )


class InterfaceCoordinatorPolicy:
    """P2 participant in P1 raises one located, version-specific interface issue."""

    def __init__(self):
        self.config = {}

    def decide(self, context):
        memory, rejected = _start(context)
        if rejected:
            return rejected
        obs = context["observation"]
        candidates = [
            (wid, item)
            for wid, item in obs["work_items"].items()
            if item.get("requirements", {}).get("sql_project", {}).get("kind") == "P1"
            and item.get("submission_state") == "accepted"
        ]
        if not candidates:
            return _wait(memory, "No accepted metric interface to inspect")
        wid, item = candidates[-1]
        task = memory["tasks"].setdefault(wid, {"phase": "coordinate"})
        request_oid = item["requirements"]["source_objects"]["request"]
        publications = [r for r in obs.get("publications", []) if r["object_id"] == request_oid]
        if not publications:
            return _wait(memory, "No published downstream interface request")
        version = publications[-1]["version_id"]
        request_key = "request:" + version
        decision = _cache(
            memory, task, wid, request_key, "read_object", object_id=request_oid, version_id=version
        )
        if decision:
            return decision
        request = task["cache"][request_key]["data"]
        if request["tables"]["interface_request"]["rows"][0][0] != "customer_month":
            return _wait(memory, "Initial customer interface is usable; no fabricated issue")
        sid = item.get("latest_submission_id")
        if not sid:
            return _wait(memory, "No publicly identified submission")
        inspect_key = "inspect:" + sid
        decision = _cache(
            memory, task, wid, inspect_key, "inspect_submission", work_id=wid, submission_id=sid
        )
        if decision:
            return decision
        sub = task["cache"][inspect_key]
        oid = obs["workspaces"][item["project_id"]]["result"]
        vid = sub["artifact_versions"][oid]
        product_key = "result:" + vid
        decision = _cache(
            memory, task, wid, product_key, "read_object", object_id=oid, version_id=vid
        )
        if decision:
            return decision
        result = task["cache"][product_key]["data"]
        if "period" in {c["name"] for c in result["tables"]["metrics"]["columns"]}:
            return _wait(memory, "Current accepted interface has the requested month key")
        marker = sid + ":" + version
        if marker in memory.setdefault("reported", []):
            return _wait(memory, "Exact interface feedback already recorded; do not duplicate it")
        memory["reported"].append(marker)
        return _act(
            memory,
            "raise_issue",
            {
                "work_id": wid,
                "submission_id": sid,
                "issue_key": "customer-month-" + version,
                "object_id": oid,
                "version_id": vid,
                "locator": ["tables", "metrics", "columns"],
                "description": "P2 requests customer-month grain. This exact published metric version has no period column, so joining it to monthly customer analysis cannot satisfy the new contract. Preserve its historical validity; publish a version with(customer_id,period).",
                "evidence": [
                    {
                        "object_id": request_oid,
                        "version_id": version,
                        "locator": ["tables", "interface_request"],
                    }
                ],
                "blocking": False,
            },
        )
