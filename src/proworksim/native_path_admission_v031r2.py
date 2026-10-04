"""Bounded SWE path-contract admission with inherited, immutable numerical proof.

Only new requests gain the explicit workspace-relative path contract. A rejected
call remains a rejected call; one fresh correction may follow its actual error.
No optimizer step, screening case, long stress rerun or historical rewrite occurs.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import time
import traceback

from . import model_qualification_v030 as original
from .online_training import probability_check
from .storage import digest, json_bytes, read_json

VERSION = "native-path-admission-v0.31r2"
CALL_LIMIT = 4
PATH = "public-note.json"
PROTECTED = ("actor", "critic", "actor_optimizer", "critic_optimizer", "recipe", "actor_identity",
             "policy_revision", "actor_steps", "critic_steps", "critic_has_nonzero_reward_history")


def path_tools():
    """Return a request-local contract; never mutate the historical tool schema."""
    tools = copy.deepcopy(original.TOOLS)
    function = tools[0]["function"]
    function["description"] = (
        "Read the actual public note inside this diagnostic workspace. The path must be "
        "workspace-relative, never absolute, and must not contain '..'. The only allowed "
        "path is exactly 'public-note.json'; '/public-note.json' is invalid.")
    function["parameters"]["properties"]["path"] = {
        "type": "string", "const": PATH,
        "description": "Exactly public-note.json relative to the diagnostic workspace; no leading slash or '..'."}
    return tools


class _ContractRenderer:
    """Measure the exact upgraded request during the original fixture search."""
    def __init__(self, owner):
        self.owner = owner

    def __getattr__(self, name):
        return getattr(self.owner, name)

    def prepare_request(self, request):
        request = copy.deepcopy(request)
        request["tools"] = path_tools()
        return self.owner.prepare_request(request)


def _request(owner, stage, fixture, observation, history):
    request, measurement = original._request(_ContractRenderer(owner), stage, fixture, observation, history)
    request["tools"] = path_tools()
    return request, measurement


def execute_read(response, fixture_root):
    """Resolve the actual unmodified sampled argument under the actual fixture root."""
    name, arguments = original._single_call(response)
    if response["body"]["choices"][0]["finish_reason"] == "length":
        raise ValueError("Public read did not reach an ordinary native stop")
    if name != "read_public_note" or set(arguments) != {"path"}:
        raise ValueError("Exactly read_public_note with one path argument is required")
    supplied = arguments["path"]
    if (not isinstance(supplied, str) or PurePosixPath(supplied).is_absolute()
            or PureWindowsPath(supplied).is_absolute() or ".." in PurePosixPath(supplied).parts
            or ".." in PureWindowsPath(supplied).parts or supplied != PATH):
        raise ValueError("Invalid workspace-relative path: only the unchanged argument 'public-note.json' is allowed; absolute paths and '..' are rejected")
    root = Path(fixture_root).resolve()
    target = (root / supplied).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Actual requested path resolves outside the diagnostic workspace")
    result = read_json(target)
    return {"passed": result == original.NOTE, "tool": name, "supplied_arguments": arguments,
            "resolved_path": str(target), "actual_result": result,
            "provenance": "actual_file_read_using_unchanged_native_argument_under_fixture_root"}


def validate_prior_qualification(owner, common_dir, prior_qualification):
    """Bind inherited update/16K/reload/return proof to this exact restored owner."""
    supplied = prior_qualification if isinstance(prior_qualification, dict) else {"path": str(prior_qualification)}
    path = Path(supplied["path"])
    sha256 = digest(path.read_bytes())
    if supplied.get("sha256", sha256) != sha256:
        raise ValueError("Prior qualification report checksum differs")
    prior, common = read_json(path), read_json(Path(common_dir) / "checkpoint.json")
    initial = original._state_fingerprints(owner)
    before = prior.get("common_before", {})
    if (owner.inference_profile.get("candidate_id") != "swe-next-14b"
            or owner.phase != "idle" or owner.busy or owner.sampling_only
            or not common.get("serialized_reload_exact")
            or initial["state_tensor_digest"] != common.get("state_tensor_digest")
            or before.get("state_tensor_digest") != initial["state_tensor_digest"]
            or before.get("actor_identity") != owner.freeze_identity()
            or any(initial[key] != 0 for key in ("actor_steps", "critic_steps", "policy_revision"))):
        raise ValueError("Inherited qualification requires the exact original SWE common actor at zero steps")
    if (owner.recipe["max_length"] != original.CONTEXT
            or owner.recipe["max_output_tokens"] != original.MAX_OUTPUT
            or owner.recipe["logprob_max_atol"] != 0.02 or owner.recipe["logprob_mean_atol"] != 0.002
            or owner.recipe["members"] != original.MEMBERS):
        raise ValueError("Original 16K/2048, probability gates and software recipe must remain frozen")
    update, roundtrip = prior.get("update") or {}, prior.get("checkpoint_roundtrip") or {}
    checks = (update.get("behavior_probability_checks", []), update.get("gradient_probability_checks", []))
    calls = prior.get("calls", [])
    required = ("training_integration_ready", "near_16k_capacity_demonstrated", "common_restored_exactly",
                "diagnostic_gradients_cleared", "updated_identity_return_passed")
    if (prior.get("version") != original.VERSION or not all(prior.get(key) is True for key in required)
            or prior.get("errors") != [] or len(calls) != 4
            or any(not row.get("actual_trace_complete") for row in calls)
            or calls[3].get("total_tokens", 0) < original.NEAR_CAPACITY
            or update.get("status") != "one_aggregate_diagnostic_update_completed"
            or update.get("actor_optimizer_steps") != 1 or update.get("critic_optimizer_steps") != 1
            or update.get("backward_decisions_completed") != 4
            or update.get("persistent_optimizer_objects_reused") is not True
            or any(len(rows) != 4 or not all(row.get("passed") is True for row in rows) for rows in checks)
            or not all(roundtrip.get(key) is True for key in ("common_reload_exact", "updated_reload_exact",
                       "updated_identity_changed", "updated_optimizer_states_changed"))
            or prior.get("common_after", {}).get("state_tensor_digest") != initial["state_tensor_digest"]):
        raise ValueError("Prior report does not contain the complete unchanged numerical/capacity/update/restore proof")
    return {"report": {"path": str(path.resolve()), "sha256": sha256},
            "common_checkpoint": {"path": str((Path(common_dir) / "checkpoint.json").resolve()),
                                  "sha256": digest((Path(common_dir) / "checkpoint.json").read_bytes())},
            "same_common_state_tensor_digest": initial["state_tensor_digest"],
            "same_actor_identity": owner.freeze_identity(), "inherited": True,
            "prior_inference_ready": prior["inference_ready"], "prior_training_ready": prior["training_ready"],
            "prior_result_reclassified": False,
            "behavior_probability_checks": copy.deepcopy(checks[0]),
            "gradient_probability_checks": copy.deepcopy(checks[1]),
            "near_16k_total_tokens": calls[3]["total_tokens"], "full_backward_decisions": 4,
            "actor_optimizer_steps_in_prior_run": 1, "critic_optimizer_steps_in_prior_run": 1,
            "checkpoint_roundtrip_passed": True, "updated_identity_return_passed": True,
            "scope": "Prior numerical evidence only; new path admission and screening require fresh observations"}


def _append_history(request, response, feedback):
    history = copy.deepcopy(request["messages"][1:])
    choices = response.get("body", {}).get("choices", [])
    message = copy.deepcopy(choices[0].get("message", {})) if choices else {}
    calls = message.get("tool_calls", [])
    if message:
        history.append(message)
    if len(calls) == 1 and calls[0].get("id"):
        history.append({"role": "tool", "tool_call_id": calls[0]["id"],
                        "content": json.dumps(feedback, ensure_ascii=False)})
    else:
        history.append({"role": "user", "content": "Actual controller validation_feedback (read_executed=false; no valid tool call was executed): "
                        + json.dumps(feedback, ensure_ascii=False)})
    return history


def _zero_step_check(owner, traces, folder):
    """Check every original target in eval/train mode and backpropagate, without a step."""
    result = {"status": "not_started", "optimizer_steps": 0, "actor_optimizer_steps": 0,
              "critic_optimizer_steps": 0, "trajectory_count": len(traces),
              "behavior_probability_checks": [], "gradient_probability_checks": [],
              "backward_decisions_completed": 0, "losses": [], "all_original_output_tokens_used": True,
              "business_rewards_used": False, "scope": "new path traces only; zero optimizer steps"}
    before = original._state_fingerprints(owner)
    optimizer_ids = id(owner.actor_optimizer), id(owner.critic_optimizer)
    started = time.monotonic()
    original._reset_peaks(owner)
    try:
        if owner.phase != "idle" or owner.busy or not traces:
            raise ValueError("Zero-step check requires all retained traces at a closed idle boundary")
        owner.phase = "updating"
        owner.clear_generation_cache()
        owner.model.eval()
        for index, trace in enumerate(traces):
            owner._resource_guard()
            with owner.torch.no_grad():
                values = owner.learning_logprobs(trace).detach().cpu().tolist()
            check = probability_check(values, trace["behavior_logprobs"], owner.recipe)
            result["behavior_probability_checks"].append({"trace_index": index, **check})
            original._write(folder / "zero-step-progress.json", result)
        if not all(row["passed"] for row in result["behavior_probability_checks"]):
            result["status"] = "behavior_probability_mismatch"
            return result
        owner.actor_optimizer.zero_grad(set_to_none=True)
        owner.critic_optimizer.zero_grad(set_to_none=True)
        owner.model.train()
        for index, trace in enumerate(traces):
            owner._resource_guard()
            probabilities = owner.learning_logprobs(trace)
            check = probability_check(probabilities.detach().cpu().tolist(), trace["behavior_logprobs"], owner.recipe)
            result["gradient_probability_checks"].append({"trace_index": index, **check})
            if not check["passed"]:
                result["status"] = "gradient_probability_mismatch"
                return result
            loss = -probabilities.mean() / len(traces)
            if not bool(owner.torch.isfinite(loss)):
                raise ValueError("Nonfinite path diagnostic loss")
            loss.backward()
            result["losses"].append({"trace_index": index, "input_tokens": len(trace["input_ids"]),
                "output_tokens": len(trace["output_ids"]), "loss": float(loss.detach()),
                "all_original_output_tokens_used": True})
            result["backward_decisions_completed"] += 1
            del probabilities, loss
            original._write(folder / "zero-step-progress.json", result)
        gradients = [parameter.grad for parameter in owner.actor_parameters.values() if parameter.grad is not None]
        finite = bool(gradients) and all(bool(owner.torch.isfinite(value).all()) for value in gradients)
        nonzero = sum(int(owner.torch.count_nonzero(value)) for value in gradients)
        result.update(finite_actor_gradients=finite, nonzero_actor_gradient_elements=nonzero)
        result["status"] = "full_trace_zero_step_backward_completed" if finite and nonzero > 0 else "invalid_actor_gradients"
    except Exception as exception:
        result.update(status="error", error={"type": type(exception).__name__, "message": str(exception)})
        (folder / "zero-step-errors.log").write_text(traceback.format_exc())
    finally:
        owner.actor_optimizer.zero_grad(set_to_none=True)
        owner.critic_optimizer.zero_grad(set_to_none=True)
        owner.model.eval()
        owner.clear_generation_cache()
        owner.phase = "idle"
        after = original._state_fingerprints(owner)
        result.update(before=before, after=after, elapsed_seconds=time.monotonic() - started,
            actor_optimizer_steps=after["actor_steps"] - before["actor_steps"],
            critic_optimizer_steps=after["critic_steps"] - before["critic_steps"],
            protected_state_unchanged=all(before["components"][key] == after["components"][key] for key in PROTECTED),
            persistent_optimizer_objects_reused=optimizer_ids == (id(owner.actor_optimizer), id(owner.critic_optimizer)),
            resources=original._cuda_peaks(owner))
        result["optimizer_steps"] = result["actor_optimizer_steps"] + result["critic_optimizer_steps"]
        result["passed"] = (result["status"] == "full_trace_zero_step_backward_completed"
            and result["backward_decisions_completed"] == len(traces)
            and result["optimizer_steps"] == 0 and result["protected_state_unchanged"]
            and result["persistent_optimizer_objects_reused"])
        original._write(folder / "zero-step-check.json", result)
    return result


def qualify_path(owner, output, *, common_dir, prior_qualification, on_stage=None):
    """Run at most four fresh native calls, then restore the exact original common."""
    folder, common_dir = Path(output), Path(common_dir)
    folder.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {"version": VERSION, "scope": "fresh path-contract technical admission; no business performance claim",
              "native_call_limit": CALL_LIMIT, "correction_call_limit": 1, "correction_calls_executed": 0,
              "inference_ready": False, "training_ready": False, "training_integration_ready": False,
              "common_restored_exactly": False, "new_optimizer_steps": 0, "optimizer_steps": 0,
              "near_16k_capacity_demonstrated": False, "near_16k_capacity_source": "inherited_prior_numerical_qualification",
              "near_16k_stress_rerun": False, "screening_episodes_consumed": 0,
              "training_screening_cases_used": False, "calls": [], "errors": [], "stages": [],
              "zero_step_check": None, "inherited_numerical_qualification": None}

    def stage(kind, label):
        report["stages"].append({"kind": kind, "label": label, "elapsed_seconds": time.monotonic() - started})
        original._write(folder / "report.json", report)
        if on_stage:
            on_stage(kind, label)

    def error(where, exception):
        report["errors"].append({"stage": where, "type": type(exception).__name__, "message": str(exception)})
        with (folder / "errors.log").open("a") as stream:
            stream.write("\n" + where + "\n" + traceback.format_exc())

    traces, history = [], []
    try:
        stage("boundary", "bind_original_numerical_proof_and_common")
        inherited = validate_prior_qualification(owner, common_dir, prior_qualification)
        report["inherited_numerical_qualification"] = inherited
        report["near_16k_capacity_demonstrated"] = True
        report["common_before"] = original._state_fingerprints(owner)
        original._write(folder / "path-contract.json", path_tools())
        original._write(folder / "recipe.json", owner.recipe)
        fixture = original._public_fixture(folder)
        report["source_fixture"] = {"path": str(fixture["source"]), "sha256": fixture["source_sha256"]}
        identity = owner.freeze_identity()
        owner.begin_window("v031r2-native-path-admission")

        def call(request, measurement, branch):
            nonlocal history
            index = len(report["calls"])
            if index >= CALL_LIMIT:
                raise ValueError("Frozen native call budget exhausted")
            stage("qualification_inference", f"native_call_{index + 1}_{branch}")
            directory = folder / f"native-call-{index + 1}"
            directory.mkdir()
            original._write(directory / "request.json", request)
            original._write(directory / "prompt-measurement.json", measurement)
            record = {"index": index, "branch": branch, "prompt": measurement,
                      "interface_passed": False, "actual_trace_complete": False,
                      "response_path": str(directory / "response.json")}
            report["calls"].append(record)
            call_started = time.monotonic()
            response = owner.complete(request, timeout_seconds=900)
            original._write(directory / "response.json", response)
            record.update(http_status=response.get("http_status"), elapsed_seconds=time.monotonic() - call_started)
            try:
                name, arguments = original._single_call(response)
                record.update(sampled_tool=name, supplied_arguments=arguments)
                result = execute_read(response, folder) if branch.startswith("read") else original._execute(
                    response, 1 if branch == "record_fact_8k" else 2, fixture, folder)
                record.update(interface_passed=result["passed"], tool_result=result)
                feedback = result["actual_result"]
                if not result["passed"]:
                    feedback = {"error": "Actual native tool arguments did not match the public file", "result": feedback}
            except Exception as exception:
                rejection = {"type": type(exception).__name__, "message": str(exception),
                    "supplied_tool": record.get("sampled_tool"), "supplied_arguments": record.get("supplied_arguments"),
                    "provenance": "actual_controller_rejection_of_unchanged_native_call",
                    "feedback_kind": "file_operation_error" if isinstance(exception, OSError) else "validation_feedback",
                    "read_executed": isinstance(exception, OSError), "read_succeeded": False}
                record["interface_error"] = rejection
                feedback = {"error": rejection}
            history = _append_history(request, response, feedback)
            original._write(directory / "actual-tool-feedback.json", feedback)
            try:
                trace = original._trace(response, identity, measurement["actual_rendered_prompt_tokens"])
                traces.append(trace)
                body = response["body"]
                record.update(actual_trace_complete=True, trace_sha256=digest(json_bytes(trace)),
                    input_tokens=len(trace["input_ids"]), output_tokens=len(trace["output_ids"]),
                    total_tokens=len(trace["input_ids"]) + len(trace["output_ids"]), actor_identity=body["actor_identity"],
                    finish_reason=body["choices"][0]["finish_reason"], protocol_parse_error=body.get("protocol_parse_error"))
            except Exception as exception:
                record["trace_error"] = {"type": type(exception).__name__, "message": str(exception)}
            original._write(folder / "report.json", report)
            return record

        request, measurement = _request(owner, 0, fixture, None, history)
        read_record = call(request, measurement, "read_initial")
        if not read_record["interface_passed"] and read_record["actual_trace_complete"]:
            retry = copy.deepcopy(request)
            retry["messages"] = [retry["messages"][0], *history, {"role": "user", "content": (
                "The actual controller rejected your preceding operation as shown above. One correction "
                "attempt is allowed. Follow the declared workspace-relative path contract and use "
                "read_public_note to read the actual note before recording any fact.")}]
            count, rendered, projection = original._render_count(owner, retry)
            report["correction_calls_executed"] = 1
            read_record = call(retry, {"target_prompt_tokens": None, "actual_rendered_prompt_tokens": count,
                "rendered_prompt_sha256": rendered, "projection": projection, "render_measurements": 1}, "read_correction")
        if read_record["interface_passed"] and read_record["actual_trace_complete"]:
            request, measurement = _request(owner, 1, fixture, read_record["tool_result"], history)
            call(request, measurement, "record_fact_8k")
            try:
                (folder / "missing-public-note.json").read_text()
            except FileNotFoundError as exception:
                missing = {"type": type(exception).__name__, "errno": exception.errno,
                    "path": "missing-public-note.json", "text": str(exception),
                    "provenance": "controller_executed_missing_file_read_not_a_model_action"}
            else:
                raise ValueError("The declared missing-file diagnostic unexpectedly exists")
            original._write(folder / "actual-missing-file-feedback.json", missing)
            request, measurement = _request(owner, 2, fixture,
                {"failure": missing, "actual_public_note": read_record["tool_result"]["actual_result"]}, history)
            call(request, measurement, "missing_file_feedback_10k")
        else:
            report["stopped_after_read_failure"] = True
        owner.finish_evaluation([], folder / "closed-native-window")
        report["native_window_closed"] = True
        successful = [row["branch"] for row in report["calls"] if row["interface_passed"] and row["actual_trace_complete"]]
        report["inference_ready"] = (any(branch.startswith("read") for branch in successful)
            and "record_fact_8k" in successful and "missing_file_feedback_10k" in successful
            and all(row["actual_trace_complete"] for row in report["calls"]))
        if len(traces) == len(report["calls"]) and traces:
            stage("qualification_update", "all_fresh_traces_full_probability_and_zero_step_backward")
            report["zero_step_check"] = _zero_step_check(owner, traces, folder)
            report["training_integration_ready"] = report["zero_step_check"]["passed"]
    except Exception as exception:
        error(report["stages"][-1]["label"] if report["stages"] else "initialization", exception)
    finally:
        try:
            stage("boundary", "restore_exact_original_common")
            owner.actor_optimizer.zero_grad(set_to_none=True)
            owner.critic_optimizer.zero_grad(set_to_none=True)
            owner.model.eval()
            if owner.busy:
                raise ValueError("Cannot restore while an actual native call is busy")
            if owner.phase == "collecting":
                owner.finish_evaluation([], folder / "closed-interrupted-native-window")
            if owner.phase != "idle":
                raise ValueError("Path admission did not reach an idle restore boundary")
            owner.restore_checkpoint(common_dir)
            final = original._state_fingerprints(owner)
            report["common_after"] = final
            report["common_restored_exactly"] = final["state_tensor_digest"] == read_json(common_dir / "checkpoint.json")["state_tensor_digest"]
            report["diagnostic_gradients_cleared"] = all(parameter.grad is None
                for parameter in [*owner.actor_parameters.values(), *owner.critic.parameters()])
            if not report["common_restored_exactly"] or not report["diagnostic_gradients_cleared"]:
                raise ValueError("Original common state or cleared gradients differ after restore")
        except Exception as exception:
            error("restore_exact_original_common", exception)
        check = report["zero_step_check"] or {}
        report["new_optimizer_steps"] = report["optimizer_steps"] = check.get("optimizer_steps", 0)
        report["training_ready"] = bool(report["inference_ready"] and report["training_integration_ready"]
            and report["inherited_numerical_qualification"] and report["common_restored_exactly"]
            and report.get("diagnostic_gradients_cleared") and report["new_optimizer_steps"] == 0 and not report["errors"])
        report["native_calls_executed"] = len(report["calls"])
        report["elapsed_seconds"] = time.monotonic() - started
        report["status"] = "measured_training_ready" if report["training_ready"] else "path_admission_not_ready"
        original._write(folder / "report.json", report)
    return report
