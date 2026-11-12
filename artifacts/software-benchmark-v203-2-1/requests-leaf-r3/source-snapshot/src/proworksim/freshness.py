"""Separate declared data freshness from approval applicability to current work."""

from .contracts import artifact_contracts, declared_bindings
from .core.rules import registered_applicability
from .core.types import CheckStatus


def refresh_freshness(state):
    artifacts = state["artifacts"]
    contracts = state.get("artifact_contracts", artifact_contracts())
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

    def applicable_work(aid):
        candidates = [
            item
            for wid, item in state.get("work_items", {}).items()
            if wid not in state.get("work_replacements", {})
            and item["status"] not in {"superseded", "cancelled"}
            and item.get("applicability", "current") == "current"
            and aid in item.get("deliverables", [])
        ]
        return tuple(item["work_item_id"] for item in candidates)

    def approved_for_work(work_id):
        from .basis import basis_context, legacy_basis_applicability

        item = state["work_items"][work_id]
        reference = item.get("required_basis")
        if (
            not reference
            or reference.get("artifact_id") != "basis"
            or reference.get("version_id") not in artifacts.get("basis", {}).get("versions", {})
        ):
            return None
        version = reference["version_id"]
        if "attestations" in state or state.get("schema_version") not in (
            None,
            "0.1",
            "0.2",
            "0.3",
        ):
            result = registered_applicability(
                state,
                reference,
                basis_context(item, state["project"]["project_id"], state["clock"]),
            )
            return version if result.status == CheckStatus.PASS else None
        return version if legacy_basis_applicability(state, item, version) else None

    def pinned_basis_status(version, work_ids):
        if version not in artifacts.get("basis", {}).get("versions", {}):
            return "unknown"
        if not work_ids:
            # No work context means no applicability conclusion. This is not a
            # comparison against the globally newest credential.
            return "not_applicable"
        required = [approved_for_work(work_id) for work_id in work_ids]
        if any(reference is None for reference in required):
            return "unknown"
        return "current" if all(reference == version for reference in required) else "stale"

    def requires_basis(aid, path=()):
        if aid == "basis":
            return True
        if aid in path:
            return False
        return any(
            requires_basis(parent, (*path, aid))
            for parent in contracts.get(aid, {}).get("required_input_roles", [])
        )

    def basis_status(aid, version_id=None, work_ids=None, path=()):
        artifact = artifacts.get(aid)
        if artifact is None:
            return "unknown"
        version_id = version_id or artifact["current_version"]
        work_ids = applicable_work(aid) if work_ids is None else work_ids
        key = aid, version_id, work_ids
        if key in basis_memo:
            return basis_memo[key]
        if key in path or version_id not in artifact["versions"]:
            return "unknown"
        declared = declared_bindings(artifact["versions"][version_id]["derived_from"])
        if declared is None:
            return "unknown"
        flags = [
            "unknown"
            for parent in contracts.get(aid, {}).get("required_input_roles", [])
            if parent not in declared and requires_basis(parent)
        ]
        for parent, pinned in declared.items():
            if parent == "basis":
                status = pinned_basis_status(pinned, work_ids)
                if status != "not_applicable":
                    flags.append(status)
            else:
                # Follow the version actually adopted, not an unrelated newer
                # parent version that happens to have a current approval.
                status = basis_status(parent, pinned, work_ids, (*path, key))
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
        basis_memo[key] = status
        return status

    for aid, artifact in artifacts.items():
        if artifact["current_version"]:
            data = artifact["data_freshness"] = data_status(aid)
            by_work = {wid: basis_status(aid, work_ids=(wid,)) for wid in applicable_work(aid)}
            artifact["basis_applicability_by_work"] = by_work
            artifact["basis_applicability_relations"] = [
                {
                    "artifact_id": aid,
                    "version_id": artifact["current_version"],
                    "work_item_id": wid,
                    "requirement_version": state["work_items"][wid].get(
                        "basis_requirement_version", state["work_items"][wid]["requirement_version"]
                    ),
                    "applicability": status,
                }
                for wid, status in by_work.items()
            ]
            statuses = set(by_work.values())
            basis = artifact["basis_applicability"] = (
                next(iter(statuses))
                if len(statuses) == 1
                else "unknown"
                if statuses
                else basis_status(aid)
            )
            flags = (data, basis)
            artifact["freshness"] = (
                "stale" if "stale" in flags else "unknown" if "unknown" in flags else "current"
            )
            artifact["freshness_basis"] = "declared_dependencies_and_per_work_approval"
            artifact["possibly_stale"] = artifact["freshness"] != "current"
