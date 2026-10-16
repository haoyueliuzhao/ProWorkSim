"""Finite CPU-only startup races; no real torch, device, model or allocator."""
import copy
import json
import os

import pytest

from scripts import software_learning_resources_v050r5 as resource

MIB = resource.prior.MIB
IDENTITY = {"worker": "update-Q_minus", "run_root": "/frozen/run", "source": {"head": "frozen"}}


def binding():
    return resource.prior.launch_target({"index": 3, "uuid": "GPU-3", "free_mib": 46080})


class FakeCuda:
    class OutOfMemoryError(RuntimeError):
        pass

    def __init__(self):
        self.allocated = self.reserved = self.peak_allocated = self.peak_reserved = 0
        self.foreign = 0
        self.total = 81920 * MIB
        self.error = None
        self.snapshot_calls = 0
        self.error_on_snapshot = None
        self.failed = False
        self.reset_calls = 0

    def check(self):
        assert not self.failed, "CUDA must not be called again after an error"

    def mem_get_info(self):
        self.check()
        self.snapshot_calls += 1
        if self.error_on_snapshot == self.snapshot_calls:
            self.failed = True
            raise self.error
        return self.total - self.foreign - self.reserved, self.total

    def memory_allocated(self):
        self.check()
        return self.allocated

    def memory_reserved(self):
        self.check()
        return self.reserved

    def max_memory_allocated(self):
        self.check()
        return self.peak_allocated

    def max_memory_reserved(self):
        self.check()
        return self.peak_reserved

    def reset_peak_memory_stats(self):
        self.check()
        self.reset_calls += 1
        self.peak_allocated, self.peak_reserved = self.allocated, self.reserved


class FakeTensor:
    def __init__(self, cuda, size):
        self.cuda, self.size = cuda, size
        cuda.allocated += size
        cuda.reserved = max(cuda.reserved, cuda.allocated)
        cuda.peak_allocated = max(cuda.peak_allocated, cuda.allocated)
        cuda.peak_reserved = max(cuda.peak_reserved, cuda.reserved)

    def __del__(self):
        self.cuda.allocated -= self.size


class FakeTorch:
    uint8 = "uint8"

    def __init__(self):
        self.cuda = FakeCuda()
        self.allocation_calls = self.model_calls = self.backward_calls = 0
        self.error_on_allocation = None
        self.rng = "untouched"

    def empty(self, shape, *, dtype, device):
        self.cuda.check()
        assert (dtype, device) == (self.uint8, "cuda")
        self.allocation_calls += 1
        if self.error_on_allocation == self.allocation_calls:
            self.cuda.failed = True
            raise self.cuda.error
        return FakeTensor(self.cuda, shape[0])


def receipt(output):
    return json.loads((output / resource.RECEIPT).read_text())


@pytest.mark.parametrize("error", [
    RuntimeError("CUDA error: out of memory\nCUDA kernel errors might be asynchronously reported"),
    RuntimeError("CUDA out of memory. Tried to allocate 44.00 GiB"),
    FakeCuda.OutOfMemoryError("typed allocation unavailable"),
])
def test_first_cuda_snapshot_oom_becomes_recorded_pending_without_second_cuda_call(tmp_path, error):
    torch = FakeTorch()
    torch.cuda.error, torch.cuda.error_on_snapshot = error, 1
    startup = tmp_path / "startup"
    with pytest.raises(resource.StartupResourceUnavailable) as captured:
        resource.acquire_startup_cache(startup, binding(), torch=torch, identity=IDENTITY)
    record = receipt(startup)
    assert captured.value.receipt == record
    assert record["error"] == {"type": type(error).__name__, "message": str(error)}
    assert record["phase"] == "cuda_capacity_snapshot"
    assert record["status"] == "resource_unavailable" and record["retryable"] is True
    assert record["loader_not_entered"] is True and record["restart_requires_fresh_process"] is True
    assert record["new_model_calls"] == record["new_backward_calls"] == record["new_optimizer_steps"] == 0
    assert record["allocation_attempts"] == torch.allocation_calls == 0
    assert record["pid"] == os.getpid() and record["binding"] == binding() and record["identity"] == IDENTITY
    assert torch.cuda.snapshot_calls == 1 and torch.cuda.reset_calls == 0
    assert not (tmp_path / "actual").exists() and not (startup / "cache-reservation.json").exists()


def test_capacity_lost_after_dispatch_returns_once_without_wait_or_allocation(tmp_path):
    torch = FakeTorch()
    torch.cuda.foreign = 74218 * MIB
    with pytest.raises(resource.StartupResourceUnavailable) as captured:
        resource.acquire_startup_cache(tmp_path / "startup", binding(), torch=torch)
    record = captured.value.receipt
    assert record["reason"] == "frozen_startup_capacity_unavailable"
    assert record["available_capacity_bytes"] < record["required_capacity_bytes"]
    assert record["allocation_attempts"] == torch.allocation_calls == 0
    assert torch.cuda.snapshot_calls == 1


