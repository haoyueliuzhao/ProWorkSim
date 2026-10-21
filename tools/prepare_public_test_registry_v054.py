"""Bind public repository-wide test commands to all 500 admitted Actor setup trees."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = Path(__file__).resolve().parents[1]
VERSION = "software-benchmark-public-test-registry-v054"


def entry_command(repo, python, observation):
    help_result = observation.get("details", {}).get("public_help", {})
    directories = observation.get("details", {}).get("root_entries", {})
    ready = (observation.get("returncode") in {None, 0} and help_result.get("returncode") == 0
             and not help_result.get("timed_out"))
    if repo == "django/django":
        ready &= directories.get("tests/runtests.py", {}).get("exists", False)
        ready &= all(flag in help_result.get("stdout", "") for flag in ("--noinput", "--parallel"))
        return [python, "tests/runtests.py", "--noinput", "--parallel", "1"], ready
    if repo == "sympy/sympy":
        ready &= directories.get("bin/test", {}).get("exists", False)
        return [python, "bin/test"], ready
    probe = observation.get("details", {}).get("import_probe", {})
    try:
        pytest = json.loads(probe.get("stdout", "{}"))["pytest"]
    except (ValueError, KeyError):
        pytest = {}
    ready &= probe.get("returncode") == 0 and bool(pytest.get("version")) and not pytest.get("error")
    return [python, "-m", "pytest"], ready


def prepare(family_directory, mapping_directory, output, overrides=()):
    state = json.loads((family_directory / "state.json").read_text())
    observations = {}
    for row in state["results"]:
        path = Path(row["path"])
        observation = json.loads(path.read_text())
        observations[(observation["repo"], observation["python_family"])] = (path, observation)
    for path in overrides:
        observation = json.loads(path.read_text())
        key = (observation["repo"], observation["python_family"])
        if key not in observations:
            raise ValueError("A corrective observation cannot add a new performance-selected family")
        before = observations[key][1]
        if any(before[field] != observation[field] for field in
               ("representative", "covered_task_ids", "actor_image_id", "public_python")):
            raise ValueError("Correct only the original fixed representative and environment")
        observations[key] = (path, observation)
    identities_path = ROOT / "artifacts/software-benchmark-v054/manifests/identities.json"
    tasks = json.loads(identities_path.read_text())["tasks"]
    if len(tasks) != 500 or len({row["instance_id"] for row in tasks}) != 500:
        raise ValueError("Keep the complete fixed 500-task denominator")
    entries = []
    for task in tasks:
        path = mapping_directory / (task["instance_id"] + ".json")
        mapping = json.loads(path.read_text())
        if (mapping["status"] != "actor_baseline_admitted"
                or mapping.get("schema") not in {"proworksim.v054.actor-admission-r3", "proworksim.v054.actor-admission-r3.1"}
                or mapping.get("runtime_version", {}).get("equal") is not True
                or mapping["instance_id"] != task["instance_id"]
                or mapping["repo"] != task["repo"] or mapping["dataset_base"] != task["base_commit"]
                or mapping["actor_tree"] != mapping["official_tree"]):
            raise ValueError("Public entry must bind the admitted original task and setup tree")
        version = mapping["public_python_details"]["version"]
        match = re.match(r"(\d+\.\d+)\.", version)
        if not match:
            raise ValueError("Actual public interpreter version is missing")
        key = (task["repo"], match.group(1))
        observed_path, observation = observations[key]
        if task["instance_id"] not in observation["covered_task_ids"]:
            raise ValueError("Family qualification does not cover this planned task")
        command, admitted = entry_command(task["repo"], mapping["public_python"], observation)
        entries.append({
            "instance_id": task["instance_id"], "repo": task["repo"],
            "source": "public_repository", "cwd": "/testbed", "argv": command,
            "admitted": admitted,
            "status": "public_frontend_family_admitted" if admitted else "public_frontend_unresolved",
            "public_python": mapping["public_python"], "public_python_version": version,
            "source_identity": {"dataset_base": mapping["dataset_base"],
                "official_setup_head": mapping["official_head"], "official_setup_tree": mapping["official_tree"],
                "actor_head": mapping["actor_head"], "actor_tree": mapping["actor_tree"],
                "actor_image_id": mapping["actor_image_id"]},
            "baseline_mapping": reference(path), "policy_sha256": mapping["policy_sha256"],
            "family": {"repo": key[0], "python_major_minor": key[1],
                       "representative": observation["representative"]},
            "family_observation": reference(observed_path),
            "observed_frontend_actor_image_id": observation["actor_image_id"],
            "instance_frontend_executed_on_current_actor_image": (
                task["instance_id"] == observation["representative"]
                and mapping["actor_image_id"] == observation["actor_image_id"]),
            "frontend_qualification_reuse": "same public test source/interpreter/frontend dependency; r2 representative help evidence, independent final r3/r3.1 runtime-version equivalence proof",
            "current_runtime_version_matches_original_official": mapping["runtime_version"]["equal"],
            "full_suite_executed_for_admission": False, "hidden_material_used": False,
            "selection": "repository-wide public default; no answer-derived files or task-result selection",
        })
    result = {
        "version": VERSION, "planned_tasks": 500, "entries": entries,
        "actual_repository_entries_admitted": sum(row["admitted"] for row in entries),
        "unresolved_tasks": [row["instance_id"] for row in entries if not row["admitted"]],
        "repository_counts": dict(Counter(row["repo"] for row in entries)),
        "families_observed": len(observations), "family_qualification_basis": "repository and actual Python major.minor",
        "identity_manifest": reference(identities_path),
        "family_observations": [reference(path) for path, _ in observations.values()],
        "coverage_limit": "21 fixed representatives, not every project release or every task frontend executed; all 500 commands bind their actual interpreter and immutable source/setup mapping",
        "public_test_timeout_seconds": 1800, "baseline_all_green_required": False,
        "normal_public_test_exit_nonzero_is_not_automatically_infrastructure_failure": True,
        "full_suites_executed": 0, "model_calls": 0, "formal_execution_authorized": False,
        "automatic_model_dispatch": False,
    }
    return write_new(output, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--families", type=Path, required=True)
    parser.add_argument("--mappings", type=Path, required=True)
    parser.add_argument("--override", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.families.resolve(), args.mappings.resolve(), args.output,
                             [path.resolve() for path in args.override])))


if __name__ == "__main__":
    main()
