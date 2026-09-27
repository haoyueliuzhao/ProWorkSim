"""CPU-only admission of pinned TeamBench D1/D2 assets; never a model benchmark.

Only the exact manually reviewed upstream bytes below may execute. Child
processes have a minimal environment, bounded CPU/address space/file size and a
fresh workspace. These controls are not an OS filesystem/network sandbox:
Docker role isolation is reported independently and remains pending unless
actually demonstrated. No models, API clients or arbitrary task code are loaded.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time

COMMIT = "d185aef1916fd86a9ba554d581fd256319a973af"
REVIEWED = {
    'generators/registry.py': 'cd64c9f73b6dcec090d298a39e2eb56fa71a1e2fcb98b86e97110422d3402970',
    'generators/gen_d2_data_quality.py': '23a5280be58a36e0a26f2a2d3c4fb0b8a0a50c6d03aab0a05bb334711c0a8e27',
    'tasks/D2_data_quality/grade.sh': '39e0b4726b21b34a2fbcd5b3987b1a193cdcb1028dc9d84dea766d7366f1d970',
    "generators/__init__.py": "cf35de34a5ce4836c40865df97c145930abcc0b9c50a99dc4b77d23f0503e37a",
    "generators/base.py": "5f72d5e9abecbc7c738211020f8ed00f60977f4b383a1b8a72f2c9104c3f30ba",
    "generators/primitives.py": "1d9076095c488abc22208c2ff5a6e797d37bd84e79c0a95a9807ccfd14ce002e",
    "generators/gen_d1_schema_drift.py": "008b27d6b5b1da8af0fc05866db48e832d0297d80daa19b37e11f41873c07f0e",
    "tasks/D1_schema_drift/grade.sh": "63e1ae844d85d0eb547b7f8a1013a3cc2502055dd3df0480ef9ffb83d6cb64dd",
    "harness/agent_interface.py": "110a67d21380529150f2ffdde12555653b02069981e45ed91876a456020a4a44",
    "harness/grade_task.py": "fac2e10b561924d5a3d9a0eb2ce8da987a90b4d7a04a6fc1dcfd28fd31a23501",
    "harness/utils.py": "429f71ed20cc4179ee1b190d43e4016dccc84b72f5c46b903f647668cc03cce6",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def verify_assets(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest["commit"] != COMMIT:
        raise ValueError("unreviewed TeamBench commit")
    for entry in manifest["files"]:
        path = root / "files" / entry["path"]
        if digest(path) != entry["sha256"]:
            raise ValueError(f"asset hash mismatch: {entry['path']}")
    for name, expected in REVIEWED.items():
        if digest(root / "files" / name) != expected:
            raise ValueError(f"execution denied for unreviewed bytes: {name}")
    # Copy no other upstream Python into the import tree. Namespace packages
    # avoid loading an unreviewed harness/__init__.py.
    return manifest


def limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2, 16 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run(command: list[str], cwd: Path, log: Path, *, constrain: bool = True) -> dict:
    env = {"PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin", "LANG": "C.UTF-8",
           "LC_ALL": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
    started = time.monotonic()
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True,
                            timeout=30, preexec_fn=limits if constrain else None, check=False)
    row = {"command": command, "cwd": str(cwd), "returncode": result.returncode,
           "stdout": result.stdout, "stderr": result.stderr,
           "elapsed_seconds": time.monotonic() - started}
    dump(log, row)
    return row


GENERATION = """
import sys
sys.path.insert(0, sys.argv[1])
from generators.registry import get_generator
from pathlib import Path
root=Path(sys.argv[2])
for task in ('D1_schema_drift','D2_data_quality'):
    generator=get_generator(task)
    for seed in (0,1,2):
        folder=root/task/('seed'+str(seed))
        generated=generator.generate(seed)
        generator.write_to_disk(generated,str(folder/'workspace'),str(folder/'reports'),str(folder/'task'))
