"""Freeze an already installed scorer and check all 500 local TestSpecs on CPU.

No containers, test suites, model calls, remote datasets or downloads are started.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import zipfile

from proworksim.software_benchmark_scorer_v054 import (
    WHEEL_SHA256,
    canonical,
    file_reference,
    installation_manifest,
    install_offline_guard,
    read_local_dataset,
    sha256,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--dataset-sha256", required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--docker-cli", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    counters = Counter()

    def count(event, _args):
        if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen"}:
            counters[event] += 1

    sys.addaudithook(count)
    install_offline_guard()
    args.output.mkdir(parents=True, exist_ok=True)
    dataset_ref = {
        "path": str(args.dataset.resolve()), "bytes": args.dataset.stat().st_size,
        "sha256": args.dataset_sha256}
    rows = read_local_dataset(dataset_ref)
    manifest = installation_manifest()
    wheel_ref = file_reference(args.wheel)
    if wheel_ref["sha256"] != WHEEL_SHA256:
        raise ValueError("Wheel identity mismatch")
    with zipfile.ZipFile(args.wheel) as wheel:
        wheel_sources = {
            name.removeprefix("swebench/"): sha256(wheel.read(name))
            for name in wheel.namelist()
            if name.startswith("swebench/") and name.endswith(".py")}
    if manifest["official_python_sources"] != wheel_sources:
        raise ValueError("Installed official source differs from the pinned wheel")
    from swebench.harness.constants import (
        END_TEST_OUTPUT, START_TEST_OUTPUT, TEST_EXIT_CODE, EvalType,
    )
    from swebench.harness.grading import get_eval_report
    from swebench.harness.log_parsers import PARSER_REGISTRY
    from swebench.harness.utils import make_test_spec

    contracts = []
    parsers = Counter()
    for instance_id, row in sorted(rows.items()):
        spec = make_test_spec(row)
        assert spec.instance_id == instance_id and spec.image == row["image"]
        assert spec.log_parser in PARSER_REGISTRY
        EvalType(spec.eval_type)
        assert spec.FAIL_TO_PASS == row["FAIL_TO_PASS"]
        assert spec.PASS_TO_PASS == row["PASS_TO_PASS"]
        assert not any(spec.image_assets.values()), "Unprepared external binary asset"
        parsers[spec.log_parser] += 1
        contracts.append({
            "instance_id": instance_id, "image": spec.image,
            "trusted_row_sha256": sha256(canonical(row)),
            "official_eval_script_sha256": sha256(spec.eval_script.encode()),
            "log_parser": spec.log_parser, "eval_type": spec.eval_type,
            "external_binary_assets": False,
        })

    fixture = {
        "instance_id": "v054__cpu-synthetic-scorer", "image": "fixture/local:latest",
        "repo": "fixture/fixture", "version": "synthetic",
        "FAIL_TO_PASS": ["test_fixture.py::test_fix"],
        "PASS_TO_PASS": ["test_fixture.py::test_keep"],
        "log_parser": "parse_log_pytest", "eval_type": "pass_and_fail",
        "eval_script": 'echo "synthetic only"\n',
    }
    spec = make_test_spec(fixture)
    prediction = {"instance_id": fixture["instance_id"], "model_name_or_path": "CPU",
                  "model_patch": ""}
    synthetic = {}
    for name, fix, expected in (("passing", "PASSED", True), ("failing", "FAILED", False)):
        log = args.output / f"synthetic-{name}.log"
        log.write_text(
            START_TEST_OUTPUT + "\n"
            + f"{fix} test_fixture.py::test_fix\nPASSED test_fixture.py::test_keep\n"
            + END_TEST_OUTPUT + f"\n{TEST_EXIT_CODE}: {0 if expected else 1}\n")
        report = get_eval_report(spec, prediction, log, include_tests_status=True)
        assert report[fixture["instance_id"]]["resolved"] is expected
        synthetic[name] = report[fixture["instance_id"]]["resolved"]
    empty = args.output / "synthetic-no-tests.log"
    empty.write_text(START_TEST_OUTPUT + "\n" + END_TEST_OUTPUT + f"\n{TEST_EXIT_CODE}: 0\n")
    report = get_eval_report(spec, prediction, empty, include_tests_status=True)
    assert not report[fixture["instance_id"]]["resolved"]
    assert not report[fixture["instance_id"]]["patch_successfully_applied"]
    synthetic["no_test_evidence_not_resolved"] = True
    docker_version = subprocess.run(
        [str(args.docker_cli), "--version"], capture_output=True, text=True, check=True)
    (args.output / "installation-manifest.json").write_bytes(canonical(manifest))
    (args.output / "task-contracts.json").write_bytes(canonical(contracts))
    result = {
        "version": "v054-scorer-preparation-v1", "passed": True,
        "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset_ref, "wheel": wheel_ref,
        "installed_official_sources_equal_wheel": True,
        "installed_official_python_files": len(wheel_sources),
        "effective_dependency_versions": len(manifest["effective_dependency_versions"]),
        "installation_manifest": file_reference(args.output / "installation-manifest.json"),
        "task_contracts": file_reference(args.output / "task-contracts.json"),
        "docker_cli": file_reference(args.docker_cli),
        "docker_cli_version": docker_version.stdout.strip(),
        "all_500_specs_compatible": True, "parser_counts": dict(sorted(parsers.items())),
        "external_binary_assets": 0, "synthetic_grading": synthetic,
        "model_calls": 0, "gpu_launches": 0, "containers": 0, "benchmark_test_runs": 0,
        "network_attempts": counters["socket.connect"] + counters["socket.getaddrinfo"],
        "subprocesses": counters["subprocess.Popen"],
        "scope": "Official code/schema/parser CPU controls, not benchmark model results",
        "control_script": file_reference(__file__),
    }
    assert result["network_attempts"] == 0
    (args.output / "preparation-receipt.json").write_bytes(canonical(result))
    print(json.dumps({key: result[key] for key in (
        "passed", "all_500_specs_compatible", "installed_official_python_files",
        "network_attempts", "containers", "benchmark_test_runs")}))


if __name__ == "__main__":
    main()
