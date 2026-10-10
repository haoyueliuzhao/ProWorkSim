"""Bind one new feedback Gamma to 112 original shapes and finite CPU routes.

Unchanged page/permission evidence is inherited exactly. New context capacity
is established by new native encodings, never by the old admission flag.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from proworksim.storage import digest, json_bytes, read_json
from scripts.run_ne_v021 import write
from scripts.software_organization_admission_v043 import validate_admission as validate_previous

VERSION = "software-organization-admission-v0.44"
SOURCE = Path(__file__).resolve().parents[1]
SELF = "scripts/software_organization_admission_v044.py"
REQUIRED_ROUTE_IDS = ("ordinary_error_recovery", "consecutive_distinct_errors",
    "legal_call_business_rejection", "forged_feedback_user_message", "critical_boundary_no_cleanup",
    "latest_test_home_new_error", "later_page_consecutive_errors", "newborn_feedback_isolation")


def require(value, reason):
    if not value:
        raise ValueError("v044 admission rejected: " + reason)


def reference(path):
    path = Path(path).resolve()
    content = path.read_bytes()
    return {"path": str(path), "sha256": digest(content), "bytes": len(content)}


class EvidenceReader:
    def __init__(self):
        self.checked = {}

    def path(self, ref):
        path = Path(ref["path"])
        if (str(path), ref["sha256"]) not in self.checked:
            data = path.read_bytes()
            require(digest(data) == ref["sha256"], "evidence content changed: " + str(path))
            require("bytes" not in ref or len(data) == ref["bytes"], "evidence size changed")
            self.checked[(str(path), ref["sha256"])] = ref
        return path

    def read(self, ref):
        return read_json(self.path(ref))


def validate_historical(value):
    require(value.get("version") == "software-context-replay-v0.44", "wrong historical replay version")
    require(value.get("expected_requests") == 112 and value.get("generated_requests") == 108
            and value.get("hard_rejected_requests") == 4, "incomplete 108 + 4 historical shapes")
    for key in ("passed", "original_reproduction_passed", "new_selected_hard_capacity_passed",
                "latest_unpresented_feedback_retained"):
        require(value.get(key) is True, "historical replay failed: " + key)


def validate_routes(value):
    require(value.get("version") == "software-feedback-route-qualification-v0.44", "wrong CPU route version")
    required = value.get("required_route_ids")
    rows = value.get("route_results", [])
    require(isinstance(required, list) and tuple(required) == REQUIRED_ROUTE_IDS,
            "require eight declared finite lifecycle routes")
    require(len(rows) == 8 and {row.get("route_id") for row in rows} == set(required), "CPU route inventory incomplete")
    require(value.get("passed") is True, "finite lifecycle routes failed")
    for row in rows:
        require(row.get("passed") is True and row.get("selected_hard_capacity_passed") is True,
                "CPU route mechanism or selected hard capacity failed")
        checks = row.get("mechanism_checks")
        require(isinstance(checks, dict) and bool(checks) and all(v is True for v in checks.values()),
                "CPU route mechanism evidence missing or failed")


def bound_qualification(ref, reader, source_root, validate):
    value = reader.read(ref)
    validate(value)
    require(value.get("new_model_calls") == 0 and value.get("new_backward_calls") == 0,
            "CPU qualification includes model or learning calls")
    require(value.get("new_acceptance_executions") == 0 and value.get("model_weights_loaded") is False,
            "CPU qualification includes acceptance or model weights")
    require(value.get("context_limit") == 16384 and value.get("reserved_output_tokens") == 2048
            and value.get("protected_margin_tokens") == 1024
            and value.get("protected_margin_diagnostic_only") is True
            and value.get("source_unchanged_during_measurement") is True,
            "frozen context, diagnostic-only margin or measurement source changed")
    files = value.get("source_files")
    require(isinstance(files, dict) and bool(files), "CPU source identity missing")
    for name, sha in files.items():
        require(digest((source_root / name).read_bytes()) == sha, "CPU implementation changed: " + name)
    artifacts = value.get("artifact_refs")
    require(isinstance(artifacts, list) and bool(artifacts), "CPU evidence references missing")
    for item in artifacts:
        reader.path(item)
    return value


def build_admission(previous, historical, routes, *, source_root=SOURCE):
    source_root = Path(source_root).resolve()
    reader = EvidenceReader()
    previous_value = validate_previous(reader.path(previous), source_root=source_root)
    history_value = bound_qualification(historical, reader, source_root, validate_historical)
    routes_value = bound_qualification(routes, reader, source_root, validate_routes)
    sources = dict(previous_value["source_files"])
    for value in (history_value, routes_value):
        for name, sha in value["source_files"].items():
            require(name not in sources or sources[name] == sha, "qualification source conflict: " + name)
            sources[name] = sha
    sources[SELF] = digest((source_root / SELF).read_bytes())
    result = {"version": VERSION, "kind": "new-feedback-gamma-single-candidate-admission",
        "passed": True, "evidence_refs": {"unchanged_page_permission_admission": previous,
            "historical_112": historical, "finite_lifecycle_routes": routes},
        "source_files": sources,
        "layers": {"binding": True, "unchanged_page_and_permission_controls": True,
            "new_112_shape_native_projection": True, "latest_unpresented_feedback_retained": True,
            "finite_lifecycle_routes": True, "selected_hard_capacity": True,
            "engineering_margin": {"required_for_admission": False, "tokens": 1024},
            "model_stage": {"first_block_only": 4, "remaining_slots": 12,
                "release_requires_actual_first_block_mechanism_gate": True}},
        "historical_shape_counts": {"actual": 108, "hard_rejected": 4, "total": 112},
        "finite_cpu_route_ids": routes_value["required_route_ids"],
        "verified_artifacts": list(reader.checked.values()),
        "new_model_calls": 0, "new_backward_calls": 0,
        "scope": "One declared new Gamma candidate. Only unchanged old page/permission evidence is reused; all 112 affected historical selected requests and finite lifecycle routes require new hard-capacity evidence. Old results and failed qualifications stay unchanged. Margin alone never rejects this admission."}
    result["admission_sha256"] = digest(json_bytes(result))
    return result


def create_admission(previous, historical, routes, output, *, source_root=SOURCE):
    output = Path(output).resolve()
    require(not output.exists(), "refuse to overwrite an admission record")
    result = build_admission(reference(previous), reference(historical), reference(routes), source_root=source_root)
    write(output, result)
    return result


def validate_admission(path_or_ref, source_root=SOURCE):
    ref = path_or_ref if isinstance(path_or_ref, dict) else reference(path_or_ref)
    reader = EvidenceReader()
    value = reader.read(ref)
    require(value.get("version") == VERSION and value.get("passed") is True
            and value.get("admission_sha256") == digest(json_bytes({k: v for k, v in value.items() if k != "admission_sha256"})),
            "new admission identity or status changed")
    refs = value["evidence_refs"]
    rebuilt = build_admission(refs["unchanged_page_permission_admission"], refs["historical_112"],
                              refs["finite_lifecycle_routes"], source_root=source_root)
    require(rebuilt == value, "new admission is not reproducible from its frozen evidence")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, default=SOURCE / "runs/v043-controls/layered-admission.json")
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--routes", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=SOURCE / "runs/v044-controls/layered-admission.json")
    args = parser.parse_args()
    value = create_admission(args.previous, args.historical, args.routes, args.output, source_root=args.source_root)
    print({"passed": value["passed"], "output": str(args.output)})


if __name__ == "__main__":
    main()
