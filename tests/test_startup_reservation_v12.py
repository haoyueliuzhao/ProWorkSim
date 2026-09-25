"""Resource-only startup lifecycle with CPU mocks; never allocates a GPU tensor."""

import pytest

from proworksim.local_model_service import load_with_startup_reservation, service_parser
from proworksim.storage import read_json


class FakeCUDA:
    def __init__(self):
        self.allocated = 0
        self.reserved = 0
        self.peak = 0
        self.reserved_peak = 0
        self.calls = []

    def allocate(self, size):
        self.allocated += size
        self.reserved = max(self.reserved, self.allocated)
        self.peak = max(self.peak, self.allocated)
        self.reserved_peak = max(self.reserved_peak, self.reserved)

    def mem_get_info(self):
        return 80 * 1024**3 - self.reserved, 80 * 1024**3

    def memory_allocated(self):
        return self.allocated

    def memory_reserved(self):
        return self.reserved

    def max_memory_allocated(self):
        return self.peak

    def max_memory_reserved(self):
        return self.reserved_peak

    def reset_peak_memory_stats(self):
        self.calls.append("reset_peaks")
        self.peak = self.allocated
        self.reserved_peak = self.reserved

    def empty_cache(self):
        raise AssertionError("Startup must not surrender its allocator cache")


class FakeReservation:
    def __init__(self, cuda, size):
        self.cuda = cuda
        self.size = size
        cuda.allocate(size)

    def __del__(self):
        self.cuda.allocated -= self.size
        self.cuda.calls.append("reservation_released")


class FakeTorch:
    uint8 = "uint8"

    def __init__(self):
        self.cuda = FakeCUDA()

    def empty(self, shape, dtype, device):
        assert dtype == self.uint8 and device == "cuda"
        self.cuda.calls.append(("reserve", shape[0]))
        return FakeReservation(self.cuda, shape[0])


class FakeModel:
    def __init__(self, torch):
        self.torch = torch

    def to(self, device):
        assert device == "cuda" and self.torch.cuda.allocated == 0
        self.torch.cuda.calls.append("weights_to_cuda")
        self.torch.cuda.allocate(256 * 1024)
        return self

    def eval(self):
        return self


def test_reservation_is_held_during_cpu_load_then_reused_and_separate_from_compute_peak(tmp_path):
    torch = FakeTorch()
    path = tmp_path / "startup-resource.json"

    def cpu_loader():
        assert path.exists() and torch.cuda.allocated == 1024**2
        assert read_json(path)["stages"][-1]["stage"] == "reservation_held"
        torch.cuda.calls.append("cpu_load")
        return FakeModel(torch)

    model, record = load_with_startup_reservation(
        cpu_loader, torch=torch, reserve_gib=1 / 1024, record_path=path
    )
    assert isinstance(model, FakeModel) and record["status"] == "ready"
    assert torch.cuda.calls == [
        "reset_peaks",
        ("reserve", 1024**2),
        "cpu_load",
        "reservation_released",
        "weights_to_cuda",
        "reset_peaks",
    ]
    assert record["startup_peak_allocated_bytes"] == 1024**2
    assert record["stages"][-1]["peak_allocated_bytes"] == 256 * 1024
    assert record["stages"][-1]["reserved_bytes"] == 1024**2
    assert record["empty_cache_used"] is False and record["other_processes_controlled"] is False
    assert read_json(path) == record


def test_default_zero_reservation_never_allocates_placeholder(tmp_path):
    torch = FakeTorch()
    _, record = load_with_startup_reservation(
        lambda: FakeModel(torch), torch=torch, reserve_gib=0, record_path=tmp_path / "startup.json"
    )
    assert record["requested_reserve_bytes"] == 0
    assert not any(isinstance(x, tuple) and x[0] == "reserve" for x in torch.cuda.calls)
    assert record["startup_peak_allocated_bytes"] == 256 * 1024


def test_failed_cpu_load_preserves_error_and_releases_only_own_reservation(tmp_path):
    torch = FakeTorch()
    path = tmp_path / "failed-startup.json"

    def fail():
        raise RuntimeError("actual CPU load failure")

    with pytest.raises(RuntimeError, match="actual CPU load failure"):
        load_with_startup_reservation(fail, torch=torch, reserve_gib=1 / 1024, record_path=path)
    assert torch.cuda.allocated == 0 and torch.cuda.reserved == 1024**2
    record = read_json(path)
    assert (
        record["status"] == "startup_error"
        and record["error"]["message"] == "actual CPU load failure"
    )
    assert "weights_to_cuda" not in torch.cuda.calls


def test_adapter_load_is_within_startup_peak_accounting(tmp_path):
    torch = FakeTorch()

    def attach(network):
        torch.cuda.allocate(32 * 1024)
        return network

    _, record = load_with_startup_reservation(
        lambda: FakeModel(torch),
        torch=torch,
        reserve_gib=0,
        record_path=tmp_path / "with-adapter.json",
        on_device=attach,
    )
    assert record["startup_peak_allocated_bytes"] == 288 * 1024
    assert record["stages"][-1]["allocated_bytes"] == 288 * 1024


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "-1", "64.01"])
def test_cli_rejects_nonfinite_or_out_of_range_reservation(value):
    with pytest.raises(SystemExit):
        service_parser().parse_args(
            ["--model", "x", "--revision", "r", "--output", "out", "--startup-reserve-gib=" + value]
        )


def test_cli_reservation_default_and_inclusive_upper_limit():
    parser = service_parser()
    common = ["--model", "x", "--revision", "r", "--output", "out"]
    assert parser.parse_args(common).startup_reserve_gib == 0
    assert parser.parse_args(common + ["--startup-reserve-gib", "34"]).startup_reserve_gib == 34
    assert parser.parse_args(common + ["--startup-reserve-gib", "64"]).startup_reserve_gib == 64


def test_reservation_allocation_failure_is_saved_before_any_weight_loading(tmp_path):
    torch = FakeTorch()

    def refused(*args, **kwargs):
        raise RuntimeError("actual reservation allocation failure")

    torch.empty = refused

    def forbidden_load():
        raise AssertionError("Weights must not load after failed reservation")

    path = tmp_path / "reserve-failed.json"
    with pytest.raises(RuntimeError, match="actual reservation allocation failure"):
        load_with_startup_reservation(forbidden_load, torch=torch, reserve_gib=1, record_path=path)
    record = read_json(path)
    assert record["status"] == "startup_error"
    assert record["error"]["message"] == "actual reservation allocation failure"
    assert torch.cuda.allocated == 0
