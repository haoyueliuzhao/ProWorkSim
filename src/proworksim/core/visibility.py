"""Version-scoped technical access. Access grants do not imply observation or use."""

from .references import VersionRef, resolve_version


def visible_version(artifact, actor, clock, requested=None):
    candidates = [requested] if requested is not None else reversed(list(artifact["versions"]))
    for version_id in candidates:
        version = artifact["versions"].get(version_id)
        if version is None or version["logical_time"] > clock:
            continue
        if actor in artifact.get("readers", ()) or actor in artifact.get("version_readers", {}).get(
            version_id, ()
        ):
            return version_id
    return None


def grant_version(state, object_id, version_id, actor, reason_ref):
    """Grant exactly one existing version, recording only the first identical grant."""
    if actor not in {role["role_id"] for role in state.get("roles", [])}:
        raise ValueError("Cannot grant access to an unknown actor")
    resolve_version(state, VersionRef(object_id, version_id))
    artifact = state["artifacts"][object_id]
    if actor in artifact.get("readers", []):
        return False
    readers = artifact.setdefault("version_readers", {}).setdefault(version_id, [])
    if actor in readers:
        return False
    readers.append(actor)
    state.setdefault("access_grants", []).append(
        {
            "actor_id": actor,
            "object_id": object_id,
            "version_id": version_id,
            "reason_ref": reason_ref,
            "at": state["clock"],
        }
    )
    return True


def project_fields(value, private_fields):
    """Project nested business records without changing their canonical history."""
    if isinstance(value, dict):
        return {
            key: project_fields(item, private_fields)
            for key, item in value.items()
            if key not in private_fields
        }
    if isinstance(value, list):
        return [project_fields(item, private_fields) for item in value]
    return value
