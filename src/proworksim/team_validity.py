"""Finite team validity from readable world facts and independently caught ports.

This is a work-contract gate, not a reward threshold. It validates actual reads,
manual handoffs, submitted adoptions, and reviewer evidence before every approval.
"""

import copy
from pathlib import Path

from .episode import assess_historical_episode
from .member_views import member_view
from .storage import Store, digest, read_json
from .team_rollout import work_validity


def _ref(value):
    if not isinstance(value, dict):
        return None
    a, v = value.get("object_id", value.get("artifact_id")), value.get("version_id")
    return (a, v) if isinstance(a, str) and isinstance(v, str) else None


def assess_team_validity(episode, *, members, independent_capture, spec, assessment_spec=None):
    required = {
        "spec_id",
        "project_id",
        "work_node",
        "implementer",
        "reviewer",
        "required_handoff_routes",
        "required_direct_reads",
        "allow_rejected_actions",
        "allow_repair",
        "blocked_outcome",
    }
    if not isinstance(spec, dict) or set(spec) != required:
        raise ValueError("Team validity specification must predeclare the finite evidence contract")
    if spec["blocked_outcome"] != "unknown":
        raise ValueError("This finite validator only declares unknown blocked outcomes")
    root = Path(episode)
    if root.name == "manifest.json":
        root = root.parent
    manifest = read_json(root / "manifest.json")
    assessment = assess_historical_episode(root, **(assessment_spec or {}))
    checks = []

    def add(dimension, value, reason, evidence):
        checks.append(
            {"dimension": dimension, "value": value, "reason": reason, "evidence": evidence}
        )

    manifest_ref = {"manifest_sha256": digest((root / "manifest.json").read_bytes())}
    if assessment.get("assessment_execution", {}).get("status") != "complete":
        add("record", None, "Historical evidence cannot be reliably evaluated", manifest_ref)
        return work_validity(checks, spec_id=spec["spec_id"])
    state = read_json(root / "end/control/state.json")
    history = read_json(root / manifest["experience"]["path"])["events"]
    start, end = manifest["experience"]["start"], manifest["experience"]["end"]
    events = history[start:end]
    capture_ok = True if isinstance(independent_capture, dict) else None
    for member_id in members:
        actual = (
            independent_capture.get(member_id) if isinstance(independent_capture, dict) else None
        )
        if actual is None:
            capture_ok = None if capture_ok is not False else False
            continue
        retained = []
        for event in events:
            if event.get("worker_id") != member_id or event["kind"] not in {
                "public_tools",
                "public_observation",
                "tool_call",
            }:
                continue
            payload = copy.deepcopy(event["payload"])
            if event["kind"] == "tool_call":
                for key in ("model_call_id", "model_tool_call_id", "decision_id", "opportunity_id"):
                    payload.pop(key, None)
            retained.append({"kind": event["kind"], "payload": payload})
        if actual != retained:
            capture_ok = False
    add(
        "record",
        capture_ok,
        "Independent actual public-port capture matches retained episode events",
        {**manifest_ref, "event_interval": [start, end]},
    )
    calls = [
        event
        for event in events
        if event["kind"] == "tool_call" and event.get("worker_id") in members
    ]
    # Public-port capture alone does not certify a model's HTTP trajectory.
    # Token availability is intentionally excluded from semantic integrity.
    for member_id, member in members.items():
        if member["origin"] != "target_model":
            continue
        view = member_view(
            {
                "rollout_id": manifest["episode_id"],
                "window": {},
                "manifest": manifest,
                "members": members,
                "events": events,
            },
            member_id,
        )
        conflicts = [
            row
            for row in view["diagnostics"]
            if row["reason"]
            in {
                "transport_response_or_request_link_mismatch",
                "context_selection_request_mismatch",
                "duplicate_model_call_identity",
                "orphan_actual_model_record",
            }
        ]
        required_decisions = [row for row in view["decisions"] if row["actor_required"]]
        unlinked_actions = [
            event["sequence"]
            for event in calls
            if event["worker_id"] == member_id and not event["payload"].get("model_call_id")
        ]
        semantic_integrity = (
            False
            if conflicts
            else None
            if unlinked_actions
            or any(not row["semantic_recoverable"] for row in required_decisions)
            else True
        )
        add(
            "record",
            semantic_integrity,
            "All observed model generations have complete matching actual requests/responses; tokens are a separate actor gate",
            {
                "member_id": member_id,
                "conflicts": conflicts,
                "unlinked_action_sequences": unlinked_actions,
                "required_decisions": [row["call_id"] for row in required_decisions],
            },
        )
    successful = [
        event for event in calls if event["payload"].get("response", {}).get("ok") is True
    ]
    permission = True
    receipt_refs = []
    for event in calls:
        response = event["payload"].get("response", {})
        commit = state.get("operation_commits", {}).get(response.get("command_id"))
        if commit is None:
            permission = None if permission is not False else False
            continue
        receipt_refs.append({"sequence": event["sequence"], "command_id": response["command_id"]})
        if (
            commit.get("bound_actor") != members[event["worker_id"]]["actor_id"]
            or commit.get("public_result") != response
        ):
            permission = False
        if response.get("ok") is False:
            if not spec["allow_rejected_actions"] or commit.get("receipt", {}).get("apply_delta"):
                permission = False
    if not spec["allow_repair"] and any(
        event["payload"]["action"] == "withdraw" for event in successful
    ):
        permission = False
    add(
        "permission",
        permission,
        "Actual scoped world receipts agree; allowed refusals have no apply-phase business mutation",
        {"receipts": receipt_refs},
    )
    reads = []
    for event in successful:
        if event["payload"]["action"] == "read_object":
            ref = _ref(event["payload"]["response"]["result"].get("reference"))
            if ref:
                reads.append((event, ref))

    def presented_before(member_id, evidence, action):
        if members[member_id]["origin"] != "target_model":
            return True
        call_id = action["payload"].get("model_call_id")
        attempts = [
            event["payload"]
            for event in events
            if event.get("worker_id") == member_id
            and event["kind"] == "model_attempt"
            and event["payload"].get("call_id") == call_id
            and event["payload"].get("stage") == "finished"
            and event["payload"].get("status") == "success"
        ]
        if len(attempts) != 1:
            return None
        result_messages = [
            event["payload"]["message"]
            for event in events
            if event.get("worker_id") == member_id
            and event["kind"] == "model_tool_result"
            and event["payload"].get("call_id") == evidence["payload"].get("model_call_id")
        ]
        return any(message in attempts[0]["request"]["messages"] for message in result_messages)

    def read_before(member_id, ref, action):
        matches = [
            event
            for event, seen in reads
            if event["worker_id"] == member_id
            and seen == ref
            and event["sequence"] < action["sequence"]
        ]
        if not matches:
            return False
        values = [presented_before(member_id, evidence, action) for evidence in matches]
        return True if True in values else None if None in values else False

    team_items = [
        item for item in state["work_items"].values() if item["node_id"] == spec["work_node"]
    ]
    routes = {
        route["route_id"]: route
        for route in state["projects"][spec["project_id"]]["information_routes"]
    }
    team_ids = {item["work_item_id"] for item in team_items}
    selected_ids = team_ids.intersection(manifest["selected_work_ids"])
    fixed_sids = {manifest["fixed_deliveries"][wid]["submission_id"] for wid in selected_ids}

    def scoped_work(args):
        raw = args.get("work_id", "")
        return raw if raw in team_ids else spec["project_id"] + "::" + raw

    approved_sids = {
        event["payload"]["arguments"].get("submission_id")
        for event in successful
        if event["payload"]["action"] == "approve"
        and scoped_work(event["payload"].get("arguments", {})) in team_ids
    }
    for route_id in spec["required_handoff_routes"]:
        route = routes.get(route_id)
        matches = [
            event
            for event in successful
            if event["payload"]["action"] == "handoff_information"
            and event["payload"]["arguments"].get("route_id") == route_id
            and event["payload"]["arguments"].get("status", "delivered") == "delivered"
        ]
        good = False
        for event in matches:
            ref = _ref(event["payload"]["arguments"].get("reference"))
            hid = event["payload"]["response"]["result"].get("handoff_id")
            fact = state.get("handoffs", {}).get(hid, {})
            if (
                route
                and ref
                and fact.get("origin") == "member_action"
                and fact.get("status") == "delivered"
                and fact.get("sender") == members[event["worker_id"]]["actor_id"]
                and fact.get("route_id") == route_id
                and _ref(fact.get("reference")) == ref
                and fact.get("work_item_id") in selected_ids
                and any(
                    delivered.get("kind") == "environment_event"
                    and delivered["payload"].get("event_id") == fact.get("event_id")
                    and delivered["payload"].get("outcome") == "applied"
                    and delivered["payload"].get("payload", {}).get("handoff_id") == hid
                    for delivered in events
                )
            ):
                value = read_before(event["worker_id"], ref, event)
                good = (
                    True if value is True else None if value is None and good is not True else good
                )
        if (
            good is False
            and spec["blocked_outcome"] == "unknown"
            and any(
                event["payload"]["action"] == "handoff_information"
                and event["payload"]["arguments"].get("route_id") == route_id
                and event["payload"]["arguments"].get("status") == "unavailable"
                and state.get("handoffs", {})
                .get(event["payload"]["response"]["result"].get("handoff_id"), {})
                .get("status")
                == "delivered"
                for event in successful
            )
        ):
            # A real unavailable response is retained as such, never relabeled
            # a delivered business basis. This version does not certify the
            # sufficiency of all possible lawful blocked-exit contracts.
            good = None
        add(
            "basis",
            good,
            "Required manual handoff chose actually read evidence and was actually delivered",
            {"route_id": route_id, "handoff_sequences": [event["sequence"] for event in matches]},
        )
    for event in successful:
        action, args = event["payload"]["action"], event["payload"].get("arguments", {})
        if action not in {"submit", "approve"} or scoped_work(args) not in team_ids:
            continue
        item = state["work_items"][scoped_work(args)]
        sid = (
            args.get("submission_id")
            if action == "approve"
            else event["payload"]["response"]["result"]["submission_id"]
        )
        submission = next(sub for sub in item["submissions"] if sub["submission_id"] == sid)
        if action == "submit":
            # A discarded, never-approved draft may be repaired under the
            # declared contract. A past approval cannot be erased by repair.
            if spec["allow_repair"] and sid not in fixed_sids | approved_sids:
                continue
            aliases = {
                source["alias"]
                for check in submission["requirement_snapshot"]["deliverable_contract"][
                    "content_checks"
                ]
                for source in check.get("sources", [])
            }
            for alias in aliases:
                adopted = submission.get("adoption_snapshot", {}).get(
                    item["work_item_id"] + "::" + alias
                )
                value = read_before(event["worker_id"], _ref(adopted), event) if adopted else False
                add(
                    "basis",
                    value,
                    "Submission source was actually read and adopted for this exact work edition",
                    {"submission_id": sid, "alias": alias, "action_sequence": event["sequence"]},
                )
        else:
            reviewer = spec["reviewer"]
            inspections = [
                prior
                for prior in successful
                if prior["worker_id"] == reviewer
                and prior["sequence"] < event["sequence"]
                and prior["payload"]["action"] == "inspect_submission"
                and prior["payload"]["arguments"].get("submission_id") == sid
            ]
            presented = [presented_before(reviewer, prior, event) for prior in inspections]
            inspected = True if True in presented else None if None in presented else False
            values = [inspected, event["worker_id"] == reviewer] + [
                read_before(reviewer, (aid, vid), event)
                for aid, vid in submission["artifact_versions"].items()
            ]
            for required_read in spec["required_direct_reads"]:
                if required_read["member_id"] == reviewer:
                    aid = state["workspaces"][spec["project_id"]].get(required_read["alias"])
                    if not aid:
                        values.append(False)
                    else:
                        requirements = submission["requirement_snapshot"].get("requirements", {})
                        audit_alias = requirements.get("review_contract", {}).get("audit_alias")
                        declared = required_read.get("version_id")
                        # Select observed reads, never an end-current version
                        # that may have appeared after the review.
                        candidates = {
                            ref[1]
                            for read, ref in reads
                            if read["worker_id"] == reviewer
                            and read["sequence"] < event["sequence"]
                            and ref[0] == aid
                            and (declared is None or ref[1] == declared)
                        }
                        audited = []
                        for version in candidates:
                            available = read_before(reviewer, (aid, version), event)
                            if required_read["alias"] == audit_alias:
                                try:
                                    data = read_json(
                                        Store(root / "end").version_path(
                                            state["artifacts"][aid], version
                                        )
                                    )
                                except (OSError, ValueError):
                                    applicable = None
                                else:
                                    applicable = (
                                        isinstance(data, dict)
                                        and data.get("edition") == "approved"
                                        and data.get("period")
                                        == requirements.get("reporting_period")
                                    )
                                available = (
                                    False
                                    if available is False or applicable is False
                                    else None
                                    if available is None or applicable is None
                                    else True
                                )
                            audited.append(available)
                        values.append(
                            True if True in audited else None if None in audited else False
                        )

            value = (
                False
                if any(item is False for item in values)
                else None
                if any(item is None for item in values)
                else True
            )
            add(
                "basis",
                value,
                "Every successful review used the exact fixed submission and declared independent basis",
                {"submission_id": sid, "approval_sequence": event["sequence"]},
            )
    relevant = [
        row
        for row in assessment["content_quality"]["submissions"]
        if row["work_id"] in selected_ids
    ]
    statuses = [row["evaluation"]["status"] for row in relevant]
    accepted = bool(selected_ids) and all(
        (manifest["fixed_deliveries"][wid].get("review") or {}).get("decision") == "accepted"
        and manifest["fixed_deliveries"][wid]["submission_id"] in approved_sids
        for wid in selected_ids
    )
    delivered = accepted and bool(statuses) and all(status == "pass" for status in statuses)
    delivery = (
        True
        if delivered
        else False
        if any(status in {"content_failure", "structure_failure"} for status in statuses)
        or any(not state["work_items"][wid]["submissions"] for wid in selected_ids)
        or (bool(statuses) and all(status == "pass" for status in statuses) and not accepted)
        else None
    )
    # A blocked exit is never silently admitted as a completed positive. The
    # separate declared blocked contract is conservatively unassessed here.
    if (
        spec["blocked_outcome"] == "unknown"
        and any(
            event["payload"]["action"] == "handoff_information"
            and event["payload"]["arguments"].get("status") == "unavailable"
            and state.get("handoffs", {})
            .get(event["payload"]["response"]["result"].get("handoff_id"), {})
            .get("status")
            == "delivered"
            for event in successful
        )
        and not any(item["submissions"] for item in team_items)
    ):
        delivery = None
    add(
        "delivery",
        delivery,
        "Finite independent end-delivery contract, separate from institutional acceptance",
        {
            "work_ids": [row["work_id"] for row in relevant],
            "statuses": statuses,
            "accepted_within_episode": accepted,
        },
    )
    return work_validity(checks, spec_id=spec["spec_id"])
