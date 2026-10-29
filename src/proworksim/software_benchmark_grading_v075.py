"""Use v075 aggregate admission while preserving official v068 scoring code."""
from __future__ import annotations

from types import ModuleType

from . import software_benchmark_grading_recovery_v068 as recovery
from . import software_benchmark_resources_v075 as resources
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = "v075-consistent-resource-grading-r1"


def factory(guard, *, authorization_ref=None, primary_policy=None):
    primary_policy = primary_policy or resources.policy(guard, authorization_ref=authorization_ref)
    namespace = clone_namespace(recovery.original_grading(), policy=primary_policy)
    base = ModuleType(__name__ + ".private_original_grading")
    base.__dict__.update(namespace)

    def authorize(operation="v068.run", **identity):
        return guard("v075.run", **identity)

    # RecoveryGrading.run_request clones this base once more only to redirect
    # the child scorer to the existing v068 TLS lifecycle. The captured policy
    # remains v075. The child consumes this exact already acquired capacity;
    # it does not run another aggregate reservation decision.
    return recovery.RecoveryGrading(guard=authorize, base=base,
        releaser=primary_policy.release_resource,
        proof_root=resources.original.ROOT / "artifacts/software-benchmark-v075/physical-cleanup-r1")
