"""Finite exact-version publication facts, independent of files and notifications.

The runner owns atomic persistence; the adapter owns subscription sharing and
message delivery. These functions never advance an artifact's current version,
change adoption bindings, grant readers, or recalculate a downstream product.
"""

import copy
import hashlib
import json

from ..policies.organization import require_authority


PUBLICATION_POLICIES = frozenset({"explicit", "implicit_write"})


def effective_policy(state, artifact):
    """Resolve declared object/project/world policy, with old-state fallback.

    A missing field is the recorded v0.6 write-as-publication convention, not an
    invented retroactive release history. New world constructors set explicit.
    """
    project = state.get("projects", {}).get(artifact.get("project_id"), {})
    policy = artifact.get(
        "publication_policy",
        project.get("publication_policy", state.get("publication_policy", "implicit_write")),
    )
    if policy not in PUBLICATION_POLICIES:
        raise ValueError("Unknown publication policy")
    return policy


def latest_published_version(state, object_id, project_id):
    """Latest release in the consuming project's declared publication scope.

    With no project context, only world-owned releases can be observed. Sharing
    and access are separate checks; a release alone is never a read grant.
    """
    for release in reversed(state.get("releases", [])):
        if release["object_id"] != object_id:
            continue
        if project_id is None:
            if release["source_project"] is None:
                return release["version_id"]
        elif project_id in release["scope"]["target_projects"]:
            return release["version_id"]
    return None


def _arguments(state, actor, source_project, object_id, version_id, target_projects, work_ids):
    if actor not in state.get("actors", {}):
        raise ValueError("Unknown publication actor")
    artifact = state.get("artifacts", {}).get(object_id)
    if artifact is None or artifact.get("project_id") != source_project:
        raise ValueError("Publication object escapes the bound source project")
    if source_project is not None:
        project = state.get("projects", {}).get(source_project)
        if project is None or actor not in project.get("participants", []):
            raise ValueError("Publication actor is not a source project participant")
    version = artifact.get("versions", {}).get(version_id)
    if version is None or version.get("logical_time", state["clock"]) > state["clock"]:
        raise ValueError("Publication requires an existing exact object version")
    if not isinstance(target_projects, list) or any(
        not isinstance(pid, str) or pid not in state.get("projects", {}) for pid in target_projects
    ):
        raise ValueError("Publication targets must be existing project identities")
    if work_ids is None:
        work_ids = []
    if not isinstance(work_ids, list) or any(not isinstance(wid, str) for wid in work_ids):
        raise ValueError("Publication work scope must be a list of work identities")
    for wid in work_ids:
        item = state.get("work_items", {}).get(wid)
        if item is None or item.get("project_id") != source_project:
            raise ValueError("Publication work escapes the source project")
    scope = {"target_projects": sorted(set(target_projects)), "work_ids": sorted(set(work_ids))}
    return artifact, scope


def _record(state, actor, source_project, object_id, version_id, scope, policy):
    identity = {
        "source_project": source_project,
        "object_id": object_id,
        "version_id": version_id,
        "scope": scope,
    }
    for release in state.get("releases", []):
        if all(release.get(key) == value for key, value in identity.items()):
            return {"release": copy.deepcopy(release), "created": False}
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    release = {
        "release_id": "release-" + digest[:24],
        **identity,
        "actor_id": actor,
        "at": state["clock"],
        "policy": policy,
    }
    state.setdefault("releases", []).append(copy.deepcopy(release))
    return {"release": release, "created": True}


def publish_release(
    state, actor, source_project, object_id, version_id, target_projects, work_ids=None
):
    """Record an authorized release, idempotent by exact version and scope.

    Every supplied source work must be covered. An omitted work scope requires
    an object-level grant whose work scope is unrestricted; it cannot widen a
    narrow work grant. The caller also enforces its file/write access policy.
    """
    _, scope = _arguments(
        state, actor, source_project, object_id, version_id, target_projects, work_ids
    )
    for wid in scope["work_ids"] or [None]:
        item = state.get("work_items", {}).get(wid, {})
        require_authority(
            state,
            actor,
            "publish",
            "artifact",
            item.get("node_id", wid),
            project_id=source_project,
            object_id=object_id,
        )
    return _record(state, actor, source_project, object_id, version_id, scope, "explicit")


def record_implicit_release(
    state, actor, source_project, object_id, version_id, target_projects, work_ids=None
):
    """Record the explicitly selected write-as-publication policy's consequence.

    This is an internal write-completion helper, not a callable employee tool.
    It requires the effective implicit policy and the object's write ACL. It
    cannot be used to publish an explicit-policy object without publication power.
    """
    artifact, scope = _arguments(
        state, actor, source_project, object_id, version_id, target_projects, work_ids
    )
    if effective_policy(state, artifact) != "implicit_write":
        raise ValueError("Implicit release is forbidden by the effective publication policy")
    if actor not in artifact.get("writers", []):
        raise ValueError("Implicit release requires the exact object's writer")
    return _record(state, actor, source_project, object_id, version_id, scope, "implicit_write")
