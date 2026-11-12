"""Server device admission with the unchanged r3/r5 reusable-cache controls."""
from __future__ import annotations

from functools import lru_cache
import importlib.util
import json
import os
from pathlib import Path
import sys

VERSION = "software-panel-resources-v053-v1"
ROOT = Path(__file__).resolve().parents[2]
RESOURCE_ROOT = ROOT / "artifacts/software-learning-v050/resume-r6-source/scripts"
MINIMUM_FREE_MIB = 46080
MAX_RESIDENTS = 4


@lru_cache(maxsize=1)
def modules():
    loaded = []
    for name in ("software_learning_resources_v050r3", "software_learning_resources_v050r5"):
        source = RESOURCE_ROOT / (name + ".py")
        qualified_name = "scripts." + name
        existing = sys.modules.get(qualified_name)
        if existing is not None:
            if Path(existing.__file__).resolve() != source.resolve():
                raise RuntimeError(f"Conflicting frozen resource module: {qualified_name}")
            loaded.append(existing)
            continue
        spec = importlib.util.spec_from_file_location(qualified_name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[qualified_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[qualified_name]
            raise
        loaded.append(module)
    return tuple(loaded)


def select_cards(rows, *, excluded=()):
    """Shared A100/A800 80-GiB devices; actual free capacity, no idle gate."""
    cards = []
    seen = set()
    for row in rows:
        index = int(row["index"])
        if index in seen:
            raise ValueError("Duplicate physical GPU observation")
        seen.add(index)
        free, total = int(row["free_mib"]), int(row["total_mib"])
        if not 0 <= free <= total or not row["uuid"].startswith("GPU-"):
            raise ValueError("Invalid observed GPU capacity or identity")
        if (index in range(8) and index not in excluded and total >= 81920
                and any(model in row["name"] for model in ("A100", "A800"))
                and free >= MINIMUM_FREE_MIB):
            cards.append(dict(row, index=index, free_mib=free, total_mib=total))
    return sorted(cards, key=lambda row: (-row["free_mib"], row["index"]))


def binding_for(card):
    r3, _ = modules()
    return r3.launch_target(card)


def validate_worker_binding(binding):
    r3, _ = modules()
    binding = r3.validate_binding(binding)
    if (os.environ.get("CUDA_VISIBLE_DEVICES") != binding["gpu_uuid"]
            or os.environ.get("PROWORKSIM_HOST_GPU_DEVICES") != str(binding["gpu_index"])):
        raise ValueError("Worker namespace UUID/physical GPU does not match its reservation")
    if os.environ.get("PYTORCH_CUDA_ALLOC_CONF") != "backend:native":
        raise ValueError("The reusable-cache protocol requires the native allocator")
    return binding


def acquire_startup(output, binding, *, identity):
    _, r5 = modules()
    return r5.acquire_startup_cache(output, validate_worker_binding(binding), identity=identity)


def native_context(owner, output, binding):
    r3, _ = modules()
    return r3.native_cache_context(owner, output, validate_worker_binding(binding))


def binding_from_environment():
    return validate_worker_binding(json.loads(os.environ["PROWORKSIM_V053_GPU_BINDING"]))


def is_preload_resource_wait(error):
    _, r5 = modules()
    return isinstance(error, r5.StartupResourceUnavailable) and error.receipt.get("retryable") is True
