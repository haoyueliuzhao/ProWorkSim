"""Trusted, local-only entry to the unmodified SWE-bench 5.0.2 scorer.

Run one candidate per process. This module is never an actor tool and its input,
working directory and receipts must not be mounted in an actor workspace.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import socket
import sys

VERSION = "software-benchmark-scorer-v054"
WHEEL_SHA256 = "b7f0416a1e686eca22c2f749b5f816685a202835032f6683080e2b53545bbb62"
DATASET_REVISION = "78f471bf655a3137b2e8a75af1501690ec009ec3"
DATASET_SHA256 = "030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            + "\n").encode("utf-8")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_reference(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": sha256(data)}


def checked_file(reference):
    path = Path(reference["path"])
    if not path.is_absolute() or file_reference(path) != reference:
        raise ValueError("Changed trusted input")
    return path


def install_offline_guard(docker_socket=None):
    """Process-local denial; Docker may connect only to its private Unix socket."""
    for name in tuple(os.environ):
        if name.lower() in {"http_proxy", "https_proxy", "all_proxy"}:
            os.environ.pop(name)
    os.environ.update({
        "HF_HUB_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1",
        "PYTHON_DOTENV_DISABLED": "1", "NO_PROXY": "*", "no_proxy": "*",
    })
    expected = str(Path(docker_socket).resolve()) if docker_socket else None

    def audit(event, args):
        if event == "socket.getaddrinfo":
            raise RuntimeError("Scorer DNS/network disabled")
        if event == "socket.connect":
            sock, address = args
            if (sock.family != socket.AF_UNIX or not isinstance(address, str)
                    or expected is None or str(Path(address).resolve()) != expected):
                raise RuntimeError("Scorer socket is outside the private Docker endpoint")

    sys.addaudithook(audit)


def installation_manifest():
    """Bind installed official code and the effective dependency versions."""
    import swebench
    import swebench.harness.grading
    import swebench.harness.run_evaluation
    import swebench.harness.utils

    if importlib.metadata.version("swebench") != "5.0.2":
        raise ValueError("Requires the pinned official scorer")
    root = Path(swebench.__file__).parent
    sources = {str(path.relative_to(root)): sha256(path.read_bytes())
               for path in sorted(root.rglob("*.py"))}
    # Match import precedence: a local overlay wins over later shared packages.
    packages = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name", "").lower().replace("_", "-")
        packages.setdefault(name, distribution.version)
    return {
        "version": VERSION, "official_version": "5.0.2",
        "wheel_sha256": WHEEL_SHA256, "official_python_sources": sources,
        "effective_dependency_versions": dict(sorted(packages.items())),
        "python": sys.version, "python_executable": file_reference(sys.executable),
        "adapter": file_reference(__file__),
    }


def read_local_dataset(reference):
    path = checked_file(reference)
    if path.suffix != ".json":
        raise ValueError("Only a pinned local JSON projection is accepted")
    rows = json.loads(path.read_bytes())
    if (not isinstance(rows, list) or len(rows) != 500
            or len({row["instance_id"] for row in rows}) != 500):
        raise ValueError("The trusted projection must preserve all 500 tasks")
    return {row["instance_id"]: row for row in rows}


def make_identity(*, instance, arm, endpoint, patch, candidate_tree_sha256,
                  baseline_tree_sha256, dataset_reference, scorer_manifest,
                  image_record, config_sha256, limits, preparation_only=False,
                  attempt=1):
    if arm not in {"REF", "MATCH", "PROJECT"}:
        raise ValueError("Unknown arm")
    if endpoint not in {"code", "delivery"} or endpoint == "delivery" and arm != "PROJECT":
        raise ValueError("Invalid endpoint")
    if type(attempt) is not int or attempt < 1:
        raise ValueError("A positive, separately recorded scoring attempt is required")
    for value in (candidate_tree_sha256, baseline_tree_sha256, config_sha256):
        if not HEX64.fullmatch(value):
            raise ValueError("Full tree and configuration SHA256 are required")
    if image_record["instance_id"] != instance["instance_id"]:
        raise ValueError("Image identity belongs to another task")
    if image_record["image_name"] + ":" + image_record["tag"] != instance["image"]:
        raise ValueError("Image name differs from the fixed dataset")
    if image_record.get("status") != "loaded":
        raise ValueError("Image has not completed local loading")
    for key in ("manifest_digest", "config_digest", "image_id"):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_record.get(key) or ""):
            raise ValueError("Image is not locally admitted by immutable identity")
    if image_record["image_id"] != image_record["config_digest"]:
        raise ValueError("Local image ID differs from the admitted config")
    if image_record.get("platform") != {"os": "linux", "architecture": "amd64"}:
        raise ValueError("Unexpected image platform")
    if limits.get("network_mode") != "none":
        raise ValueError("Scoring containers must be offline")
    for key in ("timeout_seconds", "nano_cpus", "memory_bytes", "pids_limit"):
        if type(limits.get(key)) is not int or limits[key] <= 0:
            raise ValueError("Explicit positive scoring limits are required")
    identity = {
        "version": VERSION, "instance_id": instance["instance_id"], "arm": arm,
        "endpoint": endpoint, "base_commit": instance["base_commit"],
        "tree_identity_scheme": (
            "preparation_image_config_and_base_commit" if preparation_only
            else "v054_complete_repository_tree"),
        "candidate_tree_sha256": candidate_tree_sha256,
        "baseline_tree_sha256": baseline_tree_sha256, "patch_sha256": sha256(patch),
        "dataset_revision": DATASET_REVISION, "dataset_parquet_sha256": DATASET_SHA256,
        "dataset_projection": dataset_reference,
        "trusted_record_sha256": sha256(canonical(instance)),
        "scorer_manifest_sha256": sha256(canonical(scorer_manifest)),
        "wheel_sha256": WHEEL_SHA256, "image": image_record,
        "config_sha256": config_sha256, "limits": limits,
        "preparation_only": preparation_only, "attempt": attempt,
    }
    identity_sha = sha256(canonical(identity))
    return identity, f"v054-{arm}-{endpoint}-{identity_sha[:40]}"


class LocalImages:
    def __init__(self, delegate, image_id):
        self.delegate, self.image_id = delegate, image_id

    def get(self, value):
        if value != self.image_id:
            raise ValueError("Only the admitted image ID is accepted")
        image = self.delegate.get(value)
        if (image.id != self.image_id or image.attrs.get("Os") != "linux"
                or image.attrs.get("Architecture") != "amd64"):
            raise ValueError("Local Docker image differs from admission")
        return image

    def pull(self, *args, **kwargs):
        raise RuntimeError("Implicit image pull is forbidden")


class LocalContainers:
    def __init__(self, delegate, image_id, limits, preparation=None):
        self.delegate, self.image_id, self.limits = delegate, image_id, limits
        self.preparation = preparation

    def get(self, name):
        return self.delegate.get(name)

    def create(self, **kwargs):
        if kwargs["image"] != self.image_id:
            raise ValueError("Container image differs from admission")
        if kwargs.get("volumes") or kwargs.get("mounts") or kwargs.get("devices"):
            raise ValueError("No host material or GPU may be mounted into scoring")
        kwargs.update(
            network_mode="none", mem_limit=self.limits["memory_bytes"],
            nano_cpus=self.limits["nano_cpus"], pids_limit=self.limits["pids_limit"])
        container = self.delegate.create(**kwargs)
        if self.preparation is not None:
            return PreparationObservedContainer(container, self.preparation)
        return container


class PreparationObservedContainer:
    """Record the real initial tree in the same official preflight container."""
    def __init__(self, delegate, preparation):
        self.delegate, self.preparation = delegate, preparation

    def __getattr__(self, key):
        return getattr(self.delegate, key)

    def start(self, *args, **kwargs):
        result = self.delegate.start(*args, **kwargs)
        self.delegate.reload()
        observation = self.delegate.exec_run([
            "/bin/bash", "-c",
            "git -c safe.directory=/testbed -C /testbed rev-parse HEAD 'HEAD^{tree}'"
            " && git -c safe.directory=/testbed -C /testbed status --porcelain"])
        lines = observation.output.decode("utf-8", errors="replace").splitlines()
        host = self.delegate.attrs["HostConfig"]
        evidence = {
            "scope": "preparation_only_before_eval_script", "container_id": self.delegate.id,
            "image_id": self.delegate.attrs["Image"], "git_returncode": observation.exit_code,
            "head": lines[0] if len(lines) >= 2 else None,
            "head_git_tree": lines[1] if len(lines) >= 2 else None,
            "working_tree_clean": len(lines) == 2 if observation.exit_code == 0 else None,
            "host_config": {key: host.get(key) for key in (
                "NetworkMode", "Memory", "NanoCpus", "PidsLimit", "DeviceRequests",
                "Devices", "Binds")},
        }
        Path(self.preparation["path"]).write_bytes(canonical(evidence))
        if observation.exit_code != 0 or evidence["head"] != self.preparation["base_commit"]:
            raise ValueError("Preparation container baseline does not match the fixed dataset")
        return result


class LocalDocker:
    def __init__(self, delegate, image_id, limits, preparation=None):
        self.images = LocalImages(delegate.images, image_id)
        self.containers = LocalContainers(delegate.containers, image_id, limits, preparation)


def score_request(request):
    """Execute an already closed candidate; no model or actor is ever resumed."""
    socket_path = Path(request["docker_socket"]).resolve()
    if not socket_path.is_socket():
        raise ValueError("The private Docker socket must already exist")
    install_offline_guard(socket_path)
    from swebench.harness.run_evaluation import run_instance
    from swebench.harness.utils import make_test_spec
    import docker

    expected_manifest = json.loads(checked_file(request["scorer_manifest"]).read_bytes())
    actual_manifest = installation_manifest()
    if actual_manifest != expected_manifest:
        raise ValueError("Scorer installation changed after preparation")
    rows = read_local_dataset(request["dataset"])
    instance = rows[request["instance_id"]]
    patch = checked_file(request["patch"]).read_bytes()
    if request["arm"] == "PROJECT" and not request.get("preparation_only", False):
        from .software_benchmark_candidates_v054 import checked, read_episode_candidates
        episode = read_episode_candidates(request["episode_candidate_lock"])
        endpoint = "terminal_code" if request["endpoint"] == "code" else "last_legal_delivery"
        reference = episode["lock"][endpoint]
        if reference is None:
            raise ValueError("No legal delivery candidate exists to score")
        lock = json.loads(checked(reference).read_bytes())
        exported = json.loads(checked(lock["patch_receipt"]).read_bytes())
        if (lock["task_id"] != request["instance_id"]
                or lock["tree_sha256"] != request["candidate_tree_sha256"]
                or exported["base_tree_sha256"] != request["baseline_tree_sha256"]
                or exported["patch"] != request["patch"]):
            raise ValueError("Request does not identify the uniquely closed candidate")
    spec = make_test_spec(instance)
    # Verified currently needs no external multimodal assets. Never silently
    # omit assets or follow an official fallback URL if another dataset needs them.
    if any(spec.image_assets.values()):
        raise ValueError("External binary scoring assets require separate pinned preparation")
    identity, run_id = make_identity(
        instance=instance, arm=request["arm"], endpoint=request["endpoint"],
        patch=patch, candidate_tree_sha256=request["candidate_tree_sha256"],
        baseline_tree_sha256=request["baseline_tree_sha256"],
        dataset_reference=request["dataset"], scorer_manifest=actual_manifest,
        image_record=request["image"], config_sha256=request["config_sha256"],
        limits=request["limits"], preparation_only=request.get("preparation_only", False),
        attempt=request.get("attempt", 1))
    output = Path(request["trusted_output_root"]).resolve() / run_id
    # Existence is deliberately an error: even an identical retry needs a new,
    # separately identified attempt rather than official patch-blind cache reuse.
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (output / "identity.json").write_bytes(canonical(identity))
    os.umask(0o077)
    os.chdir(output)
    for key in ("DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        os.environ.pop(key, None)
    os.environ["DOCKER_HOST"] = "unix://" + str(socket_path)
    cli = checked_file(request["docker_cli"])
    os.environ["PATH"] = str(cli.parent) + os.pathsep + "/usr/bin:/bin"
    spec.image = request["image"]["image_id"]
    prediction = {"instance_id": instance["instance_id"],
                  "model_name_or_path": request["arm"], "model_patch": patch.decode("utf-8")}
    client = docker.DockerClient(base_url=os.environ["DOCKER_HOST"], timeout=1800)
    try:
        preparation = (
            {"path": str(output / "initial-container.json"),
             "base_commit": instance["base_commit"]}
            if request.get("preparation_only", False) else None)
        restricted = LocalDocker(client, spec.image, request["limits"], preparation)
        restricted.images.get(spec.image)
        result = run_instance(
            spec, prediction, restricted, run_id,
            timeout=request["limits"]["timeout_seconds"],
            rewrite_reports=False,
            # An empty candidate is still a candidate; unchanged source must be
            # tested rather than fail git-apply solely because the patch is empty.
            skip_patch=not patch, task_repo=None)
        report = result[1].get(instance["instance_id"], {}) if result else {}
        determinate = (
            result is not None and report.get("patch_successfully_applied") is True
            and not report.get("infra_failure", False)
            and type(report.get("resolved")) is bool)
        receipt = {
            "version": VERSION, "run_id": run_id,
            "identity_sha256": sha256(canonical(identity)),
            "status": "official_report" if determinate else "technical_unknown",
            "resolved": report["resolved"] if determinate else None,
            "official_result": result, "model_calls": 0, "actor_feedback": False,
            "preparation_only": request.get("preparation_only", False),
        }
        (output / "receipt.json").write_bytes(canonical(receipt))
        return receipt
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    args = parser.parse_args()
    receipt = score_request(json.loads(args.request.read_bytes()))
    print(json.dumps({key: receipt[key] for key in ("run_id", "status", "preparation_only")}))


if __name__ == "__main__":
    main()
