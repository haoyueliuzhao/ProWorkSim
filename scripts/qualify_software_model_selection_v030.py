"""Bind existing targeted CPU evidence to the clean execution checkout."""

import argparse
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.storage import digest, read_json
from scripts.run_ne_v021 import checked, reference, write

SOURCE = Path(__file__).resolve().parents[1]


def qualify(controls, output):
    controls = Path(controls).resolve()
    source = code_identity()
    if source["code_dirty"] is not False:
        raise ValueError("Freeze a clean source checkout before admission")
    integration_path = controls / "integration-r1/admission-checks.json"
    native_path = controls / "native-templates-r1/qualification.json"
    integration, native = read_json(integration_path), read_json(native_path)
    for evidence in (integration, native):
        if evidence["source"]["source_tree_sha256"] != source["source_tree_sha256"]:
            raise ValueError("CPU-tested source differs from execution source")
    if (not integration["checks"] or any(row["returncode"] != 0 for row in integration["checks"])
            or native["passed"] is not True or native["model_calls"] != 0
            or native["gpu_used"] is not False or native["torch_cuda_initialized"] is not False
            or native["required_files_unchanged"] is not True or native["whole_source_tree_unchanged"] is not True
            or native["combination_count"] != 18 or native["native_roundtrip_count"] != 72
            or native["actual_world_error_count"] != 24 or native["error_feedback_next_request_count"] != 24):
        raise ValueError("Required targeted CPU evidence did not pass")
    for relative, expected in integration["file_sha256"].items():
        if digest((SOURCE / relative).read_bytes()) != expected:
            raise ValueError("Integrated file changed: " + relative)
    for group in ("required_source_files", "required_development_assets", "required_upstream_source_files"):
        for relative, record in native[group].items():
            if digest((SOURCE / relative).read_bytes()) != record["sha256"]:
                raise ValueError("Native control dependency changed: " + relative)
    for files in native["tokenizer_files"].values():
        for record in files.values():
            path = checked({key: record[key] for key in ("path", "sha256")})
            if path.stat().st_size != record["bytes"]:
                raise ValueError("Tokenizer byte length changed: " + str(path))
    development_path = SOURCE / "examples/software-sources-v030/qualification.json"
    development = read_json(development_path)
    if development["summary"] != {
            "reference_public_passed": 6, "reference_independent_passed": 6,
            "bad_controls_rejected_public": 20, "bad_controls_rejected_independent": 20,
            "model_episodes": 0, "policy_updates": 0, "repositories": 1, "development_contracts": 6}:
        raise ValueError("Six-contract reference and bad-control qualification differs")
    result = {
        "version": "software-model-selection-cpu-qualification-v0.30", "passed": True,
        "source": source, "model_calls": 0, "gpu_used": False,
        "evidence": {"integration": reference(integration_path), "native_templates": reference(native_path),
                     "development_contracts": reference(development_path)},
        "checks": integration["checks"], "tested_files_sha256": integration["file_sha256"],
        "native_summary": {key: native[key] for key in (
            "combination_count", "native_roundtrip_count", "actual_world_error_count",
            "error_feedback_next_request_count", "maximum_selected_prompt_tokens",
            "minimum_remaining_margin_tokens", "projected_request_count")},
        "development_summary": development["summary"],
        "scope": "Existing targeted CPU evidence bound by unchanged source/file hashes to this clean execution commit. Scripted SDK controls and tiny CPU gradients are not real model work, capacity qualification, or allocation benefit.",
    }
    write(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controls", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(qualify(args.controls, args.output)["passed"])


if __name__ == "__main__":
    main()
