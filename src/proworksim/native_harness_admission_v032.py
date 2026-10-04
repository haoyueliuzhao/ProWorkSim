"""Fresh no-argument native admission using the unchanged v031 numerical learner.

The three-call diagnostic includes a real zero-argument read and real public
facts at 8K/10K. One actual rejected read may be corrected once; original traces
are never altered. Previously measured 16K/update evidence is inherited only
under the exact old common state; all fresh targets receive zero-step backward.
"""
import copy
from pathlib import Path
import time
import traceback

from . import model_qualification_v030 as original
from . import native_path_admission_v031r2 as prior
from .storage import digest, json_bytes, read_json

VERSION = "native-harness-admission-v0.32"
CALL_LIMIT = 4


def public_tools():
    tools = copy.deepcopy(original.TOOLS)
    tools[0]["function"]["description"] = (
        "Read the actual public-note.json file in this diagnostic workspace. "
        "This function takes no arguments; omit every parameter element. "
        "The controller reads that fixed public file and returns its actual contents.")
    tools[0]["function"]["parameters"] = {
        "type": "object", "properties": {}, "required": [], "additionalProperties": False}
    return tools


class _ContractRenderer:
    def __init__(self, owner):
        self.owner = owner

    def __getattr__(self, name):
        return getattr(self.owner, name)

    def prepare_request(self, request):
        request = copy.deepcopy(request)
        request["tools"] = public_tools()
        return self.owner.prepare_request(request)


def _request(owner, stage, fixture, observation, history):
    request, measurement = original._request(_ContractRenderer(owner), stage, fixture, observation, history)
    request["tools"] = public_tools()
    return request, measurement


def execute_read(response, fixture_root):
    name, arguments = original._single_call(response)
    if response["body"]["choices"][0]["finish_reason"] == "length":
        raise ValueError("Public read did not reach an ordinary native stop")
    if name != "read_public_note" or arguments != {}:
        raise ValueError("read_public_note takes exactly zero arguments under its supplied public schema")
    target = Path(fixture_root) / "public-note.json"
    result = read_json(target)
    return {"passed": result == original.NOTE, "tool": name, "supplied_arguments": arguments,
            "resolved_path": str(target.resolve()), "actual_result": result,
            "provenance": "actual_zero_argument_function_read_of_its_declared_fixed_public_file"}


def qualify_harness(owner, output, *, common_dir, prior_qualification, on_stage=None):
    """Run at most four fresh native calls, then restore the exact original common."""
    folder, common_dir = Path(output), Path(common_dir)
    folder.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {"version": VERSION, "scope": "fresh no-argument native harness admission; no business performance claim",
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
        inherited = prior.validate_prior_qualification(owner, common_dir, prior_qualification)
        report["inherited_numerical_qualification"] = inherited
        report["near_16k_capacity_demonstrated"] = True
        report["common_before"] = original._state_fingerprints(owner)
        original._write(folder / "public-contract.json", public_tools())
        original._write(folder / "recipe.json", owner.recipe)
        fixture = original._public_fixture(folder)
        report["source_fixture"] = {"path": str(fixture["source"]), "sha256": fixture["source_sha256"]}
        identity = owner.freeze_identity()
        owner.begin_window("v032-native-harness-admission")

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
            history = prior._append_history(request, response, feedback)
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
                "attempt is allowed. Follow the declared public schema: read_public_note takes zero arguments. Use "
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
            report["zero_step_check"] = prior._zero_step_check(owner, traces, folder)
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
                raise ValueError("Harness admission did not reach an idle restore boundary")
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
        report["status"] = "measured_training_ready" if report["training_ready"] else "harness_admission_not_ready"
        original._write(folder / "report.json", report)
    return report
