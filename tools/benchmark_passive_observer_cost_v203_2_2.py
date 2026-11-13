"""Bounded paired CPU control for the existing passive Sidecar, without live work.

Each arm runs in a fresh ordinary-user process. The synthetic input file is shared
and immutable by convention/hash; only the existing Sidecar is toggled. Recovery
is a separate process after an injected exit at the journal's after_commit seam.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CRASH_EXIT = 73
THREAD_ENV = {
    "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1",
    "CUDA_VISIBLE_DEVICES": "", "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONHASHSEED": "0",
}
LIMITATIONS = [
    "Only 3 pairs of 1000 synthetic capture boundaries; no long-duration production or leak claim.",
    "The real v203.2.1 Sidecar.record/finish and ObserverJournal WAL/FULL path are reused; no legacy PassiveRecorder substitute.",
    "Both arms import the same runtime modules. Startup, imports and frozen-file loading are excluded from capture_lifecycle/workload times but included in parent-measured process totals.",
    "Synthetic model inputs/outputs and tool receipts are frozen, small and deterministic; no provider, real tool, controller scheduling, actual task, model reasoning or production payload replay occurs.",
    "Measured latency is a local synthetic operation (two capture boundaries), not provider/HTTP request latency; off-arm work is deliberately tiny, so relative slowdown is not a production percentage.",
    "Capture lifecycle includes initialization, INITIAL, append boundaries and finish/CAPTURE_CLOSED; operation percentiles exclude initialization, finish, disk/RSS sampling and verification.",
    "Workload CPU/wall includes common synthetic result hashing and bounded resource samples; no online graph projection is added, matching the real append-only Sidecar.",
    "Host HTTP capture, physical provider journal, SDK history, archival/compression, scoring, export, full offline analysis and persistent services are excluded.",
    "RSS is a process high-water mark/current Linux proc snapshot, not an allocation attribution. Startup imports are present in both arms; small paired differences can be noisy.",
    "Disk figures are logical file bytes and allocated st_blocks*512, sampled while open and after close; transient within-sample WAL peaks and directory metadata are not measured.",
    "Crash recovery covers process exit after final durable commit, with no prior projection checkpoint; it verifies the journal and reconstructs receipt-derived PassiveState only. It is not a restored running agent/controller or full accepted-request view reconstruction.",
    "Recovery excludes MODEL_REQUEST/MODEL_RESPONSE semantic projection; those records are still hash-chain verified and exactly reconciled against the frozen manifest.",
    "No power/storage loss, precommit evidence loss, concurrent writers, missing host records or production completeness guarantee is tested here.",
    "A single sequential run order off/on, on/off, off/on has no CPU pinning, cache flushing, isolation or confidence interval; shared-host scheduling/filesystem load may influence results.",
]


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def sha(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def frozen_workload(events):
    assert events > 0 and events % 4 == 0
    operations = []
    tools = ["read_file", "replace_file", "send_message", "handoff_patch", "integrate_patch", "run_tests"]
    for i in range(events // 4):
        actor = ["implementer", "reviewer"][i % 2]
        request_id = f"synthetic-request-{i:04d}"
        request = {"member_id": actor, "request_id": request_id, "model": "synthetic-no-provider",
                   "messages": [{"role": "system", "content": "Frozen CPU control; no API execution."},
                                {"role": "user", "content": "fixed-context-" * 128 + str(i)}],
                   "tools": [{"type": "function", "function": {"name": tools[i % len(tools)]}}]}
        reply = {"id": f"synthetic-response-{i}", "choices": [{"message": {"content": "frozen"}}],
                 "usage": {"prompt_tokens": 128, "completion_tokens": 8, "total_tokens": 136},
                 "synthetic_witness_not_provider_acceptance": True}
        operations.append({"operation": "synthetic_request", "output": reply, "records": [
            {"kind": "MODEL_REQUEST", "key": "request:" + request_id, "payload": request},
            {"kind": "MODEL_RESPONSE", "key": "response:" + request_id,
             "payload": {"actor": actor, "request_id": request_id, "body": reply}}]})
        tool = tools[i % len(tools)]
        arguments = {"path": f"src/file_{i % 16}.py", "body": "synthetic message " + str(i),
                     "patch_id": f"patch-{i // 6}", "selection": "synthetic-test"}
        response = {"ok": i % 17 != 0, "result": {
            "source_reference": f"synthetic-version-{i}", "path": arguments["path"],
            "paths": [arguments["path"]], "sequence": i, "patch_id": arguments["patch_id"],
            "report_id": f"synthetic-test-{i}", "executed": True, "passed": i % 3 != 0,
            "recipient": ["reviewer", "implementer"][i % 2]},
            "synthetic_witness_not_tool_execution": True}
        if not response["ok"]:
            response["error"] = {"code": "replacement_not_unique", "message": "frozen synthetic rejection"}
        payload = {"actor": actor, "tool": tool, "arguments": arguments,
                   "association": {"model_call_id": request_id, "model_tool_call_id": f"call-{i}"}}
        operations.append({"operation": "synthetic_tool", "output": response, "records": [
            {"kind": "INTENT", "key": f"intent:{actor}:{request_id}:call-{i}", "payload": payload},
            {"kind": "RECEIPT", "key": f"receipt:{actor}:{request_id}:call-{i}",
             "payload": {**payload, "response": response}}]})
    return {"schema": "synthetic-observer-cost-v203.2.2", "capture_boundaries": events,
            "initial": {"episode_id": "synthetic-cost", "fixed_members": ["implementer", "reviewer"],
                        "synthetic_only": True, "policy_input_is_not_global_observer_graph": True},
            "operations": operations}


def process_sample():
    fields = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(("VmRSS:", "Threads:")):
            key, value = line.split(":", 1)
            fields[key] = int(value.split()[0])
    assert fields["Threads"] == 1, fields
    return {"current_RSS_bytes": fields["VmRSS"] * 1024,
            "peak_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "threads": fields["Threads"]}


def disk_sample(folder):
    files = [p for p in folder.glob("*") if p.is_file()]
    return {"logical_bytes": sum(p.stat().st_size for p in files),
            "allocated_bytes": sum(p.stat().st_blocks * 512 for p in files)}


def quantiles(values):
    ordered = sorted(values)
    def percentile(q):
        position = (len(ordered) - 1) * q
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return {"count": len(ordered), "p50_us": percentile(.5), "p95_us": percentile(.95),
            "p99_us": percentile(.99), "max_us": ordered[-1], "mean_us": statistics.mean(ordered),
            "quantile_method": "linear interpolation at (n-1)*q"}


def load_mechanism():
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.environ.update(THREAD_ENV)
    # Local guard: imported modules may define transports, but workers cannot use
    # a network socket or create a process. The coordinator alone launches workers.
    def guard(event, args):
        if event in {"socket.connect", "socket.connect_ex", "socket.bind", "subprocess.Popen", "os.system", "os.fork"}:
            raise RuntimeError(f"Forbidden in offline measurement worker: {event}")
    sys.addaudithook(guard)
    sys.path.insert(0, str(ROOT / "src"))
    from proworksim.software_role_baseline_runtime_v203_2_1 import Sidecar
    from proworksim.software_observer_journal_v203_2_1 import ObserverJournal
    from proworksim.software_passive_observer_v203_2 import PassiveState
    return Sidecar, ObserverJournal, PassiveState


def verify_records(journal, workload, project=None):
    expected = [{"kind": "INITIAL", "key": "initial", "payload": workload["initial"]}]
    expected.extend(r for op in workload["operations"] for r in op["records"])
    count, kinds, head = 0, Counter(), None
    for row in journal.records():  # Validates every record and the complete chain.
        count += 1
        if row["kind"] == "CAPTURE_CLOSED":
            assert count == len(expected) + 1
            assert row["payload"]["status"] == "synthetic_complete"
        else:
            wanted = expected[count - 1]
            assert all(row[field] == wanted[field] for field in ("kind", "key", "payload"))
        kinds[row["kind"]] += 1
        head = row["chain_sha256"]
        if project is not None and row["kind"] in {"INITIAL", "INTENT", "RECEIPT"}:
            project.apply(row)
    return {"records": count, "kinds": dict(kinds), "head_sha256": head,
            "hash_chain_verified": True, "manifest_payloads_reconciled": True}


def worker(mode, workload_path, directory):
    Sidecar, ObserverJournal, PassiveState = load_mechanism()
    workload_bytes = workload_path.read_bytes()
    workload = json.loads(workload_bytes)
    directory.mkdir(parents=True, exist_ok=True)
    capture = directory / "capture"
    if mode == "recover":
        started, cpu = time.perf_counter(), time.process_time()
        before = process_sample()
        state = PassiveState("synthetic-cost", workload["initial"]["fixed_members"])
        with ObserverJournal(capture / "events.sqlite") as journal:
            proof = verify_records(journal, workload, state)
            assert proof["records"] == workload["capture_boundaries"] + 1
            assert state.receipt_count == workload["capture_boundaries"] // 4
            assert journal.load_projection()["cursor"] == 0
            checkpoint = journal.save_projection("default", proof["records"], state.snapshot(), expected_cursor=0)
            assert checkpoint["cursor"] == proof["records"]
        result = {"mode": mode, "recovery_wall_seconds": time.perf_counter() - started,
                  "recovery_CPU_seconds": time.process_time() - cpu,
                  "before": before, "after": process_sample(), "proof": proof,
                  "projected_receipts": state.receipt_count, "projected_events": len(state.events),
                  "checkpoint_cursor": checkpoint["cursor"], "world_actions_dispatched": 0,
                  "full_agent_runtime_recovered": False, "disk_after": disk_sample(capture)}
        save(directory / "recovery.json", result)
        return
    assert mode in {"on", "off", "crash"}
    capture.mkdir(exist_ok=False)
    before = process_sample()
    lifecycle_start, lifecycle_cpu = time.perf_counter(), time.process_time()
    sidecar = Sidecar(capture, "synthetic-cost") if mode != "off" else None
    if sidecar:
        sidecar.record("INITIAL", "initial", workload["initial"])
        assert sidecar.journal is not None and sidecar.fault_count == 0
    initialized = process_sample()
    latencies = {"synthetic_request": [], "synthetic_tool": [], "all": []}
    samples = [{"completed_boundaries": 0, **process_sample(), **disk_sample(capture)}]
    outcome_hash, operation_counts = hashlib.sha256(), Counter()
    workload_start, workload_cpu = time.perf_counter(), time.process_time()
    for ordinal, operation in enumerate(workload["operations"]):
        start = time.perf_counter_ns()
        first, second = operation["records"]
        if sidecar:
            sidecar.record(first["kind"], first["key"], first["payload"])
        # This deterministic local result is identical with observation on/off.
        outcome_hash.update(encoded(operation["output"]))
        operation_counts[operation["operation"]] += 1
        if sidecar:
            if mode == "crash" and ordinal == len(workload["operations"]) - 1:
                sidecar.journal._fault = lambda stage: os._exit(CRASH_EXIT) if stage == "after_commit" else None
            sidecar.record(second["kind"], second["key"], second["payload"])
        elapsed = (time.perf_counter_ns() - start) / 1000
        latencies[operation["operation"]].append(elapsed)
        latencies["all"].append(elapsed)
        if (ordinal + 1) % 100 == 0:
            samples.append({"completed_boundaries": 2 * (ordinal + 1),
                            **process_sample(), **disk_sample(capture)})
    workload_cost = {"wall_seconds": time.perf_counter() - workload_start,
                     "CPU_seconds": time.process_time() - workload_cpu}
    assert hashlib.sha256(workload_path.read_bytes()).hexdigest() == hashlib.sha256(workload_bytes).hexdigest()
    sidecar_summary = sidecar.finish("synthetic_complete") if sidecar else None
    lifecycle_cost = {"wall_seconds": time.perf_counter() - lifecycle_start,
                      "CPU_seconds": time.process_time() - lifecycle_cpu}
    after = process_sample()
    disk_after = disk_sample(capture)
    proof = None
    if sidecar:
        assert sidecar.fault_count == 0
        with ObserverJournal(capture / "events.sqlite") as journal:
            proof = verify_records(journal, workload)
        assert proof["records"] == workload["capture_boundaries"] + 2
    else:
        assert disk_after["logical_bytes"] == 0
    result = {"mode": mode, "pid": os.getpid(), "input_sha256": hashlib.sha256(workload_bytes).hexdigest(),
              "outcome_sha256": outcome_hash.hexdigest(), "operation_counts": dict(operation_counts),
              "capture_lifecycle": lifecycle_cost, "workload": workload_cost,
              "latency": {key: quantiles(values) for key, values in latencies.items()},
              "before": before, "initialized": initialized, "after": after,
              "resource_samples": samples, "disk_after": disk_after,
              "sampled_open_disk_max": {key: max(sample[key] for sample in samples)
                                        for key in ("logical_bytes", "allocated_bytes")},
              "sidecar_summary": sidecar_summary, "proof": proof,
              "resource_caps": {"CPU_seconds": 60, "address_space_bytes": 1024 ** 3, "threads": 1}}
    save(directory / "measurement.json", result)


def launch(mode, workload, directory, expected=0):
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", mode,
               "--workload", str(workload), "--directory", str(directory)]
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.perf_counter()
    completed = subprocess.run(command, env={**os.environ, **THREAD_ENV}, capture_output=True,
                               text=True, timeout=90, check=False)
    wall = time.perf_counter() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    assert completed.returncode == expected, (mode, completed.returncode, completed.stdout, completed.stderr)
    return {"exit_code": completed.returncode, "process_wall_seconds": wall,
            "process_CPU_seconds": after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
            "stdout": completed.stdout, "stderr": completed.stderr}


def main(output, events, pairs):
    assert 1 <= pairs <= 3 and 4 <= events <= 1000 and events % 4 == 0
    output.mkdir(parents=True, exist_ok=False)
    workload = output / "frozen-input.json"
    save(workload, frozen_workload(events))
    paths = [Path(__file__), ROOT / "src/proworksim/software_role_baseline_runtime_v203_2_1.py",
             ROOT / "src/proworksim/software_observer_journal_v203_2_1.py",
             ROOT / "src/proworksim/software_passive_observer_v203_2.py"]
    protocol = {"version": "v203.2.2", "pairs": pairs, "capture_boundaries_per_arm": events,
                "operations_per_arm": events // 2, "extra_initial_and_close_records_on_arm": 2,
                "input_sha256": hashlib.sha256(workload.read_bytes()).hexdigest(),
                "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                "runtime": sys.version, "command": sys.argv, "real_API_calls": 0,
                "containers": 0, "GPU_use": False, "root_or_host_configuration_changes": False,
                "maximum_concurrent_workers": 1, "worker_caps": {"CPU_seconds": 60, "address_space_bytes": 1024 ** 3},
                "limitations": LIMITATIONS}
    save(output / "protocol.json", protocol)
    pair_results = []
    for pair in range(pairs):
        modes = ["off", "on"] if pair % 2 == 0 else ["on", "off"]
        arms = {}
        for mode in modes:
            directory = output / f"pair-{pair + 1}" / mode
            process = launch(mode, workload, directory)
            arms[mode] = {**json.loads((directory / "measurement.json").read_text()), "process": process}
        assert arms["on"]["input_sha256"] == arms["off"]["input_sha256"] == protocol["input_sha256"]
        assert arms["on"]["outcome_sha256"] == arms["off"]["outcome_sha256"]
        assert arms["on"]["operation_counts"] == arms["off"]["operation_counts"]
        delta = {"workload_CPU_seconds": arms["on"]["workload"]["CPU_seconds"] - arms["off"]["workload"]["CPU_seconds"],
                 "workload_wall_seconds": arms["on"]["workload"]["wall_seconds"] - arms["off"]["workload"]["wall_seconds"],
                 "capture_lifecycle_CPU_seconds": arms["on"]["capture_lifecycle"]["CPU_seconds"] - arms["off"]["capture_lifecycle"]["CPU_seconds"],
                 "peak_RSS_bytes": arms["on"]["after"]["peak_RSS_bytes"] - arms["off"]["after"]["peak_RSS_bytes"],
                 "closed_disk_logical_bytes": arms["on"]["disk_after"]["logical_bytes"] - arms["off"]["disk_after"]["logical_bytes"],
                 "operation_p95_us": arms["on"]["latency"]["all"]["p95_us"] - arms["off"]["latency"]["all"]["p95_us"]}
        pair_results.append({"pair": pair + 1, "order": modes, "on": arms["on"], "off": arms["off"], "on_minus_off": delta})
    recovery_directory = output / "after-commit-crash"
    crashed = launch("crash", workload, recovery_directory, CRASH_EXIT)
    recovered = launch("recover", workload, recovery_directory)
    recovery = {**json.loads((recovery_directory / "recovery.json").read_text()),
                "crashed_process": crashed, "recovery_process": recovered}
    medians = {key: statistics.median(pair["on_minus_off"][key] for pair in pair_results)
               for key in pair_results[0]["on_minus_off"]}
    summary = {"version": "v203.2.2", "status": "synthetic_controls_passed", "protocol": protocol,
               "pairs": pair_results, "median_paired_on_minus_off": medians, "recovery": recovery,
               "assertions": {"same_frozen_input": True, "same_synthetic_outputs": True,
                              "exact_durable_payload_sequence": True, "no_capture_faults": True,
                              "single_thread_workers": True, "postcommit_prefix_recovered_without_world_replay": True}}
    save(output / "summary.json", summary)
    rows = []
    for pair in pair_results:
        for mode in ["off", "on"]:
            arm = pair[mode]
            latency = arm["latency"]["all"]
            rows.append(f"| {pair['pair']} | {mode} | {arm['workload']['CPU_seconds']:.6f} | {arm['workload']['wall_seconds']:.6f} | "
                        f"{arm['after']['peak_RSS_bytes'] / 2**20:.3f} | {latency['p50_us']:.3f} / {latency['p95_us']:.3f} / {latency['p99_us']:.3f} | "
                        f"{arm['disk_after']['logical_bytes']} |")
    readme = "\n".join([
        "# v203.2.2 观测器有限合成配对成本控制", "",
        "本实验直接使用现行 `Sidecar.record/finish`、`ObserverJournal`，未修改旧模块；恢复时使用真实 `PassiveState`。它衡量局部追加捕获开销，不能代表完整生产请求成本或长期可靠性。",
        "", f"同一冻结输入：{pairs} 对 × 每臂 {events} 个捕获边界，另有 INITIAL/CAPTURE_CLOSED 两条。每臂 {events // 2} 个合成操作，每操作两条边界；250 个模型输入/响应和 250 个工具意图/回执（默认规模）。全部为本地数据，真实模型/API/容器/GPU调用为 0。",
        "", "各臂使用独立普通子进程，顺序交替，最多 1 个运行中子进程；单线程，CPU 硬上限 60 秒、地址空间上限 1 GiB。两臂输入散列、输出散列、操作数完全相同。所有开启臂逐条校验完整 journal 哈希链、键、类型及 payload；无捕获故障。",
        "", "| 配对 | 观测 | 工作负载 CPU 秒 | 工作负载墙钟秒 | 进程峰值 RSS MiB | 每操作 p50 / p95 / p99 μs | 关闭后逻辑字节 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |", *rows, "",
        f"配对增量中位数：工作负载 CPU {medians['workload_CPU_seconds']:.6f} 秒、墙钟 {medians['workload_wall_seconds']:.6f} 秒、生命周期 CPU {medians['capture_lifecycle_CPU_seconds']:.6f} 秒；峰值 RSS 差 {medians['peak_RSS_bytes'] / 2**20:.3f} MiB。RSS 是进程高水位，含双方共同导入，微小差值不解释为精确分配量。",
        "", f"独立故障例在最后一条回执提交成功、返回确认前自退出（退出码 73）；恢复子进程验证 {recovery['proof']['records']} 条 durable 记录并重建 {recovery['projected_receipts']} 个回执的 PassiveState，持久化投影检查点。恢复内部墙钟 {recovery['recovery_wall_seconds']:.6f} 秒、CPU {recovery['recovery_CPU_seconds']:.6f} 秒；含解释器启动、导入、结果写出的恢复进程墙钟 {recovered['process_wall_seconds']:.6f} 秒。未重新派发任何世界动作。",
        "", "`summary.json` 保存每臂的全部指标、配对差值、按操作类型延迟、进程总 CPU/墙钟、每 200 边界的 RSS/磁盘增长、开库采样峰值、故障恢复及限制；`protocol.json` 固定源文件和输入 SHA-256。`pair-*/{on,off}/measurement.json` 是原始测量，开启臂保留 SQLite 原件，`frozen-input.json` 是完整合成数据。",
        "", "## 边界与限制", "", *[f"- {item}" for item in LIMITATIONS], "",
        "## 复现", "", "以新的空输出目录执行（拒绝覆盖已有证据）：", "", "```bash",
        ".venv/bin/python tools/benchmark_passive_observer_cost_v203_2_2.py --output artifacts/software-benchmark-v203-2-2/observer-cost-r2", "```", "",
        "本次运行是必要机制断言与测量本身；未重算原 12 题统计，未全量重放原模型载荷，也未运行冗余测试。", "",
    ])
    (output / "README.md").write_text(readme)
    print(json.dumps({"output": str(output), "status": summary["status"], "median_paired_delta": medians,
                      "recovery_wall_seconds": recovery["recovery_wall_seconds"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/software-benchmark-v203-2-2/observer-cost-r1")
    parser.add_argument("--events", type=int, default=1000)
    parser.add_argument("--pairs", type=int, default=3)
    parser.add_argument("--worker", choices=["on", "off", "crash", "recover"])
    parser.add_argument("--workload", type=Path)
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.workload, args.directory)
    else:
        main(args.output.resolve(), args.events, args.pairs)
