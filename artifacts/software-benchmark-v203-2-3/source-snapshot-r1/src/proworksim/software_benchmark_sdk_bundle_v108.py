"""Same v106 execution bundle, with the exact REF budget-closure import repaired."""
from __future__ import annotations

from . import software_benchmark_sdk_bundle_v066 as original
from . import software_benchmark_sdk_bundle_v106 as previous
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = 'v108-unchanged-v106-tools-ref-budget-closure-bundle-r1'
OUTPUT = original.ROOT / 'runs/software-benchmark-v108/sdk-bundle-r1'
NEW_MODULES = (*previous.NEW_MODULES, 'software_benchmark_normal_boundary_v108.py')
NEW_TOOLS = (*previous.NEW_TOOLS, 'run_ref_controller_v108.py')
_namespace = clone_namespace(original, VERSION=VERSION, OUTPUT=OUTPUT, __file__=__file__,
    PROJECT_MODULES=tuple(sorted(set(original.PROJECT_MODULES) | set(NEW_MODULES))),
    TOOLS=original.TOOLS + NEW_TOOLS,
    ENTRYPOINT_ALIASES={**original.ENTRYPOINT_ALIASES,
        'managed-worker.py': 'run_managed_worker_docker_v106.py',
        'controller.py': 'run_ref_controller_v108.py',
        'project-controller.py': 'run_project_controller_v106.py'})


def probe_source():
    source = previous.probe_source()
    old, new = 'tool_module("run_ref_controller_v105")', 'tool_module("run_ref_controller_v108")'
    if source.count(old) != 1:
        raise ValueError('The one native factory bundle probe changed')
    source = source.replace(old, new)
    marker = 'from proworksim.software_benchmark_normal_boundary_v064 import GuardedModelAdapter'
    if source.count(marker) != 1:
        raise ValueError('The original boundary import probe changed')
    return source.replace(marker,
        'from proworksim.software_benchmark_normal_boundary_v108 import GuardedModelAdapter, unwrap_normal_boundary')


_namespace['probe_source'] = probe_source
prepare_bundle = _namespace['prepare_bundle']
runtime_environment = _namespace['runtime_environment']
python_argv = _namespace['python_argv']
controller_inputs = previous.controller_inputs
