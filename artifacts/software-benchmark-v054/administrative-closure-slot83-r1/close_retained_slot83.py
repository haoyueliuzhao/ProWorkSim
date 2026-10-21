"""Explicit slot83 export/one-shot grading/finalize; never reopen generation."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path("/data0/zhuxinrui/projects/ProWorkSim")
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new  # noqa: E402
from proworksim.software_benchmark_queue_v054 import atomic, lock_file, now, scorer_argv  # noqa: E402
from proworksim.software_benchmark_runner_v054 import score_requests  # noqa: E402
from proworksim.software_benchmark_supervision_v054 import assert_outer_launcher_exited, assert_quiet  # noqa: E402

QUEUE = ROOT / "runs/software-benchmark-v054/formal-queue-r1"
OUT = ROOT / "runs/software-benchmark-v054/administrative-closure-slot83-r1"
EP = QUEUE / "slots/83/preclaim-1/episode"
CLAIM = ROOT / "runs/software-benchmark-v054/episode-claims/cd4b428de4d11f5a86f0bc30c7d4f07f8033dd0d45a690d9467b61dbf2cf4dbe"
SLOT_ID = "v054-REF-matplotlib__matplotlib-24970"
CLAIM_ID = "becab8774b0e4d408c0fdeece06c9cd1"
UNIT = "proworksim-v054-admin-score-slot83-r1.service"
OLD_RESULT_SHA = "103606f1a42365fb2d898494e120f62b44bd742bee97d9636f7daf21d2bc282a"
CONTROLLER_SHA = "003154e3495b65be58c21113441e4fca58248019acd547bbafeda17b4045f292"
OLD_ERROR = {"type": "RepositorySourceError", "message": "Symlinks must have relative repository-contained targets"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def read_ref(item):
    return read(checked(item))


def row83(queue):
    row = queue["rows"][82]
    require(row["slot"]["slot_id"] == SLOT_ID and row["slot"]["slot_index"] == 83,
            "Only the original fixed REF slot83 is authorized")
    return row


def drained(queue):
    require(queue["status"] in {"paused_technical_unknown", "paused_operator_drain"},
            "Administrative closure requires an explicitly paused queue")
    require(not any(row["generation"]["status"] in {"intent", "running"} for row in queue["rows"]),
            "Existing generation must finish before administrative queue updates")
    require(not any(score["status"] in {"intent", "running"}
                    for row in queue["rows"] for score in row["scores"].values()),
            "Existing grader workers must finish before administrative queue updates")


def quiet(scopes):
    values = []
    for scope in scopes:
        require(scope["claim_id"] == CLAIM_ID, "Foreign process scope")
        values.append(assert_quiet(scope))
        assert_outer_launcher_exited(scope)
    return values


def original_files():
    paths = [EP / "result.json", EP / "controller-result.json", CLAIM / "claim.json",
             CLAIM / "candidate-claim.json", CLAIM / "state.json", CLAIM / "quiescence.json",
             CLAIM / "resident-quiescence.json"]
    require(not (CLAIM / "candidate-result.json").exists(),
            "An original candidate result now exists; do not select another candidate")
    return [reference(path) for path in paths]


def verify_preserved(refs):
    for item in refs:
        checked(item)
    require(not (CLAIM / "candidate-result.json").exists(), "Original candidate result must remain absent")
    require(not any((EP / "candidates").iterdir()), "Original failed candidate directory must remain untouched")


def recount(queue):
    rows = queue["rows"]
    queue["generation_counts"] = dict(Counter(row["generation"]["status"] for row in rows))
    queue["scoring_counts"] = dict(Counter(score["status"] for row in rows for score in row["scores"].values()))
    queue["active_generation"] = sum(row["generation"]["status"] in {"intent", "running"} for row in rows)
    queue["active_graders"] = sum(score["status"] in {"intent", "running"}
                                  for row in rows for score in row["scores"].values())
    queue["fully_closed_slots"] = sum(row["generation"]["status"] == "closed" and bool(row["scores"])
        and all(score["status"] == "official_report" for score in row["scores"].values())
        and row["delivery"]["status"] != "pending" for row in rows)
    queue["updated_utc"] = now()
    # The normal coordinator will recompute its version-stratified summaries.
    # Never fabricate a full-panel rate while keeping its old partial summary.
    queue["administrative_summary_refresh_pending"] = True


def export():
    from proworksim import software_benchmark_native_artifact_v054 as artifact
    from proworksim import software_benchmark_native_closure_v054 as closure
    require(closure.capture_native_candidate is artifact.capture_native_candidate
            and closure.export_native_git_patch is artifact.export_native_git_patch,
            "Apply the independently controlled native opaque-symlink exporter first")
    with lock_file(QUEUE / "controller.lock"):
        queue = read(QUEUE / "state.json")
        drained(queue)
        row = row83(queue)
        generation, slot = row["generation"], row["slot"]
        require(generation["status"] == "technical_unknown" and generation["claimed"] is True
                and not row["scores"], "Original slot must be ungraded with its original failed export")
        require(generation["result"]["sha256"] == OLD_RESULT_SHA, "Original error result changed")
        original = read_ref(generation["result"])
        controller_ref = reference(EP / "controller-result.json")
        require(controller_ref["sha256"] == CONTROLLER_SHA, "Original controller evidence changed")
        child = read_ref(controller_ref)
        ledger = child["ledger"]
        require(original["error"] == OLD_ERROR and original["entered"] is True
                and child["status"] == "closed" and child["hidden_feedback_received"] is False
                and child["hidden_grader_calls"] == 0, "Not the known generation-closed export-only fault")
        require(ledger["attempts"] == len(ledger["calls"]) == 29
                and ledger["complete_actual_tokens"] == ledger["known_actual_tokens"] == 464460
                and sum(call["usage"]["total_tokens"] for call in ledger["calls"]) == 464460
                and ledger["inflight"] is None and ledger["uncertain_reserved_tokens"] == 0,
                "Preserve the complete original 29-call/464460-token ledger")
        claim, start = read(CLAIM / "claim.json"), read(EP / "start.json")
        selection = read(CLAIM / "candidate-claim.json")
        oldquiet = read_ref(selection["quiescence"])
        require(claim["slot"] == slot and claim["claim_id"] == start["claim_id"] == CLAIM_ID
                and selection["claim_id"] == CLAIM_ID and selection["selection_after_scoring"] is False
                and oldquiet["claim_id"] == CLAIM_ID and oldquiet["all_quiet"] is True
                and oldquiet["errors"] == [], "The original before-grading candidate boundary must already exist")
        require(read(CLAIM / "state.json")["phase"] == "candidate_export_technical_unknown",
                "Original export state changed")
        release = read_ref(original["resident_release"])
        session = read_ref(release["session"])
        result = release["result"]
        require(result["claim_id"] == session["claim_id"] == CLAIM_ID
                and all(result[key] is True for key in ("released", "quiescent", "resident_still_loaded", "cache_reset"))
                and result["engine_unfinished"] == 0 and result["weights_unloaded"] is False,
                "Original REF session did not release normally")
        config = read_ref(generation["config"])
        require(config["slot_id"] == SLOT_ID and config["arm"] == "REF" and config["seed"] == slot["seed"]
                and config["authorization"] == claim["authorization"], "Original slot configuration changed")
        require(not (EP / "official-code-request.json").exists() and not any((EP / "candidates").iterdir()),
                "A previous candidate/export or official request exists; do not choose again")
        preserved = original_files()
        stopped = quiet(oldquiet["scopes"])
        OUT.mkdir(parents=True, exist_ok=False)
        boundary_root = OUT / "same-claim-boundary"
        boundary_root.mkdir()
        before = write_new(OUT / "state-before-export.json", (QUEUE / "state.json").read_bytes())
        intent = write_new(OUT / "intent.json", {
            "version": "v054-slot83-explicit-administrative-export-r1", "slot_id": SLOT_ID,
            "claim_id": CLAIM_ID, "original_claim": reference(CLAIM / "claim.json"),
            "original_candidate_claim": reference(CLAIM / "candidate-claim.json"),
            "original_result": generation["result"], "controller_result": controller_ref,
            "original_configuration": generation["config"], "original_bindings": row.get("next_execution_bindings", queue["bindings"]),
            "original_quiescence": selection["quiescence"], "normal_resident_release": original["resident_release"],
            "preserved_original_files": preserved,
            "exporter_sources": [reference(artifact.__file__), reference(closure.__file__)],
            "script": reference(__file__), "new_model_calls": 0, "formal_claims_created": 0,
            "new_candidate_selection_claims_created": 0, "actor_worktree_modified_by_script": False,
            "candidate_reselection": False, "hidden_score_observed": False, "grading_calls": 0})
        proof = write_new(OUT / "quiescence.json", {**oldquiet, "stopped": stopped,
            "original_quiescence": selection["quiescence"], "administrative_closure": intent,
            "original_candidate_claim": reference(CLAIM / "candidate-claim.json"),
            "same_claim": True, "selection_after_scoring": False, "outer_launchers_proven_exited": True})

        class Boundary:
            root = boundary_root  # Only the new sidecar receives candidate-result.json.
            claim_id = CLAIM_ID
            def __init__(self):
                self.slot = slot
            @contextmanager
            def candidate_boundary(self):
                with lock_file(CLAIM / "administrative-candidate-slot83.lock"):
                    quiet(oldquiet["scopes"])
                    verify_preserved(preserved)
                    write_new(boundary_root / "same-claim-proof.json", {
                        "original_claim": reference(CLAIM / "claim.json"),
                        "original_candidate_claim": reference(CLAIM / "candidate-claim.json"),
                        "quiescence": proof, "administrative_closure": intent,
                        "claim_id": CLAIM_ID, "new_claim": False, "selection_after_scoring": False})
                    yield proof
                    quiet(oldquiet["scopes"])
                    verify_preserved(preserved)

        candidate = closure.lock_native_candidate(Boundary(),
            baseline_reference=reference(EP / "public-source/initial-tree.json"),
            public_worktree=EP / "actor/rootfs/testbed", public_task=config["public_task"],
            dataset_revision=config["dataset_revision"], output=OUT / "candidates")
        lock = read_ref(candidate)
        require(lock["claim_id"] == CLAIM_ID and lock["slot"] == slot
                and lock["patch_receipt"].get("native_artifact_protocol")
                and lock["patch_receipt"].get("symlink_targets_followed") is False,
                "The same terminal candidate must retain opaque symlink payloads without following targets")
        requests = score_requests(config, candidate, OUT)
        require(len(requests) == 1, "Only the original REF code endpoint is allowed")
        request = read_ref(requests[0])
        require(request["instance_id"] == slot["instance_id"] and request["endpoint"] == "code"
                and request["native_candidate_lock"] == candidate and request["actor_feedback"] is False,
                "Wrong official endpoint")
        result = {**original, "status": "closed_candidate_and_official_requests_ready", "candidate": candidate,
            "official_requests": requests, "controller_result": controller_ref, "quiescence": proof,
            "hidden_feedback_to_actor": False, "public_test_calls": 0, "administrative_closure": intent,
            "original_error_result": generation["result"], "original_error": original["error"],
            "model_calls": 29, "actual_tokens": 464460, "new_model_calls_from_administrative_closure": 0,
            "temporary_rootfs_retained": True, "official_score_pending": True}
        result.pop("error", None)
        result.pop("resident_poison", None)
        result_ref = write_new(OUT / "result.json", result)
        generation.update(status="closed", result=result_ref, controller_result=controller_ref,
            actual_cost_ledger=controller_ref, administrative_closure=intent)
        row.setdefault("original_execution_bindings", row.get("next_execution_bindings", queue["bindings"]))
        row["scores"]["code"] = {"status": "pending", "request": requests[0]}
        queue["status"] = "paused_operator_drain"
        queue.setdefault("administrative_closures", []).append(intent)
        recount(queue)
        verify_preserved(preserved)
        require(reference(QUEUE / "state.json")["sha256"] == before["sha256"], "Queue changed during export")
        atomic(QUEUE / "state.json", queue)
        applied = write_new(OUT / "export-applied.json", {"state_before": before,
            "state_after": reference(QUEUE / "state.json"), "result": result_ref,
            "request": requests[0], "same_claim_proof": reference(boundary_root / "same-claim-proof.json"),
            "new_model_calls": 0, "grading_calls": 0, "original_fault_history_retained": True})
        print(json.dumps({"export": applied, "official_request": requests[0], "grading_started": False}))


def validate_scoring(request_ref):
    request = read_ref(request_ref)
    result = read(OUT / "result.json")
    require(request_ref == result["official_requests"][0] and request["native_candidate_lock"] == result["candidate"]
            and request["arm"] == "REF" and request["endpoint"] == "code"
            and request["instance_id"] == "matplotlib__matplotlib-24970"
            and request["preparation_only"] is False and request["actor_feedback"] is False,
            "Scoring may only consume this one already locked original candidate")
    manifest = read_ref(request["scorer_manifest"])
    require(manifest["version"] == "software-benchmark-scorer-v054-r5"
            and manifest["official_version"] == "5.0.2", "Use the original official r5 installation")
    for key in ("adapter", "mapped_adapter", "baseline_validator", "historical_git_format_policy"):
        checked(manifest[key])
    for item in manifest["historical_git_source_audits"].values():
        checked(item)
    checked(request["patch"])
    lock = read_ref(request["native_candidate_lock"])
    require(lock["claim_id"] == CLAIM_ID and lock["lock_before_grading"] is True
            and lock["patch_receipt"]["patch"] == request["patch"]
            and lock["tree_sha256"] == request["candidate_tree_sha256"], "Candidate changed before official scoring")
    return request


def score():
    with lock_file(QUEUE / "controller.lock"):
        queue = read(QUEUE / "state.json")
        drained(queue)
        row = row83(queue)
        require(row["generation"]["status"] == "closed" and row["scores"]["code"]["status"] == "pending",
                "Export must be administratively closed and never previously scored")
        request_ref = row["scores"]["code"]["request"]
        validate_scoring(request_ref)
        directory = OUT / "score"
        directory.mkdir(exist_ok=False)
        job = write_new(directory / "job.json", {"kind": "score", "request": request_ref,
            "argv": scorer_argv(request_ref["path"]), "unit": UNIT, "runner": reference(__file__),
            "scorer_manifest": read_ref(request_ref)["scorer_manifest"], "attempt": 1,
            "global_grader_limit": 2, "legacy_full_runtime_freeze_not_used": True,
            "automatic_retry": False, "model_calls": 0, "formal_claims": 0})
        before = write_new(directory / "state-before-score.json", (QUEUE / "state.json").read_bytes())
        row["scores"]["code"].update(status="intent", job=job, worker_directory=str(directory), unit=UNIT,
                                     administrative_one_shot=True)
        recount(queue)
        atomic(QUEUE / "state.json", queue)
        argv = ["systemd-run", "--user", "--unit=" + UNIT, "--property=Restart=no",
            "--property=KillMode=control-group", "--property=RuntimeMaxSec=2400",
            "--property=WorkingDirectory=" + str(ROOT),
            "--setenv=PYTHONPATH=" + str(ROOT / "src") + ":" + str(ROOT),
            str(ROOT / ".venv/bin/python"), str(Path(__file__).resolve()), "score-worker", "--job-sha256", job["sha256"]]
        launch = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
        write_new(directory / "launch.json", {"argv": argv, "returncode": launch.returncode,
            "stdout": launch.stdout, "stderr": launch.stderr, "state_before": before, "job": job})
        require(launch.returncode == 0, "Scoring unit launch failed/ambiguous; no automatic repeat")
        print(json.dumps({"unit": UNIT, "job": job, "formal_generation_calls": 0}))


def score_worker(expected_sha):
    directory = OUT / "score"
    job_ref = reference(directory / "job.json")
    require(job_ref["sha256"] == expected_sha, "One-shot scoring job changed")
    job = read_ref(job_ref)
    checked(job["runner"])
    require(job["unit"] == UNIT and job["argv"] == scorer_argv(job["request"]["path"]), "Scoring argv changed")
    state = dict(line.split("=", 1) for line in subprocess.check_output(
        ["systemctl", "--user", "show", UNIT, "--property=MainPID,InvocationID,ControlGroup"], text=True).splitlines())
    require(int(state["MainPID"]) == os.getpid() and state["ControlGroup"].endswith("/" + UNIT),
            "Run this worker only inside its declared one-shot unit")
    with lock_file(directory / "worker.lock"):
        require(not (directory / "started.json").exists() and not (directory / "completion.json").exists(),
                "A started official scorer is never replayed")
        validate_scoring(job["request"])
        lease = None
        for index in range(2):
            try:
                lease = lock_file(QUEUE / "locks" / ("grader-" + str(index) + ".lock"))
                break
            except BlockingIOError:
                continue
        if lease is None:
            write_new(directory / "completion.json", {"job": job_ref, "status": "technical_unknown",
                "returncode": None, "official_scoring_started": False,
                "error": "Both original global grader leases occupied; no automatic repeat"})
            return 1
        value = {"job": job_ref, "started_utc": now(), "pid": os.getpid(), "unit": UNIT,
                 "unit_identity": state, "status": "running", "official_scoring_started": True}
        write_new(directory / "started.json", value)
        try:
            env = {**os.environ, "PYTHONPATH": str(ROOT / "src") + ":" + str(ROOT),
                   "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1",
                   "TRANSFORMERS_OFFLINE": "1", "NO_PROXY": "*", "no_proxy": "*",
                   "CUDA_VISIBLE_DEVICES": "", "NVIDIA_VISIBLE_DEVICES": "void"}
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
                env[key] = ""
            with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
                process = subprocess.Popen(job["argv"], cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
                write_new(directory / "child.json", {"pid": process.pid, "job": job_ref, "started_utc": now()})
                value.update(returncode=process.wait(), status="exited", completed_utc=now())
        except BaseException as error:
            value.update(status="technical_unknown", returncode=None, error=repr(error), completed_utc=now())
        finally:
            write_new(directory / "completion.json", value)
            lease.close()
        return 0 if value.get("returncode") == 0 else 1


def finalize_unknown(job_ref, error):
    """Same fail-closed scoring classification as Coordinator.complete_score."""
    with lock_file(QUEUE / "controller.lock"):
        queue = read(QUEUE / "state.json")
        require(queue["status"] in {"paused_operator_drain", "paused_technical_unknown"}, "Queue resumed before finalize")
        row = row83(queue)
        score = row["scores"]["code"]
        require(score["status"] == "intent" and score["job"] == job_ref,
                "This scoring attempt is already terminal or was replaced")
        require(not (OUT / "finalize-intent.json").exists(), "Finalization intent already exists")
        before = write_new(OUT / "state-before-finalize.json", (QUEUE / "state.json").read_bytes())
        proof = write_new(OUT / "finalize-intent.json", {"state_before": before, "job": job_ref,
            "status": "technical_unknown", "error": {"type": type(error).__name__, "message": str(error)},
            "resolved": None, "automatic_retry": False, "new_model_calls": 0})
        score.update(status="technical_unknown", error=str(error), administrative_finalization=proof)
        queue["status"] = "paused_technical_unknown"
        queue.setdefault("faults", []).append({"utc": now(), "kind": "administrative_official_scoring_unknown",
            "detail": {"slot_id": SLOT_ID, "endpoint": "code", "proof": proof}, "automatic_retry": False})
        recount(queue)
        atomic(QUEUE / "state.json", queue)
        final = write_new(OUT / "finalized.json", {"intent": proof,
            "state_after": reference(QUEUE / "state.json"), "status": "technical_unknown",
            "resolved": None, "new_model_calls": 0, "original_fault_history_retained": True})
        print(json.dumps({"finalization": final, "status": "technical_unknown", "automatic_retry": False}))
        return 1


def finalize():
    directory = OUT / "score"
    completion = read(directory / "completion.json")
    job_ref, job = reference(directory / "job.json"), read(directory / "job.json")
    try:
        require(completion["job"] == job_ref and completion.get("returncode") == 0,
                "Official grading did not produce a successful worker completion; preserve unknown")
        request = validate_scoring(job["request"])
        lines = (directory / "stdout.log").read_text().splitlines()
        report = json.loads(next(line for line in reversed(lines) if line.strip()))
        run_id = report["run_id"]
        require(re.fullmatch(r"v054-REF-code-[0-9a-f]{40}", run_id) is not None, "Unexpected official run ID")
        score_root = Path(request["trusted_output_root"]) / run_id
        receipt, identity = read(score_root / "receipt.json"), read(score_root / "identity.json")
        require(receipt["status"] == "official_report" and type(receipt["resolved"]) is bool
                and receipt["preparation_only"] is False and receipt["actor_feedback"] is False
                and receipt["run_id"] == run_id and identity["arm"] == "REF" and identity["endpoint"] == "code"
                and identity["instance_id"] == request["instance_id"]
                and identity["candidate_tree_sha256"] == request["candidate_tree_sha256"]
                and identity["patch_sha256"] == request["patch"]["sha256"],
                "Official report does not belong to the one locked original candidate")
    except (OSError, ValueError, KeyError, StopIteration) as error:
        return finalize_unknown(job_ref, error)
    with lock_file(QUEUE / "controller.lock"):
        queue = read(QUEUE / "state.json")
        require(queue["status"] in {"paused_operator_drain", "paused_technical_unknown"}, "Queue resumed before finalize")
        row = row83(queue)
        score = row["scores"]["code"]
        require(row["generation"]["status"] == "closed" and score["status"] == "intent"
                and score["request"] == job["request"] and score["job"] == job_ref,
                "Slot83 score was already finalized or its candidate changed")
        require(not (OUT / "finalize-intent.json").exists(), "Administrative score finalization is one-shot")
        preserved = read(OUT / "intent.json")["preserved_original_files"]
        verify_preserved(preserved)
        before = write_new(OUT / "state-before-finalize.json", (QUEUE / "state.json").read_bytes())
        final_intent = write_new(OUT / "finalize-intent.json", {"request": job["request"],
            "completion": reference(directory / "completion.json"), "state_before": before,
            "receipt": reference(score_root / "receipt.json"), "identity": reference(score_root / "identity.json"),
            "candidate_selected_again": False, "model_calls": 0, "formal_claims": 0})
        score.update(status="official_report", resolved=receipt["resolved"],
            receipt=reference(score_root / "receipt.json"), identity=reference(score_root / "identity.json"),
            administrative_finalization=final_intent)
        queue["status"] = "paused_operator_drain"
        recount(queue)
        atomic(QUEUE / "state.json", queue)
        final = write_new(OUT / "finalized.json", {"intent": final_intent,
            "state_after": reference(QUEUE / "state.json"), "resolved": receipt["resolved"],
            "original_calls": 29, "original_tokens": 464460, "new_model_calls": 0,
            "new_formal_claims": 0, "new_candidate_selection_claims": 0, "original_fault_history_retained": True})
        print(json.dumps({"finalization": final, "resolved": receipt["resolved"], "new_model_calls": 0}))
        return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("export", "score", "score-worker", "finalize"))
    parser.add_argument("--job-sha256")
    args = parser.parse_args()
    if args.mode == "export":
        export()
    elif args.mode == "score":
        score()
    elif args.mode == "score-worker":
        require(bool(args.job_sha256), "Worker needs the immutable job hash")
        return score_worker(args.job_sha256)
    else:
        return finalize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
