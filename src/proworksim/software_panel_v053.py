"""Outcome-blind SWE-smith panel selection and immutable repetition inventory.

Mutation families are generator labels, not human-validated defect categories.
No model score, trajectory, difficulty rating or successful patch is an input.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

VERSION = "software-panel-v053-v1"
DATASET = "SWE-bench/SWE-smith-py"
DATASET_REVISION = "77cab9055d42ab4a5c25c89a8f937096db13558e"
CODE_REVISION = "9b74ac08118a85c39c356802f7961893af73e07f"
SELECTION_SEED = "20261020-v053-main-panel"
REPEAT_SEED = "20261020-v053-repeat-panel"
GENERATION_SEED = "20261020-v053-independent-generations"
LEGACY_TASK_IDS = (
    "mahmoud__boltons.3bfcfdd0.combine_file__5i1f4zan",
    "mahmoud__boltons.3bfcfdd0.combine_file__7nlifqzn",
    "r1chardj0n3s__parse.30da9e4f.combine_file__gag0ta2m",
    "r1chardj0n3s__parse.30da9e4f.combine_file__p70qcld7",
    "martinblech__xmltodict.0952f382.combine_file__wpu0bspk",
    "martinblech__xmltodict.0952f382.func_basic__254qp8xw",
)
SOURCE_COLUMNS = (
    "instance_id", "patch", "FAIL_TO_PASS", "PASS_TO_PASS",
    "image_name", "repo", "problem_statement",
)
SELECTION_RULES = {
    "repository_order": "ascending SHA256(selection_seed, repository); first 20 admitted",
    "main_allocation": "20 repositories x 10 distinct tasks",
    "within_repository": (
        "Round robin over mutation families ordered by seeded SHA256; within each "
        "family prefer previously unused changed functions, then files, then seeded "
        "SHA256. Reject exact and near duplicates against already selected tasks."
    ),
    "repeat_allocation": (
        "2 per selected repository; different mutation families when available, "
        "then ascending SHA256(repeat_seed, task_id). Fixed before model outcomes."
    ),
    "exact_duplicate": (
        "Same repository and ordered changed file/addition/deletion content after "
        "whitespace normalization; diff metadata, hunk offsets and context omitted."
    ),
    "near_duplicate": (
        "Same repository and F2P-set Jaccard >= 0.8, plus either shared changed "
        "function contexts or >= 0.8 overlap of the smaller changed-old-line set. "
        "Same normalized patch is always a duplicate. This mechanical heuristic "
        "does not certify semantic independence."
    ),
    "environment_replacement": (
        "Only before the first model run: preserve rejected repositories/reasons "
        "and use next repository in the predeclared order. No task substitution "
        "after model outcomes; unknowns remain in the fixed denominator."
    ),
}


def canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       indent=2, allow_nan=False) + "\n").encode()


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def rank(seed, value):
    return sha256((seed + "\0" + value).encode())


def write_new(path, value):
    """Allow idempotent byte-identical writes, never overwrite changed evidence."""
    path = Path(path)
    content = canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(f"Refuse to replace frozen evidence: {path}")
        return
    with path.open("xb") as stream:
        stream.write(content)


def patch_features(patch):
    """Describe original mutation locations without consulting a solution."""
    paths, changes, loci, functions = set(), [], set(), set()
    current_path, old_line = None, 0
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            match = re.fullmatch(r"diff --git a/(.+) b/(.+)", line)
            if not match or match[1] != match[2]:
                raise ValueError("Require a same-path textual source mutation")
            current_path = match[1]
            path = PurePosixPath(current_path)
            if path.is_absolute() or ".." in path.parts or ".git" in path.parts:
                raise ValueError("Unsafe mutation path")
            paths.add(current_path)
            changes.append(["file", current_path])
        elif line.startswith("@@ "):
            match = re.match(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@(.*)", line)
            if not match or current_path is None:
                raise ValueError("Malformed mutation hunk")
            old_line = int(match[1])
            context = match[2].strip()
            if re.search(r"\b(?:async\s+def|def)\s+\w+", context):
                functions.add(current_path + "::" + context)
        elif line.startswith(("--- ", "+++ ", "index ")):
            continue
        elif line.startswith(("+", "-")):
            if current_path is None:
                raise ValueError("Mutation content outside a file")
            changes.append([line[0], " ".join(line[1:].split())])
            loci.add((current_path, old_line))
            if line[0] == "-":
                old_line += 1
        elif line.startswith(" "):
            old_line += 1
    if not paths or not any(row[0] in ("+", "-") for row in changes):
        raise ValueError("Empty mutation")
    return {
        "changed_paths": sorted(paths),
        "changed_functions": sorted(functions),
        "changed_old_lines": sorted(loci),
        "normalized_patch_sha256": sha256(canonical_bytes(changes)),
    }


def source_record(row):
    if any(key not in row for key in SOURCE_COLUMNS):
        raise ValueError("Incomplete official task schema")
    original = {key: row[key] for key in SOURCE_COLUMNS}
    task_id, repo = original["instance_id"], original["repo"]
    slug = repo.removeprefix("swesmith/")
    prefix = slug + "."
    if not task_id.startswith(prefix):
        raise ValueError("Task identity does not match the official repository")
    suffix = task_id[len(prefix):]
    if "__" in suffix:
        mutation_family = suffix.rsplit("__", 1)[0]
    elif re.fullmatch(r"pr_\d+", suffix):
        mutation_family = "pr_mined"
    else:
        raise ValueError("Unrecognized official task-generation identity")
    repository_slug, commit_prefix = slug.rsplit(".", 1)
    owner, project = repository_slug.split("__", 1)
    if not original["problem_statement"] or not original["image_name"]:
        raise ValueError("Missing problem statement or official image")
    f2p, p2p = original["FAIL_TO_PASS"], original["PASS_TO_PASS"]
    if (not isinstance(f2p, list) or not isinstance(p2p, list) or not f2p
            or len(f2p) != len(set(f2p)) or len(p2p) != len(set(p2p))
            or set(f2p) & set(p2p)):
        raise ValueError("Require unique disjoint official test inventories and nonempty F2P")
    return {
        "task_id": task_id, "repository": owner + "/" + project,
        "official_repo": repo, "base_commit_prefix": commit_prefix,
        "mutation_family": mutation_family, "image_name": original["image_name"],
        "source_row_sha256": sha256(canonical_bytes(original)),
        "patch_sha256": sha256(original["patch"].encode()),
        "FAIL_TO_PASS_count": len(f2p), "PASS_TO_PASS_count": len(p2p),
        "FAIL_TO_PASS": sorted(f2p),
        **patch_features(original["patch"]),
    }


def near_duplicate(left, right):
    if left["repository"] != right["repository"]:
        return False
    if left["normalized_patch_sha256"] == right["normalized_patch_sha256"]:
        return True
    a, b = set(left["FAIL_TO_PASS"]), set(right["FAIL_TO_PASS"])
    if len(a & b) / len(a | b) < 0.8:
        return False
    if set(left["changed_functions"]) & set(right["changed_functions"]):
        return True
    a = {tuple(item) for item in left["changed_old_lines"]}
    b = {tuple(item) for item in right["changed_old_lines"]}
    return bool(a and b and len(a & b) / min(len(a), len(b)) >= 0.8)


def select_repository_tasks(records, *, count=10, seed=SELECTION_SEED):
    """Balanced generator families with outcome-blind location diversity."""
    groups = defaultdict(list)
    for row in records:
        groups[row["mutation_family"]].append(row)
    repository = records[0]["repository"] if records else ""
    families = sorted(groups, key=lambda family: rank(seed + ":family:" + repository, family))
    selected, rejected, used_functions, used_paths = [], [], set(), set()
    while len(selected) < count:
        progress = False
        for family in families:
            remaining = groups[family]
            remaining.sort(key=lambda row: (
                len(used_functions & set(row["changed_functions"])),
                len(used_paths & set(row["changed_paths"])),
                rank(seed + ":task", row["task_id"]),
            ))
            while remaining:
                candidate = remaining.pop(0)
                duplicate = next((row for row in selected
                                  if near_duplicate(candidate, row)), None)
                if duplicate:
                    rejected.append({"task_id": candidate["task_id"],
                                     "duplicate_of": duplicate["task_id"],
                                     "reason": "exact_or_near_duplicate"})
                    continue
                selected.append(candidate)
                used_functions.update(candidate["changed_functions"])
                used_paths.update(candidate["changed_paths"])
                progress = True
                break
            if len(selected) == count:
                break
        if not progress:
            break
    return selected, rejected


def build_inventory(rows, *, source_manifest, official_profile_slugs):
    """Freeze all repo candidates before inspecting any model performance."""
    groups, excluded, seen_ids = defaultdict(list), [], set()
    raw_rows, counts = {}, Counter()
    rows = sorted(rows, key=lambda row: (
        row.get("instance_id", ""), sha256(canonical_bytes(row))))
    legacy = [source_record(row) for row in rows if row.get("instance_id") in LEGACY_TASK_IDS]
    for raw in rows:
        task_id = raw.get("instance_id")
        if task_id in seen_ids:
            excluded.append({"task_id": task_id, "reason": "duplicate_instance_id"})
            continue
        seen_ids.add(task_id)
        counts["raw_rows"] += 1
        if task_id in LEGACY_TASK_IDS:
            excluded.append({"task_id": task_id, "reason": "legacy_six_task"})
            continue
        try:
            row = source_record(raw)
        except (ValueError, TypeError, KeyError) as error:
            excluded.append({"task_id": task_id, "reason": "schema_or_mutation_ineligible",
                             "detail": str(error)})
            continue
        prior = next((old for old in legacy if near_duplicate(row, old)), None)
        if prior:
            excluded.append({"task_id": task_id, "reason": "legacy_six_duplicate_variant",
                             "duplicate_of": prior["task_id"]})
            continue
        raw_rows[task_id] = {key: raw[key] for key in SOURCE_COLUMNS}
        groups[row["repository"]].append(row)
    repositories = []
    for repository, records in groups.items():
        selected, duplicates = select_repository_tasks(records)
        profile_slug = records[0]["official_repo"].removeprefix("swesmith/")
        eligible = len(selected) == 10 and profile_slug in official_profile_slugs
        repositories.append({
            "repository": repository, "official_repo": records[0]["official_repo"],
            "profile_slug": profile_slug, "image_name": records[0]["image_name"],
            "official_profile": (official_profile_slugs.get(profile_slug)
                                 if isinstance(official_profile_slugs, dict) else None),
            "repository_rank": rank(SELECTION_SEED, repository),
            "source_task_count": len(records),
            "mutation_family_counts": dict(sorted(Counter(
                row["mutation_family"] for row in records).items())),
            "eligible_before_environment_check": eligible,
            "ineligibility_reason": None if eligible else (
                "missing_official_profile" if profile_slug not in official_profile_slugs
                else "fewer_than_10_distinct_candidates"),
            "candidate_task_ids": [row["task_id"] for row in selected],
            "candidate_tasks": selected,
            "duplicate_rejections": duplicates,
        })
    repositories.sort(key=lambda row: row["repository_rank"])
    inventory = {
        "version": VERSION, "kind": "outcome_blind_candidate_inventory",
        "source": source_manifest, "selection_seed": SELECTION_SEED,
        "repeat_seed": REPEAT_SEED, "generation_seed": GENERATION_SEED,
        "rules": SELECTION_RULES, "legacy_excluded_task_ids": list(LEGACY_TASK_IDS),
        "raw_row_count": counts["raw_rows"], "repository_count": len(groups),
        "eligible_repository_count": sum(row["eligible_before_environment_check"]
                                         for row in repositories),
        "mutation_family_label_scope": "instance_id generator-family proxy, not verified defect type",
        "model_outcomes_read": 0, "repositories": repositories,
        "excluded_records": excluded,
    }
    return inventory, raw_rows


def freeze_panel(inventory, admission):
    """Select first 20 admitted repositories; missing checks fail closed."""
    if inventory.get("version") != VERSION:
        raise ValueError("Unexpected inventory version")
    if admission.get("paused_common_system_fault") is True:
        raise ValueError("A common system fault must be resolved before panel freezing")
    expected = sha256(canonical_bytes(inventory))
    if admission.get("inventory_sha256") != expected or admission.get("model_runs_started") != 0:
        raise ValueError("Bind admissions to this inventory before every model run")
    admissions = {row["repository"]: row for row in admission["repositories"]}
    selected_repositories, rejections = [], []
    for repo in inventory["repositories"]:
        if not repo["eligible_before_environment_check"]:
            continue
        evidence = admissions.get(repo["repository"])
        if evidence is None:
            raise ValueError(f"Earlier ranked repository lacks admission: {repo['repository']}")
        if type(evidence.get("admitted")) is not bool:
            raise ValueError(f"Earlier ranked repository admission is unresolved: {repo['repository']}")
        if evidence.get("admitted") is True:
            if set(evidence.get("qualified_task_ids", [])) != set(repo["candidate_task_ids"]):
                raise ValueError("Admission must cover exactly all ten candidate tasks")
            selected_repositories.append(repo)
            if len(selected_repositories) == 20:
                break
        else:
            if not evidence.get("reason"):
                raise ValueError("Record a reason for every environment rejection")
            rejections.append(evidence)
    if len(selected_repositories) != 20:
        raise ValueError("Need 20 admitted repositories / 200 qualified distinct tasks")
    tasks, repeats = [], []
    for repo in selected_repositories:
        candidates = repo["candidate_tasks"]
        tasks.extend(candidates)
        ranked = sorted(candidates, key=lambda row: rank(REPEAT_SEED, row["task_id"]))
        first = ranked[0]
        second = next((row for row in ranked[1:]
                       if row["mutation_family"] != first["mutation_family"]), ranked[1])
        repeats.extend([first["task_id"], second["task_id"]])
    main = [row["task_id"] for row in tasks]
    slots, seeds = [], set()
    for repeat_index, task_ids in ((1, main), (2, repeats), (3, repeats)):
        for task_id in task_ids:
            identity = f"{task_id}:r{repeat_index}"
            seed = int(rank(GENERATION_SEED, identity)[:8], 16) % (2**31 - 1)
            if seed in seeds:
                raise ValueError("Generation seed collision; freeze a new protocol before model use")
            seeds.add(seed)
            slots.append({
                "slot_id": f"v053-{len(slots) + 1:03d}-r{repeat_index}",
                "task_id": task_id, "seed": seed, "repeat_index": repeat_index,
                "role": "main" if repeat_index == 1 else "repeat_diagnostic",
            })
    return {
        "version": VERSION, "kind": "frozen_single_agent_panel",
        "source": inventory["source"], "inventory_sha256": expected,
        "admission_sha256": sha256(canonical_bytes(admission)),
        "selection_seed": SELECTION_SEED, "repeat_seed": REPEAT_SEED,
        "generation_seed": GENERATION_SEED, "rules": SELECTION_RULES,
        "main_task_ids": main, "repeat_task_ids": repeats,
        "tasks": tasks, "slots": slots,
        "repositories": [{key: repo[key] for key in (
            "repository", "official_repo", "official_profile", "image_name",
            "repository_rank", "candidate_task_ids")} for repo in selected_repositories],
        "repository_count": 20, "main_task_count": 200,
        "repeat_task_count": 40, "episode_count": 280,
        "per_episode_token_cap": 500_000, "generation_token_cap": 140_000_000,
        "pre_model_environment_rejections": rejections,
        "model_runs_started_at_freeze": 0,
        "purpose": "single_agent_capability_calibration_not_independent_confirmation",
        "estimand": "single_run_completion_on_this_repository_stratified_panel",
        "main_result": "first preregistered run for all 200 tasks; unknown separate",
        "repeat_result": "three rates and task counts with 0/3,1/3,2/3,3/3 successes",
        "not_allowed": ["pooled_280_episode_mean_as_main", "pass_at_3_as_main",
                        "outcome_dependent_task_replacement", "training_or_adapter"],
    }
