"""Exact weighted-decision gradient reuse over the frozen v036 learning path.

Cache entries contain the gradient actually computed from loss * weight. We do
not scale an unweighted leaf gradient across BF16 operations. Every candidate
keeps the original decision order, clipping and complete-common Adam state.
"""
from contextlib import contextmanager
import fcntl
from functools import partial
import math
from pathlib import Path
import time

from .gradient_bank_v037 import WeightedGradientCache
from .online_training import (prepare_window, probability_check, ppo_sum, reference,
                              tensor_tree_digest, validate_actor_composition)
from .online_signals import sampled_change, select_post_update_rows, summarize_signals
from .software_learning_v036 import validate_training_entries, software_feature_function
from .storage import atomic_write, digest, json_bytes, read_json

VERSION = "exact-weighted-gradient-reuse-v0.37"


def _progress(output, name, kind="boundary"):
    import os
    atomic_write(Path(output).parent / "task.json", json_bytes(
        {"task": name, "kind": kind, "started_at": time.time(), "pid": os.getpid()}))


@contextmanager
def _locked(path, output):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        _progress(output, "wait-exact-cache-lock-" + path.stem, "cache_wait")
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            _progress(output, "inspect-exact-cache-" + path.stem)
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _accumulate(parameters, gradients):
    # Match dense AccumulateGrad: preserve original row order, no regrouping,
    # precision conversion, post-hoc scalar multiplication or optimizer step.
    for name, value in gradients.items():
        parameter = parameters[name]
        if parameter.grad is None:
            parameter.grad = value.clone()
        else:
            parameter.grad.add_(value)


def _snapshot_rng(owner):
    torch = owner.torch
    return tensor_tree_digest({"cpu": torch.get_rng_state(),
        "cuda": torch.cuda.get_rng_state_all() if owner.device.startswith("cuda") else []}, torch)


def _cache_binding(owner, entries, prepared, binding):
    if not isinstance(binding, dict) or not binding:
        raise ValueError("An explicit immutable common/material/source binding is required")
    state = owner._state_bundle()
    from . import gradient_bank_v037
    return {"version": VERSION, "execution_binding": binding,
            "cache_implementation_sha256": {Path(path).name: digest(Path(path).read_bytes())
                for path in (__file__, gradient_bank_v037.__file__)},
            "complete_initial_state_sha256": tensor_tree_digest(state, owner.torch),
            "actor_identity": owner.freeze_identity(), "recipe": owner.recipe,
            "entries_sha256": digest(json_bytes(entries)),
            "prepared_sha256": digest(json_bytes(prepared)),
            "initial_rng_sha256": _snapshot_rng(owner)}


def update_software_window(owner, entries, output, *, declaration,
                           request_evidence_root, composition=None, cache_root, binding):
    output = Path(output)
    proof = validate_training_entries(owner, entries, declaration,
                                      request_evidence_root=request_evidence_root)
    atomic_write(output.parent / (output.name + "-token-evidence.json"), json_bytes(proof))
    started = time.monotonic()
    report = update_window(owner, entries, output, cache_root=cache_root,
        binding={**binding, "declaration_sha256": digest(json_bytes(declaration)),
                 "training_material_sha256": digest(json_bytes(proof))},
        feature_function=software_feature_function, composition=composition)
    consumption = {"version": VERSION, "elapsed_seconds": time.monotonic() - started,
        "actual_material": {key: proof[key] for key in ("original_slot_count", "admitted_decisions",
            "admitted_input_tokens", "admitted_own_output_tokens", "sum_actual_sequence_tokens",
            "maximum_actual_sequence_tokens")},
        **{key: report.get(key) for key in ("status", "cache_actual_backward_decisions",
            "cache_hit_decisions", "cache_applied_decisions", "actor_optimizer_steps", "critic_optimizer_steps")},
        "scope": "Actual newly executed backwards and exact cached contributions are counted separately."}
    atomic_write(output / "software-consumption.json", json_bytes(consumption))
    return report

