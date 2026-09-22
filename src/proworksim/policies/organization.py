"""Configurable institutional powers; the operating organization is one policy."""


def operating_organization(roles):
    """Build the operating template's organization; powers follow configured roles."""
    ids = {role["role_id"] for role in roles}
    coordinator = next((r["role_id"] for r in roles if r.get("can_confirm_basis")), None)
    worker = next((r["role_id"] for r in roles if r.get("trainable")), None)
    reviewer = next((r["role_id"] for r in roles if r.get("can_approve")), None)
    positions = {
        "coordinator": coordinator,
        "worker": worker,
        "reviewer": reviewer,
        "client": "client" if "client" in ids else None,
    }
    grants = []

    def add(actor, power, subject):
        if actor:
            grants.append(
                {"actor_id": actor, "power": power, "subject": subject, "work_nodes": ["*"]}
            )

    add(coordinator, "confirm", "analytical_assumptions")
    add(coordinator, "revise_requirement", "*")
    add(coordinator, "restore_information", "*")
    add(coordinator, "view_work", "*")
    add(coordinator, "provide", "scope")
    add(coordinator, "provide", "evidence")
    add(reviewer, "approve", "deliverable")
    add(reviewer, "view_work", "*")
    add(worker, "view_work", "own_work")
    add(positions["client"], "provide", "audience")
    add(positions["client"], "provide", "brief")
    add(positions["client"], "confirm", "audience")
    return {
        "positions": positions,
        "grants": grants,
        "request_providers": {
            "scope": "coordinator",
            "audience": "client",
            "evidence": "coordinator",
        },
    }


def organization(state):
    configured = state.get("organization")
    if configured is not None:
        return configured
    if state.get("schema_version") not in (None, "0.1", "0.2", "0.3"):
        # An incomplete current world must not silently acquire legacy powers.
        return {"positions": {}, "grants": []}
    # Only historical worlds lack an explicit institution configuration.
    return operating_organization(state.get("roles", []))


def position(state, key):
    actor = organization(state).get("positions", {}).get(key)
    if not actor:
        raise ValueError(f"Organization position is not configured: {key}")
    if actor not in {r["role_id"] for r in state.get("roles", [])}:
        raise ValueError(f"Organization position refers to unknown actor: {key}")
    return actor


def request_provider(state, topic):
    key = organization(state).get("request_providers", {}).get(topic)
    if not key:
        raise ValueError(f"No request provider configured for {topic}")
    return position(state, key)


def authority(state, actor, power, subject, work_node=None):
    if actor not in {r["role_id"] for r in state.get("roles", [])}:
        return False
    for grant in organization(state).get("grants", []):
        if grant.get("actor_id") != actor or grant.get("power") not in (power, "*"):
            continue
        if grant.get("subject") not in (subject, "*"):
            continue
        nodes = grant.get("work_nodes", ["*"])
        if "*" in nodes or (work_node is not None and work_node in nodes):
            return True
    return False


def require_authority(state, actor, power, subject, work_node=None):
    if not authority(state, actor, power, subject, work_node):
        raise ValueError(f"Actor lacks institutional power: {power} ({subject})")
