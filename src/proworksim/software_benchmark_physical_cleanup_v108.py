"""Reconcile two consumed graders using new exact-ID absence observations.

This module makes no Docker, network, model or scoring call. It preserves old
CA/scoring evidence and releases only the two original grader reservations.
"""
from __future__ import annotations

from pathlib import Path
import re
import time

from . import software_benchmark_scope_v106 as owner_scope
from . import software_benchmark_scope_v107 as authorization_scope
from .software_benchmark_candidates_v054 import reference, write_new

VERSION = 'v108-exact-owned-grader-physical-reconciliation-r1'
KEYS = ('score-7038', 'score-7039')
PROOF_ROOT = owner_scope.ROOT / 'artifacts/software-benchmark-v108/physical-cleanup-r1'
AGGREGATE_FILE = PROOF_ROOT / 'summary.json'


def inspect_inputs(request_ref):
    request = owner_scope.load(request_ref)
    key = request.get('resource_key')
    folder = owner_scope.GRADING_ROOT / str(key)
    if (key not in KEYS or Path(request_ref['path']).resolve() != folder / 'request.json'
            or request.get('directory') != str(folder)
            or request.get('plan') != reference(owner_scope.PLAN_FILE)
            or request.get('instance_id') != 'psf__requests-1921'):
        raise ValueError('Only the two exact original Requests-1921 graders may be reconciled')
    authorization_scope.require_allowed('v066.run', slot_id=request['slot_id'],
                                        instance_id=request['instance_id'])
    plan = owner_scope.load(request['plan'])
    row = next(row for row in plan['rows'] if row['slot_index'] == int(key.removeprefix('score-')))
    if request['slot_id'] != row['slot_id'] or request['configuration'] != row['configuration']:
        raise ValueError('The consumed request changed its original task/condition identity')
    refs = {name: reference(folder / filename) for name, filename in (
        ('quiet', 'quiescence.json'), ('completion', 'completion.json'),
        ('admission', 'capacity-claim.json'), ('initial', 'official-output/initial-container.json'),
        ('receipt', 'receipt.json'))}
    values = {name: owner_scope.load(ref) for name, ref in refs.items()}
    quiet, done, initial = (values[name] for name in ('quiet', 'completion', 'initial'))
    claim_ref = values['admission']['claim']
    claim = owner_scope.load(claim_ref)
    ids = quiet.get('owned_container_ids')
    if (not isinstance(ids, list) or len(ids) != 1 or not re.fullmatch(r'[0-9a-f]{64}', str(ids[0]))
            or initial.get('container_id') != ids[0] or quiet.get('resource_key') != key
            or quiet.get('create_result_unknown') is not False
            or quiet.get('other_containers_affected') is not False
            or done.get('request') != request_ref or done.get('resource_key') != key
            or done.get('status') not in ('process_exited', 'technical_unknown') or done.get('returncode') != 0
            or type(done.get('finished_unix')) not in (int, float)
            or done['finished_unix'] < done.get('started_unix', float('inf'))
            or values['admission'].get('prepared_request') != request_ref
            or done.get('capacity_claim') != claim_ref
            or Path(claim_ref['path']).resolve() != owner_scope.BATCH_ROOT / 'resource-claims' / (key + '.json')
            or claim.get('version') != owner_scope.VERSION or claim.get('key') != key
            or claim.get('plan') != request['plan'] or claim.get('spec') != plan['resources'][key]
            or Path(claim.get('lease', '')).parent != owner_scope.BATCH_ROOT / 'resource-claims'
            or Path(claim.get('lease', '')).name not in ('active-grader-0.json', 'active-grader-1.json')
            or values['receipt'].get('status') != 'technical_unknown'):
        raise ValueError('Original ownership, process exit or preserved unknown evidence is incomplete')
    transport_ref = quiet.get('transport_result')
    if (not isinstance(transport_ref, dict)
            or Path(transport_ref['path']).resolve() != folder / 'official-output/transport.json'):
        raise ValueError('Missing the original bounded relay record')
    transport = owner_scope.load(transport_ref)
    if transport.get('thread_finished') is not True:
        raise ValueError('A live or unproven relay cannot release its physical capacity')
    return {'request': request, 'request_ref': request_ref, 'container_id': ids[0],
            'configuration': owner_scope.load(request['configuration']), 'refs': refs,
            'claim': claim, 'claim_ref': claim_ref, 'transport_ref': transport_ref,
            'finished_unix': done['finished_unix']}


