"""Complete public repository snapshots for the v054 managed single agent.

Capture an exclusively owned, already isolated actor-visible checkout. No task
patch, hidden tests, filename allowlist, or gold-derived editable set is read.
The host stores complete trees; model-facing tools must page their metadata and
text instead of rendering this bundle in the prompt. Resource ceilings reject
the whole preparation and are deployment limits, never sampling/truncation.
"""
from __future__ import annotations

import base64
import binascii
from collections import deque
import copy
import json
import os
from pathlib import Path, PurePosixPath
import stat

from .storage import digest, json_bytes

VERSION = "repository-sources-v054"
MANIFEST_VERSION = "repository-source-manifest-v054"
TREE_VERSION = "repository-tree-manifest-v054"
POLICY_VERSION = "repository-file-policy-v054"
DEFAULT_POLICY = {
    "version": POLICY_VERSION,
    "readonly_paths": [],
    "readonly_prefixes": [],
    "max_files": None,
    "max_source_bytes": 1024**3,
    "max_file_bytes": 256 * 1024**2,
}


class RepositorySourceError(ValueError):
    def __init__(self, message, *, code="invalid_repository_tree", category="source_integrity"):
        super().__init__(message)
        self.code = code
        self.category = category


def validate_path(path):
    if (not isinstance(path, str) or not path or "\0" in path or "\\" in path
            or any(part in ("", ".", "..", ".git") for part in path.split("/"))
            or PurePosixPath(path).is_absolute()):
        raise RepositorySourceError("Expected a normalized repository-relative path without .git")
    try:
        path.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise RepositorySourceError("Repository paths must be UTF-8 representable") from exc
    return path


def normalize_policy(policy=None):
    if policy is not None and (not isinstance(policy, dict) or set(policy) - set(DEFAULT_POLICY)):
        raise RepositorySourceError("Unknown repository deployment policy fields")
    result = {**copy.deepcopy(DEFAULT_POLICY), **copy.deepcopy(policy or {})}
    if result["version"] != POLICY_VERSION:
        raise RepositorySourceError("Unknown repository deployment policy version")
    for name in ("max_files", "max_source_bytes", "max_file_bytes"):
        value = result[name]
        if value is not None and (type(value) is not int or value <= 0):
            raise RepositorySourceError(f"{name} must be a positive integer or null")
    for name in ("readonly_paths", "readonly_prefixes"):
        values = result[name]
        if not isinstance(values, list) or any(not isinstance(path, str) for path in values):
            raise RepositorySourceError(f"{name} must contain relative paths")
        normalized = [validate_path(path.rstrip("/") if name == "readonly_prefixes" else path)
                      for path in values]
        if len(normalized) != len(set(normalized)):
            raise RepositorySourceError(f"Duplicate {name}")
        result[name] = sorted(normalized)
    return result


def is_readonly(path, policy):
    return (path in policy["readonly_paths"]
            or any(path == prefix or path.startswith(prefix + "/")
                   for prefix in policy["readonly_prefixes"]))


def _validate_link(path, target):
    if (not target or "\0" in target or "\\" in target
            or PurePosixPath(target).is_absolute()):
        raise RepositorySourceError("Symlinks must have relative repository-contained targets")
    parts = list(PurePosixPath(path).parent.parts)
    for part in target.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise RepositorySourceError("Symlink target escapes the repository")
            parts.pop()
        else:
            if part == ".git":
                raise RepositorySourceError("Symlink target exposes .git metadata")
            parts.append(part)


def decode_entry(path, text, metadata):
    validate_path(path)
    if not isinstance(text, str) or not isinstance(metadata, dict):
        raise RepositorySourceError("Every entry needs an explicit string and file metadata")
    if set(metadata) != {"kind", "encoding", "mode"}:
        raise RepositorySourceError("Entry metadata must contain exactly kind, encoding, mode")
    kind, encoding, mode = (metadata[key] for key in ("kind", "encoding", "mode"))
    if kind == "symlink":
        if encoding != "symlink-target" or mode != "120000":
            raise RepositorySourceError("Invalid symlink encoding or mode")
        _validate_link(path, text)
    elif kind != "file" or encoding not in ("utf-8", "base64") or mode not in ("100644", "100755"):
        raise RepositorySourceError("Unsupported repository entry type, encoding or mode")
    try:
        if encoding == "base64":
            raw = base64.b64decode(text, validate=True)
            if base64.b64encode(raw).decode("ascii") != text:
                raise RepositorySourceError("Binary entries require canonical base64")
            return raw
        raw = text.encode("utf-8")
    except (UnicodeEncodeError, ValueError, binascii.Error) as exc:
        raise RepositorySourceError("Invalid encoded repository content") from exc
    if encoding == "utf-8" and b"\0" in raw:
        raise RepositorySourceError("NUL-containing files must use binary encoding")
    return raw