"""

D1_WITNESS = '''import csv, glob, json, os
# Column mapping comes from the public specification, not grader expected.json.
MAPPING = __MAPPING__
by_id = {}
for name in sorted(glob.glob('data/input/*.csv')):
    with open(name, encoding='utf-8') as stream:
        for raw in csv.DictReader(stream):
            row = {MAPPING.get(k, k): v for k, v in raw.items()}
            try:
                value = max(0, int(row['value']))
            except ValueError:
                value = 0
            row = dict(id=row['id'], name=row['name'], value=str(value),
                       category=row.get('category') or 'unknown')
            previous = by_id.get(row['id'])
            if previous is None or value >= int(previous['value']):
                by_id[row['id']] = row
os.makedirs('data/output', exist_ok=True)
with open('data/output/result.csv', 'w', encoding='utf-8', newline='') as stream:
    writer = csv.DictWriter(stream, fieldnames=['id', 'name', 'value', 'category'], lineterminator='\\n')
    writer.writeheader()
    writer.writerows(sorted(by_id.values(), key=lambda r: (r['category'], int(r['id']))))
'''

D2_WITNESS = '''import csv, os
with open('data/input/records.csv', encoding='utf-8') as stream:
    reader = csv.DictReader(stream)
    columns = reader.fieldnames
    rows = list(reader)
score, department = columns[2:]
def numeric(row, missing=0):
    return missing if row[score] in ('', 'N/A', 'MISSING') else int(row[score])
by_id = {}
for row in rows:
    if row['id'] not in by_id or numeric(row) > numeric(by_id[row['id']]):
        by_id[row['id']] = row
clean = []
for row in by_id.values():
    if row[score] not in ('', 'N/A') and not 0 <= int(row[score]) <= 100:
        continue
    row = {key: ('MISSING' if value in ('', 'N/A') else value) for key, value in row.items()}
    if row[department] == 'MISSING' and numeric(row, missing=999) < 50:
        row[department] = 'review_needed'
    clean.append(row)
clean.sort(key=lambda row: (-numeric(row, missing=-1), row['name']))
os.makedirs('data/output', exist_ok=True)
with open('data/output/clean.csv', 'w', encoding='utf-8', newline='') as stream:
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\\n')
    writer.writeheader()
    writer.writerows(clean)
'''


def witness(task: str, spec: str, bad: bool = False) -> str:
    if task == "D1_schema_drift":
        mapping = dict(re.findall(r"`([^`]+)` must be mapped to `([^`]+)`", spec))
        if set(mapping.values()) != {"id", "name", "value"}:
            raise ValueError("public column mapping missing")
        code = D1_WITNESS.replace("__MAPPING__", repr(mapping))
        return code.replace("value >= int(previous['value'])", "True") if bad else code
    if task != "D2_data_quality":
        raise ValueError("task outside reviewed subset")
    return D2_WITNESS.replace("row[department] = 'review_needed'", "pass") if bad else D2_WITNESS


def native_contract_conflicts(expected: dict) -> list[str]:
    if (expected.get("dedup_id") in expected.get("batch1_missing_category_ids", [])
            and expected.get("dedup_category") != "unknown"):
        return ["same_id_requires_unknown_and_nonunknown_dedup_category"]
    return []


def decompose_score(score: dict) -> dict:
    secondary = score["secondary"]
    failures = score["failure_modes"]
    attestation_pass = "bad_attestation" not in failures
    return {"native_total": secondary["checks_total"],
            "native_passed": secondary["checks_passed"],
            "artifact_checks_total": secondary["checks_total"] - 1,
            "artifact_checks_passed": secondary["checks_passed"] - int(attestation_pass),
            "attestation_verdict_check_passed": attestation_pass,
            "verifier_execution_or_independence_measured": False,
            "failure_modes": failures, "native_pass": score["pass"]}


def check_candidate_inputs(case: Path) -> None:
    """Fail closed before official grading: absent expected otherwise skips checks."""
    if not (case / "reports/expected.json").is_file():
        raise ValueError("missing native expected.json; never grade for admission")
    expected = json.loads((case / "reports/expected.json").read_text())
    if native_contract_conflicts(expected):
        raise ValueError("contradictory native scoring contract")


D2_REQUIRED_FIELDS = {
    "row_count": int, "columns": list, "score_col": str, "dept_col": str,
    "dup_ids": list, "dup_winner_scores": dict, "out_of_range_ids": list,
    "missing_ids": list, "low_score_missing_dept_id": str,
    "correct_fill": str, "review_needed_id": str,
}


def validate_d2_expected(path: Path, expected_sha256: str) -> dict:
    if not path.is_file():
        raise ValueError("missing expected.json")
    if digest(path) != expected_sha256:
        raise ValueError("expected.json does not match frozen instance SHA256")
    expected = json.loads(path.read_text())
    if not isinstance(expected, dict) or set(expected) != set(D2_REQUIRED_FIELDS):
        raise ValueError("incomplete or unexpected D2 expected schema")
    for key, kind in D2_REQUIRED_FIELDS.items():
        if type(expected[key]) is not kind:
            raise ValueError(f"invalid D2 expected type: {key}")
    if (expected["row_count"] < 1 or expected["correct_fill"] != "MISSING"
            or expected["columns"] != ["id", "name", expected["score_col"], expected["dept_col"]]
            or len(set(expected["columns"])) != 4
            or set(expected["dup_ids"]) != set(expected["dup_winner_scores"])):
        raise ValueError("inconsistent D2 expected contract")
    for key in ("dup_ids", "out_of_range_ids", "missing_ids"):
        if not all(isinstance(value, str) and value for value in expected[key]):
            raise ValueError(f"invalid D2 expected ids: {key}")
    return expected


def write_d2_variant(native: Path, destination: Path) -> dict:
    """One message-quoting fix; no content predicate or expected values change."""
    source = native.read_text()
    old = chr(92) + '"{r.get(col)}' + chr(92) + '"'
    if source.count(old) != 1:
        raise ValueError("reviewed D2 quoting pattern must occur exactly once")
    repaired = source.replace(old, "{r.get(col)}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(repaired)
    patch = "".join(difflib.unified_diff(source.splitlines(True), repaired.splitlines(True),
                                       fromfile="upstream/tasks/D2_data_quality/grade.sh",
                                       tofile="proworksim-v021/D2/grade.sh"))
    destination.with_suffix(".patch").write_text(patch)
    return {"version": "proworksim-d2-quote-failclosed-v0.21", "official_native_score": False,
            "upstream_sha256": digest(native), "variant_sha256": digest(destination),
            "patch_sha256": digest(destination.with_suffix(".patch")),
            "modified_content_predicates": False, "expected_values_modified": False,
            "change": "remove message-only inner double quotes which break shell eval"}


def run_d2_variant_controls(out: Path, reviewed: Path) -> dict:
    folder = out / "d2-local-variant"
    folder.mkdir()
    # Written before any variant grading. All fixtures and denominators fixed.
    variants = ["correct_pass", "wrong_department_forged_pass", "correct_fail_attestation",
                "missing_expected", "tampered_expected"]
    dump(folder / "declaration.json", {"seeds": [0, 1, 2], "variants": variants,
         "controls_planned": 15, "model_calls": 0, "no_resampling": True,
         "interpretation": "local patched grader controls, not official TeamBench/model score"})
    grader = folder / "grade.sh"
    metadata = write_d2_variant(reviewed / "tasks/D2_data_quality/grade.sh", grader)
    rows = []
    for seed in (0, 1, 2):
        source_root = out / "controls/D2_data_quality" / f"seed{seed}"
        expected_sha = digest(source_root / "correct_program/reports/expected.json")
        for name in variants:
            source = source_root / ("wrong_program" if name == "wrong_department_forged_pass" else
                                    "correct_bad_attestation" if name == "correct_fail_attestation" else
                                    "correct_program")
            case = folder / f"seed{seed}" / name
            shutil.copytree(source, case)
            (case / "reports/score.json").unlink()
            expected_path = case / "reports/expected.json"
            if name == "missing_expected":
                expected_path.unlink()
            elif name == "tampered_expected":
                expected = json.loads(expected_path.read_text())
                expected["row_count"] += 1
                dump(expected_path, expected)
            row = {"seed": seed, "variant": name, "frozen_expected_sha256": expected_sha,
                   "case_path": str(case)}
            try:
                validate_d2_expected(expected_path, expected_sha)
            except ValueError as error:
                row.update({"status": "preflight_rejected", "reason": str(error), "score": None})
            else:
                execution = run(["bash", str(grader), str(case / "workspace"),
                                 str(case / "reports"), str(case / "submission"),
                                 str(case / "task"), str(expected_path)], case,
                                case / "variant-execution.json")
                if execution["returncode"]:
                    raise RuntimeError("local variant grader process failed")
                score = json.loads((case / "reports/score.json").read_text())
                row.update({"status": "graded", "score": score, "decomposed": decompose_score(score)})
            desired = (row["status"] == "preflight_rejected" if name in ("missing_expected", "tampered_expected")
                       else row["score"]["pass"] is (name == "correct_pass"))
            row["control_matches_declared_expectation"] = desired
            rows.append(row)
    return {"metadata": metadata, "controls": rows,
            "bounded_contract_passed": all(row["control_matches_declared_expectation"] for row in rows),
            "role_duties_or_model_quality_claimed": False}


def diagnose_d2_grader(reviewed: Path, case: Path, out: Path) -> dict:
    """Replay only the exact reviewed failing check, with stderr visible.

    The original grade.sh and score remain untouched. The diagnostic replaces
    only the check() wrapper's stderr suppression, not the checked expression.
    """
    source = (reviewed / "tasks/D2_data_quality/grade.sh").read_text()
    block = source.split("# Missing values replaced with MISSING", 1)[1].split("# Dedup:", 1)[0]
    check = block[block.index("check "):].strip()
    diagnostic = out / "d2-missing-check.sh"
    diagnostic.write_text('EXPECTED="$1"\nRESULT="$2"\ncheck() { eval "$1"; }\n' + check + "\n")
    result = run(["bash", str(diagnostic), str(case / "reports/expected.json"),
                  str(case / "workspace/data/output/clean.csv")], case,
                 out / "d2-missing-check-execution.json")
    return {"exact_check_source_sha256": hashlib.sha256(check.encode()).hexdigest(),
            "diagnostic_sha256": digest(diagnostic),
            "native_grader_modified": False,
            "change": "display failing eval stderr instead of suppressing it",
            "execution": result}


def d2_public_contract_check(case: Path) -> dict:
    """Independent full-row oracle from input and public D2 rules, not expected.

    This is a local product-control result, never an official benchmark score.
    """
    with (case / "workspace/data/input/records.csv").open() as stream:
        reader = csv.DictReader(stream)
        columns, records = reader.fieldnames, list(reader)
    score_col, dept_col = columns[2:]
    grouped = {}
    for row in records:
        grouped.setdefault(row["id"], []).append(row)
    output = []
    for group in grouped.values():
        winner = max(group, key=lambda row: int(row[score_col] or "0")).copy()
        if winner[score_col] and not 0 <= int(winner[score_col]) <= 100:
            continue
        for col in columns:
            if winner[col] in ("", "N/A"):
                winner[col] = "MISSING"
        if (winner[dept_col] == "MISSING" and winner[score_col] != "MISSING"
                and int(winner[score_col]) < 50):
            winner[dept_col] = "review_needed"
        output.append(winner)
    output.sort(key=lambda row: (-(-1 if row[score_col] == "MISSING" else int(row[score_col])), row["name"]))
    path = case / "workspace/data/output/clean.csv"
    with path.open() as stream:
        reader = csv.DictReader(stream)
        actual_columns, actual = reader.fieldnames, list(reader)
    return {"source": "input_and_public_spec_only", "official_score": False,
            "columns_exact": actual_columns == columns, "rows_exact": actual == output,
            "unix_line_endings": b"\r" not in path.read_bytes(),
            "expected_rows": len(output), "actual_rows": len(actual),
            "passed": actual_columns == columns and actual == output and b"\r" not in path.read_bytes()}


def role_probe_code() -> str:
    return """
