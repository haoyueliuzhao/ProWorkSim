"""Four native diagnostic calls and one reversible aggregate technical update.

This uses the existing owner, PPO sum, critic loss and persistent optimizers. The
declared +1 advantage/critic target is a numerical control, never a work reward.
No screening case, allocation support or learned policy survives common restore.
"""
from __future__ import annotations

import ast
import copy
import json
import math
from pathlib import Path
import time
import traceback

from .online_training import ppo_sum, probability_check, tensor_tree_digest
from .storage import atomic_write, digest, json_bytes, read_json

VERSION = "model-qualification-v0.30"
CALL_LIMIT = 4
MAX_OUTPUT = 2048
CONTEXT = 16384
NEAR_CAPACITY = 15360
PROMPT_TARGETS = (None, 8192, 10240, 14336)
NOTE = {"code": "NATIVE-DIAGNOSTIC-AMBER", "revision": 17}
MEMBERS = ["member_a", "member_b", "software_inactive"]
TOOLS = [
    {"type": "function", "function": {"name": "read_public_note",
        "description": "Read an actual public diagnostic note file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                       "required": ["path"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "record_fact",
        "description": "Record the code and integer revision observed in the public note.",
        "parameters": {"type": "object", "properties": {"code": {"type": "string"},
                         "revision": {"type": "integer"}},
                       "required": ["code", "revision"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "write_diagnostic_file",
        "description": "Write the requested independent Python functions to diagnostic_functions.py.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"},
                         "content": {"type": "string"}}, "required": ["path", "content"],
                       "additionalProperties": False}}},
]


def _write(path, value):
    atomic_write(Path(path), json_bytes(value))


def _public_fixture(folder):
    note = folder / "public-note.json"
    _write(note, NOTE)
    source = ["# Real, controller-authored public interface fixture; not a software screening case.\n",
              "NOTE_CODE = " + repr(NOTE["code"]) + "\n", "NOTE_REVISION = 17\n\n"]
    for index in range(1600):
        source.extend([f"def public_fixture_{index:04d}(value):\n",
                       f'    """Independent public fixture transformation number {index}."""\n',
                       f"    return (value * {index + 1} + {index % 113}) % 100003\n\n"])
    text = "".join(source)
    ast.parse(text)
    path = folder / "public_fixture.py"
    path.write_text(text)
    return {"note": note, "source": path, "source_sha256": digest(path.read_bytes()),
            "lines": path.read_text().splitlines(keepends=True)}


def _render_count(owner, request):
    rendered, _, projection = owner.prepare_request(request)
    ids = owner.tokenizer(rendered, add_special_tokens=False)["input_ids"]
    return len(ids), digest(str(rendered).encode()), projection