def _ceiling(name, observed, policy):
    maximum = policy[name]
    if maximum is not None and observed > maximum:
        raise RepositorySourceError(
            f"Repository deployment limit {name} exceeded: {observed} > {maximum}; no files truncated",
            code=name + "_exceeded", category="deployment_limit")


def _validate_link_graph(files, entry_metadata):
    """Resolve link components, including '..' after an intermediate symlink."""
    links = {path for path, item in entry_metadata.items() if item["kind"] == "symlink"}
    for path in links:
        pending = deque([*PurePosixPath(path).parent.parts, *files[path].split("/")])
        resolved, expansions = [], 0
        while pending:
            part = pending.popleft()
            if part in ("", "."):
                continue
            if part == "..":
                if not resolved:
                    raise RepositorySourceError("Symlink chain escapes the repository")
                resolved.pop()
                continue
            candidate = "/".join([*resolved, part])
            if candidate in links:
                expansions += 1
                if expansions > 40:
                    raise RepositorySourceError(
                        "Symlink chain exceeds deployment resolution limit",
                        code="symlink_resolution_limit", category="deployment_limit")
                pending.extendleft(reversed(files[candidate].split("/")))
            else:
                resolved.append(part)


def validate_tree(files, entry_metadata, policy=None):
    policy = normalize_policy(policy)
    if not isinstance(files, dict) or not isinstance(entry_metadata, dict):
        raise RepositorySourceError("Repository files and entry_metadata must be maps")
    if set(files) != set(entry_metadata):
        raise RepositorySourceError("Every repository entry must have exactly one metadata record")
    _ceiling("max_files", len(files), policy)
    total = 0
    for path, text in files.items():
        raw = decode_entry(path, text, entry_metadata[path])
        _ceiling("max_file_bytes", len(raw), policy)
        total += len(raw)
        _ceiling("max_source_bytes", total, policy)
        if any(str(parent) in files for parent in PurePosixPath(path).parents if str(parent) != "."):
            raise RepositorySourceError("A repository entry cannot be an ancestor of another entry")
    _validate_link_graph(files, entry_metadata)


def tree_manifest(files, entry_metadata):
    entries = []
    for path in sorted(files):
        raw = decode_entry(path, files[path], entry_metadata[path])
        entries.append({"path": path, **entry_metadata[path],
                        "size_bytes": len(raw), "sha256": digest(raw)})
    return {"version": TREE_VERSION, "entries": entries, "entry_count": len(entries),
            "total_bytes": sum(row["size_bytes"] for row in entries),
            "tree_sha256": digest(json_bytes(entries))}


def snapshot_repository(source_root, *, file_policy=None, gitlinks=None):
    """Read all ordinary files and symlinks, excluding Git control metadata.

    No link is traversed and no suffix, hidden filename, size or gold-dependent
    selection is used. The caller must prevent concurrent source writers.
    """
    root = Path(source_root).resolve(strict=True)
    if not root.is_dir():
        raise RepositorySourceError("The public repository root must be a directory")
    policy = normalize_policy(file_policy)
    from .software_benchmark_gitlinks_v054 import bind_gitlinks
    links = bind_gitlinks(root, gitlinks)
    files, metadata = {}, {}
    total = 0
    for folder, directories, names in os.walk(root, topdown=True, followlinks=False):
        directory = Path(folder)
        paths = []
        for name in sorted(directories):
            child = directory / name
            if name == ".git":
                directories.remove(name)
            elif child.is_symlink():
                directories.remove(name)
                paths.append(child)
        for name in sorted(names):
            if name == ".git":
                continue
            paths.append(directory / name)
        directories.sort()
        for path in sorted(paths):
            relative = validate_path(path.relative_to(root).as_posix())
            before = path.lstat()
            _ceiling("max_files", len(files) + 1, policy)
            _ceiling("max_file_bytes", before.st_size, policy)
            _ceiling("max_source_bytes", total + before.st_size, policy)
            if stat.S_ISLNK(before.st_mode):
                text = os.readlink(path)
                item = {"kind": "symlink", "encoding": "symlink-target", "mode": "120000"}
                raw = decode_entry(relative, text, item)
            elif stat.S_ISREG(before.st_mode):
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(descriptor, "rb") as handle:
                    opened = os.fstat(handle.fileno())
                    if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                        raise RepositorySourceError("Repository changed while opening a file")
                    # One extra byte detects growth without unbounded allocation.
                    ceiling = policy["max_file_bytes"]
                    total_remaining = (None if policy["max_source_bytes"] is None
                                       else policy["max_source_bytes"] - total)
                    bounds = [value for value in (ceiling, total_remaining) if value is not None]
                    raw = handle.read(min(bounds) + 1 if bounds else -1)
                try:
                    text = raw.decode("utf-8")
                    encoding = "utf-8" if b"\0" not in raw else "base64"
                except UnicodeDecodeError:
                    encoding = "base64"
                if encoding == "base64":
                    text = base64.b64encode(raw).decode("ascii")
                item = {"kind": "file", "encoding": encoding,
                        "mode": "100755" if before.st_mode & 0o111 else "100644"}
            else:
                raise RepositorySourceError(
                    f"Unsupported special repository entry: {relative}",
                    code="unsupported_special_file", category="deployment_limit")
            _ceiling("max_file_bytes", len(raw), policy)
            total += len(raw)
            _ceiling("max_source_bytes", total, policy)
            after = path.lstat()
            if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_mode)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_mode)):
                raise RepositorySourceError("Repository changed during source capture")
            files[relative], metadata[relative] = text, item
    validate_tree(files, metadata, policy)
    return {"files": dict(sorted(files.items())), "entry_metadata": dict(sorted(metadata.items())),
            "tree": tree_manifest(files, metadata), "file_policy": policy,
            "capture_scope": "complete_preisolated_public_worktree",
            "excluded_control_metadata": [".git at every repository depth"],
            "gitlinks": links, "truncated": False}


