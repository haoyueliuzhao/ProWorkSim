"""Work-scoped adoption facts, independent of workspace aliases and file bytes.

The runtime checks readable object versions and institutional authority before
recording these facts. This module enforces the declared policy and exact work
edition; it never follows work replacements or changes historical bindings.
"""

import copy


ADOPTION_POLICIES = frozenset({"fixed", "current_applicable", "current_published"})


def binding_key(work_id, alias):
    if not isinstance(work_id, str) or not work_id or not isinstance(alias, str) or not alias:
        raise ValueError("Adoption requires an exact work identity and alias")
    return work_id + "::" + alias


def allowed_policies(item, alias):
    """Resolve a declared input policy without inventing an evaluator policy.

    ``requirements.input_policy`` supplies an optional common default;
    ``requirements.input_policies[alias]`` overrides it for one alias. Each may
    be a policy string or a nonempty list of explicitly permitted policies. An
    absent declaration permits all supported policies, preserving the choice
    itself as a submission fact.
    """
    requirements = item.get("requirements", {})
    if not isinstance(requirements, dict):
        raise ValueError("Work requirements must be an object")
    by_alias = requirements.get("input_policies", {})
    if not isinstance(by_alias, dict) or any(
        not isinstance(key, str) or not key for key in by_alias
    ):
        raise ValueError("Input policies must map aliases to declared policies")
    if alias not in by_alias and "input_policy" not in requirements:
        return ADOPTION_POLICIES
    declaration = by_alias.get(alias, requirements.get("input_policy"))
    if isinstance(declaration, str):
        declaration = [declaration]
    if (
        not isinstance(declaration, list)
        or not declaration
        or any(not isinstance(policy, str) for policy in declaration)
        or len(set(declaration)) != len(declaration)
        or not set(declaration) <= ADOPTION_POLICIES
    ):
        raise ValueError("Declared input policy must be supported or an explicit allowed list")
    return frozenset(declaration)


def require_policy(item, alias, policy):
    if not isinstance(policy, str) or policy not in ADOPTION_POLICIES:
        raise ValueError("Unknown adoption policy")
    if policy not in allowed_policies(item, alias):
        raise ValueError("Adoption policy does not satisfy this work's input contract")


def validate_policy_contract(item):
    """Validate all policy declarations at installation or requirement revision."""
    allowed_policies(item, "")
    requirements = item.get("requirements", {})
    for alias in requirements.get("input_policies", {}):
        allowed_policies(item, alias)
    declared_version(item, "")
    for alias in requirements.get("input_versions", {}):
        declared_version(item, alias)


def declared_version(item, alias):
    """Return an optional explicitly declared exact version for fixed adoption."""
    requirements = item.get("requirements", {})
    by_alias = requirements.get("input_versions", {})
    if not isinstance(by_alias, dict) or any(
        not isinstance(key, str) or not key for key in by_alias
    ):
        raise ValueError("Input versions must map aliases to exact versions")
    if alias not in by_alias and "input_version" not in requirements:
        return None
    value = by_alias.get(alias, requirements.get("input_version"))
    if not isinstance(value, str) or not value:
        raise ValueError("Declared input version must be an exact nonempty version identity")
    return value


def require_version(item, alias, version_id, policy):
    require_policy(item, alias, policy)
    expected = declared_version(item, alias)
    if policy == "fixed" and expected is not None and version_id != expected:
        raise ValueError("Fixed adoption does not satisfy this work's declared input version")


def make_binding(state, item, alias, object_id, version_id, policy, actor_id):
    require_version(item, alias, version_id, policy)
    wid = item["work_item_id"]
    return {
        "adoption_id": binding_key(wid, alias),
        "project_id": item["project_id"],
        "work_id": wid,
        "work_ids": [wid],
        "requirement_version": item["requirement_version"],
        "alias": alias,
        "object_id": object_id,
        "version_id": version_id,
        "policy": policy,
        "actor_id": actor_id,
        "at": state["clock"],
        "history": [],
    }


def binding_for(state, work_id, alias):
    """Return only this exact work edition's binding; never inherit a predecessor."""
    result = state.get("adoptions", {}).get(binding_key(work_id, alias))
    if result is None:
        return None
    item = state.get("work_items", {}).get(work_id)
    if item is None:
        raise ValueError("Adoption references unknown work")
    if (
        result.get("work_id") != work_id
        or result.get("work_ids") != [work_id]
        or result.get("requirement_version") != item["requirement_version"]
        or result.get("project_id") != item["project_id"]
        or result.get("alias") != alias
    ):
        raise ValueError("Adoption binding does not match its exact work edition")
    require_version(item, alias, result["version_id"], result["policy"])
    return result


def snapshot_bindings(state, item, adoption_view=None):
    """Copy this edition's bindings and contemporaneous targets for submission.

    A subsequent release or requirement replacement cannot change this result.
    The derived view must explicitly contain every selected binding: an absent
    target is represented by ``None``, never substituted with the adopted version.
    """
    view = state.get("adoption_view", {}) if adoption_view is None else adoption_view
    wid = item["work_item_id"]
    snapshots = {}
    for key, adoption in state.get("adoptions", {}).items():
        if adoption.get("work_id") != wid:
            continue
        binding = binding_for(state, wid, adoption["alias"])
        if key != binding_key(wid, adoption["alias"]) or binding is not adoption:
            raise ValueError("Adoption registry key does not match its work binding")
        if key not in view or "target_version" not in view[key]:
            raise ValueError("Adoption target projection is missing")
        snapshots[key] = {
            **copy.deepcopy(binding),
            "target_version": view[key]["target_version"],
            "allowed_policies": sorted(allowed_policies(item, adoption["alias"])),
        }
    return snapshots
