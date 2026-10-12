"""One read-only final aggregation; no model, tensor, world or measurement replay."""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import shutil
import time
from scripts import software_learning_reporting_v049 as reporting

ROOT = Path.cwd().resolve()
DOC = ROOT / 'docs/experiments'
OLD = DOC / 'software-learning-v049-r1-evidence'
ANALYSIS = ROOT / 'artifacts/software-learning-v049/analysis'
NEW = DOC / 'software-learning-v049-final-evidence'
RUN = ROOT / 'runs/software-learning-v049-dev-resume-r2g'

def read(path):
    return json.loads(path.read_text())

def ref(path):
    data = path.read_bytes()
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

assert not (DOC / 'software-learning-v049-final.json').exists()
plan, supervisor = read(RUN / 'plan.json'), read(RUN / 'supervisor.json')
assert supervisor['status'] == 'complete' and supervisor.get('ended_at')
assert all(v['status'] == 'complete' and v['exit_code'] == 0 for v in supervisor['states'].values())
old = read(OLD / 'original-stage-report.json')
rows = copy.deepcopy(old['rows'])
units = reporting.inventory(plan)
issues, replacements = [], []
for i, (unit, row) in enumerate(zip(units, rows, strict=True)):
    if row['slot_id'] not in ('org49-dev-DB-s1-B', 'org49-dev-DB-s2-B'):
        continue
    assert row['status'] == 'not_started'
    unit['worker'] = 'dev-B-DB-' + ('s1' if '-s1-' in unit['slot_id'] else 's2')
    worker = unit['worker']
    result = reporting._slot(RUN, unit, supervisor['states'][worker], read(RUN / worker / 'actual/report.json'), issues)
    assert result['status'] == 'closed' and result['R_joint'] == 1
    result.update(source_phase='resource_resume_r2g', source_identity=plan['source'],
                  original_not_started_row_preserved_in=ref(OLD / 'original-stage-report.json'))
    rows[i] = result
    replacements.append(unit['slot_id'])
assert not issues
assert replacements == ['org49-dev-DB-s1-B', 'org49-dev-DB-s2-B']
assert all(rows[i] == row for i, row in enumerate(old['rows']) if row['slot_id'] not in replacements)
metrics = reporting.aggregate_rows(units, rows, old['direction'])
metrics['scope'] = 'Original eight training plus four B development units; no admissible I direction was executed; Q branches are conditional not applicable.'
assert metrics['status_counts'] == {'closed': 11, 'technical_unknown': 1, 'conditional_not_applicable': 8}
assert metrics['branches']['B']['F'] is None and metrics['generation']['complete_actual_tokens'] is None
assert metrics['generation']['known_actual_tokens_subtotal'] == 3722098
assert metrics['generation']['budget_charged_tokens'] == 3735147
assert metrics['generation']['known_output_bearing_calls'] == 271
assert metrics['generation']['attempts_started'] == 272
assert metrics['generation']['decisions'] == 277
assert metrics['generation']['uncertain_usage_attempts'] == 1
assert metrics['generation']['prompt_tokens'] == 3639631
assert metrics['generation']['completion_tokens'] == 82467

development = read(ANALYSIS / 'development-four-work-facts-r2g.json')
resource = read(ANALYSIS / 'r2g-execution-resource-audit.json')
assert development['aggregate']['known_complete_response_tokens'] == 889510
assert development['aggregate']['member_tests_known_sum'] == 11
assert development['aggregate']['F_B'] is None
new_workers = [{'worker': name, **{key: state.get(key) for key in ('status', 'attempted', 'gpu', 'gpu_uuid', 'pid', 'process_identity', 'started_at', 'ended_at', 'elapsed_gpu_seconds', 'exit_code')}} for name, state in supervisor['states'].items()]
new_gpu_seconds = sum(row['elapsed_gpu_seconds'] for row in new_workers)
old_gpu_seconds = old['GPU_worker_cost']['complete_worker_seconds']
total_gpu_seconds = old_gpu_seconds + new_gpu_seconds
assert new_gpu_seconds == development['aggregate']['new_r2g_development_worker_seconds']

NEW.mkdir(exist_ok=False)
archive = []
for name in ('development-four-work-facts-r2g.json', 'development-four-work-facts-r2g.md', 'r2g-execution-resource-audit.json', 'r2g-execution-resource-audit.md', 'summarize_development_four_r2.py', 'build-final-report.py', 'final-training-method-draft.md'):
    source = ANALYSIS / name
    target = NEW / name
    shutil.copyfile(source, target)
    archive.append({'source': str(source), 'durable': ref(target), 'same_original_bytes': target.read_bytes() == source.read_bytes()})
write(NEW / 'manifest.json', {'version': 'v049-final-readonly-evidence-archive', 'files': archive, 'original_bytes_preserved': True, 'new_model_calls': 0, 'new_GPU_calls': 0, 'new_tensor_reads': 0, 'new_acceptances': 0})
method = (ANALYSIS / 'final-training-method-draft.md').read_text()
method = method.replace('# v049 最终训练与方法证据草稿', '# v049 训练方法、实际更新与完整状态证据').replace('本草稿', '本文').replace('本最终草稿', '本文')
(DOC / 'software-learning-v049-final-method.md').write_text(method)

