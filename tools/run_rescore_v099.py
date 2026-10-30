"""Prepare or serially execute the six separately approved v099 grading objects."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time

from proworksim import software_benchmark_rescore_v099 as scoring
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_expansion_episode_v069 import clone_namespace


def command(*args):
    return [str(scoring.ROOT / '.venv/bin/python'), '-B',
        str(scoring.ROOT / 'tools/run_offline_scorer_v058.py'),
        '-m', 'proworksim.software_benchmark_rescore_v099', *map(str, args)]


def clean_environment():
    return {key: value for key, value in os.environ.items()
            if key not in {'PYTHONHOME', 'PYTHONPATH', 'PYTHONEXECUTABLE', 'LD_LIBRARY_PATH', 'LD_PRELOAD'}}


def source_paths():
    names = ['software_benchmark_rescore_v099.py', 'software_benchmark_grading_repairs_v099.py',
        'software_benchmark_test_reset_v099.py', 'software_benchmark_offline_flit_v099.py',
        'software_benchmark_grading_repairs_v097.py', 'software_benchmark_grader_probe_v097.py',
        'software_benchmark_requests_tls_v068.py', 'software_benchmark_scorer_v066.py',
        'software_benchmark_dispatch_v066.py', 'software_benchmark_diff_diagnostics_v063.py',
        'software_benchmark_rescore_v095.py', 'software_benchmark_deepseek_runtime_v069.py',
        'software_benchmark_expansion_episode_v069.py']
    return [scoring.ROOT / 'src/proworksim' / name for name in names] + [
        scoring.ROOT / 'tools' / name for name in ('run_rescore_v099.py', 'check_rescore_v099.py',
            'run_offline_scorer_v058.py', 'run_capability_grading_v066.py')]


def prepare():
    if scoring.PLAN_FILE.exists() or scoring.AUTH_FILE.exists():
        raise ValueError('The standalone preparation/authorization is single-use')
    source_ref = reference(scoring.original_policy.PLAN_FILE)
    source = scoring.load(source_ref)
    rows, candidates, resources, environments = [], {}, {}, {}
    for slot, task in scoring.SLOTS.items():
        row = next(r for r in source['rows'] if r['slot_index'] == slot)
        old_folder = scoring.original_policy.GRADING_ROOT / f'score-{slot}'
        old_request = reference(old_folder / 'request.json')
        request = scoring.load(old_request)
        old_receipt, old_quiet = scoring.load(reference(old_folder / 'receipt.json')), scoring.load(reference(old_folder / 'quiescence.json'))
        if (old_receipt.get('status') != 'technical_unknown' or old_receipt.get('resolved') is not None
                or old_quiet.get('quiescent') is not True or old_quiet.get('cleanup_errors')
                or old_quiet.get('create_result_unknown')):
            raise ValueError('Only the two preserved, cleaned scoring exceptions may enter')
        result = scoring.load(request['generation_result'])
        quiet = scoring.load(result['quiescence'])
        if (result.get('status') != 'closed' or quiet.get('quiescent') is not True
                or quiet.get('cleanup_errors') or quiet.get('create_result_unknown')):
            raise ValueError('Original candidate writers must remain closed and quiet')
        rows.append(row)
        environments[task] = source['environments'][task]
        candidates[str(slot)] = {'origin_request': old_request,
            **{key: request[key] for key in ('configuration', 'generation_result', 'candidate_lock')},
            'original_score_receipt': reference(old_folder / 'receipt.json'),
            'original_score_quiescence': reference(old_folder / 'quiescence.json')}
        image = scoring.load(row['configuration'])['scorer_request_base']['image']['image_id']
        for kind in ('gold', 'empty'):
            resources[f'control-{task}-{kind}'] = {'role': 'control', 'instance_id': task,
                                                'patch_kind': kind, 'image_id': image}
        resources[f'score-{slot}'] = {'role': 'score', 'slot_id': row['slot_id'],
                                    'instance_id': task, 'image_id': image, 'endpoint': 'code'}
    plan = {'version': scoring.VERSION, 'administrative_root': str(scoring.RUN_ROOT),
        'original_plan': source_ref, 'rows': rows, 'resources': resources, 'environments': environments,
        'candidates': candidates, 'constraints': scoring.CONSTRAINTS,
        'cpu_set': scoring.original_policy.cpu_set('grader', 0),
        'offline_dependency': reference(scoring.ROOT / 'artifacts/software-benchmark-v099/offline-build-dependency-r1/manifest.json'),
        'wheel_download_receipt': reference(scoring.ROOT / 'runs/software-benchmark-v099/offline-wheel-preparation-r1/downloaded-wheel.json'),
        'runtime_qualified': False, 'candidate_patches_changed': False, 'new_model_calls': 0}
    scoring.RUN_ROOT.mkdir(parents=True, exist_ok=True)
    input_path = scoring.RUN_ROOT / ('plan-input-' + hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()[:12] + '.json')
    if input_path.exists():
        inputs = reference(input_path)
        if scoring.load(inputs) != plan:
            raise ValueError('Preparatory input changed')
    else:
        inputs = write_new(input_path, plan)
    result = subprocess.run(command('--manifest', '--plan', inputs['path']), cwd=scoring.ROOT,
        env=clean_environment(), capture_output=True, text=True, timeout=120)
    if result.returncode:
        write_new(scoring.RUN_ROOT / f'manifest-failure-{time.time_ns()}.json', {
            'input': inputs, 'returncode': result.returncode, 'stderr': result.stderr, 'stdout': result.stdout})
        raise RuntimeError('Fresh isolated manifest failed: ' + result.stderr[-3000:])
    plan['scorer_manifest'] = write_new(scoring.RUN_ROOT / 'scorer-manifest.json', json.loads(result.stdout))
    plan_ref = write_new(scoring.PLAN_FILE, plan)
    context = scoring.Context(plan_ref)
    controls = []
    for task in scoring.SLOTS.values():
        for kind in ('gold', 'empty'):
            controls.append(prepare_request(context, f'control-{task}-{kind}'))
    sources = write_new(scoring.SOURCE_FILE, {'version': scoring.VERSION,
        'files': [reference(path) for path in source_paths()]})
    proposal = {'version': scoring.VERSION, 'status': 'pending_review_not_started',
        'plan': plan_ref, 'source_index': sources, 'constraints': scoring.CONSTRAINTS,
        'scorer_manifest': plan['scorer_manifest'], 'control_requests': controls,
        'order_per_task': ['gold', 'empty', 'original_candidate_only_after_new_qualification'],
        'object_count': 6, 'serial_concurrency': 1, 'candidate_count': 2, 'controls': 4,
        'no_automatic_retry': True, 'scope': 'existing Docker API: only six fresh own containers; no volumes/services/host binding/network',
        'mechanisms': ['exact official test preimage reset', 'offline pinned flit_core wheel in Sphinx graders'],
        'official_test_patch_and_test_commands_changed': False,
        'old_results_preserved': True, 'fresh_independent_run_ids': True,
        'new_models_or_tokens': 0, 'run_command': '.venv/bin/python tools/run_rescore_v099.py --run'}
    scoring.PROPOSAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    proposal_ref = write_new(scoring.PROPOSAL_FILE, proposal)
    write_new(scoring.PROPOSAL_FILE.parent / 'pending-authorization.json', {'version': scoring.VERSION,
        'status': 'pending', 'explicit_authorization': None, 'plan': plan_ref,
        'source_index': sources, 'proposal': proposal_ref, 'constraints': scoring.CONSTRAINTS})
    return {'plan': plan_ref, 'proposal': proposal_ref, 'approved_authorization_written': False,
            'Docker_operations': 0, 'model_calls': 0}


def prepare_request(context, key, qualification=None):
    item = context.plan['resources'][key]
    task = item['instance_id']
    folder = context.grading_root / key
    folder.mkdir(parents=True, exist_ok=True)
    value = {'version': scoring.original.VERSION, 'resource_key': key, 'instance_id': task,
        'plan': context.plan_ref, 'configuration': context.plan['environments'][task]['configuration'],
        'candidate_lock': None, 'slot_id': None, 'patch_kind': item.get('patch_kind'),
        'limits': scoring.original.LIMITS, 'scorer_manifest': context.plan['scorer_manifest'],
        'cpuset_cpus': None, 'directory': str(folder), 'environment_revision': None, 'network_resolution': None}
    if item['role'] == 'score':
        row = next(r for r in context.plan['rows'] if r['slot_id'] == item['slot_id'])
        candidate = context.plan['candidates'][str(row['slot_index'])]
        scorer = scoring.build_scorer(context)
        scorer.validate_qualification(qualification, scoring.load(row['configuration']), context.plan_ref)
        value.update(**{name: candidate[name] for name in ('configuration', 'generation_result', 'candidate_lock')},
            slot_id=row['slot_id'], source_slot_id=row['source_slot_id'], measurement_kind=row['measurement_kind'],
            qualification=qualification, delivery_evidence=None)
    return write_new(folder / 'request.json', value)


def host(context, policy, scorer):
    spec = importlib.util.spec_from_file_location('v099_original_grading_host',
        scoring.ROOT / 'tools/run_capability_grading_v066.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    namespace = clone_namespace(module, policy=policy, scorer=scorer,
        RUN_ROOT=context.root, BATCH_ROOT=context.root)

    def fixed_python(arguments):
        if arguments[:2] != ['-m', 'proworksim.software_benchmark_scorer_v066']:
            raise ValueError('Only the official scorer subprocess may be redirected')
        return command(*arguments[2:])

    def capacity_available():
        available = next(int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))
        return available >= 24 * 1024**3 and shutil.disk_usage(context.root).free >= 16 * 1024**3

    namespace.update(fixed_python=fixed_python, bootstrap_environment=clean_environment,
                     capacity_available=capacity_available)
    return SimpleHost(namespace)


class SimpleHost:
    def __init__(self, namespace):
        self.run_request = namespace['run_request']
        self.trustworthy_cleanup = namespace['trustworthy_cleanup']
        self.qualify = namespace['qualify']


def run():
    context = scoring.Context(reference(scoring.PLAN_FILE))
    context.allowed()
    scoring.host_limits(context.plan['cpu_set'])
    owner_policy = scoring.policy(context)
    scorer = scoring.build_scorer(context)
    owner = host(context, owner_policy, scorer)
    write_new(context.root / 'started.json', {'version': scoring.VERSION, 'plan': context.plan_ref,
        'unix': time.time(), 'maximum_containers': 6, 'concurrency': 1, 'model_calls': 0})
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    outcomes, quarantined = [], False
    for slot, task in scoring.SLOTS.items():
        if stop.is_set() or quarantined:
            break
        result = {'instance_id': task, 'slot_index': slot, 'status': 'technical_unknown', 'controls': []}
        try:
            for kind in ('gold', 'empty'):
                ref = reference(context.grading_root / f'control-{task}-{kind}/request.json')
                result['controls'].append(owner.run_request(ref, stop_event=stop))
                if not owner.trustworthy_cleanup(ref):
                    quarantined = True
                    raise RuntimeError('Owned grader cleanup unproven; keep lease and quarantine')
            qualification = owner.qualify(task)  # Original full gold/empty validator.
            ref = prepare_request(context, f'score-{slot}', qualification)
            result.update(qualification=qualification, candidate_request=ref,
                          candidate_completion=owner.run_request(ref, stop_event=stop))
            if not owner.trustworthy_cleanup(ref):
                quarantined = True
                raise RuntimeError('Owned candidate grader cleanup unproven')
            receipt = reference(context.grading_root / f'score-{slot}/receipt.json')
            value = scoring.load(receipt)
            result.update(status=value['status'], resolved=value.get('resolved'), receipt=receipt)
        except Exception as error:
            result['error'] = {'type': type(error).__name__, 'message': str(error)}
        outcomes.append(result)
        write_new(context.root / f'outcome-{slot}.json', result)
    return write_new(context.root / 'completed.json', {'version': scoring.VERSION, 'plan': context.plan_ref,
        'outcomes': outcomes, 'owned_cleanup_quarantined': quarantined, 'cancelled': stop.is_set(),
        'new_model_calls': 0, 'finished_unix': time.time(), 'runtime_qualified': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--run', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else run(), ensure_ascii=False))
