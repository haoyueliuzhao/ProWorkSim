"""Versioned centralized critic inputs from strictly past public observations.

This finite 30-value schema uses the world's actual status vocabulary. Actor
inputs, business values, evaluator truth and future states are never read here.
"""

FEATURE_VERSION = "past-public-structure-v0.13"
FEATURE_DIMENSION = 30
DEFAULT_MEMBERS = ("provider", "implementer", "reviewer")
STATUS_BINS = ("open", "in_progress", "in_review", "accepted", "blocked")
WORLD_STATUSES = frozenset(
    (*STATUS_BINS, "revision_required", "superseded", "cancelled", "waiting_dependencies")
)


def feature_names(member_ids=DEFAULT_MEMBERS):
    members = tuple(member_ids)
    if (
        len(members) != 3
        or len(set(members)) != 3
        or any(not isinstance(m, str) or not m for m in members)
    ):
        raise ValueError(
            "The v0.13 critic schema requires three distinct ordered member identities"
        )
    fields = (
        "visible_work_count",
        *("work_status_" + status for status in STATUS_BINS),
        "workspace_alias_count",
        "tool_ok_count",
        "tool_refusal_count",
    )
    return [member + "." + field for member in members for field in fields] + [
        "acting_member." + member for member in members
    ]


def past_features(events, before_sequence, member_id, member_ids=DEFAULT_MEMBERS):
    names = feature_names(member_ids)
    members = tuple(member_ids)
    if member_id not in members or type(before_sequence) is not int or before_sequence < 0:
        raise ValueError(
            "A declared acting member and a nonnegative decision-start sequence are required"
        )
    latest, counts, refs = {}, {member: [0, 0] for member in members}, {}
    previous = -1
    for event in events:
        sequence = event["sequence"]
        if type(sequence) is not int or sequence < 0:
            raise ValueError("Experience sequence must be an original nonnegative integer")
        if sequence >= before_sequence:
            break
        if sequence <= previous:
            raise ValueError("Past experience must retain its original increasing order")
        previous = sequence
        member = event.get("worker_id")
        if member not in counts:
            continue
        if event["kind"] == "public_observation":
            latest[member], refs[member] = event["payload"], sequence
        elif event["kind"] == "tool_call":
            ok = event["payload"].get("response", {}).get("ok")
            if type(ok) is bool:
                counts[member][0 if ok else 1] += 1
    features, unbinned = [], {}
    for member in members:
        observation = latest.get(member, {})
        works = observation.get("work_items", {})
        if not isinstance(works, dict) or any(not isinstance(w, dict) for w in works.values()):
            raise ValueError("Public work observations must be a mapping of work records")
        statuses = [work.get("status") for work in works.values()]
        if any(status not in WORLD_STATUSES for status in statuses):
            raise ValueError(
                "Unknown public work status; revise the versioned critic schema explicitly"
            )
        features.extend(
            [len(works) / 10.0] + [statuses.count(status) / 10.0 for status in STATUS_BINS]
        )
        workspaces = observation.get("workspaces", {})
        if not isinstance(workspaces, dict):
            raise ValueError("Public workspaces must be a mapping")
        features.append(
            sum(len(value) for value in workspaces.values() if isinstance(value, dict)) / 100.0
        )
        features.extend(value / 100.0 for value in counts[member])
        unbinned[member] = {
            status: statuses.count(status)
            for status in sorted(WORLD_STATUSES - set(STATUS_BINS))
            if status in statuses
        }
    features.extend(float(member == member_id) for member in members)
    return features, {
        "version": FEATURE_VERSION,
        "dimension": FEATURE_DIMENSION,
        "member_order": list(members),
        "feature_names": names,
        "before_event_sequence": before_sequence,
        "latest_observation_sequences": refs,
        "members_without_past_observation": [member for member in members if member not in latest],
        "recognized_unbinned_work_status_counts": unbinned,
        "scope": "Three-role centralized actually observed prefix; cut at model_call started sequence. Inactive members have zero observed counts. Five status bins are exact public states; other known states are reported, never renamed. No content values, future observations, terminal rewards or evaluator truth.",
    }
