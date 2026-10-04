"""Bind changed-interface CPU controls to a clean v031 execution snapshot."""

import argparse
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.storage import digest, read_json
from scripts.run_ne_v021 import reference, write

SOURCE = Path(__file__).resolve().parents[1]
COMPONENTS = {
    "functional_graph": ("runs/v031-functional-dense-controls/summary.json", "file_sha256"),
    "native_codecs": ("runs/v031-controls/native-codecs-r2/report.json", "source_files"),
    "profile_binding": ("runs/v031-controls/profile.json", "tested_files_sha256"),
    "gpu_probe_control": ("runs/v031-dense-probe-cpu/summary.json", "file_sha256"),
    "model_queue": ("runs/v031-controls/pipeline/checks.json", "file_sha256"),
    "continuation_driver": ("runs/v031-controls/driver/checks.json", "file_sha256"),
    "final_static": ("runs/v031-controls/final-static.json", "file_sha256"),
}


def qualify(data_root, output):
    root = Path(data_root).resolve()
    source = code_identity()
    if source["code_dirty"] is not False:
        raise ValueError("Freeze a clean v031 execution checkout before CPU admission")
    evidence, components, fingerprints = {}, {}, {}
    for name, (relative, hash_key) in COMPONENTS.items():
        path = root / relative
        value = read_json(path)
        checks = value.get("checks") or [value]
        if not checks or any(row.get("returncode") != 0 for row in checks):
            raise ValueError("Required targeted CPU component did not pass: " + name)
        if not value.get(hash_key):
            raise ValueError("CPU component omitted the tested source fingerprints: " + name)
        for filename, expected in value[hash_key].items():
            if Path(filename).is_absolute() or ".." in Path(filename).parts:
                raise ValueError("CPU source fingerprint must be relative to the execution checkout")
            if digest((SOURCE / filename).read_bytes()) != expected:
                raise ValueError("CPU-tested file changed: " + filename)
            fingerprints[filename] = expected
        evidence[name] = reference(path)
        components[name] = {"checks": checks, "scope": value.get("scope"),
                            "coverage_notice": value.get("coverage_notice"),
                            "overlap_notice": value.get("overlap_notice")}
    native_path = root / "runs/v031-controls/native-templates/qualification.json"
    native = read_json(native_path)
    if (native.get("passed") is not True or native.get("model_calls") != 0
            or native.get("torch_cuda_initialized") is not False
            or native.get("required_files_unchanged") is not True
            or native["source"]["source_tree_sha256"] != source["source_tree_sha256"]
            or native["source_after"]["source_tree_sha256"] != source["source_tree_sha256"]
            or native.get("combination_count") != 12 or native.get("native_roundtrip_count") != 48
            or native.get("scripted_sdk_transport_calls") != 48
            or native.get("actual_world_error_count") != 16
            or native.get("error_feedback_next_request_count") != 16):
        raise ValueError("New native interfaces lack same-source actual SDK/read/error CPU controls")
    for group in ("required_source_files", "required_development_assets", "required_upstream_source_files"):
        for name, record in native[group].items():
            if digest((SOURCE / name).read_bytes()) != record["sha256"]:
                raise ValueError("SDK control source or development asset changed: " + name)
    for files in native["tokenizer_files"].values():
        for record in files.values():
            path = Path(record["path"])
            if path.stat().st_size != record["bytes"] or digest(path.read_bytes()) != record["sha256"]:
                raise ValueError("Actual qualified tokenizer changed: " + str(path))
    evidence["actual_sdk_native_controls"] = reference(native_path)
    value = {"version": "software-model-selection-cpu-qualification-v0.31", "passed": True,
             "source": source, "model_calls": 0, "gpu_used": False,
             "evidence": evidence, "components": components, "tested_files_sha256": fingerprints,
             "native_summary": {key: native[key] for key in ("combination_count", "native_roundtrip_count",
                 "actual_world_error_count", "error_feedback_next_request_count", "maximum_selected_prompt_tokens",
                 "minimum_remaining_margin_tokens", "projected_request_count")},
             "scope": "Separate targeted component checks and actual SDK CPU fixtures, bound by exact unchanged files to this clean commit. Overlapping test invocations are not summed. Real old-trace GPU numerical validation and fresh per-model qualification are still required before screening."}
    write(output, value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(qualify(args.data_root, args.output)["passed"])


if __name__ == "__main__":
    main()
