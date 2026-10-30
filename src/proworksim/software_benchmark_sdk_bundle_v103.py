"""Explicit future bundle selection; never starts or resumes an experiment."""
from __future__ import annotations

from . import software_benchmark_sdk_bundle_v066 as original
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = 'v103-managed-interface-budget-bundle-r1'
OUTPUT = original.ROOT / 'runs/software-benchmark-v103/sdk-bundle-r1'
NEW_MODULES = (
    'software_benchmark_managed_actor_v103.py', 'software_benchmark_managed_v103.py',
    'software_benchmark_managed_v096.py', 'software_benchmark_managed_sync_v095.py',
    'software_benchmark_nullable_cursor_v090.py', 'software_benchmark_budget_closure_v103.py',
)
NEW_TOOLS = ('run_project_controller_v103.py', 'run_managed_worker_docker_v103.py')
_namespace = clone_namespace(original, VERSION=VERSION, OUTPUT=OUTPUT, __file__=__file__,
    PROJECT_MODULES=tuple(sorted(set(original.PROJECT_MODULES) | set(NEW_MODULES))),
    TOOLS=original.TOOLS + NEW_TOOLS,
    ENTRYPOINT_ALIASES={**original.ENTRYPOINT_ALIASES,
        'managed-worker.py': 'run_managed_worker_docker_v103.py',
        'project-controller.py': 'run_project_controller_v103.py'})


def probe_source():
    value = original.probe_source()
    for before, after in (
        ('tool_module("run_project_controller_v066")', 'tool_module("run_project_controller_v103")'),
        ('tool_module("run_managed_worker_docker_v066")', 'tool_module("run_managed_worker_docker_v103")'),
        ('from proworksim.software_benchmark_managed_v064 import worker_type',
         'from proworksim.software_benchmark_managed_v103 import worker_type'),
        ('from proworksim.software_benchmark_managed_actor_v064 import validate_public_entry',
         'from proworksim.software_benchmark_managed_actor_v103 import validate_public_entry'),
    ):
        if before not in value:
            raise ValueError('Original bundle probe boundary changed: ' + before)
        value = value.replace(before, after)
    return value


_namespace['probe_source'] = probe_source
prepare_bundle = _namespace['prepare_bundle']
runtime_environment = _namespace['runtime_environment']
python_argv = _namespace['python_argv']
controller_inputs = _namespace['controller_inputs']
