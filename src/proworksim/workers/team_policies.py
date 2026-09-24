"""Finite business policies for StaffRuntime's observation-only decision ABI.

Policies have no port, world, evaluator, controller callback or answer oracle.
Their JSON memory stores only previous public observations/results and local
business computations. Fault options are explicit experimental strategy choices.
"""

import copy
import json
import math

from .reconciliation import match_public_tables
from .research_review import _fact, _field, _sentence


def _act(memory, action, arguments, pending=None):
    memory["pending"] = pending or {"kind": "ack"}
    return {"kind": "act", "action": action, "arguments": arguments, "memory": memory}


def _wait(memory, reason):
    return {"kind": "wait", "memory": memory, "reason": reason}


def _start(context):
    memory = copy.deepcopy(context.get("memory") or {})
    memory.setdefault("tasks", {})
    pending = memory.pop("pending", None)
    result = context.get("last_result")
    if pending is not None and result is not None:
        if not result.get("ok"):
            memory["last_rejection"] = copy.deepcopy(result)
            return memory, _wait(
                memory, "Previous business action was rejected; raw result retained"
            )
        data = result["result"]
        task = memory["tasks"].get(pending.get("work"))
        if pending["kind"] == "cache":
            task.setdefault("cache", {})[pending["key"]] = copy.deepcopy(data)
        elif pending["kind"] == "stage":
            task["phase"] = pending["phase"]
        elif pending["kind"] == "submit":
            task["submitted"] = data["submission_id"]
            task["phase"] = "respond" if task.get("repair_issue") else "idle"
            task["ever_submitted"] = True
        elif pending["kind"] == "response":
            task.setdefault("responded", []).append(pending["issue"])
            task["phase"] = "idle"
            task.pop("repair_issue", None)
        elif pending["kind"] == "delivered":
            task.setdefault("delivery_steps", []).append(pending["key"])
    return memory, None


def _cache(memory, task, wid, key, action, **arguments):
    if key not in task.setdefault("cache", {}):
        return _act(memory, action, arguments, {"kind": "cache", "work": wid, "key": key})
    return None


def _checks(item, kind):
    return [
        c
        for c in item.get("deliverable_contract", {}).get("content_checks", [])
        if c.get("kind") == kind
    ]


