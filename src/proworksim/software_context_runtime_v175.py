"""Explicit future-runtime bindings; no mutation of archived controller modules.

P1 replays execute no World actions. A later full-task deployment must call these
bindings and include the returned public files in its own immutable bundle.
"""
from pathlib import Path
from types import FunctionType, SimpleNamespace

from . import software_benchmark_managed_actor_v141 as actor_original
from . import software_benchmark_public_test_evidence_v175 as evidence
from .software_benchmark_delivery_reuse_v175 import bind_grading

ROOT=Path(__file__).resolve().parents[2]
VERSION='v175-public-entry-and-own-score-bindings-r1'
PUBLIC_FILES={
    'public-test-library.py':ROOT/'tools/public_test_library_v175.py',
    'public-test.py':ROOT/'tools/run_public_tests_v175.py',
    'public-test-dependencies.py':ROOT/'tools/public_test_dependencies_v130.py',
    'public-test-execution.py':ROOT/'tools/public_test_execution_v175.py',
    'public-test-evidence.py':ROOT/'tools/public_test_evidence_v175.py',
}


def managed_actor():
    """New actor namespace with the actual execute entry using the repaired helper."""
    original=actor_original.ManagedOperationSession.execute
    namespace={**original.__globals__,'run_public_entry':evidence.run_public_entry}
    execute=FunctionType(original.__code__,namespace,original.__name__,
                         original.__defaults__,original.__closure__)
    class ManagedOperationSession(actor_original.ManagedOperationSession):
        pass
    ManagedOperationSession.execute=execute
    module=SimpleNamespace(**vars(actor_original))
    module.ManagedOperationSession=ManagedOperationSession
    module.run_public_entry=evidence.run_public_entry
    module.deployment_revision=VERSION
    return module


def public_file_bindings():
    from .software_benchmark_candidates_v054 import reference
    return {target:reference(source) for target,source in PUBLIC_FILES.items()}


def grading(grader):
    return bind_grading(grader)
