"""The one N1 fixed functional-state candidate: three archived traces, no update.

Run only under the separately authorized resource supervisor. No GPU discovery,
new sampling, retry, alternative implementation or automatic training lives here.
"""

import argparse
import os
from pathlib import Path
import time

from proworksim.audit import code_identity
from proworksim.functional_qwen_v022 import CONTRACT, learning_logprobs
from proworksim.online_training import probability_check
from proworksim.storage import atomic_write, digest, json_bytes, read_json

VERSION = "functional-state-N1-experiment-v0.22"


def ref(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def checked(record):
    if ref(record["path"]) != record:
        raise ValueError("Frozen request/owner reference changed")
    return Path(record["path"])


def write(path, data):
    atomic_write(Path(path), json_bytes(data))


def task(output, name):
    write(output / "task.json", {"task": name, "started_at": time.time(), "pid": os.getpid()})


def validate_plan(plan):
    if (plan.get("version") != "functional-state-N1-heldout-selection-v0.22"
            or plan.get("candidate_count") != 1 or plan.get("new_sampling") is not False
            or plan.get("optimizer_steps") != 0 or plan.get("actual_backward_required") is not True
            or plan.get("auto_retry_or_new_candidate") is not False
            or plan.get("probability_gate") != {"max_abs_logp": .02, "mean_abs_logp": .002}
            or [(r["input_tokens"], r["output_tokens"]) for r in plan["heldout_requests"]]
                != [(4251, 308), (13275, 2048)]):
        raise ValueError("N1 requires the frozen one-candidate three-request contract")
    owner_plan = read_json(checked(plan["owner_plan_ref"]))
    if (owner_plan["runtime_profile"]["version"] != "candidate-runtime-v0.20.1"
            or owner_plan["runtime_profile"]["devices"] != 1):
        raise ValueError("N1 must retain the original single-resident v0.20.1 configuration")
    return owner_plan


def run(plan_path, output):
    from proworksim.candidate_runtime_v0201 import CandidateActor

    output = Path(output).resolve()
    plan = read_json(plan_path)
    owner_plan = validate_plan(plan)
    source = code_identity()
    if source["code_dirty"] or os.environ.get("CUDA_VISIBLE_DEVICES") not in {str(i) for i in range(8)}:
        raise ValueError("Freeze N1 source and provide exactly one authorized physical GPU")
    output.mkdir(parents=True, exist_ok=False)
    report = {"version": VERSION, "status": "loading", "qualification_passed": False,
              "plan": ref(plan_path), "source_before": source, "candidate_contract": CONTRACT,
              "planned_requests": 3, "rows": [], "new_sampling": False,
              "actual_backward_calls": 0, "backward_calls_attempted": 0, "parameter_steps": 0,
              "implementation_selection_scope": "CPU candidate and checkpoint block8 frozen before reading retained request contents; no GPU-result-dependent modification",
              "scope": "Diagnostic negative mean of every original selected-token logprob; no reward or optimizer update, no claim of learning gain"}
    def save():
        write(output / "report.json", report)
    save()
    owner = None
    snapshot = None
    try:
        task(output, "N1-model-loading")
        owner = CandidateActor.from_candidate(owner_plan["model"], manifest=checked(owner_plan["manifest"]),
            profile=owner_plan["runtime_profile"], recipe=owner_plan["recipe"], output=output / "resident")
        initial = owner.freeze_identity()
        report["initial_actor_identity"] = initial
        snapshot = owner.capture_evaluation_state()
        requests = [("development", plan["development_response"], 8473, 146)] + [
            (f"heldout-{i}", row["response"], row["input_tokens"], row["output_tokens"])
            for i, row in enumerate(plan["heldout_requests"])]
        report["status"] = "running"
        for name, request_ref, inputs, outputs in requests:
            task(output, name)
            record = read_json(checked(request_ref))
            body = record["response"]
            trace = body["token_trace"]
            if (record["status"] != 200 or record["actor_identity"] != initial
                    or body["actor_identity"] != initial or body["inference_profile"] != owner.inference_profile
                    or len(trace["input_ids"]) != inputs or len(trace["output_ids"]) != outputs
                    or trace["raw_output_ids"] != trace["output_ids"]
                    or trace["raw_behavior_logprobs"] != trace["behavior_logprobs"]
                    or len(trace["behavior_logprobs"]) != outputs):
                raise ValueError("Request is not the frozen original actor/token/probability evidence")
            row = {"request": name, "record": request_ref, "input_tokens": inputs, "output_tokens": outputs,
                   "status": "forward_started", "actual_backward": False, "parameter_steps": 0,
                   "raw_tokens_and_behavior_preserved": True, "all_output_targets_included": outputs}
            report["rows"].append(row)
            save()
            owner._verify_execution()
            owner.model.train()
            owner.actor_optimizer.zero_grad(set_to_none=True)
            owner.torch.cuda.reset_peak_memory_stats()
            started = time.monotonic()
            probabilities = learning_logprobs(owner.model, trace)
            owner.torch.cuda.synchronize()
            row.update(forward_seconds=time.monotonic() - started, model_training=owner.model.training,
                       probability_dtype=str(probabilities.dtype), probability_requires_grad=probabilities.requires_grad)
            row["probability"] = probability_check(probabilities.detach().cpu().tolist(), trace["behavior_logprobs"], owner.recipe)
            row["forward_peak_gpu_allocated_bytes"] = owner.torch.cuda.max_memory_allocated()
            save()
            if not row["probability"]["passed"]:
                row["status"] = "failed_original_probability_gate"
                report["status"] = "stopped_candidate_probability_failure"
                del probabilities
                break
            row["status"] = "backward_started"
            row["backward_attempted"] = True
            report["backward_calls_attempted"] += 1
            save()
            started = time.monotonic()
            (-probabilities.mean()).backward()
            owner.torch.cuda.synchronize()
            gradients = [p.grad for p in owner.actor_parameters.values() if p.grad is not None]
            finite = bool(gradients) and all(bool(owner.torch.isfinite(g).all()) for g in gradients)
            row.update(actual_backward=True, backward_seconds=time.monotonic() - started,
                       gradient_tensors=len(gradients), finite_gradients=finite,
                       gradient_dtypes=sorted({str(g.dtype) for g in gradients}),
                       nonzero_gradient_elements=sum(int(owner.torch.count_nonzero(g)) for g in gradients),
                       peak_gpu_allocated_bytes=owner.torch.cuda.max_memory_allocated(),
                       actor_identity_unchanged=owner._make_identity() == initial,
                       status="complete" if finite else "failed_gradients")
            if finite and row["nonzero_gradient_elements"] == 0:
                row["status"] = "no_observable_gradient_diagnostic"
            report["actual_backward_calls"] += 1
            owner.actor_optimizer.zero_grad(set_to_none=True)
            del probabilities, gradients
            save()
            if not finite or not row["actor_identity_unchanged"]:
                report["status"] = "stopped_candidate_gradient_or_identity_failure"
                break
            if row["nonzero_gradient_elements"] == 0:
                report["status"] = "stopped_candidate_zero_gradient_diagnostic"
                break
        else:
            report["status"] = "qualified_fixed_list"
            report["qualification_passed"] = True
    except BaseException as error:
        report.update(status="interrupted_or_error", qualification_passed=False,
                      error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        if owner is not None:
            report.update(actor_steps=owner.actor_steps, critic_steps=owner.critic_steps)
            try:
                report["final_actor_identity"] = owner._make_identity()
                report["actor_identity_unchanged"] = report["final_actor_identity"] == report["initial_actor_identity"]
                if snapshot is not None:
                    report["learning_state_guard"] = owner.finish_evaluation_guard(snapshot)
                if (owner.actor_steps or owner.critic_steps or not report["actor_identity_unchanged"]
                        or not report.get("learning_state_guard", {}).get("learning_unchanged", False)):
                    report.update(qualification_passed=False, status="failed_final_identity_guard")
            except BaseException as error:
                report.update(qualification_passed=False,
                              final_identity_error={"type": type(error).__name__, "message": str(error)})
        report["source_after"] = code_identity()
        report["source_unchanged"] = report["source_after"] == source
        if not report["source_unchanged"]:
            report["qualification_passed"] = False
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.plan, args.output)
    return 0 if report["qualification_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
