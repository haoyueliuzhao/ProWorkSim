"""Read-only CAL-2 S1 bindings for the frozen v050 feedback/refusal proofs.

The original algebra, exact pre-dispatch refusal and feedback/page proofs are
rebound in a private namespace; no old globals, records or parser are changed.
New predicates bind one member, no initial test, the read-only actor and two
explicit terminal endpoints. They do not choose continuation by success.
"""
from __future__ import annotations

import ast
import copy
import inspect
from pathlib import Path
from types import FunctionType

from . import software_organization_measurement_v050 as original
from .software_calibration_collector_v051 import VERSION as RUNTIME_VERSION, SCHEDULER
from .software_calibration_world_v051 import INTERFACE_REVISION, validate_case
from .storage import atomic_write, digest, json_bytes

VERSION = "repository-calibration-measurement-v0.51"
MEMBERS = ["member_001"]
BINDING_VERSION = "v051-readonly-S1-actor-capacity-binding"
require = original.require
load = original.load


def validate_episode_capacity(binding, *, result, budget):
    require(isinstance(binding, dict) and binding.get("version") == BINDING_VERSION,
            "missing_v051_readonly_actor_binding", missing=binding is None)
    require(result.get("version") == RUNTIME_VERSION and result.get("condition") == "S1"
        and result.get("calibration_condition") in {"P", "U"}
        and result.get("team_token_budget") == 500000
        and budget.get("members") == MEMBERS
        and budget.get("limits") == {"max_decisions": 128, "max_attempts": 128, "max_total_tokens": 500000}
        and budget.get("team_id") == binding.get("window_id") == result.get("online_window_id")
        and binding.get("actor_identity") == result.get("actor_identity"), "v051_actor_or_budget_mismatch")
    expected = {key: binding[key] for key in ("actor_identity", "window_id", "recipe_sha256")}
    require(budget.get("binding") == expected or budget.get("binding") is None and budget.get("attempts") == 0,
            "v051_ledger_actor_window_or_recipe_mismatch")
    return copy.deepcopy(binding)


def episode_binding(folder, *, result, budget, provider):
    manifest = load(Path(folder) / "episode/manifest.json")
    require(isinstance(manifest, dict), "missing_episode_manifest", missing=True)
    scope = manifest.get("scenario", {}).get("variation", {}).get("organization_runtime", {})
    require(manifest.get("status") == "closed" and scope.get("version") == RUNTIME_VERSION
        and all(scope.get(key) == result.get(key) for key in ("slot_id", "actor_identity", "online_window_id",
            "learning_binding", "episode_start_steps", "calibration_condition")), "v051_manifest_slot_or_actor_mismatch")
    case = scope.get("case")
    validate_case(case, provider=provider)
    require(manifest["scenario"]["variation"].get("software_case") == case,
            "duplicated_v051_source_case_differs")
    require(scope.get("purpose") == result.get("purpose") == case["purpose"] == "single_agent_calibration"
        and scope.get("training_eligible") is result.get("training_eligible") is case["training_eligible"] is False
        and scope.get("scheduling_protocol") == SCHEDULER
        and result.get("condition") == case["condition"] == "S1"
        and case["active_roles"] == budget.get("members") == MEMBERS,
        "v051_S1_source_or_member_identity_mismatch")
    window = result["online_window_id"]
    require(window == "calibration-v051:" + result["slot_id"], "wrong_v051_logical_window")
    recipe, contract = scope.get("recipe"), scope.get("native_contract")
    require(isinstance(recipe, dict) and recipe.get("max_length") == 18432
        and recipe.get("max_output_tokens") == 2048 and recipe.get("temperature") == .7
        and scope.get("recipe_sha256") == digest(json_bytes(recipe)), "wrong_v051_recipe_binding")
    expected_contract = {"context_limit": 18432, "max_output_tokens": 2048, "enable_thinking": False,
        "preserve_thinking": False, "temperature": .7, "top_p": 1.0, "top_k": 0, "max_generation_seconds": 600}
    require(isinstance(contract, dict) and all(contract.get(k) == v for k, v in expected_contract.items())
            and scope.get("native_contract_sha256") == digest(json_bytes(contract)), "wrong_v051_native_decoder")
    policies = manifest.get("policies", {})
    require(set(policies) == set(MEMBERS), "missing_or_extra_v051_S1_policy")
    config = policies[MEMBERS[0]].get("config", {})
    require(config.get("weight_identity") == result["actor_identity"]
        and config.get("max_context_tokens") == 18432 and config.get("max_output_tokens") == 2048
        and config.get("timeout_seconds") == 600, "v051_member_policy_differs_from_actor_or_limits")
    steps = scope["episode_start_steps"]
    expected_steps = (0, 0) if result["calibration_condition"] == "P" else (4, 4)
    require((steps.get("actor_steps"), steps.get("critic_steps")) == expected_steps,
            "v051_wrong_historical_actor_state")
    checkpoint = result["actor_identity"].get("checkpoint")
    require((checkpoint is None) == (result["calibration_condition"] == "P"), "v051_raw_adapter_condition_mismatch")
    bound = {"version": BINDING_VERSION, "slot_id": result["slot_id"],
        "actor_identity": copy.deepcopy(result["actor_identity"]), "window_id": window,
        "recipe_sha256": scope["recipe_sha256"], "context_limit": 18432, "reserved_output_tokens": 2048,
        "episode_manifest": original.reference(Path(folder) / "episode/manifest.json"),
        "source_purpose": case["purpose"], "training_eligible": False,
        "episode_start_steps": copy.deepcopy(steps), "native_contract_sha256": scope["native_contract_sha256"],
        "inherited_projection_library_provenance": original.reference_protocol.presentation_identity(),
        "actual_world_runtime_version": RUNTIME_VERSION, "new_capacity_qualification_performed": False}
    validate_episode_capacity(bound, result=result, budget=budget)
    return bound