import json,sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from harness.agent_interface import make_executor_config,make_verifier_config
root=Path(sys.argv[2]); records=[]
for name in ('workspace','reports','task','messages','submission'): (root/name).mkdir(parents=True,exist_ok=True)
(root/'task/brief.md').write_text('brief fixture')
(root/'task/spec.md').write_text('private spec fixture')
(root/'reports/expected.json').write_text('{"gold":"grader-only fixture"}')
kwargs=dict(workspace_dir=str(root/'workspace'),reports_dir=str(root/'reports'),messages_dir=str(root/'messages'),submission_dir=str(root/'submission'),task_dir=str(root/'task'))
executor=make_executor_config(brief_path=str(root/'task/brief.md'),**kwargs)
verifier=make_verifier_config(spec_path=str(root/'task/spec.md'),**kwargs)
for role,config,path in [('executor',executor,'/task/spec.md'),('executor',executor,'/shared/reports/expected.json'),('verifier',verifier,'/shared/reports/expected.json')]:
    tool=next(t for t in config.tools if t.name=='read'); result=tool.execute(path=path)
    records.append(dict(role=role,operation='read',path=path,exit_code=result.exit_code,stdout=result.stdout,stderr=result.stderr))
tool=next(t for t in verifier.tools if t.name=='write')
result=tool.execute(path='/shared/workspace/marker.txt',content='fixture')
records.append(dict(role='verifier',operation='write_tool',path='/shared/workspace/marker.txt',exit_code=result.exit_code,stdout=result.stdout,stderr=result.stderr))
# Only this literal harmless command is executed, against a disposable fixture.
tool=next(t for t in verifier.tools if t.name=='run')
result=tool.execute(cmd="printf fixture > marker.txt")
records.append(dict(role='verifier',operation='run_workspace_write',path='marker.txt',exit_code=result.exit_code,stdout=result.stdout,stderr=result.stderr,actual_file_written=(root/'workspace/marker.txt').is_file()))
(root/'role-probes.json').write_text(json.dumps(records,indent=2)+'\\n')
"""


def container_availability(out: Path) -> dict:
    results = []
    for command in (["docker", "info", "--format", "{{.ServerVersion}}"],
                    ["sudo", "-n", "docker", "info", "--format", "{{.ServerVersion}}"],
                    ["podman", "info", "--format", "{{.Version.Version}}"]):
        if shutil.which(command[0]):
            results.append(run(command, out, out / f"container-{command[0]}.json", constrain=False))
        else:
            results.append({"command": command, "available": False, "reason": "executable_absent"})
    return {"read_only_probes": results, "os_role_isolation": "pending",
            "containers_started": 0, "daemon_or_group_changes": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=Path("runs/assets/domain-v021/TeamBench"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assets, out = args.assets.resolve(), args.output.resolve()
    if not re.fullmatch(r"[/A-Za-z0-9_.-]+", str(out)):
        raise ValueError("output path must not contain shell metacharacters used by native eval grader")
    manifest = verify_assets(assets)
    out.mkdir(parents=True, exist_ok=False)
    # Avoid all unreviewed package files and imports, including pre-existing pyc.
    reviewed = out / "reviewed-source"
    for name in REVIEWED:
        target = reviewed / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(assets / "files" / name, target)
    generated = out / "generated"
    result = run([sys.executable, "-I", "-B", "-S", "-c", GENERATION,
                  str(reviewed), str(generated)], out, out / "generation.json")
    if result["returncode"]:
        raise RuntimeError("native generation failed; see generation.json")
    controls = []
    for task in ("D1_schema_drift", "D2_data_quality"):
        for seed in (0, 1, 2):
            original = generated / task / f"seed{seed}"
            expected = json.loads((original / "reports/expected.json").read_text())
            for variant in ("upstream_buggy", "correct_program", "wrong_program", "correct_bad_attestation"):
                case = out / "controls" / task / f"seed{seed}" / variant
                shutil.copytree(original, case)
                (case / "submission").mkdir()
                script = "etl.py" if task.startswith("D1") else "clean.py"
                if variant != "upstream_buggy":
                    (case / "workspace" / script).write_text(witness(
                        task, (case / "task/spec.md").read_text(), bad=variant == "wrong_program"))
                dump(case / "submission/attestation.json", {
                    "verdict": "fail" if variant == "correct_bad_attestation" else "pass",
                    "producer": "programmatic_grader_control_not_role_execution"})
                command = ["bash", str(reviewed / "tasks" / task / "grade.sh"),
                           str(case / "workspace"), str(case / "reports"),
                           str(case / "submission"), str(case / "task"),
                           str(case / "reports/expected.json")]
                result = run(command, case, case / "execution.json")
                if result["returncode"]:
                    raise RuntimeError(f"native grader process failure: {case}")
                score = json.loads((case / "reports/score.json").read_text())
                output_name = "result.csv" if task.startswith("D1") else "clean.csv"
                output = case / "workspace/data/output" / output_name
                control = {"task": task, "seed": seed, "variant": variant,
                           "score": score, "decomposed": decompose_score(score),
                           "contract_conflicts": native_contract_conflicts(expected),
                           "expected_sha256": digest(case / "reports/expected.json"),
                           "output_sha256": digest(output) if output.is_file() else None,
                           "case_path": str(case), "model_episode": False}
                if output.is_file():
                    with output.open() as stream:
                        rows = list(csv.DictReader(stream))
                    control["observed_output_rows"] = len(rows)
                    if task.startswith("D1"):
                        control["observed_id3_category"] = next((r.get("category") for r in rows if r.get("id") == "3"), None)
                        control["native_required_id3_category"] = expected["dedup_category"]
                if task.startswith("D2") and output.is_file():
                    control["local_public_product_check"] = d2_public_contract_check(case)
                controls.append(control)
    d2_variant = run_d2_variant_controls(out, reviewed)
    d2_diagnostic = diagnose_d2_grader(reviewed, out / "controls/D2_data_quality/seed0/correct_program", out)
    # Demonstrate fail-open expected-file behavior without changing canonical assets.
    absence = out / "missing-expected-control"
    shutil.copytree(out / "controls/D2_data_quality/seed0/wrong_program", absence)
    (absence / "reports/expected.json").unlink()
    (absence / "reports/score.json").unlink()
    run(["bash", str(reviewed / "tasks/D2_data_quality/grade.sh"),
         str(absence / "workspace"), str(absence / "reports"),
         str(absence / "submission"), str(absence / "task")], absence, absence / "execution.json")
    absent_score = json.loads((absence / "reports/score.json").read_text())
    try:
        check_candidate_inputs(absence)
    except ValueError as error:
        missing_gate = {"rejected": True, "reason": str(error)}
    else:
        raise AssertionError("expected-file guard failed")
    # Upstream Python role tools, exercised without models in fixture directories.
    acl = out / "role-fixtures"
    run([sys.executable, "-I", "-B", "-S", "-c", role_probe_code(), str(reviewed), str(acl)],
        out, out / "role-execution.json")
    role_results = json.loads((acl / "role-probes.json").read_text())
    docker = container_availability(out)
    d2_correct = [c for c in controls if c["task"].startswith("D2") and c["variant"] == "correct_program"]
    d2_negative = [c for c in controls if c["task"].startswith("D2") and c["variant"] != "correct_program"]
    scoring_passed = all(c["score"]["pass"] for c in d2_correct) and all(not c["score"]["pass"] for c in d2_negative)
    report = {
        "schema": "teambench-cpu-admission-v0.21", "upstream_commit": COMMIT,
        "source_type": "official_synthetic_parameterized_ETL_not_real_dataset_not_UCI",
        "scope": "D1/D2 seeds 0,1,2 program witnesses and negative controls only",
        "asset_manifest": manifest, "reviewed_execution_sha256": REVIEWED,
        "model_calls": 0, "model_episodes": 0, "gpu_seconds": 0, "parameter_updates": 0,
        "native_grader_controls": controls,
        "D2_native_check_diagnostic": d2_diagnostic,
        "D2_explicit_local_variant": d2_variant,
        "missing_expected": {"raw_native_score": absent_score, "admission_guard": missing_gate},
        "native_python_role_controls": role_results, "container_probe": docker,
        "admission": {
            "asset_acquisition": "passed", "D1_scoring_contract": "rejected_conflicting_expected",
            "D2_bounded_native_scoring": "passed" if scoring_passed else "rejected",
            "D2_local_quote_failclosed_variant": "passed" if d2_variant["bounded_contract_passed"] else "rejected",
            "grader_requires_complete_expected": True,
            "native_python_role_isolation": "rejected",
            "native_compose_hidden_expected": "rejected_static_mount_exposure",
            "actual_os_role_isolation": "pending", "model_benchmark_launchable": False,
            "final_external_evaluation_eligible": False,
            "reasons": ["D1 expected contains incompatible category requirements",
                        "D2 missing-values check fails before inspecting rows due to shell eval quoting syntax",
                        "native host tools expose expected and executor full spec",
                        "verifier native host run can write workspace",
                        "native compose mounts reports containing expected into agent roles",
                        "OS role mount behavior not demonstrated; Docker access unavailable",
                        "seeds inspected for development; reserve independent evaluation instances"],
        },
        "process_limits": {"cpu_seconds": 20, "address_space_bytes": 1024**3,
                           "file_bytes": 16 * 1024**2, "wall_seconds": 30,
                           "minimal_environment": True, "os_sandbox": False,
                           "reviewed_code_only": True, "upstream_bytes_modified": False},
    }
    dump(out / "report.json", report)
    print(json.dumps(report["admission"], indent=2))


if __name__ == "__main__":
    main()
