"""One predeclared native C18432 request; never a task solver or retry loop."""
from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import sys
import time

from proworksim.audit import code_identity
from proworksim.online_training import tensor_tree_digest
from proworksim.storage import digest, json_bytes, read_json
from scripts.run_ne_v021 import reference, write
from scripts import software_organization_v045 as original

VERSION = "software-organization-capacity-qualification-v0.46"
SOURCE = Path(__file__).resolve().parents[1]
CONTEXT, PROMPT, OUTPUT = 18432, 16384, 2048
TECHNICAL_SEED = 202610110046
checked = original.checked


def require(value, message):
    if not value:
        raise ValueError(message)


def apply_capacity_binding(owner, *, original_plan, common_restore, output=None):
    """Change only declared capacity after exact restoration of the 16K common."""
    require(owner.phase == "idle" and not owner.busy
            and (owner.actor_steps, owner.critic_steps) == (3, 3), "Require idle complete original 3/3 common")
    before = copy.deepcopy(owner._state_bundle())
    before_sha = tensor_tree_digest(before, owner.torch)
    common = read_json(checked(original_plan["common"]))
    require(before_sha == common_restore["state_sha256"] == common["state_tensor_digest"]
            and common_restore["rng_sha256"] == common["training_rng_sha256"]
            and owner._make_identity() == owner.freeze_identity() == original_plan["expected_actor_identity"]
            == common_restore["actor_identity"], "Original common identity/state/RNG mismatch")
    recipe, profile = copy.deepcopy(owner.recipe), copy.deepcopy(owner.inference_profile)
    require(recipe["max_length"] == profile["max_context_tokens"] == 16384
            and recipe["max_output_tokens"] == OUTPUT
            and owner.inference_profile_sha256 == digest(json_bytes(profile)), "Original 16K capacity/profile changed")
    owner.recipe = {**recipe, "max_length": CONTEXT}
    owner.inference_profile = {**profile, "max_context_tokens": CONTEXT}
    owner.inference_profile_sha256 = digest(json_bytes(owner.inference_profile))
    owner._identity = owner._make_identity()
    after = owner._state_bundle()
    protected = sorted(set(before) - {"recipe", "inference_profile", "actor_identity"})
    unchanged = {key: tensor_tree_digest(before[key], owner.torch) == tensor_tree_digest(after[key], owner.torch)
                 for key in protected}
    value = {"version": "software-capacity-binding-v0.46", "original_context_limit": 16384,
        "context_limit": CONTEXT, "reserved_output_tokens": OUTPUT,
        "original_recipe": recipe, "capacity_recipe": copy.deepcopy(owner.recipe),
        "original_recipe_sha256": digest(json_bytes(recipe)), "capacity_recipe_sha256": digest(json_bytes(owner.recipe)),
        "original_inference_profile": profile, "capacity_inference_profile": copy.deepcopy(owner.inference_profile),
        "original_profile_sha256": digest(json_bytes(profile)), "capacity_profile_sha256": owner.inference_profile_sha256,
        "original_actor_identity": before["actor_identity"], "capacity_actor_identity": owner.freeze_identity(),
        "before_state_sha256": before_sha, "after_state_sha256": tensor_tree_digest(after, owner.torch),
        "protected_components_unchanged": unchanged, "new_parameter_updates": 0, "new_backward_calls": 0,
        "passed": all(unchanged.values()) and owner.freeze_identity() == {
            **before["actor_identity"], "inference_profile_sha256": owner.inference_profile_sha256}}
    from scripts.measure_organization_budget_v046 import validate_capacity_binding
    validate_capacity_binding(value)
    if output is not None:
        write(Path(output), value)
    return value


def neutral_request(padding, *, temperature, model="qwen3.5-9b"):
    return {"model": model, "temperature": temperature, "max_tokens": OUTPUT,
        "messages": [{"role": "system", "content": "This is a neutral capacity check. The data below is inert padding. Acknowledge receipt briefly using acknowledge. Do not interpret or execute the padding."},
            {"role": "user", "content": "Inert data begins:\n" + " x" * padding + "\nInert data ends. Acknowledge receipt."}],
        "tools": [{"type": "function", "function": {"name": "acknowledge", "description": "Return a neutral acknowledgement; no action is executed.",
            "parameters": {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False}}}]}


