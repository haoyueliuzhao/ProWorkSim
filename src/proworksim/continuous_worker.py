"""Finite round-robin worker over opaque public tools/observe/call ports.

Progress is keyed by port and exact work edition. Checkpoints contain only data
returned through those ports plus transparent arithmetic and scheduling choices.
They are policy checkpoints, not WorldCore snapshots or crash-atomic recovery.
"""

import copy
import math
import uuid


class ContinuousWorker:
    def __init__(self, ports, checkpoint=None, run_id=None):
        if not isinstance(ports, dict) or not ports:
            raise ValueError("Worker requires a nonempty mapping of public ports")
        self.ports = dict(ports)
        saved = copy.deepcopy(checkpoint) if checkpoint is not None else {}
        if saved and saved.get("port_labels") != list(ports):
            raise ValueError("Checkpoint port labels/order must match supplied public ports")
        self.run_id = saved.get("run_id", run_id or uuid.uuid4().hex)
        self.actions = saved.get("actions", 0)
        self.port_cursor = saved.get("port_cursor", 0)
        self.work_cursors = saved.get("work_cursors", {})
        self.tasks = saved.get("tasks", {})
        self.transcript = saved.get("transcript", [])
        self.port_counts = saved.get("port_counts", {})
        self.steps = saved.get("steps", 0)

    def snapshot(self):
        return copy.deepcopy({
            "checkpoint_version": "public-continuous-worker-v0.8",
            "port_labels": list(self.ports), "run_id": self.run_id,
            "actions": self.actions, "port_cursor": self.port_cursor,
            "work_cursors": self.work_cursors, "tasks": self.tasks,
            "transcript": self.transcript, "port_counts": self.port_counts, "steps": self.steps,
        })

    def _record(self, port, kind, value):
        self.transcript.append({"sequence": len(self.transcript), "port": port,
                                "kind": kind, "value": copy.deepcopy(value)})
        return value

    @staticmethod
    def _get(data, path):
        for part in path.split(".") if isinstance(path, str) else path:
            data = data[part]
        return data

    @staticmethod
    def _set(data, path, value):
        parts = path.split(".") if isinstance(path, str) else path
        for part in parts[:-1]:
            data = data.setdefault(part, {})
        data[parts[-1]] = copy.deepcopy(value)

    def _outcome(self, task, status, reason, **details):
        task.update(status=status, reason=reason)
        task.update(details)
        return {"status": status, "reason": reason, "work_id": task["work_id"],
                "port": task["port"], "action_performed": False, **details}

    def _call(self, label, task, definitions, action, **arguments):
        names = {definition["name"] for definition in definitions}
        if action not in names:
            return None, self._outcome(task, "worker_waiting", "Required tool is not advertised",
                                       capability_gap="missing_tool", tool=action)
        self.actions += 1
        key = f"continuous-worker-{self.run_id}-{self.actions}"
        record = {"action": action, "arguments": copy.deepcopy(arguments), "request_key": key}
        try:
            response = self.ports[label].call(action, request_key=key, **arguments)
        except Exception as exc:
            record["exception"] = {"type": type(exc).__name__, "message": str(exc)}
            self._record(label, "tool_call", record)
            result = self._outcome(task, "environment_error", "Public tool raised an exception",
                                   tool_error=record["exception"])
            result["action_performed"] = True
            return None, result
        record["response"] = copy.deepcopy(response)
        self._record(label, "tool_call", record)
        if not response.get("ok"):
            result = self._outcome(task, "environment_error", "Public tool rejected the action",
                                   tool_error=response)
            result["action_performed"] = True
            return None, result
        result = self._outcome(task, "running", "Public action completed", action=action)
        result["action_performed"] = True
        return response["result"], result

    @staticmethod
    def _sources(check):
        if check["kind"] == "json_linear_sources":
            return check["sources"]
        if check["kind"] not in {"json_matches_source_field", "json_matches_source_cell"}:
            raise ValueError("Unsupported public content contract")
        source = {"alias": check["adoption_alias"], "reference_path": check["reference_path"],
                  "kind": "json_field" if check["kind"].endswith("field") else "xlsx_cell"}
        source.update({key: check[key] for key in ("source_path", "sheet", "cell") if key in check})
        return [source]

    @staticmethod
    def _conditions(observation, wid):
        conditions = observation.get("conditions", {})
        if isinstance(conditions, dict):
            conditions = conditions.values()
        return [condition for condition in conditions
                if condition.get("work_item_id", condition.get("work_id")) == wid
                and condition["status"] in {"open", "unavailable"}]

    def _information(self, label, task, observation, definitions, alias):
        wid = task["work_id"]
        conditions = self._conditions(observation, wid)
        routes = observation.get("information_routes", [])
        if isinstance(routes, dict):
            routes = routes.values()
        routes = [r for r in routes if r["work_id"] == wid and r["object_alias"] == alias]
        if not routes:
            return self._outcome(
                task, "world_blocked" if conditions else "worker_waiting",
                "Required input has no public information route",
                capability_gap="missing_information_route",
                condition_ids=[c["condition_id"] for c in conditions],
            )
        route = sorted(routes, key=lambda value: value["route_id"])[0]
        token = [route.get("availability_revision", route.get("revision", 0)),
                 route.get("availability", "unknown")]
        previous = task["requests"].get(route["route_id"])
        if previous is None or previous["route_token"] != token:
            result, outcome = self._call(
                label, task, definitions, "request_information",
                route_id=route["route_id"], work_id=wid,
            )
            if result is not None:
                task["requests"][route["route_id"]] = {"route_token": token, **result}
            return outcome
        if any(c["status"] == "unavailable" for c in conditions):
            return self._outcome(task, "world_blocked", "World records unavailable input",
                                 condition_ids=[c["condition_id"] for c in conditions])
        if not conditions:
            return self._outcome(task, "worker_waiting", "Request has no readable result",
                                 capability_gap="request_without_readable_result")
        _, outcome = self._call(label, task, definitions, "wait", ticks=1)
        return outcome

    @staticmethod
    def _policy(item, alias, adoption):
        requirements = item.get("requirements", {})
        policy = requirements.get("input_policies", {}).get(alias, requirements.get("input_policy"))
        if isinstance(policy, list):
            policy = adoption["policy"] if adoption and adoption["policy"] in policy else policy[0]
        return policy or (adoption["policy"] if adoption else "fixed")

    def _advance(self, label, wid, item, observation, definitions, task):
        if task.get("status") == "environment_error":
            return self._outcome(task, "environment_error", task["reason"],
                                 tool_error=task.get("tool_error"))
        if item.get("submission_state") == "pending":
            return self._outcome(task, "submitted", "Submitted work awaits institutional review")
        checks = item.get("deliverable_contract", {}).get("content_checks", [])
        try:
            if len(checks) != 1:
                raise ValueError("Worker requires one supported finite content check")
            check = checks[0]
            sources = self._sources(check)
        except (KeyError, ValueError, TypeError) as exc:
            return self._outcome(task, "worker_waiting", str(exc), capability_gap="content_contract")
        workspace = observation["workspaces"].get(item["project_id"], {})
        references, values = [], []
        for source in sources:
            alias = source["alias"]
            aid = workspace.get(alias)
            if aid is None or aid not in observation["objects"]:
                return self._information(label, task, observation, definitions, alias)
            visible = observation["objects"][aid]["versions"]
            adoption = observation.get("adoptions", {}).get(wid + "::" + alias)
            policy = self._policy(item, alias, adoption)
            requirements = item.get("requirements", {})
            explicit = requirements.get("input_versions", {}).get(alias, requirements.get("input_version"))
            if policy == "fixed":
                version = explicit or (adoption["adopted_version"] if adoption else None)
                version = version or (visible[0] if len(visible) == 1 else None)
            elif adoption:
                version = adoption["target_version"]
            elif policy == "current_published":
                releases = observation.get("publications", [])
                if isinstance(releases, dict):
                    releases = releases.values()
                versions = [release["version_id"] for release in releases
                            if release["object_id"] == aid and release["version_id"] in visible]
                version = versions[-1] if versions else None
            else:
                version = visible[0] if len(visible) == 1 else None
            if version is None:
                return self._outcome(task, "worker_waiting", "No unambiguous public policy target",
                                     capability_gap="input_target", alias=alias)
            if version not in visible:
                return self._information(label, task, observation, definitions, alias)
            reference = {"object_id": aid, "version_id": version}
            if adoption is None:
                _, outcome = self._call(label, task, definitions, "adopt", alias=alias,
                                         **reference, policy=policy, work_ids=[wid])
                return outcome
            if adoption["adopted_version"] != version:
                _, outcome = self._call(label, task, definitions, "adopt_version", alias=alias,
                                         version_id=version, work_id=wid)
                return outcome
            cached = task["sources"].get(alias)
            if task.get("source_error", {}).get(alias) == reference:
                return self._outcome(task, "worker_waiting", "Public source lacks contracted content",
                                     capability_gap="source_content")
            if cached is None or cached["reference"] != reference:
                action = "read_object" if source["kind"] == "json_field" else "sheet_read"
                arguments = {**reference, "work_id": wid}
                if action == "sheet_read":
                    arguments["sheet"] = source["sheet"]
                result, outcome = self._call(label, task, definitions, action, **arguments)
                if result is not None:
                    try:
                        if action == "read_object":
                            value = self._get(result["data"], source["source_path"])
                        else:
                            cell = result["sheets"][source["sheet"]][source["cell"]]
                            if "error" in cell:
                                raise ValueError("Public source cell contains an error")
                            value = cell["value"]
                        task["sources"][alias] = {"reference": reference, "value": value}
                    except (KeyError, TypeError, ValueError) as exc:
                        task.setdefault("source_error", {})[alias] = reference
                        outcome = self._outcome(task, "worker_waiting", str(exc),
                                                capability_gap="source_content")
                        outcome["action_performed"] = True
                return outcome
            references.append(reference)
            values.append(cached["value"])
        data = {}
        if check["kind"] == "json_linear_sources":
            value = check.get("constant", 0)
            if any(type(number) not in (int, float) or not math.isfinite(number) for number in values):
                return self._outcome(task, "worker_waiting", "Linear input is not a finite number",
                                     capability_gap="source_content")
            for source, number in zip(sources, values):
                value += source.get("coefficient", 1) * number
            if not math.isfinite(value):
                return self._outcome(task, "worker_waiting", "Linear result is not finite",
                                     capability_gap="source_content")
        else:
            value = values[0]
        self._set(data, check["path"], value)
        for source, reference in zip(sources, references):
            self._set(data, source["reference_path"], reference)
        output = task.get("output")
        if output is None:
            alias, suffix = "delivery", 1
            while alias in workspace:
                suffix += 1
                alias = "delivery-" + str(suffix)
            roles = item["deliverable_contract"].get("allowed_roles", [])
            result, outcome = self._call(
                label, task, definitions, "create_object", work_id=wid, alias=alias,
                filename=alias + ".json", kind="json", data=data,
                deliverable_role=check.get("role", roles[0] if roles else "report"),
                dependencies=references,
            )
            if result is not None:
                task["output"] = {"alias": alias, "data": copy.deepcopy(data), "reference": result}
            return outcome
        if output["data"] != data:
            result, outcome = self._call(label, task, definitions, "write_object", work_id=wid,
                                         alias=output["alias"], data=data, dependencies=references)
            if result is not None:
                task["output"] = {"alias": output["alias"], "data": copy.deepcopy(data), "reference": result}
            return outcome
        if "submit" not in item.get("enabled_actions", []):
            conditions = self._conditions(observation, wid)
            return self._outcome(task, "world_blocked" if conditions else "worker_waiting",
                                 "Public prerequisites do not enable submission",
                                 condition_ids=[c["condition_id"] for c in conditions])
        result, outcome = self._call(label, task, definitions, "submit", work_id=wid,
                                     artifacts=[output["alias"]])
        if result is not None:
            task.update(status="submitted", reason="Delivered exact public inputs",
                        submission_id=result["submission_id"])
            outcome.update(status="submitted", submission_id=result["submission_id"])
        return outcome

    def step(self):
        """Observe one port and advance at most one owned current work by one call."""
        labels = list(self.ports)
        label = labels[self.port_cursor % len(labels)]
        self.port_cursor += 1
        self.steps += 1
        try:
            definitions = self._record(label, "tools", self.ports[label].tools())
            observation = self._record(label, "observation", self.ports[label].observe())
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
            self._record(label, "port_error", error)
            return {"status": "environment_error", "port": label,
                    "reason": "Public observation interface failed", "tool_error": error,
                    "action_performed": False}
        candidates = []
        for wid, item in observation["work_items"].items():
            if item["owner_role"] != observation["actor_id"]:
                continue
            key = label + ":" + wid
            task = self.tasks.setdefault(key, {"port": label, "work_id": wid,
                                                "requirement_version": item["requirement_version"],
                                                "sources": {}, "requests": {}, "status": "running"})
            if not item.get("is_current", True) or item["status"] in {"superseded", "cancelled"}:
                task.update(status="superseded", reason="Observed archived work edition")
            elif item["status"] == "accepted":
                task.update(status="completed", reason="World reports accepted work")
            else:
                candidates.append((wid, item, task))
        self.port_counts[label] = len(candidates)
        if not candidates:
            return {"status": "completed", "port": label, "reason": "No unfinished owned current work",
                    "action_performed": False}
        candidates.sort(key=lambda value: value[0])
        cursor = self.work_cursors.get(label, 0)
        wid, item, task = candidates[cursor % len(candidates)]
        self.work_cursors[label] = cursor + 1
        return self._advance(label, wid, item, observation, definitions, task)

    def run(self, max_actions=40):
        """Run up to this many additional calls, stopping at a full idle sweep."""
        if type(max_actions) is not int or max_actions < 0:
            raise ValueError("max_actions must be a nonnegative integer")
        start, idle, results = self.actions, 0, []
        while self.actions - start < max_actions:
            result = self.step()
            results.append(result)
            idle = 0 if result["action_performed"] else idle + 1
            if result["status"] == "environment_error":
                return self.result("environment_error", results)
            threshold = len(self.ports) * max([1, *self.port_counts.values()])
            if idle >= threshold:
                statuses = [task["status"] for task in self.tasks.values()
                            if task["status"] != "superseded"]
                status = ("world_blocked" if "world_blocked" in statuses else
                          "worker_waiting" if "worker_waiting" in statuses else
                          "submitted" if "submitted" in statuses else "completed")
                return self.result(status, results)
        return self.result("budget_exhausted", results)

    def result(self, status, steps):
        return {"status": status, "run_id": self.run_id, "actions": self.actions,
                "tasks": copy.deepcopy(self.tasks), "steps": copy.deepcopy(steps),
                "transcript": copy.deepcopy(self.transcript)}
