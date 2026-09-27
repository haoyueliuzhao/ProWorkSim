"""Two real sampling processes, original own-token replay, and measured overlap."""

import argparse
import copy
import os
import subprocess
import sys
import time
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.storage import atomic_write, json_bytes, read_json


def wait_for(path, child=None, seconds=900):
    deadline = time.monotonic() + seconds
    while not path.exists():
        if child is not None and child.poll() is not None:
            raise RuntimeError("Sampling process exited before its declared control artifact")
        if time.monotonic() > deadline:
            raise TimeoutError("Sampling control artifact absent; no retry or replacement")
        time.sleep(0.1)
    return read_json(path)


def calls(owner, config, indices, output):
    rows = []
    for index in indices:
        ref = config["requests"][(index // 2) % len(config["requests"])]
        source = read_json(Path(ref["path"]))
        request = copy.deepcopy(source["request"])
        request["max_tokens"] = config["max_output_tokens"]
        owner.reseed(config["seed_base"] + index, label="parallel-probe-" + str(index))
        start = time.time()
        response = owner.complete(request, timeout_seconds=600)
        rows.append(
            {
                "index": index,
                "started_at": start,
                "ended_at": time.time(),
                "request": ref,
                "response": response,
            }
        )
        atomic_write(output, json_bytes(rows))
    return rows


def child_main(config_path):
    from proworksim.sampling_replica_v019 import load_replica

    config = read_json(config_path)
    out = Path(config["output"])
    start = time.time()
    source = code_identity()
    owner = load_replica(Path(config["snapshot"]), out / "replica-resident")
    ready = {
        "identity": owner.verify_sampling_identity(),
        "seconds": time.time() - start,
        "source": source,
    }
    atomic_write(out / "replica-ready.json", json_bytes(ready))
    wait_for(out / "start-parallel.json")
    rows = calls(
        owner,
        config,
        [i for i in range(config["count"]) if (i + 1 - config["count"]) % 2 == 1],
        out / "replica-calls.json",
    )
    atomic_write(
        out / "replica-finished.json",
        json_bytes(
            {
                "identity": owner.verify_sampling_identity(),
                "source_before": source,
                "source_after": code_identity(),
                "rows": len(rows),
                "actual_optimizer_steps": 0,
                "has_optimizer": hasattr(owner, "actor_optimizer")
                or hasattr(owner, "critic_optimizer"),
            }
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--child-config", type=Path)
    p.add_argument("--model", type=Path)
    p.add_argument("--manifest", type=Path)
    p.add_argument("--candidate")
    p.add_argument("--devices", type=int)
    p.add_argument("--replica-gpus")
    p.add_argument("--request-record", type=Path, action="append")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.child_config is not None:
        child_main(a.child_config)
        return
    from proworksim.candidate_runtime_v019 import CandidateActor, candidate_profile
    from proworksim.online_training import reference
    import torch

    parent_gpus = os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",")
    replica_gpus = a.replica_gpus.split(",")
    if (
        set(parent_gpus) & set(replica_gpus)
        or len(parent_gpus) != a.devices
        or len(replica_gpus) != a.devices
    ):
        raise ValueError("Two disjoint groups with unchanged device count are required")
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = code_identity()
    started = time.time()
    owner = CandidateActor.from_candidate(
        a.model,
        manifest=a.manifest,
        profile=candidate_profile(a.candidate, devices=a.devices),
        output=out / "resident",
        recipe={
            "seed": 2026093041,
            "max_length": 16384,
            "max_output_tokens": 2048,
            "diagnostic_max_groups": 0,
            "post_update_max_decisions": 0,
            "max_rss_bytes": 192 * 1024**3,
        },
    )
    owner.begin_window("parallel-sampling-diagnostic-v019")
    owner.export_sampling_snapshot(out / "snapshot")
    config = {
        "version": "parallel-sampling-diagnostic-v0.19",
        "snapshot": str(out / "snapshot"),
        "output": str(out),
        "requests": [reference(p) for p in a.request_record],
        "count": 8,
        "seed_base": 202609271950,
        "max_output_tokens": 64,
    }
    atomic_write(out / "config.json", json_bytes(config))
    command = [
        sys.executable,
        "-m",
        "scripts.parallel_sampling_probe_v019",
        "--child-config",
        str(out / "config.json"),
    ]
    log = (out / "replica.log").open("x")
    child = subprocess.Popen(
        command,
        env={**os.environ, "CUDA_VISIBLE_DEVICES": a.replica_gpus},
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    wait_for(out / "replica-ready.json", child)
    # Both residents have loaded. Separate whole-run cold cost remains reported.
    owner.prefix_cache.clear()
    start = time.time()
    serial = calls(owner, config, list(range(8)), out / "serial-calls.json")
    serial_seconds = time.time() - start
    owner.prefix_cache.clear()
    parallel_start = time.time()
    atomic_write(out / "start-parallel.json", json_bytes({"at": parallel_start}))
    parent_indices = [i for i in range(8) if (i + 1 - 8) % 2 == 0]
    own = calls(owner, config, parent_indices, out / "parent-calls.json")
    replica_finish = wait_for(out / "replica-finished.json", child)
    child.wait(timeout=30)
    log.close()
    parallel_seconds = time.time() - parallel_start
    remote = read_json(out / "replica-calls.json")
    rows = sorted(own + remote, key=lambda x: x["index"])
    checks = []
    for row in rows:
        response = row["response"]
        item = {"index": row["index"], "http_status": response["http_status"]}
        if response["http_status"] == 200:
            body = response["body"]
            trace = body["token_trace"]
            with torch.no_grad():
                current = owner.learning_logprobs(trace).detach().cpu()
            difference = (current - torch.tensor(trace["behavior_logprobs"])).abs()
            item.update(
                actor_matches=body["actor_identity"] == owner.freeze_identity(),
                input_matches_serial=trace["input_ids"]
                == serial[row["index"]]["response"]["body"]["token_trace"]["input_ids"],
                output_matches_serial=trace["output_ids"]
                == serial[row["index"]]["response"]["body"]["token_trace"]["output_ids"],
                max_abs=float(difference.max()),
                mean_abs=float(difference.mean()),
                original_probability_passed=bool(
                    difference.max() <= 0.02 and difference.mean() <= 0.002
                ),
            )
        checks.append(item)
    identity_ok = owner._make_identity() == owner.freeze_identity()
    overlap = max(
        0,
        min(max(x["ended_at"] for x in own), max(x["ended_at"] for x in remote))
        - max(min(x["started_at"] for x in own), min(x["started_at"] for x in remote)),
    )
    record = {
        "version": "parallel-sampling-probe-v0.19",
        "status": "complete",
        "candidate": a.candidate,
        "scope": "Eight serial and the same eight two-process diagnostic requests capped64; no world actions/optimizer steps. Cold startup reported separately; not a full episode speedup.",
        "source_before": source,
        "source_after": code_identity(),
        "runtime_profile": candidate_profile(a.candidate, devices=a.devices),
        "actor_identity": owner.freeze_identity(),
        "parent_actual_identity_unchanged": identity_ok,
        "replica_ready": read_json(out / "replica-ready.json"),
        "replica_finished": replica_finish,
        "replica_exit_code": child.returncode,
        "checks": checks,
        "actual_optimizer_steps": 0,
        "serial_generation_seconds": serial_seconds,
        "parallel_generation_seconds": parallel_seconds,
        "generation_speedup": serial_seconds / parallel_seconds,
        "actual_process_overlap_seconds": overlap,
        "cold_total_seconds_including_both_loads_and_checks": time.time() - started,
        "parent_gpu_group": parent_gpus,
        "replica_gpu_group": replica_gpus,
    }
    record["passed"] = bool(
        identity_ok
        and child.returncode == 0
        and overlap > 0
        and not replica_finish["has_optimizer"]
        and replica_finish["actual_optimizer_steps"] == 0
        and source
        == record["source_after"]
        == replica_finish["source_before"]
        == replica_finish["source_after"]
        and all(
            c.get("actor_matches")
            and c.get("input_matches_serial")
            and c.get("original_probability_passed")
            for c in checks
        )
    )
    atomic_write(out / "report.json", json_bytes(record))
    print(
        json_bytes(
            {
                k: record[k]
                for k in [
                    "passed",
                    "generation_speedup",
                    "actual_process_overlap_seconds",
                    "cold_total_seconds_including_both_loads_and_checks",
                ]
            }
        ).decode()
    )
    if not record["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
