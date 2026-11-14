"""Explicit gitlink identity beside the complete public working-tree payload.

Gitlink OIDs are metadata of the parent repository; initialized submodule files
remain ordinary editable public files. A flattened patch-encoding tree must
never be reported as the official parent Git tree.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess


NESTED_GIT_CONTROL = r'''
import json, os, shutil, sys, tempfile
from pathlib import Path
mode, root_arg, argument = sys.argv[1:]
root=Path(root_arg).resolve()
def destination(relative):
    parts=relative.split('/')
    if not parts or any(part in ('','.', '..','.git') for part in parts) or relative.startswith('/'):
        raise ValueError('Invalid nested Git control path')
    current=root
    for part in parts:
        current=current/part
        if current.is_symlink():
            raise ValueError('Gitlink directory cannot be a symlink')
    return current/'.git'
if mode=='stage':
    staging=Path(tempfile.mkdtemp(prefix='pws-v054-git-control-'))
    paths=json.loads(argument)
    for index,relative in enumerate(paths):
        source=destination(relative)
        if not source.is_dir() or source.is_symlink():
            raise ValueError('Expected isolated nested Git directory')
        shutil.move(str(source),str(staging/str(index)))
    (staging/'paths.json').write_text(json.dumps(paths))
    print(str(staging))
elif mode=='restore':
    staging=Path(argument)
    if staging.parent!=Path(tempfile.gettempdir()) or not staging.name.startswith('pws-v054-git-control-'):
        raise ValueError('Invalid staged control directory')
    paths=json.loads((staging/'paths.json').read_text())
    for index,relative in enumerate(paths):
        target=destination(relative)
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            raise ValueError('Candidate introduced forbidden Git metadata')
        shutil.move(str(staging/str(index)),str(target))
    shutil.rmtree(str(staging))
else:
    raise ValueError('Unknown nested control operation')
'''


def checked_gitlinks(value):
    from .repository_sources_v054 import validate_path
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Gitlink descriptors must be a list")
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"path", "oid"}:
            raise ValueError("Each parent gitlink needs its path and exact commit OID")
        path = validate_path(item["path"])
        if path in seen or not re.fullmatch(r"[0-9a-f]{40}", item["oid"]):
            raise ValueError("Duplicate gitlink or invalid commit identity")
        if any(path.startswith(other + "/") or other.startswith(path + "/") for other in seen):
            raise ValueError("Parent gitlinks cannot contain one another")
        seen.add(path)
        result.append({"path": path, "oid": item["oid"]})
    return sorted(result, key=lambda item: item["path"])


def discover_gitlinks(root):
    root = Path(root)
    if not (root / ".git").exists():
        return []
    executable = shutil.which("git", path=os.defpath)
    if executable is None:
        raise RuntimeError("System Git required to inspect a real repository index")
    result = subprocess.run(
        [executable, "-c", "safe.directory=" + str(root), "-C", str(root),
         "ls-files", "--stage", "-z"], capture_output=True, check=True, timeout=60,
        env={"PATH": os.defpath, "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
             "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull})
    links = []
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        descriptor, path = entry.split(b"\t", 1)
        mode, oid, stage = descriptor.decode().split()
        if stage != "0":
            raise ValueError("Unmerged index cannot define a unique gitlink candidate")
        if mode == "160000":
            links.append({"path": path.decode("utf-8"), "oid": oid})
    return checked_gitlinks(links)


def bind_gitlinks(root, supplied=None):
    observed = discover_gitlinks(root)
    if supplied is None:
        return observed
    supplied = checked_gitlinks(supplied)
    if (Path(root) / ".git").exists() and observed != supplied:
        from .repository_sources_v054 import RepositorySourceError
        raise RepositorySourceError(
            "Changing parent gitlink identities is not represented by a working-tree patch",
            code="unsupported_gitlink_identity_change", category="deployment_limit")
    return supplied


def check_gitlink_payload(files, links):
    paths = [item["path"] for item in checked_gitlinks(links)]
    if any(prefix == path or prefix.startswith(path + "/") for prefix in paths for path in files):
        from .repository_sources_v054 import RepositorySourceError
        raise RepositorySourceError(
            "Replacing a gitlink directory with a file or symlink is unsupported",
            code="unsupported_gitlink_identity_change", category="deployment_limit")


def annotate_patch(receipt, links, baseline, candidate):
    links = checked_gitlinks(links)
    if not links:
        return receipt
    other = candidate.get("gitlinks")
    if other is not None and checked_gitlinks(other) != links:
        from .repository_sources_v054 import RepositorySourceError
        raise RepositorySourceError(
            "Candidate changes gitlink identity",
            code="unsupported_gitlink_identity_change", category="deployment_limit")
    paths = [item["path"] for item in links]
    check_gitlink_payload(candidate["files"], links)
    def covered(path):
        return any(path.startswith(prefix + "/") for prefix in paths)
    receipt["base_encoding_git_tree"] = receipt.pop("base_git_tree")
    receipt["candidate_encoding_git_tree"] = receipt.pop("candidate_git_tree")
    receipt.update(
        gitlinks=links, gitlink_oids_preserved=True,
        git_tree_identity_scope="flattened encoding of complete public files; not official parent Git tree",
        parent_git_tree_claimed=False,
        submodule_base_file_count=sum(covered(path) for path in baseline["files"]),
        submodule_candidate_file_count=sum(covered(path) for path in candidate["files"]),
        submodule_changed_paths=sorted(path for key in ("added_paths", "deleted_paths", "modified_paths")
                                       for path in receipt[key] if covered(path)),
        application_semantics="git apply to initialized public working tree; parent gitlink OIDs unchanged",
        unsupported_operations=["change, add, remove or rename parent gitlink identities"],
    )
    return receipt
