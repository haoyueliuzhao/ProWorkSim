"""Private passive REVIEW2 bundle; model-visible v141 behavior is unchanged.

The v143 actor aliases retain the public-result compatibility repair. New files
are packaged into a new directory; no frozen bundle is overwritten.
"""
from __future__ import annotations
import json
from types import FunctionType
from . import software_benchmark_sdk_bundle_v143 as previous
from .software_benchmark_runtime_inputs_v203_2_1 import actor_inputs, controller_inputs
from .software_benchmark_content_tokenizer_v141 import descriptor
from .storage import atomic_write, json_bytes

VERSION = 'v203.2.1-passive-review2-offline-bundle-r1'
OUTPUT = previous.previous.packaging.ROOT/'runs/software-benchmark-v203-2-1/sdk-bundle-r2'
NEW_MODULES = (
    'software_benchmark_alignment_contract_v203_2_1.py',
    'software_benchmark_runtime_inputs_v203_2_1.py',
    'software_benchmark_project_closure_v203_2_1.py',
    'software_role_baseline_runtime_v203_2_1.py',
    'software_observer_journal_v203_2_1.py', 'software_observer_views_v203_2_1.py',
    'software_passive_observer_v203_2.py',
    'software_collaboration_runtime_observer_v156.py',
    'software_collaboration_runtime_observer_v167.py',
    'software_collaboration_runtime_observer_v172.py',
    'software_collaboration_observation_v156.py',
    'software_collaboration_observation_v167.py',
    'software_benchmark_finalization_v159.py',
)
NEW_TOOLS = ('run_passive_controller_v203_2_1.py',)
ALIASES = {**previous.ALIASES,
    'controller.py':'run_passive_controller_v203_2_1.py',
    'project-controller.py':'run_passive_controller_v203_2_1.py'}


def probe_source():
    source = previous.probe_source()
    source = source.replace('software_benchmark_alignment_contract_v141',
                            'software_benchmark_alignment_contract_v203_2_1')
    source = source.replace('software_role_baseline_runtime_v141',
                            'software_role_baseline_runtime_v203_2_1')
    # Runtime schema inventory may retain the original three-baseline catalog;
    # deployment identities admit REVIEW2 alone, with exact original schemas.
    source = source.replace('assert set(current_inventory()["schemas"]) == {"S1", "FREE2", "REVIEW2"}',
        'assert "REVIEW2" in current_inventory()["schemas"]\n'
        'from proworksim.software_role_baseline_runtime_v141 import member_wire_tools as original_tools\n'
        'from proworksim.software_role_baseline_runtime_v203_2_1 import member_wire_tools as current_tools\n'
        'assert all(current_tools("REVIEW2", m) == original_tools("REVIEW2", m) for m in ("member_001", "member_002"))')
    return source


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
        raise ValueError('Passive deployment cannot change the frozen content tokenizer')
    if 'content_tokenizer' not in saved:
        result.update(content_tokenizer=expected, model_visible_contract_unchanged=True,
                      organization_id='REVIEW2', observer_is_passive=True,
                      old_runtime_bundles_modified=False)
        atomic_write(path,json_bytes(result))
    return result


runtime_environment = previous.runtime_environment
python_argv = previous.python_argv
