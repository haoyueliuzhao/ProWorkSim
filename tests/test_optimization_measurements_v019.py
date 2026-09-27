"""Measurement gates must use equal token work and original numerical tolerances."""

import copy

from scripts.build_optimization_admission_v019 import assess


def measured():
    source = {"code_commit": "frozen", "code_dirty": False}
    profile = {"fixture": "explicit test runtime"}
    base = []
    opt = []
    for index in range(3):
        for repeat in range(2):
            row = {
                "repeat": repeat,
                "http_status": 200,
                "wall_seconds": 4,
                "same_output_as_highest_baseline": False,
                "fixed_work_replay": {"token_sha256": str(index), "seconds": 1},
                "behavior_check": {
                    "passed": True,
                    "max_atol": 0.02,
                    "mean_atol": 0.002,
                    "max_abs": 0.001,
                    "mean_abs": 0.0001,
                },
                "backward_check": {
                    "original_probability_passed": True,
                    "finite": True,
                    "nonzero_elements": 1,
                    "optimizer_steps": 0,
                    "max_abs": 0.001,
                    "mean_abs": 0.0001,
                },
                "service": {
                    "execution_optimization": {
                        "prefix_cache": {
                            "hit": True,
                            "original_input_preserved": True,
                            "cache_sequence_length": 2048,
                        }
                    }
                },
            }
            opt.append(row)
            old = copy.deepcopy(row)
            old["wall_seconds"] = 8
            old["fixed_work_replay"]["seconds"] = 3
            base.append(old)
    probe = {
        "status": "complete",
        "source_before": source,
        "source_after": source,
        "requests": [{}, {}, {}],
        "max_output_override": 2048,
        "variants": [
            {"name": "fp32-highest-baseline", "status": "complete", "calls": base},
            {"name": "fp32-high-prefix2048", "status": "complete", "calls": opt},
        ],
    }
    parallel = {
        "status": "complete",
        "passed": True,
        "source_before": source,
        "source_after": source,
        "runtime_profile": profile,
        "replica_exit_code": 0,
        "actual_optimizer_steps": 0,
        "parent_actual_identity_unchanged": True,
        "replica_finished": {"has_optimizer": False, "actual_optimizer_steps": 0},
        "generation_speedup": 1.8,
        "actual_process_overlap_seconds": 1,
        "checks": [
            {
                "index": i,
                "actor_matches": True,
                "input_matches_serial": True,
                "original_probability_passed": True,
                "max_abs": 0.001,
                "mean_abs": 0.0001,
            }
            for i in range(8)
        ],
    }
    return probe, parallel, profile, source


def test_different_sampled_lengths_do_not_invent_paired_generation_speedup():
    inputs = measured()
    checks, summary = assess(*inputs)
    assert all(checks.values())
    assert summary["paired_warm_request_speedup"] is None
    assert summary["fixed_original_token_replay_speedup"] == 3
    inputs[0]["variants"][1]["calls"][1]["fixed_work_replay"]["token_sha256"] = "different-work"
    assert assess(*inputs)[0]["throughput"] is False


def test_short_output_or_failed_original_gate_cannot_admit_production():
    inputs = measured()
    inputs[0]["max_output_override"] = 64
    assert assess(*inputs)[0]["full_recompute_probability"] is False
    inputs = measured()
    inputs[0]["variants"][1]["calls"][1]["behavior_check"]["max_abs"] = 0.021
    assert assess(*inputs)[0]["prefix_probability"] is False
    inputs = measured()
    inputs[1]["replica_finished"]["has_optimizer"] = True
    assert assess(*inputs)[0]["two_replica"] is False
