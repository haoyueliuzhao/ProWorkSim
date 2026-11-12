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


def authority(state, actor, power, subject, work_node=None, project_id=None, object_id=None):
    """Check explicit powers, with strict project/work/object scope in World Core.

    v0.5 worlds retain their recorded single-project interpretation. In v0.6,
    omitting context cannot turn a project grant into a world-wide grant. A full
    world work identifier can resolve its project without trusting a local name.
    """
    scoped_world = "projects" in state
    actors = (
        state.get("actors", {})
        if scoped_world
        else {role["role_id"]: role for role in state.get("roles", [])}
    )
    if actor not in actors:
        return False
    if scoped_world:
        inferred = {
            item.get("project_id")
            for key, item in state.get("work_items", {}).items()
            if work_node is not None and (key == work_node or item.get("node_id") == work_node)
        }
        if len(inferred) > 1 or (inferred and project_id not in (None, next(iter(inferred)))):
            return False
        if inferred:
            project_id = next(iter(inferred))
        if work_node is not None and not inferred:
            return False
        if project_id is not None and project_id not in state["projects"]:
            return False
        if object_id is not None and object_id not in state.get("artifacts", {}):
            return False
        if (
            object_id is not None
            and project_id is not None
            and object_id not in state.get("workspaces", {}).get(project_id, {}).values()
        ):
            return False
    for grant in organization(state).get("grants", []):
        if grant.get("actor_id") != actor or grant.get("power") not in (power, "*"):
            continue
        if grant.get("subject") not in (subject, "*"):
            continue
        if scoped_world:
            if grant.get("scope") == "world":
                if project_id is not None or work_node is not None:
                    continue
            elif not project_id or grant.get("project_id") != project_id:
                continue
            objects = grant.get("object_ids", ["*"])
            if "*" not in objects and (object_id is None or object_id not in objects):
                continue
        nodes = grant.get("work_nodes", ["*"])
        if "*" in nodes or (work_node is not None and work_node in nodes):
            return True
    return False


def require_authority(
    state, actor, power, subject, work_node=None, project_id=None, object_id=None
):
    if not authority(state, actor, power, subject, work_node, project_id, object_id):
        raise ValueError(f"Actor lacks institutional power: {power} ({subject})")