report = {
    'version': 'software-learning-v049-final-original-inventory-r2g',
    'generated_at': time.time(),
    'status': 'authorized_inventory_finished_with_one_preserved_technical_unknown',
    'scope': 'One original strict O1 Gamma1 learning window. All applicable slots attempted once; DA-s2 incomplete remains unknown. No automatically added work.',
    'original_design': old['design'],
    'source_phases': {'original': old['GPU_worker_cost']['original_phase'], 'r1': old['GPU_worker_cost']['r1_phase'], 'r2_wait_only': {'plan': ref(ROOT / 'runs/software-learning-v049-dev-resume-r2/plan.json'), 'stop': ref(ROOT / 'runs/software-learning-v049-dev-resume-r2/gpu-scope-amendment-stop.json'), 'new_model_calls': 0, 'GPU_worker_seconds': 0}, 'r2g': {'plan': ref(RUN / 'plan.json'), 'supervisor': ref(RUN / 'supervisor.json'), 'source': plan['source'], 'workers': new_workers}},
    'rows': rows,
    'metrics': metrics,
    'formal_outcome_counts': {'applicable_slots_started': 12, 'known_R1': 11, 'known_R0': 0, 'technical_unknown': 1, 'conditional_not_applicable': 8, 'unstarted_applicable': 0},
    'observed_member_tests_supplement': {'training': 26, 'development': 11, 'total': 37, 'DA_s2_tests_observed': 0, 'original_reader_null_preserved': True, 'scope': 'Existing test ledgers show 37 tests executed; old report public_member_tests for DA2 remains null in its original row. No new acceptance run.', 'development_proof': ref(NEW / 'development-four-work-facts-r2g.json')},
    'training_update': {'B': old['updates']['B'], 'Q_plus': old['updates']['Q_plus'], 'Q_minus': old['updates']['Q_minus'], 'totals': old['new_update_totals'], 'native_actor_wrapper_forwards_completed': 414, 'native_gradient_forwards_completed': 206, 'native_no_grad_forwards_completed': 208, 'actor_backward_calls': 206, 'critic_backward_calls': 206, 'actor_optimizer_steps': 1, 'critic_optimizer_steps': 1, 'r2_or_r2g_new_update_steps': 0, 'full_B_worker_seconds': 30103.32239460945, 'nested_updater_interval_seconds': 29529.820029708557, 'nested_interval_not_added_twice': True},
    'support': old['support'],
    'direction': old['direction'],
    'state_comparison': {'independent_complete_saved_state_CPU_comparison_executed_once': True, 'proof': ref(OLD / 'S0-B-saved-state-comparison.json'), 'original_reporter_comparison_flag_preserved': old['complete_tensor_checkpoint_comparison_executed'], 'comparison_repeated_for_final_report': False, 'tensor_reads_by_this_report': 0},
    'GPU_worker_cost': {'original_and_r1_seconds_once': old_gpu_seconds, 'r2_wait_only_seconds': 0, 'r2g_seconds': new_gpu_seconds, 'complete_worker_seconds': total_gpu_seconds, 'complete_worker_hours': total_gpu_seconds / 3600, 'original_and_r1_breakdown': old['GPU_worker_cost'], 'r2g_workers': new_workers, 'scope': 'Assigned GPU worker intervals including loading/collection/update/evaluation; not utilization. No addition of nested episode or update durations.'},
    'development_fact_proof': ref(NEW / 'development-four-work-facts-r2g.json'),
    'resource_execution_proof': ref(NEW / 'r2g-execution-resource-audit.json'),
    'generation_stage_totals': {'training_original5': {'calls': 119, 'tokens': 1617987, 'tests': 14}, 'training_r1_new3': {'calls': 87, 'tokens': 1214601, 'tests': 12}, 'development_r1_DA': {'known_complete_calls': 37, 'attempts_started': 38, 'known_actual_tokens': 531273, 'budget_charged_tokens': 544322, 'full_actual_tokens': None, 'tests': 7}, 'r2_wait_only': {'calls': 0, 'tokens': 0, 'tests': 0}, 'development_r2g_DB': {'calls': 28, 'tokens': 358237, 'tests': 4}},
    'original_r1_snapshot': ref(OLD / 'original-stage-report.json'),
    'all_retained_non_DB_rows_exactly_unchanged': True,
    'old_costs_counted_once': True,
    'original_unknown_and_stops_preserved': True,
    'source_scope_resource_change_is_policy_improvement': False,
    'B_improvement_over_S0_established': False,
    'Contribution_sensitivity_estimated': False,
    'read_only_report': True,
    'new_model_calls': 0,
    'new_GPU_calls': 0,
    'new_backward_calls': 0,
    'new_test_or_acceptance_calls': 0,
    'new_tensor_reads': 0,
    'evidence_issues': issues,
    'automatic_successors': [],
    'old_queues_remain_paused': True,
    'reporter_snapshot': ref(NEW / 'build-final-report.py'),
}
write(DOC / 'software-learning-v049-final.json', report)
print(json.dumps({'metrics': metrics['generation'], 'counts': report['formal_outcome_counts'], 'GPU_worker_seconds': total_gpu_seconds, 'GPU_worker_hours': total_gpu_seconds / 3600, 'new_DB_tokens': 358237, 'final_json': ref(DOC / 'software-learning-v049-final.json')}, ensure_ascii=False))
