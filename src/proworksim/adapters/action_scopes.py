"""Allowed object effects for the currently supported tool and event adapters."""

from proworksim.core.transitions import ActionFrame

PROJECTIONS = (
    "freshness",
    "data_freshness",
    "basis_applicability",
    "basis_applicability_by_work",
    "basis_applicability_relations",
    "freshness_basis",
    "possibly_stale",
)


def projections(state):
    return tuple(("artifacts", aid, field) for aid in state["artifacts"] for field in PROJECTIONS)


def tool_frame(state, actor, action, args):
    paths = []
    wid = args.get("work_item_id")
    aid = args.get("artifact_id", "model")
    if action in {"read_file", "sheet_read", "search", "mail_read"}:
        paths.append(("knowledge", actor))
    if action in {"write_file", "sheet_update", "sheet_recalculate"}:
        paths += [("artifacts", aid), ("knowledge", actor)]
        paths += [
            ("work_items", key)
            for key, item in state["work_items"].items()
            if aid in item["deliverables"]
        ]
    if action == "mail_send":
        paths += [("messages",), ("requests",), ("events",)]
        bid = args.get("blocker_id")
        if bid:
            paths += [
                ("blockers", bid),
                (
                    "condition_specs",
                    state.get("blockers", {}).get(bid, {}).get("condition_id", bid),
                ),
            ]
    if action in {"submit", "withdraw", "block_work"} and wid:
        paths.append(("work_items", wid))
    if action == "submit":
        paths.append(("events",))
    if action == "block_work":
        paths += [("blockers",), ("condition_specs",)]
    if action == "approve":
        # Approval may activate downstream obligations via workflow adaptation.
        paths += [("work_items",), ("events",), ("fired_rules",), ("open_releases",)]
        if wid in state["work_items"]:
            paths += [
                ("artifacts", a)
                for a in state["work_items"][wid]["deliverables"]
                if a in state["artifacts"]
            ]
    if action == "revise_requirements":
        # Scope selection is a domain policy; the generic revision helper itself
        # is tested against explicit targets and cannot modify artifact bytes.
        paths += [("artifacts", "basis"), ("artifacts", "scope")]
        paths += [
            (key,)
            for key in (
                "attestations",
                "basis_approvals",
                "basis_by_scenario",
                "basis_visibility",
                "access_grants",
                "requirement_events",
                "work_items",
                "work_replacements",
                "blockers",
                "condition_specs",
                "events",
                "fired_rules",
                "messages",
                "interactions",
            )
        ]
    if action == "restore_information":
        paths += [
            ("provider_availability",),
            ("messages",),
            ("information_restorations",),
            ("future_opportunities",),
        ]
        for cid in args.get("condition_ids", []):
            paths.append(("condition_specs", cid))
            condition = state.get("condition_specs", {}).get(cid, {})
            if condition.get("work_item_id"):
                paths.append(("work_items", condition["work_item_id"]))
    if action == "wait":
        paths.append(("clock",))
    return ActionFrame(
        action, tuple(paths), projections(state), ("required_basis",), ("basis_approvals",)
    )


def reply_frame(state, request):
    wid = request["work_item_id"]
    paths = [("messages",), ("requests", request["request_id"]), ("interactions",)]
    paths += [("knowledge", request["requested_role"]), ("work_items", wid)]
    for bid, blocker in state.get("blockers", {}).items():
        if blocker.get("request_id") == request["request_id"]:
            paths += [
                ("blockers", bid),
                (
                    "condition_specs",
                    state.get("blockers", {}).get(bid, {}).get("condition_id", bid),
                ),
            ]
    reference = request.get("evidence_reference") or request.get("basis_ref")
    if reference:
        aid, vid = reference["artifact_id"], reference["version_id"]
        paths.append(("artifacts", aid, "version_readers", vid))
    paths += [("basis_visibility",)]
    paths += [
        ("access_grants",),
        ("communication_grants",),
        ("condition_responses",),
        ("raw_condition_responses",),
    ]
    return ActionFrame(
        "Reply", tuple(paths), projections(state), ("required_basis",), ("basis_approvals",)
    )