def _adapt_function(function, namespace, kind):
    source = inspect.getsource(function)
    tree = ast.parse(source)
    replacements = 0
    for node in ast.walk(tree):
        if (kind == "single_lifecycle" and isinstance(node, ast.Compare) and isinstance(node.left, ast.Call)
                and isinstance(node.left.func, ast.Attribute) and isinstance(node.left.func.value, ast.Name)
                and node.left.func.value.id == "lifecycle" and node.left.func.attr == "get"
                and len(node.left.args) == 1 and isinstance(node.left.args[0], ast.Constant)
                and node.left.args[0].value in {"cumulative_births", "live_at_end"}
                and len(node.comparators) == 1 and isinstance(node.comparators[0], ast.Constant)
                and node.comparators[0].value == 2):
            node.comparators[0].value = 1
            replacements += 1
        if (kind == "no_initial_test" and isinstance(node, ast.If)
                and ast.dump(node.test, include_attributes=False) == ast.dump(
                    ast.parse("not initial or not assignments", mode="eval").body, include_attributes=False)):
            node.test = ast.parse("initial != {} or assignments != {'member_001': []}", mode="eval").body
            replacements += 1
        if (kind == "no_initial_test" and isinstance(node, ast.ImportFrom)
                and node.module == "scripts.software_context_replay_v044"
                and [value.name for value in node.names] == ["reconstruct_feedback_timeline"]):
            node.module = "proworksim.software_calibration_measurement_v051"
            replacements += 1
    expected = 2
    if replacements != expected:
        raise ValueError("Original measurement predicate changed; refuse broad adaptation")
    ast.fix_missing_locations(tree)
    exec(compile(tree, "<v051-private-bound-original-measurement>", "exec"), namespace)
    return {"function": function.__name__, "source_sha256": digest(source.encode()),
            "replacements": replacements, "kind": kind,
            "adapted_AST_sha256": digest(ast.dump(tree, include_attributes=False).encode())}


def reconstruct_feedback_timeline(history):
    """Preserve explicit CPU fixtures; live archives keep the original default."""
    from scripts import software_context_replay_v044 as replay
    from .software_feedback_v044 import OrdinaryFeedbackLedger

    requests = history.get("requests", [])
    fixtures = [row.get("response", {}).get("body", {}).get("token_trace", {}).get("fixture_only") is True
                for row in requests]
    if not fixtures or not any(fixtures):
        return replay.reconstruct_feedback_timeline(history)
    require(all(fixtures), "mixed_fixture_and_actual_generations")
    tree = ast.parse(inspect.getsource(replay.reconstruct_feedback_timeline))
    changed = 0
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "OrdinaryFeedbackLedger" and not node.args and not node.keywords):
            node.keywords = [ast.keyword(arg="evidence_kind", value=ast.Constant(value="cpu_programmed_fixture"))]
            changed += 1
    require(changed == 1, "original_reconstruction_constructor_changed")
    ast.fix_missing_locations(tree)
    namespace = dict(replay.__dict__)
    namespace["OrdinaryFeedbackLedger"] = OrdinaryFeedbackLedger
    exec(compile(tree, "<v051-CPU-fixture-evidence-kind-only>", "exec"), namespace)
    return namespace["reconstruct_feedback_timeline"](history)


