#!/usr/bin/env python3
"""One owned CPU service: partial RPC, escaped session, once-only candidate close."""
from __future__ import annotations

import argparse
import ast
import datetime
import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import sys
import threading
import time
import uuid

from proworksim.repository_sources_v054 import snapshot_repository
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_episode_v054 import Episode
from proworksim.software_benchmark_native_closure_v054 import lock_native_candidate
from proworksim.software_benchmark_supervision_v054 import launch_owned, stop_owned


class ScriptedOwner:
    def __init__(self):
        self.events = []

    def freeze_identity(self):
        return {"raw_release": True, "checkpoint": None, "adapter_sha256": None}

    def capture_evaluation_state(self):
        self.events.append("capture")
        return {"synthetic": True}

    def begin_window(self, window):
        self.events.append(["window", window])

    def reseed(self, seed, *, label):
        self.events.append(["seed", seed, label])
        return {"synthetic": True, "seed": seed, "label": label}


def rpc_class(source):
    """Execute the exact production class, without importing the heavyweight SDK."""
    parsed = ast.parse(source.read_text())
    definition = next(item for item in parsed.body
                      if isinstance(item, ast.ClassDef) and item.name == "NativeToolRPC")
    namespace = {"json": json, "math": math, "os": os, "selectors": selectors,
                 "threading": threading, "time": time, "uuid": uuid}
    exec(compile(ast.Module(body=[definition], type_ignores=[]),
                 str(source), "exec"), namespace)
    return namespace["NativeToolRPC"]


