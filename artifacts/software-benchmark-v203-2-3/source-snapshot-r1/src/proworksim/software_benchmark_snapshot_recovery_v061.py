"""Recover one interrupted export from its original, already chosen snapshot.

This offline path never reads the surviving actor workspace, invokes a model,
starts a container or changes the original episode. It closes the missing export
receipt using the exact pre-scoring snapshot and historical quiescence proof.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from .software_benchmark_candidates_v054 import checked, changed_paths, reference, write_new, _git
from .software_benchmark_native_artifact_v054 import PROTOCOL, _native_tree
from .software_benchmark_patch_transport_v056 import (
    _attribute_pattern, _forced_paths, _object_trees, _round_trip,
)
from .storage import digest

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v061-original-terminal-snapshot-export-recovery-r1"
TASK = "scikit-learn__scikit-learn-14894"
SLOT_ID = "v056:scikit-learn__scikit-learn-14894:REF_B5000K:20261024056040"
EPISODE_KEY = "9068a1a135c28142d64c6b7b1914d6549b527fb569d31248bb2170541a3fd00d"
DEFAULT_OUTPUT = ROOT / "runs/software-benchmark-v061/original-terminal-recovery-r1-20261025"
EXPECTED_TERMINAL_SHA = "376cc7b31af638feac09a6605f362e205e9d48b2b5e5ec4e2e548d607ce554b3"
EXPECTED_BASELINE_SHA = "e0ecb769048dba2c40241383a7ff7628b6005d41c159461f2463ceeb392090ed"


def read(path):
    return json.loads(Path(path).read_bytes())


def historical_paths():
    episode = ROOT / "runs/software-benchmark-v056/episodes" / EPISODE_KEY
    claim = ROOT / "runs/software-benchmark-v056/episode-claims" / EPISODE_KEY
    return {
        "original_config": ROOT / "runs/software-benchmark-v056/queue-r2/configs" / (EPISODE_KEY + ".json"),
        "claim": claim / "claim.json", "candidate_claim": claim / "candidate-claim.json",
        "dispatch_closed": claim / "dispatch-closed.json", "quiescence": claim / "quiescence.json",
        "controller": episode / "controller-result.json", "sdk_terminal": episode / "sdk-terminal-state.json",
        "baseline_manifest": episode / "public-source/source-manifest.json",
        "baseline": episode / "public-source/initial-tree.json",
        "terminal_manifest": episode / "candidates/terminal-snapshot/source-manifest.json",
        "terminal": episode / "candidates/terminal-snapshot/initial-tree.json",
    }


def validate_history(records, refs):
    """Pure binding checks before touching any export destination."""
    claim, config = records["claim"], records["original_config"]
    slot = claim.get("slot", {})
    if (slot.get("slot_id") != SLOT_ID or slot.get("slot_index") != 163
            or slot.get("instance_id") != TASK or slot.get("arm") != "REF"
            or slot.get("condition_id") != "REF_B5000K" or slot.get("seed") != 20261024056040
            or config.get("slot_id") != SLOT_ID or config.get("condition_id") != slot["condition_id"]
            or claim.get("configuration") != config.get("configuration")):
        raise ValueError("Recovery is bound to the original slot, condition, seed and configuration")
    identity = claim.get("claim_id")
    controller, sdk = records["controller"], records["sdk_terminal"]
    if (controller.get("slot_id") != SLOT_ID or controller.get("condition_id") != slot["condition_id"]
            or controller.get("status") != "closed" or controller.get("normal_completion") is not True
            or controller.get("native_finished") is not True or sdk.get("execution_status") != "finished"
            or controller.get("hidden_feedback_received") is not False
            or controller.get("preparation_only") is not False):
        raise ValueError("The original model must already have finished normally without hidden feedback")
    closed, quiet, selected = (records[key] for key in ("dispatch_closed", "quiescence", "candidate_claim"))
    if (not identity or any(value.get("claim_id") != identity for value in (closed, quiet, selected))
            or closed.get("reason") != "ref_budget_controller_returned"
            or quiet.get("all_quiet") is not True or quiet.get("errors") != []
            or selected.get("quiescence") != refs["quiescence"]
            or selected.get("selection_after_scoring") is not False):
        raise ValueError("Original candidate selection must follow its own trusted quiescence boundary")
    scopes, stopped = quiet.get("scopes", []), quiet.get("stopped", [])
    if (len(scopes) != 2 or len(stopped) != 2 or {s.get("role") for s in scopes} != {"actor", "controller"}
            or any(s.get("claim_id") != identity for s in scopes)
            or {s.get("unit") for s in scopes} != {s.get("unit") for s in stopped}
            or any(s.get("populated") is not False or s.get("registered_main_exited") is not True
                   or s.get("active_state") != "inactive" for s in stopped)):
        raise ValueError("Both original writers must have matching stopped-scope evidence")
    public = config["public_task"]
    expected_identity = {k: public[k] for k in ("instance_id", "repo", "base_commit")}
    expected_identity["dataset_revision"] = config["dataset_revision"]
    for kind in ("baseline", "terminal"):
        manifest = records[kind + "_manifest"]
        if (len(manifest.get("tasks", [])) != 1
                or kind == "terminal" and manifest.get("version") != PROTOCOL):
            raise ValueError("Expected one fixed task in the original snapshot manifest")
        task = manifest["tasks"][0]
        if (task.get("task_id") != TASK or task.get("source_identity") != expected_identity
                or task.get("problem_statement") != public["problem_statement"]):
            raise ValueError("Snapshot task or source identity differs from the original task")
        advertised = task.get("initial_tree", {})
        if (advertised.get("path") != "initial-tree.json"
                or any(advertised.get(k) != refs[kind].get(k) for k in ("sha256", "bytes"))):
            raise ValueError("Original snapshot bytes differ from their source manifest")
    return slot


def export_utf8_patch(baseline, terminal, path, *, policy=None):
    """Encode all original target bytes and modes once; verify exact Git apply."""
    before, after = _native_tree(baseline, policy), _native_tree(terminal, policy)
    forced = _forced_paths(baseline, terminal)
    path = Path(path)
    with tempfile.TemporaryDirectory(prefix="proworksim-v061-original-export-") as temp:
        repo, payloads = Path(temp) / "git", Path(temp) / "payloads"
        repo.mkdir()
        payloads.mkdir()
        _git(repo, ["init", "--bare", "--quiet", "--template="])
        base_tree, target_tree = _object_trees(repo, payloads, ((baseline, before), (terminal, after)))
        (repo / "info").mkdir(exist_ok=True)
        (repo / "info/attributes").write_text(
            "".join(_attribute_pattern(name) + " -diff\n" for name in forced), encoding="utf-8")
        raw = _git(repo, ["-c", "core.quotePath=true", "diff", "--binary", "--full-index",
                         "--no-renames", "--no-ext-diff", "--no-textconv", "--src-prefix=a/",
                         "--dst-prefix=b/", base_tree, target_tree, "--"])
        raw.decode("utf-8", "strict")
        write_new(path, raw)
        _round_trip(repo, path.resolve(), base_tree, target_tree)
    result = {
        "patch": reference(path), "base_git_tree": base_tree, "candidate_git_tree": target_tree,
        "base_tree_sha256": before["tree_sha256"], "candidate_tree_sha256": after["tree_sha256"],
        "round_trip_verified": True, "utf8_strict": True, "forced_binary_paths": forced,
        "candidate_content_changed": False, "binary_patch": True, "editable_path_filter_used": False,
        "native_artifact_protocol": PROTOCOL, "symlink_targets_followed": False,
        "rename_representation": "delete-and-add; exact target bytes and modes retained",
        **changed_paths(baseline, terminal),
    }
    from .software_benchmark_gitlinks_v054 import annotate_patch
    return annotate_patch(result, baseline.get("gitlinks", []), baseline, terminal)


def recover(output=DEFAULT_OUTPUT):
    if os.geteuid() == 0 or os.getuid() == 0:
        raise PermissionError("Snapshot recovery uses ordinary user files only")
    output = Path(output).resolve()
    if output != DEFAULT_OUTPUT.resolve():
        raise ValueError("Use the fixed fresh v061 original-terminal recovery directory")
    paths = historical_paths()
    # Read each large bundle once, retaining the exact bytes only until parsed.
    records, refs = {}, {}
    for name, path in paths.items():
        data = path.read_bytes()
        refs[name] = {"path": str(path.resolve()), "sha256": digest(data), "bytes": len(data)}
        records[name] = json.loads(data)
    if (refs["terminal"]["sha256"] != EXPECTED_TERMINAL_SHA
            or refs["baseline"]["sha256"] != EXPECTED_BASELINE_SHA):
        raise ValueError("The pre-reviewed original snapshots changed")
    slot = validate_history(records, refs)
    terminal, baseline = records["terminal"], records["baseline"]
    for kind, bundle in (("terminal", terminal), ("baseline", baseline)):
        expected = records[kind + "_manifest"]["tasks"][0]
        if (bundle.get("truncated") is not False or bundle.get("file_policy") != expected["file_policy"]
                or bundle.get("tree", {}).get("tree_sha256") != expected["tree_sha256"]):
            raise ValueError("Original complete snapshot metadata is inconsistent")
    old_episode = paths["terminal"].parents[2]
    old_claim = paths["claim"].parent
    old_missing = [old_episode / "candidates/lock.json", old_claim / "candidate-result.json",
                   old_episode / "result.json", old_episode / "official-code-request.json"]
    if any(p.exists() for p in old_missing):
        raise ValueError("An original final candidate/result appeared; do not select or replace it")
    output.mkdir(parents=True, exist_ok=False)
    source = {"version": VERSION, "utc": datetime.now(timezone.utc).isoformat(), "slot": slot,
              "source_module": reference(__file__), "original_evidence": refs,
              "model_calls": 0, "scoring_calls": 0, "old_workspace_read": False}
    source_ref = write_new(output / "recovery-source.json", source)
    patch = export_utf8_patch(baseline, terminal, output / "candidate.patch", policy=terminal["file_policy"])
    if (patch["base_tree_sha256"] != baseline["tree"]["tree_sha256"]
            or patch["candidate_tree_sha256"] != terminal["tree"]["tree_sha256"]):
        raise ValueError("Recovered blobs do not reproduce the originally manifested trees")
    lock = {
        "version": "software-benchmark-native-closure-v054", "claim_id": records["claim"]["claim_id"],
        "slot": slot, "endpoint": "terminal_code", "quiescence": refs["quiescence"],
        "baseline": refs["baseline"], "candidate": refs["terminal"],
        "source_manifest": refs["terminal_manifest"], "patch_receipt": patch,
        "tree_sha256": patch["candidate_tree_sha256"], "delivery": None,
        "lock_before_grading": True, "model_calls": 0, "grading_calls": 0,
        "recovery_version": VERSION, "original_candidate_claim": refs["candidate_claim"],
        "recovery_source": source_ref, "new_export_receipt_not_original_file": True,
    }
    lock_ref = write_new(output / "lock.json", lock)
    result = {"version": VERSION, "status": "candidate_recovered_pending_scoring", "slot": slot,
        "measurement_kind": "original_terminal_snapshot_recovery", "original_config": refs["original_config"],
        "candidate_lock": lock_ref, "patch": patch["patch"], "source": source_ref,
        "original_terminal_tree_sha256": terminal["tree"]["tree_sha256"],
        "original_terminal_file_count": terminal["tree"]["entry_count"],
        "candidate_content_changed": False, "original_episode_files_changed": False,
        "queue_state_changed": False, "model_calls": 0, "scoring_calls": 0,
        "new_claim_or_resampling": False, "round_trip_verified": True, "utf8_strict": True}
    return write_new(output / "recovery-result.json", result)


def validate_recovery(result_ref):
    result = json.loads(checked(result_ref).read_bytes())
    if (result.get("version") != VERSION or result.get("status") != "candidate_recovered_pending_scoring"
            or result.get("measurement_kind") != "original_terminal_snapshot_recovery"
            or result.get("slot", {}).get("slot_id") != SLOT_ID
            or result.get("candidate_content_changed") is not False
            or result.get("model_calls") != 0 or result.get("scoring_calls") != 0):
        raise ValueError("Expected the bounded original terminal recovery")
    source = json.loads(checked(result["source"]).read_bytes())
    if source.get("source_module") != reference(__file__):
        raise ValueError("Recovery implementation changed after candidate export")
    lock = json.loads(checked(result["candidate_lock"]).read_bytes())
    originals = source.get("original_evidence", {})
    if (lock.get("version") != "software-benchmark-native-closure-v054"
            or lock.get("endpoint") != "terminal_code"
            or lock.get("recovery_source") != result["source"] or lock.get("recovery_version") != VERSION
            or lock.get("slot") != result["slot"] or lock.get("lock_before_grading") is not True
            or lock.get("baseline") != originals.get("baseline")
            or lock.get("candidate") != originals.get("terminal")
            or lock.get("source_manifest") != originals.get("terminal_manifest")
            or lock.get("quiescence") != originals.get("quiescence")
            or lock.get("original_candidate_claim") != originals.get("candidate_claim")
            or result.get("original_config") != originals.get("original_config")
            or lock.get("tree_sha256") != result["original_terminal_tree_sha256"]
            or lock.get("patch_receipt", {}).get("patch") != result["patch"]
            or lock["patch_receipt"].get("round_trip_verified") is not True):
        raise ValueError("Recovered candidate identity differs from its immutable recovery result")
    checked(result["patch"]).read_bytes().decode("utf-8", "strict")
    return result
