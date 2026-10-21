"""Read-only native final artifacts: symlink targets are opaque Git blob bytes.

This module is not a PROJECT repository provider and never materializes or
follows candidate links. Every entry path remains normalized and repository
relative. Only ordinary files and Git mode-120000 links are exported.
"""
from __future__ import annotations

import base64
import binascii
import copy
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile

from .repository_sources_v054 import (
    RepositorySourceError, TREE_VERSION, _ceiling, _validate_identity,
    decode_entry, normalize_policy, validate_path,
)
from .software_benchmark_candidates_v054 import _git, changed_paths, reference
from .storage import digest, json_bytes

PROTOCOL = "v054-native-final-artifact-opaque-links-r1"


def decode_native_entry(path, text, metadata):
    validate_path(path)
    if not isinstance(text, str) or not isinstance(metadata, dict):
        raise RepositorySourceError("Native artifacts require explicit content and metadata")
    if metadata.get("kind") != "symlink":
        return decode_entry(path, text, metadata)
    if (set(metadata) != {"kind", "encoding", "mode"} or metadata["mode"] != "120000"
            or metadata["encoding"] not in {"symlink-target", "base64-symlink-target"}):
        raise RepositorySourceError("Invalid native symlink blob metadata")
    try:
        raw = (base64.b64decode(text, validate=True) if metadata["encoding"] == "base64-symlink-target"
               else text.encode("utf-8"))
    except (UnicodeEncodeError, ValueError, binascii.Error) as error:
        raise RepositorySourceError("Invalid encoded native symlink target") from error
    if not raw or b"\0" in raw:
        raise RepositorySourceError("A native symlink target must be nonempty and NUL-free")
    if (metadata["encoding"] == "base64-symlink-target"
            and base64.b64encode(raw).decode("ascii") != text):
        raise RepositorySourceError("Native link bytes require canonical base64")
    return raw


def validate_native_tree(files, metadata, policy=None):
    policy = normalize_policy(policy)
    if not isinstance(files, dict) or not isinstance(metadata, dict) or set(files) != set(metadata):
        raise RepositorySourceError("Native artifacts require one metadata record per path")
    _ceiling("max_files", len(files), policy)
    total = 0
    for path, text in files.items():
        raw = decode_native_entry(path, text, metadata[path])
        _ceiling("max_file_bytes", len(raw), policy)
        total += len(raw)
        _ceiling("max_source_bytes", total, policy)
        if any(str(parent) in files for parent in PurePosixPath(path).parents if str(parent) != "."):
            raise RepositorySourceError("A native artifact entry cannot be another entry's ancestor")


def native_tree_manifest(files, metadata):
    entries = []
    for path in sorted(files):
        raw = decode_native_entry(path, files[path], metadata[path])
        entries.append({"path": path, **metadata[path], "size_bytes": len(raw), "sha256": digest(raw)})
    return {"version": TREE_VERSION, "entries": entries, "entry_count": len(entries),
            "total_bytes": sum(row["size_bytes"] for row in entries),
            "tree_sha256": digest(json_bytes(entries))}


def _native_tree(bundle, policy=None):
    validate_native_tree(bundle["files"], bundle["entry_metadata"], policy)
    return native_tree_manifest(bundle["files"], bundle["entry_metadata"])


def snapshot_native_candidate(source_root, *, file_policy=None, gitlinks=None):
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
                raw_target = os.readlink(os.fsencode(path))
                try:
                    text, encoding = raw_target.decode("utf-8"), "symlink-target"
                except UnicodeDecodeError:
                    text, encoding = base64.b64encode(raw_target).decode("ascii"), "base64-symlink-target"
                item = {"kind": "symlink", "encoding": encoding, "mode": "120000"}
                raw = decode_native_entry(relative, text, item)
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
    validate_native_tree(files, metadata, policy)
    return {"files": dict(sorted(files.items())), "entry_metadata": dict(sorted(metadata.items())),
            "tree": native_tree_manifest(files, metadata), "file_policy": policy,
            "capture_scope": "complete_closed_native_worktree_opaque_symlink_targets",
            "native_artifact_protocol": PROTOCOL, "symlink_targets_followed": False,
            "excluded_control_metadata": [".git at every repository depth"],
            "gitlinks": links, "truncated": False}


