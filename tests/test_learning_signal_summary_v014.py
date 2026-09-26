"""Pure saved-record fixtures: no model or business world execution."""

import json

import pytest

from scripts.learning_signal_summary_v014 import summarize_study


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def group(task, member, call, *, positive=0, negative=0, zero=0):
    return {"task": task, "member_id": member, "stage": "open/no_episode_basis_delivery",
            "decisions": 1, "output_tokens": 2, "advantages": {"positive": positive, "negative": negative, "zero": zero},
            "advantage_range": [1, 1] if positive else [-1, -1] if negative else [0, 0],
            "critic_value_range": [0, 0], "return_target_range": [1, 1] if positive else [0, 0],
            "actor_loss_sum": -0.5 if positive else 0.5 if negative else 0.0,
            "critic_loss_sum": 0.1, "call_ids": [call], "clipped_objective_tokens": 0,
            "ratio_outside_interval_tokens": 0, "clipping_measured_tokens": 2,
            "clipped_objective_fraction": 0, "ratio_outside_interval_fraction": 0}


def fixture(tmp_path):
    study = {"jobs": [{"name": "mc-s0", "run": "run", "protocol": "protocol.json"}]}
    windows = [{"window_id": name, "mode": mode, "slots": [{"slot_id": "a"}, {"slot_id": "b"}]}
               for name, mode in [("first", "online"), ("probe", "evaluate"), ("second", "online"), ("not-started", "online")]]
    protocol = {"mode": "online", "condition": "mc", "replicate_index": 0,
                "recipe": {"seed": 7, "credit_assignment": "terminal_mc", "logprob_max_atol": .02, "logprob_mean_atol": .002},
                "windows": windows}
    save(tmp_path / "study.json", study)
    save(tmp_path / "run/online/protocol.json", protocol)
    save(tmp_path / "run/online/report.json", {"status": "running", "actor_steps_total": 2, "critic_steps_total": 2,
        "windows": [{"window_id": w["window_id"], "mode": w["mode"], "status": "complete"} for w in windows[:3]]})
    for index, value in [(0, 1), (2, -1)]:
        path = tmp_path / "run/online" / ("window-" + str(index)) / "update"
        groups = [group("handoff", "provider", "h", positive=int(value > 0), negative=int(value < 0)),
                  group("implement", "implementer", "i", zero=1)]
        admissions = [{"call_id": g["call_ids"][0], "task": g["task"], "member_id": g["member_id"],
                       "stage": {"label": g["stage"]}, "tokens": {"output_ids": [1, 2]}, "actor_denominator": 4} for g in groups]
        save(path / "admission.json", {"decisions": admissions})
        save(path / "report.json", {"status": "updated", "actor_optimizer_steps": 1, "critic_optimizer_steps": 1,
             "before_actor_identity": {"policy_version": "theta-" + str(index)},
             "after_actor_identity": {"policy_version": "theta-" + str(index + 1)}, "composition": "Q=B"})
        save(path / "signal-diagnostics.json", {"groups": groups, "gradient_capture": {
            "maximum_groups": 1, "groups": [{"task": "handoff", "member_id": "provider", "stage": groups[0]["stage"],
                "gradient_l2_norm": 2.0, "dot_with_total_gradient": 4.0}],
            "omitted_groups": [["implement", "implementer", groups[1]["stage"]]], "total_gradient_l2_norm": 2.0}})
        save(path / "losses.json", [{"call_id": "h", "composition_weight": 1}, {"call_id": "i", "composition_weight": 1}])
        checks = [{"call_id": "h", "passed": True, "signed_delta": [.001, -.001], "mean_abs_delta": .001}]
        save(path / "behavior-probability-check.json", checks)
        save(path / "gradient-probability-check.json", checks)
        if index == 0:
            save(path / "post-update-sampled-policy.json", {"maximum_decisions": 1,
                "old_probability_source": "Pre-update full-sequence recomputation after behavior-agreement guard",
                "new_probability_source": "Post-update full-sequence recomputation",
                "decisions": [{"call_id": "h", "task": "handoff", "member_id": "provider", "stage": {"label": groups[0]["stage"]},
                    "new_minus_old_logprob": [.01, -.01], "sampled_ratio_outside_clip_fraction": 0.0}]})
    save(tmp_path / "run/online/window-1/evaluation/report.json", {"actor_optimizer_steps": 0, "critic_optimizer_steps": 0})
    # Poisoned decoy must not be read or pooled, because this window is a probe.
    save(tmp_path / "run/online/window-1/update/signal-diagnostics.json", {"groups": "not a training signal"})
    return tmp_path / "study.json"


