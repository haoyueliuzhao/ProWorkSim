"""Unchanged v131 model/runtime with bounded preparation-only audit hashing."""
from . import software_fixed_organization_runtime_v131 as previous
from .software_fixed_organization_world_v132 import prepare_case as prepare_case

MEMORY_REVISION = "v132-preparation-audit-hash-streaming-r1"


def __getattr__(name):
    return getattr(previous, name)
