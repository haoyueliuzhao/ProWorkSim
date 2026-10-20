"""Materialize the complete pinned Verified panel without authorizing execution.

Run in a trusted CPU process with pyarrow. Full evaluator records stay in the
private source directory; the published identity/slot manifests contain no
problem solutions, hidden tests, evaluator programs or scoring outcomes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import re
import stat
import tempfile

import pyarrow.parquet as pq

from domestic_asset_download import verified_file

REVISION = "78f471bf655a3137b2e8a75af1501690ec009ec3"
DATA_SHA256 = "030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25"
DATA_BYTES = 6_304_616
DATA_NAME = "test-00000-of-00001.parquet"
IDENTITY_COLUMNS = ("instance_id", "repo", "base_commit", "image")
PUBLIC_COLUMNS = (*IDENTITY_COLUMNS, "problem_statement")
REQUIRED_PRIVATE_COLUMNS = (
    "patch", "test_patch", "eval_script", "eval_type", "log_parser",
    "FAIL_TO_PASS", "PASS_TO_PASS",
)
ARMS = ("MATCH", "PROJECT", "REF")
ORDER_SEED = 202610200542


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n").encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_frozen(path, value, *, private=False):
    """An existing different preparation result must never be overwritten."""
    body = encoded(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != body:
            raise ValueError(f"Refusing to replace frozen preparation file: {path}")
        return {"path": str(path), "bytes": len(body), "sha256": digest(body)}
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
            temporary.chmod(0o600 if private else 0o644)
            # link() atomically fails if another preparer created the final file.
            os.link(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return {"path": str(path), "bytes": len(body), "sha256": digest(body)}


def task_seed(instance_id):
    prefix = ("v054:202610200541:" + instance_id).encode("utf-8")
    return int.from_bytes(hashlib.sha256(prefix).digest()[:8], "big") % 2**63


def prepare(root):
    root = root.resolve()
    source = root / "source"
    parquet = source / DATA_NAME
    if parquet.is_symlink() or not parquet.is_file():
        raise ValueError("Expected a regular local fixed parquet file")
    if stat.S_IMODE(source.stat().st_mode) != 0o700:
        source.chmod(0o700)
    if stat.S_IMODE(parquet.stat().st_mode) != 0o600:
        parquet.chmod(0o600)
    # The chmod changes ctime. Validate content once against the exact asset SHA;
    # subsequent preparation reuses the downloader's file-identity receipt.
    verification = verified_file(
        parquet, parquet.with_name(DATA_NAME + ".verified.json"),
        expected_sha256=DATA_SHA256, expected_bytes=DATA_BYTES,
        chunk_bytes=1024 * 1024,
    )
    table = pq.read_table(parquet)
    required = set(PUBLIC_COLUMNS + REQUIRED_PRIVATE_COLUMNS)
    if not required <= set(table.column_names):
        raise ValueError("The fixed dataset does not expose the required schema")
    if table.num_rows != 500:
        raise ValueError("The complete official test split must contain 500 rows")
    identities = table.select(IDENTITY_COLUMNS).to_pylist()
    identities.sort(key=lambda row: row["instance_id"].encode("utf-8"))
    if len({row["instance_id"] for row in identities}) != 500:
        raise ValueError("Duplicate instance IDs in the complete split")
    for row in identities:
        if any(not isinstance(row[key], str) or not row[key] for key in IDENTITY_COLUMNS):
            raise ValueError("An identity field is absent")
        if re.fullmatch(r"[0-9a-f]{40}", row["base_commit"]) is None:
            raise ValueError("A base commit is not a complete SHA1")
        if not row["image"].startswith("swebench/") or ":latest" not in row["image"]:
            raise ValueError("Unexpected official image reference; inspect before freezing")
    private_rows = table.to_pylist()
    private_rows.sort(key=lambda row: row["instance_id"].encode("utf-8"))
    for row in private_rows:
        for key in ("FAIL_TO_PASS", "PASS_TO_PASS"):
            if not isinstance(row[key], list) or not all(
                    isinstance(item, str) for item in row[key]):
                raise ValueError("Current scoring schema requires lists of test names")
    source_identity = {
        "dataset": "SWE-bench/SWE-bench_Verified",
        "configuration": "default", "split": "test", "revision": REVISION,
        "upstream_path": "data/" + DATA_NAME,
        "parquet_bytes": DATA_BYTES, "parquet_sha256": DATA_SHA256,
    }
    manifest = {
        "version": "software-benchmark-v054-identities-v1",
        "source": source_identity,
        "serialization": "UTF8_JSON_sort_keys_true_indent_2_trailing_LF",
        "identity_order": "UTF8_lexicographic_instance_id",
        "task_count": 500,
        "repository_counts": dict(sorted(Counter(row["repo"] for row in identities).items())),
        "projection": list(IDENTITY_COLUMNS),
        "tasks": identities,
    }
    identity_receipt = write_frozen(root / "manifests/identities.json", manifest)
    public_rows = [{key: row[key] for key in PUBLIC_COLUMNS} for row in private_rows]
    private_receipt = write_frozen(source / "trusted-evaluation.json", private_rows, private=True)
    public_receipt = write_frozen(source / "public-tasks.json", public_rows, private=True)
    ordered_ids = [row["instance_id"] for row in identities]
    random.Random(ORDER_SEED).shuffle(ordered_ids)
    permutations = tuple(itertools.permutations(ARMS))
    slots = []
    for task_index, instance_id in enumerate(ordered_ids):
        for arm_index, arm in enumerate(permutations[task_index % len(permutations)]):
            slots.append({
                "slot_index": len(slots) + 1,
                "slot_id": f"v054-{arm}-{instance_id}",
                "instance_id": instance_id,
                "arm": arm,
                "task_order_index": task_index + 1,
                "arm_order_within_task": arm_index + 1,
                "seed": task_seed(instance_id),
                "execution_authorized": False,
                "model_attempts": 0,
                "status": "planned_not_authorized",
            })
    if Counter(row["arm"] for row in slots) != Counter({arm: 500 for arm in ARMS}):
        raise AssertionError("The slot plan must preserve every complete arm")
    slot_manifest = {
        "version": "software-benchmark-v054-slots-v1",
        "source": source_identity,
        "identity_manifest_sha256": identity_receipt["sha256"],
        "formal_execution_authorized": False,
        "automatic_start": False,
        "authorized_model_episodes": 0,
        "planned_slot_count": 1500,
        "distinct_task_count": 500,
        "seed_formula": "int.from_bytes(SHA256(UTF8('v054:202610200541:'+instance_id))[:8],'big') % 2**63",
        "order_seed": ORDER_SEED,
        "order_rule": "shuffle_sorted_ids_with_random.Random_then_cycle_six_lexicographic_arm_permutations",
        "arm_permutations": permutations,
        "slots": slots,
    }
    slot_receipt = write_frozen(root / "manifests/slots.json", slot_manifest)
    receipt = {
        "version": "software-benchmark-v054-data-preparation-v1",
        "source": source_identity,
        "dataset_rows": 500,
        "unique_instance_ids": 500,
        "unique_images": len({row["image"] for row in identities}),
        "repository_counts": manifest["repository_counts"],
        "identity_manifest": identity_receipt,
        "slots_manifest": slot_receipt,
        "trusted_evaluation": private_receipt,
        "actor_input_projection": public_receipt,
        "actor_input_columns": list(PUBLIC_COLUMNS),
        "hidden_fields_in_actor_projection": [],
        "private_material_must_not_be_mounted_to_actor": True,
        "private_source_directory_mode": "0700",
        "private_data_files_mode": "0600",
        "all_data_rows_kept": True,
        "formal_execution_authorized": False,
        "automatic_start": False,
        "authorized_model_episodes": 0,
        "model_calls": 0,
        "gpu_use": False,
        "actual_environments_ready": False,
    }
    write_frozen(root / "manifests/data-preparation.json", receipt)
    return {**receipt, "this_read_verification": verification}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