def _validate_identity(task_id, problem_statement, source_identity):
    if not isinstance(task_id, str) or not task_id or not isinstance(problem_statement, str) or not problem_statement.strip():
        raise RepositorySourceError("A task identity and original problem statement are required")
    if (not isinstance(source_identity, dict)
            or set(source_identity) != {"instance_id", "repo", "base_commit", "dataset_revision"}
            or any(not isinstance(value, str) or not value for value in source_identity.values())):
        raise RepositorySourceError("Only public dataset/repository identity belongs in this source manifest")
    if source_identity["instance_id"] != task_id:
        raise RepositorySourceError("The captured task must retain its original instance_id")


def capture_repository(source_root, snapshot_root, *, task_id, problem_statement,
                       source_identity, file_policy=None, gitlinks=None):
    """Persist one complete source snapshot and return its manifest path."""
    _validate_identity(task_id, problem_statement, source_identity)
    snapshot = snapshot_repository(source_root, file_policy=file_policy, gitlinks=gitlinks)
    output = Path(snapshot_root).resolve()
    if output == Path(source_root).resolve() or Path(source_root).resolve() in output.parents:
        raise RepositorySourceError("Snapshot storage must be outside the captured public repository")
    output.mkdir(parents=True, exist_ok=False)
    payload = json_bytes(snapshot)
    (output / "initial-tree.json").write_bytes(payload)
    manifest = {"version": MANIFEST_VERSION, "tasks": [{
        "task_id": task_id, "problem_statement": problem_statement,
        "source_identity": copy.deepcopy(source_identity), "file_policy": snapshot["file_policy"],
        "initial_tree": {"path": "initial-tree.json", "sha256": digest(payload), "bytes": len(payload)},
        "tree_sha256": snapshot["tree"]["tree_sha256"],
    }]}
    manifest_path = output / "source-manifest.json"
    manifest_path.write_bytes(json_bytes(manifest))
    return manifest_path


