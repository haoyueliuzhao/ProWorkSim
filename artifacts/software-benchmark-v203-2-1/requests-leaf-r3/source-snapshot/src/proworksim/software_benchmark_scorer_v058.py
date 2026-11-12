"""Regrade the same sixteen requests candidates in a qualified local environment.

Only independently admitted grader fixtures change. Model candidates, official
tests, score semantics, and the original scoring records remain immutable.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path

from . import software_benchmark_scorer_v054 as base
from . import software_benchmark_scorer_v056 as predecessor
from . import software_benchmark_grading_environment_v058 as environment
from . import software_benchmark_grading_qualification_v058 as qualification
from . import software_benchmark_scorer_r6_v055 as resources
from .software_benchmark_baseline_v054 import validate_mapping
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_dispatch_v058 import require_v058_dispatch_allowed

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v058-official-ref-offline-requests-scorer-r1"
LIMITS = resources.LIMITS
RELOCATED_PYTHON = "/data0/zhuxinrui/proworksim-runtime/sysroot/usr/bin/python3.12"


def installation_manifest():
    return {"version": VERSION, "parent": predecessor.installation_manifest(),
            "adapter": reference(__file__), "environment_adapter": reference(environment.__file__),
            "environment_qualification_adapter": reference(qualification.__file__),
            "shared_server_hold": reference(ROOT / "config/v057-shared-server-hold.json"),
            "dispatch_guard": reference(ROOT / "src/proworksim/software_benchmark_dispatch_v058.py"),
            "dispatch_authorization": reference(ROOT / "config/v058-offline-rescore-authorization.json"),
            "unprivileged_launcher": reference(ROOT / "tools/run_offline_scorer_v058.py"),
            "original_limits": LIMITS, "visible_cpu_count": 4,
            "grader_network_changed": False, "actor_network_changed": False,
            "effective_network_policy": "network none; only container-local fixtures; no host network helper",
            "official_harness_changed": False, "candidate_content_changed": False}


def validate_runtime_relocation(original, current):
    """Permit only the same interpreter bytes at its physical, non-chroot path."""
    if original == current:
        return False
    before = original.get("parent", {}).get("python_executable", {})
    after = current.get("parent", {}).get("python_executable", {})
    if (before.get("path") != "/usr/bin/python3.12" or after.get("path") != RELOCATED_PYTHON
            or set(before) != {"path", "bytes", "sha256"} or set(after) != set(before)
            or any(before[key] != after[key] for key in ("bytes", "sha256"))):
        raise ValueError("Scorer interpreter differs beyond its approved physical path relocation")
    normalized = copy.deepcopy(current)
    normalized["parent"]["python_executable"] = before
    if normalized != original:
        raise ValueError("Official harness, dependencies or source changed during runtime relocation")
    return True


def validate_original_request(request):
    """Retain v056 candidate checks while recording the non-privileged Python launch."""
    if (request.get("arm") != "REF" or request.get("condition_id") not in predecessor.BUDGETS
            or request.get("model") != "Qwen/Qwen3.5-9B" or request.get("thinking") is not True
            or request.get("endpoint") != "code" or request.get("attempt") != 1
            or request.get("preparation_only") is not False or request.get("actor_feedback") is not False
            or request.get("limits") != LIMITS):
        raise ValueError("Only the original fixed REF budget candidate may be regraded")
    manifest = json.loads(checked(request["scorer_manifest"]).read_bytes())
    validate_runtime_relocation(manifest, predecessor.installation_manifest())
    predecessor.mapped.check_candidate(request)
    lock = json.loads(checked(request["native_candidate_lock"]).read_bytes())
    if (lock["slot"]["slot_id"] != request["slot_id"]
            or lock["slot"]["condition_id"] != request["condition_id"]):
        raise ValueError("Locked candidate belongs to another budget slot")
    if not set(resources.cpus(request["scoring_cpuset_cpus"])) <= os.sched_getaffinity(0):
        raise ValueError("Scoring CPUs exceed current affinity")
    return manifest


def validate_request(request):
    original = json.loads(checked(request["scoring_recovery_of"]).read_bytes())
    validate_original_request(original)
    additions = {"scoring_recovery_of", "environment_revision", "environment_qualification"}
    permitted_changes = {"scorer_manifest", "trusted_output_root", "receipt_output",
                         "quiescence_output", "scoring_cpuset_cpus"}
    if (set(request) != set(original) | additions
            or any(request[key] != value for key, value in original.items()
                   if key not in permitted_changes)):
        raise ValueError("Recovery may change only the qualified grading environment and output locations")
    for key in ("trusted_output_root", "receipt_output", "quiescence_output"):
        if request[key] == original[key]:
            raise ValueError("Recovery must preserve the original scoring output")
    manifest = json.loads(checked(request["scorer_manifest"]).read_bytes())
    if manifest != installation_manifest():
        raise ValueError("Revised scorer changed after freezing")
    if request["instance_id"] not in environment.PROFILES:
        raise ValueError("This grading revision covers only the four requests tasks")
    admitted = qualification.validate_qualification(request["environment_qualification"], original)
    if admitted["environment_revision"] != request["environment_revision"]:
        raise ValueError("Grader environment differs from the task-specific control qualification")
    selected = resources.cpus(request["scoring_cpuset_cpus"])
    if not set(selected) <= os.sched_getaffinity(0):
        raise ValueError("Scoring CPUs exceed the admitted host affinity")
    return manifest


def cleanup_scoring(request, tracking):
    proof = predecessor.cleanup_scoring(request, tracking)
    proof.update(version=VERSION, environment_revision=request.get("environment_revision"),
                 environment_qualification=request.get("environment_qualification"))
    return proof


def score_request(request):
    require_v058_dispatch_allowed("v058.scorer.score_request", instance_id=request.get("instance_id"))
    proof_path = Path(request["quiescence_output"]).resolve()
    if not proof_path.is_relative_to(ROOT / "runs/software-benchmark-v058") or proof_path.exists():
        raise ValueError("Each fresh score requires its own v058 quiescence receipt")
    tracking = {"phase": "before_admission", "owned_container_ids": [],
                "create_result_unknown": False, "client": None}
    try:
        return _score_request(request, tracking)
    finally:
        write_new(proof_path, cleanup_scoring(request, tracking))


def _score_request(request, tracking):
    manifest = validate_request(request)
    instance = base.read_local_dataset(request["dataset"])[request["instance_id"]]
    mapping = validate_mapping(json.loads(checked(request["baseline_mapping"]).read_bytes()),
                               instance=instance, image=request["image"])
    patch = checked(request["patch"]).read_bytes()
    identity, _ = base.make_identity(
        instance=instance, arm="REF", endpoint="code", patch=patch,
        candidate_tree_sha256=request["candidate_tree_sha256"],
        baseline_tree_sha256=request["baseline_tree_sha256"], dataset_reference=request["dataset"],
        scorer_manifest=manifest, image_record=request["image"], config_sha256=request["config_sha256"],
        limits=LIMITS, preparation_only=False, attempt=1)
    identity.update(version=VERSION, condition_id=request["condition_id"], slot_id=request["slot_id"],
                    baseline_mapping=request["baseline_mapping"],
                    native_candidate_lock=request["native_candidate_lock"],
                    scoring_cpuset_cpus=request["scoring_cpuset_cpus"],
                    scoring_recovery_of=request["scoring_recovery_of"],
                    environment_revision=request["environment_revision"],
                    environment_qualification=request["environment_qualification"])
    identity_sha = base.sha256(base.canonical(identity))
    run_id = "v058-requests-environment-" + request["condition_id"].lower() + "-" + identity_sha[:40]
    root = Path(request["trusted_output_root"]).resolve()
    if not root.is_relative_to(ROOT / "runs/software-benchmark-v058"):
        raise ValueError("Fresh v058 scoring cannot reuse historical output roots")
    output = root / run_id
    socket = Path(request["docker_socket"]).resolve()
    if not socket.is_socket():
        raise ValueError("Private Docker socket is unavailable")
    base.install_offline_guard(socket)
    import docker
    from swebench.harness.run_evaluation import run_instance
    from swebench.harness.utils import make_test_spec
    spec = make_test_spec(instance)
    if any(spec.image_assets.values()):
        raise ValueError("External grading assets require separately pinned preparation")
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    write_new(output / "identity.json", identity)
    os.umask(0o077)
    os.chdir(output)
    for key in ("DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        os.environ.pop(key, None)
    os.environ["DOCKER_HOST"] = "unix://" + str(socket)
    cli = base.checked_file(request["docker_cli"])
    os.environ["PATH"] = str(cli.parent) + os.pathsep + "/usr/bin:/bin"
    spec.image = request["image"]["image_id"]
    prediction = {"instance_id": request["instance_id"], "model_name_or_path": request["condition_id"],
                  "model_patch": patch.decode("utf-8")}
    client = docker.DockerClient(base_url=os.environ["DOCKER_HOST"], timeout=1800)
    tracking.update(client=client, phase="official_scoring")
    try:
        observation = {"path": str(output / "initial-container.json"), "base_commit": mapping["official_head"],
            "mapping": mapping, "mapping_reference": request["baseline_mapping"], "image_id": spec.image,
            "revision": manifest, "revision_reference": request["scorer_manifest"],
            "cpuset_cpus": request["scoring_cpuset_cpus"],
            "environment_revision": request["environment_revision"]}
        restricted = base.LocalDocker(client, spec.image, LIMITS)
        restricted.containers = environment.EnvironmentContainers(client.containers, spec.image, LIMITS, observation,
                                                  tracking=tracking)
        restricted.images.get(spec.image)
        result = run_instance(spec, prediction, restricted, run_id, timeout=1800,
                              rewrite_reports=False, skip_patch=not patch, task_repo=None)
        report = result[1].get(instance["instance_id"], {}) if result else {}
        known = (result is not None and report.get("patch_successfully_applied") is True
                 and not report.get("infra_failure", False) and type(report.get("resolved")) is bool)
        receipt = {"version": VERSION, "run_id": run_id, "identity_sha256": identity_sha,
                   "status": "official_report" if known else "technical_unknown",
                   "resolved": report["resolved"] if known else None, "official_result": result,
                   "condition_id": request["condition_id"], "slot_id": request["slot_id"],
                   "actor_feedback": False, "model_calls": 0, "preparation_only": False,
                   "scoring_recovery_of": request["scoring_recovery_of"],
                   "environment_revision": request["environment_revision"],
                   "environment_qualification": request["environment_qualification"],
                   "candidate_changed": False, "original_patch": request["patch"],
                   "native_candidate_lock": request["native_candidate_lock"]}
        receipt_ref = write_new(output / "receipt.json", receipt)
        write_new(request["receipt_output"], {"receipt": receipt_ref,
                  "identity": reference(output / "identity.json")})
        return receipt
    finally:
        tracking["phase"] = "official_scoring_returned"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    request = parser.parse_args().request
    receipt = score_request(json.loads(request.read_bytes()))
    print(json.dumps({key: receipt[key] for key in ("status", "run_id", "resolved")}))


if __name__ == "__main__":
    main()
