"""Reuse successful r2 deployment controls across a host-startup-only revision.

No passed/failed receipt is rewritten. Reuse requires identical executable
actor/controller/SDK/model transport bytes, identical formal limits and task
bindings, and both original zero-model controls' complete cleanup.
"""
from __future__ import annotations

import json

from . import software_benchmark_dispatch_v066 as policy
from .software_benchmark_candidates_v054 import reference, checked

ROOT = policy.ROOT
PREVIOUS = ROOT / 'runs/software-benchmark-v066/v064-continuation-r2'
SUMMARY = ROOT / 'artifacts/software-benchmark-v066/deployment-diagnostic-r2/summary.json'
REUSE_FILE = policy.BATCH_ROOT / 'deployment-qualification-reuse.json'
VERSION = 'v066-reused-passed-deployment-qualification-r1'
PROTOCOL_FILES = (
    'src/proworksim/software_benchmark_episode_v066.py',
    'src/proworksim/software_benchmark_docker_actor_v066.py',
    'src/proworksim/software_benchmark_host_usage_v066.py',
    'src/proworksim/software_benchmark_sdk_bundle_v066.py',
    'src/proworksim/software_benchmark_ref_resident_v066.py',
    'src/proworksim/software_benchmark_model_capacity_v066.py',
    'tools/run_ref_controller_v066.py', 'tools/run_project_controller_v066.py',
    'tools/run_native_worker_docker_v066.py', 'tools/run_managed_worker_docker_v066.py',
    'runs/software-benchmark-v066/sdk-bundle-r1/manifest.json',
)


def value():
    old = policy.load(reference(PREVIOUS / 'plan.json'))
    new = policy.load(reference(policy.PLAN_FILE))
    summary = policy.load(reference(SUMMARY))
    if (summary.get('formal_model_calls') != 0 or summary.get('formal_execution_started') is not False
            or (PREVIOUS / 'coordinator/execution-started.json').exists()
            or list((PREVIOUS / 'resource-claims').glob('active-*.json'))):
        raise ValueError('Only clean completed preparation, with zero formal entry, may be inherited')
    excluded = {'zero_model_diagnostic_pairs', 'initial_zero_model_diagnostic_pairs',
                'conditional_zero_model_repair_pairs'}
    if ({k: v for k, v in old['constraints'].items() if k not in excluded}
            != {k: v for k, v in new['constraints'].items() if k not in excluded}
            or old['matrix'] != new['matrix'] or old['configurations'] != new['configurations']
            or old['continuation_inventory'] != reference(PREVIOUS / 'continuation-inventory.json')):
        raise ValueError('Formal deployment limits or the exact panel/configuration changed')
    # The inventory bytes must be the same; their new own-root reference differs.
    old_inventory, new_inventory = old['continuation_inventory'], new['continuation_inventory']
    if any(old_inventory[k] != new_inventory[k] for k in ('sha256', 'bytes')):
        raise ValueError('The allowed logical continuation inventory changed')
    old_resources = {k: v for k, v in old['resources'].items() if not v.get('diagnostic')}
    if old_resources != new['resources']:
        raise ValueError('Only removal of consumed diagnostic creation identities is permitted')
    old_sources = policy.load(summary['source_index'])['files']
    old_by_path = {item['path']: item for item in old_sources}
    bound = []
    for name in PROTOCOL_FILES:
        ref = reference(ROOT / name)
        if old_by_path.get(ref['path']) != ref:
            raise ValueError('Passed deployment control does not cover changed runtime: ' + name)
        bound.append(ref)
    diagnostics = {}
    for item in summary['results']:
        arm = item['arm']
        record = policy.load(item['qualification'])
        result, quiet = policy.load(item['result']), policy.load(item['quiescence'])
        if (arm not in ('REF', 'PROJECT') or arm in diagnostics
                or record.get('result') != item['result']
                or result.get('passed') is not True or result.get('model_calls') != 0
                or quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []
                or quiet.get('create_result_unknown') is not False):
            raise ValueError('An actual passed, zero-model, cleaned deployment receipt is required')
        diagnostics[arm] = item['result']
    if set(diagnostics) != {'REF', 'PROJECT'}:
        raise ValueError('Both actual execution protocols must have qualified')
    return {'version': VERSION, 'new_plan': reference(policy.PLAN_FILE),
        'original_summary': reference(SUMMARY), 'original_plan': reference(PREVIOUS / 'plan.json'),
        'identical_protocol_sources': bound, 'diagnostics': diagnostics,
        'new_diagnostic_containers': 0, 'new_model_calls': 0,
        'source_grading_proof_canonicalization_does_not_change_actor_protocol': True}


def prepare():
    return policy.retain(REUSE_FILE, value())


def qualifications():
    expected = value()
    actual = json.loads(checked(reference(REUSE_FILE)).read_bytes())
    if actual != expected:
        raise ValueError('The reviewed deployment reuse proof changed')
    return actual['diagnostics']
