"""Independent recovery identity with unchanged actor and model-visible tools."""
from __future__ import annotations

import json
from types import FunctionType

from . import software_benchmark_sdk_bundle_v143 as previous
from .software_benchmark_runtime_inputs_v146 import actor_inputs as actor_inputs, controller_inputs as controller_inputs
from .software_benchmark_content_tokenizer_v141 import descriptor
from .storage import atomic_write, json_bytes

VERSION = 'v146-independent-recovery-offline-bundle-r1'
OUTPUT = previous.previous.packaging.ROOT/'runs/software-benchmark-v146/sdk-bundle-r1'
NEW_MODULES = ('software_benchmark_alignment_contract_v146.py',
               'software_benchmark_runtime_inputs_v146.py')
NEW_TOOLS = ('run_role_baseline_controller_v146.py',)
ALIASES = {**previous.ALIASES, 'controller.py':'run_role_baseline_controller_v146.py',
           'project-controller.py':'run_role_baseline_controller_v146.py'}


def probe_source():
    return ("from proworksim import software_benchmark_alignment_contract_v146 as recovery_contract\n"
            "assert recovery_contract.GROUP_IDS == ('FREE2', 'REVIEW2')\n"
            + previous.probe_source())


_namespace = {**previous._namespace, '__file__':__file__, 'VERSION':VERSION, 'OUTPUT':OUTPUT,
    'PROJECT_MODULES':tuple(sorted(set(previous._namespace['PROJECT_MODULES'])|set(NEW_MODULES))),
    'TOOLS':tuple(dict.fromkeys((*previous._namespace['TOOLS'], *NEW_TOOLS))),
    'ENTRYPOINT_ALIASES':ALIASES, 'probe_source':probe_source}
_prepare = FunctionType(previous._prepare.__code__, _namespace, previous._prepare.__name__,
                        previous._prepare.__defaults__, previous._prepare.__closure__)


def prepare_bundle():
    result = _prepare()
    expected = descriptor()
    path = OUTPUT/'manifest.json'
    saved = json.loads(path.read_bytes())
    if 'content_tokenizer' in saved and saved['content_tokenizer'] != expected:
        raise ValueError('Recovery cannot change the original content tokenizer')
    if 'content_tokenizer' not in saved:
        result.update(content_tokenizer=expected, independent_recovery_identity=True,
                      model_visible_contract_unchanged=True, original_attempts_preserved=True)
        atomic_write(path,json_bytes(result))
    return result


runtime_environment = previous.runtime_environment
python_argv = previous.python_argv