def denied(call, error=Exception):
    try:
        call()
    except error:
        return True
    raise AssertionError("Expected operation to be rejected")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    repository = Path(__file__).resolve().parents[1]
    work = root / "public-worktree"
    work.mkdir()
    (work / "keep.txt").write_text("before\n")
    baseline = write_new(root / "baseline.json", snapshot_repository(work))
    task = {"instance_id": "synthetic-lifecycle", "repo": "fixture/lifecycle",
            "base_commit": "0" * 40, "problem_statement": "Synthetic repository only."}
    slot = {"slot_id": "synthetic-MATCH-lifecycle", "instance_id": task["instance_id"],
            "arm": "MATCH", "seed": 11, "execution_authorized": False}
    slots = write_new(root / "slots.json", {"slots": [slot]})
    binding = {key: write_new(root / (key + ".json"), {"synthetic": True, "kind": key})
               for key in ("configuration", "environment", "owner")}
    (work / "keep.txt").write_text("after\n")
    (work / "new.bin").write_bytes(b"\0binary")
    arguments = dict(binding=binding, synthetic=True, synthetic_claim_root=root / "claims")
    episode = Episode(slots, slot["slot_id"], **arguments)
    checks = {"duplicate_slot_claim_rejected": denied(
        lambda: Episode(slots, slot["slot_id"], **arguments), FileExistsError)}
    child_code = """
import os, pathlib, signal, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))
while True:
    pathlib.Path(sys.argv[2]).write_text(str(time.monotonic()))
    time.sleep(.02)
"""
    parent_code = """
import os, pathlib, signal, subprocess, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))
subprocess.Popen([sys.executable, "-c", sys.argv[2], sys.argv[3], sys.argv[4]],
                 start_new_session=True, stdin=subprocess.DEVNULL,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
sys.stdin.readline()
sys.stdout.write('{"id":1,"type":')
sys.stdout.flush()
while True:
    time.sleep(10)
"""
    process = scope = None
    try:
        process, scope = launch_owned(
            [sys.executable, "-c", parent_code, root / "parent.pid", child_code,
             root / "descendant.pid", root / "heartbeat"],
            claim_id=episode.claim_id, role="synthetic", runtime_seconds=30,
            stop_seconds=0.3, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=(root / "service.stderr").open("xb"))
        episode.register_scope(scope)
        deadline = time.monotonic() + 5
        while not (root / "heartbeat").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert (root / "heartbeat").exists()
        owner = ScriptedOwner()
        episode.enter(owner=owner, synthetic_limits=(10, 20))
        checks["entered_slot_cannot_restart"] = denied(lambda: episode.enter(owner=owner))
        checks["owner_window_seed_sequence"] = (
            owner.events[0] == "capture" and owner.events[1][0] == "window"
            and owner.events[2] == ["seed", 11, slot["slot_id"]])
        checks["lock_before_process_exit_rejected"] = denied(
            lambda: episode.candidate_boundary().__enter__())
        rpc_source = repository / "src/proworksim/software_benchmark_native_binding_v054.py"
        ready = {"type": "ready", "version": "software-benchmark-native-worker-v054",
                 "isolation": {"pid": 1, "capabilities_all_zero": True,
                               "dumpable": False, "no_new_privileges": True},
                 "synthetic_ready_only": True}
        import io
        writer = io.TextIOWrapper(process.stdin, encoding="utf-8", write_through=True)
        rpc = rpc_class(rpc_source)(ready=ready, reader=process.stdout, writer=writer)
        with episode.request("synthetic_partial_RPC", synthetic_seconds=0.4):
            checks["production_RPC_partial_frame_timeout"] = denied(
                lambda: rpc.request("terminal", {"command": "synthetic"}, timeout_seconds=0.1),
                TimeoutError)
            checks["failed_RPC_close_not_used_for_quiescence"] = denied(rpc.close, RuntimeError)
            assert episode.watchdog.wait(timeout=10) == 0
        process.wait(timeout=5)  # Reap the actual outer systemd-run launcher.
        quiet = episode.accept_quiescence()
        receipt = json.loads(Path(quiet["path"]).read_text())
        checks["external_watchdog_request_timeout"] = receipt["reason"] == "request_timeout"
        checks["cgroup_empty_after_TERM_then_KILL"] = receipt["all_quiet"]
        checks["outer_launcher_reaped"] = process.poll() is not None
        checks["setsid_descendant_no_longer_running"] = True
        for name in ("parent", "descendant"):
            pid = int((root / (name + ".pid")).read_text())
            stat = Path(f"/proc/{pid}/stat")
            if stat.exists():
                state = stat.read_text().rsplit(")", 1)[1].split()[0]
                checks["setsid_descendant_no_longer_running"] &= state in {"Z", "X"}
        heartbeat = (root / "heartbeat").read_bytes()
        time.sleep(0.1)
        checks["descendant_writes_stopped"] = heartbeat == (root / "heartbeat").read_bytes()
        locked = lock_native_candidate(
            episode, baseline_reference=baseline, public_worktree=work,
            public_task=task, dataset_revision="synthetic-only", output=root / "candidate")
        value = json.loads(Path(locked["path"]).read_text())
        checks["lossless_patch_roundtrip"] = value["patch_receipt"]["round_trip_verified"]
        checks["only_terminal_code_no_delivery"] = value["delivery"] is None
        checks["second_candidate_lock_rejected"] = denied(lambda: lock_native_candidate(
            episode, baseline_reference=baseline, public_worktree=work,
            public_task=task, dataset_revision="synthetic-only", output=root / "candidate-again"))
        result = {
            "version": "software-benchmark-episode-lifecycle-control-v054",
            "started_utc": started,
            "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "all_passed": all(checks.values()), "checks": checks,
            "claim": reference(episode.root / "claim.json"), "quiescence": quiet,
            "candidate_lock": locked, "production_RPC_source": reference(rpc_source),
            "RPC_execution": "exact AST class, synthetic ready and half-frame process; no SDK Agent",
            "owner": "scripted CPU fixture; no actual RNG or model operations",
            "model_calls": 0, "GPU_opens": 0, "weight_opens": 0,
            "actual_Docker_or_repository_admission": False,
            "formal_execution_authorized": False,
        }
        write_new(root / "result.json", result)
        print(json.dumps({"all_passed": result["all_passed"], "checks": checks,
                          "receipt": reference(root / "result.json")}, ensure_ascii=False))
        return 0 if result["all_passed"] else 1
    finally:
        if scope is not None:
            stop_owned(scope)
        if process is not None:
            process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