def _request(owner, stage, fixture, observation, native_history=()):
    system = ("This is a bounded native-interface technical diagnostic, not a business task. "
              "Emit exactly one supplied native tool call. Tool results are actual controller "
              "observations only where explicitly stated. Do not fabricate execution results.")
    if stage == 0:
        task = "Read public-note.json using read_public_note. Do not record a fact before reading it."
    elif stage == 1:
        task = ("Record the actual public note's code and integer revision using record_fact. "
                "The following observation came from the real file read described in its provenance.\n"
                + json.dumps(observation, ensure_ascii=False))
    elif stage == 2:
        task = ("The controller independently attempted the missing-file read below and caught the "
                "real exception. That failed read was NOT an action sampled from you. Continue from "
                "this feedback: record the already read actual public note's code and revision "
                "using record_fact; do not invent the missing file.\n"
                + json.dumps(observation, ensure_ascii=False))
    else:
        task = ("Call write_diagnostic_file with path diagnostic_functions.py. Its content must be "
                "a complete Python module containing exactly 180 independent top-level functions "
                "named diagnostic_000 through diagnostic_179. Each takes one argument value and "
                "returns value plus its numeric suffix (for example diagnostic_000 returns value + 0). "
                "Write each function separately in full, with no loop, comprehension, generated-code "
                "wrapper or ellipsis. This is an output/gradient length diagnostic. Do not describe "
                "the file instead of calling the tool. Use the ordinary native generation stop rules.")
    prefix = [{"role": "system", "content": system},
              *copy.deepcopy(list(native_history) if stage in (1, 2) else []),
              {"role": "user", "content": task}]
    request = {"model": owner.inference_profile.get("candidate_id", "resident-diagnostic"),
               "temperature": owner.recipe["temperature"], "max_tokens": MAX_OUTPUT,
               "tools": copy.deepcopy(TOOLS), "messages": prefix}
    target = PROMPT_TARGETS[stage]
    if target is None:
        count, rendered_sha, projection = _render_count(owner, request)
        return request, {"target_prompt_tokens": None, "actual_rendered_prompt_tokens": count,
                         "rendered_prompt_sha256": rendered_sha, "projection": projection,
                         "fixture_lines": 0, "render_measurements": 1}
    lines = fixture["lines"]
    header = ("\n\nThe controller actually read this prefix from public_fixture.py, SHA256 "
              + fixture["source_sha256"] + ". It is real public fixture source, not a tool result "
              "attributed to a model action. It does not change the requested single call.\n```python\n")
    measured = {}

    def measure(length):
        current = copy.deepcopy(request)
        current["messages"][-1]["content"] = task + header + "".join(lines[:length]) + "```\n"
        tokens, rendered_sha, projection = _render_count(owner, current)
        measured[length] = (tokens, rendered_sha, projection, current)
        return tokens

    if measure(0) > target:
        raise ValueError("Unshortened public diagnostic instruction already exceeds its prompt target")
    left, right = 0, len(lines)
    while left < right:
        midpoint = (left + right + 1) // 2
        if measure(midpoint) <= target:
            left = midpoint
        else:
            right = midpoint - 1
    if left not in measured:
        measure(left)
    tokens, rendered_sha, projection, current = measured[left]
    if not target - 128 <= tokens <= target:
        raise ValueError("Real fixture source could not achieve the frozen native prompt length")
    return current, {"target_prompt_tokens": target, "actual_rendered_prompt_tokens": tokens,
                     "rendered_prompt_sha256": rendered_sha, "projection": projection,
                     "fixture_path": str(fixture["source"]), "fixture_sha256": fixture["source_sha256"],
                     "fixture_first_line": 1, "fixture_last_line": left,
                     "fixture_prefix_sha256": digest("".join(lines[:left]).encode()),
                     "render_measurements": len(measured),
                     "scope": "Predeclared prompt construction from whole real source lines; no sampled tokens cropped"}


def _single_call(response):
    if response.get("http_status") != 200:
        raise ValueError("Native inference did not return HTTP 200")
    body = response["body"]
    if body.get("protocol_parse_error"):
        raise ValueError("Native output format failed: " + str(body["protocol_parse_error"]))
    calls = body["choices"][0]["message"].get("tool_calls", [])
    if len(calls) != 1:
        raise ValueError("Exactly one native tool call is required")
    call = calls[0]
    arguments = json.loads(call["function"]["arguments"])
    if not isinstance(arguments, dict):
        raise ValueError("Native arguments must be an object")
    return call["function"]["name"], arguments


