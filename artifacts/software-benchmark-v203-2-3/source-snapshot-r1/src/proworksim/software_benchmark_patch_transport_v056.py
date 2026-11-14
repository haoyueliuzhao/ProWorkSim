"""UTF-8-safe representation of one already locked native candidate.

Git's default binary heuristic checks for NULs, not UTF-8 validity. NUL-free
PDF or compressed payloads can therefore enter text hunks that an official
JSON prediction cannot encode. This adapter forces those paths to Git binary
patch syntax, with exact before/after tree verification for both representations.
It never edits a candidate, starts a model, runs tests, or selects an alternative.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile

from .software_benchmark_candidates_v054 import _git, checked, reference, write_new
from .software_benchmark_native_artifact_v054 import _native_tree, decode_native_entry

VERSION = "v056-locked-candidate-utf8-patch-transport-r1"


def _load(reference_value):
    return json.loads(checked(reference_value).read_bytes())


def _locked(native_lock_reference):
    lock = _load(native_lock_reference)
    if (lock.get("version") != "software-benchmark-native-closure-v054"
            or lock.get("lock_before_grading") is not True
            or lock.get("endpoint") != "terminal_code"
            or lock.get("slot", {}).get("arm") != "REF"):
        raise ValueError("Transport requires the original closed REF candidate")
    exported = lock["patch_receipt"]
    checked(exported["patch"])
    if (exported.get("round_trip_verified") is not True
            or exported["candidate_tree_sha256"] != lock["tree_sha256"]):
        raise ValueError("Original candidate export is not an exact locked tree")
    return lock, exported


def _object_trees(repo, payloads, pairs):
    blobs = {}
    for bundle, manifest in pairs:
        for entry in manifest["entries"]:
            sha = entry["sha256"]
            if sha not in blobs:
                payload = payloads / sha
                payload.write_bytes(decode_native_entry(
                    entry["path"], bundle["files"][entry["path"]],
                    bundle["entry_metadata"][entry["path"]]))
                blobs[sha] = payload
    ordered = sorted(blobs)
    ids = _git(repo, ["hash-object", "-w", "--no-filters", "--stdin-paths"],
               data="".join(str(blobs[sha]) + "\n" for sha in ordered).encode()).decode().splitlines()
    if len(ids) != len(ordered):
        raise ValueError("Incomplete raw blob inventory")
    ids = dict(zip(ordered, ids, strict=True))
    trees = []
    for _, manifest in pairs:
        _git(repo, ["read-tree", "--empty"])
        records = b"".join(
            (entry["mode"] + " " + ids[entry["sha256"]] + "\t").encode()
            + entry["path"].encode("utf-8") + b"\0" for entry in manifest["entries"])
        _git(repo, ["update-index", "-z", "--index-info"], data=records)
        trees.append(_git(repo, ["write-tree"]).decode().strip())
    return trees


def _round_trip(repo, patch, before_tree, after_tree):
    _git(repo, ["read-tree", before_tree])
    if before_tree != after_tree:
        _git(repo, ["apply", "--cached", "--binary", "--", str(patch)])
    elif patch.read_bytes():
        raise ValueError("An unchanged tree cannot have a nonempty transport patch")
    if _git(repo, ["write-tree"]).decode().strip() != after_tree:
        raise ValueError("Patch representation does not reproduce the exact locked candidate")


def _forced_paths(baseline, terminal):
    result = []
    for path in sorted(set(baseline["files"]) | set(terminal["files"])):
        left = (baseline["files"].get(path), baseline["entry_metadata"].get(path))
        right = (terminal["files"].get(path), terminal["entry_metadata"].get(path))
        if left == right:
            continue
        for bundle in (baseline, terminal):
            if path not in bundle["files"]:
                continue
            raw = decode_native_entry(path, bundle["files"][path], bundle["entry_metadata"][path])
            try:
                raw.decode("utf-8", "strict")
            except UnicodeDecodeError:
                result.append(path)
                break
    return result


def _attribute_pattern(path):
    # Attributes use glob syntax even inside quotes; quote exact path bytes
    # separately from escaping wildcard and negation syntax.
    escaped = "".join("\\" + character if character in "\\*?[]!" else character for character in path)
    return json.dumps(escaped, ensure_ascii=False)


def prepare_transport(native_lock_reference, output_directory):
    """Create a fresh transport artifact and two independent exact-tree proofs."""
    lock, exported = _locked(native_lock_reference)
    baseline, terminal = _load(lock["baseline"]), _load(lock["candidate"])
    before_manifest, after_manifest = _native_tree(baseline), _native_tree(terminal)
    if (before_manifest["tree_sha256"] != exported["base_tree_sha256"]
            or after_manifest["tree_sha256"] != lock["tree_sha256"]):
        raise ValueError("Retained snapshots differ from the original locked tree")
    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=False)
    forced = _forced_paths(baseline, terminal)
    original_patch = checked(exported["patch"])
    patch = output / "candidate-utf8.patch"
    with tempfile.TemporaryDirectory(prefix="proworksim-v056-patch-transport-") as temporary:
        repo, payloads = Path(temporary) / "git", Path(temporary) / "payloads"
        repo.mkdir()
        payloads.mkdir()
        _git(repo, ["init", "--bare", "--quiet", "--template="])
        before_tree, after_tree = _object_trees(repo, payloads, (
            (baseline, before_manifest), (terminal, after_manifest)))
        if (before_tree != exported.get("base_encoding_git_tree", exported.get("base_git_tree"))
                or after_tree != exported.get("candidate_encoding_git_tree", exported.get("candidate_git_tree"))):
            raise ValueError("Snapshot Git object identities differ from the original export")
        _round_trip(repo, original_patch, before_tree, after_tree)
        # info/attributes has precedence over candidate .gitattributes; it is
        # temporary Git control data and never becomes a candidate file.
        (repo / "info").mkdir(exist_ok=True)
        (repo / "info/attributes").write_text(
            "".join(_attribute_pattern(path) + " -diff\n" for path in forced),
            encoding="utf-8")
        raw = _git(repo, ["-c", "core.quotePath=true", "diff", "--binary", "--full-index",
            "--no-renames", "--no-ext-diff", "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/",
            before_tree, after_tree, "--"])
        try:
            raw.decode("utf-8", "strict")
        except UnicodeDecodeError as error:
            # Git does not honor -diff for every entry type (notably opaque
            # non-UTF8 symlink targets). Never repair such bytes by replacement.
            raise ValueError("Git could not encode this candidate as a UTF-8-safe patch") from error
        write_new(patch, raw)
        _round_trip(repo, patch, before_tree, after_tree)
    result = {
        "version": VERSION, "adapter_source": reference(__file__),
        "native_candidate_lock": native_lock_reference,
        "slot_id": lock["slot"]["slot_id"], "condition_id": lock["slot"]["condition_id"],
        "original_patch": exported["patch"], "transport_patch": reference(patch),
        "baseline_snapshot": lock["baseline"], "terminal_snapshot": lock["candidate"],
        "base_tree_sha256": before_manifest["tree_sha256"],
        "candidate_tree_sha256": after_manifest["tree_sha256"],
        "base_git_tree": before_tree, "candidate_git_tree": after_tree,
        "original_patch_round_trip_verified": True, "transport_patch_round_trip_verified": True,
        "utf8_strict": True, "forced_binary_paths": forced,
        "candidate_content_changed": False, "candidate_files_filtered": False,
        "symlink_targets_followed": False, "model_calls": 0, "scoring_calls": 0,
    }
    if "gitlinks" in exported:
        result["base_encoding_git_tree"] = result.pop("base_git_tree")
        result["candidate_encoding_git_tree"] = result.pop("candidate_git_tree")
        result.update(gitlinks=exported["gitlinks"], parent_git_tree_claimed=False,
                      git_tree_identity_scope=exported["git_tree_identity_scope"])
    return write_new(output / "receipt.json", result)


def validate_transport(native_lock_reference, transport_receipt_reference):
    """Validate immutable preparation evidence without repeating its CPU proof."""
    lock, exported = _locked(native_lock_reference)
    receipt = _load(transport_receipt_reference)
    expected = {
        "version": VERSION, "adapter_source": reference(__file__),
        "native_candidate_lock": native_lock_reference, "original_patch": exported["patch"],
        "slot_id": lock["slot"]["slot_id"], "condition_id": lock["slot"]["condition_id"],
        "baseline_snapshot": lock["baseline"], "terminal_snapshot": lock["candidate"],
        "base_tree_sha256": exported["base_tree_sha256"], "candidate_tree_sha256": lock["tree_sha256"],
        "original_patch_round_trip_verified": True, "transport_patch_round_trip_verified": True,
        "utf8_strict": True, "candidate_content_changed": False, "candidate_files_filtered": False,
        "symlink_targets_followed": False, "model_calls": 0, "scoring_calls": 0,
    }
    for key in ("base_git_tree", "candidate_git_tree", "base_encoding_git_tree",
                "candidate_encoding_git_tree", "gitlinks", "git_tree_identity_scope"):
        if key in exported:
            expected[key] = exported[key]
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError("Patch transport is not bound to the original exact candidate")
    for key in ("adapter_source", "original_patch", "baseline_snapshot", "terminal_snapshot"):
        checked(receipt[key])
    checked(receipt["transport_patch"]).read_bytes().decode("utf-8", "strict")
    return receipt
