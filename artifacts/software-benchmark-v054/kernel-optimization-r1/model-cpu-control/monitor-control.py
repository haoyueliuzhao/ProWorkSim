"""Small synthetic CPU controls for the read-only rollout monitor."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile


root = Path(__file__).resolve().parents[4]
source = root / "tools/monitor_kernel_rollout_v054.py"
spec = importlib.util.spec_from_file_location("rollout_monitor", source)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)
checks = {}
start = monitor.timestamp("2026-10-21T13:00:00+00:00")
assert start == monitor.timestamp("2026-10-21T21:00:00+08:00")
checks["timezone_normalization"] = True
assert monitor.in_window(start, start, start + 1800)
assert not monitor.in_window(start + 1800, start, start + 1800)
assert not monitor.in_window(start - 1, start, start + 1800)
checks["half_open_window_boundaries"] = True
native = {"ledger": {"calls": [{"usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}],
    "complete_actual_tokens": 12, "uncertain_reserved_tokens": 0, "inflight": None}}
project = {"ledger": {"model": {"records": {"call1": {"status": "settled", "charge": {
    "reported_usage": {"prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23}}}},
    "charged_tokens": 23, "held_tokens": 0, "integrity_failure": None}}}
assert monitor.token_totals(native)["complete"]
assert monitor.token_totals(project)["complete"]
project["ledger"]["model"]["held_tokens"] = 8
assert not monitor.token_totals(project)["complete"]
checks["native_project_tokens_and_unknown_reservations"] = True
row = {"slot_id": "a", "gpu": 6, "arm": "MATCH", "revision": "old",
       "wall_seconds": 100, "started_before_window": False, "tokens": monitor.token_totals(native)}
row2 = {**row, "slot_id": "b", "revision": "new", "arm": "PROJECT"}
groups = monitor.summarize_groups([row, dict(row), row2], 1800)
assert len(groups) == 2 and sum(g["closed"] for g in groups) == 2
assert all(g["closed_per_hour"] == 2 for g in groups)
assert groups[0]["known_complete_total_tokens"] == 12
checks["slot_deduplication_arm_revision_grouping_window_rate"] = True
state = {"rows": [{"slot": {"slot_id": "a"}, "next_execution_bindings": {"sha256": "new"}}],
    "generation_dispatches": [{"slot_id": "a", "physical_gpu": 6,
        "worker_started_utc": "2026-10-21T13:00:00+00:00"}]}
assert monitor.first_dispatch(state, "new", start) == (start, "a", "2026-10-21T13:00:00+00:00")
assert monitor.first_dispatch(state, "old", start) is None
assert monitor.first_dispatch(state, "new", start + 1) is None
checks["exact_revision_and_activation_trigger"] = True
with tempfile.TemporaryDirectory(prefix="v054-monitor-cpu-") as temporary:
    path = Path(temporary) / "receipt.json"
    path.write_text('{"value": 1}')
    reader = monitor.OnceReader()
    assert reader.read(path)[0] == {"value": 1}
    path.write_text('{"value": 2}')
    assert reader.read(path)[0] == {"value": 1} and len(reader.cache) == 1
checks["immutable_receipt_read_once"] = True
assert monitor.distribution([0, 50, 100])["median"] == 50
assert monitor.percentile([0, 50, 100], .9) == 90
checks["utilization_percentile_arithmetic"] = True
receipt = {"version": "v054-kernel-rollout-monitor-cpu-control-r1", "passed": all(checks.values()),
    "source": {"path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
               "bytes": source.stat().st_size}, "checks": checks,
    "GPU_queries": 0, "model_calls": 0, "live_queue_reads": 0, "monitor_started": False}
Path(__file__).with_name("monitor-control.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
