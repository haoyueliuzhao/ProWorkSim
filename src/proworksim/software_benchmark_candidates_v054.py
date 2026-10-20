"""Lossless last-submission export for the v054 managed single-agent world.

No editable-path filtering or v052 canonical tree restoration occurs here.
Content, deletions, file modes, binary payloads and symlink targets are bound
before producing a standard Git patch. No model, tests or grader are invoked.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .repository_sources_v054 import decode_entry, tree_manifest, validate_tree
from .storage import digest, json_bytes, read_json

VERSION = "software-benchmark-candidates-v054"
EPISODE_VERSION = "software-benchmark-episode-candidates-v054"


def reference(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {"path": str(path), "sha256": digest(data), "bytes": len(data)}


def write_new(path, value):
    path = Path(path)
    data = value if isinstance(value, bytes) else json_bytes(value)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return reference(path)


def checked(value):
    path = Path(value["path"])
    if not path.is_absolute() or reference(path) != value:
        raise ValueError("Immutable v054 candidate evidence changed")
    return path


def _tree(bundle, policy=None):
    files, metadata = bundle["files"], bundle["entry_metadata"]
    validate_tree(files, metadata, policy)
    return tree_manifest(files, metadata)


def changed_paths(baseline, candidate):
    """Compare the union, including absent entries and metadata-only changes."""
    before, after = baseline["files"], candidate["files"]
    before_meta, after_meta = baseline["entry_metadata"], candidate["entry_metadata"]
    return {
        "added_paths": sorted(set(after) - set(before)),
        "deleted_paths": sorted(set(before) - set(after)),
        "modified_paths": sorted(
            path for path in set(before) & set(after)
            if before[path] != after[path] or before_meta[path] != after_meta[path]),
    }


def materialize_tree(files, entry_metadata, destination, *, policy=None):
    """Write a new empty tree exactly; never follow a candidate symlink."""
    validate_tree(files, entry_metadata, policy)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    # Parents are directories in this new tree. Create links only after regular
    # files so even a valid internal symlink is never used as a write traversal.
    for kind in ("file", "symlink"):
        for name in sorted(files):
            metadata = entry_metadata[name]
            if metadata["kind"] != kind:
                continue
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = decode_entry(name, files[name], metadata)
            if kind == "symlink":
                path.symlink_to(raw.decode("utf-8"))
            else:
                with path.open("xb") as stream:
                    stream.write(raw)
                path.chmod(0o755 if metadata["mode"] == "100755" else 0o644)
    return {"path": str(destination.resolve()), **tree_manifest(files, entry_metadata)}


def _git(repo, args, *, data=None, stdout=subprocess.PIPE):
    executable = shutil.which("git", path=os.defpath)
    if executable is None:
        raise RuntimeError("A system Git executable is required for a lossless binary patch")
    # Do not inherit GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE, config, proxy or
    # external-diff environment from the project or the caller.
    environment = {
        "PATH": os.defpath, "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull, "GIT_ATTR_NOSYSTEM": "1",
    }
    process = subprocess.run(
        [executable, "-c", "core.hooksPath=" + os.devnull,
         "-c", "core.attributesFile=" + os.devnull,
         "-c", "core.autocrlf=false", "-c", "core.filemode=true", *args],
        cwd=repo, env=environment, input=data, stdout=stdout, stderr=subprocess.PIPE,
        timeout=300, check=False)
    if process.returncode:
        raise RuntimeError(
            f"Isolated Git {args[0]} failed ({process.returncode}): "
            + process.stderr[-2048:].decode("utf-8", "replace"))
    return process.stdout


def export_git_patch(baseline, candidate, path, *, policy=None):
    """Write a binary-capable patch and verify its exact index-tree round trip.

    Raw blobs bypass attributes, clean filters and newline conversion. The
    temporary bare repository has no project history, hooks or network access
    commands. It exists only to encode and verify this candidate artifact.
    """
    before_manifest, after_manifest = _tree(baseline, policy), _tree(candidate, policy)
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
                    payload.write_bytes(decode_entry(
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
    return {
        "patch": reference(path), "base_git_tree": before_tree,
        "candidate_git_tree": after_tree, "round_trip_verified": True,
        "base_tree_sha256": before_manifest["tree_sha256"],
        "candidate_tree_sha256": after_manifest["tree_sha256"],
        **changed_paths(baseline, candidate),
        "rename_representation": "delete-and-add; exact target bytes and modes retained",
        "binary_patch": True, "editable_path_filter_used": False,
    }


def _select_last_submission_locked(prepared):
    """Caller holds the World lock and has loaded its state."""
    world = prepared.world
    facts = world._software()
    if not facts["deliveries"]:
        return None
    delivery = copy.deepcopy(facts["deliveries"][-1])
    actor = delivery["actor_id"]
    source = delivery["source_reference"]
    artifact, version, bundle = world._bundle(actor, reference=source)
    if source != {"object_id": artifact["artifact_id"], "version_id": version}:
        raise ValueError("Delivery no longer identifies its exact immutable version")
    base_artifact, base_version, baseline = world._bundle(actor, baseline=True)
    base_reference = {"object_id": base_artifact["artifact_id"], "version_id": base_version}
    expected = {
        "source_reference": source, "source_sha256": digest(json_bytes(bundle)),
        "files_sha256": digest(json_bytes(bundle["files"])),
    }
    if any(delivery.get(key) != value for key, value in expected.items()):
        raise ValueError("Last delivery content differs from its immutable version")
    metadata_sha = digest(json_bytes(bundle["entry_metadata"]))
    if delivery.get("entry_metadata_sha256", metadata_sha) != metadata_sha:
        raise ValueError("Last delivery entry metadata changed")
    patches = [
        patch for patch in facts["patches"].values()
        if patch.get("author") == actor
        and all(patch.get(key) == value for key, value in expected.items())
        and patch.get("base_reference") == base_reference
        and patch.get("entry_metadata_sha256") == metadata_sha
    ]
    if not patches:
        raise ValueError("Last delivery lacks its exact fixed patch")
    changes = changed_paths(baseline, bundle)
    union = sorted(set().union(*changes.values()))
    patch = copy.deepcopy(patches[-1])
    if patch.get("changed_paths") != union or any(
            patch.get(key) != value for key, value in changes.items()):
        raise ValueError("Fixed patch omitted an addition, deletion or metadata change")
    tests = [
        event for event in world.state["software_events"]
        if event.get("kind") == "test"
        and event.get("sequence") == delivery["test_sequence"]
        and event.get("actor_id") == actor and event.get("executed") is True
        and all(event.get(key) == value for key, value in expected.items())
    ]
    if len(tests) != 1:
        raise ValueError("Last delivery lacks its same-version executed public test")
    policy = copy.deepcopy(facts["case"]["file_policy"])
    _tree(baseline, policy)
    manifest = _tree(bundle, policy)
    # The provider checks read-only entries against its full original tree.
    # It must reject violations, not silently restore or omit candidate files.
    prepared.source_provider.validate_files(
        prepared.case["case_id"], bundle["files"],
        entry_metadata=bundle["entry_metadata"])
    return {
        "task_id": prepared.case["case_id"], "baseline": copy.deepcopy(baseline),
        "candidate": copy.deepcopy(bundle), "policy": policy, "manifest": manifest,
        "binding": {
            "delivery": delivery, "fixed_patch": patch,
            "baseline_reference": base_reference, **expected,
            "entry_metadata_sha256": metadata_sha,
            "public_test_sequence": tests[0]["sequence"],
            "public_test_executed": True,
            "public_test_pass_required_for_submission": False,
            "endpoint": "last_legal_submission",
            "current_working_tree_substitution": False,
        },
    }


def select_last_submission(prepared):
    """Read the last real delivery, never substitute the later working tree."""
    world = prepared.world
    with world.store.lock():
        world.state = world.store.load()
        return _select_last_submission_locked(prepared)


def lock_last_submission(prepared, *, run_root):
    """Legacy single-endpoint API; v054 episodes use lock_episode_candidates."""
    root = Path(run_root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    selected = select_last_submission(prepared)
    # This is an immutable close claim in this world's own evidence directory,
    # not a mutation of a submitted version. It also prevents a second process
    # selecting another output folder after inspecting a score.
    write_new(Path(prepared.world.store.control) / "v054-candidate-close.json", {
        "version": VERSION, "task_id": prepared.case["case_id"],
        "candidate_lock_path": str(root / "lock.json"),
        "source_reference": selected["binding"]["source_reference"] if selected else None,
    })
    if selected is None:
        return write_new(root / "lock.json", {
            "version": VERSION, "task_id": prepared.case["case_id"], "submitted": False,
            "candidate": None, "endpoint": "last_legal_submission",
            "reason": "No legal fixed delivery; no working-tree fallback",
            "model_calls": 0, "public_test_calls": 0, "grading_calls": 0,
        })
    return _write_selected(root, selected, endpoint="last_legal_submission")[0]


def _write_selected(root, selected, *, endpoint, reuse=None):
    if reuse is None:
        candidate_ref = write_new(root / "candidate-bundle.json", selected["candidate"])
        manifest_ref = write_new(root / "candidate-tree.json", selected["manifest"])
        policy_ref = write_new(root / "file-policy.json", selected["policy"])
        patch = export_git_patch(
            selected["baseline"], selected["candidate"], root / "candidate.patch",
            policy=selected["policy"])
        patch_ref = write_new(root / "patch-receipt.json", patch)
    else:
        candidate_ref, manifest_ref = reuse["candidate"], reuse["tree"]
        policy_ref, patch_ref = reuse["file_policy"], reuse["patch_receipt"]
    binding_ref = write_new(root / "submission-binding.json", selected["binding"])
    value = {
        "version": VERSION, "task_id": selected["task_id"],
        "submitted": True if endpoint == "last_legal_submission" else None,
        "endpoint": endpoint, "candidate": candidate_ref,
        "tree": manifest_ref, "binding": binding_ref, "patch_receipt": patch_ref,
        "file_policy": policy_ref,
        "tree_sha256": selected["manifest"]["tree_sha256"],
        "source_reference": selected["binding"]["source_reference"],
        "files_sha256": selected["binding"]["files_sha256"],
        "entry_metadata_sha256": selected["binding"]["entry_metadata_sha256"],
        "lock_before_grading": True, "candidate_selection_after_scoring": False,
        "reused_identical_candidate_artifacts": reuse is not None,
        "model_calls": 0, "public_test_calls": 0, "grading_calls": 0,
    }
    return write_new(root / "lock.json", value), value


def lock_episode_candidates(prepared, *, run_root):
    """Capture terminal and last legal delivery in one World transaction.

    Both endpoints are frozen before any grading. Absence of a legal submission
    never removes the terminal-code candidate.
    """
    root = Path(run_root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    world = prepared.world
    with world.store.lock():
        world.state = world.store.load()
        facts = world._software()
        actors = facts["case"]["active_roles"]
        if len(actors) != 1:
            raise ValueError("v054 candidate closing requires the actual single agent")
        actor = actors[0]
        artifact, version, bundle = world._bundle(actor)
        base_artifact, base_version, baseline = world._bundle(actor, baseline=True)
        policy = copy.deepcopy(facts["case"]["file_policy"])
        _tree(baseline, policy)
        manifest = _tree(bundle, policy)
        prepared.source_provider.validate_files(
            prepared.case["case_id"], bundle["files"],
            entry_metadata=bundle["entry_metadata"])
        terminal = {
            "task_id": prepared.case["case_id"], "baseline": copy.deepcopy(baseline),
            "candidate": copy.deepcopy(bundle), "policy": policy, "manifest": manifest,
            "binding": {
                "endpoint": "terminal_code", "actor_id": actor,
                "baseline_reference": {
                    "object_id": base_artifact["artifact_id"], "version_id": base_version},
                "source_reference": {"object_id": artifact["artifact_id"], "version_id": version},
                "source_sha256": digest(json_bytes(bundle)),
                "files_sha256": digest(json_bytes(bundle["files"])),
                "entry_metadata_sha256": digest(json_bytes(bundle["entry_metadata"])),
                "requires_fixed_patch_or_submission": False,
                "automatic_submission": False,
            },
        }
        delivery = _select_last_submission_locked(prepared)
        claim_ref = write_new(Path(world.store.control) / "v054-candidate-close.json", {
            "version": EPISODE_VERSION, "task_id": prepared.case["case_id"],
            "episode_lock_path": str(root / "lock.json"),
            "terminal_source_reference": terminal["binding"]["source_reference"],
            "delivery_source_reference": delivery["binding"]["source_reference"] if delivery else None,
        })
    # Everything below uses detached snapshots from the same transaction.
    terminal_root = root / "terminal-code"
    terminal_root.mkdir()
    terminal_ref, terminal_value = _write_selected(
        terminal_root, terminal, endpoint="terminal_code")
    delivery_ref = None
    identical = False
    if delivery is not None:
        delivery_root = root / "last-legal-delivery"
        delivery_root.mkdir()
        identical = (
            delivery["candidate"] == terminal["candidate"]
            and delivery["baseline"] == terminal["baseline"]
            and delivery["policy"] == terminal["policy"])
        delivery_ref, _ = _write_selected(
            delivery_root, delivery, endpoint="last_legal_submission",
            reuse=terminal_value if identical else None)
    return write_new(root / "lock.json", {
        "version": EPISODE_VERSION, "task_id": prepared.case["case_id"],
        "close_claim": claim_ref, "terminal_code": terminal_ref,
        "last_legal_delivery": delivery_ref, "submitted": delivery is not None,
        "same_candidate_artifacts": identical,
        "same_tree": (terminal["manifest"]["tree_sha256"] == delivery["manifest"]["tree_sha256"]
                      if delivery else None),
        "assessment_reuse": "not_performed; requires full evaluator identity as well as identical tree",
        "current_working_tree_substituted_for_delivery": False,
        "same_world_transaction": True, "locked_before_grading": True,
        "model_calls": 0, "public_test_calls": 0, "grading_calls": 0,
    })


def read_locked_candidate(lock_reference):
    lock = read_json(checked(lock_reference))
    if (lock.get("version") != VERSION
            or lock.get("endpoint") not in {"terminal_code", "last_legal_submission"}):
        raise ValueError("Expected a v054 endpoint candidate lock")
    if lock["endpoint"] == "last_legal_submission" and lock.get("submitted") is not True:
        if lock.get("submitted") is False and lock.get("candidate") is None:
            return None
        raise ValueError("Invalid unsubmitted candidate lock")
    candidate = read_json(checked(lock["candidate"]))
    manifest = read_json(checked(lock["tree"]))
    binding = read_json(checked(lock["binding"]))
    policy = read_json(checked(lock["file_policy"]))
    patch_receipt = read_json(checked(lock["patch_receipt"]))
    checked(patch_receipt["patch"])
    actual = _tree(candidate, policy)
    if (actual != manifest or actual["tree_sha256"] != lock["tree_sha256"]
            or digest(json_bytes(candidate)) != binding["source_sha256"]
            or digest(json_bytes(candidate["files"])) != lock["files_sha256"]
            or digest(json_bytes(candidate["entry_metadata"])) != lock["entry_metadata_sha256"]
            or binding["source_reference"] != lock["source_reference"]
            or patch_receipt["candidate_tree_sha256"] != lock["tree_sha256"]):
        raise ValueError("Candidate artifacts differ from the unique submission lock")
    return candidate


def read_episode_candidates(lock_reference):
    """Read both independently identified candidates without invoking a grader."""
    lock = read_json(checked(lock_reference))
    if lock.get("version") != EPISODE_VERSION or lock.get("same_world_transaction") is not True:
        raise ValueError("Expected one v054 episode candidate closure")
    claim = read_json(checked(lock["close_claim"]))
    if claim.get("episode_lock_path") != lock_reference["path"]:
        raise ValueError("Episode candidate lock differs from its one-time close claim")
    terminal = read_locked_candidate(lock["terminal_code"])
    delivery = (read_locked_candidate(lock["last_legal_delivery"])
                if lock["last_legal_delivery"] is not None else None)
    if terminal is None or lock["submitted"] is not (delivery is not None):
        raise ValueError("Episode lost a terminal candidate or misrepresented delivery")
    return {"lock": lock, "terminal_code": terminal, "last_legal_delivery": delivery}
