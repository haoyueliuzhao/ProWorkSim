"""Finite allowlisted cache recovery using fresh evidence, preserving old failures.

The original sealed rootfs deleter keeps its path, lock, manifest, mount and
nine-terminal-consumer checks. Only its historical quiescence prerequisite is
replaced in this private process by a fresh, complete ownership observation.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT = ROOT / 'runs/software-benchmark-v055/terminal-cache-recovery-r2'
VERSION = 'v055-terminal-cache-current-quiescence-r2'
ORIGINAL_SHA = 'add7b61e57b7518f130eda86294b225a30dadacec70ad549dd6ed94649e300de'
ALLOCATED = {
    'django__django-11276': 3022393344,
    'django__django-11603': 3023544320,
    'django__django-12741': 3027808256,
    'django__django-14559': 3139665920,
    'matplotlib__matplotlib-23314': 7492997120,
    'matplotlib__matplotlib-24970': 7619231744,
    'pydata__xarray-2905': 5502316544,
    'pydata__xarray-6461': 5122621440,
    'pytest-dev__pytest-7490': 2807558144,
    'pytest-dev__pytest-7982': 2806280192,
    'scikit-learn__scikit-learn-14629': 3928723456,
    'sphinx-doc__sphinx-9229': 2954813440,
    'sympy__sympy-12489': 2857619456,
    'sympy__sympy-14531': 2872651776,
    'sympy__sympy-19783': 2895298560,
    'sympy__sympy-22456': 2904514560,
}
SLOT_SHA = {
    'v054': '55899d0b83a5bab1082bccb50496fb6c1d7111ecb951fc4d61c222be19d88676',
    'v055': 'fe78ae4bf281ebe9257b71bf159bafc7c7d39a3a5ca4838a61da906b16d7c9e5',
}


def original():
    path = ROOT / 'tools/reclaim_benchmark_cache_v055_r1.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != ORIGINAL_SHA:
        raise ValueError('Original authorized deletion implementation changed')
    spec = importlib.util.spec_from_file_location('cache_recovery_original_r1', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_scope(scope, claim_id):
    if (scope.get('claim_id') != claim_id
            or not re.fullmatch(r'proworksim-v054-episode-' + claim_id + r'-[a-z]+\.service', scope['unit'])
            or scope.get('manager', 'user') not in {'user', 'system'}
            or not scope['cgroup'].endswith('/' + scope['unit'])):
        raise ValueError('Scope crossed its exact retained claim')
    for key in ('main', 'outer_launcher'):
        identity = scope[key]
        if (type(identity.get('pid')) is not int or identity['pid'] <= 1
                or type(identity.get('start_ticks')) is not int or identity['start_ticks'] < 1):
            raise ValueError('Scope lacks exact host process identity')


def verify_scope_quiet(base, scope, state):
    collected = state.get('LoadState') == 'not-found'
    if (state.get('InvocationID') not in ('', scope['invocation_id'])
            or state.get('ControlGroup') not in ('', scope['cgroup'])
            or (collected and state.get('InvocationID') != '')
            or (not collected and state.get('KillMode') != 'control-group')
            or state.get('ActiveState') not in {'inactive', 'failed'}
            or state.get('MainPID') != '0' or base.populated(scope['cgroup'])):
        raise RuntimeError('Registered episode service or cgroup is not quiet')
    if any(base.process_identity(scope[key]['pid']) == scope[key]
           for key in ('main', 'outer_launcher')):
        raise RuntimeError('A registered main process or outer launcher remains alive')


def slice_quiet(claim_id):
    proofs = []
    name = 'proworksimv054ep' + claim_id + '.slice'
    for parent in (Path('/sys/fs/cgroup'), Path('/sys/fs/cgroup/system.slice')):
        path = parent / name / 'cgroup.events'
        try:
            observed = dict(line.split() for line in path.read_text().splitlines())
        except FileNotFoundError:
            observed = None
        if observed is not None and observed.get('populated') != '0':
            raise RuntimeError('The complete claim resource slice remains populated')
        proofs.append({'path': str(path), 'observed': observed, 'populated': False})
    return proofs


def current_proof(base, a, b, prep, plan_ref):
    jobs, scopes, claims, inventories, sealed = set(), {}, set(), [], []
    slot_maps = {}
    for cohort in ('v054', 'v055'):
        path = ROOT / f'artifacts/software-benchmark-{cohort}/manifests/slots.json'
        slot_ref = base.ref(path)
        if slot_ref['sha256'] != SLOT_SHA[cohort]:
            raise ValueError('Original complete slot inventory changed')
        rows = base.checked(slot_ref)['slots']
        slot_maps[cohort] = (slot_ref, {r['slot_id']: r for r in rows})
    for item in [prep.get('worker', {}), *prep.get('attempts', [])]:
        if item.get('unit'):
            jobs.add(item['unit'])
        if item.get('job'):
            jobs.add(base.checked(item['job'])['unit'])
    for cohort, rows in (('v054', a), ('v055', b)):
        slot_ref, frozen = slot_maps[cohort]
        for row in rows:
            slot, generation = row['slot'], row['generation']
            if frozen.get(slot['slot_id']) != slot:
                raise ValueError('Terminal consumer differs from its original slot')
            claim_dir = ROOT / f'runs/software-benchmark-{cohort}/episode-claims' / hashlib.sha256(slot['slot_id'].encode()).hexdigest()
            claim_ref = base.ref(claim_dir / 'claim.json')
            claim = base.checked(claim_ref)
            claim_id = claim.get('claim_id', '')
            if (claim.get('slot') != slot or claim.get('slots') != slot_ref
                    or not re.fullmatch(r'[a-f0-9]{32}', claim_id) or claim_id in claims):
                raise ValueError('Retained claim is absent, duplicated or crosses the slot')
            claims.add(claim_id)
            registry_ref = base.ref(claim_dir / 'scope-registry.json')
            registered = base.checked(registry_ref)
            if not isinstance(registered, list) or not registered:
                raise ValueError('The full retained scope inventory is absent')
            if len({(x.get('manager', 'user'), x['unit']) for x in registered}) != len(registered):
                raise ValueError('Scope inventory contains duplicate identities')
            for scope in registered:
                check_scope(scope, claim_id)
                scopes[(scope.get('manager', 'user'), scope['unit'])] = scope
            sealed.extend([claim_ref, registry_ref])
            old_quiet_ref = base.ref(claim_dir / 'quiescence.json')
            old_quiet = base.checked(old_quiet_ref)
            if old_quiet.get('claim_id') != claim_id:
                raise ValueError('Historical quiescence crossed its retained claim')
            # Include any historical scope not in the latest registry. This is
            # conservative and never drops a writer from the old failed proof.
            for scope in old_quiet.get('scopes', []):
                check_scope(scope, claim_id)
                key = (scope.get('manager', 'user'), scope['unit'])
                if key in scopes and scopes[key] != scope:
                    raise ValueError('Historical and retained scope identities differ')
                scopes[key] = scope
            attempts = list(generation.get('attempts', []))
            if not any(x.get('job') == generation.get('job') for x in attempts):
                attempts.append(generation)
            attempt_evidence = []
            for attempt in attempts:
                job_ref, result_ref = attempt['job'], attempt['result']
                job, result = base.checked(job_ref), base.checked(result_ref)
                if job.get('kind') != 'generation' or result.get('slot_id') != slot['slot_id']:
                    raise ValueError('Historical generation attempt has no exact provenance')
                jobs.add(job['unit'])
                completion_ref = attempt.get('completion')
                if completion_ref is None:
                    completion_ref = base.ref(Path(job_ref['path']).with_name('completion.json'))
                completion = base.checked(completion_ref)
                expected_completion = 'exited' if cohort == 'v054' else 'process_exited'
                if (completion.get('job') != job_ref or completion.get('status') != expected_completion
                        or type(completion.get('returncode')) is not int):
                    raise ValueError('Historical generation attempt has not exited')
                preclaim = result.get('slot_claimed') is False and result.get('entered') is False and result.get('model_calls') == 0
                if not preclaim:
                    # Every entered attempt must refer to this same durable
                    # single-use claim; arbitrary extra attempt roots fail closed.
                    if result.get('claim') is not None and result['claim'] != claim_ref:
                        raise ValueError('Historical attempt belongs to another claim')
                    if result.get('resource_release', {}).get('slice') not in (None, 'proworksimv054ep' + claim_id + '.slice'):
                        raise ValueError('Historical attempt used another resource slice')
                    qref = result.get('quiescence')
                    if qref and base.checked(qref).get('claim_id') != claim_id:
                        raise ValueError('Historical attempt has another quiescence claim')
                attempt_evidence.append({'job': job_ref, 'result': result_ref, 'completion': completion_ref, 'unentered_preclaim_failure': preclaim})
            if generation.get('unit') not in jobs:
                raise ValueError('Current generation worker lacks retained job provenance')
            for score in base.scores(row):
                if score.get('unit'):
                    jobs.add(score['unit'])
                if score.get('job'):
                    jobs.add(base.checked(score['job'])['unit'])
            inventories.append({'slot_id': slot['slot_id'], 'generation_status': generation['status'],
                'final_result': generation['result'], 'claim': claim_ref, 'scope_registry': registry_ref,
                'historical_quiescence': old_quiet_ref, 'historical_all_quiet': old_quiet.get('all_quiet'),
                'historical_errors_preserved': old_quiet.get('errors'), 'attempts': attempt_evidence,
                'score_statuses': [s['status'] for s in base.scores(row)]})
    observed = {}
    for manager in ('user', 'system'):
        units = [unit for owner, unit in scopes if owner == manager]
        if manager == 'user':
            units += sorted(jobs)
        observed[manager] = base.system_show(units, manager)
    for unit in jobs:
        state = observed['user'][unit]
        if state.get('ActiveState') not in {'inactive', 'failed'} or state.get('MainPID') != '0':
            raise RuntimeError('A generation, historical attempt, preparer or scorer remains alive')
        group = state.get('ControlGroup')
        if group and base.populated(group):
            raise RuntimeError('A consumer worker cgroup remains populated')
    for (manager, unit), scope in scopes.items():
        verify_scope_quiet(base, scope, observed[manager][unit])
    slices = {claim_id: slice_quiet(claim_id) for claim_id in sorted(claims)}
    for item in sealed:
        if base.ref(item['path']) != item:
            raise ValueError('Retained claim or full scope inventory changed during observation')
    return {'version': VERSION, 'observed_utc': base.now(), 'recovery_plan': plan_ref,
        'recovery_source': base.ref(__file__), 'nine_consumers': inventories,
        'current_systemd_observations': observed, 'registered_scope_count': len(scopes),
        'resource_slices': slices, 'all_scope_cgroups_empty': True,
        'all_registered_main_and_outer_launcher_identities_absent': True,
        'historical_quiescence_and_results_not_modified': True,
        'process_signals': 0, 'model_calls': 0, 'queue_or_ledger_writes': 0}


def prepare():
    base = original()
    OUT.mkdir(exist_ok=False)
    a, b = base.snapshot()
    registry = base.registry()
    rows = []
    for name, allocated in ALLOCATED.items():
        selected = base.task_rows(a, b, name)
        mapping = registry[name]['baseline_mapping']
        entry = base.CACHE / name / mapping['sha256'][:16]
        rootfs = entry / 'rootfs'
        identity = rootfs.lstat()
        rows.append({'instance_id': name, 'payload': str(rootfs), 'device': identity.st_dev,
            'inode': identity.st_ino, 'allocated_bytes_observed_du': allocated,
            'terminal_projection_sha256': base.projection(*selected),
            'lazy_preparation': base.ref(entry / 'lazy-preparation.json')})
    return base.write_new(OUT / 'plan.json', {'version': VERSION, 'created_utc': base.now(),
        'source': base.ref(__file__), 'original_helper': base.ref(ROOT / 'tools/reclaim_benchmark_cache_v055_r1.py'),
        'allowlist': rows, 'allocated_bytes_observed_du': sum(ALLOCATED.values()),
        'measurement': 'sudo du -s -B1 -x on the sixteen terminal cache rootfs, one invocation',
        'scope': 'only shared terminal native cache rootfs; no episode records or Docker images',
        'prior_failures_preserved': True, 'fresh_quiescence_required_under_original_cache_lock': True})


def run_one(plan_path, plan_sha, name):
    base = original()
    if plan_path.resolve() != OUT / 'plan.json' or base.ref(plan_path)['sha256'] != plan_sha:
        raise ValueError('Recovery plan path or SHA differs')
    plan_ref = base.ref(plan_path)
    plan = base.checked(plan_ref)
    if (plan.get('version') != VERSION or plan.get('source') != base.ref(__file__)
            or plan.get('original_helper', {}).get('sha256') != ORIGINAL_SHA
            or [r['instance_id'] for r in plan['allowlist']] != list(ALLOCATED)
            or name not in ALLOCATED):
        raise ValueError('Only the fixed sixteen-source-sealed recovery plan is admitted')
    target = next(r for r in plan['allowlist'] if r['instance_id'] == name)
    rootfs = Path(target['payload'])
    if not rootfs.exists():
        raise ValueError('Payload is already absent; no repeated deletion attempt')
    identity = rootfs.lstat()
    if (identity.st_dev, identity.st_ino) != (target['device'], target['inode']):
        raise ValueError('Allowlisted payload identity changed')
    old_output = base.OUTPUT
    if any((old_output / (name + suffix)).exists() for suffix in ('.intent.json', '.completed.json', '.dispatch-uncertain.json')):
        raise ValueError('Original helper has a durable mutation intent or uncertain dispatch; separate audit required')
    if any((OUT / (name + suffix)).exists() for suffix in ('.intent.json', '.completed.json', '.failed.json')):
        raise ValueError('Recovery attempt already exists; no automatic retry')
    base.OUTPUT, base.VERSION = OUT, VERSION
    def bound_proof(a, b, prep):
        if base.projection(a, b, prep) != target['terminal_projection_sha256']:
            raise ValueError('Allowlisted terminal consumers changed after plan')
        if base.ref(rootfs.parent / 'lazy-preparation.json') != target['lazy_preparation']:
            raise ValueError('Allowlisted cache template identity changed')
        return current_proof(base, a, b, prep, plan_ref)
    base.quiet_consumers = bound_proof
    result = base.privileged_one(name, ORIGINAL_SHA)
    if result.get('status') == 'reclaimed':
        # New forwarding receipt lets the unchanged rolling collector recognize
        # this separately audited retirement. Existing failures stay untouched.
        forward = old_output / (name + '.completed.json')
        if not forward.exists():
            base.write_new(forward, {'version': VERSION, 'instance_id': name,
                'status': 'reclaimed_by_independent_current_quiescence_recovery',
                'completion': result['completion'], 'recovery_plan': plan_ref,
                'old_failed_evidence_preserved': True})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--sha256')
    parser.add_argument('--instance')
    args = parser.parse_args()
    if args.prepare:
        if os.geteuid() != 1021:
            raise PermissionError('Prepare the fixed plan as the project owner')
        result = prepare()
    else:
        if not args.plan or not args.sha256 or not args.instance:
            parser.error('A sealed plan and one allowlisted instance are required')
        try:
            result = run_one(args.plan, args.sha256, args.instance)
        except Exception as error:
            base = original()
            path = OUT / ((args.instance if args.instance in ALLOCATED else 'invalid-instance') + '.failed.json')
            failure = {'version': VERSION, 'instance_id': args.instance, 'observed_utc': base.now(),
                'status': 'deferred', 'error': {'type': type(error).__name__, 'message': str(error)},
                'automatic_retry': False, 'original_records_not_modified': True}
            if path.parent.exists() and not path.exists():
                base.write_new(path, failure)
            print(json.dumps(failure), flush=True)
            raise SystemExit(1)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
