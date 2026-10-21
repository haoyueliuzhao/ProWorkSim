"""One CPU-only boundary check of the dynamic 32-worker admission arithmetic."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from proworksim.software_benchmark_candidates_v054 import reference, write_new  # noqa: E402
from proworksim.software_benchmark_network_v055 import concurrency_limits, disk_admission  # noqa: E402


def disk_extension():
    previous = ROOT / "runs/software-benchmark-v055/dynamic-concurrency-control-r1.json"
    assert json.loads(previous.read_bytes())["passed"] is True
    observed = []
    for free, generation, preparation in ((99, False, False), (100, True, False), (110, True, False), (128, True, True)):
        value = disk_admission(free * 1024**3)
        assert value["generation_disk_admitted"] is generation
        assert value["preparation_disk_admitted"] is preparation
        assert value["low_water_stops_existing_work_or_scoring"] is False
        assert value["old_cache_or_task_data_deleted"] is False
        observed.append(value)
    receipt = {"version": "v055-dynamic-concurrency-disk-control-r2", "passed": True,
        "inherited_unchanged_CPU_RAM_API_arithmetic_control": reference(previous),
        "prior_seven_cases_repeated": False, "disk_cases": observed,
        "model_calls": 0, "grader_calls": 0, "workers_started": 0,
        "source": reference(ROOT / "src/proworksim/software_benchmark_network_v055.py")}
    ref = write_new(ROOT / "runs/software-benchmark-v055/dynamic-concurrency-control-r2.json", receipt)
    print(json.dumps({"passed": True, "new_disk_cases": 4, "model_calls": 0, "receipt": ref}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disk-extension-only", action="store_true")
    if parser.parse_args().disk_extension_only:
        disk_extension()
        return
    gib = 1024**3
    cases = [
        ("ample_capacity_hard_32", 176, 914, 0, 0, 64, 0, 32),
        ("five_legacy_workers_reduce_capacity", 176, 914, 5, 0, 64, 0, 29),
        ("CPU_reserve_blocks_new_generation", 32, 914, 0, 0, 64, 0, 0),
        ("RAM_reserve_blocks_new_generation", 176, 128, 0, 0, 64, 0, 0),
        ("RAM_leaves_one_after_four_graders", 176, 208, 0, 0, 64, 0, 1),
        ("API_capacity_can_be_tighter", 176, 914, 0, 0, 4, 0, 4),
        ("capacity_drop_does_not_kill_existing", 64, 914, 4, 0, 64, 8, 2),
    ]
    observations = []
    for name, cpu, memory, old_generation, old_graders, api, current, expected in cases:
        limits = concurrency_limits(cpu_count=cpu, memory_available_bytes=memory * gib,
            legacy_generations=old_generation, legacy_graders=old_graders,
            api_concurrency=api, current_generations=current)
        desired = limits["desired_generation_concurrency"]
        assert desired == expected
        assert 0 <= desired <= min(32, api, limits["generation_cpu_capacity"], limits["generation_ram_capacity"])
        assert limits["desired_scoring_concurrency"] <= 4
        assert limits["existing_workers_terminated_when_capacity_drops"] is False
        observations.append({"case": name, "passed": True, "observed": limits})
    receipt = {"version": "v055-dynamic-concurrency-control-r1", "passed": True,
        "model_calls": 0, "grader_calls": 0, "workers_started": 0,
        "cases": observations, "source": reference(ROOT / "src/proworksim/software_benchmark_network_v055.py")}
    output = ROOT / "runs/software-benchmark-v055/dynamic-concurrency-control-r1.json"
    ref = write_new(output, receipt)
    print(json.dumps({"passed": True, "cases": len(cases), "model_calls": 0, "receipt": ref}))


if __name__ == "__main__":
    main()