def _namespace(provider):
    namespace = dict(original.__dict__)
    namespace.update(VERSION=VERSION, PAGE_INTERFACE=INTERFACE_REVISION, RUNTIME_VERSION=RUNTIME_VERSION,
                     SCHEDULER=SCHEDULER, MEMBERS=MEMBERS, validate_episode_capacity=validate_episode_capacity)
    for name, value in original.__dict__.items():
        if isinstance(value, FunctionType) and value.__module__ == original.__name__:
            bound = FunctionType(value.__code__, namespace, value.__name__, value.__defaults__, value.__closure__)
            bound.__kwdefaults__ = value.__kwdefaults__
            namespace[name] = bound
    namespace["validate_episode_capacity"] = validate_episode_capacity
    namespace["episode_binding"] = lambda folder, *, result, budget: episode_binding(
        folder, result=result, budget=budget, provider=provider)
    changes = [_adapt_function(original.assess_records, namespace, "single_lifecycle"),
               _adapt_function(original._measure_feedback, namespace, "no_initial_test")]
    return namespace, {"version": VERSION, "source_module_sha256": digest(Path(original.__file__).read_bytes()),
        "rebound_constants": {"interface": INTERFACE_REVISION, "runtime": RUNTIME_VERSION,
                              "members": MEMBERS, "scheduling_protocol": SCHEDULER},
        "new_source_and_capacity_binding": BINDING_VERSION, "AST_changes": changes,
        "unchanged_refusal_algorithms": ["bind_context", "bind_shared_budget", "bind_member_fixed_budget"],
        "old_globals_or_records_modified": False}


def evidence_mode(row, *, allow_cpu_fixture=False):
    """Formal admission accepts only the bound read-only native actor path."""
    require(type(allow_cpu_fixture) is bool, "invalid_fixture_mode")
    folder = Path(row["episode_manifest"]).resolve().parent.parent
    responses = [load(path).get("body", {}) for path in sorted((folder / "raw-transport").glob("request-*/response.json"))]
    ledgers = [load(path) for path in sorted((folder / "raw-transport").glob("request-*/feedback-lifecycle-before.json"))]
    identity = row.get("actor_identity", {})
    if allow_cpu_fixture:
        require(bool(responses) and all(body.get("token_trace", {}).get("fixture_only") is True for body in responses)
                and all(ledger.get("evidence_kind") == "cpu_programmed_fixture" for ledger in ledgers)
                and row.get("slot_id", "").startswith("CPU-")
                and identity.get("policy_version") == "synthetic-no-tensor-cpu-owner"
                and identity.get("adapter_sha256") == "no-weights", "fixture_mode_requires_explicit_CPU_provenance")
        return {"mode": "cpu_control_only", "formal_model_admission_eligible": False, "actual_model_generations": 0}
    require(all(body.get("token_trace", {}).get("fixture_only") is not True for body in responses)
            and all(ledger.get("evidence_kind") == "actual_generation_settled" for ledger in ledgers)
            and identity.get("policy_version", "").startswith("calibration:")
            and bool(identity.get("base_manifest")) and bool(identity.get("base_revision")), "formal_measurement_rejects_CPU_fixture_or_unbound_actor")
    calls_path = Path(row.get("native_provider_calls_path") or "__missing_native_provider__")
    owner = load(calls_path.parent / "owner.json", {})
    profile = owner.get("inference_profile", {})
    require(calls_path.is_dir() and owner.get("version") == "software-calibration-runtime-v0.51"
            and owner.get("actor_identity") == identity
            and profile.get("version") == owner["version"] and profile.get("path") == "project"
            and profile.get("optimizer_constructed") is profile.get("critic_constructed") is profile.get("learning_enabled") is False
            and digest(json_bytes(profile)) == identity.get("inference_profile_sha256"), "formal_native_provider_owner_not_bound")
    for body in responses:
        trace, service = body.get("token_trace", {}), body.get("service_record", {})
        require(body.get("actor_identity") == identity and body.get("online_window_id") == row["online_window_id"]
                and body.get("inference_profile") == profile
                and trace.get("source") == "actual generation IDs"
                and trace.get("raw_output_ids") == trace.get("output_ids")
                and service.get("transport_kind") == "resident_direct"
                and service.get("batch_size") == 1, "formal_response_not_actual_native_actor_generation")
    return {"mode": "formal_native_generation", "formal_model_admission_eligible": True,
            "actual_model_generations": len(responses), "owner_source": original.reference(calls_path.parent / "owner.json")}


