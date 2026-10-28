"""Read existing qualification and cash receipts through the client boundary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from proworksim import software_benchmark_deepseek_runtime_v067 as runtime  # noqa: E402
from proworksim.software_benchmark_candidates_v054 import reference, write_new  # noqa: E402


def check(output):
    instance = runtime.DeepSeekRuntime()
    prepared = instance.read_only_preflight()
    neutral = runtime.preparation_usage()
    result = {"version": "v067-real-existing-api-preparation-control-r1", "passed": True,
        "python": sys.version, "runtime_source": reference(runtime.__file__),
        "control_script": reference(__file__), "qualification": reference(runtime.QUALIFICATION),
        "continuation_inventory": reference(runtime.policy.RESUME_FILE),
        "ledger_path": str(runtime.LEDGER), "canonical_receipts": neutral,
        "validated_usage": prepared["neutral_usage"], "eligible_API_slots": prepared["eligible_API_slots"],
        "tool_names": sorted(prepared["allowed_tool_names"]),
        "client_created": instance.client is not None, "counter_created": instance.counter is not None,
        "identity_written": False, "API_calls": 0, "credentials_read": False,
        "old_ledger_writes": 0, "Docker_operations": 0, "GPU_operations": 0}
    if instance.client is not None or instance.counter is not None:
        raise ValueError("The read-only preparation crossed the real client boundary")
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    return write_new(output, result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    print(json.dumps(check(parser.parse_args().output)))
