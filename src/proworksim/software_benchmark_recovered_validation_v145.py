"""Bounded validation of an already exported stopped pilot candidate.

The exporter verifies the committed world, archive stream and patch round trip
once. A grader checks the resulting immutable byte identities without parsing
the large managed state or reconstructing the code tree again.
"""
from __future__ import annotations

from pathlib import Path

from . import software_benchmark_stopped_recovery_v145 as recovery

VERSION = 'v145-bounded-stopped-candidate-byte-validation-r1'
MAXIMUM_SMALL_RECORD = 16*1024**2


def _small(ref):
    if type(ref.get('bytes')) is not int or not 0 <= ref['bytes'] <= MAXIMUM_SMALL_RECORD:
        raise ValueError('Metadata record exceeds the bounded validation envelope')
    return recovery.load(ref)


def _bytes(ref):
    if recovery.stream_reference(ref['path']) != ref:
        raise ValueError('Frozen candidate evidence bytes changed')


def validate_recovery_result_bounded(ref, row):
    output = recovery.OUTPUT/str(row['slot_index'])
    value = _small(ref)
    if (Path(ref['path']).resolve() != (output/'recovery-result.json').resolve()
            or value.get('version') != recovery.VERSION
            or value.get('status') != 'supplemental_candidate_locked'
            or value.get('endpoint') != recovery.ENDPOINT
            or value.get('original_generation_status') != 'technical_unknown'
            or value.get('replaces_original_endpoint') is not False
            or value.get('model_resampling') is not False
            or value.get('model_calls') != 0 or value.get('scoring_calls') != 0
            or value.get('round_trip_verified') is not True
            or value.get('original_usage_complete') is not False
            or value.get('unresolved_original_requests') != 1
            or any(value.get(k) != row[k] for k in
                   ('slot_id','slot_index','instance_id','condition_id','configuration'))
            or value.get('original_result') != recovery.reference(
                recovery.BATCH/'episodes'/str(row['slot_index'])/'result.json')):
        raise ValueError('Supplemental candidate identity or unknown status changed')
    lock, source = _small(value['candidate_lock']), _small(value['source'])
    evidence = source['original_evidence']
    names = ('original_result','writer_quiescence','quiescence','controller_transfer',
             'interrupted_actor','baseline_provenance')
    records = {k:_small(evidence[k]) for k in names}
    recovery.validate_original(row, *(records[k] for k in names))
    if (source.get('source_module') != recovery.reference(recovery.__file__)
            or source.get('slot') != row
            or source.get('full_archive_stream_verified_once') is not True
            or source.get('controller_archive') != records['controller_transfer']['archive_storage']
            or source.get('old_result_changed') is not False
            or any(source.get(k) != 0 for k in ('model_calls','tool_calls','scoring_calls'))):
        raise ValueError('Original complete export proof changed')
    _bytes(source['controller_archive']['blob'])
    for name, member in source['frozen_selected_bytes'].items():
        _bytes(member)
        if source['archive_members'][name] != {
                'member': name, 'sha256':member['sha256'], 'bytes':member['bytes']}:
            raise ValueError('Frozen managed member differs from its original archive')
    _bytes(evidence['baseline'])
    _bytes(lock['candidate'])
    _bytes(value['patch'])
    member = source['binding']['source_reference']
    committed_name = ('output/managed-world/world/control/versions/'+member['object_id']
                      +'/'+member['version_id']+'/member_001.json')
    committed = source['archive_members'].get(committed_name)
    patch = lock['patch_receipt']
    usage = source['provider_usage']
    if (not committed or committed['sha256'] != source['binding']['source_version_metadata']['sha256']
            or source['binding'].get('committed_prefix_validated') is not True
            or source['binding'].get('pending_actions_replayed') is not False
            or lock.get('recovery_source') != value['source'] or lock.get('slot') != row
            or lock.get('endpoint') != recovery.ENDPOINT
            or lock.get('source_reference') != member
            or lock.get('lock_before_grading') is not True
            or lock.get('candidate_selection_after_scoring') is not False
            or lock.get('baseline') != evidence['baseline']
            or lock.get('tree_sha256') != value.get('candidate_tree_sha256')
            or patch.get('patch') != value['patch']
            or patch.get('candidate_tree_sha256') != lock['tree_sha256']
            or patch.get('round_trip_verified') is not True
            or usage.get('usage_complete') is not False
            or usage.get('unresolved_requests') != 1
            or usage.get('ledger_rows_changed') is not False
            or usage.get('total_tokens') != value['known_original_tokens_lower_bound']):
        raise ValueError('Frozen committed version, patch or retained unknown accounting changed')
    return lock