def measure_slot(row, destination=None, *, provider, allow_cpu_fixture=False):
    try:
        mode = evidence_mode(row, allow_cpu_fixture=allow_cpu_fixture)
    except (KeyError, TypeError, ValueError, OSError) as error:
        report = {"version": VERSION, "slot_id": row.get("slot_id"), "decision": "global_pause",
            "read_only": True, "new_model_calls": 0, "new_tokenizer_calls": 0,
            "new_test_or_acceptance_executions": 0, "new_world_actions": 0,
            "stop_assessment": {"decision": "global_pause", "global_violations": [str(error)], "unresolved": []}}
        if destination is not None:
            path = Path(destination)
            if path.exists():
                raise FileExistsError("A v051 read-only measurement receipt cannot be overwritten")
            atomic_write(path, json_bytes(report))
        return report
    namespace, adaptation = _namespace(provider)
    report = namespace["measure_slot"](row)
    report["evidence_mode"] = mode
    report["adaptation"] = adaptation
    report["scope"] = "New CAL-2 S1 archive only; original refusal/projection proofs with explicit new identity binding"
    stop = report.get("stop_assessment", {})
    pending = stop.setdefault("unresolved", [])
    try:
        folder = Path(row["episode_manifest"]).resolve().parent.parent
        terminal = load(folder / "terminal-code/terminal-code-assessment.json")
        lock = load(folder / "terminal-code/terminal-candidate-lock.json")
        require(terminal == row.get("terminal_code") and isinstance(terminal, dict), "terminal_code_receipt_missing_or_different", missing=True)
        require({key: terminal[key] for key in lock} == lock, "terminal_code_lock_mismatch")
        require(type(terminal.get("R_code")) is int and terminal["R_code"] in (0, 1)
                and terminal.get("executed") is True, "terminal_code_technical_unknown", missing=True)
        require(row.get("R_code") == terminal["R_code"]
                and row.get("Q_task_terminal") == terminal.get("Q_task"), "terminal_code_metric_mismatch")
        raw_fixed = load(folder / "raw-independent-assessment.json")
        same = bool(raw_fixed.get("submitted") and raw_fixed.get("files_sha256") == terminal["files_sha256"])
        terminal_executed = terminal.get("assessment", {}).get("independent_acceptance", {}).get("execution", {}).get("command_executed") is True
        fixed_executed = raw_fixed.get("independent_acceptance", {}).get("execution", {}).get("command_executed") is True
        require(terminal.get("reused_same_fixed_tree_assessment") is same
                and terminal.get("new_evaluation_attempts") == (0 if same else 1)
                and terminal.get("new_test_executions") == int(not same and terminal_executed), "duplicate_or_missing_terminal_same_tree_assessment")
        require(row.get("host_final_test_executions") == int(fixed_executed)
                + terminal["new_test_executions"]
                and row.get("host_final_evaluation_attempts") == int(raw_fixed.get("submitted") is True)
                + terminal["new_evaluation_attempts"], "host_final_test_count_mismatch")
        require(row.get("fixed_and_terminal_metrics_are_distinct") is True, "fixed_and_native_code_endpoints_merged")
        report["terminal_code_binding"] = {"status": "verified", "R_used_for_selection": False,
            "same_fixed_tree_reused": same, "source_reference": terminal["source_reference"],
            "files_sha256": terminal["files_sha256"], "host_final_test_executions": row["host_final_test_executions"]}
    except (KeyError, TypeError, ValueError, OSError) as error:
        missing = isinstance(error, original.EvidenceProblem) and error.missing
        if isinstance(error, original.EvidenceProblem) and not missing:
            stop.setdefault("global_violations", []).append(str(error))
        else:
            pending.append({"terminal_code_binding_unresolved": str(error)})
        report["terminal_code_binding"] = {"status": "unresolved", "error": str(error)}
    stop["decision"] = "global_pause" if stop.get("global_violations") else "measurement_pending" if pending else "continue"
    report["decision"] = stop["decision"]
    if destination is not None:
        path = Path(destination)
        if path.exists():
            raise FileExistsError("A v051 read-only measurement receipt cannot be overwritten")
        atomic_write(path, json_bytes(report))
    return report


def bind_member_fixed_budget(call_id, *, provider, **kwargs):
    """The original strict v050/r2 provenance proof, with new S1 identity only."""
    namespace, _ = _namespace(provider)
    return namespace["bind_member_fixed_budget"](call_id, **kwargs)
