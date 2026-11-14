"""Independent v055 scoring cache over the unchanged official SWE-bench scorer.

The six API conditions, immutable candidate, configuration and scoring attempt
all enter the cache identity. Actor output never includes this trusted report.
Original v054 scored results and cache directories remain untouched.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from . import software_benchmark_scorer_v054 as original
from . import software_benchmark_baseline_v054 as baseline
from .software_benchmark_baseline_v054 import validate_mapping

VERSION = "software-benchmark-scorer-v055-r1"


def installation_manifest():
    value = original.installation_manifest()
    policy = baseline.format_policy()
    return {**value, "version": VERSION, "mapped_adapter": original.file_reference(__file__),
            "baseline_validator": original.file_reference(baseline.__file__),
            "historical_git_format_policy": original.file_reference(baseline.FORMAT_POLICY),
            "historical_git_source_audits": {
                repo: original.file_reference(baseline.ROOT / item["official_source_audit"]["path"])
                for repo, item in sorted(policy["repos"].items())}}




class MappedObservedContainer(original.PreparationObservedContainer):
    def start(self, *args, **kwargs):
        result = super().start(*args, **kwargs)
        path = Path(self.preparation["path"])
        evidence = json.loads(path.read_bytes())
        mapping = self.preparation["mapping"]
        if (evidence["head_git_tree"] != mapping["official_tree"]
                or evidence["working_tree_clean"] is not True):
            raise ValueError("Actual scorer initial tree differs from the pinned official setup tree")
        evidence.update(
            dataset_base=mapping["dataset_base"], dataset_base_tree=mapping["base_tree"],
            official_setup_head=mapping["official_head"], official_setup_tree=mapping["official_tree"],
            actor_head=mapping["actor_head"], actor_tree=mapping["actor_tree"],
            mapping_sha256=self.preparation["mapping_reference"]["sha256"],
            official_setup_mapping_verified=True)
        path.write_bytes(original.canonical(evidence))
        return result


class MappedContainers(original.LocalContainers):
    def __init__(self, delegate, image_id, limits, observation):
        super().__init__(delegate, image_id, limits)
        self.observation = observation

    def create(self, **kwargs):
        return MappedObservedContainer(super().create(**kwargs), self.observation)


def condition_identity(request):
    if (not re.fullmatch(r"(REF|MATCH|PROJECT)-(thinking|nonthinking)", request.get("condition_id", ""))
            or type(request.get("thinking")) is not bool
            or request["condition_id"] != request["arm"] + ("-thinking" if request["thinking"] else "-nonthinking")
            or request.get("actor_feedback") is not False
            or request.get("model") != "deepseek-flash"
            or not request.get("slot_id", "").startswith("v055-")):
        raise ValueError("An independent six-condition slot and feedback isolation are required")
    return {key: request[key] for key in ("condition_id", "thinking", "slot_id", "model")}


def check_candidate(request):
    condition_identity(request)
    if request.get("preparation_only"):
        raise ValueError("v055 formal scorer does not reuse preparation scoring identities")
    from .software_benchmark_candidates_v054 import checked, read_episode_candidates
    if request["arm"] == "PROJECT":
        episode = read_episode_candidates(request["episode_candidate_lock"])
        endpoint = "terminal_code" if request["endpoint"] == "code" else "last_legal_delivery"
        reference = episode["lock"][endpoint]
        if reference is None:
            raise ValueError("No legal delivery candidate exists to score")
        lock = json.loads(checked(reference).read_bytes())
        exported = json.loads(checked(lock["patch_receipt"]).read_bytes())
        task_id = lock["task_id"]
    else:
        lock = json.loads(checked(request["native_candidate_lock"]).read_bytes())
        if (lock.get("version") != "software-benchmark-native-closure-v054"
                or lock.get("lock_before_grading") is not True
                or lock["slot"]["arm"] != request["arm"]):
            raise ValueError("Native candidate lacks its closed episode identity")
        exported, task_id = lock["patch_receipt"], lock["slot"]["instance_id"]
    if (task_id != request["instance_id"] or lock["tree_sha256"] != request["candidate_tree_sha256"]
            or exported["base_tree_sha256"] != request["baseline_tree_sha256"]
            or exported["patch"] != request["patch"]):
        raise ValueError("Scoring request differs from the unique closed candidate")


def scoring_output_paths(request, identity_sha):
    condition_identity(request)
    if not re.fullmatch(r"[a-f0-9]{64}", identity_sha):
        raise ValueError("A full immutable scoring identity is required")
    expected_root = Path(__file__).resolve().parents[2] / "runs/software-benchmark-v055"
    root, pointer = Path(request["trusted_output_root"]).resolve(), Path(request["receipt_output"]).resolve()
    if not root.is_relative_to(expected_root) or not pointer.is_relative_to(expected_root):
        raise ValueError("v055 scorer cannot write into another experiment")
    run_id = f"v055-{request['condition_id']}-{request['endpoint']}-{identity_sha[:40]}"
    return run_id, root / run_id, pointer


def score_request(request):
    socket = Path(request["docker_socket"]).resolve()
    if not socket.is_socket():
        raise ValueError("Private Docker socket must already exist")
    original.install_offline_guard(socket)
    import docker
    from swebench.harness.run_evaluation import run_instance
    from swebench.harness.utils import make_test_spec
    manifest = installation_manifest()
    if json.loads(original.checked_file(request["scorer_manifest"]).read_bytes()) != manifest:
        raise ValueError("Mapped scorer installation changed after preparation")
    instance = original.read_local_dataset(request["dataset"])[request["instance_id"]]
    mapping = validate_mapping(json.loads(original.checked_file(request["baseline_mapping"]).read_bytes()),
                               instance=instance, image=request["image"])
    patch = original.checked_file(request["patch"]).read_bytes()
    check_candidate(request)
    spec = make_test_spec(instance)
    if any(spec.image_assets.values()):
        raise ValueError("External scoring assets require separate pinned preparation")
    identity, _ = original.make_identity(
        instance=instance, arm=request["arm"], endpoint=request["endpoint"], patch=patch,
        candidate_tree_sha256=request["candidate_tree_sha256"],
        baseline_tree_sha256=request["baseline_tree_sha256"], dataset_reference=request["dataset"],
        scorer_manifest=manifest, image_record=request["image"], config_sha256=request["config_sha256"],
        limits=request["limits"], preparation_only=request.get("preparation_only", False),
        attempt=request.get("attempt", 1))
    identity.update(version=VERSION, baseline_mapping=request["baseline_mapping"], **condition_identity(request))
    if request.get("preparation_only"):
        identity["tree_identity_scheme"] = "preparation_pinned_official_setup_tree_mapping"
    identity_sha = original.sha256(original.canonical(identity))
    run_id, output, pointer = scoring_output_paths(request, identity_sha)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (output / "identity.json").write_bytes(original.canonical(identity))
    os.umask(0o077)
    os.chdir(output)
    for key in ("DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        os.environ.pop(key, None)
    os.environ["DOCKER_HOST"] = "unix://" + str(socket)
    cli = original.checked_file(request["docker_cli"])
    os.environ["PATH"] = str(cli.parent) + os.pathsep + "/usr/bin:/bin"
    spec.image = request["image"]["image_id"]
    prediction = {"instance_id": instance["instance_id"], "model_name_or_path": request["condition_id"],
                  "model_patch": patch.decode("utf-8")}
    client = docker.DockerClient(base_url=os.environ["DOCKER_HOST"], timeout=1800)
    try:
        observation = {"path": str(output / "initial-container.json"),
                       "base_commit": mapping["official_head"], "mapping": mapping,
                       "mapping_reference": request["baseline_mapping"]}
        restricted = original.LocalDocker(client, spec.image, request["limits"])
        restricted.containers = MappedContainers(client.containers, spec.image, request["limits"], observation)
        restricted.images.get(spec.image)
        result = run_instance(spec, prediction, restricted, run_id,
                              timeout=request["limits"]["timeout_seconds"], rewrite_reports=False,
                              skip_patch=not patch, task_repo=None)
        report = result[1].get(instance["instance_id"], {}) if result else {}
        determinate = (result is not None and report.get("patch_successfully_applied") is True
                       and not report.get("infra_failure", False) and type(report.get("resolved")) is bool)
        receipt = {"version": VERSION, "run_id": run_id, "identity_sha256": identity_sha,
                   "status": "official_report" if determinate else "technical_unknown",
                   "resolved": report["resolved"] if determinate else None, "official_result": result,
                   "model_calls": 0, "actor_feedback": False,
                   "preparation_only": request.get("preparation_only", False)}
        (output / "receipt.json").write_bytes(original.canonical(receipt))
        with pointer.open("xb") as stream:
            stream.write(original.canonical({"receipt": original.file_reference(output / "receipt.json"),
                                             "identity": original.file_reference(output / "identity.json")}))
        return receipt
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    args = parser.parse_args()
    result = score_request(json.loads(args.request.read_bytes()))
    print(json.dumps({key: result[key] for key in ("run_id", "status", "preparation_only")}))
