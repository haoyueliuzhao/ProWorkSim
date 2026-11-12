"""Finite reconciliation strategy using only an opaque public project port.

The matcher is independent of the domain validator. It groups by the public key,
then classifies applicability before doing arithmetic. No hidden answer, storage
handle, evaluator call, privileged state mutation or model is used.
"""

import copy
import math

from ..tool_outcomes import classify_tool_result


def match_public_tables(left, right, policy, left_alias, right_alias):
    groups = {}
    for side, table in enumerate((left, right)):
        for record in table["records"]:
            key = (record["entity"], record["metric"])
            groups.setdefault(key, [[], []])[side].append(record)
    rows = []
    counts = {
        key: 0
        for key in ("matched", "converted", "conflict", "incomparable", "missing", "ambiguous")
    }
    unresolved = []
    factors = policy["unit_factors"]
    for key in sorted(groups):
        lrows, rrows = groups[key]
        lrows = sorted(lrows, key=lambda r: r["record_id"])
        rrows = sorted(rrows, key=lambda r: r["record_id"])
        row = {
            "key": list(key),
            "period": None,
            "left_ids": [r["record_id"] for r in lrows],
            "right_ids": [r["record_id"] for r in rrows],
            "left_value": None,
            "right_value": None,
            "delta": None,
            "evidence": [],
        }
        for alias, records in ((left_alias, lrows), (right_alias, rrows)):
            for record in records:
                row["evidence"].append(
                    {
                        "alias": alias,
                        **{
                            k: record[k]
                            for k in (
                                "record_id",
                                "location",
                                "period",
                                "definition",
                                "currency",
                                "unit",
                                "value",
                            )
                        },
                    }
                )
        if len(lrows) > 1 or len(rrows) > 1:
            category = "ambiguous"
        elif not lrows or not rrows:
            category = "missing"
        else:
            a, b = lrows[0], rrows[0]
            if a["period"] == b["period"]:
                row["period"] = a["period"]
            compatible = all(a[field] == b[field] for field in ("period", "definition", "currency"))
            compatible = (
                compatible
                and a["period"] == policy["reporting_period"]
                and all(r["unit"] in factors for r in (a, b))
            )
            if not compatible:
                category = "incomparable"
            elif a["value"] is None or b["value"] is None:
                category = "missing"
            else:
                values = [r["value"] * factors[r["unit"]] for r in (a, b)]
                if any(type(r["value"]) not in (int, float) for r in (a, b)) or not all(
                    math.isfinite(v) for v in values
                ):
                    raise ValueError("Unsupported non-finite numeric input")
                row.update(left_value=values[0], right_value=values[1], delta=values[0] - values[1])
                category = (
                    "conflict"
                    if row["delta"] != 0
                    else ("matched" if a["unit"] == b["unit"] else "converted")
                )
        row["status"] = category
        rows.append(row)
        counts[category] += 1
        if category not in {"matched", "converted"}:
            unresolved.append(list(key))
    return {
        "rows": rows,
        "summary": counts,
        "unresolved": unresolved,
        "period": policy["reporting_period"],
        "base_unit": policy["base_unit"],
    }


