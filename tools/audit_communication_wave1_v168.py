"""Read-only, score-blind audit of the first 36 planned communication identities.

Select the 14 explicitly authorized independent replacements, the 21 v159
attempts, and the one trustworthy original v157 attempt. Old costs stay in the
same ledger; interrupted attempts are not silently described as measured.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import resource
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'artifacts/software-benchmark-v168/wave1-measurement-r1'


def read(path):
    return json.loads(Path(path).read_bytes())


def main():
    # Bound only this ordinary-user analysis process, never the shared host.
    os.environ.update(OMP_NUM_THREADS='1', TOKENIZERS_PARALLELISM='false',
                      HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[-2:])
    resource.setrlimit(resource.RLIMIT_AS, (8*1024**3, 8*1024**3))
    from functools import lru_cache
    from proworksim.software_benchmark_candidates_v054 import reference, checked, write_new
    from proworksim.software_collaboration_observation_v141 import load_official_content_counter
    from proworksim.software_communication_admission_v157 import assess_wave

    OUT.mkdir(parents=True, exist_ok=True)
    write_new(OUT/'started.json', {'pid': os.getpid(), 'unix': time.time(),
        'model_calls': 0, 'Docker_operations': 0, 'scores_consulted': False,
        'cpu_affinity': sorted(os.sched_getaffinity(0)), 'address_space_limit_bytes': 8*1024**3})
    old = ROOT/'runs/software-benchmark-v157/communication-pilot24-r1'
    interim = ROOT/'runs/software-benchmark-v159/communication-pilot-recovery-r1'
    repaired = ROOT/'runs/software-benchmark-v161/independent-technical-recovery-r1'
    original = read(old/'execution-plan-r2.json')
    replacements = read(ROOT/'artifacts/software-benchmark-v161/final-independent-recovery-plan-r1/proposal.json')['attempts']
    mapping = {r['original_slot_id']: r for r in replacements}
    wave = [r for r in original['rows'] if r['wave'] == 1]
    assert len(wave) == 36 and len(mapping) == 14
    selected, exceptions, new_errors = [], [], []
    for row in wave:
        if row['slot_id'] in mapping:
            replacement = mapping[row['slot_id']]
            slot, index, base = replacement['recovery_slot_id'], replacement['slot_index'], repaired
        else:
            slot, index = row['slot_id'], row['slot_index']
            base = old if index == 15703 else interim
        folder = base/'episodes'/str(index)/'controller-output'
        summary = read(folder/'model-ledger/collaboration-observation/summary.json')
        boundary = read(folder/'managed-boundary.json')
        if boundary.get('status') != 'bounded_work_closed' or boundary.get('execution_integrity_failure'):
            exceptions.append({'original_slot_id': row['slot_id'], 'attempt_slot_id': slot,
                'reason': 'interrupted_generation_preserved',
                'boundary': reference(folder/'managed-boundary.json'),
                'measurement_errors': summary.get('runtime_measurement_errors', [])})
        if base == repaired and summary.get('runtime_measurement_errors'):
            new_errors.append({'slot': slot, 'errors': summary['runtime_measurement_errors']})
        selected.append({'original_slot_id': row['slot_id'], 'selected_slot_id': slot,
            'root': str(base/'episodes'), 'index': index,
            'observation': reference(folder/'model-ledger/collaboration-observation/summary.json'),
            'observation_completion': summary['completion_status'],
            'partial_channels': summary.get('runtime_partial_channels', []),
            'historical_errors_rewritten': False})
    assert len({r['selected_slot_id'] for r in selected}) == 36
    evidence = ROOT/'artifacts/software-benchmark-v167'
    for rel in ('observer-cpu-r1/summary.json', 'observer-sdk-r1/summary.json'):
        proof = read(evidence/rel)
        assert proof['passed'] is True
        for ref in proof.get('sources', []):
            checked(ref)
    current_source = read(repaired/'runtime-sources-r2.json')
    for ref in current_source['files']:
        checked(ref)
    write_new(OUT/'selected-attempts.json', {'rows': selected, 'technical_exceptions': exceptions,
        'repaired_observer_errors': new_errors, 'normal_scores_used_to_select_attempts': False,
        'excluded_original14_costs_still_in_same_cash_ledger': True,
        'presentations_partial_flags_not_erased': True})
    spec = importlib.util.spec_from_file_location('streaming_audit', ROOT/'tools/audit_communication_measurement_v157.py')
    audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
    manifest = ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
    counter, meta = load_official_content_counter(manifest, manifest_sha256=reference(manifest)['sha256'])
    slots = {r['selected_slot_id'] for r in selected}
    measurement = audit.audit(old/'ledgers/pilot.sqlite', [old/'episodes', interim/'episodes', repaired/'episodes'],
        lru_cache(maxsize=16384)(counter), meta['tokenizer_id'], slots=slots,
        mechanism_gates={key: not new_errors for key in ('G0-4', 'G0-5', 'G0-6')})
    physical = write_new(OUT/'physical-measurement.json', measurement)
    grant = read(ROOT/'artifacts/software-benchmark-v157/user-amendment-r1/authorization.json')
    gate = assess_wave(1, measurement, grant, planned_episodes=36, terminal_episodes=len(selected),
        unresolved_attempts=exceptions, frozen_source_verified=True, protocol_unchanged=True)
    gate.update(physical_measurement=physical, selection=reference(OUT/'selected-attempts.json'),
        current_observer_revision='v167', legacy_observer_exceptions_quarantined=True,
        previous_failed_source_gate_preserved=True, actual_API_calls_during_audit=0,
        original_task_condition_denominator=72, additional_attempts_authorized=14,
        cash_cap_CNY='500.00', new_cash_allowance_CNY='0.00', finished_unix=time.time())
    result = write_new(OUT/'gate.json', gate)
    print(json.dumps({'gate': result, 'passed': gate['advance_to_wave_2'],
        'requests': measurement['captured_requests'], 'issues': measurement['issues'],
        'estimated_unknown': measurement['payload_local_estimated_unattributed_fraction']}))


if __name__ == '__main__':
    main()
