"""Transparent worker for one finite publicly described source-to-JSON task.

The only environment interface is session.observe(), session.tools(), and
session.call(). Inputs, exact references, work IDs and values are discovered from
those returns. The worker keeps the actual returns as they arrive; it does not
rebuild past observations or inspect the world's persistence implementation.
This is a deterministic mechanism witness, not a general planning agent.
"""

import copy
import uuid


class PublicWorker:
    def __init__(self, session, max_actions=24, run_id=None):
        self.session = session
        self.run_id = run_id or uuid.uuid4().hex
        self.max_actions = max_actions
        self.transcript = []
        self.actions = 0
        self.tool_names = set()

    def record(self, kind, value):
        self.transcript.append(
            {"sequence": len(self.transcript), "kind": kind, "value": copy.deepcopy(value)}
        )
        return value

    def observe(self):
        return self.record("observation", self.session.observe())

    def call(self, action, **arguments):
        if action not in self.tool_names:
            return {"ok": False, "error": {"type": "CapabilityGap", "message": action}}
        if self.actions >= self.max_actions:
            return {"ok": False, "error": {"type": "BudgetExhausted", "message": action}}
        self.actions += 1
        key = "public-worker-" + self.run_id + "-" + str(self.actions)
        response = self.session.call(action, request_key=key, **arguments)
        self.record(
            "tool_call",
            {"action": action, "arguments": arguments, "request_key": key, "response": response},
        )
        return response

    def outcome(self, status, reason, **details):
        return {
            "status": status,
            "reason": reason,
            "run_id": self.run_id,
            "actions": self.actions,
            "transcript": self.transcript,
            **details,
        }

    @staticmethod
    def _get(data, path):
        for key in path.split(".") if isinstance(path, str) else path:
            data = data[key]
        return data

    @staticmethod
    def _set(data, path, value):
        parts = path.split(".") if isinstance(path, str) else path
        for key in parts[:-1]:
            data = data.setdefault(key, {})
        data[parts[-1]] = copy.deepcopy(value)

    def run(self):
        definitions = self.record("tools", self.session.tools())
        self.tool_names = {definition["name"] for definition in definitions}
        observation = self.observe()
        candidates = [
            (wid, item)
            for wid, item in observation["work_items"].items()
            if item["owner_role"] == observation["actor_id"]
            and item.get("is_current", True)
            and item["status"] not in {"accepted", "cancelled", "superseded"}
        ]
        if len(candidates) != 1:
            return self.outcome("capability_gap", "Worker requires exactly one current owned task")
        work_id, item = candidates[0]
        project_id = item["project_id"]
        contract = item.get("deliverable_contract", {})
        checks = contract.get("content_checks", [])
        if len(checks) != 1 or checks[0].get("kind") not in {
            "json_matches_source_cell",
            "json_matches_source_field",
        }:
            return self.outcome(
                "capability_gap", "Unsupported public content contract", work_id=work_id
            )
        check = checks[0]
        alias = check["adoption_alias"]
        policy = item.get("requirements", {}).get("input_policy", "fixed")
        requested = set()
        while self.actions < self.max_actions:
            workspace = observation["workspaces"].get(project_id, {})
            object_id = workspace.get(alias)
            if object_id is not None:
                break
            routes = observation.get("information_routes", [])
            if isinstance(routes, dict):
                routes = list(routes.values())
            matching = [
                route
                for route in routes
                if route["work_id"] == work_id and route["object_alias"] == alias
            ]
            if not matching:
                return self.outcome(
                    "waiting",
                    "Required input has no public information route",
                    capability_gap="missing_information_route",
                    work_id=work_id,
                )
            route = matching[0]
            if route["route_id"] not in requested:
                response = self.call(
                    "request_information", route_id=route["route_id"], work_id=work_id
                )
                if not response.get("ok"):
                    return self.outcome(
                        "capability_gap",
                        "Advertised request could not execute",
                        tool_error=response,
                        work_id=work_id,
                    )
                requested.add(route["route_id"])
            else:
                conditions = observation.get("conditions", {})
                if isinstance(conditions, dict):
                    conditions = list(conditions.values())
                if any(
                    condition.get("work_item_id", condition.get("work_id")) == work_id
                    and condition["status"] == "unavailable"
                    for condition in conditions
                ):
                    return self.outcome(
                        "waiting", "Requested input is explicitly unavailable", work_id=work_id
                    )
                response = self.call("wait", ticks=1)
                if not response.get("ok"):
                    return self.outcome(
                        "waiting",
                        "Cannot advance the pending public request",
                        tool_error=response,
                        work_id=work_id,
                    )
            observation = self.observe()
        else:
            return self.outcome(
                "waiting", "Information wait reached the action budget", work_id=work_id
            )
        adoption_key = project_id + "::" + alias
        adoption = observation.get("adoptions", {}).get(adoption_key)
        visible = observation["objects"][object_id]["versions"]
        if adoption is not None:
            version_id = (
                adoption["adopted_version"] if policy == "fixed" else adoption["target_version"]
            )
        elif policy == "fixed":
            explicit = item.get("requirements", {}).get("input_version")
            if explicit is not None:
                version_id = explicit
            elif len(visible) == 1:
                version_id = visible[0]
            else:
                return self.outcome(
                    "waiting",
                    "Fixed input has multiple versions without a declared choice",
                    work_id=work_id,
                )
        elif policy == "current_published":
            releases = observation.get("publications", [])
            if isinstance(releases, dict):
                releases = list(releases.values())
            releases = [
                release
                for release in releases
                if release["object_id"] == object_id and release["version_id"] in visible
            ]
            if not releases:
                return self.outcome(
                    "waiting", "No publicly discoverable published input version", work_id=work_id
                )
            version_id = releases[-1]["version_id"]
        else:
            return self.outcome(
                "capability_gap", "Unsupported public input policy", work_id=work_id
            )
        if version_id not in visible:
            return self.outcome("waiting", "Policy target is not readable", work_id=work_id)
        if adoption is None:
            adopted = self.call(
                "adopt",
                alias=alias,
                object_id=object_id,
                version_id=version_id,
                policy=policy,
                work_ids=[work_id],
            )
        elif adoption["adopted_version"] != version_id:
            adopted = self.call("adopt_version", alias=alias, version_id=version_id)
        else:
            adopted = {"ok": True}
        if not adopted.get("ok"):
            return self.outcome(
                "capability_gap",
                "Discovered adoption could not execute",
                tool_error=adopted,
                work_id=work_id,
            )
        read_tool = "sheet_read" if check["kind"] == "json_matches_source_cell" else "read_object"
        read_args = {"object_id": object_id, "version_id": version_id}
        if read_tool == "sheet_read":
            read_args["sheet"] = check["sheet"]
        read = self.call(read_tool, **read_args)
        if not read.get("ok"):
            return self.outcome(
                "waiting",
                "Selected exact input could not be read",
                tool_error=read,
                work_id=work_id,
            )
        try:
            if read_tool == "sheet_read":
                cell = read["result"]["sheets"][check["sheet"]][check["cell"]]
                if "error" in cell:
                    return self.outcome(
                        "waiting", "Source cell has a formula error", work_id=work_id
                    )
                value = cell["value"]
            else:
                value = self._get(read["result"]["data"], check["source_path"])
        except (KeyError, TypeError):
            return self.outcome(
                "waiting", "Public source lacks the contracted content", work_id=work_id
            )
        reference = {"object_id": object_id, "version_id": version_id}
        data = {}
        self._set(data, check["path"], value)
        self._set(data, check["reference_path"], reference)
        # Alias selection depends only on publicly visible names; it carries no
        # hidden artifact identity or expected answer.
        output_alias = "delivery"
        suffix = 1
        while output_alias in workspace:
            suffix += 1
            output_alias = "delivery-" + str(suffix)
        roles = contract.get("allowed_roles", [])
        created = self.call(
            "create_object",
            alias=output_alias,
            filename=output_alias + ".json",
            kind="json",
            data=data,
            deliverable_role=check.get("role", roles[0] if roles else "report"),
            dependencies=[reference],
        )
        if not created.get("ok"):
            return self.outcome(
                "capability_gap",
                "Delivery creation could not execute",
                tool_error=created,
                work_id=work_id,
            )
        observation = self.observe()
        if "submit" not in observation["work_items"][work_id]["enabled_actions"]:
            return self.outcome(
                "waiting", "Public work prerequisites do not permit submission", work_id=work_id
            )
        submitted = self.call("submit", work_id=work_id, artifacts=[output_alias])
        if not submitted.get("ok"):
            return self.outcome(
                "capability_gap",
                "Publicly enabled submission could not execute",
                tool_error=submitted,
                work_id=work_id,
            )
        self.observe()
        return self.outcome(
            "submitted",
            "Created delivery from the exact public input",
            work_id=work_id,
            submission_id=submitted["result"]["submission_id"],
            source_reference=reference,
            output_reference=created["result"],
        )


def run_public_worker(session, max_actions=24, run_id=None):
    return PublicWorker(session, max_actions=max_actions, run_id=run_id).run()