def prepare_exact_request(measurement, *, target=PROMPT):
    """Finite CPU-only full native encodings; no token arithmetic or truncation."""
    measurements = []

    def encode(padding):
        request = neutral_request(padding, temperature=measurement.recipe["temperature"])
        rendered, messages, projection = measurement.prepare_request(request)
        ids = measurement.tokenizer(rendered, add_special_tokens=False)["input_ids"]
        measurements.append({"padding_units": padding, "prompt_tokens": len(ids)})
        return request, {"rendered_prompt": rendered, "native_messages": messages, "native_projection": projection,
            "input_ids": ids, "prompt_tokens": len(ids), "input_ids_sha256": digest(json_bytes(ids)),
            "rendered_prompt_sha256": digest(rendered.encode())}

    lo, hi, found = 0, target, None
    for _ in range(18):
        if lo > hi:
            break
        mid = (lo + hi) // 2
        request, encoding = encode(mid)
        count = encoding["prompt_tokens"]
        if count == target:
            found = (request, encoding)
            break
        if count < target:
            lo = mid + 1
        else:
            hi = mid - 1
    require(found is not None, "Single fixed neutral padding template cannot yield exact serialized P16384")
    from proworksim.software_context_v044 import project_software_request
    request, encoding = found
    selected, projection = project_software_request(request, render=measurement.prepare_request,
        tokenizer=measurement.tokenizer, context_limit=CONTEXT, member_id="neutral_qualification")
    require(selected == request and projection["selected_prompt_tokens"] == target
            and projection["input_ids_sha256"] == encoding["input_ids_sha256"] and projection["fits"],
            "Neutral exact prompt must survive unchanged through original native projection")
    return {"version": VERSION, "request": request, "encoding": encoding, "projection": projection,
        "selected_equals_original": True, "padding_measurements": measurements,
        "native_measurement_identity": measurement.identity, "target_prompt_tokens": target,
        "context_limit": CONTEXT, "reserved_output_tokens": OUTPUT, "new_model_calls": 0,
        "model_weights_loaded": False, "new_world_actions": 0, "passed": True}


def validate_response(response, prepared, encoding, request, owner):
    """Only capacity/trace integrity qualifies; native tool parse success is not a gate."""
    body = response.get("body", {})
    trace, usage = body.get("token_trace", {}), body.get("usage", {})
    outputs = trace.get("output_ids", [])
    checks = {
        "exact_original_and_selected_request": prepared.get("original_request_sha256") == prepared.get("selected_request_sha256") == digest(json_bytes(request)),
        "exact_serialized_prompt_tokens": prepared.get("prompt_tokens") == encoding.get("prompt_tokens") == PROMPT,
        "exact_native_input_ids": trace.get("input_ids") == encoding.get("input_ids") and prepared.get("input_ids_sha256") == encoding.get("input_ids_sha256"),
        "output_nonempty": bool(outputs) and bool(body.get("raw_generated_text")),
        "output_within_reservation": 0 < len(outputs) <= OUTPUT and body.get("effective_generation", {}).get("max_new_tokens") == OUTPUT,
        "all_generated_tokens_retained": outputs == trace.get("raw_output_ids") and body.get("generation_stop_check", {}).get("all_generated_tokens_retained") is True,
        "usage_consistent": usage == {"prompt_tokens": PROMPT, "completion_tokens": len(outputs), "total_tokens": PROMPT + len(outputs)},
    }
    identity_ok = (body.get("actor_identity") == owner.freeze_identity()
        and body.get("inference_profile_sha256") == owner.inference_profile_sha256
        and body.get("online_window_id") == owner.window_id)
    stop = (body.get("choices") or [{}])[0].get("finish_reason")
    return {"passed": response.get("http_status") == 200 and all(checks.values()) and identity_ok
            and stop in {"stop", "length", "tool_calls"}, "checks": checks, "identity_matches": identity_ok,
        "stop_reason": stop, "protocol_parse_error": body.get("protocol_parse_error"),
        "implicit_truncation": False if checks["exact_native_input_ids"] and checks["all_generated_tokens_retained"] else None,
        "usage_complete": bool(usage) and checks["usage_consistent"], "usage": usage or None}


