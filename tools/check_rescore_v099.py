"""Execute the real isolated scorer validator for six CPU-only fixture requests."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

from proworksim import software_benchmark_rescore_v099 as scoring
from proworksim.software_benchmark_candidates_v054 import reference, write_new as write_file


def write_new(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return write_file(path, value)


def runner():
    spec = importlib.util.spec_from_file_location('v099_runner_for_CPU_controls',
        scoring.ROOT / 'tools/run_rescore_v099.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def control_evidence(context, task, kind):
    key = f'control-{task}-{kind}'
    folder = context.grading_root / key
    (folder / 'official-output').mkdir(parents=True, exist_ok=True)
    config = scoring.load(context.plan['environments'][task]['configuration'])
    original = config['scorer_request_base']
    mapping = scoring.load(original['baseline_mapping'])
    identity = write_new(folder / 'official-output/identity.json', {
        'plan': context.plan_ref, 'resource_key': key, 'dataset': original['dataset'],
        'image': original['image'], 'baseline_mapping': original['baseline_mapping'],
        'scorer_manifest': context.plan['scorer_manifest'], 'limits': scoring.original.LIMITS,
        'patch_kind': kind, 'actor_feedback': False, 'model_calls': 0,
        'environment_revision': None, 'network_resolution': None})
    observed = write_new(folder / 'official-output/initial-container.json', {
        'head_git_tree': mapping['official_tree'], 'working_tree_clean': True,
        'effective_network_mode': 'none', 'namespace_evidence': {'all_distinct': True},
        'CPU_fixture_only_not_an_actual_container': True})
    receipt = write_new(folder / 'receipt.json', {'version': scoring.original.VERSION,
        'status': 'official_report', 'resource_key': key, 'instance_id': task, 'identity': identity,
        'resolved': kind == 'gold', 'actor_feedback': False, 'model_calls': 0,
        'official_result': [None, {task: {'patch_successfully_applied': True, 'infra_failure': False,
            'resolved': kind == 'gold', 'tests_status': {'FAIL_TO_PASS': {
                'failure': ['CPU-synthetic-failure'] if kind == 'empty' else [],
                'success': ['CPU-synthetic-success'] if kind == 'gold' else []}}}}]})
    quiet = write_new(folder / 'quiescence.json', {'resource_key': key, 'quiescent': True,
        'cleanup_errors': [], 'create_result_unknown': False, 'deadline_reached': False})
    completion = write_new(folder / 'completion.json', {'returncode': 0})
    return {'patch_kind': kind, 'receipt': receipt, 'quiescence': quiet,
            'completion': completion, 'initial_container': observed}


def main():
    module = runner()
    results = []
    with tempfile.TemporaryDirectory(prefix='pws-v099-validation-') as raw:
        root = Path(raw)
        plan = {**scoring.load(reference(scoring.PLAN_FILE)), 'administrative_root': str(root / 'run')}
        inputs = write_new(root / 'input.json', plan)
        child = subprocess.run(module.command('--manifest', '--plan', inputs['path'], '--cpu-fixture', root),
            cwd=scoring.ROOT, env=module.clean_environment(), capture_output=True, text=True, check=True, timeout=120)
        plan['scorer_manifest'] = write_new(root / 'run/scorer-manifest.json', json.loads(child.stdout))
        plan_ref = write_new(root / 'plan.json', plan)
        sources = write_new(root / 'sources.json', {'files': [reference(p) for p in module.source_paths()]})
        proposal = write_new(root / 'proposal.json', {'plan': plan_ref, 'constraints': scoring.CONSTRAINTS})
        write_new(root / 'CPU-AUTH.json', {'version': scoring.VERSION, 'status': 'cpu-only',
            'plan': plan_ref, 'constraints': scoring.CONSTRAINTS, 'source_index': sources, 'proposal': proposal})
        context = scoring.Context(plan_ref, fixture=root)
        bound_policy = scoring.policy(context)
        try:
            context.allowed('v066.grader.create')
        except PermissionError:
            create_denied = True
        else:
            raise AssertionError('A CPU-only authority must never permit container creation')
        requests = []
        for task in scoring.SLOTS.values():
            controls = []
            for kind in ('gold', 'empty'):
                key = f'control-{task}-{kind}'
                requests.append(module.prepare_request(context, key))
                controls.append(control_evidence(context, task, kind))
            qualification = write_new(context.root / 'qualifications' / (task + '.json'), {
                'version': scoring.original.VERSION, 'instance_id': task, 'plan': plan_ref,
                'controls': controls, 'passed': True, 'model_calls': 0})
            slot = next(index for index, name in scoring.SLOTS.items() if name == task)
            requests.append(module.prepare_request(context, f'score-{slot}', qualification))
        for request_ref in requests:
            request = scoring.load(request_ref)
            claim = bound_policy.claim_resource(request['resource_key'])
            write_new(Path(request['directory']) / 'capacity-claim.json', {'prepared_request': request_ref, 'claim': claim})
            child = subprocess.run(module.command('--validate-request', request_ref['path'], '--cpu-fixture', root),
                cwd=scoring.ROOT, env=module.clean_environment(), capture_output=True, text=True, timeout=120)
            if child.returncode:
                raise RuntimeError(request['resource_key'] + ': ' + child.stderr[-5000:])
            value = json.loads(child.stdout)
            assert value['passed'] and value['actual_original_validate_request_executed'] and value['manifest_equal']
            results.append(value)
            assert bound_policy.release_resource(claim, quiescent=True)
        # Real qualification validator must reject a synthetic gold that did not
        # pass, without rewriting any real control evidence.
        task = next(iter(scoring.SLOTS.values()))
        qref = reference(context.root / 'qualifications' / (task + '.json'))
        q = scoring.load(qref)
        gold = scoring.load(q['controls'][0]['receipt'])
        gold['resolved'] = False
        bad_gold = write_new(root / 'bad-gold.json', gold)
        q['controls'][0]['receipt'] = bad_gold
        bad_q = write_new(root / 'bad-qualification.json', q)
        try:
            scoring.build_scorer(context).validate_qualification(bad_q,
                scoring.load(context.plan['environments'][task]['configuration']), plan_ref)
        except ValueError:
            bad_control_denied = True
        else:
            raise AssertionError('Bad gold control was accepted')
    destination = scoring.ROOT / 'artifacts/software-benchmark-v099/isolated-scorer-control-r1/summary.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_new(destination, {'version': scoring.VERSION, 'passed': True,
        'real_isolated_module_validate_requests': results, 'control_requests': 4, 'original_candidates': 2,
        'new_scope_and_original_claim_candidate_qualification_validators_executed': True,
        'synthetic_control_evidence_only_in_tmp': True, 'fixture_container_creation_denied': create_denied,
        'bad_control_qualification_rejected': bad_control_denied,
        'production_AUTH_written': False, 'Docker_operations': 0, 'model_calls': 0,
        'network_connections': 0, 'host_changes': 0, 'runtime_qualified': False,
        'plan': reference(scoring.PLAN_FILE), 'source_index': reference(scoring.SOURCE_FILE),
        'control_source': reference(__file__)})
    print(json.dumps({'passed': True, 'requests': len(results), 'summary': str(destination)}))


if __name__ == '__main__':
    main()