def _execute(response, stage, fixture, folder):
    """Execute only the public technical environment's narrow real file tools."""
    name, arguments = _single_call(response)
    if stage < 3 and response["body"]["choices"][0]["finish_reason"] == "length":
        raise ValueError("Normal interface diagnostic did not reach an ordinary native stop")
    if stage == 0:
        if name != "read_public_note" or arguments != {"path": "public-note.json"}:
            raise ValueError("The first public operation must read the declared actual note")
        result = read_json(fixture["note"])
        return {"passed": result == NOTE, "tool": name, "actual_result": result,
                "provenance": "actual_file_read_requested_by_native_model_call"}
    if stage in (1, 2):
        actual = read_json(fixture["note"])
        passed = (name == "record_fact" and arguments == actual
                  and type(arguments.get("revision")) is int)
        result = {"recorded": arguments, "matches_actual_public_note": passed}
        if name == "record_fact":
            _write(folder / f"recorded-fact-{stage}.json", result)
        return {"passed": passed, "tool": name, "actual_result": result,
                "provenance": "actual_native_arguments_checked_against_real_public_file"}
    if (name != "write_diagnostic_file" or set(arguments) != {"path", "content"}
            or arguments["path"] != "diagnostic_functions.py" or not isinstance(arguments["content"], str)):
        raise ValueError("Stress output did not contain the requested single public write")
    text = arguments["content"]
    (folder / "diagnostic_functions.py").write_text(text)
    tree = ast.parse(text)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    independent = len(functions) == len(tree.body) == 180
    independent &= not any(isinstance(node, (ast.For, ast.While, ast.ListComp, ast.SetComp,
                                            ast.DictComp, ast.GeneratorExp))
                           or isinstance(node, ast.Constant) and node.value is Ellipsis
                           for node in ast.walk(tree))
    for index, node in enumerate(functions):
        expected = ast.parse(f"def diagnostic_{index:03d}(value):\n    return value + {index}\n").body[0]
        independent &= ast.dump(node, include_attributes=False) == ast.dump(expected, include_attributes=False)
    return {"passed": bool(independent), "tool": name, "actual_result": {
                "file_sha256": digest(text.encode()), "independent_function_count": len(functions),
                "requested_independent_functions": 180},
            "provenance": "actual_native_public_file_write_not_work_performance"}


def _trace(response, identity, expected_prompt):
    body = response.get("body", {})
    trace = body.get("token_trace")
    if response.get("http_status") != 200 or not isinstance(trace, dict):
        raise ValueError("A complete actual sampled token trace is required")
    inputs, outputs = trace.get("input_ids"), trace.get("output_ids")
    values = trace.get("behavior_logprobs")
    if (body.get("actor_identity") != identity or not isinstance(inputs, list) or not inputs
            or not isinstance(outputs, list) or not outputs or not isinstance(values, list)
            or len(inputs) != expected_prompt or len(outputs) != len(values)
            or outputs != trace.get("raw_output_ids") or values != trace.get("raw_behavior_logprobs")
            or trace.get("input_mask") != [0] * len(inputs)
            or trace.get("output_mask") != [1] * len(outputs)
            or not body.get("generation_stop_check", {}).get("all_generated_tokens_retained")
            or len(inputs) + len(outputs) > CONTEXT or len(outputs) > MAX_OUTPUT
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in values)):
        raise ValueError("Actual identity, complete original token targets or behavior probabilities differ")
    return copy.deepcopy(trace)


def _state_fingerprints(owner):
    state = owner._state_bundle()
    fields = ("actor", "critic", "actor_optimizer", "critic_optimizer", "rng_cpu", "rng_cuda",
              "recipe", "actor_identity", "policy_revision", "actor_steps", "critic_steps",
              "critic_has_nonzero_reward_history", "last_window_id", "used_window_ids")
    return {"state_tensor_digest": tensor_tree_digest(state, owner.torch),
            "components": {key: tensor_tree_digest(state[key], owner.torch) for key in fields},
            "actor_identity": owner.freeze_identity(), "actor_steps": owner.actor_steps,
            "critic_steps": owner.critic_steps, "policy_revision": owner.policy_revision}


def _cuda_peaks(owner):
    if not str(owner.device).startswith("cuda"):
        return {"device": "cpu", "peak_gpu_allocated_bytes": {}}
    return {"device": str(owner.device), "peak_gpu_allocated_bytes": {
        str(index): owner.torch.cuda.max_memory_allocated(index)
        for index in range(owner.torch.cuda.device_count())}, "peak_gpu_reserved_bytes": {
        str(index): owner.torch.cuda.max_memory_reserved(index)
        for index in range(owner.torch.cuda.device_count())}}