def prepare_plan(root, original_plan, cpu_controls, native_support, prepared_request, data_root):
    root = Path(root).resolve()
    require(not root.exists(), "Qualification root already exists; no replacement/retry")
    parent, controls, support = map(read_json, (original_plan, cpu_controls, native_support))
    from scripts.software_organization_admission_v046 import source_audit, validate_cpu_controls, validate_native_support
    source = code_identity()
    prior = read_json(Path(data_root) / "runs/software-organization-v045-complete-r1/plan.json")
    audit = source_audit(prior, source_root=SOURCE)
    require(source["code_dirty"] is False, "Freeze clean sources before qualification")
    validate_cpu_controls(controls, audit)
    validate_native_support(support, parent)
    request = read_json(prepared_request)
    require(request["passed"] is True and request["target_prompt_tokens"] == PROMPT
            and request["context_limit"] == CONTEXT and request["reserved_output_tokens"] == OUTPUT,
            "Exact CPU neutral request preparation failed")
    value = {"version": VERSION, "source": source, "source_files": original.source_files(),
        "original_plan": reference(original_plan), "cpu_controls": reference(cpu_controls),
        "native_support": reference(native_support), "prepared_request": reference(prepared_request),
        "native_python": str(Path(data_root).resolve() / "runs/v016-sdk/resident-venv/bin/python"),
        "technical_seed": TECHNICAL_SEED, "context_limit": CONTEXT, "target_prompt_tokens": PROMPT,
        "reserved_output_tokens": OUTPUT, "max_native_calls": 1, "automatic_retries": False,
        "automatic_successors": [], "gpu_preference": list(original.GPU_ORDER), "limits": original.LIMITS}
    value["plan_sha256"] = digest(json_bytes(value))
    root.mkdir(parents=True, exist_ok=False)
    write(root / "qualification-plan.json", value)
    return value


def frozen(root):
    value = read_json(Path(root) / "qualification-plan.json")
    require(value["plan_sha256"] == digest(json_bytes({k: v for k, v in value.items() if k != "plan_sha256"}))
            and value["source"] == code_identity() and value["source_files"] == original.source_files()
            and value["max_native_calls"] == 1 and value["technical_seed"] == TECHNICAL_SEED
            and value["limits"] == original.LIMITS, "Frozen qualification changed")
    for key in ("original_plan", "cpu_controls", "native_support", "prepared_request"):
        checked(value[key])
    return value


