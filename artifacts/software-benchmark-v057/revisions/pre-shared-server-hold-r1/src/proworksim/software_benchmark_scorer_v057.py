"""Regrade the same sixteen requests candidates in a qualified local environment.

Only independently admitted grader fixtures change. Model candidates, official
tests, score semantics, and the original scoring records remain immutable.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from . import software_benchmark_scorer_v054 as base
from . import software_benchmark_scorer_v056 as predecessor
from . import software_benchmark_grading_environment_v057 as environment
from . import software_benchmark_grading_qualification_v057 as qualification
from . import software_benchmark_grader_nat_v057 as nat
from . import software_benchmark_scorer_r6_v055 as resources
from .software_benchmark_baseline_v054 import validate_mapping
from .software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v057-official-ref-requests-environment-scorer-r2-private-nat"
LIMITS = resources.LIMITS


def installation_manifest():
    return {"version": VERSION, "parent": predecessor.installation_manifest(),
            "adapter": reference(__file__), "environment_adapter": reference(environment.__file__),
            "environment_qualification_adapter": reference(qualification.__file__),
            "grader_nat_adapter": reference(nat.__file__),
            "original_limits": LIMITS, "visible_cpu_count": 4,
            "grader_network_changed": True, "actor_network_changed": False,
            "effective_network_policy": "fresh private grader-only NAT bound by environment_revision and grading_network_lane",
            "official_harness_changed": False, "candidate_content_changed": False}


def validate_network_binding(request, admitted):
    """Check immutable profile/ownership binding; host and container check live PIDs."""
    binding = request["grading_network_lane"]
    if (set(binding) != {"registry", "lane"} or type(binding["lane"]) is not int
            or binding["lane"] not in (0, 1)):
        raise ValueError("Each grading request must bind one exact private NAT lane")
    registry = json.loads(checked(binding["registry"]).read_bytes())
    previous = json.loads(checked(admitted["nat_registry"]).read_bytes())
    manifest = json.loads(checked(request["environment_revision"]).read_bytes())
    expected_root = Path(request["trusted_output_root"]).resolve().parent / "grading-nat"
    if (Path(binding["registry"]["path"]).resolve() != expected_root / "registry.json"
            or Path(registry.get("root", "")).resolve() != expected_root
            or registry.get("version") != nat.VERSION or registry.get("ready") is not True
            or registry.get("source_manifest") != previous.get("source_manifest")
            or registry.get("source_manifest", {}).get("helper") != manifest.get("nat_adapter")
            or registry.get("allowed_image_ids", {}).get(request["instance_id"]) != request["image"]["image_id"]
            or registry.get("actor_network_access") is not False
            or binding["registry"] == admitted["nat_registry"]):
        raise ValueError("Runtime grading NAT differs from its admitted profile or fresh ownership")
    lanes = registry.get("lanes", [])
    if ({lane.get("lane") for lane in lanes} != {0, 1} or len(lanes) != 2
            or {lane.get("keeper_id") for lane in lanes}
            & {lane.get("keeper_id") for lane in previous.get("lanes", [])}):
        raise ValueError("Model scoring must use fresh keepers, not admission containers")
    return registry


def validate_request(request):
    original = json.loads(checked(request["scoring_recovery_of"]).read_bytes())
    predecessor.validate_request(original)
    additions = {"scoring_recovery_of", "environment_revision", "environment_qualification", "grading_network_lane"}
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
        raise ValueError("Grader environment differs from the complete control qualification")
    validate_network_binding(request, admitted)
    selected = resources.cpus(request["scoring_cpuset_cpus"])
    if not set(selected) <= os.sched_getaffinity(0):
        raise ValueError("Scoring CPUs exceed the admitted host affinity")
    return manifest


def cleanup_scoring(request, tracking):
    proof = predecessor.cleanup_scoring(request, tracking)
    proof.update(version=VERSION, environment_revision=request.get("environment_revision"),
                 environment_qualification=request.get("environment_qualification"),
                 grading_network_lane=request.get("grading_network_lane"))
    return proof


def score_request(request):
    proof_path = Path(request["quiescence_output"]).resolve()
    if not proof_path.is_relative_to(ROOT / "runs/software-benchmark-v057") or proof_path.exists():
        raise ValueError("Each fresh score requires its own v057 quiescence receipt")
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
                    environment_qualification=request["environment_qualification"],
                    grading_network_lane=request["grading_network_lane"])
    identity_sha = base.sha256(base.canonical(identity))
    run_id = "v057-requests-environment-" + request["condition_id"].lower() + "-" + identity_sha[:40]
    root = Path(request["trusted_output_root"]).resolve()
    if not root.is_relative_to(ROOT / "runs/software-benchmark-v057"):
        raise ValueError("Fresh v057 scoring cannot reuse historical output roots")
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
            "environment_revision": request["environment_revision"],
            "nat_lane": request["grading_network_lane"]}
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
                   "grading_network_lane": request["grading_network_lane"],
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