def _reset_peaks(owner):
    if str(owner.device).startswith("cuda"):
        for index in range(owner.torch.cuda.device_count()):
            owner.torch.cuda.reset_peak_memory_stats(index)


def _aggregate_update(owner, traces, folder):
    """Exactly one owner optimizer step after all full-sequence gates pass."""
    torch = owner.torch
    result = {"status": "not_started", "actor_optimizer_steps": 0, "critic_optimizer_steps": 0,
              "backward_decisions_completed": 0, "advantages": [1.0] * CALL_LIMIT,
              "critic_targets": [1.0] * CALL_LIMIT, "business_rewards_used": False,
              "diagnostic_control_only": True, "trajectory_count": len(traces),
              "actor_normalization": "sum of four per-trace token means divided by four",
              "base_loss": "original online_training.ppo_sum and original squared critic loss",
              "behavior_probability_checks": [], "gradient_probability_checks": [], "losses": []}
    if len(traces) != CALL_LIMIT:
        result["status"] = "zero_step_incomplete_actual_trace_inventory"
        return result
    before = _state_fingerprints(owner)
    before_actor = owner.actor_state()
    before_critic = {name: tensor.detach().cpu().clone() for name, tensor in owner.critic.state_dict().items()}
    actor_steps, critic_steps = owner.actor_steps, owner.critic_steps
    optimizer_ids = id(owner.actor_optimizer), id(owner.critic_optimizer)
    cache_before = owner.cache_clear_count
    _reset_peaks(owner)
    started = time.monotonic()
    try:
        if owner.phase != "idle" or owner.busy:
            raise ValueError("Aggregate diagnostic update requires a closed native window")
        owner.phase = "updating"
        owner.model.eval()
        owner.clear_generation_cache()
        for index, trace in enumerate(traces):
            owner._resource_guard()
            replay_started = time.monotonic()
            with torch.no_grad():
                values = owner.learning_logprobs(trace).detach().cpu().tolist()
            check = probability_check(values, trace["behavior_logprobs"], owner.recipe)
            result["behavior_probability_checks"].append({"trace_index": index,
                "elapsed_seconds": time.monotonic() - replay_started, **check})
            _write(folder / "aggregate-update-progress.json", result)
        if not all(row["passed"] for row in result["behavior_probability_checks"]):
            result["status"] = "zero_step_behavior_probability_mismatch"
            return result
        owner.actor_optimizer.zero_grad(set_to_none=True)
        owner.critic_optimizer.zero_grad(set_to_none=True)
        owner.model.train()
        for index, trace in enumerate(traces):
            owner._resource_guard()
            backward_started = time.monotonic()
            probabilities = owner.learning_logprobs(trace)
            check = probability_check(probabilities.detach().cpu().tolist(), trace["behavior_logprobs"], owner.recipe)
            result["gradient_probability_checks"].append({"trace_index": index, **check})
            if not check["passed"]:
                result["status"] = "zero_step_gradient_probability_mismatch"
                return result
            behavior = torch.tensor(trace["behavior_logprobs"], device=probabilities.device)
            total, ratio = ppo_sum(torch, probabilities, behavior, 1.0, owner.recipe["clip"])
            denominator = CALL_LIMIT * len(trace["output_ids"])
            actor_loss = total / denominator
            if not bool(torch.isfinite(actor_loss)):
                raise ValueError("Nonfinite diagnostic actor loss")
            actor_loss.backward()
            features = torch.zeros(len(owner.recipe["members"]) * 10, dtype=torch.float32,
                                   device=owner.device)
            value = owner.critic(features).squeeze()
            critic_loss = 0.5 * (value - 1.0).square() / CALL_LIMIT
            if not bool(torch.isfinite(critic_loss)):
                raise ValueError("Nonfinite diagnostic critic loss")
            (critic_loss * owner.recipe["critic_coefficient"]).backward()
            result["losses"].append({"trace_index": index, "input_tokens": len(trace["input_ids"]),
                "output_tokens": len(trace["output_ids"]), "actor_denominator": denominator,
                "critic_denominator": CALL_LIMIT, "actor_loss": float(actor_loss.detach()),
                "critic_loss": float(critic_loss.detach()),
                "forward_backward_seconds": time.monotonic() - backward_started,
                "ratio_range": [float(ratio.detach().min()), float(ratio.detach().max())],
                "all_original_output_tokens_used": True})
            result["backward_decisions_completed"] += 1
            del probabilities, behavior, total, ratio, actor_loss, features, value, critic_loss
            _write(folder / "aggregate-update-progress.json", result)
        actor_norm = torch.nn.utils.clip_grad_norm_(list(owner.actor_parameters.values()), owner.recipe["gradient_clip"])
        critic_norm = torch.nn.utils.clip_grad_norm_(owner.critic.parameters(), owner.recipe["gradient_clip"])
        result["gradient_norms_before_clip"] = {"actor": float(actor_norm), "critic": float(critic_norm)}
        if (not bool(torch.isfinite(actor_norm)) or not bool(torch.isfinite(critic_norm))
                or float(actor_norm) <= 0 or float(critic_norm) <= 0):
            result["status"] = "zero_step_nonfinite_or_zero_diagnostic_gradient"
            return result
        owner.actor_optimizer.step()
        owner.actor_steps += 1
        owner.policy_revision += 1
        owner._identity = owner._make_identity()
        result.update(status="actor_updated_pending_critic", actor_optimizer_steps=1)
        _write(folder / "aggregate-update-progress.json", result)
        owner.critic_optimizer.step()
        owner.critic_steps += 1
        owner.critic_has_nonzero_reward_history = True
        result["critic_optimizer_steps"] = 1
        after_actor = owner.actor_state()
        after_critic = owner.critic.state_dict()
        result["changed_actor_elements"] = sum(int((after_actor[name] != before_actor[name]).sum())
                                               for name in before_actor)
        result["changed_critic_elements"] = sum(int((after_critic[name].detach().cpu() != before_critic[name]).sum())
                                                for name in before_critic)
        if result["changed_actor_elements"] <= 0 or result["changed_critic_elements"] <= 0:
            raise ValueError("A diagnostic optimizer step did not change actual actor/critic parameters")
        result["status"] = "one_aggregate_diagnostic_update_completed"
    finally:
        owner.actor_optimizer.zero_grad(set_to_none=True)
        owner.critic_optimizer.zero_grad(set_to_none=True)
        owner.model.eval()
        owner.clear_generation_cache()
        owner.phase = "idle"
        owner._identity = owner._make_identity()
        result.update(before=before, after=_state_fingerprints(owner),
                      actor_optimizer_steps=owner.actor_steps - actor_steps,
                      critic_optimizer_steps=owner.critic_steps - critic_steps,
                      persistent_optimizer_objects_reused=optimizer_ids == (id(owner.actor_optimizer), id(owner.critic_optimizer)),
                      generation_cache_clear_count_before=cache_before,
                      generation_cache_clear_count_after=owner.cache_clear_count,
                      elapsed_seconds=time.monotonic() - started, resources=_cuda_peaks(owner))
        _write(folder / "aggregate-update.json", result)
    return result