def run_worker(root):
    root = Path(root).resolve()
    plan = frozen(root)
    require(os.environ.get("CUDA_VISIBLE_DEVICES") in set(map(str, original.GPU_ORDER)), "Single allowed physical GPU required")
    require(Path(sys.executable).absolute() == Path(plan["native_python"]).absolute()
            and Path(sys.prefix).resolve() == Path(plan["native_python"]).parent.parent.resolve(), "Require the original native SDK interpreter")
    output = root / "actual"
    output.mkdir(parents=True, exist_ok=False)
    report = {"version": VERSION, "status": "loading", "passed": False, "started_at": time.time(),
        "source_before": code_identity(), "source_files": original.source_files(), "plan": reference(root / "qualification-plan.json"),
        "original_plan": plan["original_plan"], "cpu_controls": plan["cpu_controls"], "native_support": plan["native_support"],
        "candidate_context": CONTEXT, "context_limit": CONTEXT, "target_prompt_tokens": PROMPT, "prompt_tokens": PROMPT,
        "reserved_output_tokens": OUTPUT, "max_native_calls": 1, "native_calls_started": 0,
        "actual_model_calls": 0, "new_model_calls": 0, "usage_complete": True,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "world_instances": 0, "tools_executed": 0, "new_world_actions": 0, "new_parameter_updates": 0,
        "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_calls": 0}
    report.update(python_executable=sys.executable, python_prefix=sys.prefix)
    write(output / "report.json", report)
    owner, snapshot = None, None
    try:
        from proworksim.deterministic_work_v024 import DeterministicCandidateActor
        from proworksim.software_learning_v036 import migrate_software_owner, restore_common
        from proworksim.software_context_v044 import SoftwareContextTransport
        from scripts.software_allocation_v037 import available_cards
        parent = read_json(checked(plan["original_plan"]))
        original.task(output, "load-original-common", "loading")
        sample = original.allowed_resources()
        write(output / "preload-resources.json", sample)
        require(int(os.environ["CUDA_VISIBLE_DEVICES"]) in [c["index"] for c in available_cards(parent, sample)], "GPU capacity changed before loading")
        refs = parent["model_references"]
        saved = read_json(checked(refs["owner"]))
        old_plan = read_json(checked(refs["plan"]))
        model_plan = read_json(checked(old_plan["prior_model_plan"]))
        owner = DeterministicCandidateActor.from_candidate(model_plan["model"], manifest=checked(model_plan["manifest"]),
            profile=model_plan["runtime_profile"], recipe=saved["recipe"], output=output / "resident")
        write(output / "software-coordinate-binding.json", migrate_software_owner(owner, expected_steps=None))
        original.task(output, "restore-complete-common", "boundary")
        common = read_json(checked(parent["common"]))
        restored = restore_common(owner, checked(common["common"]).parent)
        write(output / "common-restore.json", restored)
        apply_capacity_binding(owner, original_plan=parent, common_restore=restored, output=output / "capacity-binding.json")
        report.update(capacity_binding=reference(output / "capacity-binding.json"), original_common=parent["common"])

        def forbidden(*args, **kwargs):
            raise RuntimeError("Qualification forbids all learning computation")

        owner.learning_logprobs = forbidden
        owner.update_window = forbidden
        ready = read_json(checked(plan["prepared_request"]))
        request, encoding = ready["request"], ready["encoding"]
        rendered, _, _ = owner.prepare_request(request)
        ids = owner.tokenizer(rendered, add_special_tokens=False)["input_ids"]
        require(rendered == encoding["rendered_prompt"] and ids == encoding["input_ids"] and len(ids) == PROMPT,
                "Resident native serialized input differs from CPU exact preparation")
        snapshot = owner.capture_evaluation_state()
        owner.begin_window("capacity-qualification-v046-single-neutral-request")
        report["seed_binding"] = owner.reseed(TECHNICAL_SEED, label="predeclared-neutral-qualification-no-business-seed")
        transport = SoftwareContextTransport(owner, output / "context")
        association = {"worker_id": "neutral_qualification", "call_id": "capacity-qualification-v046-only-call"}
        transport.bind_turn("neutral_qualification", association)
        prepared = transport.prepare_for_budget(request)
        write(output / "sealed-preparation.json", prepared)
        require(prepared["fits"] is True and prepared["prompt_tokens"] == PROMPT
                and prepared["context_limit"] == CONTEXT and prepared["reserved_output_tokens"] == OUTPUT,
                "Original context projection rejected exact candidate request")
        original.task(output, "single-neutral-native-request", "episode")
        report.update(status="single_native_request_started", native_calls_started=1,
            usage_complete=False, usage=None, actual_model_calls=None, new_model_calls=None)
        write(output / "report.json", report)
        with (output / "native-call.claim").open("x") as stream:
            stream.write("Exactly one attempt. No retry, replacement, world action or successor.\n")
        response = transport.complete(request, timeout_seconds=original.LIMITS["task_seconds"]["episode"])
        write(output / "response.json", response)
        transport.unbind_turn("neutral_qualification", association)
        outcome = validate_response(response, prepared, encoding, request, owner)
        report.update(outcome)
        report.update(actual_model_calls=1 if response.get("http_status") == 200 else None,
            new_model_calls=1 if response.get("http_status") == 200 else None,
            response=reference(output / "response.json"))
        original.task(output, "qualification-final-guard", "boundary")
        report["evaluation"] = owner.finish_evaluation([], output / "evaluation")
        report["evaluation_guard"] = owner.finish_evaluation_guard(snapshot)
        report["calls"] = [reference(path) for path in sorted((output / "resident/calls").glob("*.json"))]
        report["checks"]["numerical_path_unchanged"] = response.get("body", {}).get("inference_profile") == owner.inference_profile
        report["checks"]["zero_parameter_updates"] = report["evaluation_guard"]["learning_unchanged"] is True and (owner.actor_steps, owner.critic_steps) == (3, 3)
        report["passed"] = report["passed"] and all(report["evaluation_guard"][key] is True for key in ("learning_unchanged", "rng_restored_exactly"))
        report["passed"] = report["passed"] and all(report["checks"].values()) and len(report["calls"]) == 1
    except BaseException as error:
        report.update(passed=False, error={"type": type(error).__name__, "message": str(error)})
    finally:
        if owner is not None:
            report.update(new_actor_steps=max(0, owner.actor_steps - 3), new_critic_steps=max(0, owner.critic_steps - 3))
        usage = report.get("usage") or {}
        report.update(actual_prompt_tokens=usage.get("prompt_tokens"), actual_output_tokens=usage.get("completion_tokens"),
            actual_total_tokens=usage.get("total_tokens"), ended_at=time.time(), source_after=code_identity())
        report["passed"] = (report["passed"] and report["source_before"] == report["source_after"]
            and report["new_actor_steps"] == report["new_critic_steps"] == 0)
        report["status"] = "passed" if report["passed"] else "failed_no_successor"
        write(output / "report.json", report)
    return report