def test_summary_keeps_actual_theta_and_unknown_measurements_separate_and_excludes_probes(tmp_path):
    path = fixture(tmp_path)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    report = summarize_study(path, tmp_path)
    job = report["jobs"][0]
    assert [w["window_id"] for w in job["training_windows"]] == ["first", "second", "not-started"]
    assert [w["window_id"] for w in job["evaluation_windows_excluded"]] == ["probe"]
    first, second, missing = job["training_windows"]
    a, zero = first["rows"]
    assert a["actor_identity"] != second["rows"][0]["actor_identity"]
    assert a["advantages"] == {"positive": 1, "negative": 0, "zero": 0}
    assert second["rows"][0]["advantages"] == {"positive": 0, "negative": 1, "zero": 0}
    assert a["normalization"]["member_token_surrogate_mass"] == 0.5
    assert a["normalization"]["signed_dot_fraction_of_total_squared_norm"] == 1
    assert a["normalization"]["gradient_norm_ratio_nonadditive"] == 1
    assert zero["advantages"]["zero"] == 1
    assert zero["actual_group_gradient"]["status"] == "unknown"  # Even a zero advantage is not a saved gradient.
    assert zero["post_update"]["status"] == "unknown"
    assert second["post_update"]["status"] == "unknown"
    assert first["post_update"]["matches_predeclared_first_group_selection"] is True
    assert a["post_update"]["sampled_k3_proxy_mean"] > 0
    assert "not original cached sampling" in report["post_probability_scope"]
    assert first["behavior_probability"]["mean_abs_delta_token_weighted"] == .001
    assert missing["status"] == "not_started"
    assert missing["actual_optimizer_steps"]["status"] == "unknown"
    assert missing["rows"] == []
    assert job["evaluation_windows_excluded"][0]["saved_optimizer_steps"] == {"actor": 0, "critic": 0}
    assert {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")} == before
    assert not any("window-1/update" in row["path"] for row in report["source_files"])


def test_summary_retains_numeric_failure_and_rejects_cross_stage_binding(tmp_path):
    path = fixture(tmp_path)
    folder = tmp_path / "run/online/window-0/update"
    save(folder / "behavior-probability-check.json", [{"call_id": "h", "passed": False,
         "signed_delta": [0.03, 0.01], "mean_abs_delta": 0.02}])
    result = summarize_study(path, tmp_path)["jobs"][0]["training_windows"][0]
    assert result["behavior_probability"]["all_saved_checks_passed"] is False
    assert result["behavior_probability"]["max_abs_delta"] == .03
    assert result["behavior_probability"]["failed_call_ids"] == ["h"]
    failed = result["numerical_failure_details"]["behavior"]["failed_calls"][0]
    assert failed["task"] == "handoff" and failed["member_id"] == "provider"
    assert failed["maximum_gate_failed"] is True and failed["mean_gate_failed"] is True
    assert failed["tokens_exceeding_maximum_gate"] == [{"output_index": 0, "actual_token_id": 1,
        "behavior_logprob": None, "recomputed_logprob": None, "signed_logprob_delta": .03}]
    assert failed["full_sequence_tokens"] is None  # The fixture did not record input token IDs.
    admission = json.loads((folder / "admission.json").read_text())
    admission["decisions"][0]["stage"]["label"] = "another_saved_stage"
    save(folder / "admission.json", admission)
    with pytest.raises(ValueError, match="does not bind"):
        summarize_study(path, tmp_path)
