"""Derive the launch gate from original fixed-input and two-process measurements."""

import argparse
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.candidate_runtime_v019 import candidate_profile
from proworksim.storage import atomic_write, digest, json_bytes, read_json


CANDIDATES = {"qwen35-9b": ("qwen3.5-9b", 2), "qwen38-27b": ("qwen3.8-27b", 4)}


def reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def mappings(rows):
    result = {}
    for row in rows:
        key, path = row.split("=", 1)
        if key not in CANDIDATES or key in result:
            raise ValueError("Unique declared candidate paths required")
        result[key] = Path(path)
    return result


def assess(probe, parallel, profile, source):
    variants = {v["name"]: v for v in probe.get("variants", [])}
    old = variants.get("fp32-highest-baseline", {})
    new = variants.get("fp32-high-prefix2048", {})
    rows = new.get("calls", [])
    warm = [r for r in rows if r.get("repeat") == 1]
    original_warm = [r for r in old.get("calls", []) if r.get("repeat") == 1]
    source_ok = bool(
        probe.get("source_before") == probe.get("source_after") == source
        and parallel.get("source_before") == parallel.get("source_after") == source
    )
    complete = bool(
        source_ok
        and probe.get("status") == "complete"
        and new.get("status") == "complete"
        and probe.get("max_output_override") == 2048
        and len(probe.get("requests", [])) == 3
        and len(rows) == 6
        and len(warm) == 3
        and all(r.get("http_status") == 200 for r in rows)
    )
    prefixes = [
        r.get("service", {}).get("execution_optimization", {}).get("prefix_cache", {}) for r in warm
    ]
    probabilities = bool(
        complete
        and all(
            r.get("behavior_check", {}).get("passed") is True
            and r["behavior_check"].get("max_atol") == 0.02
            and r["behavior_check"].get("mean_atol") == 0.002
            and r["behavior_check"]["max_abs"] <= 0.02
            and r["behavior_check"]["mean_abs"] <= 0.002
            for r in warm
        )
    )
    backward = bool(
        complete
        and all(
            r.get("backward_check", {}).get("original_probability_passed") is True
            and r["backward_check"].get("finite") is True
            and r["backward_check"].get("nonzero_elements", 0) > 0
            and r["backward_check"].get("optimizer_steps") == 0
            and r["backward_check"]["max_abs"] <= 0.02
            and r["backward_check"]["mean_abs"] <= 0.002
            for r in warm
        )
    )
    replica_checks = parallel.get("checks", [])
    replica = bool(
        source_ok
        and parallel.get("status") == "complete"
        and parallel.get("passed") is True
        and parallel.get("runtime_profile") == profile
        and len(replica_checks) == 8
        and {c.get("index") for c in replica_checks} == set(range(8))
        and parallel.get("replica_exit_code") == 0
        and parallel.get("actual_optimizer_steps") == 0
        and parallel.get("parent_actual_identity_unchanged") is True
        and parallel.get("replica_finished", {}).get("has_optimizer") is False
        and parallel.get("replica_finished", {}).get("actual_optimizer_steps") == 0
        and all(
            c.get("actor_matches") is True
            and c.get("input_matches_serial") is True
            and c.get("original_probability_passed") is True
            and c.get("max_abs", 1) <= 0.02
            and c.get("mean_abs", 1) <= 0.002
            for c in replica_checks
        )
    )
    equal_work = bool(
        len(original_warm) == 3
        and all(r.get("same_output_as_highest_baseline") is True for r in warm)
    )
    ratio = (
        sum(r["wall_seconds"] for r in original_warm) / sum(r["wall_seconds"] for r in warm)
        if equal_work
        else None
    )
    fixed_work = bool(
        len(original_warm) == len(warm) == 3
        and all(
            a.get("fixed_work_replay", {}).get("token_sha256")
            == b.get("fixed_work_replay", {}).get("token_sha256")
            and a.get("fixed_work_replay", {}).get("seconds", 0) > 0
            and b.get("fixed_work_replay", {}).get("seconds", 0) > 0
            for a, b in zip(original_warm, warm)
        )
    )
    replay_ratio = (
        (
            sum(r["fixed_work_replay"]["seconds"] for r in original_warm)
            / sum(r["fixed_work_replay"]["seconds"] for r in warm)
        )
        if fixed_work
        else None
    )
    timing = bool(
        complete
        and replica
        and fixed_work
        and replay_ratio > 1
        and parallel.get("generation_speedup", 0) > 1
        and parallel.get("actual_process_overlap_seconds", 0) > 0
    )
    return {
        "prefix_probability": bool(
            probabilities
            and all(
                p.get("hit") is True
                and p.get("original_input_preserved") is True
                and p.get("cache_sequence_length") == 2048
                for p in prefixes
            )
        ),
        "full_recompute_probability": probabilities,
        "backward": backward,
        "two_replica": replica,
        "throughput": timing,
    }, {
        "paired_warm_request_speedup": ratio,
        "fixed_original_token_replay_speedup": replay_ratio,
        "two_process_generation_speedup": parallel.get("generation_speedup"),
        "replica_probe_cold_total_seconds": parallel.get(
            "cold_total_seconds_including_both_loads_and_checks"
        ),
        "scope": "Measured paired micro-workload and real simultaneous samplers, not whole-episode or full-pilot speedup. Original backward/probability gates remain active during every actual update.",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--probe", action="append", required=True)
    p.add_argument("--parallel", action="append", required=True)
    p.add_argument("--manifest", action="append", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("New gate output required")
    source = code_identity()
    if source["code_dirty"] is not False:
        raise ValueError("Freeze the execution source before formal admission")
    probes, parallels, manifests = map(mappings, (a.probe, a.parallel, a.manifest))
    if not set(probes) == set(parallels) == set(manifests):
        raise ValueError("Candidate artifact inventories differ")
    result = {
        "version": "harness-optimization-admission-v0.19",
        "execution_source_commit": source["code_commit"],
        "source_identity": source,
        "candidates": {},
    }
    for key, path in probes.items():
        name, devices = CANDIDATES[key]
        profile = candidate_profile(name, devices=devices)
        probe, parallel = read_json(path), read_json(parallels[key])
        if probe.get("candidate") != name or parallel.get("candidate") != name:
            raise ValueError("Actual measured candidate differs")
        checks, summary = assess(probe, parallel, profile, source)
        result["candidates"][key] = {
            "passed": all(checks.values()),
            "runtime_profile": profile,
            "weight_manifest_sha256": digest(manifests[key].read_bytes()),
            "checks": {
                k: {
                    "passed": v,
                    "evidence": reference(parallels[key] if k == "two_replica" else path),
                }
                for k, v in checks.items()
            },
            "additional_parallel_evidence": reference(parallels[key]),
            "measured_summary": summary,
        }
    atomic_write(a.output, json_bytes(result))
    print(json_bytes({k: v["passed"] for k, v in result["candidates"].items()}).decode())


if __name__ == "__main__":
    main()
