"""Seal untouched Qwen history and only its unused original physical identities."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
import subprocess
import time

from proworksim import software_benchmark_qwen_scope_v084 as scope
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

VERSION = 'v084-original-Qwen-recovery-preparation-r1'


def load(ref):
    return json.loads(checked(ref).read_bytes())


def old_inactive():
    result = subprocess.run(['systemctl', '--user', 'show', scope.OLD_UNIT, '--no-pager',
        '--property=LoadState,ActiveState,SubState,MainPID'], env=user_manager_environment(),
        capture_output=True, text=True, timeout=20)
    props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if result.returncode or props.get('MainPID') != '0' or props.get('ActiveState') not in {'inactive', 'failed'}:
        raise ValueError('The exact previous primary remains active')
    return {'unit': scope.OLD_UNIT, 'properties': props, 'observed_unix': time.time()}


def terminal_result(row, ref):
    value = load(ref)
    if (value.get('slot_id') != row['slot_id'] or value.get('configuration') != row['configuration']
            or value.get('condition_id') != row['condition_id'] or value.get('model_key') != 'QWEN'
            or value.get('status') not in {'closed', 'technical_unknown'}):
        raise ValueError('Original result identity differs from the fixed task')
    quiet = load(value['quiescence'])
    if (quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []
            or quiet.get('create_result_unknown') is not False or value.get('retained_objects')):
        raise ValueError('The stopped Qwen result is not physically quiet')
    return {'result': ref, 'status': value['status'], 'entered': True,
        'administrative_truncation': False, 'retained_objects': [], 'prior_zero_generation_attempt': None}


def prepare():
    scope.original.require_v066_allowed('v066.run')
    if scope.AUTH_FILE.exists() or scope.INVENTORY_FILE.exists():
        raise FileExistsError('Never overwrite a prepared recovery inventory')
    inactive = old_inactive()
    old_summary_ref = reference(scope.OLD_ROOT/'run-summary.json')
    summary = load(old_summary_ref)
    if (summary.get('failure', {}).get('kind') != 'coordinator_error'
            or summary['failure'].get('error', {}).get('type') != 'JSONDecodeError'):
        raise ValueError('This recovery requires the exact recorded parse failure')
    rows = [row for row in load(reference(scope.original.PLAN_FILE))['rows'] if row['model_key'] == 'QWEN']
    if len(rows) != 3000:
        raise ValueError('Preserve the original complete Qwen six-condition plan')
    by_id = {row['slot_id']: row for row in rows}
    prior = load(summary['continuation_inventory'])
    generations = {slot: entry for slot, entry in summary['generation'].items() if slot in by_id}
    scores, deliveries = dict(summary['scores']), dict(summary['deliveries'])
    claim_root = scope.original.BATCH_ROOT/'resource-claims'
    for path in claim_root.glob('active-*.json'):
        item = load(reference(path))
        if ':QWEN_' in item.get('spec', {}).get('slot_id', ''):
            raise ValueError('A Qwen object still has an active reservation')
    events_ref = reference(scope.OLD_ROOT/'events.jsonl')
    events = [json.loads(line) for line in checked(events_ref).read_bytes().splitlines() if line]
    scheduled = {event['slot_id'] for event in events if event.get('kind') == 'generation_scheduled'}
    eligible, audits, recovered = [], [], []
    roots = (scope.original.PREDECESSOR_ROOT, scope.original.BATCH_ROOT)
    for row in rows:
        slot, index = row['slot_id'], row['slot_index']
        claims = [str(path) for root in roots for role in ('actor', 'controller', 'volume')
                  if (path := root/'resource-claims'/f'{role}-{index}.json').exists()]
        candidates = [root/'episodes'/str(index) for root in roots if (root/'episodes'/str(index)).exists()]
        if slot in generations:
            reason = 'retained_terminal_generation'
        elif slot in scheduled or claims or candidates:
            result_path = scope.original.BATCH_ROOT/'episodes'/str(index)/'result.json'
            if result_path.exists():
                generations[slot] = terminal_result(row, reference(result_path))
                recovered.append(slot)
                reason = 'original_terminal_result_reconciled_after_queue_error'
            else:
                generations[slot] = {'status': 'technical_unknown', 'entered': bool(claims),
                    'error': 'Consumed or scheduled original identity lacks trusted terminal result',
                    'automatic_replay': False, 'actual_model_generation_known': None}
                reason = 'consumed_identity_without_terminal_result_no_replay'
        else:
            eligible.append(slot)
            reason = 'unused_original_identity'
        audits.append({'slot_id': slot, 'slot_index': index, 'reason': reason, 'claims': claims})
    jobs, reconcile = [], []
    for slot, entry in generations.items():
        if entry.get('status') != 'closed':
            continue
        row = by_id[slot]
        if slot not in scores:
            folder = scope.original.GRADING_ROOT/f"score-{row['slot_index']}"
            request = folder/'request.json'
            if request.exists():
                ref, completion, quiet = reference(request), folder/'completion.json', folder/'quiescence.json'
                if load(ref).get('generation_result') != entry['result']:
                    raise ValueError('Original score is bound to another candidate')
                if completion.exists() and quiet.exists() and load(reference(quiet)).get('quiescent') is True:
                    scores[slot] = {'request': ref, 'completion': load(reference(completion))}
                elif (claim_root/f"score-{row['slot_index']}.json").exists():
                    scores[slot] = {'status': 'technical_unknown', 'request': ref,
                        'error': 'Consumed score has incomplete result; no replay'}
                else:
                    jobs.append(['code', row, ref, True])
            else:
                jobs.append(['code', row, entry['result'], False])
        if (row['arm'] == 'PROJECT' and slot in scores and scores[slot].get('request')
                and scores[slot].get('completion') and slot not in deliveries):
            reconcile.append({'slot_id': slot, 'generation_result': entry['result'], 'code_request': scores[slot]['request']})
    usage = {slot: ref for slot, ref in prior['usage_record_files'].items() if slot in generations}
    for path in (scope.OLD_ROOT/'usage-records').glob('*.json'):
        ref = reference(path)
        record = load(ref)
        if record.get('slot_id') in generations:
            usage[record['slot_id']] = ref
    scope.BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    if recovered:
        spec = importlib.util.spec_from_file_location('v084_original_usage_recovery',
            scope.ROOT/'tools/run_full_benchmark_v066.py')
        base = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(base)
        usage_folder = scope.BATCH_ROOT/'recovered-usage-records'
        usage_folder.mkdir()

        class Recorder(base.UsageRecorder):
            def save_record(self, row, record):
                ref = write_new(usage_folder/f"{row['slot_index']}.json", record)
                usage[row['slot_id']] = ref
                self.remember_record(row, record, ref)

            def flush(self, **kwargs):
                pass

        recorder = Recorder(load(reference(scope.original.MATRIX_FILE)), None)
        for slot in recovered:
            row, entry = by_id[slot], generations[slot]
            if slot in usage:
                recorder.remember_record(row, load(usage[slot]), usage[slot])
            try:
                recorder(row, entry, load(entry['result']), scores.get(slot), deliveries.get(slot))
            except Exception as error:
                if (usage_folder/f"{row['slot_index']}.json").exists():
                    raise
                recorder.mark_unknown(row, entry, type(error).__name__+': '+str(error))
    history_ref = write_new(scope.BATCH_ROOT/'predecessor-proof.json', {'version': VERSION,
        'predecessor_summary': old_summary_ref, 'predecessor_events': events_ref,
        'old_inactive': inactive, 'Qwen_owned_active_claims': 0,
        'original_records_modified': False, 'model_services_reloaded': False})
    audit_ref = write_new(scope.BATCH_ROOT/'slot-audit.json', {'version': VERSION, 'rows': audits})
    inventory_ref = write_new(scope.INVENTORY_FILE, {'version': VERSION, 'generation': generations,
        'scores': scores, 'deliveries': deliveries, 'qualifications': summary['qualifications'],
        'allowed_generation_slot_ids': eligible, 'allowed_generation_slot_indices': [by_id[s]['slot_index'] for s in eligible],
        'retry_zero_generation': {}, 'usage_record_files': usage, 'unused_score_jobs': jobs,
        'unused_control_requests': [], 'completed_controls': prior.get('completed_controls', {}),
        'delivery_reconciliation': reconcile, 'exceptions': summary.get('exceptions', []),
        'prior_failure': summary['failure'], 'predecessor_proof': history_ref, 'slot_audit': audit_ref,
        'original_panel_denominator': 3000, 'automatic_replay': False})
    module_spec = importlib.util.spec_from_file_location('v084_owned_launcher', scope.ROOT/'tools/launch_qwen_recovery_v084.py')
    launcher = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(launcher)
    prepared_unit = launcher.prepare()
    plan_ref = write_new(scope.PLAN_FILE, {'version': scope.VERSION,
        'original_plan': reference(scope.original.PLAN_FILE), 'inventory': inventory_ref,
        'planned_Qwen_slots': 3000, 'coordinator_memory_bytes': scope.MEMORY_BYTES,
        'maximum_generation': 4, 'maximum_grading': 1, 'new_model_residencies': 0,
        'unit': prepared_unit['specification'], 'predecessor_proof': history_ref})
    # Bind the actual dependency graph, not every unrelated recovery utility
    # which happens to share this deployment number.
    files = [scope.ROOT/path for path in (
        'src/proworksim/software_benchmark_resources_v084.py',
        'src/proworksim/software_benchmark_episodes_v084.py',
        'src/proworksim/software_benchmark_qwen_scope_v084.py',
        'tools/run_qwen_recovery_v084.py',
        'tools/prepare_qwen_recovery_v084.py',
        'tools/launch_qwen_recovery_v084.py')]
    sources_ref = write_new(scope.SOURCE_FILE, {'version': scope.VERSION, 'files': [reference(path) for path in sorted(files)]})
    auth_ref = write_new(scope.AUTH_FILE, {'version': scope.VERSION, 'status': 'approved',
        'original_authorization': reference(scope.original.AUTHORIZATION_FILE),
        'predecessor_authorization': reference(scope.predecessor.AUTH_FILE), 'plan': plan_ref,
        'source_index': sources_ref, 'model_visible_configuration_unchanged': True,
        'basis': '用户授权自主修复实验故障并提高并发，保留已进入结果、禁止共享主机修改和模型重载'})
    return {'authorization': auth_ref, 'inventory': inventory_ref, 'unused_Qwen_slots': len(eligible),
        'retained_states': dict(Counter(e['status'] for e in generations.values())),
        'original_terminal_results_recovered': recovered,
        'pending_scores': len(jobs), 'new_model_calls': 0, 'unit': prepared_unit}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(prepare(), ensure_ascii=False))
