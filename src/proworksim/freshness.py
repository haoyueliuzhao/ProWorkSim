"""Freshness from declarations and required edges, without inferring use from reads."""

from .contracts import artifact_contracts, declared_bindings


def refresh_freshness(state):
    artifacts = state["artifacts"]
    contracts = state.get("artifact_contracts", artifact_contracts())
    memo = {}

    def resolve(aid, path=()):
        if aid in memo:
            return memo[aid]
        if aid in path or aid not in artifacts or not artifacts[aid]["current_version"]:
            return "unknown"
        artifact = artifacts[aid]
        version = artifact["versions"][artifact["current_version"]]
        declared = declared_bindings(version["derived_from"])
        if declared is None:
            return "unknown"
        required = contracts.get(aid, {}).get("required_input_roles", [])
        values = ["unknown"] if any(dep not in declared for dep in required) else []
        for upstream, pinned in declared.items():
            parent = artifacts.get(upstream)
            if parent is None or pinned not in parent["versions"]:
                values.append("unknown")
            elif pinned != parent["current_version"]:
                values.append("stale")
            else:
                values.append(resolve(upstream, (*path, aid)))
        result = "stale" if "stale" in values else "unknown" if "unknown" in values else "current"
        memo[aid] = result
        return result

    for aid, artifact in artifacts.items():
        if artifact["current_version"]:
            artifact["freshness"] = resolve(aid)
            artifact["freshness_basis"] = "declared_dependencies_and_required_edges"
            artifact["possibly_stale"] = artifact["freshness"] != "current"
