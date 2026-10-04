"""One original failed dense trace: numerical replay and full gradient control.

No model output is sampled, no optimizer is stepped, and no screening episode is
created. Historical full replay is a diagnostic comparator; the candidate gate
requires native cached, functional no-grad, and functional train/backward replay
of every original target under the unchanged probability tolerances.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import time
import traceback

from proworksim.audit import code_identity
from proworksim.candidate_runtime_v030 import DenseCandidateActor, candidate_profile as loading_profile
from proworksim.candidate_runtime_v031 import candidate_profile
from proworksim.functional_dense_v031 import learning_logprobs, native_cache_logprobs
from proworksim.model_qualification_v030 import _trace
from proworksim.online_training import probability_check, selected_logprobs, tensor_tree_digest
from proworksim.software_learning_v029 import migrate_software_owner
from proworksim.storage import digest, json_bytes, read_json
from scripts.run_ne_v021 import reference, resources, write
from scripts.software_development_v028 import available_cards, task

VERSION = "dense-original-trace-replay-control-v0.31"
SOURCE = Path(__file__).resolve().parents[1]
FAILED_TRACE_INDEX = {"swe-next-14b": 0, "devstral-small-2507": 2}
TESTED_FILES = (
    "scripts/probe_dense_replay_v031.py",
    "src/proworksim/candidate_runtime_v031.py", "src/proworksim/native_codecs_v031.py",
    "src/proworksim/functional_dense_v031.py", "src/proworksim/candidate_runtime_v030.py",
    "src/proworksim/candidate_runtime_v0201.py", "src/proworksim/candidate_runtime_v020.py",
    "src/proworksim/candidate_runtime_v015.py", "src/proworksim/local_model_service.py",
    "src/proworksim/online_training.py", "src/proworksim/software_learning_v029.py",
    "src/proworksim/model_qualification_v030.py", "scripts/software_development_v028.py",
)
CANDIDATE_PATHS = ("native_cached_no_grad", "functional_no_grad", "functional_train_backward")


def implementation_hashes():
    return {name: digest((SOURCE / name).read_bytes()) for name in TESTED_FILES}


def _checked(ref):
    path = Path(ref["path"])
    if digest(path.read_bytes()) != ref["sha256"] or ("bytes" in ref and path.stat().st_size != ref["bytes"]):
        raise ValueError("Original artifact reference changed: " + str(path))
    return path


def _resources(owner):
    result = {"host": owner._resource_guard(), "device": owner.device}
    if owner.device.startswith("cuda"):
        result["peak_gpu_allocated_bytes"] = owner.torch.cuda.max_memory_allocated()
        result["peak_gpu_reserved_bytes"] = owner.torch.cuda.max_memory_reserved()
    return result


def _reset_peaks(owner):
    if owner.device.startswith("cuda"):
        owner.torch.cuda.reset_peak_memory_stats()


def _gradient_summary(owner):
    torch = owner.torch
    rows = []
    for name, parameter in owner.actor_parameters.items():
        value = parameter.grad
        row = {"parameter": name, "shape": list(parameter.shape), "parameter_dtype": str(parameter.dtype),
               "gradient_present": value is not None}
        if value is not None:
            detached = value.detach()
            row.update(gradient_dtype=str(value.dtype), finite=bool(torch.isfinite(detached).all()),
                       nonzero_elements=int(torch.count_nonzero(detached)),
                       norm=float(detached.float().norm()), maximum_absolute=float(detached.abs().max()))
        rows.append(row)
    return {"parameters": rows, "all_expected_actor_gradients_present": all(row["gradient_present"] for row in rows),
            "all_gradients_finite": all(row.get("finite", False) for row in rows),
            "total_nonzero_elements": sum(row.get("nonzero_elements", 0) for row in rows),
            "critic_gradients_present": any(parameter.grad is not None for parameter in owner.critic.parameters()),
            "scope": "Actual gradients from the complete original target mean; no optimizer or clipping operation"}


def evaluate_owner(owner, trace, output, *, common_dir, common_record, report):
    """Run the four paths and always restore the complete already-bound common."""
    output, common_dir = Path(output), Path(common_dir)
    output.mkdir(parents=True, exist_ok=True)
    torch = owner.torch
    original = copy.deepcopy(trace)
    before_steps = owner.actor_steps, owner.critic_steps
    report.setdefault("paths", {})
    report.setdefault("errors", [])
    report.update(status="replaying", passed=False, full_backward_completed=False,
                  all_full_tokens_retained=False, all_behavior_and_gradient_probability_passed=False,
                  common_restored_exactly=False, optimizer_steps=0, new_model_calls=0,
                  original_input_tokens=len(trace["input_ids"]), original_output_tokens=len(trace["output_ids"]),
                  original_trace_sha256=digest(json_bytes(trace)),
                  probability_gate={"logprob_max_atol": .02, "logprob_mean_atol": .002})
    write(output / "report.json", report)
    try:
        if owner.phase != "idle" or owner.busy or owner.sampling_only:
            raise ValueError("Replay starts from an idle complete learner")
        if owner.recipe["logprob_max_atol"] != .02 or owner.recipe["logprob_mean_atol"] != .002:
            raise ValueError("The original maximum/mean probability gates cannot be changed")
        if tensor_tree_digest(owner._state_bundle(), torch) != common_record["state_tensor_digest"]:
            raise ValueError("Owner must exactly equal the original saved common before diagnosis")
        owner.phase = "updating"
        owner.actor_optimizer.zero_grad(set_to_none=True)
        owner.critic_optimizer.zero_grad(set_to_none=True)
        functions = (
            ("original_full_no_grad", lambda: selected_logprobs(owner.model, trace, torch, owner.device)),
            ("native_cached_no_grad", lambda: native_cache_logprobs(owner.model, trace)),
            ("functional_no_grad", lambda: learning_logprobs(owner.model, trace)),
            ("functional_train_backward", lambda: learning_logprobs(owner.model, trace)),
        )
        for name, function in functions:
            task(output, name, "qualification_update")
            _reset_peaks(owner)
            owner.clear_generation_cache()
            owner.model.train(name == "functional_train_backward")
            started = time.monotonic()
            row = {"status": "running", "path": name, "backward_completed": False,
                   "original_input_tokens": len(trace["input_ids"]), "original_output_tokens": len(trace["output_ids"])}
            report["paths"][name] = row
            write(output / "report.json", report)
            try:
                with torch.set_grad_enabled(name == "functional_train_backward"):
                    values = function()
                    actual = values.detach().cpu().tolist()
                    row.update(returned_targets=len(actual), selected_probability_dtype=str(values.dtype),
                               full_tokens_retained=(len(actual) == len(trace["output_ids"]) and trace == original),
                               comparison_to_original_behavior=probability_check(actual, trace["behavior_logprobs"], owner.recipe))
                    # Preserve exact derived values even if the original gate fails.
                    write(output / (name + "-logprobs.json"), {
                        "original_trace_sha256": report["original_trace_sha256"],
                        "input_ids": original["input_ids"], "output_ids": original["output_ids"],
                        "behavior_logprobs": original["behavior_logprobs"],
                        "recomputed_logprobs": actual, "comparison": row["comparison_to_original_behavior"]})
                    if name == "functional_train_backward":
                        loss = -values.mean()
                        if not bool(torch.isfinite(loss)):
                            raise ValueError("Functional diagnostic loss is not finite")
                        loss.backward()
                        row.update(backward_completed=True, full_target_mean_loss=float(loss.detach()),
                                   gradient_summary=_gradient_summary(owner))
                        gradient = row["gradient_summary"]
                        report["full_backward_completed"] = bool(
                            gradient["all_expected_actor_gradients_present"] and gradient["all_gradients_finite"]
                            and gradient["total_nonzero_elements"] > 0 and not gradient["critic_gradients_present"])
                        write(output / "functional-parameter-gradients.json", gradient)
                        del loss
                    del values
                row["status"] = "completed"
            except Exception as error:
                row.update(status="error", error={"type": type(error).__name__, "message": str(error)})
                report["errors"].append({"stage": name, **row["error"]})
                with (output / "errors.log").open("a") as stream:
                    stream.write(name + "\n" + traceback.format_exc() + "\n")
            finally:
                row.update(elapsed_seconds=time.monotonic() - started, resources=_resources(owner))
                write(output / (name + "-report.json"), row)
                write(output / "report.json", report)
        report["all_full_tokens_retained"] = (trace == original and len(report["paths"]) == 4
            and all(row.get("full_tokens_retained") is True for row in report["paths"].values()))
        report["all_behavior_and_gradient_probability_passed"] = all(
            report["paths"][name].get("comparison_to_original_behavior", {}).get("passed") is True
            for name in CANDIDATE_PATHS)
        report["historical_full_failure_reproduced"] = (
            report["paths"]["original_full_no_grad"].get("comparison_to_original_behavior", {}).get("passed") is False)
        report["candidate_gate_excludes_historical_full_replay"] = True
        report["before_restore_state_unchanged"] = tensor_tree_digest(owner._state_bundle(), torch) == common_record["state_tensor_digest"]
        report["optimizer_steps"] = (owner.actor_steps - before_steps[0]) + (owner.critic_steps - before_steps[1])
    except Exception as error:
        report["errors"].append({"stage": "replay_setup_or_summary", "type": type(error).__name__, "message": str(error)})
        with (output / "errors.log").open("a") as stream:
            stream.write(traceback.format_exc() + "\n")
    finally:
        task(output, "restore_original_complete_common", "boundary")
        try:
            owner.actor_optimizer.zero_grad(set_to_none=True)
            owner.critic_optimizer.zero_grad(set_to_none=True)
            owner.model.eval()
            owner.clear_generation_cache()
            if owner.busy:
                raise ValueError("Cannot restore common while a model operation is active")
            owner.phase = "idle"
            owner.restore_checkpoint(common_dir)
            actual = tensor_tree_digest(owner._state_bundle(), torch)
            report.update(common_restored_exactly=actual == common_record["state_tensor_digest"],
                          restored_state_tensor_digest=actual,
                          gradients_cleared=all(parameter.grad is None for parameter in [*owner.actor_parameters.values(), *owner.critic.parameters()]))
        except Exception as error:
            report["errors"].append({"stage": "restore_common", "type": type(error).__name__, "message": str(error)})
        report["passed"] = bool(report["all_full_tokens_retained"] and report["all_behavior_and_gradient_probability_passed"]
            and report["full_backward_completed"] and report["common_restored_exactly"]
            and report.get("gradients_cleared") and report.get("before_restore_state_unchanged")
            and report["optimizer_steps"] == 0 and not report["errors"])
        report["status"] = "passed" if report["passed"] else "failed"
        write(output / "report.json", report)
    return report


def run(candidate, data_root, prior_recovery_root, output):
    if candidate not in FAILED_TRACE_INDEX:
        raise ValueError("Only the two declared failed dense traces may be replayed")
    started = time.time()
    output, data_root, prior_root = Path(output).resolve(), Path(data_root).resolve(), Path(prior_recovery_root).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = code_identity()
    report = {"version": VERSION, "candidate_id": candidate, "passed": False, "status": "loading",
              "source": source, "tested_files_sha256": implementation_hashes(),
              "profile_sha256": digest(json_bytes(candidate_profile(candidate))),
              "original_trace_refs": [], "original_actor_identity_matched": False,
              "optimizer_steps": 0, "new_model_calls": 0, "full_backward_completed": False,
              "all_full_tokens_retained": False, "all_behavior_and_gradient_probability_passed": False,
              "common_restored_exactly": False, "errors": [], "started_at": started,
              "capacity_proven": False, "scope": "Original failed-trace numerical/backward control only; no fresh token, optimizer update, screening episode or 16K capacity claim."}
    write(output / "report.json", report)
    owner, common, common_dir = None, None, None
    try:
        actual = prior_root / candidate / "actual"
        response_path = actual / "qualification" / f"native-call-{FAILED_TRACE_INDEX[candidate] + 1}" / "response.json"
        report["original_trace_refs"] = [reference(response_path)]
        response = read_json(response_path)
        write(output / "report.json", report)
        task(output, "load-original-" + candidate, "loading")
        if source["code_dirty"] is not False:
            raise ValueError("GPU replay requires the clean frozen source tree")
        visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
        if visible not in {str(index) for index in range(8)}:
            raise ValueError("Bind exactly one declared physical GPU to this replay worker")
        sample = resources()
        write(output / "preload-resources.json", sample)
        gate = {"gpu_preference": list(range(8)), "limits": {"minimum_free_gpu_mib": 78000}}
        if int(visible) not in [row["index"] for row in available_cards(gate, sample)]:
            raise ValueError("Original-trace replay requires an empty A100 with at least 78000 MiB free")
        prior_plan = read_json(prior_root / "plan.json")
        if prior_plan["candidate_profiles"][candidate] != loading_profile(candidate):
            raise ValueError("Original loader profile differs from the fixed v030 numerical path")
        original_owner = read_json(actual / "resident/owner.json")
        common_dir = actual / "common-state"
        common = read_json(common_dir / "checkpoint.json")
        manifest = _checked(original_owner["base_identity"]["manifest"])
        if manifest != data_root / "runs/v030-models/downloads" / (candidate + ".json"):
            raise ValueError("Original actor must bind the declared global completed model manifest")
        owner = DenseCandidateActor.from_candidate(original_owner["base_identity"]["path"], manifest=manifest,
            profile=loading_profile(candidate), recipe=original_owner["recipe"], output=output / "resident")
        migrate_software_owner(owner, output / "software-critic-migration.json", expected_steps=None)
        task(output, "restore-original-common-before-replay", "boundary")
        restored = owner.restore_checkpoint(common_dir)
        if restored != common or tensor_tree_digest(owner._state_bundle(), owner.torch) != common["state_tensor_digest"]:
            raise ValueError("Original complete actor/critic/optimizer/RNG state did not restore exactly")
        identity = owner.freeze_identity()
        report["original_actor_identity_matched"] = (identity == response["body"]["actor_identity"] == common["actor_identity"])
        if not report["original_actor_identity_matched"]:
            raise ValueError("The recorded original response belongs to a different effective actor")
        trace = _trace(response, identity, len(response["body"]["token_trace"]["input_ids"]))
        report.update(original_common_reference=reference(common_dir / "checkpoint.json"),
                      original_actor_identity=identity, original_trace_index=FAILED_TRACE_INDEX[candidate])
        evaluate_owner(owner, trace, output, common_dir=common_dir, common_record=common, report=report)
    except Exception as error:
        report["errors"].append({"stage": "worker", "type": type(error).__name__, "message": str(error)})
        with (output / "errors.log").open("a") as stream:
            stream.write(traceback.format_exc() + "\n")
        report.update(status="failed", passed=False)
    finally:
        # evaluate_owner has its own unconditional restore. If preparation failed
        # after loading a common, also retain a best-effort explicit restoration.
        if owner is not None and common is not None and not report.get("common_restored_exactly"):
            try:
                task(output, "restore-common-after-worker-error", "boundary")
                owner.actor_optimizer.zero_grad(set_to_none=True)
                owner.critic_optimizer.zero_grad(set_to_none=True)
                owner.model.eval()
                if owner.busy:
                    raise ValueError("A live model operation prevents safe common restore")
                owner.phase = "idle"
                owner.restore_checkpoint(common_dir)
                report["common_restored_exactly"] = tensor_tree_digest(owner._state_bundle(), owner.torch) == common["state_tensor_digest"]
            except Exception as error:
                report["errors"].append({"stage": "worker_restore", "type": type(error).__name__, "message": str(error)})
        if owner is not None:
            calls = list((owner.output / "calls").glob("*.json"))
            report["new_model_calls"] = len(calls)
            if calls:
                report.update(passed=False, status="failed")
                report["errors"].append({"stage": "sampling_guard", "type": "ValueError", "message": "A numerical probe must not generate any new response"})
        unchanged = source == code_identity() and report["tested_files_sha256"] == implementation_hashes()
        originals_unchanged = all(reference(Path(ref["path"])) == ref for ref in report["original_trace_refs"])
        report.update(ended_at=time.time(), actual_worker_gpu_seconds=time.time() - started,
                      source_unchanged=unchanged, original_trace_files_unchanged=originals_unchanged,
                      source_after=code_identity())
        report["passed"] = bool(report.get("passed") and report["original_actor_identity_matched"] and unchanged
                                and originals_unchanged and report["new_model_calls"] == 0)
        report["status"] = "passed" if report["passed"] else "failed"
        write(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=tuple(FAILED_TRACE_INDEX), required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--prior-recovery-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.candidate, args.data_root, args.prior_recovery_root, args.output)
    print(json.dumps({key: result[key] for key in ("candidate_id", "passed", "status", "common_restored_exactly")}))


if __name__ == "__main__":
    main()
