"""One real managed SDK opportunity rejected before any provider request."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    folder = parser.parse_args().output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    from proworksim.software_benchmark_deepseek_api_v055 import BudgetStopped
    from proworksim.software_benchmark_deepseek_interfaces_v055 import DeepSeekAdapter
    from proworksim.software_benchmark_deepseek_managed_v055 import RemoteProjectOwner, build_runtime
    from proworksim.software_benchmark_managed_v054 import managed_port
    from proworksim.software_benchmark_world_v054 import build_software_collaboration_case
    from proworksim.software_calibration_collector_v051 import DispatchDeadline, close_runtime, run_fragment
    from proworksim.repository_sources_v054 import RepositorySources, capture_repository
    from proworksim.model_policy import CONTROL_TOOLS
    from proworksim.storage import digest, json_bytes

    source = folder / "public"
    source.mkdir()
    (source / "fixture.py").write_text("value = 0\n")
    manifest = capture_repository(source, folder / "source", task_id="fixture__budget-1",
        problem_statement="Neutral pre-dispatch budget check only.", source_identity={
            "instance_id": "fixture__budget-1", "repo": "fixture/budget", "base_commit": "a" * 40,
            "dataset_revision": "b" * 40})
    def never_test(**kwargs):
        raise RuntimeError("No public test is part of this pre-dispatch control")

    prepared = build_software_collaboration_case("fixture__budget-1", folder / "world",
                                               provider=RepositorySources(manifest, runner=never_test))
    names = {tool["name"] for tool in managed_port(prepared).tools()} | {tool["name"] for tool in CONTROL_TOOLS}

    class NeverDispatch:
        ledger = SimpleNamespace(snapshot=lambda: {"inflight_count": 0, "halted": None})

        def complete(self, *args, **kwargs):
            raise BudgetStopped("synthetic_global_budget_pre_dispatch_stop")

    def counter(request):
        return {"prompt_tokens": 1000, "method": "programmed_CPU_fixture",
                "request_sha256": digest(json_bytes(request))}

    adapter = DeepSeekAdapter(client=NeverDispatch(), arm="PROJECT", thinking=True,
        slot_id="synthetic-budget", condition_id="PROJECT-thinking", folder=folder / "provider-ledger",
        allowed_tool_names=names, counter=counter)
    runtime, _, _ = build_runtime(RemoteProjectOwner(adapter, window_id="synthetic-budget"),
        prepared, folder / "runtime", deadline=DispatchDeadline())
    try:
        boundary = run_fragment(prepared, runtime)
        budget = runtime.team_budget.snapshot()
        assert boundary["execution_integrity_failure"] is None
        assert runtime.actions == 0 and runtime.opportunities == 1
        assert budget["attempts"] == budget["charged_tokens"] == budget["held_tokens"] == 0
        assert budget["decisions"] == 1 and adapter.ledger.attempts == 0
        assert boundary["role_stops"] == {"member_001": "model_budget_exhausted"}
        receipt = {"version": "v055-managed-predispatch-control-r1", "passed": True,
            "network_requests": 0, "model_requests": 0, "GPU_loads": 0,
            "boundary": boundary, "provider_ledger": adapter.ledger.snapshot()}
        (folder / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"passed": True, "model_requests": 0, "decisions": 1,
                          "actual_attempts": 0, "actual_tokens": 0, "held_tokens": 0}))
    finally:
        close_runtime(runtime)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
