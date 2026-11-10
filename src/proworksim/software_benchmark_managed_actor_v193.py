"""Same S1 public interface, using the verified v175 pytest-loading repair."""
from types import FunctionType
from . import software_benchmark_managed_actor_v141 as original
from .software_benchmark_public_test_evidence_v175 import run_public_entry as repaired_public_entry

globals().update({k:v for k,v in vars(original).items() if not k.startswith('__') and k not in {'previous','original'}})
DEPLOYMENT_VERSION='v193-private-actor-v175-public-tests-r1'
_execute=original.ManagedOperationSession.execute
_namespace={**_execute.__globals__,'run_public_entry':repaired_public_entry}


class ManagedOperationSession(original.ManagedOperationSession):
    execute=FunctionType(_execute.__code__,_namespace,_execute.__name__,_execute.__defaults__,_execute.__closure__)


run_public_entry=repaired_public_entry
