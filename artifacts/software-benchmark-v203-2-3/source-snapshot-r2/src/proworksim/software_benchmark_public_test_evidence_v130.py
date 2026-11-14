"""PROJECT adapter for the same stdlib public evidence path used by REF."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import time

_here = Path(__file__).resolve()
_source = (Path('/opt/pws-runtime/public-test-execution.py') if _here.is_relative_to(Path('/opt/pws-runtime'))
           else _here.parents[2]/'tools/public_test_execution_v130.py')
_spec = importlib.util.spec_from_file_location('_pws_public_test_execution_v130', _source)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
execute_public_entry = _module.execute_public_entry
parse_test_evidence = _module.parse_test_evidence
VERSION = _module.VERSION


def run_public_entry(entry, *, root, environment, request, candidate_tree_sha256):
    remaining = request['hard_deadline_monotonic']-time.monotonic()
    if remaining <= 0:
        raise TimeoutError('The episode ended before the accepted public test could start')
    try:
        value = execute_public_entry(entry, root=root, environment=environment,
            timeout_seconds=min(entry['timeout_seconds'], remaining))
    finally:
        # This entry is only used inside the private managed PID1 actor.
        # The native convenience wrapper calls execute_public_entry directly.
        from .software_benchmark_managed_actor_v064 import _reap_private_children
        _reap_private_children()
    proof = {key: value[key] for key in ('validation_status', 'counts', 'test_evidence')}
    return {'passed': value['passed'], **proof, 'execution': {
        'executed': True, 'command_executed': True, 'input_tree_sha256': candidate_tree_sha256,
        'source_reference': request['source_reference'], 'argv': value['argv'], 'cwd': '/testbed',
        'returncode': value['returncode'], 'timed_out': value['timed_out'],
        'wall_seconds': value['wall_seconds'], 'descendants_quiescent': True,
        'stdout_sha256': value['output_sha256'], 'stdout_bytes': value['output_bytes'],
        'stdout_utf8_strict': value['stdout_utf8_strict'], 'hidden_evaluator': False,
        'model_supplied_command': False, **proof},
        'groups': {'public_repository_tests': {'status': 'passed' if value['passed'] else 'failed',
            'executed': True, 'passed': value['passed'], 'output': value['output'], **proof,
            'tests': [{'test_id': 'repository-wide-public-entrypoint', 'passed': value['passed']}]}},
        'repository_collection_errors': [],
        'verification_diagnostics': [] if value['validation_status'] == 'verified' else
            [{'kind': value['validation_status'], 'counts': value['counts'],
              'command_executed': True, 'test_verification_completed': False}]}
