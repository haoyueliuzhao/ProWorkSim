"""v049 original-input bridge and composition adapter for the original H=1 learner.

The updater executes SharedActor.update_window's original code object in private
globals. Only the composition validator and optional, read-only gradient observer
are bound here; old modules, loss arithmetic, accumulation and optimizer code are
unchanged. No gradient cache or reconstructed expanded input enters learning.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from functools import partial
import math
import marshal
from pathlib import Path
import time
import re
from types import FunctionType

from .critic_features import past_features
from .member_views import member_view
from .online_signals import GroupGradientCapture
from .online_training import SharedActor, prepare_window, reference, tensor_tree_digest
from .software_context_v048 import CANDIDATE_SHA256, VERSION as CONTEXT_VERSION, project_software_request
from .software_learning_v029 import CRITIC_MEMBERS as ORIGINAL_MEMBERS, _projection_index
from .software_learning_v036 import material_summary
from .storage import atomic_write, digest, json_bytes, read_json
from .team_rollout import optimizer_scope_allows_update

VERSION = "software-learning-bridge-v0.49"
COMPOSITION_VERSION = "software-composition-weights-v0.49"
MEMBERS = ("member_001", "member_002")
CRITIC_MEMBERS = (*MEMBERS, "software_inactive")
COORDINATE_BINDING = dict(zip(ORIGINAL_MEMBERS, CRITIC_MEMBERS))
NUMERICAL_STATE_FIELDS = ("actor", "critic", "actor_optimizer", "critic_optimizer", "rng_cpu", "rng_cuda",
    "policy_revision", "actor_steps", "critic_steps", "critic_has_nonzero_reward_history")


def migrate_o1_owner(owner, output=None):
    """Rename the two existing critic coordinates without any numerical change."""
    if (owner.phase != "idle" or owner.busy or owner.sampling_only
            or tuple(owner.recipe["members"]) != ORIGINAL_MEMBERS
            or tuple(owner.critic[0].weight.shape) != (32, 30)):
        raise ValueError("O1 binding requires the idle original software learner coordinates")
    before = owner._state_bundle()
    owner.recipe = {**copy.deepcopy(owner.recipe), "members": list(CRITIC_MEMBERS)}
    after = owner._state_bundle()
    checks = {key: tensor_tree_digest(value, owner.torch) == tensor_tree_digest(after[key], owner.torch)
              for key, value in before.items() if key != "recipe"}
    if not all(checks.values()) or {**before["recipe"], "members": list(CRITIC_MEMBERS)} != after["recipe"]:
        raise ValueError("O1 coordinate binding changed protected numerical/common state")
    proof = {"version": VERSION, "coordinate_binding": copy.deepcopy(COORDINATE_BINDING),
        "original_recipe": before["recipe"], "o1_recipe": after["recipe"],
        "before_state_sha256": tensor_tree_digest(before, owner.torch),
        "after_state_sha256": tensor_tree_digest(after, owner.torch),
        "protected_state_unchanged": checks, "new_parameter_updates": 0, "new_backward_calls": 0,
        "scope": "Explicit ordered member-coordinate metadata binding; original 30 critic features, weights, both Adam states and RNG unchanged."}
    owner.o1_learning_binding = copy.deepcopy(proof)
    if output is not None:
        atomic_write(Path(output), json_bytes(proof))
    return proof


def software_feature_function(events, before_sequence, member_id, member_ids=CRITIC_MEMBERS):
    if tuple(member_ids) != CRITIC_MEMBERS or member_id not in MEMBERS:
        raise ValueError("Use the explicitly frozen O1 critic coordinates")
    if any(event.get("worker_id") == CRITIC_MEMBERS[-1] for event in events):
        raise ValueError("Inactive critic coordinate cannot acquire synthetic actions")
    values, proof = past_features(events, before_sequence, member_id, CRITIC_MEMBERS)
    proof.update(software_binding_version=VERSION, coordinate_binding=copy.deepcopy(COORDINATE_BINDING),
                 numerical_transfer_only=True, inactive_coordinate=CRITIC_MEMBERS[-1])
    return values, proof


def save_s0_checkpoint(owner, directory):
    """Save the pre-generation complete S0, then expose its exact declaration binding."""
    if owner.phase != "idle" or owner.busy or tuple(owner.recipe["members"]) != CRITIC_MEMBERS:
        raise ValueError("S0 must be saved at an idle, explicitly migrated O1 boundary")
    directory = Path(directory)
    record = owner.save_checkpoint(directory)
    state = owner._state_bundle()
    if tensor_tree_digest(state, owner.torch) != record["state_tensor_digest"]:
        raise ValueError("S0 changed across its original full checkpoint serialization")
    return {"checkpoint_ref": reference(directory / "checkpoint.json"),
        "state_tensor_digest": record["state_tensor_digest"],
        "learning_protected_digest": tensor_tree_digest({key: state[key] for key in NUMERICAL_STATE_FIELDS}, owner.torch),
        "actor_identity": owner.freeze_identity(), "recipe_sha256": digest(json_bytes(owner.recipe)),
        "member_coordinate_mapping": copy.deepcopy(COORDINATE_BINDING)}


def validate_selected_trace(owner, *, original, actual, folder, member_id, call_id):
    """Replay the exact frozen Γ1 with its archived runner-owned feedback state."""
    folder = Path(folder)
    names = ("original-request.json", "selected-request.json", "projection.json", "response.json",
             "feedback-lifecycle-before.json", "runner-turn.json")
    saved_original, selected, projection, saved, ledger, turn = [read_json(folder / name) for name in names]
    if (saved.get("http_status") != 200 or saved_original != original or saved.get("body") != actual
            or projection.get("version") != CONTEXT_VERSION or projection.get("fits") is not True
            or turn.get("member_id") != member_id or turn.get("association", {}).get("worker_id") != member_id
            or turn.get("association", {}).get("call_id") != call_id):
        raise ValueError("Saved original/native response or Γ1 runner/member/call binding differs")
    replayed, replay_audit = project_software_request(original, render=owner.prepare_request,
        tokenizer=owner.tokenizer, context_limit=owner.recipe["max_length"], ledger=ledger, member_id=member_id)
    if replayed != selected or replay_audit != projection:
        raise ValueError("Actual native input is not the exact frozen Γ1 projection")
    rendered, _, _ = owner.prepare_request(selected)
    ids = owner.tokenizer(rendered, add_special_tokens=False)["input_ids"]
    trace = actual["token_trace"]
    if (ids != trace["input_ids"] or digest(rendered.encode()) != projection["rendered_prompt_sha256"]
            or digest(json_bytes(ids)) != projection["input_ids_sha256"]
            or len(ids) != projection["selected_prompt_tokens"]):
        raise ValueError("Training trace differs from the actual Γ1 native input IDs")
    budget_path = folder / "budget-preparation.json"
    if budget_path.exists():
        budget = read_json(budget_path)
        seal = {key: value for key, value in budget.items() if key != "preparation_sha256"}
        if (budget.get("preparation_sha256") != digest(json_bytes(seal))
                or budget.get("recipe_sha256") != digest(json_bytes(owner.recipe))
                or budget.get("actor_identity") != owner.freeze_identity()
                or budget.get("window_id") != actual.get("online_window_id")
                or budget.get("input_ids_sha256") != projection["input_ids_sha256"]
                or budget.get("selected_request_sha256") != digest(json_bytes(selected))):
            raise ValueError("Actual selected-input budget seal differs from the learner binding")
        names = (*names, "budget-preparation.json")
    return {"sampler_response_id": actual["id"], "source_files": [reference(folder / name) for name in names],
        "training_token_trace_sha256": digest(json_bytes(trace)), "input_tokens": len(ids),
        "output_tokens": len(trace["output_ids"]), "training_targets_reconstructed": False,
        "same_input_reference_count": len(projection["same_input_references"]["generated_references"])}


def _declared_slots(entries, declaration):
    slots = declaration["slots"]
    if ([row["slot_id"] for row in entries] != [row["slot_id"] for row in slots]
            or any(row["active_members"] != list(MEMBERS) for row in slots)
            or any(row["active_members"] != list(MEMBERS) for row in entries)):
        raise ValueError("Keep every declared original slot and both stable O1 member coordinates")
    return slots


def validate_training_entries(owner, entries, declaration, *, request_evidence_root, require_open_window=True):
    _declared_slots(entries, declaration)
    if (tuple(owner.recipe["members"]) != CRITIC_MEMBERS
            or owner.freeze_identity() != declaration["actor_identity"]
            or require_open_window and owner.window_id != declaration["window_id"]):
        raise ValueError("Keep exact S0 actor, O1 coordinates and shared logical training window")
    gamma = declaration["gamma_identity"]
    if (gamma.get("source_usage") != "policy_training" or gamma.get("optimizer_update_allowed") is not True
            or gamma.get("presentation_version") != CONTEXT_VERSION
            or gamma.get("learning_bridge_version") != VERSION):
        raise ValueError("Only the isolated v049 Γ1 policy-training declaration admits updates")
    presentation = gamma.get("presentation_identity", {})
    s0 = gamma.get("s0", {})
    if (presentation.get("candidate_sha256") != CANDIDATE_SHA256
            or presentation.get("presentation_version") != CONTEXT_VERSION
            or s0.get("actor_identity") != declaration["actor_identity"]
            or s0.get("recipe_sha256") != digest(json_bytes(owner.recipe))
            or s0.get("member_coordinate_mapping") != COORDINATE_BINDING
            or any(not isinstance(gamma.get(key), str) or re.fullmatch(r"[0-9a-f]{64}", gamma[key]) is None
                   for key in ("design_sha256", "mapper_spec_sha256"))):
        raise ValueError("Frozen Γ1 candidate, design, Mapper or complete S0 binding differs")
    checkpoint_ref = s0.get("checkpoint_ref", {})
    checkpoint_path = Path(checkpoint_ref.get("path", ""))
    if not checkpoint_path.is_file() or digest(checkpoint_path.read_bytes()) != checkpoint_ref.get("sha256"):
        raise ValueError("Original S0 checkpoint reference is missing or changed")
    checkpoint = read_json(checkpoint_path)
    state = owner._state_bundle()
    if (checkpoint.get("state_tensor_digest") != s0.get("state_tensor_digest")
            or checkpoint.get("actor_identity") != s0["actor_identity"]
            or tensor_tree_digest({key: state[key] for key in NUMERICAL_STATE_FIELDS}, owner.torch)
               != s0.get("learning_protected_digest")):
        raise ValueError("Actual actor/critic/Adam/RNG state differs from the complete frozen S0")
    for entry in entries:
        rollout = entry.get("rollout")
        if rollout is None:
            continue
        scope = rollout.get("online_scope", {})
        if (not optimizer_scope_allows_update(rollout) or scope.get("purpose") != "policy_training"
                or scope.get("source_training_admission") is not True
                or scope.get("optimizer_update_allowed") is not True):
            raise ValueError("Development or undeclared source cannot become v049 training material")
    prepared = prepare_window(entries, owner.freeze_identity(), declaration["window_id"],
                              owner.recipe, software_feature_function)
    index, proofs = _projection_index(request_evidence_root), []
    views = {(entry["slot_id"], member): member_view(entry["rollout"], member)
             for entry in entries if entry.get("rollout") is not None for member in entry["active_members"]}
    for row in prepared["decisions"]:
        view = views[row["slot_id"], row["member_id"]]
        decision = next(item for item in view["decisions"] if item["call_id"] == row["call_id"])
        actual = decision["actual_response"]
        folder = index.get(actual.get("id"))
        if folder is None or row["tokens"] != actual["token_trace"]:
            raise ValueError("Original own-token target lacks unique durable actual-input evidence")
        proof = validate_selected_trace(owner, original=decision["actual_input"], actual=actual,
            folder=folder, member_id=row["member_id"], call_id=row["call_id"])
        proofs.append({"slot_id": row["slot_id"], "member_id": row["member_id"], "call_id": row["call_id"],
            "actor_denominator": row["actor_denominator"], "critic_denominator": row["critic_denominator"], **proof})
    return {"version": VERSION, "entries_sha256": digest(json_bytes(entries)),
        "declaration_sha256": digest(json_bytes(declaration)), "recipe_sha256": digest(json_bytes(owner.recipe)),
        "rows": proofs, "admission_slots": prepared["slots"], **material_summary(prepared),
        "probability_recomputation_executed": False, "optimizer_steps": 0,
        "scope": "Archived actual Γ1 native input and own sampled output only. The original learner separately checks probabilities and full backward; unknown/excluded slots retain their original denominator mass."}


def bind_composition(entries, declaration, weights_by_slot, *, binding):
    """Seal transparent per-original-slot/member weights; no target reconstruction."""
    slots = _declared_slots(entries, declaration)
    if (not isinstance(binding, dict) or not binding or not isinstance(weights_by_slot, dict)
            or set(weights_by_slot) != {row["slot_id"] for row in slots}):
        raise ValueError("Composition needs its provenance and all original slot/member weights")
    required = ("declaration_sha256", "design_sha256", "mapper_spec_sha256", "support_artifact_sha256")
    if (any(not isinstance(binding.get(key), str) or re.fullmatch(r"[0-9a-f]{64}", binding[key]) is None for key in required)
            or binding["declaration_sha256"] != digest(json_bytes(declaration))
            or any(binding[key] != declaration["gamma_identity"].get(key) for key in ("design_sha256", "mapper_spec_sha256"))
            or "selected_direction_artifact_sha256" not in binding
            or binding["selected_direction_artifact_sha256"] is not None and
               (not isinstance(binding["selected_direction_artifact_sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", binding["selected_direction_artifact_sha256"]) is None)):
        raise ValueError("Composition must bind the frozen declaration, design, Mapper, support and direction")
    totals = {}
    for slot in slots:
        sid = slot["slot_id"]
        if not isinstance(weights_by_slot[sid], dict) or set(weights_by_slot[sid]) != set(MEMBERS):
            raise ValueError("Composition cannot omit or invent target-member coordinates")
        for member in MEMBERS:
            weight = weights_by_slot[sid][member]
            if type(weight) not in (int, float) or not math.isfinite(weight) or not .5 <= weight <= 2:
                raise ValueError("Composition weight must be finite and inside the frozen ratio bounds")
            totals.setdefault((slot["xi_id"], member), []).append(weight)
    if any(not math.isclose(math.fsum(values), len(values), rel_tol=0, abs_tol=1e-12)
           for values in totals.values()):
        raise ValueError("Composition must preserve each original root/member block mass")
    if binding["selected_direction_artifact_sha256"] is None and any(weight != 1 for row in weights_by_slot.values() for weight in row.values()):
        raise ValueError("Nonunit composition requires the frozen selected-direction artifact")
    value = {"version": COMPOSITION_VERSION, "window_id": declaration["window_id"],
        "actor_identity": copy.deepcopy(declaration["actor_identity"]),
        "entries_sha256": digest(json_bytes(entries)), "declaration": copy.deepcopy(declaration),
        "weights_by_slot": copy.deepcopy(weights_by_slot), "binding": copy.deepcopy(binding),
        "Q_equals_B": all(weight == 1 for row in weights_by_slot.values() for weight in row.values())}
    value["seal_sha256"] = digest(json_bytes(value))
    return value


def validate_composition(entries, prepared, composition):
    if not isinstance(composition, dict) or composition.get("version") != COMPOSITION_VERSION:
        raise ValueError("Only v049 original-member composition weights are accepted")
    rebuilt = bind_composition(entries, composition["declaration"], composition["weights_by_slot"],
                               binding=composition["binding"])
    if (rebuilt != composition or prepared["window_id"] != composition["window_id"]
            or prepared["slot_count"] != len(entries)
            or [row["slot_id"] for row in prepared["slots"]] != [row["slot_id"] for row in entries]
            or prepared["actor_identity"] != composition["actor_identity"]):
        raise ValueError("Composition seal, original material, shared actor or window changed")
    byslot, seen, weights, audit = {row["slot_id"]: row for row in entries}, set(), [], []
    views = {}
    for row in prepared["decisions"]:
        sid, member, call = row["slot_id"], row["member_id"], row["call_id"]
        if (sid, member, call) in seen:
            raise ValueError("An original own action cannot receive duplicated composition mass")
        seen.add((sid, member, call))
        key = (sid, member)
        if key not in views:
            views[key] = member_view(byslot[sid]["rollout"], member)
        view = views[key]
        own = [decision for decision in view["decisions"] if decision["call_id"] == call and decision["actor_required"]]
        if len(own) != 1:
            raise ValueError("Each composition row must be exactly one original own action")
        decision, tokens = own[0], own[0]["tokens"]
        if (row["tokens"] != tokens or row["actual_response_sha256"] != decision["response_sha256"]
                or decision["loss_mask"] != [0] * len(tokens["input_ids"]) + [1] * len(tokens["output_ids"])
                or row["actor_denominator"] != len(entries) * len(MEMBERS) * view["own_action_tokens"]
                or row["critic_denominator"] != len(entries) * len(MEMBERS)
                   * sum(item["actor_required"] for item in view["decisions"])):
            raise ValueError("Keep original native tokens, own-output mask and fixed base denominators")
        weight = composition["weights_by_slot"][sid][member]
        weights.append(weight)
        audit.append({"slot_id": sid, "member_id": member, "call_id": call, "weight": weight,
            "tokens_sha256": digest(json_bytes(tokens)), "actor_denominator": row["actor_denominator"],
            "critic_denominator": row["critic_denominator"]})
    expected_order = [(entry["slot_id"], member, decision["call_id"])
        for entry in entries for member in entry["active_members"]
        for decision in views.get((entry["slot_id"], member), {}).get("decisions", [])
        if (entry["slot_id"], member, decision["call_id"]) in seen]
    if expected_order != [(row["slot_id"], row["member_id"], row["call_id"]) for row in prepared["decisions"]]:
        raise ValueError("Keep the original slot/member/decision accumulation order")
    return weights, {"version": COMPOSITION_VERSION, "composition_sha256": composition["seal_sha256"],
        "Q_equals_B": composition["Q_equals_B"], "rows": audit, "original_normalization_preserved": True,
        "additional_target_rows": 0, "critic_reweighted": False}


class SupportGradientObserver:
    """Observe original B leaf gradients, grouped by exact slot and stable member."""
    def __init__(self, parameters, torch, maximum, *, output):
        if maximum != 0:
            raise ValueError("v049 retains the original disabled group diagnostics recipe")
        self.parameters, self.torch, self.output = parameters, torch, Path(output)
        self.current, self.buffers, self.rows = None, {}, []
        self.handles = [parameter.register_hook(self._hook(name)) for name, parameter in parameters.items()]

    def _hook(self, name):
        def observe(gradient):
            if self.current is None:
                raise ValueError("Unbound gradient cannot enter original material support")
            sid, member = self.current
            target = self.buffers[sid][member]
            data = gradient.detach().cpu()
            if name not in target:
                target[name] = data.clone()
            else:
                target[name].add_(data)
            return None
        return observe

    def select(self, row):
        self.current = row["slot_id"], row["member_id"]
        self.buffers.setdefault(row["slot_id"], {}).setdefault(row["member_id"], {})
        self.rows.append({key: row[key] for key in ("slot_id", "member_id", "call_id", "actor_denominator")})

    def finish(self):
        for handle in self.handles:
            handle.remove()
        self.handles.clear()
        path = self.output / "support-gradients.pt"
        self.torch.save(self.buffers, path)
        groups = [{"slot_id": sid, "member_id": member, "parameters": len(values),
            "gradient_l2_norm": math.sqrt(sum(float(value.double().square().sum()) for value in values.values())),
            "gradient_sha256": tensor_tree_digest(values, self.torch)}
            for sid, members in self.buffers.items() for member, values in members.items()]
        receipt = {"version": VERSION, "tensor_file": reference(path), "groups": groups, "original_rows": self.rows,
            "additional_actor_forwards": 0, "additional_actor_backwards": 0, "optimizer_steps": 0,
            "hook_returns": None, "observed_baseline_loss_before_shared_clipping": True,
            "scope": "Actual original B leaf gradients, summed in original row order within each slot/member. Group sums support direction inspection only; they never replace native weighted Q+/- backwards or prove optimizer sensitivity."}
        atomic_write(self.output / "support-gradients.json", json_bytes(receipt))
        original = GroupGradientCapture(self.parameters, self.torch, 0).finish()
        return {**original, "v049_support_observation": reference(self.output / "support-gradients.json")}


@contextmanager
def _forward_meter(owner):
    old = owner.learning_logprobs
    previous = owner.__dict__.get("learning_logprobs")
    had_override = "learning_logprobs" in owner.__dict__
    meter = {"actor_forwards_started": 0, "actor_forwards_completed": 0,
             "gradient_actor_forwards_started": 0, "gradient_actor_forwards_completed": 0,
             "no_grad_actor_forwards_started": 0, "no_grad_actor_forwards_completed": 0}
    def measured(*args, **kwargs):
        kind = "gradient" if owner.torch.is_grad_enabled() else "no_grad"
        meter["actor_forwards_started"] += 1
        meter[kind + "_actor_forwards_started"] += 1
        value = old(*args, **kwargs)
        meter["actor_forwards_completed"] += 1
        meter[kind + "_actor_forwards_completed"] += 1
        return value
    owner.learning_logprobs = measured
    try:
        yield meter
    finally:
        if had_override:
            owner.learning_logprobs = previous
        else:
            del owner.learning_logprobs


def update_window(owner, entries, output, *, composition=None, observe_support_gradients=False):
    """Execute the original H=1 bytecode with only explicit isolated adapters."""
    if observe_support_gradients and composition is not None and composition.get("Q_equals_B") is not True:
        raise ValueError("Support gradients are observed only on the actual B branch")
    original = SharedActor.update_window
    namespace = {**original.__globals__, "validate_actor_composition": validate_composition}
    if observe_support_gradients:
        namespace["GroupGradientCapture"] = partial(SupportGradientObserver, output=Path(output))
    inherited = FunctionType(original.__code__, namespace, original.__name__, original.__defaults__, original.__closure__)
    inherited.__kwdefaults__ = original.__kwdefaults__
    receipt = {"version": VERSION, "original_function": "proworksim.online_training.SharedActor.update_window",
        "original_function_code_sha256": digest(marshal.dumps(original.__code__)),
        "original_source": reference(Path(original.__code__.co_filename)),
        "code_object_identical": inherited.__code__ is original.__code__,
        "closure_identical": inherited.__closure__ is original.__closure__,
        "defaults_identical": inherited.__defaults__ is original.__defaults__ and inherited.__kwdefaults__ is original.__kwdefaults__,
        "private_global_overrides": ["validate_actor_composition"] + (["GroupGradientCapture"] if observe_support_gradients else []),
        "original_module_globals_mutated": False, "original_owner_method_mutated": False,
        "scope": "Execute the original H=1 function code with isolated v049 composition validation and optional observer; original PPO, critic, accumulation, clipping and optimizer statements unchanged."}
    atomic_write(Path(output).parent / (Path(output).name + "-original-updater-binding.json"), json_bytes(receipt))
    return inherited(owner, entries, output, feature_function=software_feature_function, composition=composition)


def update_software_window(owner, entries, output, *, declaration, request_evidence_root,
                           composition=None, observe_support_gradients=False):
    output = Path(output)
    proof = validate_training_entries(owner, entries, declaration, request_evidence_root=request_evidence_root)
    atomic_write(output.parent / (output.name + "-token-evidence.json"), json_bytes(proof))
    torch = owner.torch
    if owner.device.startswith("cuda"):
        for device in range(torch.cuda.device_count()):
            torch.cuda.reset_peak_memory_stats(device)
    started = time.monotonic()
    report, meter = {}, {}
    try:
        with _forward_meter(owner) as meter:
            report = update_window(owner, entries, output, composition=composition,
                                   observe_support_gradients=observe_support_gradients)
        return report
    finally:
        if (output / "report.json").exists():
            report = read_json(output / "report.json")
        completed = report.get("backward_decisions_completed", 0)
        consumption = {"version": VERSION, "elapsed_seconds": time.monotonic() - started,
            "actual_material": {key: proof[key] for key in ("original_slot_count", "admitted_decisions",
                "admitted_input_tokens", "admitted_own_output_tokens", "sum_actual_sequence_tokens", "maximum_actual_sequence_tokens")},
            **meter, "backward_decisions_completed": completed,
            "actor_backward_decisions_completed": completed if report.get("actor_update_enabled") else 0,
            "critic_backward_decisions_completed": completed,
            "partial_row_backward_cost_exact": report.get("stage") == "complete",
            "support_additional_backward_calls": 0, "support_observer_enabled": observe_support_gradients,
            "status": report.get("status"), "actor_optimizer_steps": report.get("actor_optimizer_steps", 0),
            "critic_optimizer_steps": report.get("critic_optimizer_steps", 0),
            "peak_gpu_allocated_bytes": {str(device): torch.cuda.max_memory_allocated(device)
                for device in range(torch.cuda.device_count())} if owner.device.startswith("cuda") else {},
            "scope": "Actual learning interval, separate from generation token cost. Completed backward counts are lower bounds if a row is interrupted; no extra backward for support and no old v037 cache."}
        atomic_write(output / "software-consumption.json", json_bytes(consumption))
