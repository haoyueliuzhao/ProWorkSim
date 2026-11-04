"""Original REF runtime with only the source-bound rejected-history repair.

Preparation copies pinned local SDK files and runs an offline import probe.
No API, repository test, container, model, or shared-server change is performed.
"""
from __future__ import annotations

from types import FunctionType

from . import software_benchmark_sdk_bundle_v110 as original
from . import software_benchmark_sdk_bundle_v066 as packaging
from .software_benchmark_runtime_inputs_v110 import (
    controller_inputs as controller_inputs, actor_inputs as actor_inputs,
)

VERSION = 'v126-original-ref-rejected-history-offline-bundle-r1'
OUTPUT = packaging.ROOT/'runs/software-benchmark-v126/sdk-bundle-r1'
NEW_MODULES = ('software_benchmark_rejected_history_v114.py',)
NEW_TOOLS = ('run_ref_controller_v126.py',)
ALIASES = {**original.ALIASES, 'controller.py': 'run_ref_controller_v126.py'}


def probe_source():
    source = original.probe_source()
    source = source.replace('    entrypoints.append(name)', '''    entrypoints.append(name)
    if name == "controller.py":
        assert "create_ref_conversation" in module.create_conversation.__code__.co_names
from proworksim.software_benchmark_rejected_history_v114 import VERSION as REJECTED_HISTORY_VERSION
assert REJECTED_HISTORY_VERSION == "v114-native-source-bound-rejected-tool-history-r1"''')
    source = source.replace('"real_SDK_scripted_factory_controls_are_separate": True',
        '"real_SDK_scripted_factory_controls_are_separate": True, '
        '"native_rejected_history_revision": REJECTED_HISTORY_VERSION, '
        '"original_v110_model_visible_strategy_retained": True')
    return source


# Rebind only the ordinary local file-packaging function to explicit new files.
_namespace = {**original._namespace, '__file__': __file__, 'VERSION': VERSION, 'OUTPUT': OUTPUT,
    'PROJECT_MODULES': tuple(sorted(set(original._namespace['PROJECT_MODULES']) | set(NEW_MODULES))),
    'TOOLS': tuple(dict.fromkeys((*original._namespace['TOOLS'], *NEW_TOOLS))),
    'ENTRYPOINT_ALIASES': ALIASES, 'probe_source': probe_source}
prepare_bundle = FunctionType(packaging.prepare_bundle.__code__, _namespace,
    'prepare_bundle', packaging.prepare_bundle.__defaults__)
runtime_environment = packaging.runtime_environment
python_argv = packaging.python_argv
