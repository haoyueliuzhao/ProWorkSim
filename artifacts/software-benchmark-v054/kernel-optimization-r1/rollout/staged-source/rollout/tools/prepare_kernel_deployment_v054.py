"""Freeze an independent GPU6 successor; prepare/register metadata, never launch CUDA."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')


def prepare(source_root, kernel_plan_path, output):
    from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
    from proworksim.software_benchmark_source_freeze_v054 import MANIFEST, freeze_sources
    from proworksim.software_benchmark_resident_pool_v054 import read_pool, validate_pool_policy
    from proworksim.software_benchmark_queue_v054 import stat_id, validate_frozen
    from tools.check_match_interleave_v054 import preparation_permit
    source_root, output = source_root.resolve(), output.resolve()
    if (Path(__file__).resolve().parents[1] != source_root or MANIFEST != source_root /
            'artifacts/software-benchmark-v054/runner/source-manifest.json'):
        raise ValueError('Execute the independent copied preparation entry point')
    if not output.is_relative_to(ROOT / 'runs/software-benchmark-v054/kernel-optimization-r1'):
        raise ValueError('New deployment artifacts must remain in the independent kernel run')
    output.mkdir(parents=True, exist_ok=False)
    old_ref = reference(ROOT / 'runs/software-benchmark-v054/formal-bindings-r7.json')
    old = json.loads(checked(old_ref).read_bytes())
    validate_frozen(old, initial=True)
    old_pool = read_pool(old['resident_pool_policy'])
    matches = [entry for entry in old_pool['active'].values() if entry['gpu_index'] == 6]
    if len(matches) != 1:
        raise ValueError('Exactly one original GPU6 registration is required')
    registration = matches[0]
    old_registration = registration['event_reference']
    old_spec = json.loads(checked(registration['source_spec']).read_bytes())
    old_declaration = json.loads(checked(registration['declaration']).read_bytes())
    old_ready = reference(old_declaration['ready_path'])
    kernel_plan = reference(kernel_plan_path)
    kernel = json.loads(checked(kernel_plan).read_bytes())
    for key in ('operator_control', 'dependencies_manifest'):
        checked(kernel[key])
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    source_ref = freeze_sources()
    dependency_files = [{key: item[key] for key in ('path', 'sha256', 'bytes')}
        for item in json.loads(checked(kernel['dependencies_manifest']).read_bytes())['files']]
    # Conditions are excluded from the source hash to avoid a source-reference cycle.
    conditions = {}
    for arm, old_condition in old['conditions'].items():
        value = json.loads(checked(old_condition).read_bytes())
        value['source_manifest'] = source_ref
        if arm != 'REF':
            value['kernel_optimization_revision'] = {'revision': 'FLA-only-kernel-g6-r1',
                'plan': kernel_plan, 'original_condition': old_condition,
                'same_sampling_tools_limits': True, 'numerically_identical_claimed': False}
        path = source_root / 'config' / ('v054-condition-' + arm + '.json')
        path.write_text(json.dumps(value, indent=2) + '\n')
        conditions[arm] = reference(path)
    policy = json.loads(checked(old['resident_pool_policy']).read_bytes())
    policy.update(version='v054-resident-pool-policy-v3-kernel-g6',
        pool_root=str(output / 'pool'), physical_gpus=[6], maximum_residents=1,
        inherit_modes=[], ref_to_mp_after_all_500_scored=False,
        source_manifest=source_ref, original_pool_policy=old['resident_pool_policy'],
        kernel_plan=kernel_plan, runtime_revision='FLA-only-kernel-g6-r1',
        maximum_kernel_qualification_requests=6, automatic_provisioner=False,
        new_device_qualification='six paired neutral model diagnostics followed by six interleaved requests; no benchmark tasks')
    policy_ref = write_new(output / 'pool-policy.json', policy)
    validate_pool_policy(policy_ref)
    revision = output.name.rsplit('-', 1)[-1]
    if not revision.startswith('r') or not revision[1:].isdigit():
        raise ValueError('Use an explicit numbered deployment revision')
    resident_id = 'mp-g6-kernel-' + revision
    owner_root, short = output / 'resident', ROOT / ('runs/v054-gpu/kernel6' + revision)
    permit = preparation_permit(resident_id=resident_id, gpu_index=6,
        gpu_uuid=old_spec['card']['uuid'], source_manifest=source_ref, run_revision='r2')
    permit_ref = write_new(output / 'preparation-permit.json', permit)
    spec = copy.deepcopy(old_spec)
    spec.update(resident_id=resident_id, unit='proworksim-v054-resident-mp-g6-kernel-' + revision + '.service',
        root=str(owner_root), short=str(short), identity_path=str(owner_root / 'identity.json'),
        ready_path=str(owner_root / 'ready.json'), pool_policy=policy_ref,
        source_manifest=source_ref, preparation_permit=permit_ref,
        owner_entrypoint=reference(source_root / 'tools/serve_kernel_interleaved_owner_v054.py'),
        kernel_source_root=str(source_root), kernel_plan=kernel_plan,
        dependencies_manifest=kernel['dependencies_manifest'],
        old_registration=old_registration, old_ready=old_ready,
        release_path=str(output / 'predecessor-release.json'),
        gpu_runtime=reference(ROOT / 'tools/run_ref_preparation_v054.sh'),
        sources=[reference(source_root / name) for name in (
            'tools/run_kernel_resident_v054.py', 'tools/guard_kernel_owner_v054.py',
            'tools/serve_kernel_interleaved_owner_v054.py',
            'src/proworksim/software_benchmark_kernel_diagnostic_v054.py',
            'src/proworksim/software_benchmark_interleaved_owner_v054.py',
            'src/proworksim/software_benchmark_resident_pool_v054.py')],
        capacity_evidence_reuse={'original_receipt': old_spec['capacity_receipt'],
            'original_model_weights_and_contract': True,
            'new_kernel_identity_requires_six_neutral_requests': True,
            'full_capacity_retested_on_this_device': False})
    spec_ref = write_new(output / 'spec.json', spec)
    declaration_ref = write_new(output / 'declaration.json', {
        'version': 'v054-resident-declaration-v2', 'session_protocol': 'mp-interleave-v1',
        'maximum_sessions': 2, 'resident_id': resident_id, 'pool_policy': policy_ref,
        'mode': 'MATCH_PROJECT', 'gpu_index': 6, 'gpu_uuid': spec['card']['uuid'],
        'unit': spec['unit'], 'source_spec': spec_ref, 'ready_path': spec['ready_path'],
        'identity_path': spec['identity_path'], 'session_lock_path': str(owner_root / 'session.lock'),
        'admin': {'socket_path': str(short / 'admin.sock')}})
    # CPU prewarm stays on the immutable original pool-independent cache. Only
    # numerical/source identities differ; original slots/authorization stay exact.
    bindings = copy.deepcopy(old)
    bindings.update(source_manifest=source_ref, conditions=conditions,
        resident_pool_policy=policy_ref, numerical_runtime_revision='FLA-only-kernel-g6-r1',
        original_execution_bindings=old_ref, kernel_plan=kernel_plan,
        original_CPU_prewarm_reused=True)
    refs = {x['reference']['path']: x['reference'] for x in old['frozen_files']}
    for item in [source_ref, policy_ref, kernel_plan, kernel['dependencies_manifest'],
                 kernel['operator_control'], *dependency_files, *conditions.values(),
                 *json.loads(checked(source_ref).read_bytes())['files']]:
        refs[item['path']] = item
    bindings['frozen_files'] = [{'reference': item, 'stat': stat_id(item['path'])}
                                 for item in refs.values()]
    bindings_ref = write_new(output / 'bindings.json', bindings)
    validate_frozen(bindings, initial=True)
    commands = {
        'launcher': [str(ROOT / '.venv/bin/python'), str(source_root / 'tools/run_kernel_resident_v054.py'),
                     '--spec', spec_ref['path'], '--sha256', spec_ref['sha256']],
        'qualification': [str(ROOT / '.venv/bin/python'), str(source_root / 'tools/check_match_interleave_v054.py'),
            '--declaration', declaration_ref['path'], '--authorization', permit_ref['path'],
            '--output', str(output / 'interleave-qualification')],
        'register': [str(ROOT / '.venv/bin/python'), str(source_root / 'tools/prepare_kernel_deployment_v054.py'),
            'register', '--deployment', str(output / 'deployment.json')],
        'environment': {'PYTHONPATH': str(source_root / 'src') + ':' + str(source_root)},
        'systemd_unit': spec['unit']}
    result = {'version': 'v054-kernel-deployment-r1', 'original_bindings': old_ref,
        'bindings': bindings_ref, 'pool_policy': policy_ref, 'source_root': str(source_root),
        'source_manifest': source_ref, 'kernel_plan': kernel_plan, 'spec': spec_ref,
        'declaration': declaration_ref, 'old_registration': old_registration,
        'old_ready': old_ready, 'commands': commands, 'model_loads': 0,
        'model_calls': 0, 'services_launched': 0, 'formal_admission_passed': False}
    return write_new(output / 'deployment.json', result)


def register(deployment_path):
    from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
    from proworksim.software_benchmark_resident_provisioner_v054 import admission, register as register_event
    from proworksim.software_benchmark_resident_pool_v054 import read_pool
    deployment = json.loads(deployment_path.read_bytes())
    root = deployment_path.parent
    declaration_ref = deployment['declaration']
    declaration = json.loads(checked(declaration_ref).read_bytes())
    ready = json.loads(Path(declaration['ready_path']).read_bytes())
    check = reference(root / 'interleave-qualification/receipt.json')
    kernel = ready['kernel_runtime']
    qualifier = json.loads(checked(kernel['qualification']).read_bytes())
    if qualifier.get('passed') is not True or kernel['plan'] != deployment['kernel_plan']:
        raise ValueError('Do not register before fixed model diagnostics pass')
    value = admission(deployment['pool_policy'], declaration_ref, check, declaration['resident_id'])
    value.update(kernel_runtime=kernel, numerical_capacity_evidence_reused=False,
        original_capacity_evidence_reused=True, kernel_model_qualification=kernel['qualification'])
    admitted = write_new(root / 'admission.json', value)
    result = register_event(deployment['pool_policy'], declaration_ref, admitted, declaration['resident_id'])
    read_pool(deployment['pool_policy'])
    return {'registration': result, 'admission': admitted, 'formal_model_requests': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--source-root', type=Path, required=True)
    prep.add_argument('--kernel-plan', type=Path, required=True)
    prep.add_argument('--output', type=Path, required=True)
    reg = sub.add_parser('register')
    reg.add_argument('--deployment', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.source_root, args.kernel_plan, args.output) if args.command == 'prepare' else register(args.deployment)
    print(json.dumps(result))


if __name__ == '__main__':
    sys.exit(main())
