"""Seal one reviewable scoring-only proposal; never grant or execute it."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess

from proworksim import software_benchmark_scope_v127 as scope
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

PROPOSAL = scope.ROOT/'artifacts/software-benchmark-v127/scoring-authorization-r1/proposal.json'
ENTRIES = ('tools/prepare_preserved_score_v127.py', 'tools/check_preserved_score_v127.py',
    'tools/seal_preserved_score_v127.py', 'tools/run_preserved_score_v127.py',
    'tools/run_offline_scorer_v096.py', 'src/proworksim/software_benchmark_grading_v127.py',
    'src/proworksim/software_benchmark_scope_v127.py',
    'src/proworksim/software_benchmark_environment_v127.py')


def source_closure():
    pending, found = [scope.ROOT/name for name in ENTRIES], {}
    while pending:
        path = pending.pop().resolve()
        if str(path) in found:
            continue
        found[str(path)] = reference(path)
        try:
            package = '.'.join(path.relative_to(scope.ROOT/'src').with_suffix('').parts).rsplit('.', 1)[0]
        except ValueError:
            package = None
        for node in ast.walk(ast.parse(path.read_bytes(), filename=str(path))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith('.py'):
                literal = node.value
                target = (scope.ROOT/'tools'/literal if Path(literal).name == literal
                          else scope.ROOT/literal if literal.startswith('tools/') else None)
                if target is not None and target.is_file():
                    pending.append(target)
            candidates = []
            if isinstance(node, ast.Import):
                candidates = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    if package is None:
                        continue
                    base = '.'.join(package.split('.')[:len(package.split('.'))-node.level+1])
                    full = base+('.'+node.module if node.module else '')
                else:
                    full = node.module or ''
                candidates = [full, *[full+'.'+item.name for item in node.names]]
            for name in candidates:
                if name.startswith('proworksim'):
                    target = scope.ROOT/'src'/Path(*name.split('.'))
                    for candidate in (target.with_suffix('.py'), target/'__init__.py'):
                        if candidate.is_file():
                            pending.append(candidate)
                            break
    return [found[key] for key in sorted(found)]


def seal():
    from proworksim import software_benchmark_grading_v127 as grading
    if any(path.exists() for path in (scope.AUTH_FILE, scope.SOURCE_FILE, PROPOSAL)):
        raise PermissionError('Never reseal an approved or entered scoring attempt')
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    released = scope.prior_owner_released()
    control_ref = reference(scope.ROOT/'artifacts/software-benchmark-v127/scoring-controls-r1/summary.json')
    control = scope.load(control_ref)
    if (control.get('passed') is not True or control.get('scope_source') != reference(scope.__file__)
            or control.get('scorer_source') != reference(grading.__file__)
            or control.get('runner_source') != reference(scope.ROOT/'tools/run_preserved_score_v127.py')
            or control.get('request') != reference(plan['score_request_path'])):
        raise ValueError('The necessary local binding control does not match the final source')
    completed = subprocess.run(grading.command(['--verify-preparation']),
        cwd=scope.ROOT, env=grading.clean_environment(), capture_output=True, text=True,
        timeout=60, check=False)
    if completed.returncode:
        raise ValueError('Prepared identity mismatch: '+completed.stderr[-3000:])
    verification = json.loads(completed.stdout)
    if verification.get('passed') is not True:
        raise ValueError('Read-only verification did not pass')
    refs = source_closure()+[reference(path) for path in (
        scope.PLAN_FILE, scope.CPU_POOL_FILE, scope.NETWORK_RESOLUTION_FILE, scope.CA_PROFILE_FILE,
        Path(plan['score_request_path']), Path(control_ref['path']))]
    refs += [plan[key] for key in ('original_score_request', 'original_score_receipt',
        'original_score_quiescence', 'original_transport_failure', 'preserved_candidate_lock',
        'preserved_generation_result', 'prior_v125_owner_release')]
    refs += [reference(path) for path in scope.COORDINATOR_ROOT.rglob('*.json')]
    refs = list({item['path']: item for item in refs}.values())
    for ref in refs:
        checked(ref)
    source = write_new(scope.SOURCE_FILE, {'version': scope.VERSION, 'files': refs,
        'control': control_ref, 'prepared_grading_identity_verified': verification,
        'runtime_authorized': False})
    value = {'version': scope.VERSION, 'status': 'prepared', 'runtime_authorized': False,
        'plan': reference(scope.PLAN_FILE), 'source_index': source, 'constraints': scope.CONSTRAINTS,
        'original_score_request': plan['original_score_request'],
        'original_score_receipt': plan['original_score_receipt'],
        'preserved_candidate_lock': plan['preserved_candidate_lock'],
        'preserved_generation_result': plan['preserved_generation_result'],
        'prior_v125_owner_release': released,
        'new_score_request': reference(plan['score_request_path']),
        'cause': 'One original upstream TLS connection timed out before connecting or forwarding payload.',
        'original_status': 'technical_unknown', 'official_report_preserved': True,
        'candidate_reselected': False, 'candidate_bytes_changed': False,
        'maximum_containers': 1, 'maximum_named_volumes': 0,
        'maximum_generation_pairs': 0, 'maximum_graders': 1, 'model_calls': 0,
        'new_gold_empty_controls': 0, 'prior_v119_qualification_reused': True,
        'container_CPU': 4, 'container_memory_GiB': 16,
        'supervisor_process_address_space_GiB': 4,
        'scorer_process_address_space_GiB': 4,
        'maximum_combined_reserved_memory_GiB': 24,
        'host_process_count': 2,
        'host_and_container_CPU_set': scope.cpu_set('grader'),
        'CPU_pool_allocation': 'Original frozen pool indices 28:32; disjoint from v126 indices 0:28',
        'container_network': 'none', 'container_cap_drop': ['ALL'],
        'grading_only_cap_add': ['NET_ADMIN', 'NET_BIND_SERVICE'],
        'maximum_TLS_sessions': 1, 'maximum_external_grading_connections': 512,
        'maximum_external_grading_payload_bytes': 64*1024**2,
        'network_resolution': reference(scope.NETWORK_RESOLUTION_FILE),
        'CA_profile': reference(scope.CA_PROFILE_FILE), 'TLS_verification_enabled': True,
        'host_binds': 0, 'host_listeners': 0, 'GPUs': 0, 'new_services': 0,
        'shared_host_configuration_changes': 0, 'other_resources_touched': False,
        'automatic_retry': False, 'cleanup_required': True, 'execution_started': False,
        'control': control_ref,
        'execute_argv': grading.command([])[:-2]+[str(scope.ROOT/'tools/run_preserved_score_v127.py'), '--execute']}
    PROPOSAL.parent.mkdir(parents=True, exist_ok=True)
    return {'proposal': write_new(PROPOSAL, value), 'source_index': source, 'runtime_authorized': False}


if __name__ == '__main__':
    print(json.dumps(seal(), ensure_ascii=False))
