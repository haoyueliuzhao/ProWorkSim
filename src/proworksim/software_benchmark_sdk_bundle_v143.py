"""New immutable actor deployment; frozen v141 model-visible execution stays intact."""
from __future__ import annotations

import json
from types import FunctionType

from . import software_benchmark_sdk_bundle_v141 as previous
from .software_benchmark_runtime_inputs_v141 import (
    actor_inputs as actor_inputs, controller_inputs as controller_inputs,
)
from .software_benchmark_content_tokenizer_v141 import descriptor
from .storage import atomic_write, json_bytes

VERSION = 'v143-native-actor-v141-result-aligned-bundle-r1'
OUTPUT = previous.packaging.ROOT/'runs/software-benchmark-v143/sdk-bundle-r1'
NEW_MODULES = ('software_benchmark_managed_actor_v143.py',)
NEW_TOOLS = ('run_native_worker_docker_v143.py', 'run_managed_worker_docker_v143.py')
ALIASES = {**previous.ALIASES, 'worker.py':'run_native_worker_docker_v143.py',
           'managed-worker.py':'run_managed_worker_docker_v143.py'}


def probe_source():
    source = previous.probe_source().replace('software_benchmark_managed_actor_v141',
                                            'software_benchmark_managed_actor_v143')
    source = source.replace('    entrypoints.append(name)', '''    if name == "worker.py":
        assert module.DEPLOYMENT_VERSION == managed_actor.DEPLOYMENT_VERSION
        assert module.RESULT_REVISION == managed_actor.RESULT_REVISION
        assert module._original_validate is module._legacy.validate_config
        assert module._original_seal is module._legacy.seal_actor
    if name == "managed-worker.py":
        assert module.managed.DEPLOYMENT_VERSION == managed_actor.DEPLOYMENT_VERSION
    entrypoints.append(name)''')
    source = source.replace('"role_schemas_match_new_contract": True,',
        '"role_schemas_match_new_contract": True, "native_managed_result_binding_matches": True,')
    return source


_namespace = {**previous._namespace, '__file__':__file__, 'VERSION':VERSION, 'OUTPUT':OUTPUT,
    'PROJECT_MODULES':tuple(sorted(set(previous._namespace['PROJECT_MODULES'])|set(NEW_MODULES))),
    'TOOLS':tuple(dict.fromkeys((*previous._namespace['TOOLS'], *NEW_TOOLS))),
    'ENTRYPOINT_ALIASES':ALIASES, 'probe_source':probe_source}
_prepare = FunctionType(previous._prepare_bundle.__code__, _namespace,
    previous._prepare_bundle.__name__, previous._prepare_bundle.__defaults__, previous._prepare_bundle.__closure__)


def prepare_bundle():
    result = _prepare()
    expected = descriptor()
    path = OUTPUT/'manifest.json'
    saved = json.loads(path.read_bytes())
    if 'content_tokenizer' in saved and saved['content_tokenizer'] != expected:
        raise ValueError('The new deployment cannot change the frozen content tokenizer')
    if 'content_tokenizer' not in saved:
        result.update(content_tokenizer=expected,
            deployment_only_revision='v143-private-actor-v141-result-binding-r1',
            model_visible_contract_unchanged=True,
            previous_bundle_deployment_failure_preserved=True)
        atomic_write(path,json_bytes(result))
    return result


runtime_environment = previous.runtime_environment
python_argv = previous.python_argv
