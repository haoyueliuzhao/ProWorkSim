"""Exactly one mapped-baseline CPU score, preserving the failed original attempt."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from proworksim.software_benchmark_scorer_v054 import canonical, checked_file, file_reference, sha256
from proworksim.software_benchmark_scorer_r4_v054 import installation_manifest, score_request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--mapping-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    mapping_ref = file_reference(args.mapping)
    if mapping_ref["sha256"] != args.mapping_sha256:
        raise ValueError("Baseline mapping changed before predeclared control")
    mapping = json.loads(args.mapping.read_bytes())
    if mapping["instance_id"] != "astropy__astropy-12907":
        raise ValueError("Only the original preselected first task may be controlled")
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    original = ROOT / "runs/software-benchmark-v054/scorer-preflight-r2"
    request = json.loads((original / "request.json").read_bytes())
    empty = checked_file(request["patch"]).read_bytes()
    if empty:
        raise ValueError("Control candidate must remain the original empty patch")
    (output / "empty.patch").write_bytes(empty)
    manifest = output / "installation-manifest-r4.json"
    manifest.write_bytes(canonical(installation_manifest()))
    config = json.loads((original / "config.json").read_bytes())
    config.update(version="v054-official-scorer-preflight-r4",
                  baseline_mapping=mapping_ref, previous_controller=file_reference(original / "controller-status.json"),
                  revised_utc=datetime.now(timezone.utc).isoformat(),
                  tree_identity_scheme="preparation_pinned_official_setup_tree_mapping")
    (output / "config.json").write_bytes(canonical(config))
    binding = {"official_image_id": mapping["official_image_id"],
               "official_setup_head": mapping["official_head"],
               "official_setup_tree": mapping["official_tree"],
               "dataset_base": mapping["dataset_base"], "baseline_mapping": mapping_ref}
    binding_sha = sha256(canonical(binding))
    (output / "baseline-binding.json").write_bytes(canonical(binding))
    request.update(attempt=2, baseline_mapping=mapping_ref,
                   patch=file_reference(output / "empty.patch"), scorer_manifest=file_reference(manifest),
                   baseline_tree_sha256=binding_sha, candidate_tree_sha256=binding_sha,
                   config_sha256=sha256(canonical(config)), trusted_output_root=str(output / "official-output"))
    (output / "request.json").write_bytes(canonical(request))
    (output / "controller-claim.json").write_bytes(canonical({
        "request": file_reference(output / "request.json"), "script": file_reference(__file__),
        "automatic_retry": False, "model_calls": 0, "preparation_only": True}))
    status = {"status": "official_scoring_in_progress", "preparation_only": True,
              "instance_id": mapping["instance_id"], "model_calls": 0, "scoring_calls": 1}
    (output / "controller-status.json").write_bytes(canonical(status))
    try:
        receipt = score_request(request)
        status.update(status="completed", official_scoring_status=receipt["status"],
                      baseline_resolved=receipt["resolved"], counted_as_model_result=False,
                      official_receipt=file_reference(output / "official-output" / receipt["run_id"] / "receipt.json"))
    except BaseException as error:
        status.update(status="technical_unknown", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        status["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "controller-status.json").write_bytes(canonical(status))
    print(json.dumps(status))


if __name__ == "__main__":
    main()
