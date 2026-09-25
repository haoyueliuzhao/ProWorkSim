"""Structural feedback over the caller's public contract and visible artifacts.

No domain answer, source contents, hidden evaluator or reference solution enters
this function. Passing it is not a submission, adoption or business assessment.
"""

from .core.references import VersionRef


def _get(data, path):
    if isinstance(path, str):
        path = path.split(".")
    for key in path:
        if not isinstance(data, dict) or key not in data:
            return False, None
        data = data[key]
    return True, data


def _ref(value):
    try:
        return VersionRef.from_mapping(value)
    except (ValueError, AttributeError, TypeError):
        return None


def _lineage(document):
    proof = document["execution_provenance"]
    inputs = list(proof.get("source_references", {}).values())
    if proof.get("source_reference") is not None:
        inputs.append(proof["source_reference"])
    return {"artifact": document["alias"], "operation": proof.get("kind"),
            "actual_inputs": [VersionRef.from_mapping(value).to_dict() for value in inputs],
            "code_reference": proof.get("code_reference"),
            "input_aliases": list(proof.get("source_references", {}))}


def inspect_structure(item, documents, bindings):
    """Report only missing public structure and exact-reference relationships."""
    contract = item.get("deliverable_contract") or {}
    issues = []

    def issue(code, **details):
        entry = {"code": code, **details}
        if entry not in issues:
            issues.append(entry)

    if not contract.get("min_files", 1) <= len(documents) <= contract.get("max_files", 10):
        issue("file_count", minimum=contract.get("min_files", 1), maximum=contract.get("max_files", 10))
    for doc in documents:
        for field, allowed in [("kind", "allowed_kinds"), ("role", "allowed_roles")]:
            if contract.get(allowed) and doc[field] not in contract[allowed]:
                issue("unsupported_" + field, artifact=doc["alias"])
    for key in contract.get("required_fields", []):
        if not any(_get(d.get("data"), [key])[0] for d in documents):
            issue("missing_field", path=[key])

    checks = contract.get("content_checks", [])
    for check in checks:
        selected = [d for d in documents if not check.get("role") or d["role"] == check["role"]]
        path = check.get("path")
        if path and not any(_get(d.get("data"), path)[0] for d in selected):
            issue("missing_field", path=path)
        sources = list(check.get("sources", []))
        if check.get("reference_path"):
            sources.append({"alias": check["adoption_alias"], "reference_path": check["reference_path"]})
        for source in sources:
            alias, reference_path = source["alias"], source["reference_path"]
            binding = bindings.get(alias)
            if binding is None:
                issue("missing_work_adoption", source_alias=alias)
            elif binding.get("policy") != "fixed" and binding.get("target_version") != binding["version_id"]:
                issue("adoption_not_at_declared_target", source_alias=alias)
            found = [(d, _get(d.get("data"), reference_path)) for d in selected]
            refs = [_ref(value) for _, (exists, value) in found if exists]
            if not refs:
                issue("missing_source_reference", source_alias=alias, path=reference_path)
            elif any(r is None for r in refs):
                issue("invalid_source_reference", source_alias=alias, path=reference_path)
            elif len(set(refs)) != 1:
                issue("conflicting_source_reference", source_alias=alias, path=reference_path)
            elif binding is not None and refs[0] != _ref(binding):
                issue("reference_differs_from_work_adoption", source_alias=alias, path=reference_path)
            # A result-bearing file and a reference-bearing file both contribute;
            # no dependency is inserted and no correct source is selected for it.
            if len(set(refs)) == 1 and refs[0] is not None:
                for doc in selected:
                    contributes = _get(doc.get("data"), reference_path)[0] or (path and _get(doc.get("data"), path)[0])
                    if contributes and refs[0] not in [_ref(r) for r in doc["dependencies"]]:
                        issue("missing_file_dependency", artifact=doc["alias"], source_alias=alias)

    return {
        "version": "public-structure-preflight-v0.12",
        "work_id": item["work_item_id"],
        "structurally_ready": not issues,
        "issues": issues,
        "inspected_versions": [{k: d[k] for k in ("alias", "object_id", "version_id")} for d in documents],
        "execution_lineage": [
            _lineage(d)
            for d in documents if d.get("execution_provenance")
        ],
        "limits": [
            "Public file/reference/dependency structure only; no business values evaluated.",
            "Actual execution inputs are separate from all read files and declared business basis.",
            "No adoption, dependency, source field, submission or approval is created.",
        ],
    }