def qualify(owner, output, *, common_dir, return_probe, on_stage=None):
    """Run bounded technical qualification, then restore the exact common state.

    ``return_probe`` owns one actual managed-SDK opportunity and returns its
    actual response identity inventory; it may not substitute a business score.
    The caller has already saved ``common_dir`` before any diagnostic sampling.
    """
    folder, common_dir = Path(output), Path(common_dir)
    folder.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {"version": VERSION, "scope": "technical qualification, not work performance or allocation benefit",
              "inference_ready": False, "training_integration_ready": False, "training_ready": False,
              "near_16k_capacity_demonstrated": False, "capacity_status": "capacity_not_demonstrated",
              "native_call_limit": CALL_LIMIT, "return_probe_call_limit": 1, "aggregate_update_limit": 1,
              "calls": [], "errors": [], "stages": [], "training_screening_cases_used": False,
              "diagnostic_advantage": 1.0, "diagnostic_critic_target": 1.0,
              "diagnostic_signals_are_business_rewards": False, "common_restored_exactly": False,
              "screening_episodes_consumed": 0, "source_fixture": {}, "update": None,
              "return_probe": None}

    def stage(kind, label):
        report["stages"].append({"kind": kind, "label": label,
                                 "elapsed_seconds": time.monotonic() - started})
        _write(folder / "report.json", report)
        if on_stage:
            on_stage(kind, label)

    def error(where, exception):
        report["errors"].append({"stage": where, "type": type(exception).__name__, "message": str(exception)})
        with (folder / "errors.log").open("a") as stream:
            stream.write("\n" + where + "\n" + traceback.format_exc())

    initial = None
    try:
        stage("boundary", "validate_common_before_sampling")
        if owner.phase != "idle" or owner.busy or owner.sampling_only:
            raise ValueError("Qualification starts from an idle learner with persistent optimizers")
        if (owner.recipe["max_length"] != CONTEXT or owner.recipe["max_output_tokens"] != MAX_OUTPUT
                or owner.recipe["logprob_max_atol"] != 0.02 or owner.recipe["logprob_mean_atol"] != 0.002
                or owner.recipe["members"] != MEMBERS):
            raise ValueError("Qualification requires the frozen 16K/2048, unchanged probability gate and software member recipe")
        common = read_json(common_dir / "checkpoint.json")
        initial = _state_fingerprints(owner)
        if (not common.get("serialized_reload_exact")
                or initial["state_tensor_digest"] != common["state_tensor_digest"]):
            raise ValueError("Owner must exactly equal the already saved common checkpoint before sampling")
        report["common_before"] = initial
        fixture = _public_fixture(folder)
        report["source_fixture"] = {"path": str(fixture["source"]), "sha256": fixture["source_sha256"],
                                     "scope": "new standalone technical fixture, no model-screening case material"}
        _write(folder / "recipe.json", owner.recipe)
        identity = owner.freeze_identity()
        owner.begin_window("v030-native-qualification")
        traces, first_read, native_history = [], None, []
        for index in range(CALL_LIMIT):
            stage("qualification_inference", f"native_call_{index + 1}_of_4")
            if index == 1:
                observation = first_read or {"provenance": "controller_actual_note_read_after_invalid_model_read",
                                             "actual_result": read_json(fixture["note"])}
            elif index == 2:
                try:
                    (folder / "missing-public-note.json").read_text()
                except FileNotFoundError as exception:
                    missing = {"type": type(exception).__name__, "errno": exception.errno,
                               "path": "missing-public-note.json", "text": str(exception),
                               "provenance": "controller_executed_missing_file_read_not_a_model_action"}
                else:
                    raise ValueError("The declared missing-file diagnostic unexpectedly exists")
                _write(folder / "actual-missing-file-feedback.json", missing)
                observation = {"failure": missing, "actual_public_note": read_json(fixture["note"])}
            else:
                observation = None
            request, measurement = _request(owner, index, fixture, observation, native_history)
            call_dir = folder / f"native-call-{index + 1}"
            call_dir.mkdir()
            _write(call_dir / "request.json", request)
            _write(call_dir / "prompt-measurement.json", measurement)
            call_started = time.monotonic()
            response = owner.complete(request, timeout_seconds=900)
            _write(call_dir / "response.json", response)
            record = {"index": index, "response_path": str(call_dir / "response.json"),
                      "http_status": response.get("http_status"), "elapsed_seconds": time.monotonic() - call_started,
                      "prompt": measurement, "interface_passed": False, "actual_trace_complete": False,
                      "stress_output_failure_affects_inference_gate": False if index == 3 else None}
            try:
                tool_result = _execute(response, index, fixture, folder)
                record.update(interface_passed=tool_result["passed"], tool_result=tool_result)
                if index == 0 and tool_result["passed"]:
                    first_read = tool_result
                if tool_result["passed"] and index < 3:
                    message = response["body"]["choices"][0]["message"]
                    native_history = [*copy.deepcopy(request["messages"][1:]), copy.deepcopy(message),
                                      {"role": "tool", "tool_call_id": message["tool_calls"][0]["id"],
                                       "content": json.dumps(tool_result["actual_result"], ensure_ascii=False)}]
            except Exception as exception:
                record["interface_error"] = {"type": type(exception).__name__, "message": str(exception)}
            try:
                trace = _trace(response, identity, measurement["actual_rendered_prompt_tokens"])
                traces.append(trace)
                body = response["body"]
                record.update(actual_trace_complete=True, trace_sha256=digest(json_bytes(trace)),
                              input_tokens=len(trace["input_ids"]), output_tokens=len(trace["output_ids"]),
                              total_tokens=len(trace["input_ids"]) + len(trace["output_ids"]),
                              finish_reason=body["choices"][0]["finish_reason"],
                              protocol_parse_error=body.get("protocol_parse_error"),
                              service_record=body.get("service_record", {}), actor_identity=body["actor_identity"])
            except Exception as exception:
                record["trace_error"] = {"type": type(exception).__name__, "message": str(exception)}
            report["calls"].append(record)
            _write(folder / "report.json", report)
        owner.finish_evaluation([], folder / "closed-native-window")
        report["native_window_closed"] = True
        report["inference_ready"] = all(row["interface_passed"] and row["actual_trace_complete"]
                                         for row in report["calls"][:3])
        stage("qualification_update", "full_trace_probability_and_one_aggregate_update")
        update = _aggregate_update(owner, traces, folder)
        report["update"] = update
        if update["status"] == "one_aggregate_diagnostic_update_completed":
            updated = _state_fingerprints(owner)
            stage("boundary", "save_updated_and_reload_from_common")
            checkpoint_started = time.monotonic()
            checkpoint = owner.save_checkpoint(folder / "updated-checkpoint")
            owner.restore_checkpoint(common_dir)
            reloaded_common = _state_fingerprints(owner)
            owner.restore_checkpoint(folder / "updated-checkpoint")
            reloaded_updated = _state_fingerprints(owner)
            checkpoint_check = {"checkpoint": checkpoint,
                "common_reload_exact": reloaded_common["state_tensor_digest"] == initial["state_tensor_digest"],
                "updated_reload_exact": reloaded_updated["state_tensor_digest"] == updated["state_tensor_digest"],
                "updated_identity_changed": updated["actor_identity"] != initial["actor_identity"],
                "updated_optimizer_states_changed": all(updated["components"][key] != initial["components"][key]
                                                        for key in ("actor_optimizer", "critic_optimizer")),
                "updated_state": updated, "reloaded_state": reloaded_updated,
                "elapsed_seconds": time.monotonic() - checkpoint_started}
            report["checkpoint_roundtrip"] = checkpoint_check
            if not all(checkpoint_check[key] for key in ("common_reload_exact", "updated_reload_exact",
                                                         "updated_identity_changed", "updated_optimizer_states_changed")):
                raise ValueError("Real diagnostic update/save/reload proof failed")
            stage("boundary", "updated_identity_managed_sdk_return_probe")
            probe_started = time.monotonic()
            probe = return_probe(owner, folder / "updated-return-probe")
            report["return_probe"] = probe
            observed = probe.get("observed_actor_identities", [])
            after_probe = _state_fingerprints(owner)
            protected = ("actor", "critic", "actor_optimizer", "critic_optimizer", "recipe",
                         "actor_identity", "policy_revision", "actor_steps", "critic_steps",
                         "critic_has_nonzero_reward_history", "rng_cpu", "rng_cuda")
            unchanged = all(after_probe["components"][key] == updated["components"][key]
                            for key in protected)
            probe_passed = (probe.get("calls") == 1
                and probe.get("expected_actor_identity") == updated["actor_identity"]
                and len(observed) == 1 and observed[0] == updated["actor_identity"]
                and observed[0] != initial["actor_identity"]
                and len(probe.get("window_ids", [])) == 1
                and bool(probe["window_ids"][0])
                and probe.get("learning_unchanged") is True and probe.get("rng_restored_exactly") is True
                and owner.phase == "idle" and not owner.busy and unchanged)
            report["updated_identity_return_passed"] = probe_passed
            report["return_probe_validation"] = {"learning_and_rng_components_unchanged": unchanged,
                "elapsed_seconds": time.monotonic() - probe_started, "after_probe": after_probe}
            if not probe_passed:
                raise ValueError("The one actual managed-SDK return call did not prove new-identity reentry")
            report["training_integration_ready"] = True
            stress = report["calls"][3]
            report["near_16k_capacity_demonstrated"] = (
                stress.get("total_tokens", 0) >= NEAR_CAPACITY
                and update["backward_decisions_completed"] == CALL_LIMIT
                and all(row["passed"] for row in update["gradient_probability_checks"]))
            report["capacity_status"] = ("actual_near_16k_full_sequence_backward_demonstrated"
                                         if report["near_16k_capacity_demonstrated"] else "capacity_not_demonstrated")
    except Exception as exception:
        error(report["stages"][-1]["label"] if report["stages"] else "initialization", exception)
    finally:
        try:
            stage("boundary", "restore_exact_common_after_all_diagnostics")
            owner.actor_optimizer.zero_grad(set_to_none=True)
            owner.critic_optimizer.zero_grad(set_to_none=True)
            owner.model.eval()
            if owner.busy:
                raise ValueError("Cannot restore common while an actual model operation is still busy")
            if owner.phase == "collecting":
                owner.finish_evaluation([], folder / "closed-interrupted-native-window")
            if owner.phase != "idle":
                raise ValueError("Qualification did not return to an idle restore boundary")
            owner.restore_checkpoint(common_dir)
            final = _state_fingerprints(owner)
            report["common_after"] = final
            expected = read_json(common_dir / "checkpoint.json")["state_tensor_digest"]
            report["common_restored_exactly"] = final["state_tensor_digest"] == expected
            report["diagnostic_gradients_cleared"] = all(parameter.grad is None
                for parameter in [*owner.actor_parameters.values(), *owner.critic.parameters()])
            if not report["common_restored_exactly"] or not report["diagnostic_gradients_cleared"]:
                raise ValueError("Final common actor/critic/optimizer/recipe/RNG/window state or gradient clearing differs")
        except Exception as exception:
            error("restore_exact_common", exception)
        report["training_ready"] = bool(report["inference_ready"] and report["training_integration_ready"]
            and report["near_16k_capacity_demonstrated"] and report["common_restored_exactly"]
            and report.get("diagnostic_gradients_cleared") and not report["errors"])
        report["elapsed_seconds"] = time.monotonic() - started
        report["native_calls_executed"] = len(report["calls"])
        report["status"] = ("measured_training_ready" if report["training_ready"] else
                            "measured_training_not_ready" if report["inference_ready"] else "inference_not_ready")
        if report["update"] is None and (folder / "aggregate-update.json").exists():
            report["update"] = read_json(folder / "aggregate-update.json")
        _write(folder / "report.json", report)
    return report
