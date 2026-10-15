"""Finite CPU-only resource contracts; the fake allocator never imports CUDA."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import software_learning_resources_v050r3 as resource


def sample(free=60000, processes="", *, uuid="GPU-4"):
    return {"gpus": {"returncode": 0,
        "stdout": f"4, {uuid}, NVIDIA A100-SXM4-80GB, {free}, 81920, 70\n"},
        "processes": {"returncode": 0, "stdout": processes}}


def binding(free=46080):
    return resource.launch_target({"index": 4, "uuid": "GPU-4", "free_mib": free})


class FakeCuda:
    class OutOfMemoryError(RuntimeError):
        pass

    def __init__(self):
        self.allocated = self.reserved = 0
        self.peak_allocated = self.peak_reserved = 0
        self.total = 81920 * resource.MIB
        self.foreign = 0

    def mem_get_info(self):
        return self.total - self.foreign - self.reserved, self.total

    def memory_allocated(self):
        return self.allocated

    def memory_reserved(self):
        return self.reserved

    def max_memory_allocated(self):
        return self.peak_allocated

    def max_memory_reserved(self):
        return self.peak_reserved

    def reset_peak_memory_stats(self):
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

    def __init__(self, failures=0):
        self.cuda = FakeCuda()
        self.failures, self.calls = failures, 0
        self.rng = "unchanged"

    def empty(self, shape, *, dtype, device):
        assert dtype == self.uint8 and device == "cuda"
        self.calls += 1
        if self.failures:
            self.failures -= 1
            raise self.cuda.OutOfMemoryError("synthetic startup race")
        if self.cuda.allocated + shape[0] > self.cuda.total - self.cuda.foreign:
            raise self.cuda.OutOfMemoryError("fake capacity")
        return FakeTensor(self.cuda, shape[0])


@pytest.mark.parametrize("free,expected", [(46080, 45056), (61419, 60395), (81920, 73728)])
def test_target_is_frozen_from_launch_capacity(free, expected):
    target = binding(free)
    assert target["target_mib"] == expected
    target["target_mib"] -= 1
    with pytest.raises(ValueError, match="target changed"):
        resource.validate_binding(target)


@pytest.mark.parametrize("free", [46079, float("nan"), float("inf"), True])
def test_bad_or_insufficient_target_rejected(free):
    with pytest.raises(ValueError):
        binding(free)


def test_admission_accepts_shared_busy_card_and_excludes_live_qplus():
    plan = {"gpu_preference": list(range(8))}
    measured = sample(processes="GPU-4, 80, 18000, foreign-python\n")
    assert resource.available_cards(plan, measured)[0]["shared"] is True
    assert resource.available_cards(plan, measured, excluded=[4]) == []
    assert resource.available_cards(plan, sample(free=46079)) == []
    measured["processes"]["returncode"] = 1
    assert resource.available_cards(plan, measured) == []
    assert resource.LIMITS_OVERRIDES["max_parallel_model_instances"] is None
    assert resource.LIMITS_OVERRIDES["own_gpu_memory_mib"] is None
    assert resource.LIMITS_OVERRIDES["minimum_live_free_gpu_mib"] == 0


def test_environment_pins_reusable_native_allocator_and_sole_device():
    env = resource.worker_env({"CUDA_VISIBLE_DEVICES": "4", "OTHER": "keep",
        "PYTORCH_CUDA_ALLOC_CONF": "max_split_size_mb:128",
        "PYTORCH_NO_CUDA_MEMORY_CACHING": "1"}, binding())
    assert env["OTHER"] == "keep"
    assert env["PYTORCH_CUDA_ALLOC_CONF"] == env["PYTORCH_ALLOC_CONF"] == "backend:native"
    assert "PYTORCH_NO_CUDA_MEMORY_CACHING" not in env
    assert resource.binding_from_env(env) == binding()
    with pytest.raises(ValueError, match="sole worker GPU"):
        resource.worker_env({"CUDA_VISIBLE_DEVICES": "2"}, binding())


def test_preload_adds_only_exact_owned_capacity_without_mutating_sample():
    plan = {"gpu_preference": list(range(8))}
    measured = sample(free=200, processes="GPU-4, 90, 45300, worker\nGPU-4, 91, 30000, foreign\n")
    actual = resource.preload_cards(plan, measured, binding=binding(), worker_pid=90)
    assert actual[0]["free_mib"] == 200
    assert actual[0]["effective_own_capacity_mib"] == 45500
    assert measured["gpus"]["stdout"].split(", ")[3] == "200"
    assert resource.preload_cards(plan, measured, binding=binding(), worker_pid=91) == []
    assert resource.preload_cards(plan, measured, binding=binding(), worker_pid=92) == []
    assert resource.preload_cards(plan, sample(free=200, uuid="wrong"), binding=binding(), worker_pid=90) == []


def test_startup_race_retries_only_reservation_and_releases_every_tensor(tmp_path):
    torch, sleeps = FakeTorch(failures=1), []
    receipt = resource.reserve_before_load(tmp_path, binding(), torch=torch, sleep=sleeps.append)
    assert receipt["allocation_attempts"] == 2
    assert receipt["new_model_calls"] == receipt["live_reservation_tensors"] == 0
    assert sleeps == [5]
    assert torch.cuda.allocated == 0
    assert torch.cuda.reserved == binding()["target_mib"] * resource.MIB
    assert receipt["startup_peak_allocated_bytes"] == torch.cuda.reserved
    assert torch.cuda.max_memory_allocated() == 0
    assert torch.rng == "unchanged"
    assert '"preload_allocation_race"' in (tmp_path / "native-cache-resources.jsonl").read_text()


def test_capacity_wait_does_not_attempt_allocation(tmp_path):
    torch = FakeTorch()
    torch.cuda.foreign = 50000 * resource.MIB

    def free_capacity(seconds):
        assert seconds == 5 and torch.calls == 0
        torch.cuda.foreign = 0

    receipt = resource.reserve_before_load(tmp_path, binding(), torch=torch, sleep=free_capacity)
    assert receipt["allocation_attempts"] == 1


def test_refill_has_no_live_ballast_and_preserves_existing_model_storage():
    torch = FakeTorch()
    model = FakeTensor(torch.cuda, 20000 * resource.MIB)
    resource.fill_cache(torch, 45056 * resource.MIB)
    assert torch.cuda.allocated == model.size
    assert torch.cuda.reserved >= 45056 * resource.MIB
    del model
    assert torch.cuda.allocated == 0


def test_native_boundary_preserves_arguments_identity_call_count_and_overrides(tmp_path):
    torch = FakeTorch()
    output, calls = object(), []

    def native(*args, **kwargs):
        assert torch.cuda.allocated == 0
        calls.append((args, kwargs))
        return output

    owner = SimpleNamespace(torch=torch, learning_logprobs=native, _generate_tokens=native)
    with resource.native_cache_context(owner, tmp_path, binding()):
        assert owner.learning_logprobs("trace", flag=True) is output
        assert owner._generate_tokens("prompt") is output
    assert calls == [(("trace",), {"flag": True}), (("prompt",), {})]
    assert owner.learning_logprobs is native and owner._generate_tokens is native
    assert torch.calls == 1 and torch.rng == "unchanged"


def test_postload_refill_oom_and_actual_native_oom_never_retry(tmp_path):
    torch, calls = FakeTorch(failures=1), []
    owner = SimpleNamespace(torch=torch, learning_logprobs=lambda: calls.append(1))
    with pytest.raises(FakeCuda.OutOfMemoryError):
        with resource.native_cache_context(owner, tmp_path, binding()):
            pytest.fail("Postload OOM must not reach a native call")
    assert calls == [] and torch.calls == 1 and torch.cuda.allocated == 0

    def native():
        calls.append(1)
        raise FakeCuda.OutOfMemoryError("actual model OOM")

    owner.learning_logprobs = native
    with pytest.raises(FakeCuda.OutOfMemoryError, match="actual model OOM"):
        with resource.native_cache_context(owner, tmp_path, binding()):
            owner.learning_logprobs()
    assert calls == [1] and owner.learning_logprobs is native


def test_resource_helpers_contain_no_explicit_cache_release():
    source = Path(resource.__file__).read_text()
    assert ".empty_cache(" not in source
    assert ".manual_seed(" not in source
    assert ".synchronize(" not in source