def capture_native_candidate(source_root, snapshot_root, *, task_id, problem_statement,
                       source_identity, file_policy=None, gitlinks=None):
    """Persist an inert native candidate bundle, never a writable PROJECT source."""
    _validate_identity(task_id, problem_statement, source_identity)
    snapshot = snapshot_native_candidate(source_root, file_policy=file_policy, gitlinks=gitlinks)
    output = Path(snapshot_root).resolve()
    if output == Path(source_root).resolve() or Path(source_root).resolve() in output.parents:
        raise RepositorySourceError("Snapshot storage must be outside the captured public repository")
    output.mkdir(parents=True, exist_ok=False)
    payload = json_bytes(snapshot)
    (output / "initial-tree.json").write_bytes(payload)
    manifest = {"version": PROTOCOL, "tasks": [{
        "task_id": task_id, "problem_statement": problem_statement,
        "source_identity": copy.deepcopy(source_identity), "file_policy": snapshot["file_policy"],
        "initial_tree": {"path": "initial-tree.json", "sha256": digest(payload), "bytes": len(payload)},
        "tree_sha256": snapshot["tree"]["tree_sha256"],
    }]}
    manifest_path = output / "source-manifest.json"
    manifest_path.write_bytes(json_bytes(manifest))
    return manifest_path


def export_native_git_patch(baseline, candidate, path, *, policy=None, gitlinks=None):
    """Write a binary-capable patch and verify its exact index-tree round trip.

    Raw blobs bypass attributes, clean filters and newline conversion. The
    temporary bare repository has no project history, hooks or network access
    commands. It exists only to encode and verify this candidate artifact.
    """
    before_manifest, after_manifest = _native_tree(baseline, policy), _native_tree(candidate, policy)
    path = Path(path)
    with tempfile.TemporaryDirectory(prefix="proworksim-v054-candidate-") as temporary:
        temporary = Path(temporary)
        repo, payloads = temporary / "git", temporary / "payloads"
        repo.mkdir()
        payloads.mkdir()
        _git(repo, ["init", "--bare", "--quiet", "--template="])
        blobs = {}
        for bundle, manifest in ((baseline, before_manifest), (candidate, after_manifest)):
            for entry in manifest["entries"]:
                sha = entry["sha256"]
                if sha not in blobs:
                    payload = payloads / sha
                    payload.write_bytes(decode_native_entry(
                        entry["path"], bundle["files"][entry["path"]],
                        bundle["entry_metadata"][entry["path"]]))
                    blobs[sha] = payload
        ordered = sorted(blobs)
        object_ids = _git(
            repo, ["hash-object", "-w", "--no-filters", "--stdin-paths"],
            data="".join(str(blobs[sha]) + "\n" for sha in ordered).encode()).decode().splitlines()
        if len(object_ids) != len(ordered):
            raise ValueError("Git did not preserve the complete blob inventory")
        object_ids = dict(zip(ordered, object_ids, strict=True))

        def index_tree(manifest):
            _git(repo, ["read-tree", "--empty"])
            records = b"".join(
                (entry["mode"] + " " + object_ids[entry["sha256"]] + "\t").encode()
                + entry["path"].encode("utf-8") + b"\0"
                for entry in manifest["entries"])
            _git(repo, ["update-index", "-z", "--index-info"], data=records)
            return _git(repo, ["write-tree"]).decode().strip()

        before_tree, after_tree = index_tree(before_manifest), index_tree(after_manifest)
        with path.open("xb") as stream:
            _git(repo, [
                "diff", "--binary", "--full-index", "--no-renames", "--no-ext-diff",
                "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/",
                before_tree, after_tree, "--",
            ], stdout=stream)
            stream.flush()
            os.fsync(stream.fileno())
        _git(repo, ["read-tree", before_tree])
        if before_tree != after_tree:
            _git(repo, ["apply", "--cached", "--binary", "--", str(path.resolve())])
        if _git(repo, ["write-tree"]).decode().strip() != after_tree:
            raise ValueError("Exported patch failed exact binary/mode/symlink round trip")
    result = {
        "patch": reference(path), "base_git_tree": before_tree,
        "candidate_git_tree": after_tree, "round_trip_verified": True,
        "base_tree_sha256": before_manifest["tree_sha256"],
        "candidate_tree_sha256": after_manifest["tree_sha256"],
        **changed_paths(baseline, candidate),
        "rename_representation": "delete-and-add; exact target bytes and modes retained",
        "binary_patch": True, "editable_path_filter_used": False,
        "native_artifact_protocol": PROTOCOL, "symlink_targets_followed": False,
    }
    from .software_benchmark_gitlinks_v054 import annotate_patch
    return annotate_patch(result, baseline.get("gitlinks", []) if gitlinks is None else gitlinks,
                          baseline, candidate)