def _output_alias(observation, item, kind):
    explicit = item.get("requirements", {}).get("output_alias")
    if explicit:
        return explicit
    role = "report" if kind == "research_report" else "reconciliation"
    workspace = observation["workspaces"][item["project_id"]]
    candidates = [
        alias
        for alias, oid in workspace.items()
        if observation["objects"].get(oid, {}).get("role") == role
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return role
    raise ValueError("Ambiguous public output; requirements.output_alias is required")


def _source_step(memory, task, observation, item, wid, spec, snapshot=None):
    """Bind and read one source per opportunity; reuse only exact-version reads."""
    docs, refs = {}, {}
    for source in spec["sources"]:
        alias = source["alias"]
        binding = (snapshot or observation.get("adoptions", {})).get(wid + "::" + alias)
        if snapshot is not None:
            if binding is None:
                return _wait(memory, "Submission has no exact public source binding"), None, None
            oid = binding["object_id"]
            version = binding.get("version_id", binding.get("adopted_version"))
        else:
            req = item.get("requirements", {})
            oid = observation["workspaces"][item["project_id"]].get(alias)
            oid = oid or req.get("source_objects", {}).get(alias)
            if oid not in observation["objects"]:
                route = next(
                    (
                        r
                        for r in observation.get("information_routes", [])
                        if r["work_id"] == wid and r["object_alias"] == alias
                    ),
                    None,
                )
                if route:
                    token = route["route_id"] + ":" + str(route.get("availability_revision", 0))
                    if token not in task.setdefault("requested", []):
                        task["requested"].append(token)
                        return (
                            _act(
                                memory,
                                "request_information",
                                {"route_id": route["route_id"], "work_id": wid},
                            ),
                            None,
                            None,
                        )
                    if route.get("availability") == "available":
                        return _act(memory, "wait", {"ticks": 1}), None, None
                return _wait(memory, "Required input is not publicly accessible"), None, None
            policy = req.get("input_policies", {}).get(alias, req.get("input_policy", "fixed"))
            if isinstance(policy, list):
                policy = policy[0]
            if policy == "fixed":
                version = req.get("input_versions", {}).get(alias, req.get("input_version"))
            elif policy == "current_applicable":
                version = observation["objects"][oid]["versions"][-1]
            else:
                version = binding.get("target_version") if binding else None
                releases = [r for r in observation.get("publications", []) if r["object_id"] == oid]
                if releases:
                    version = releases[-1]["version_id"]
            if version is None:
                return _wait(memory, "No explicit public input version target"), None, None
            if binding is None:
                return (
                    _act(
                        memory,
                        "adopt",
                        {
                            "alias": alias,
                            "object_id": oid,
                            "version_id": version,
                            "policy": policy,
                            "work_ids": [wid],
                        },
                    ),
                    None,
                    None,
                )
            if binding["adopted_version"] != version:
                return (
                    _act(
                        memory,
                        "adopt_version",
                        {"alias": alias, "version_id": version, "work_id": wid},
                    ),
                    None,
                    None,
                )
        key = "source:" + oid + ":" + version
        decision = _cache(
            memory, task, wid, key, "read_object", object_id=oid, version_id=version, work_id=wid
        )
        if decision:
            return decision, None, None
        value = task["cache"][key]
        docs[alias] = _field(value["data"], source.get("data_path", []))
        refs[alias] = {
            "object_id": value["reference"]["artifact_id"],
            "version_id": value["reference"]["version_id"],
        }
    return None, docs, refs


def inspect_report(spec, document, refs, sources, source_refs):
    """Independent finite grammar inspection; deliberately not domain evaluation."""
    sections = _field(document, spec["path"])["sections"]
    findings = []
    for claim in spec["claims"]:
        fact = _fact(claim, sources[claim["source_alias"]])
        index = next(
            (i for i, s in enumerate(sections) if s["section_id"] == claim["section_id"]), 0
        )
        section = next((s for s in sections if s["section_id"] == claim["section_id"]), {})
        body = section.get("body", "")
        citation = fact["source_alias"] + ":" + ".".join(fact["source_path"])
        number = ""
        if "; trend " in body:
            tokens = body.removesuffix(".").split("; ")
            prefix = claim["label"] + " in " + fact["period"] + ": "
            body_ok = (
                len(tokens) == 3
                and tokens[0].startswith(prefix)
                and tokens[1:] == ["trend " + fact["trend"], "source " + citation]
                and body.endswith(".")
            )
            number = tokens[0][len(prefix) :] if body_ok else ""
        else:
            prefix, marker, tail = body.partition(" = ")
            number, trend_marker, tail = tail.partition(" (")
            body_ok = (
                marker == " = "
                and prefix == fact["period"] + ": " + claim["label"]
                and trend_marker == " ("
                and tail == fact["trend"] + ") [" + citation + "]."
            )
        try:
            parsed = None if number == "unknown" else json.loads(number)
            number_ok = (
                parsed is None
                if fact["value"] is None
                else type(parsed) in (int, float)
                and math.isfinite(parsed)
                and parsed == fact["value"]
            )
        except (ValueError, TypeError):
            number_ok = False
        metadata = section.get("claims")
        metadata_ok = metadata == [fact] and (
            fact["value"] is None or type(metadata[0]["value"]) in (int, float)
        )
        if not (body_ok and number_ok and metadata_ok):
            findings.append(
                {
                    "claim_id": claim["claim_id"],
                    "locator": [
                        *spec["path"],
                        "sections",
                        index,
                        "body" if not (body_ok and number_ok) else "claims",
                    ],
                    **refs[spec["path"][0]],
                    "description": "Actual body or metadata disagrees with source " + citation,
                    "evidence": [
                        {**source_refs[claim["source_alias"]], "locator": claim["value_path"]}
                    ],
                }
            )
    return findings


def _render(spec, prior, sources, refs, style, selected=None, defects=None):
    result = copy.deepcopy(prior)
    report = _field(result, spec["path"])
    positions = {s["section_id"]: i for i, s in enumerate(report["sections"])}
    for claim in spec["claims"]:
        if selected is not None and claim["claim_id"] not in selected:
            continue
        fact = _fact(claim, sources[claim["source_alias"]])
        body = _sentence(claim, fact, style)
        defect = (defects or {}).get(claim["claim_id"])
        if defect == "body_number":
            body = body.replace(": " + str(fact["value"]) + ";", ": 999;")
        elif defect == "body_period":
            body = body.replace(fact["period"], "1999FY")
        elif defect == "body_source":
            body = body.replace(fact["source_alias"] + ":", "wrong-source:")
        elif defect == "body_trend":
            body = body.replace("trend " + fact["trend"], "trend flat")
        section = {"section_id": claim["section_id"], "body": body, "claims": [fact]}
        if claim["section_id"] in positions:
            report["sections"][positions[claim["section_id"]]] = section
        else:
            report["sections"].append(section)
    result["sources"] = refs
    return result


def _open_issues(obs, wid):
    return [
        issue
        for iid, issue in obs.get("issues", {}).items()
        if issue["work_id"] == wid
        and obs["issue_views"][iid]["status"] == "open"
        and obs["issue_views"][iid]["applicability"] == "active"
    ]


class ReconciliationPolicy:
    kind = "reconciliation_table"

    def __init__(self, *, split=False, illegal_action_once=None):
        self.split, self.illegal_action_once = split, copy.deepcopy(illegal_action_once)
        self.config = {"split": split, "illegal_action_once": copy.deepcopy(illegal_action_once)}

    def decide(self, context):
        memory, rejected = _start(context)
        if rejected:
            return rejected
        if self.illegal_action_once and not memory.get("injected_illegal"):
            memory["injected_illegal"] = True
            return _act(
                memory, self.illegal_action_once["action"], self.illegal_action_once["arguments"]
            )
        obs = context["observation"]
        for wid, item in obs["work_items"].items():
            if item.get("owner_role") != obs["actor_id"] or not _checks(item, self.kind):
                continue
            if not item.get("is_current", True) or item["status"] in {"superseded", "cancelled"}:
                continue
            task = memory["tasks"].setdefault(wid, {"phase": "idle"})
            if item.get("submission_state") == "accepted" or item["status"] == "accepted":
                delivery = self._delivery(memory, task, obs, item, wid)
                if delivery:
                    return delivery
                continue
            if item.get("submission_state") == "pending" and task["phase"] == "idle":
                issues = _open_issues(obs, wid)
                eligible = [i for i in issues if i["issue_id"] not in task.get("responded", [])]
                if not eligible:
                    continue
                # Wait for a previous local response's institutional treatment.
                if any(i["issue_id"] in task.get("responded", []) for i in issues):
                    continue
                task["repair_issue"] = eligible[0]["issue_id"]
                task["phase"] = "prepare"
            if task["phase"] == "idle":
                task["phase"] = "prepare"
            decision = self._work(memory, task, obs, item, wid, _checks(item, self.kind)[0])
            if decision and decision["kind"] == "act":
                return decision
        return _wait(
            memory, "No currently actionable owned work; future public changes may create work"
        )

    def _delivery(self, memory, task, obs, item, wid):
        instructions = item.get("requirements", {}).get("public_delivery")
        if not instructions or not task.get("submitted"):
            return None
        sid = task["submitted"]
        decision = _cache(
            memory,
            task,
            wid,
            "accepted:" + sid,
            "inspect_submission",
            work_id=wid,
            submission_id=sid,
        )
        if decision:
            return decision
        submission = task["cache"]["accepted:" + sid]
        completed = task.get("delivery_steps", [])
        for oid, vid in submission["artifact_versions"].items():
            for recipient in instructions.get("recipients", []):
                key = "share:" + oid + ":" + vid + ":" + recipient["project_id"]
                if key not in completed:
                    return _act(
                        memory,
                        "share",
                        {
                            "object_id": oid,
                            "version_id": vid,
                            "target_project": recipient["project_id"],
                            "actor_ids": recipient["actor_ids"],
                            "follow_updates": True,
                        },
                        {"kind": "delivered", "work": wid, "key": key},
                    )
            key = "publish:" + oid + ":" + vid
            if instructions.get("publish", True) and key not in completed:
                targets = sorted(
                    {
                        item["project_id"],
                        *[r["project_id"] for r in instructions.get("recipients", [])],
                    }
                )
                return _act(
                    memory,
                    "publish",
                    {
                        "object_id": oid,
                        "version_id": vid,
                        "target_projects": targets,
                        "work_ids": [wid],
                    },
                    {"kind": "delivered", "work": wid, "key": key},
                )
        return None

    def _work(self, memory, task, obs, item, wid, spec):
        decision, sources, refs = _source_step(memory, task, obs, item, wid, spec)
        if decision:
            return decision
        alias = task.get("output_alias") or _output_alias(obs, item, self.kind)
        task["output_alias"] = alias
        if task["phase"] == "prepare":
            data = {
                "reconciliation": match_public_tables(
                    sources[spec["left_alias"]],
                    sources[spec["right_alias"]],
                    sources[spec["policy_alias"]],
                    spec["left_alias"],
                    spec["right_alias"],
                ),
                "sources": refs,
            }
            task["outputs"] = (
                {
                    alias: {"reconciliation": data["reconciliation"]},
                    alias + "_sources": {"sources": refs},
                }
                if self.split
                else {alias: data}
            )
            task["output_queue"] = list(task["outputs"])
            task["phase"] = "withdraw" if task.get("repair_issue") else "write"
        return self._write_submit(memory, task, obs, item, wid, refs)

    def _write_submit(self, memory, task, obs, item, wid, refs):
        if task["phase"] == "withdraw":
            return _act(
                memory,
                "withdraw",
                {
                    "work_id": wid,
                    "submission_id": item["pending_submission_id"],
                    "reason": "Repair one located issue under unchanged requirements",
                },
                {"kind": "stage", "work": wid, "phase": "write"},
            )
        if task["phase"] == "write":
            if task["output_queue"]:
                alias = task["output_queue"].pop(0)
                exists = alias in obs["workspaces"][item["project_id"]]
                arguments = {
                    "alias": alias,
                    "data": task["outputs"][alias],
                    "dependencies": list(refs.values()),
                    "work_id": wid,
                }
                if not exists:
                    arguments.update(
                        kind="json",
                        filename=alias + ".json",
                        deliverable_role="report"
                        if self.kind == "research_report"
                        else "reconciliation",
                    )
                return _act(memory, "write_object" if exists else "create_object", arguments)
            task["phase"] = "submit"
        if task["phase"] == "submit":
            return _act(
                memory,
                "submit",
                {"work_id": wid, "artifacts": list(task["outputs"])},
                {"kind": "submit", "work": wid},
            )
        if task["phase"] == "respond":
            iid = task["repair_issue"]
            return _act(
                memory,
                "respond_issue",
                {
                    "issue_id": iid,
                    "response_key": "public-response-" + task["submitted"],
                    "submission_id": task["submitted"],
                    "body": "Read the exact public sources and addressed the located assertion; compare current evidence.",
                    "evidence": list(refs.values()),
                },
                {"kind": "response", "work": wid, "issue": iid},
            )
        return None


class ReportAuthorPolicy(ReconciliationPolicy):
    kind = "research_report"

    def __init__(
        self, *, style="prose", split=False, initial_defects=None, illegal_action_once=None
    ):
        super().__init__(split=split, illegal_action_once=illegal_action_once)
        self.style, self.initial_defects = style, copy.deepcopy(initial_defects or {})
        self.config.update(style=style, initial_defects=copy.deepcopy(self.initial_defects))

    def _work(self, memory, task, obs, item, wid, spec):
        decision, sources, refs = _source_step(memory, task, obs, item, wid, spec)
        if decision:
            return decision
        alias = task.get("output_alias") or _output_alias(obs, item, self.kind)
        task["output_alias"] = alias
        if task["phase"] == "prepare":
            oid = obs["workspaces"][item["project_id"]].get(alias)
            if oid:
                version = obs["objects"][oid]["versions"][-1]
                key = "draft:" + oid + ":" + version
                decision = _cache(
                    memory,
                    task,
                    wid,
                    key,
                    "read_object",
                    object_id=oid,
                    version_id=version,
                    work_id=wid,
                )
                if decision:
                    return decision
                prior = task["cache"][key]["data"]
            else:
                prior = {"report": {"sections": []}}
            selected = None
            if task.get("repair_issue"):
                issue = obs["issues"][task["repair_issue"]]
                sections = _field(prior, spec["path"])["sections"]
                index = issue["locator"][len(spec["path"]) + 1]
                section_id = sections[index]["section_id"]
                selected = {c["claim_id"] for c in spec["claims"] if c["section_id"] == section_id}
                expected = _render(spec, prior, sources, refs, self.style, selected)
                if _field(expected, issue["locator"]) == _field(prior, issue["locator"]):
                    task["submitted"] = item["pending_submission_id"]
                    task["phase"] = "respond"
                    return self._write_submit(memory, task, obs, item, wid, refs)
            data = _render(
                spec,
                prior,
                sources,
                refs,
                self.style,
                selected,
                self.initial_defects if not task.get("ever_submitted") else None,
            )
            task["outputs"] = (
                {alias: {"report": data["report"]}, alias + "_sources": {"sources": refs}}
                if self.split
                else {alias: data}
            )
            task["output_queue"] = list(task["outputs"])
            task["phase"] = "withdraw" if task.get("repair_issue") else "write"
        return self._write_submit(memory, task, obs, item, wid, refs)


class ReviewerPolicy:
    def __init__(
        self, *, wrong_opinion_once=False, illegal_action_once=None, late_duplicate_once=False
    ):
        self.wrong_opinion_once = wrong_opinion_once
        self.late_duplicate_once = late_duplicate_once
        self.config = {
            "wrong_opinion_once": wrong_opinion_once,
            "late_duplicate_once": late_duplicate_once,
            "illegal_action_once": copy.deepcopy(illegal_action_once),
        }
        self.illegal_action_once = copy.deepcopy(illegal_action_once)

    def decide(self, context):
        memory, rejected = _start(context)
        if rejected:
            return rejected
        if self.illegal_action_once and not memory.get("injected_illegal"):
            memory["injected_illegal"] = True
            return _act(
                memory, self.illegal_action_once["action"], self.illegal_action_once["arguments"]
            )
        obs = context["observation"]
        for wid, item in obs["work_items"].items():
            if self.late_duplicate_once and item.get("submission_state") == "accepted":
                task = memory["tasks"].get(wid, {})
                old = next(
                    (
                        (sid, rows)
                        for sid, rows in task.get("reviewed_findings", {}).items()
                        if rows
                    ),
                    None,
                )
                if old and task.get("late_repeats", 0) < 2:
                    sid, rows = old
                    finding = rows[0]
                    task["late_repeats"] = task.get("late_repeats", 0) + 1
                    args = {k: v for k, v in finding.items() if k != "claim_id"}
                    args.update(
                        work_id=wid,
                        submission_id=sid,
                        issue_key="delayed-" + finding["claim_id"],
                        blocking=True,
                    )
                    return _act(memory, "raise_issue", args)
            if (
                item.get("submission_state") != "pending"
                or item.get("owner_role") == obs["actor_id"]
            ):
                continue
            specs = _checks(item, "research_report") or _checks(item, "reconciliation_table")
            if not specs:
                continue
            sid, spec = item["pending_submission_id"], specs[0]
            task = memory["tasks"].setdefault(wid, {})
            decision = _cache(
                memory,
                task,
                wid,
                "submission:" + sid,
                "inspect_submission",
                work_id=wid,
                submission_id=sid,
            )
            if decision:
                return decision
            submission = task["cache"]["submission:" + sid]
            document, artifact_refs = {}, {}
            for oid, vid in submission["artifact_versions"].items():
                key = "artifact:" + oid + ":" + vid
                decision = _cache(
                    memory,
                    task,
                    wid,
                    key,
                    "read_object",
                    object_id=oid,
                    version_id=vid,
                    work_id=wid,
                )
                if decision:
                    return decision
                for field, value in task["cache"][key]["data"].items():
                    if field in document and document[field] != value:
                        return _wait(memory, "Ambiguous submitted top-level fields")
                    document[field], artifact_refs[field] = (
                        value,
                        {"object_id": oid, "version_id": vid},
                    )
            decision, sources, refs = _source_step(
                memory, task, obs, item, wid, spec, submission["adoption_snapshot"]
            )
            if decision:
                return decision
            if spec["kind"] == "research_report":
                findings = inspect_report(spec, document, artifact_refs, sources, refs)
            else:
                expected = match_public_tables(
                    sources[spec["left_alias"]],
                    sources[spec["right_alias"]],
                    sources[spec["policy_alias"]],
                    spec["left_alias"],
                    spec["right_alias"],
                )
                findings = (
                    []
                    if document.get("reconciliation") == expected
                    else [
                        {
                            "claim_id": "reconciliation",
                            "locator": ["reconciliation"],
                            **artifact_refs["reconciliation"],
                            "description": "Submitted table differs from independent public matching",
                            "evidence": list(refs.values()),
                        }
                    ]
                )
            task.setdefault("reviewed_findings", {})[sid] = copy.deepcopy(findings)
            issues = _open_issues(obs, wid)
            for issue in issues:
                responses = [
                    r
                    for r in obs.get("issue_responses", {}).values()
                    if r["issue_id"] == issue["issue_id"] and r["submission_id"] == sid
                ]
                if not responses:
                    continue
                response = responses[-1]
                if any(f["locator"] == issue["locator"] for f in findings):
                    continue
                old_ref = issue["target"]
                key = "artifact:" + old_ref["object_id"] + ":" + old_ref["version_id"]
                decision = _cache(memory, task, wid, key, "read_object", **old_ref, work_id=wid)
                if decision:
                    return decision
                old = task["cache"][key]["data"]
                treatment = (
                    "accept_rebuttal"
                    if _field(old, issue["locator"]) == _field(document, issue["locator"])
                    else "accept_fix"
                )
                return _act(
                    memory,
                    "decide_issue",
                    {
                        "issue_id": issue["issue_id"],
                        "response_id": response["response_id"],
                        "decision_key": "public-decision-" + response["response_id"],
                        "decision": treatment,
                        "reason": "Independently read current and originally commented bytes plus exact source evidence",
                    },
                )
            for finding in findings:
                if any(i["locator"] == finding["locator"] for i in issues):
                    continue
                arguments = {k: v for k, v in finding.items() if k != "claim_id"}
                arguments.update(
                    work_id=wid,
                    submission_id=sid,
                    issue_key="public-review-" + finding["claim_id"],
                    blocking=True,
                )
                return _act(memory, "raise_issue", arguments)
            if (
                self.wrong_opinion_once
                and not memory.get("wrong_opinion_injected")
                and not findings
            ):
                if spec["kind"] != "research_report":
                    return _wait(memory, "Wrong-opinion injection only declared for finite report")
                memory["wrong_opinion_injected"] = True
                section = next(
                    i
                    for i, s in enumerate(_field(document, spec["path"])["sections"])
                    if s["section_id"] == spec["claims"][0]["section_id"]
                )
                return _act(
                    memory,
                    "raise_issue",
                    {
                        "work_id": wid,
                        "submission_id": sid,
                        "issue_key": "declared-wrong-opinion",
                        **artifact_refs[spec["path"][0]],
                        "locator": [*spec["path"], "sections", section, "body"],
                        "description": "Explicit experimental wrong opinion: reject a source-supported assertion",
                        "evidence": list(refs.values()),
                        "blocking": True,
                    },
                )
            if not findings and not issues:
                return _act(memory, "approve", {"work_id": wid, "submission_id": sid})
        return _wait(memory, "No pending review or unresolved response is currently actionable")