def update_window(self, entries, output, *, cache_root, binding, feature_function=None, update_actor=True, post_update_selector=None, composition=None):
    """One complete-window PPO accumulation; no old D0 or reward-diversity gate."""
    if self.sampling_only:
        raise ValueError("Readonly sampling replicas cannot update")
    if self.phase != "collecting" or self.busy:
        raise ValueError("Update follows a finished collection with no active model calls")
    if self.recipe["diagnostic_max_groups"] != 0:
        raise ValueError("Exact gradient reuse requires the frozen disabled group diagnostics")
    torch = self.torch
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    self.phase = "updating"
    self.clear_generation_cache()
    before = self.actor_state()
    before_steps = self.actor_steps, self.critic_steps
    report = {
        "version": VERSION, "window_id": self.window_id, "status": "preparing",
        "before_actor_identity": self.freeze_identity(), "recipe": self.recipe,
        "actor_optimizer_steps": 0, "critic_optimizer_steps": 0,
        "training_happened": False, "backward_decisions_completed": 0,
        "cache_actual_backward_decisions": 0, "cache_hit_decisions": 0,
        "cache_applied_decisions": 0, "behavior_cache_hits": 0,
        "actual_behavior_forward_decisions": 0,
        "native_accumulation_exact_checks": 0,
        "transport_kind": "resident_direct", "actual_network_http_calls": 0,
        "composition": "Q=B, all admitted actor targets have composition weight 1",
        "advantage": self.recipe["credit_assignment"] + " return minus frozen pre-update zero-initialized observed-history critic; no normalization",
        "target_normalization_scope": "Member-token-average surrogate; no claim of exact unbiased equivalence to unnormalized episodic policy gradient",
    }

    capture_handles = []

    def save(stage):
        report["stage"] = stage
        report["resource"] = self._resource_guard()
        atomic_write(output / "report.json", json_bytes(report))

    try:
        self.model.eval()
        prepared = prepare_window(entries, self.freeze_identity(), self.window_id, self.recipe, feature_function)
        atomic_write(output / "admission.json", json_bytes(prepared))
        rows = prepared["decisions"]
        full_binding = _cache_binding(self, entries, prepared, binding)
        cache_root = Path(cache_root)
        cache_root.mkdir(parents=True, exist_ok=True)
        binding_sha = digest(json_bytes(full_binding))
        cache_folder = cache_root / binding_sha
        report.update(cache_binding_sha256=binding_sha, cache_root=str(cache_folder.resolve()),
            cache_contract="Exact original row and float.hex loss weight; native weighted backward; same-order FP32 accumulation")
        composition_weights = [1.0] * len(rows)
        if composition is not None:
            composition_weights, composition_report = validate_actor_composition(
                entries, prepared, composition
            )
            atomic_write(output / "composition.json", json_bytes({
                "version": VERSION, "original_composition_sha256": digest(json_bytes(composition)),
                "weights": composition_weights,
                "scope": "Reconstructible from frozen P2 inputs and allocation; no duplicated raw rollout histories"}))
            atomic_write(output / "composition-admission.json", json_bytes(composition_report))
            report["composition_materialization"] = reference(output / "composition.json")
            report["composition_admission"] = reference(output / "composition-admission.json")
            if not composition_report["Q_equals_B"]:
                report["composition"] = (
                    "Bound member actor weights on the declared eligible branch; "
                    "residuals and other members remain one"
                )
        # Freeze the diagnostic contexts before any optimizer step. A custom
        # selector changes only measured contexts, never loss/admission rows.
        selector = post_update_selector or select_post_update_rows
        post_indices = selector(rows, self.recipe["post_update_max_decisions"])
        if (not isinstance(post_indices, list) or len(post_indices) > self.recipe["post_update_max_decisions"]
                or any(type(i) is not int or not 0 <= i < len(rows) for i in post_indices)
                or len(set(post_indices)) != len(post_indices)):
            raise ValueError("Post-update selector must return unique bounded original decision indices")
        selection = {"selector": selector.__module__ + "." + selector.__qualname__,
                     "description": selector.__doc__, "selected_indices": post_indices,
                     "selected_calls": [{"slot_id": rows[i]["slot_id"], "task": rows[i]["task"],
                                         "member_id": rows[i]["member_id"], "call_id": rows[i]["call_id"]}
                                        for i in post_indices],
                     "frozen_before_optimizer_step": True}
        atomic_write(output / "post-update-selection.json", json_bytes(selection))
        report.update(admitted_decisions=len(rows), scheduled_slots=len(entries),
                      admitted_output_tokens=sum(len(r["tokens"]["output_ids"]) for r in rows))
        torch.save(self._state_bundle(), output / "shared-before.pt")
        save("admission")
        if not rows:
            report["status"] = "zero_step_no_admitted_own_actions"
            return report
        checks, values, advantages = [], [], []
        probability_path = cache_root / (binding_sha + "-behavior.json")
        with _locked(cache_root / "locks" / (binding_sha + "-behavior.lock"), output):
            if probability_path.exists():
                cached = read_json(probability_path)
                if (cached.get("binding") != full_binding
                        or cached.get("sha256") != digest(json_bytes({k: v for k, v in cached.items() if k != "sha256"}))
                        or [c["call_id"] for c in cached.get("checks", [])] != [r["call_id"] for r in rows]):
                    raise ValueError("Behavior cache common, row inventory or payload changed")
                checks = cached["checks"]
                report["behavior_cache_hits"] = len(rows)
            else:
                rng_before = _snapshot_rng(self)
                with torch.no_grad():
                    for row in rows:
                        self._resource_guard()
                        probabilities = self.learning_logprobs(row["tokens"])
                        check = probability_check(probabilities.cpu().tolist(), row["tokens"]["behavior_logprobs"], self.recipe)
                        checks.append({"call_id": row["call_id"], **check})
                        report["actual_behavior_forward_decisions"] += 1
                        del probabilities
                if _snapshot_rng(self) != rng_before:
                    raise ValueError("Behavior replay consumed RNG; it cannot be shared by this cache contract")
                cached = {"binding": full_binding, "checks": checks}
                cached["sha256"] = digest(json_bytes(cached))
                atomic_write(probability_path, json_bytes(cached))
        with torch.no_grad():
            for row in rows:
                value = float(self.critic(torch.tensor(row["critic_features"], dtype=torch.float32, device=self.device)).squeeze())
                values.append(value)
                advantages.append(row["reward"] - value)
        atomic_write(output / "behavior-probability-check.json", json_bytes(checks))
        report.update(behavior_probability_passed=all(c["passed"] for c in checks),
                      old_critic_values=values, advantages=advantages,
                      rewards=[r["reward"] for r in rows])
        if not report["behavior_probability_passed"]:
            report["status"] = "zero_step_probability_mismatch"
            return report
        if not all(math.isfinite(v) for v in advantages):
            raise ValueError("Nonfinite historical-return advantage")
        # No random/unsupported initial critic noise can create an actor update.
        zero_signal = not self.critic_has_nonzero_reward_history and all(r["reward"] == 0 for r in rows)
        if zero_signal and any(abs(value) > 1e-12 for value in values):
            raise ValueError("Critic before any nonzero reward history must predict exactly zero")
        actor_enabled = update_actor and not zero_signal and any(a != 0 for a in advantages)
        report.update(zero_signal_window=zero_signal, actor_update_enabled=actor_enabled,
                      critic_had_nonzero_reward_history=self.critic_has_nonzero_reward_history)
        if not update_actor:
            report["status"] = "frozen_actor_evaluation_no_update"
            return report
        self.actor_optimizer.zero_grad(set_to_none=True)
        self.critic_optimizer.zero_grad(set_to_none=True)
        self.model.train()  # All dropout zero; HF enables gradient checkpointing only in train mode.
        gradient_checks, losses = [], []
        row_bindings = [{"index": index, "row_sha256": digest(json_bytes(row)),
                         "call_id": row["call_id"], "advantage": advantage}
                        for index, (row, advantage) in enumerate(zip(rows, advantages))]
        with _locked(cache_root / "locks" / (binding_sha + "-header.lock"), output):
            cache = WeightedGradientCache(cache_folder, torch=torch, binding=full_binding,
                rows=row_bindings, actor_parameters=self.actor_parameters)
        cache_receipts = []
        for index, (row, advantage, composition_weight) in enumerate(zip(rows, advantages, composition_weights)):
            self._resource_guard()
            _progress(output, "weighted-gradient-row-" + str(index))
            actor_loss_value, ratio_range = 0.0, None
            clipped_tokens = outside_tokens = measured_tokens = 0
            if actor_enabled:
                key = digest(json_bytes([binding_sha, index, float(composition_weight).hex()]))
                with _locked(cache_root / "locks" / (key + ".lock"), output):
                    cached = cache.get(index, composition_weight, device=self.device)
                    if cached is None:
                        rng_before = _snapshot_rng(self)
                        probabilities = self.learning_logprobs(row["tokens"])
                        check = probability_check(probabilities.detach().cpu().tolist(), row["tokens"]["behavior_logprobs"], self.recipe)
                        if not check["passed"]:
                            gradient_checks.append({"call_id": row["call_id"], **check})
                            atomic_write(output / "gradient-probability-check.json", json_bytes(gradient_checks))
                            self.actor_optimizer.zero_grad(set_to_none=True)
                            self.critic_optimizer.zero_grad(set_to_none=True)
                            report["status"] = "zero_step_gradient_probability_mismatch"
                            return report
                        behavior = torch.tensor(row["tokens"]["behavior_logprobs"], device=probabilities.device)
                        total, ratio = ppo_sum(torch, probabilities, behavior, advantage, self.recipe["clip"])
                        actor_loss = total / row["actor_denominator"]
                        if composition_weight != 1.0:
                            actor_loss = actor_loss * composition_weight
                        if not torch.isfinite(actor_loss):
                            raise ValueError("Nonfinite actor loss")
                        detached_ratio = ratio.detach()
                        clipped_tokens = int(((detached_ratio > 1 + self.recipe["clip"]) & (advantage > 0)
                                              | (detached_ratio < 1 - self.recipe["clip"]) & (advantage < 0)).sum())
                        outside_tokens = int(((detached_ratio < 1 - self.recipe["clip"])
                                              | (detached_ratio > 1 + self.recipe["clip"])).sum())
                        measured_tokens = detached_ratio.numel()
                        leaf_gradients = {}
                        prior_gradients = {name: parameter.grad.detach().clone()
                            for name, parameter in self.actor_parameters.items() if parameter.grad is not None}
                        def capture(name, gradient):
                            if name in leaf_gradients:
                                raise ValueError("A leaf gradient was delivered twice for one backward")
                            leaf_gradients[name] = gradient.detach().clone()
                        capture_handles = [parameter.register_hook(partial(capture, name))
                                           for name, parameter in self.actor_parameters.items()]
                        try:
                            actor_loss.backward()
                        finally:
                            for handle in capture_handles:
                                handle.remove()
                            capture_handles = []
                        # In the actual native backward, the hooks only observe
                        # leaf contributions. Verify the precise device/dtype
                        # addition used by hits against native AccumulateGrad.
                        _progress(output, "verify-native-cache-accumulation-" + str(index))
                        for name, gradient in leaf_gradients.items():
                            expected = prior_gradients.get(name)
                            expected = gradient if expected is None else expected.add_(gradient)
                            if not torch.equal(expected, self.actor_parameters[name].grad):
                                raise ValueError("Cached same-order addition differs from native leaf accumulation")
                        del prior_gradients
                        report["native_accumulation_exact_checks"] += 1
                        report["cache_actual_backward_decisions"] += 1
                        report["backward_decisions_completed"] += 1
                        actor_loss_value = float(actor_loss.detach())
                        ratio_range = [float(ratio.detach().min()), float(ratio.detach().max())]
                        if _snapshot_rng(self) != rng_before:
                            raise ValueError("Weighted backward consumed RNG; exact replay requires unchanged RNG")
                        metadata = {"check": check, "actor_loss_value": actor_loss_value,
                            "ratio_range": ratio_range, "clipped_tokens": clipped_tokens,
                            "outside_tokens": outside_tokens, "measured_tokens": measured_tokens}
                        receipt = cache.put(index, composition_weight, leaf_gradients, metadata=metadata)
                        del probabilities, behavior, total, ratio, actor_loss, detached_ratio, leaf_gradients
                    else:
                        metadata = cached["metadata"]
                        check = metadata["check"]
                        if check.get("passed") is not True:
                            raise ValueError("Cached gradient lacks the original passing probability guard")
                        _accumulate(self.actor_parameters, cached["gradients"])
                        receipt = cached["receipt"]
                        actor_loss_value = metadata["actor_loss_value"]
                        ratio_range = metadata["ratio_range"]
                        clipped_tokens = metadata["clipped_tokens"]
                        outside_tokens = metadata["outside_tokens"]
                        measured_tokens = metadata["measured_tokens"]
                        report["cache_hit_decisions"] += 1
                        del cached
                    gradient_checks.append({"call_id": row["call_id"], **check})
                    cache_receipts.append({"index": index, "key_sha256": receipt["key_sha256"],
                        "receipt_sha256": receipt["receipt_sha256"]})
                    report["cache_applied_decisions"] += 1
            value = self.critic(torch.tensor(row["critic_features"], dtype=torch.float32, device=self.device)).squeeze()
            critic_loss = 0.5 * (value - row["reward"]).square() / row["critic_denominator"]
            if not torch.isfinite(critic_loss):
                raise ValueError("Nonfinite critic loss")
            (critic_loss * self.recipe["critic_coefficient"]).backward()
            losses.append({"call_id": row["call_id"], "slot_id": row["slot_id"],
                           "member_id": row["member_id"], "actor_loss": actor_loss_value,
                           "critic_loss": float(critic_loss.detach()), "ppo_ratio_range": ratio_range,
                           "composition_weight": composition_weight, "clipped_objective_tokens": clipped_tokens,
                           "ratio_outside_interval_tokens": outside_tokens, "clipping_measured_tokens": measured_tokens})
            del value, critic_loss
            save("backward")
        atomic_write(output / "gradient-probability-check.json", json_bytes(gradient_checks))
        atomic_write(output / "losses.json", json_bytes(losses))
        signal = summarize_signals(rows, values, advantages, losses)
        signal["gradient_capture"] = {"enabled": False, "maximum_groups": 0,
            "scope": "Original frozen recipe disables group diagnostics; exact row gradients are separately cached"}
        atomic_write(output / "cache-receipts.json", json_bytes(cache_receipts))
        report["cache_receipts"] = reference(output / "cache-receipts.json")
        atomic_write(output / "signal-diagnostics.json", json_bytes(signal))
        report["signal_diagnostics"] = reference(output / "signal-diagnostics.json")
        gradients = {"actor": {n: p.grad.detach().cpu().clone() for n, p in self.actor_parameters.items() if p.grad is not None},
                     "critic": {n: p.grad.detach().cpu().clone() for n, p in self.critic.named_parameters() if p.grad is not None}}
        torch.save(gradients, output / "gradients-before-clip.pt")
        actor_norm = torch.nn.utils.clip_grad_norm_(list(self.actor_parameters.values()), self.recipe["gradient_clip"])
        critic_norm = torch.nn.utils.clip_grad_norm_(self.critic.parameters(), self.recipe["gradient_clip"])
        if not torch.isfinite(actor_norm) or not torch.isfinite(critic_norm):
            raise ValueError("Nonfinite shared actor/critic gradient; no optimizer step")
        report["gradient_norms"] = {"actor": float(actor_norm), "critic": float(critic_norm)}
        if actor_enabled and actor_norm > 0:
            self.actor_optimizer.step()
            self.actor_steps += 1
            self.policy_revision += 1
            report.update(actor_optimizer_steps=1, training_happened=True)
            # Preserve an accurately attributed partial update if a later operation fails.
            self._identity = self._make_identity()
            save("actor_updated_pending_critic")
        if critic_norm > 0:
            self.critic_optimizer.step()
            self.critic_steps += 1
            self.critic_has_nonzero_reward_history |= any(r["reward"] != 0 for r in rows)
            report["critic_optimizer_steps"] = 1
        after = self.actor_state()
        report["changed_actor_elements"] = sum(int((after[k] != before[k]).sum()) for k in before)
        if report["actor_optimizer_steps"] and not report["changed_actor_elements"]:
            raise ValueError("An optimizer step occurred but no actor parameter changed")
        self.model.eval()
        post = {"selection": selection,
                "same_parameter_probability_gate": False,
                "maximum_decisions": self.recipe["post_update_max_decisions"], "decisions": [],
                "old_probability_source": "Pre-update full-sequence recomputation after behavior-agreement guard",
                "new_probability_source": "Post-update full-sequence recomputation at identical contexts and sampling temperature",
                "full_distribution_kl_computed": False,
                "before_actor_identity": report["before_actor_identity"], "after_actor_identity": self.freeze_identity()}
        with torch.no_grad():
            for index in post_indices:
                row = rows[index]
                self._resource_guard()
                current = self.learning_logprobs(row["tokens"]).cpu().tolist()
                post["decisions"].append({"call_id": row["call_id"], "task": row["task"],
                                          "member_id": row["member_id"], "stage": row["stage"],
                                          **sampled_change(checks[index]["recomputed_logprobs"], current, self.recipe["clip"])})
        atomic_write(output / "post-update-sampled-policy.json", json_bytes(post))
        report["post_update_sampled_policy"] = reference(output / "post-update-sampled-policy.json")
        report["post_update_additional_actor_forwards"] = len(post_indices)
        report["status"] = "updated" if report["actor_optimizer_steps"] else "zero_step_zero_actor_advantage_or_gradient"
        report["actor_enabled_without_step"] = actor_enabled and not report["actor_optimizer_steps"]
        report["stage"] = "complete"
        return report
    except (KeyboardInterrupt, SystemExit) as error:
        report.update(status="interrupted", interruption={"type": type(error).__name__, "message": str(error)})
        raise
    except Exception as error:
        report.update(status="window_update_error", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        for handle in capture_handles:
            handle.remove()
        self.model.eval()
        self.clear_generation_cache()
        self.phase = "idle"
        self._identity = self._make_identity()
        report.update(after_actor_identity=self.freeze_identity(),
                      actor_optimizer_steps=self.actor_steps - before_steps[0],
                      critic_optimizer_steps=self.critic_steps - before_steps[1],
                      actor_steps_total=self.actor_steps, critic_steps_total=self.critic_steps,
                      cache_clear_count=self.cache_clear_count)
        # Always persist the true update counters, even if resource inspection fails.
        atomic_write(output / "report.json", json_bytes(report))