def test_partial_allocation_oom_releases_tensors_and_never_queries_poisoned_context(tmp_path):
    torch = FakeTorch()
    torch.cuda.reserved = 256 * MIB
    torch.cuda.error = FakeCuda.OutOfMemoryError("second allocation lost capacity")
    torch.error_on_allocation = 2
    with pytest.raises(resource.StartupResourceUnavailable) as captured:
        resource.acquire_startup_cache(tmp_path, binding(), torch=torch)
    assert captured.value.receipt["phase"] == "cuda_cache_allocation"
    assert captured.value.receipt["allocation_attempts"] == 1
    assert captured.value.receipt["live_reservation_tensors"] == 0
    assert torch.allocation_calls == 2 and torch.cuda.snapshot_calls == 1
    assert torch.cuda.allocated == 0 and torch.model_calls == torch.backward_calls == 0
    assert torch.rng == "untouched"


def test_postallocation_snapshot_oom_is_still_pre_model_resource_attempt(tmp_path):
    torch = FakeTorch()
    torch.cuda.error = RuntimeError("CUDA error: out of memory")
    torch.cuda.error_on_snapshot = 2
    with pytest.raises(resource.StartupResourceUnavailable) as captured:
        resource.acquire_startup_cache(tmp_path, binding(), torch=torch)
    assert captured.value.receipt["phase"] == "cuda_cache_verification"
    assert torch.cuda.allocated == 0 and torch.allocation_calls == 1
    assert torch.cuda.snapshot_calls == 2 and torch.cuda.reset_calls == 0


@pytest.mark.parametrize("message", [
    "CUDA error: device-side assert triggered", "CUDA error: invalid device ordinal",
    "CPU out of memory", "other subsystem reported CUDA error: out of memory",
    "CUDA error: out of memory or corrupted allocator",
])
def test_non_oom_runtime_fault_is_not_converted_or_retried(tmp_path, message):
    torch = FakeTorch()
    error = RuntimeError(message)
    torch.cuda.error, torch.cuda.error_on_snapshot = error, 1
    with pytest.raises(RuntimeError) as captured:
        resource.acquire_startup_cache(tmp_path, binding(), torch=torch)
    assert captured.value is error
    assert not isinstance(captured.value, resource.StartupResourceUnavailable)
    record = receipt(tmp_path)
    assert record["status"] == "fault" and record["retryable"] is False
    assert record["error"]["message"] == message and torch.cuda.snapshot_calls == 1


def test_success_releases_tensors_resets_peaks_and_reuses_same_cache_without_cuda(tmp_path):
    torch = FakeTorch()
    startup, actual = tmp_path / "startup", tmp_path / "actual"
    ready = resource.acquire_startup_cache(startup, binding(), torch=torch, identity=IDENTITY)
    assert ready == receipt(startup)
    assert ready["status"] == "ready" and ready["retryable"] is False
    assert ready["startup_peak_allocated_bytes"] == binding()["target_mib"] * MIB
    assert torch.cuda.allocated == torch.cuda.peak_allocated == 0
    assert torch.cuda.reserved == binding()["target_mib"] * MIB
    assert torch.cuda.reset_calls == 1 and torch.allocation_calls == 1
    torch.cuda.failed = True  # Transfer must not touch CUDA at all.
    transferred = resource.use_startup_cache(actual, startup, ready, binding(), identity=IDENTITY)
    assert transferred["startup_cache_source"]["path"] == str(startup / "cache-reservation.json")
    assert transferred["same_process_preacquired_cache"] is True
    assert transferred["additional_reservation_attempts"] == 0
    assert ready == receipt(startup) and torch.allocation_calls == 1
    assert torch.model_calls == torch.backward_calls == 0 and torch.rng == "untouched"
    with pytest.raises(FileExistsError):
        resource.use_startup_cache(actual, startup, ready, binding(), identity=IDENTITY)
    with pytest.raises(FileExistsError):
        resource.acquire_startup_cache(startup, binding(), torch=torch, identity=IDENTITY)


@pytest.mark.parametrize("field,value", [("pid", -1), ("identity", {}), ("new_model_calls", 1)])
def test_cache_transfer_rejects_wrong_process_identity_or_side_effects(tmp_path, field, value):
    startup, actual = tmp_path / "startup", tmp_path / "actual"
    ready = resource.acquire_startup_cache(startup, binding(), torch=FakeTorch(), identity=IDENTITY)
    forged = copy.deepcopy(ready)
    forged[field] = value
    # Matching files alone must not waive semantic process/model checks.
    for name in (resource.RECEIPT, "cache-reservation.json"):
        (startup / name).write_text(json.dumps(forged))
    with pytest.raises(ValueError, match="exact ready startup cache"):
        resource.use_startup_cache(actual, startup, forged, binding(), identity=IDENTITY)
    assert not actual.exists()


def test_resource_policy_exactly_reuses_current_unlimited_r3_policy():
    assert resource.RESOURCE_POLICY == resource.prior.RESOURCE_POLICY
    assert resource.LIMITS_OVERRIDES == resource.prior.LIMITS_OVERRIDES
    assert resource.RESOURCE_POLICY["minimum_free_gpu_mib"] == 45 * 1024
    assert resource.RESOURCE_POLICY["max_parallel_model_instances"] is None
    assert resource.RESOURCE_POLICY["own_gpu_memory_mib"] is None
    assert resource.RESOURCE_POLICY["gpu_capacity_stability_seconds"] == 0
    assert resource.RESOURCE_POLICY["minimum_live_free_gpu_mib"] == 0
