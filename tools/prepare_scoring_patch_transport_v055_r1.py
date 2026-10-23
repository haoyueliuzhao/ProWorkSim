"""Re-encode a locked native patch as UTF-8 Git binary data, preserving both trees."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from proworksim.software_benchmark_candidates_v054 import (  # noqa: E402
    checked, reference, write_new,
)
from proworksim import software_benchmark_native_artifact_v054 as native  # noqa: E402
from proworksim.software_benchmark_scorer_r5_v054 import check_candidate  # noqa: E402

VERSION = "v055-locked-patch-utf8-transport-r1"


def export_transport(baseline, candidate, original_patch, destination):
    """Use the original exporter and a private repository attribute only.

    --binary alone still emits non-NUL, non-UTF8 blobs as textual hunks. Setting
    -diff in the temporary bare repository makes Git encode changed blobs as
    binary literals/deltas. Neither the locked tree nor its .gitattributes changes.
    """
    git = native._git
    observations = []

    def binary_git(repo, args, **kwargs):
        if args[0] == "diff":
            before, after = args[-3:-1]
            git(repo, ["read-tree", before])
            if before != after:
                git(repo, ["apply", "--cached", "--binary", "--", str(original_patch.resolve())])
            actual = git(repo, ["write-tree"]).decode().strip()
            if actual != after:
                raise ValueError("Original locked patch does not reproduce the exact locked candidate")
            observations.append({"base_git_tree": before, "candidate_git_tree": actual})
            attributes = Path(repo) / "info" / "attributes"
            attributes.parent.mkdir(exist_ok=True)
            attributes.write_bytes(b"* -diff\n")
        return git(repo, args, **kwargs)

    # This CLI performs one export at a time in its private process. The original
    # module on disk is immutable; restoration also covers export exceptions.
    native._git = binary_git
    try:
        result = native.export_native_git_patch(baseline, candidate, destination)
    finally:
        native._git = git
    if len(observations) != 1:
        raise ValueError("Expected exactly one complete-tree transport export")
    Path(destination).read_bytes().decode("utf-8", errors="strict")
    return result


def prepare(request_path, output):
    request_ref = reference(request_path)
    request = json.loads(checked(request_ref).read_bytes())
    check_candidate(request)
    if request["arm"] not in {"REF", "MATCH"}:
        raise ValueError("This narrow transport recovery admits only native locked candidates")
    lock_ref = request["native_candidate_lock"]
    lock = json.loads(checked(lock_ref).read_bytes())
    patch_path = checked(request["patch"])
    try:
        patch_path.read_bytes().decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        pass
    else:
        raise ValueError("Already UTF-8 patches do not require transport recovery")
    baseline = json.loads(checked(lock["baseline"]).read_bytes())
    candidate = json.loads(checked(lock["candidate"]).read_bytes())
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    result = export_transport(baseline, candidate, patch_path, output / "candidate-transport.patch")
    original = lock["patch_receipt"]
    for key in ("base_git_tree", "candidate_git_tree", "base_tree_sha256", "candidate_tree_sha256"):
        if result[key] != original[key]:
            raise ValueError("Transport changed locked tree identity: " + key)
    receipt = {
        "version": VERSION, "original_request": request_ref,
        "original_patch": request["patch"], "original_native_lock": lock_ref,
        "baseline_snapshot": lock["baseline"], "candidate_snapshot": lock["candidate"],
        "replacement_patch": result["patch"],
        **{key: result[key] for key in (
            "base_git_tree", "candidate_git_tree", "base_tree_sha256", "candidate_tree_sha256")},
        "original_patch_round_trip_verified": True,
        "replacement_patch_round_trip_verified": result["round_trip_verified"],
        "utf8": True, "candidate_reselected": False, "files_excluded": 0,
        "source": reference(__file__), "new_model_calls": 0, "official_scoring_calls": 0,
    }
    return write_new(output / "transport-receipt.json", receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.request, args.output)))


if __name__ == "__main__":
    main()
