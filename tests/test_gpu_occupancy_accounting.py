"""Finite CPU controls for GPU interval accounting, without device/model access."""
import pytest

from scripts.gpu_occupancy_accounting import (
    GpuInterval, build_report, interval_accounting, timestamp_us,
)


def interval(gpu, start, end):
    return GpuInterval(gpu, start * 1_000_000, end * 1_000_000)


def test_union_overlap_nested_adjacent_duplicates_and_independent_gpus():
    workers = [interval(4, 0, 10), interval(4, 2, 3), interval(4, 0, 10), interval(4, 10, 20),
               interval(6, 0, 10)]
    reservations = [interval(4, 5, 25), interval(4, 6, 7), interval(4, 5, 25),
                    interval(6, 10, 15)]
    report = interval_accounting(workers, reservations)
    observed = {key: item["gpu_seconds"] for key, item in report["totals"].items()}
    assert observed == {"worker_union": 30, "reservation_union": 25,
                        "worker_reservation_overlap": 15, "combined_union": 40,
                        "reservation_only": 10}
    assert len(report["per_gpu"][0]["worker_union"]["intervals"]) == 1
    assert report["per_gpu"][1]["worker_reservation_overlap"]["intervals"] == []


def test_empty_and_zero_duration_have_no_coverage():
    for workers in ([], [interval(4, 1, 1)]):
        assert all(item["gpu_seconds"] == 0
                   for item in interval_accounting(workers, [])["totals"].values())


@pytest.mark.parametrize("gpu,start,end", [(-1, 0, 1), (True, 0, 1), (4, 2, 1), (4, 0.5, 1)])
def test_invalid_interval_rejected(gpu, start, end):
    with pytest.raises(ValueError):
        GpuInterval(gpu, start, end)


@pytest.mark.parametrize("value", [None, 4, "nonsense", "2026-10-04T13:59:00"])
def test_invalid_or_timezone_missing_timestamp_rejected(value):
    with pytest.raises(ValueError):
        timestamp_us(value)


def test_timezone_normalization_is_exact():
    assert timestamp_us("2026-10-04T13:59:00.123456+08:00") == timestamp_us(
        "2026-10-04T05:59:00.123456+00:00"
    )


def test_missing_ready_is_unknown_failed_ready_is_counted_and_old_worker_cost_separate():
    start, end = "2026-10-04T13:59:00+08:00", "2026-10-04T13:59:10+08:00"
    costs = {
        "attempts": [{"gpu": 4, "worker_assigned_at_bjt": start, "worker_ended_at_bjt": end}],
        "reservations": [{"directory": "fixture", "attempts": [
            {"gpu": 4, "status": "failed", "allocation_ready_at_bjt": None,
             "ended_at_bjt": end, "child_body_wall_seconds": 0.4},
            {"gpu": 4, "status": "failed", "allocation_ready_at_bjt": start,
             "ended_at_bjt": end},
        ]}],
        "totals": {"unique_worker_gpu_seconds": 10.000001,
                   "unique_worker_gpu_hours": 10.000001 / 3600},
        "cost_definition": "fixture worker lifetime",
    }
    report = build_report(costs)
    assert report["totals"]["combined_union"]["gpu_seconds"] == 10
    assert report["totals"]["reservation_only"]["gpu_seconds"] == 0
    assert report["reservation_interval_count"] == 1
    assert report["excluded_reservations"][0]["recorded_occupancy_gpu_seconds"] is None
    assert report["historical_worker_cost_separate"]["gpu_seconds"] == 10.000001
    costs["reservations"][0]["attempts"][1]["ended_at_bjt"] = "2026-10-04T13:58:59+08:00"
    with pytest.raises(ValueError, match="negative"):
        build_report(costs)