def supervise(root):
    """One possible worker spawn, original resource guards, no automatic retry."""
    import json
    import os
    from pathlib import Path
    import shutil
    import subprocess
    import sys
    import time

    from proworksim.resource_monitor_v025 import (
        TelemetryGuard,
        target_resources,
        worker_identity,
    )
    from scripts import software_organization_capacity_qualification_v046 as qualification
    from scripts import software_organization_v045 as original
    from scripts.run_bounded_v022 import artifact_bytes, rss
    from scripts.run_ne_v021 import lock, read, reference, write
    from scripts.software_allocation_v037 import available_cards, live_free_stop_reason

    root = Path(root).resolve()
    plan = qualification.frozen(root)
    parent_path = original.checked(plan["original_plan"])
    parent = qualification.read_json(parent_path)
    native_python = Path(plan["native_python"]).absolute()
    expected_native = Path(parent["data_root"]) / "runs/v016-sdk/resident-venv/bin/python"
    if native_python != expected_native.absolute() or not native_python.is_file():
        raise ValueError("Worker must use the frozen original native SDK interpreter path")
    if tuple(original.GPU_ORDER) != (3, 4, 5, 7):
        raise ValueError("Qualification can only inspect or allocate physical GPUs3/4/5/7")
    if plan["max_native_calls"] != 1 or plan["automatic_retries"] is not False:
        raise ValueError("Only one qualification attempt, without retries, is authorized")
    limits = original.LIMITS
    name = "native-qualification"
    state = {"worker": name, "status": "not_started", "attempted": False}
    summary = {
        "version": qualification.VERSION,
        "status": "waiting",
        "passed": False,
        "started_at": time.time(),
        "observer_pid": os.getpid(),
        "supervisor_python_executable": sys.executable,
        "supervisor_python_prefix": sys.prefix,
        "worker_native_python": str(native_python),
        "source": plan["source"],
        "plan": reference(root / "qualification-plan.json"),
        "states": {name: state},
        "max_parallel_model_instances": 1,
        "max_worker_spawns": 1,
        "worker_spawn_attempts": 0,
        "max_native_calls": 1,
        "automatic_retries": False,
        "automatic_successors": [],
        "gpu_preference": list(original.GPU_ORDER),
        "resource_limits": limits,
        "queue_deadline_at": None,
        "wall_deadline_at": None,
    }
    process = log = guard = None
    stable = {}
    artifact_roots = original.support.dense._artifact_roots(
        [*parent["prior_artifact_roots"], parent_path.parent, root,
         Path(parent["data_root"]) / "runs/v046-controls"]
    )
    summary["artifact_roots"] = artifact_roots

    def publish():
        now = time.time()
        summary.update(
            observed_at=now,
            active_worker_pid=process.pid if process is not None else None,
            closed_worker_gpu_seconds=state.get("elapsed_gpu_seconds", 0),
            running_worker_gpu_seconds=(now - state["started_at"]) if process is not None else 0,
        )
        write(root / "supervisor.json", summary)

    def close(reason):
        nonlocal process, log
        if process is None:
            return
        if process.poll() is None:
            original.support.continuation._stop_worker(process, state)
        process.wait(timeout=15)
        result_path = root / "actual/report.json"
        result = read(result_path) or {}
        passed = (
            process.returncode == 0
            and reason is None
            and result.get("status") == "passed"
            and result.get("passed") is True
            and result.get("source_before") == result.get("source_after") == plan["source"]
            and all(result.get(key) == 0 for key in
                    ("new_actor_steps", "new_critic_steps", "new_backward_calls"))
        )
        ended = time.time()
        state.update(
            status="complete" if passed else "stopped",
            stop_reason=reason or (None if passed else result.get("status", "worker_incomplete")),
            exit_code=process.returncode,
            ended_at=ended,
            elapsed_gpu_seconds=ended - state["started_at"],
            worker_report=reference(result_path) if result_path.is_file() else None,
            actual_native_calls_started=result.get("native_calls_started"),
            actual_model_calls=result.get("actual_model_calls"),
            usage_complete=result.get("usage_complete"),
            usage=result.get("usage"),
        )
        summary.update(status="complete" if passed else "failed_no_successor", passed=passed)
        process = None
        if log is not None:
            log.close()
            log = None
        publish()

    with lock(root):
        if (root / "supervisor.json").exists() or (root / "worker-spawn.claim").exists() or (root / "actual").exists():
            raise FileExistsError("A qualification supervisor/worker attempt may never be reopened")
        publish()
        try:
            while state["status"] not in {"complete", "stopped"}:
                if process is not None and process.poll() is not None:
                    close(None if process.returncode == 0 else "worker_exit_error")
                    break
                size = sum(artifact_bytes(Path(path)) for path in artifact_roots)
                free = shutil.disk_usage(root).free
                if size > limits["artifact_bytes"] or free < limits["minimum_volume_free_bytes"]:
                    if process is not None:
                        close("trajectory_storage_reserve")
                    else:
                        state.update(status="stopped", stop_reason="trajectory_storage_reserve", elapsed_gpu_seconds=0)
                        summary.update(status="failed_no_successor", passed=False)
                    break
                if process is None and not state["attempted"]:
                    sample = original.allowed_resources()
                    with (root / "waiting-resources.jsonl").open("a") as stream:
                        stream.write(json.dumps(sample) + "\n")
                    cards = [card for card in available_cards(parent, sample)
                             if card["index"] in original.GPU_ORDER]
                    now = time.time()
                    stable = {card["index"]: stable.get(card["index"], now) for card in cards}
                    ready = [card for card in cards
                             if now - stable[card["index"]] >= limits["gpu_capacity_stability_seconds"]]
                    if ready:
                        # Recheck the frozen source/receipts after the original stable wait.
                        if qualification.frozen(root) != plan:
                            raise ValueError("Qualification plan changed while waiting for capacity")
                        card = ready[0]
                        temporary = root / "tmp"
                        temporary.mkdir(exist_ok=False)
                        argv = [str(native_python), "-m",
                                "scripts.software_organization_capacity_qualification_v046",
                                "worker", "--run-root", str(root)]
                        env = original.worker_env(parent, card["index"])
                        env.update(TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary))
                        log = (root / "worker.log").open("x")
                        # Claim before Popen: even a launch error consumes this sole spawn.
                        with (root / "worker-spawn.claim").open("x") as stream:
                            stream.write("One qualification worker spawn; no automatic retry or successor.\n")
                        summary["worker_spawn_attempts"] = 1
                        state.update(status="launching", attempted=True, gpu=card["index"],
                                     gpu_uuid=card["uuid"], started_at=time.time(), command=argv)
                        publish()
                        process = subprocess.Popen(argv, cwd=qualification.SOURCE, env=env,
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)
                        identity = worker_identity(process.pid)
                        state.update(status="running", pid=process.pid, process_identity=identity)
                        guard = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"],
                                               worker_pid=process.pid)
                        publish()
                if process is not None:
                    sample = target_resources(state["gpu"], worker_pid=process.pid)
                    if process.poll() is not None:
                        close(None if process.returncode == 0 else "worker_exit_error")
                        break
                    observed = guard.observe(sample, time.time(), process.pid, state["gpu"],
                                             own_memory_limit_mib=limits["own_gpu_memory_mib"])
                    current = read(root / "actual/task.json") or {
                        "kind": "loading", "started_at": state["started_at"]}
                    own_rss = rss(process.pid)
                    reason = observed.get("stop_reason") or live_free_stop_reason(sample, state["gpu"])
                    cap = limits["task_seconds"].get(current.get("kind"))
                    if cap is None:
                        reason = reason or "unknown_task_kind"
                    elif time.time() - current["started_at"] >= cap:
                        reason = reason or "single_task_budget"
                    elif own_rss > limits["host_rss_per_worker_bytes"]:
                        reason = reason or "host_memory_budget"
                    with (root / "resources.jsonl").open("a") as stream:
                        stream.write(json.dumps({"sample": sample, "guard": observed, "task": current,
                            "rss_bytes": own_rss, "artifact_bytes": size, "volume_free_bytes": free}) + "\n")
                    if reason:
                        close(reason)
                        break
                summary["status"] = "running" if process is not None else "waiting"
                publish()
                time.sleep(limits["poll_seconds"])
        except BaseException as error:
            summary.update(status="failed_no_successor", passed=False,
                           error={"type": type(error).__name__, "message": str(error)})
            if process is not None:
                try:
                    close("supervisor_interrupted")
                except BaseException as cleanup_error:
                    summary.update(status="cleanup_unresolved_no_retry",
                        cleanup_error={"type": type(cleanup_error).__name__, "message": str(cleanup_error)})
            else:
                state.update(status="stopped", stop_reason="supervisor_interrupted",
                             elapsed_gpu_seconds=0)
            raise
        finally:
            if log is not None:
                log.close()
            summary["ended_at"] = time.time()
            publish()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare-request", "prepare", "supervise", "worker"))
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--original-plan", type=Path)
    parser.add_argument("--cpu-controls", type=Path)
    parser.add_argument("--native-support", type=Path)
    parser.add_argument("--prepared-request", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "prepare-request":
        from scripts.software_context_replay_v044 import load_cpu_measurement
        require(not args.output.exists(), "Exact request preparation already exists")
        value = prepare_exact_request(load_cpu_measurement(args.original_plan))
        value["original_plan"] = reference(args.original_plan)
        write(args.output, value)
    elif args.command == "prepare":
        value = prepare_plan(args.run_root, args.original_plan, args.cpu_controls, args.native_support, args.prepared_request, args.data_root)
    elif args.command == "worker":
        value = run_worker(args.run_root)
    else:
        value = supervise(args.run_root)
    print({"version": VERSION, "status": value.get("status"), "passed": value.get("passed")})


if __name__ == "__main__":
    main()