class RepositorySources:
    """Provider for v054 managed S1; hidden judging is a separate backend."""
    def __init__(self, manifest_path, *, runner=None, expected_manifest_sha256=None):
        path = Path(manifest_path)
        if path.is_dir():
            path = path / "source-manifest.json"
        self.root = path.resolve().parent
        payload = path.read_bytes()
        self.manifest_sha256 = digest(payload)
        if expected_manifest_sha256 is not None and expected_manifest_sha256 != self.manifest_sha256:
            raise RepositorySourceError("The repository manifest identity changed")
        manifest = json.loads(payload)
        if manifest.get("version") != MANIFEST_VERSION or not manifest.get("tasks"):
            raise RepositorySourceError("Expected a nonempty v054 repository source manifest")
        self.runner, self._cases = runner, {}
        for row in manifest["tasks"]:
            task_id = row["task_id"]
            _validate_identity(task_id, row["problem_statement"], row["source_identity"])
            if task_id in self._cases:
                raise RepositorySourceError("Duplicate repository task identity")
            reference = row["initial_tree"]
            relative = validate_path(reference["path"])
            source = (self.root / relative).resolve()
            if self.root not in source.parents or source.is_symlink():
                raise RepositorySourceError("Repository snapshot reference escapes its root")
            body = source.read_bytes()
            if len(body) != reference["bytes"] or digest(body) != reference["sha256"]:
                raise RepositorySourceError("The complete repository snapshot changed")
            snapshot = json.loads(body)
            from .software_benchmark_gitlinks_v054 import checked_gitlinks
            gitlinks = checked_gitlinks(snapshot.get("gitlinks", []))
            policy = normalize_policy(row["file_policy"])
            files, metadata = snapshot["files"], snapshot["entry_metadata"]
            validate_tree(files, metadata, policy)
            observed = tree_manifest(files, metadata)
            if (observed != snapshot["tree"] or observed["tree_sha256"] != row["tree_sha256"]
                    or snapshot["file_policy"] != policy or snapshot.get("truncated") is not False
                    or snapshot.get("capture_scope") != "complete_preisolated_public_worktree"):
                raise RepositorySourceError("The repository manifest does not bind a complete tree")
            self._cases[task_id] = {"row": copy.deepcopy(row), "files": files, "entry_metadata": metadata,
                                    "file_policy": policy, "tree": observed,
                                    "gitlinks": gitlinks}
        self.case_ids = tuple(self._cases)

    def _entry(self, case_id):
        if case_id not in self._cases:
            raise RepositorySourceError("Unknown repository task")
        return self._cases[case_id]

    def gitlink_descriptors(self, case_id):
        from .software_benchmark_gitlinks_v054 import checked_gitlinks
        return checked_gitlinks(self._entry(case_id)["gitlinks"])

    def build_case(self, case_id):
        entry = self._entry(case_id)
        row, policy = entry["row"], entry["file_policy"]
        identity = row["source_identity"]
        source = {
            "source_kind": "complete_public_repository_worktree",
            "source_asset_ids": [case_id],
            "source_environment_asset_ids": [identity["repo"] + "@" + identity["base_commit"]],
            "source_revision": identity["base_commit"], "source_environment": identity["repo"],
            "dataset_revision": identity["dataset_revision"],
            "source_manifest_sha256": self.manifest_sha256,
            "complete_delivery_requires": ["original_issue", "immutable_final_candidate", "official_judge"],
            "public_file_access": "paged_repository_manifest_and_text",
            "hidden_judge_material_in_source_provider": False,
            "public_tests_are_hidden_judge": False,
            "initial_code_model_generated": False, "forced_initial_failure_feedback": False,
            "training_eligible": False,
        }
        return {
            "version": VERSION, "task_id": case_id, "family": identity["repo"],
            "purpose": "software_benchmark_v054", "files": copy.deepcopy(entry["files"]),
            "entry_metadata": copy.deepcopy(entry["entry_metadata"]),
            "editable_paths": [path for path in sorted(entry["files"]) if not is_readonly(path, policy)],
            "file_policy": copy.deepcopy(policy), "root_goal": row["problem_statement"],
            "source_contract": source,
            "initial_binding": {"initial_tree_sha256": row["tree_sha256"],
                                "initial_files_sha256": digest(json_bytes(entry["files"])),
                                "source_manifest_sha256": self.manifest_sha256},
        }

    def validate_files(self, case_id, files, *, entry_metadata=None):
        entry = self._entry(case_id)
        if entry_metadata is None:
            raise RepositorySourceError("v054 candidates must carry complete entry_metadata")
        policy = entry["file_policy"]
        validate_tree(files, entry_metadata, policy)
        from .software_benchmark_gitlinks_v054 import check_gitlink_payload
        check_gitlink_payload(files, entry["gitlinks"])
        for path in set(files) | set(entry["files"]):
            if is_readonly(path, policy) and (
                    path not in files or path not in entry["files"]
                    or files[path] != entry["files"][path]
                    or entry_metadata[path] != entry["entry_metadata"][path]):
                raise RepositorySourceError("Read-only repository content or metadata changed",
                                            code="readonly_path", category="policy_error")

    def runner_spec(self, case_id):
        entry = self._entry(case_id)
        return {"version": VERSION, "task_id": case_id,
                "source_identity": copy.deepcopy(entry["row"]["source_identity"]),
                "source_manifest_sha256": self.manifest_sha256,
                "initial_tree_sha256": entry["row"]["tree_sha256"],
                "file_policy": copy.deepcopy(entry["file_policy"]),
                "scope": "public repository tests only; no hidden judge data"}

    def run_public_tests(self, case_id, files, *, run_root, entry_metadata=None):
        self.validate_files(case_id, files, entry_metadata=entry_metadata)
        if self.runner is None:
            raise RuntimeError("No confined public repository test runner is bound")
        result = self.runner(files=copy.deepcopy(files), entry_metadata=copy.deepcopy(entry_metadata),
                             task=self.runner_spec(case_id), run_root=Path(run_root))
        expected = tree_manifest(files, entry_metadata)["tree_sha256"]
        if (not isinstance(result, dict)
                or result.get("execution", {}).get("input_tree_sha256") != expected):
            raise RepositorySourceError("Public test receipt does not bind the complete candidate tree")
        return result
