"""Read-only audit of the latest aligned REF baseline; no runtime imports."""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/software-benchmark-v124/ref-audit-r1'
OLD = ROOT / 'runs/software-benchmark-v111/aligned-interface-r1'
GAP = ROOT / 'artifacts/software-benchmark-v114/gap-evidence-recovery-r1'
LEDGER = ROOT / 'runs/software-benchmark-v105/nonthinking-interface-r1/api-ledger.sqlite'
VERSION = 'v124-aligned-ref-existing-results-audit-r1'
FIELDS = ('prompt_tokens', 'completion_tokens', 'total_tokens',
          'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens')
SOURCES = {}


def load(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    SOURCES[str(path)] = {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    return json.loads(raw)


def load_ref(ref):
    value = load(ref['path'])
    if SOURCES[str(Path(ref['path']).resolve())] != ref:
        raise ValueError('Frozen reference changed: ' + ref['path'])
    return value


def main():
    if OUT.exists():
        raise FileExistsError('Keep the original audit snapshot; use a new revision for later evidence')
    strict = [row for row in load(GAP / 'strict-original-episodes.json') if row['arm'] == 'REF']
    status = Counter('passed' if row['code_result'] is True else
                     'failed' if row['code_result'] is False else 'unknown' for row in strict)
    assert len(strict) == 50 and status == {'passed': 33, 'failed': 13, 'unknown': 4}
    by_slot = {row['slot_id']: row for row in strict}
    original_plan = load(OLD / 'execution-plan-v113.json')
    plan_by_id = {row['slot_id']: row for row in original_plan['rows']}
    supplemental = load(GAP / 'supplemental-stopped-code.json')
    stopped = supplemental['records']
    assert len(stopped) == 2 and supplemental['included_in_primary'] is False
    for row in stopped:
        assert row['code_result'] is False and row['measurement_kind'] == 'recovered_stopped_code'
        assert by_slot[row['slot_id']]['code_result'] is None
        load_ref(row['evidence'])
    overrides = load(ROOT / 'artifacts/software-benchmark-v114/recovery-score-inputs-r1/score-overrides.json')
    for row in overrides:
        assert by_slot[row['slot_id']]['code_result'] == row['code_result']
        load_ref(row['evidence'])

    db = sqlite3.connect(LEDGER.as_uri() + '?mode=ro', uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        groups = [dict(row) for row in db.execute("""SELECT condition,COUNT(*) requests,
            COUNT(DISTINCT slot_id) tasks,MIN(reserved_utc) first_utc,MAX(reserved_utc) last_utc
            FROM requests WHERE condition LIKE '%REF%' GROUP BY condition ORDER BY last_utc""")]
        records = [dict(row) for row in db.execute("""SELECT request_id,slot_id,usage_id,status,usage_json,
            settled_nanoyuan,reserved_utc FROM requests
            WHERE condition='DEEPSEEK_NT_REF_ALIGNED_B5000K' ORDER BY request_id""")]
    finally:
        db.close()
    assert len(records) == 4096 and all(row['status'] == 'settled' for row in records)
    assert {row['slot_id'] for row in records} == {row['slot_id'] for row in strict if row['requests']}
    assert groups[-1]['condition'] == 'DEEPSEEK_NT_REF_ALIGNED_B5000K'
    totals = {key: 0 for key in FIELDS}
    purposes, tasks = {}, {}
    for row in records:
        usage = json.loads(row['usage_json'])
        assert usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens']
        purpose = purposes.setdefault(row['usage_id'], {'requests': 0, 'cost_nanoyuan': 0,
                                                       **dict.fromkeys(FIELDS, 0)})
        task = tasks.setdefault(row['slot_id'], {'requests': 0, 'cost_nanoyuan': 0,
                                                 **dict.fromkeys(FIELDS, 0)})
        for key in FIELDS:
            totals[key] += usage[key]
            purpose[key] += usage[key]
            task[key] += usage[key]
        for item in (purpose, task):
            item['requests'] += 1
            item['cost_nanoyuan'] += row['settled_nanoyuan']
    assert len(tasks) == 48 and totals['total_tokens'] == 101_558_226
    assert set(purposes) == {'agent', 'condenser'}
    for slot, task in tasks.items():
        assert task['total_tokens'] == by_slot[slot]['total_tokens']
        assert task['requests'] == by_slot[slot]['requests']
    continuation = {}
    for version in ('v114', 'v115'):
        index = load(OLD / f'api-coordinator-{version}/actual-usage-records.json')
        entries = []
        for slot, ref in index['record_files'].items():
            if ':DEEPSEEK_NT_REF_' in slot:
                usage = load_ref(ref)
                assert not usage.get('calls') and not usage.get('unresolved_calls')
                entries.append({'slot_id': slot, 'calls': 0, 'unresolved_calls': 0})
        continuation[version] = entries
    old_condition = load(OLD / 'conditions/REF.json')
    new_condition = load(ROOT / 'runs/software-benchmark-v118/project-repaired-r1/conditions/PROJECT.json')
    assert old_condition['inference'] == new_condition['inference']
    assert old_condition['episode_limits'] == new_condition['episode_limits']
    assert old_condition['dataset_revision'] == new_condition['dataset_revision']
    cost = sum(row['settled_nanoyuan'] for row in records)
    summary = {'version': VERSION, 'observed_utc': datetime.now(timezone.utc).isoformat(),
        'strict_original_REF': {'planned': 50, 'called': 48, 'scored': 46, **dict(status),
            'confirmed_success_lower_bound': 33 / 50, 'unknown_assignment_range': [33 / 50, 37 / 50],
            'complete_main_point_estimate': None, 'range_is_confidence_interval': False},
        'unknown_tasks': [{'slot_index': plan_by_id[row['slot_id']]['slot_index'],
            'instance_id': row['instance_id'], 'slot_id': row['slot_id'],
            'generation_state': row['generation_state'], 'requests': row['requests'],
            'known_total_tokens': row['total_tokens'], 'reason': row['termination']}
            for row in strict if row['code_result'] is None],
        'ordinary_locked_candidate_rescores_included': overrides,
        'stopped_candidates_supplemental_only': stopped,
        'supplemental_endpoint_counts': {'passed': 33, 'failed': 15, 'not_started': 2},
        'usage': {'planned_tasks': 50, 'mean_denominator': 48,
            'includes_failed_and_generation_unknown_tasks': True,
            'includes_agent_and_condenser': True, 'includes_neutral_preparation': False,
            'all_requests_settled': True, 'requests': len(records), 'totals': totals,
            'per_called_task_exact_means': {key: format(Decimal(value) / 48, 'f') for key, value in totals.items()},
            'cost_nanoyuan': cost, 'cost_CNY': format(Decimal(cost) / 1_000_000_000, 'f'),
            'by_purpose': purposes},
        'later_REF_generation_check': {'same_unique_ledger_REF_groups': groups,
            'v114_v115_continuation_records': continuation,
            'no_new_aligned_REF_requests_after_original_v113': True,
            'current_latest_REF_is_original_v113_with_v114_locked_rescores': True,
            'scope': 'current experiment canonical ledger and preserved v114/v115 continuation indices'},
        'common_configuration': {'model': old_condition['model'], 'thinking': False,
            'single_agent': True, 'dataset_revision': old_condition['dataset_revision'],
            'inference': old_condition['inference'], 'episode_limits': old_condition['episode_limits'],
            'SDK_version': old_condition['execution_strategy']['SDK_version'],
            'API_checkpoint_hash_pinnable': False},
        'comparison_limits': [
            'REF is frozen v110/v113; current PROJECT uses repaired v117/v120, including different review/workflow text, observation projection, navigation/rejection handling and public fixture preparation.',
            'Same nominal context, I/O limits, token budget and sampling do not make tool capability or one decision equivalent: native shell versus managed operations, versioned test/patch/delivery rules.',
            'Current PROJECT fifty-task view combines 23 first generations, 18 closed v121 independent recoveries and nine separately authorized v123 independent attempts; report this lifecycle composition and retain all earlier costs.',
            'Both groups use the same task panel but REF has only 48 called and 46 strictly scored tasks. Compare the common strictly scored set separately; a 50-task PROJECT mean is not the identical task denominator to REF mean48.',
            'The two stopped-code supplemental false scores must remain separate; do not silently replace the strict REF generation unknowns.',
            'New PROJECT uses different local seeds and later API calls; provider seed is not sent. Differences combine repairs and stochastic/run-stage effects, not a single interface causal effect.',
            'A repaired PROJECT versus old REF comparison is a calibration comparison, not a fresh concurrent randomized or independent confirmation evaluation.'
        ],
        'condition_differences': {'REF': old_condition, 'PROJECT': new_condition},
        'ledger_path': str(LEDGER), 'ledger_snapshot_read_only': True,
        'queried_REF_rows_sha256': hashlib.sha256(json.dumps(records, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'model_calls': 0, 'Docker_operations': 0, 'old_records_changed': False}
    OUT.mkdir(parents=True, exist_ok=False)
    with (OUT / 'summary.json').open('x') as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    with (OUT / 'per-task.json').open('x') as stream:
        json.dump([{'slot_id': row['slot_id'], 'instance_id': row['instance_id'],
            'slot_index': plan_by_id[row['slot_id']]['slot_index'], 'repo': row['repo'],
            'code_result': row['code_result'], 'generation_state': row['generation_state'],
            'usage': tasks.get(row['slot_id']), 'mean_denominator_included': row['slot_id'] in tasks}
            for row in strict], stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    with (OUT / 'sources.json').open('x') as stream:
        json.dump({'sources': list(SOURCES.values()), 'script': str(Path(__file__).resolve())},
                  stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'summary': str(OUT / 'summary.json'), 'strict': dict(status),
                      'mean_denominator': 48, 'totals': totals}, ensure_ascii=False))


if __name__ == '__main__':
    main()
