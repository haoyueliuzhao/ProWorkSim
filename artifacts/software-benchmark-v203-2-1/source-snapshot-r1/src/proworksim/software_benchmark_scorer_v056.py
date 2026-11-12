"""Fresh REF budget-condition scoring with the unchanged official test harness."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from . import software_benchmark_scorer_v054 as base
from . import software_benchmark_scorer_r5_v054 as mapped
from . import software_benchmark_scorer_r6_v055 as resources
from .software_benchmark_baseline_v054 import validate_mapping
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_ref_budget_v056 import BUDGETS

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v056-official-ref-budget-scorer-r1"
LIMITS = resources.LIMITS


def installation_manifest():
    return {"version": VERSION, "parent": mapped.installation_manifest(),
            "adapter": reference(__file__), "resource_adapter": reference(resources.__file__),
            "original_limits": LIMITS, "visible_cpu_count": 4,
            "untracked_build_audit": reference(resources.AUDIT)}


def validate_request(request):
    if (request.get("arm") != "REF" or request.get("condition_id") not in BUDGETS
            or request.get("model") != "Qwen/Qwen3.5-9B" or request.get("thinking") is not True
            or request.get("endpoint") != "code" or request.get("attempt") != 1
            or request.get("preparation_only") is not False or request.get("actor_feedback") is not False
            or request.get("limits") != LIMITS):
        raise ValueError("Only a fresh planned REF budget candidate may be graded")
    manifest = json.loads(checked(request["scorer_manifest"]).read_bytes())
    if manifest != installation_manifest():
        raise ValueError("Official scorer installation changed after freezing")
    mapped.check_candidate(request)
    lock = json.loads(checked(request["native_candidate_lock"]).read_bytes())
    if (lock["slot"]["slot_id"] != request["slot_id"]
            or lock["slot"]["condition_id"] != request["condition_id"]):
        raise ValueError("Locked candidate does not belong to this budget condition")
    selected = resources.cpus(request["scoring_cpuset_cpus"])
    if not set(selected) <= os.sched_getaffinity(0):
        raise ValueError("Scoring CPUs exceed the admitted host affinity")
    return manifest


class TrackedContainers(resources.Containers):
    def __init__(self, *args, tracking, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracking = tracking

    def create(self, **kwargs):
        self.tracking["create_result_unknown"] = True
        container = super().create(**kwargs)
        self.tracking["owned_container_ids"].append(container.id)
        self.tracking["create_result_unknown"] = False
        return container


def cleanup_scoring(request, tracking):
    """Only containers created by this scorer can be stopped or removed here."""
    errors = []
    client = tracking.get("client")
    if tracking["create_result_unknown"]:
        errors.append({"create_result_unknown": True})
    if client is not None:
        import docker
        for identity in tracking["owned_container_ids"]:
            try:
                container = client.containers.get(identity)
                if container.id != identity:
                    raise ValueError("Docker returned another container identity")
                container.reload()
                if container.attrs.get("State", {}).get("Running"):
                    container.stop(timeout=10)
                    container.reload()
                if container.attrs.get("State", {}).get("Running"):
                    raise RuntimeError("Owned grading container is still running")
                container.remove(force=False)
            except docker.errors.NotFound:
                pass
            except Exception as error:
                errors.append({"container_id": identity, "error": str(error)})
        client.close()
    return {"version": VERSION, "slot_id": request.get("slot_id"),
            "condition_id": request.get("condition_id"), "quiescent": not errors,
            "owned_container_ids": tracking["owned_container_ids"], "cleanup_errors": errors,
            "create_result_unknown": tracking["create_result_unknown"],
            "scorer_phase": tracking["phase"], "other_containers_affected": False}


def score_request(request):
    proof_path = Path(request["quiescence_output"]).resolve()
    if not proof_path.is_relative_to(ROOT / "runs/software-benchmark-v056") or proof_path.exists():
        raise ValueError("Each fresh score requires its own v056 quiescence receipt")
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
                    scoring_cpuset_cpus=request["scoring_cpuset_cpus"])
    identity_sha = base.sha256(base.canonical(identity))
    run_id = "v056-" + request["condition_id"].lower() + "-" + identity_sha[:40]
    root = Path(request["trusted_output_root"]).resolve()
    if not root.is_relative_to(ROOT / "runs/software-benchmark-v056"):
        raise ValueError("Fresh v056 scoring cannot reuse historical output roots")
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
            "cpuset_cpus": request["scoring_cpuset_cpus"]}
        restricted = base.LocalDocker(client, spec.image, LIMITS)
        restricted.containers = TrackedContainers(client.containers, spec.image, LIMITS, observation,
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
                   "actor_feedback": False, "model_calls": 0, "preparation_only": False}
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