class ReconciliationWorker:
    def __init__(self, port, *, split=False):
        self.port, self.split = port, split
        self.transcript = []

    def observe(self):
        result = self.port.observe()
        self.transcript.append({"kind": "observation", "value": copy.deepcopy(result)})
        return result

    def call(self, action, **arguments):
        result = self.port.call(action, **arguments)
        self.transcript.append(
            {
                "kind": "call",
                "action": action,
                "arguments": copy.deepcopy(arguments),
                "response": copy.deepcopy(result),
            }
        )
        if not result.get("ok"):
            raise PublicRejection(action, result)
        return result["result"]

    def run(self, work_id=None):
        definitions = self.port.tools()
        self.transcript.append({"kind": "tools", "value": copy.deepcopy(definitions)})
        try:
            observation = self.observe()
            candidates = {
                wid: item
                for wid, item in observation["work_items"].items()
                if any(
                    c.get("kind") == "reconciliation_table"
                    for c in item.get("deliverable_contract", {}).get("content_checks", [])
                )
            }
            if work_id is None:
                work_id = next(
                    (
                        wid
                        for wid, item in candidates.items()
                        if item.get("status") not in {"accepted", "superseded"}
                        and item.get("submission_state") != "accepted"
                    ),
                    None,
                )
            if work_id not in candidates:
                return {
                    "status": "worker_waiting",
                    "reason": "No publicly selectable reconciliation work",
                }
            item = candidates[work_id]
            spec = next(
                c
                for c in item["deliverable_contract"]["content_checks"]
                if c["kind"] == "reconciliation_table"
            )
            documents, references = {}, {}
            for source in spec["sources"]:
                alias = source["alias"]
                observation = self.observe()
                aid = observation["workspaces"][item["project_id"]].get(alias)
                if aid not in observation["objects"]:
                    routes = observation.get("information_routes", [])
                    if isinstance(routes, dict):
                        routes = routes.values()
                    route = next(
                        (
                            r
                            for r in routes
                            if r["work_id"] == work_id and r["object_alias"] == alias
                        ),
                        None,
                    )
                    if route is None:
                        return {
                            "status": "worker_waiting",
                            "reason": "No legal information route",
                            "alias": alias,
                            "classification": "capability_gap",
                        }
                    self.call("request_information", route_id=route["route_id"], work_id=work_id)
                    for _ in range(3):
                        self.call("wait", ticks=1)
                        observation = self.observe()
                        aid = observation["workspaces"][item["project_id"]].get(alias)
                        if aid in observation["objects"]:
                            break
                    if aid not in observation["objects"]:
                        return {
                            "status": "world_blocked",
                            "reason": "Requested required table remains unavailable",
                            "alias": alias,
                        }
                requirement = item.get("requirements", {})
                binding = observation.get("adoptions", {}).get(work_id + "::" + alias)
                policy = requirement.get("input_policies", {}).get(alias, "fixed")
                if policy == "fixed":
                    version = requirement.get("input_versions", {}).get(alias, "v1")
                elif binding:
                    version = binding["target_version"]
                else:
                    publications = observation.get("publications", [])
                    if isinstance(publications, dict):
                        publications = publications.values()
                    versions = [r["version_id"] for r in publications if r["object_id"] == aid]
                    version = versions[-1] if versions else None
                if version is None:
                    return {
                        "status": "worker_waiting",
                        "reason": "No public policy target",
                        "alias": alias,
                    }
                if binding is None:
                    self.call(
                        "adopt",
                        alias=alias,
                        object_id=aid,
                        version_id=version,
                        policy=policy,
                        work_ids=[work_id],
                    )
                elif binding["adopted_version"] != version:
                    self.call("adopt_version", alias=alias, version_id=version, work_id=work_id)
                read = self.call("read_object", alias=alias, version_id=version, work_id=work_id)
                content = read["data"]
                for part in source.get("data_path", []):
                    content = content[part]
                documents[alias] = content
                references[alias] = {
                    "object_id": read["reference"]["artifact_id"],
                    "version_id": read["reference"]["version_id"],
                }
            reconciliation = match_public_tables(
                documents[spec["left_alias"]],
                documents[spec["right_alias"]],
                documents[spec["policy_alias"]],
                spec["left_alias"],
                spec["right_alias"],
            )
            data = {"reconciliation": reconciliation, "sources": references}
            outputs = (
                {
                    "comparison": {"reconciliation": reconciliation},
                    "evidence": {"sources": references},
                }
                if self.split
                else {"comparison": data}
            )
            observation = self.observe()
            if item.get("submission_state") == "pending":
                self.call(
                    "withdraw",
                    work_id=work_id,
                    submission_id=item["pending_submission_id"],
                    reason="Repair the existing delivery under unchanged requirements",
                )
            for alias, output in outputs.items():
                exists = alias in observation["workspaces"][item["project_id"]]
                arguments = {
                    "alias": alias,
                    "data": output,
                    "dependencies": list(references.values()),
                    "work_id": work_id,
                }
                if not exists:
                    arguments.update(
                        kind="json", filename=alias + ".json", deliverable_role="reconciliation"
                    )
                self.call("write_object" if exists else "create_object", **arguments)
            submission = self.call("submit", work_id=work_id, artifacts=list(outputs))
            return {
                "status": "submitted",
                "work_id": work_id,
                "submission": submission,
                "data": data,
                "artifacts": list(outputs),
            }
        except PublicRejection as exc:
            return {
                **classify_tool_result(exc.response),
                "tool": exc.action,
                "reason": "Raw rejection facts and explicit runtime attribution retained",
            }
        except (KeyError, ValueError, TypeError) as exc:
            return {
                "status": "worker_waiting",
                "classification": "unsupported_input_or_contract",
                "reason": str(exc),
            }


class PublicRejection(Exception):
    def __init__(self, action, response):
        self.action, self.response = action, response
