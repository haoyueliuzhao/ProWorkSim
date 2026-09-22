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

    # Keep data freshness separate from the applicability of adopted approval versions.
    data_memo, basis_memo = {}, {}

    def data_status(aid, path=()):
        if aid in data_memo:
            return data_memo[aid]
        if aid in path or aid not in artifacts or not artifacts[aid]["current_version"]:
            return "unknown"
        artifact = artifacts[aid]
        declared = declared_bindings(
            artifact["versions"][artifact["current_version"]]["derived_from"]
        )
        if declared is None:
            return "unknown"
        required = [
            r for r in contracts.get(aid, {}).get("required_input_roles", []) if r != "basis"
        ]
        flags = ["unknown"] if any(r not in declared for r in required) else []
        for parent, version in declared.items():
            if parent == "basis":
                continue
            if parent not in artifacts or version not in artifacts[parent]["versions"]:
                flags.append("unknown")
            elif version != artifacts[parent]["current_version"]:
                flags.append("stale")
            else:
                flags.append(data_status(parent, (*path, aid)))
        status = "stale" if "stale" in flags else "unknown" if "unknown" in flags else "current"
        data_memo[aid] = status
        return status

    def basis_status(aid, path=()):
        if aid in basis_memo:
            return basis_memo[aid]
        if aid in path or aid not in artifacts or not artifacts[aid]["current_version"]:
            return "unknown"
        artifact = artifacts[aid]
        declared = declared_bindings(
            artifact["versions"][artifact["current_version"]]["derived_from"]
        )
        if declared is None:
            return "unknown"
        flags = []
        if (
            "basis" in contracts.get(aid, {}).get("required_input_roles", [])
            and "basis" not in declared
        ):
            flags.append("unknown")
        for parent, version in declared.items():
            if parent == "basis":
                flags.append(
                    "current"
                    if parent in artifacts and version == artifacts[parent]["current_version"]
                    else "stale"
                )
            else:
                status = basis_status(parent, (*path, aid))
                if status != "not_applicable":
                    flags.append(status)
        status = (
            "stale"
            if "stale" in flags
            else "unknown"
            if "unknown" in flags
            else "current"
            if flags
            else "not_applicable"
        )
        basis_memo[aid] = status
        return status

    for aid, artifact in artifacts.items():
        if artifact["current_version"]:
            artifact["data_freshness"] = data_status(aid)
            artifact["basis_applicability"] = basis_status(aid)