def validate_observation(observation, inputs, observed_now):
    when = observation.get('inspected_unix')
    if (observation.get('container_id') != inputs['container_id']
            or observation.get('exists') is not False or observation.get('status') != 404
            or type(when) not in (int, float)
            or not max(inputs['finished_unix'], observed_now - 300) <= when <= observed_now + 1):
        raise ValueError('A fresh read-only 404 for the exact consumed container is required')


def validate_reconciliation(proof_ref, inputs):
    proof = owner_scope.load(proof_ref)
    if (proof.get('version') != VERSION or proof.get('request') != inputs['request_ref']
            or proof.get('original_refs') != inputs['refs']
            or proof.get('claim') != inputs['claim_ref']
            or proof.get('transport') != inputs['transport_ref']
            or proof.get('physical_quiescence') is not True
            or proof.get('original_scoring_status_unchanged') != 'technical_unknown'
            or proof.get('CA_final_identity_recovered') is not False
            or proof.get('original_records_overwritten') is not False):
        raise ValueError('Physical reconciliation may not invent recovered scoring/CA evidence')
    validate_observation(proof['inspection'], inputs, proof['recorded_unix'])
    return proof


def reconcile_absence(request_ref, observation):
    """Root supplies the real read-only inspect result; only local metadata changes."""
    inputs = inspect_inputs(request_ref)
    now = time.time()
    validate_observation(observation, inputs, now)
    PROOF_ROOT.mkdir(parents=True, exist_ok=True)
    output = PROOF_ROOT / (inputs['request']['resource_key'] + '.json')
    proof = {'version': VERSION, 'request': request_ref, 'original_refs': inputs['refs'],
        'claim': inputs['claim_ref'], 'transport': inputs['transport_ref'],
        'inspection': observation, 'recorded_unix': now, 'physical_quiescence': True,
        'original_scoring_status_unchanged': 'technical_unknown',
        'CA_final_identity_recovered': False, 'original_records_overwritten': False,
        'model_calls': 0, 'containers_created': 0, 'containers_deleted': 0}
    proof_ref = reference(output) if output.exists() else write_new(output, proof)
    validate_reconciliation(proof_ref, inputs)
    owner_scope.dispatch_view().release_resource(inputs['claim_ref'], quiescent=True)
    if Path(inputs['claim']['lease']).exists():
        raise ValueError('The original grader capacity lease was not released')
    return proof_ref


def _aggregate_value():
    proofs = []
    for key in KEYS:
        inputs = inspect_inputs(reference(owner_scope.GRADING_ROOT / key / 'request.json'))
        proof_ref = reference(PROOF_ROOT / (key + '.json'))
        validate_reconciliation(proof_ref, inputs)
        marker = owner_scope.BATCH_ROOT / 'resource-claims' / (key + '.released.json')
        released = owner_scope.load(reference(marker))
        if (released.get('claim') != inputs['claim_ref'] or released.get('quiescent') is not True
                or Path(inputs['claim']['lease']).exists()):
            raise ValueError('Both exact original grader reservations must be released')
        proofs.append({'key': key, 'proof': proof_ref, 'release': reference(marker)})
    value = {'version': VERSION, 'passed': True, 'graders': proofs,
             'original_scores_remain_unknown': True, 'original_records_overwritten': False,
             'new_containers': 0, 'new_volumes': 0, 'model_calls': 0}
    return value


def aggregate_reconciliations():
    return owner_scope.retain(AGGREGATE_FILE, _aggregate_value())


def validate_original_reconciliations():
    expected = _aggregate_value()
    ref = reference(AGGREGATE_FILE)
    if owner_scope.load(ref) != expected:
        raise ValueError('The aggregate reconciliation no longer binds both original unknown scores')
    return {'summary': ref, **expected}
