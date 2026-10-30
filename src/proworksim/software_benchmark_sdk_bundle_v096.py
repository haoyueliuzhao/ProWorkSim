"""Fresh local bundle for zero-generation continuations; no old bundle edits."""
from __future__ import annotations

from . import software_benchmark_sdk_bundle_v066 as original
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = 'v096-local-S1-bugfix-bundle-r1'
OUTPUT = original.ROOT/'runs/software-benchmark-v096/sdk-bundle-r1'
NEW_MODULES = ('software_benchmark_managed_actor_v096.py',
    'software_benchmark_managed_v096.py', 'software_benchmark_managed_sync_v095.py',
    'software_benchmark_nullable_cursor_v090.py')
NEW_TOOLS = ('run_project_controller_v096.py', 'run_managed_worker_docker_v096.py')
_namespace = clone_namespace(original, VERSION=VERSION, OUTPUT=OUTPUT, __file__=__file__,
    PROJECT_MODULES=tuple(sorted(set(original.PROJECT_MODULES)|set(NEW_MODULES))),
    TOOLS=original.TOOLS+NEW_TOOLS,
    ENTRYPOINT_ALIASES={**original.ENTRYPOINT_ALIASES,
        'managed-worker.py': 'run_managed_worker_docker_v096.py',
        'project-controller.py': 'run_project_controller_v096.py'})


def probe_source():
    value = original.probe_source()
    value = value.replace('tool_module("run_project_controller_v066")',
                          'tool_module("run_project_controller_v096")')
    value = value.replace('tool_module("run_managed_worker_docker_v066")',
                          'tool_module("run_managed_worker_docker_v096")')
    value = value.replace('from proworksim.software_benchmark_managed_v064 import worker_type',
                          'from proworksim.software_benchmark_managed_v096 import worker_type')
    value = value.replace('from proworksim.software_benchmark_managed_actor_v064 import validate_public_entry',
                          'from proworksim.software_benchmark_managed_actor_v096 import validate_public_entry')
    marker = 'loaded = []\n'
    extra = '''from proworksim.software_benchmark_world_v054 import TOOLS as public_tools
from proworksim.software_benchmark_nullable_cursor_v090 import CURSOR_TOOLS
from proworksim import software_benchmark_managed_actor_v096 as repaired_actor
actor_entry = tool_module("run_managed_worker_docker_v096")
assert actor_entry.managed is repaired_actor
assert repaired_actor.synchronize_tree.__module__ == "proworksim.software_benchmark_managed_sync_v095"
class UnusedTransport:
    def complete(self, *args, **kwargs):
        raise AssertionError("No completion in managed constructor control")
cfg = {"model": "cpu-fixture-not-a-model", "api_key_env": None,
       "base_url": "http://127.0.0.1", "backend_id": "explicit_test_fixture",
       "retry": {"max_attempts": 1, "backoff_seconds": []}, "budget": {"max_cost_usd": 50},
       "weight_identity": {"step": 0, "policy_version": "fixture-policy-0"},
       "model_revision": "fixture-policy-0"}
defs = [row for row in public_tools if row["name"] in CURSOR_TOOLS]
w = managed_class("member_001", defs, cfg, UnusedTransport(),
                  lambda *a, **k: (_ for _ in ()).throw(AssertionError("No world action")),
                  directory=output / "managed-constructor-control")
assert set(w._nullable_cursor_v090["tools"]) == set(CURSOR_TOOLS)
assert w.meter["decisions"] == 0
w.close()
'''
    if value.count(marker) != 1:
        raise ValueError('Original bundle probe boundary changed')
    value = value.replace(marker, extra + marker)
    return value


_namespace['probe_source'] = probe_source
prepare_bundle = _namespace['prepare_bundle']
runtime_environment = _namespace['runtime_environment']
python_argv = _namespace['python_argv']
controller_inputs = _namespace['controller_inputs']
