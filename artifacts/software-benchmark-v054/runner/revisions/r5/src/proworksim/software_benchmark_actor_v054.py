"""Public-only v054 Docker/source preparation; no native SDK sandbox claim.

The caller supplies only the public task projection and admitted image evidence.
This module never loads the complete dataset, hidden evaluation scripts or gold.
Native REF/MATCH SDK execution remains a separate admission gate.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import time
import uuid

from .repository_sources_v054 import (
    RepositorySources, capture_repository, decode_entry, normalize_policy,
    tree_manifest, validate_tree,
)
from .software_benchmark_candidates_v054 import materialize_tree

VERSION = "software-benchmark-actor-v054"
REVISION = "78f471bf655a3137b2e8a75af1501690ec009ec3"
PUBLIC_FIELDS = {"instance_id", "repo", "base_commit", "image", "problem_statement"}


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            + "\n").encode()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def checked_public_task(task):
    if set(task) != PUBLIC_FIELDS or any(not isinstance(task[key], str) for key in PUBLIC_FIELDS):
        raise ValueError("Actor input must be the exact public five-field projection")
    if any(not task[key] for key in PUBLIC_FIELDS):
        raise ValueError("Public task identity or problem is empty")
    return dict(task)


def admission(task, image, preflight, *, limits):
    task = checked_public_task(task)
    if (image["instance_id"] != task["instance_id"]
            or image["base_commit"] != task["base_commit"]
            or image["image_name"] + ":" + image["tag"] != task["image"]
            or image.get("status") != "loaded"
            or image["image_id"] != image["config_digest"]
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", image["image_id"])
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", image.get("manifest_digest", ""))
            or image.get("platform") != {"os": "linux", "architecture": "amd64"}):
        raise ValueError("An immutable, locally loaded image for this task is required")
    if (preflight.get("image_id") != image["image_id"]
            or preflight.get("base_commit") != task["base_commit"]):
        raise ValueError("Preflight belongs to another image or baseline")
    if (preflight.get("status") != "bounded_preflight_passed"
            or preflight.get("network") != "none" or preflight.get("read_only") is not True):
        raise ValueError("The bounded actor preflight has not passed")
    observed = preflight.get("details", {})
    # Accept only the full current preflight contract, not an older partial one.
    for key in ("future_reachable_commit_count", "future_reflog_commit_count",
                "unreachable_nonancestor_commit_count", "git_connectivity_fsck_returncode"):
        if observed.get(key) != 0:
            raise ValueError("Actor Git-history isolation is not admitted: " + key)
    if (observed.get("head_matches_base") is not True
            or observed.get("working_tree_clean") is not True):
        raise ValueError("Actor checkout is not at the prescribed baseline")
    if observed.get("target_package_copy_paths") != []:
        raise ValueError("Target-package copies require evidence-based isolation before actor use")
    if not isinstance(observed.get("public_python"), str):
        raise ValueError("The public test interpreter is not admitted")
    if not observed["public_python"].startswith("/"):
        raise ValueError("The public test interpreter must use its explicit image path")
    if limits.get("network") != "none":
        raise ValueError("Actor network must be disabled")
    for key in ("cpus", "memory_bytes", "pids_limit", "public_test_timeout_seconds"):
        if type(limits.get(key)) is not int or limits[key] <= 0:
            raise ValueError("Explicit actor resource limits required")
    return {
        "version": VERSION, "task": task, "image": dict(image),
        "preflight_sha256": sha256(canonical(preflight)), "limits": dict(limits),
        "public_python": observed["public_python"],
        "official_grading_image_modified": False,
        "host_mounts": [], "docker_socket_visible_to_actor": False,
        "additional_sdk_dependencies_mounted": False,
        "native_sdk_execution_admitted": False,
        "native_pending_reason": (
            "Official FileEditor reads absolute paths. A separate, verified SDK "
            "dependency/control boundary is required before native execution."),
    }


def _archive_name(name, prefix):
    name = name.removeprefix("./")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != prefix:
        raise ValueError("Repository archive member escapes its declared root")
    return "/".join(path.parts[1:])


def bundle_from_archive(stream, *, prefix="testbed", file_policy=None):
    """Decode a complete Docker public checkout without filesystem extraction."""
    policy = normalize_policy(file_policy)
    files, metadata, deferred = {}, {}, []
    total = 0
    with tarfile.open(fileobj=stream, mode="r|*") as archive:
        for entry in archive:
            name = _archive_name(entry.name, prefix)
            if not name or ".git" in PurePosixPath(name).parts:
                continue
            if entry.isdir():
                continue
            if name in files or any(name == item[0] for item in deferred):
                raise ValueError("Duplicate repository archive entry")
            if entry.islnk():
                deferred.append((name, _archive_name(entry.linkname, prefix), entry.mode))
                continue
            if entry.issym():
                files[name] = entry.linkname
                metadata[name] = {"kind": "symlink", "encoding": "symlink-target", "mode": "120000"}
                total += len(entry.linkname.encode())
            elif entry.isfile():
                if policy["max_file_bytes"] and entry.size > policy["max_file_bytes"]:
                    raise ValueError("Repository file deployment limit exceeded; no truncation")
                total += entry.size
                if policy["max_source_bytes"] and total > policy["max_source_bytes"]:
                    raise ValueError("Repository size deployment limit exceeded; no truncation")
                source = archive.extractfile(entry)
                assert source is not None
                raw = source.read()
                try:
                    text, encoding = raw.decode("utf-8"), "utf-8"
                    if b"\0" in raw:
                        raise UnicodeError
                except UnicodeError:
                    text, encoding = base64.b64encode(raw).decode("ascii"), "base64"
                files[name] = text
                metadata[name] = {
                    "kind": "file", "encoding": encoding,
                    "mode": "100755" if entry.mode & 0o111 else "100644"}
            else:
                raise ValueError("Unsupported repository device/socket entry")
            if policy["max_files"] and len(files) + len(deferred) > policy["max_files"]:
                raise ValueError("Repository count deployment limit exceeded; no truncation")
    while deferred:
        resolved = []
        for name, target, mode in deferred:
            if target in files:
                if metadata[target]["kind"] != "file":
                    raise ValueError("A hardlink must identify a regular repository file")
                files[name] = files[target]
                metadata[name] = {**metadata[target], "mode": "100755" if mode & 0o111 else "100644"}
                resolved.append((name, target, mode))
        if not resolved:
            raise ValueError("Unresolved or out-of-tree archive hardlink")
        deferred = [item for item in deferred if item not in resolved]
    validate_tree(files, metadata, policy)
    return {"files": files, "entry_metadata": metadata}


def bundle_archive(bundle, *, file_policy=None):
    """Encode every legitimate candidate entry, including binary/mode/link changes."""
    validate_tree(bundle["files"], bundle["entry_metadata"], file_policy)
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name in sorted(bundle["files"]):
            item = bundle["entry_metadata"][name]
            raw = decode_entry(name, bundle["files"][name], item)
            info = tarfile.TarInfo(name)
            info.uid = info.gid = 0
            info.mtime = 0
            if item["kind"] == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = raw.decode()
                info.mode = 0o777
                archive.addfile(info)
            else:
                info.mode = 0o755 if item["mode"] == "100755" else 0o644
                info.size = len(raw)
                archive.addfile(info, io.BytesIO(raw))
    return output.getvalue()


@dataclass
class ActorDocker:
    """Trusted host controller: no Docker socket is mounted into the container."""
    socket: str
    cli: str = "/usr/bin/docker"

    def run(self, *args, input=None, timeout=120, check=True):
        if not self.socket.startswith("unix:///"):
            raise ValueError("Only an explicit private Unix Docker endpoint is accepted")
        env = {key: value for key, value in os.environ.items()
               if key.lower() not in {"http_proxy", "https_proxy", "all_proxy"}
               and key not in {"DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"}}
        env.update(DOCKER_HOST=self.socket, NO_PROXY="*", no_proxy="*")
        return subprocess.run(
            [self.cli, "--host", self.socket, *args], input=input,
            capture_output=True, timeout=timeout, check=check, env=env)

    def create(self, environment, *, arm):
        if arm not in {"REF", "MATCH", "PROJECT"}:
            raise ValueError("Unknown arm")
        image_id = environment["image"]["image_id"]
        # Inspect, never pull/build. All three arms receive identical filesystem,
        # network, capabilities and resource settings.
        image = json.loads(self.run("image", "inspect", image_id).stdout)[0]
        if image["Id"] != image_id or image["Os"] != "linux" or image["Architecture"] != "amd64":
            raise ValueError("Local image differs from the shared actor environment")
        name = "pws-v054-actor-" + uuid.uuid4().hex
        limits = environment["limits"]
        result = self.run(
            "create", "--pull", "never", "--name", name, "--network", "none",
            "--label", "proworksim.v054.actor=" + environment["task"]["instance_id"],
            "--label", "proworksim.v054.arm=" + arm, "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--cpus", str(limits["cpus"]),
            "--memory", str(limits["memory_bytes"]), "--pids-limit", str(limits["pids_limit"]),
            "--workdir", "/testbed", "--entrypoint", "/bin/bash",
            image_id, "-c", "exec sleep infinity")
        container = result.stdout.decode().strip()
        try:
            self.run("start", container)
        except BaseException:
            self.remove(container)
            raise
        return container

    def remove(self, container):
        self.run("rm", "--force", container, check=False)

    def public_archive(self, container, destination):
        # Stream the complete checkout (including the Git directory, which the
        # decoder excludes) to disk instead of buffering its history in RAM.
        if not self.socket.startswith("unix:///"):
            raise ValueError("Only an explicit private Unix Docker endpoint is accepted")
        with Path(destination).open("xb") as output:
            subprocess.run(
                [self.cli, "--host", self.socket, "cp", container + ":/testbed", "-"],
                stdout=output, stderr=subprocess.PIPE, timeout=300, check=True,
                env={"PATH": "/usr/bin:/bin", "DOCKER_HOST": self.socket,
                     "NO_PROXY": "*", "no_proxy": "*"})


def prepare_public_source(environment, controller, destination, *, file_policy=None):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    container = controller.create(environment, arm="PROJECT")
    archive_path = destination / "initial-public-archive.tar"
    try:
        controller.public_archive(container, archive_path)
        with archive_path.open("rb") as archive:
            bundle = bundle_from_archive(archive, file_policy=file_policy)
    finally:
        controller.remove(container)
        archive_path.unlink(missing_ok=True)
    checkout = destination / "public-checkout"
    materialize_tree(bundle["files"], bundle["entry_metadata"], checkout, policy=file_policy)
    task = environment["task"]
    source_identity = {
        "instance_id": task["instance_id"], "repo": task["repo"],
        "base_commit": task["base_commit"], "dataset_revision": REVISION}
    manifest = capture_repository(
        checkout, destination / "snapshot", task_id=task["instance_id"],
        problem_statement=task["problem_statement"], source_identity=source_identity,
        file_policy=file_policy, gitlinks=environment.get("gitlinks", []))
    receipt = {
        "version": VERSION, "environment_sha256": sha256(canonical(environment)),
        "source_manifest": str(manifest), "tree": tree_manifest(**bundle),
        "native_initial_tree_source": "same immutable official image /testbed",
        "hidden_scoring_material_read": False, "model_calls": 0,
    }
    (destination / "preparation.json").write_bytes(canonical(receipt))
    return manifest


def project_public_runner(environment, controller, entry):
    """Return the managed callback for an admitted, public-only fixed command.

    ``entry`` is a separate public-repository command admission. It must never be
    populated from eval_script, F2P/P2P, test_patch or a reference solution.
    """
    if (entry.get("source") != "public_repository"
            or entry.get("admitted") is not True
            or entry.get("cwd") != "/testbed"
            or not isinstance(entry.get("argv"), list)
            or not all(isinstance(value, str) and value for value in entry["argv"])
            or entry["argv"][0] != environment["public_python"]):
        raise ValueError("An independently admitted public repository test entry is required")

    def run(*, files, entry_metadata, task, run_root):
        if task["source_identity"]["instance_id"] != environment["task"]["instance_id"]:
            raise ValueError("Public test callback task differs from its environment")
        bundle = {"files": files, "entry_metadata": entry_metadata}
        tree = tree_manifest(**bundle)
        payload = bundle_archive(bundle, file_policy=task["file_policy"])
        output = Path(run_root) / uuid.uuid4().hex
        output.mkdir(parents=True, exist_ok=False)
        container = controller.create(environment, arm="PROJECT")
        try:
            staged_git = None
            nested = [item["path"] for item in environment.get("submodules", [])]
            if nested:
                from .software_benchmark_gitlinks_v054 import NESTED_GIT_CONTROL
                staged_git = controller.run(
                    "exec", container, "/usr/bin/python3", "-I", "-c", NESTED_GIT_CONTROL,
                    "stage", "/testbed", json.dumps(nested)).stdout.decode().strip()
            controller.run(
                "exec", "--workdir", "/testbed", container, "/bin/bash", "-c",
                "find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf -- {} +")
            controller.run("cp", "-", container + ":/testbed", input=payload)
            if staged_git is not None:
                controller.run(
                    "exec", container, "/usr/bin/python3", "-I", "-c", NESTED_GIT_CONTROL,
                    "restore", "/testbed", staged_git)
            timed_out = False
            started = time.monotonic()
            try:
                result = controller.run(
                    "exec", "--workdir", "/testbed", container, *entry["argv"],
                    timeout=environment["limits"]["public_test_timeout_seconds"], check=False)
                stdout, stderr, returncode = result.stdout, result.stderr, result.returncode
            except subprocess.TimeoutExpired as error:
                stdout, stderr, returncode = error.stdout or b"", error.stderr or b"", None
                timed_out = True
            (output / "stdout.txt").write_bytes(stdout)
            (output / "stderr.txt").write_bytes(stderr)
            execution = {
                "executed": True, "command_executed": True, "returncode": returncode,
                "input_tree_sha256": tree["tree_sha256"], "scope": "public_repository_tests",
                "public_entry_sha256": sha256(canonical(entry)), "hidden_grader_called": False,
                "timed_out": timed_out, "technical_unknown": timed_out,
                "test_wall_seconds": time.monotonic() - started,
                "container_cpu_seconds": None,
            }
            group = {
                "executed": True, "passed": returncode == 0,
                "status": "technical_unknown" if timed_out else (
                    "passed" if returncode == 0 else "failed"),
                "tests": [], "execution": execution,
            }
            return {
                "execution": execution, "groups": {"repository_tests": group},
                "passed": returncode == 0, "tests": [],
                "output": (stdout + b"\n" + stderr).decode("utf-8", errors="replace"),
            }
        finally:
            controller.remove(container)

    return run


def project_provider(source_manifest, environment, controller, public_entry):
    provider = RepositorySources(source_manifest)
    if public_entry.get("source_manifest_sha256") != provider.manifest_sha256:
        raise ValueError("Public test entry is not bound to this complete public source")
    provider.runner = project_public_runner(environment, controller, public_entry)
    return provider
