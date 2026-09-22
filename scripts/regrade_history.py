"""Add current evaluation to copies of immutable historical traces; no model calls."""

import argparse
import json
import shutil
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.learning import export_bundle
from proworksim.storage import Store, atomic_write, digest, json_bytes
from proworksim.validation import evaluate


def regrade(source, destination, old_exports=None):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise ValueError("Destination must not exist")
    rows = []
    for path in sorted(source.iterdir()):
        if not (path / "control/state.json").is_file():
            continue
        target = destination / "worlds" / path.name
        shutil.copytree(path, target)
        store = Store(target)
        before = store.load()
        files_before = {
            str(p.relative_to(target)): digest(p.read_bytes())
            for p in (target / "control/versions").rglob("*")
            if p.is_file()
        }
        old_sft = []
        if old_exports and (Path(old_exports) / path.name / "sft.jsonl").exists():
            old_sft = [
                json.loads(line)["call_id"]
                for line in (Path(old_exports) / path.name / "sft.jsonl").read_text().splitlines()
            ]
        records = evaluate(target)
        exported = export_bundle(target, destination / "exports" / path.name)
        new_sft = [
            json.loads(line)["call_id"]
            for line in (destination / "exports" / path.name / "sft.jsonl").read_text().splitlines()
        ]
        after = store.load()
        files_after = {
            str(p.relative_to(target)): digest(p.read_bytes())
            for p in (target / "control/versions").rglob("*")
            if p.is_file()
        }
        rows.append(
            {
                "world": path.name,
                "original_calls": len(before["calls"]),
                "calls_unchanged": digest(json_bytes(before["calls"]))
                == digest(json_bytes(after["calls"])),
                "artifact_bytes_unchanged": files_before == files_after,
                "original_evaluation_versions": sorted(
                    {r["evaluator_version"] for r in before["evaluations"]}
                ),
                "retained_old_evaluations": all(
                    r in after["evaluations"] for r in before["evaluations"]
                ),
                "evaluations": records,
                "old_sft_count": len(old_sft),
                "new_sft_count": exported["counts"]["sft"],
                "removed_call_ids": sorted(set(old_sft) - set(new_sft)),
                "added_call_ids": sorted(set(new_sft) - set(old_sft)),
            }
        )
    report = {**code_identity(), "no_api_resampling": True, "worlds": rows}
    atomic_write(destination / "summary.json", json_bytes(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--old-exports")
    args = parser.parse_args()
    report = regrade(args.source, args.destination, args.old_exports)
    print(
        json.dumps(
            [{k: v for k, v in row.items() if k != "evaluations"} for row in report["worlds"]],
            indent=2,
        )
    )
