"""Read-only R2 evaluation report and isolated terminal archive.

Read saved assessments and checkpoint metadata only. Never load model tensors,
replay a world, rescore an episode or modify either previous attempt.
"""

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import time

from proworksim.storage import read_json
from scripts.composition_evidence_v025 import checked
from scripts.evaluate_work_v022 import write
from scripts.report_composition_recovery_v025 import (
    closed_episode_count,
    confirmation,
    same_ref,
    terminal,
    validate_catalog,
)
from scripts.report_domain_v022 import calls, read, reference, resources
from scripts.report_learning_v023 import index_progress

VERSION = 'postupdate-evaluation-resume-v0.25-r2'
STAGES = ('confirm_base', 'next_base')
FILES = [
    'docs/experiments/composition-pilot-v025-r2.json',
    'docs/experiments/composition-pilot-v025-r2.md',
]


def nonnegative(value, label):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(label + ' must be a finite nonnegative quantity')
    return value


def continuation(root, catalog, actor):
    folder = root / 'next_base' / 'actual'
    rows = read(folder / 'collection/progress.json', [])
    indexed = index_progress(rows, catalog['continuation_slots'])
    guard = read(folder / 'state-guard.json')
    declaration = read(folder / 'collection/declaration.json', {})
    declaration_actor = declaration.get('actor_identity')
    result = []
    for slot in catalog['continuation_slots']:
        row = indexed.get(slot['slot_id'])
        reward = row.get('reward', {}) if row else {}
        known = bool(row and row.get('status') == 'closed'
                     and row.get('record_validity') is True
                     and reward.get('eligible') is True
                     and reward.get('independent_assessability') == 'known'
                     and type(reward.get('completed')) is bool
                     and declaration_actor == actor)
        if known:
            preparation = read(folder / 'collection' / slot['slot_id'] / 'preparation.json', {})
            if preparation.get('prepared_business_state_sha256') != row.get('initial_business_state_sha256'):
                raise ValueError('Continuation initial state differs from its recorded preparation')
        result.append({**slot, 'status': row.get('status') if row else 'not_started',
                       'known': known, 'completed': reward.get('completed') if known else None,
                       'reward': reward.get('reward') if known else None,
                       'error': row.get('error') if row else None})
    verified = bool(len(rows) == 2 and all(r['known'] for r in result)
                    and guard and guard.get('learning_unchanged') is True
                    and guard.get('rng_restored_exactly') is True)
    return {'planned': 2, 'started': len(rows), 'known': sum(r['known'] for r in result),
            'unknown_started': sum(r['status'] != 'not_started' and not r['known'] for r in result),
            'not_started': 2-len(rows), 'rows': result, 'raw_progress': rows,
            'closed_episode_boundaries': closed_episode_count(folder / 'collection', catalog['continuation_slots']),
            'state_guard': guard, 'zero_extra_updates_verified': verified,
            'support': read(folder / 'support.json'),
            'references': {name: reference(folder / name) for name in
                           ('collection/progress.json', 'collection/declaration.json', 'state-guard.json', 'support.json')}}


def report(root, plan_path):
    root, plan_path = Path(root).resolve(), Path(plan_path).resolve()
    plan, supervisor = read_json(plan_path), read_json(root / 'supervisor.json')
    if plan.get('version') != VERSION or checked(supervisor['plan']).resolve() != plan_path:
        raise ValueError('R2 supervisor must bind its separate frozen evaluation-only plan')
    if supervisor.get('worker_source') != plan['worker_source']:
        raise ValueError('R2 worker source differs from the preserved R1 source')
    prior_root = Path(plan['prior_run']).resolve()
    if root == prior_root or root.is_relative_to(prior_root):
        raise ValueError('R2 must not overwrite or nest within R1')
    previous = read_json(checked(plan['prior_supervisor']))
    worker_plan = read_json(checked(plan['worker_plan']))
    marker = read_json(checked(plan['base_marker']))
    saved = read_json(checked(plan['checkpoint']))
    checked(plan['failed_confirmation'])
    if plan.get('failed_progress'):
        checked(plan['failed_progress'])
    if (not previous.get('ended_at') or previous.get('source') != plan['worker_source']
            or not same_ref(previous.get('plan'), plan['worker_plan'])
            or marker.get('source') != plan['worker_source'] or marker.get('label') != 'base'
            or not same_ref(marker.get('checkpoint'), plan['checkpoint'])
            or saved.get('actor_steps') != 3 or saved.get('critic_steps') != 3
            or saved.get('actor_identity') != marker.get('actor_identity')
            or saved.get('serialized_reload_exact') is not True):
        raise ValueError('R2 must read the complete, exact R1 post-update endpoint at 3/3')
    checked(saved['state'])
    if reference(root / 'checkpoints/base.json')['sha256'] != plan['base_marker']['sha256']:
        raise ValueError('R2 endpoint marker must retain the original R1 bytes and paths')
    actor = marker['actor_identity']
    prior_confirm_state = read_json(prior_root / 'confirm_base/state.json')
    failed_cost = nonnegative(prior_confirm_state.get('elapsed_gpu_seconds'), 'R1 failed confirmation cost')
    prior_gpu = nonnegative(plan['previous_gpu_seconds'], 'Previous cumulative GPU cost')
    if not math.isclose(prior_gpu, previous.get('cumulative_terminated_gpu_seconds', -1), abs_tol=1e-6, rel_tol=0):
        raise ValueError('R2 previous cost must include the original attempt and all of R1')
    caps = plan['resource_caps']
    if (set(caps) != set(STAGES)
            or not math.isclose(caps['confirm_base'], 16200-failed_cost, abs_tol=1e-6, rel_tol=0)
            or caps['next_base'] != 3600):
        raise ValueError('R2 keeps only the unspent confirmation and continuation allocations')
    catalog = read_json(checked(worker_plan['catalog']))
    validate_catalog(catalog)
    old_rows = read(prior_root / 'confirm_base/actual/progress.json', [])
    old_index = index_progress(old_rows, catalog['confirmation_slots'])
    if (len(old_rows) != 1 or old_rows[0].get('slot_id') != catalog['confirmation_slots'][0]['slot_id']
            or old_rows[0].get('status') != 'interrupted_or_unassessed'):
        raise ValueError('R2 retry must preserve exactly the recorded unknown first confirmation attempt')
    for row in old_rows:
        if row.get('assessment_ref') and read_json(checked(row['assessment_ref'])) != row.get('assessment'):
            raise ValueError('Original failed assessment has changed')
    old_worker = read_json(prior_root / 'confirm_base/actual/report.json')
    confirm = confirmation(root, catalog, actor)
    confirm['interpretation'] = ('Same R1 post-update endpoint on the original twelve fixed confirmation slots. '
        'The original unknown first attempt is preserved separately; its same-slot same-seed retry is not a new situation.')
    confirm_progress = read(root / 'confirm_base/actual/progress.json', [])
    confirm_index = index_progress(confirm_progress, catalog['confirmation_slots'])
    confirm.update(started=len(confirm_progress), not_started=12-len(confirm_progress),
                   unknown_started=len(confirm_progress)-confirm['known'])
    retry = []
    for key, old_row in old_index.items():
        new_row = confirm_index.get(key)
        if new_row and new_row.get('initial_business_state_sha256') != old_row.get('initial_business_state_sha256'):
            raise ValueError('R2 retry changed the original initial business state')
        retry.append({'slot_id': key, 'case_id': old_row['case_id'], 'seed': old_row['seed'],
                      'prior_status': old_row['status'], 'R2_status': new_row.get('status') if new_row else 'not_started',
                      'same_initial_state': True if new_row else None, 'new_situation': False})
    next_result = continuation(root, catalog, actor)
    closed = bool(supervisor.get('ended_at')) and supervisor.get('status') in {
        'complete', 'closed_with_incomplete_stages', 'supervisor_error'}
    stages, costs = {}, {}
    for name in STAGES:
        folder = root / name
        state, worker = read(folder / 'state.json', {}), read(folder / 'actual/report.json', {})
        for field in ('source_before', 'source_after'):
            if worker.get(field) not in (None, plan['worker_source']):
                raise ValueError('Frozen worker imported a different source tree')
        if worker.get('plan') and not same_ref(worker['plan'], plan['worker_plan']):
            raise ValueError('Worker no longer uses the immutable R1 plan')
        if worker.get('actor_steps') not in (None, 3) or worker.get('critic_steps') not in (None, 3):
            raise ValueError('Evaluation-only R2 changed the optimizer step count')
        if worker.get('final_actor_identity') not in (None, actor):
            raise ValueError('Evaluation-only R2 changed the actor endpoint')
        ended = terminal(state, closed)
        elapsed = state.get('elapsed_gpu_seconds')
        if elapsed is not None:
            nonnegative(elapsed, name + ' cost')
        costs[name] = elapsed if ended and elapsed is not None else 0 if ended and state.get('attempted') is False else None
        stages[name] = {'terminal': ended, 'state': state, 'worker_status': worker.get('status'),
                        'worker_error': worker.get('error'), 'worker_source_unchanged': worker.get('source_unchanged'),
                        'actor_steps': worker.get('actor_steps'), 'critic_steps': worker.get('critic_steps'),
                        'actual_final_actor_identity': worker.get('final_actor_identity'),
                        'resources': resources(folder / 'resources.jsonl', state),
                        'resident_calls': calls(folder / 'actual'),
                        'references': {item: reference(folder / item) for item in
                                       ('state.json', 'actual/report.json', 'model.log')}}
    execution_terminal = closed and all(s['terminal'] for s in stages.values())
    final_cost = math.fsum(costs.values()) if execution_terminal and all(v is not None for v in costs.values()) else None
    known_cost = math.fsum(v for v in costs.values() if v is not None)
    if final_cost is not None:
        if not math.isclose(final_cost, supervisor.get('terminated_gpu_seconds', -1), rel_tol=0, abs_tol=1e-6):
            raise ValueError('R2 final stage costs differ from supervisor accounting')
        if not math.isclose(prior_gpu+final_cost, supervisor.get('cumulative_terminated_gpu_seconds', -1), rel_tol=0, abs_tol=1e-6):
            raise ValueError('Cumulative costs must retain both earlier attempts')
    protocol = bool(execution_terminal and confirm['known'] == 12 and next_result['zero_extra_updates_verified']
                    and all(s['state'].get('status') == 'complete' and s['worker_status'] == 'complete'
                            and s['worker_source_unchanged'] is True and s['actor_steps'] == 3 and s['critic_steps'] == 3
                            and s['actual_final_actor_identity'] == actor for s in stages.values()))
    return {'version': VERSION, 'generated_at_epoch': time.time(), 'run_root': str(root),
            'source': supervisor['source'], 'worker_source': plan['worker_source'],
            'report_kind': 'closed_evaluation_resume_complete' if protocol else 'closed_incomplete' if execution_terminal else 'snapshot',
            'execution_terminal': execution_terminal, 'evaluation_resume_complete': protocol,
            'parameter_learning_effect': None, 'planned_primary_composition_difference': None,
            'endpoint': {'marker': marker, 'saved_metadata': saved, 'actor_identity': actor},
            'training': {'R2_new_training_episodes': 0, 'R2_new_actor_steps': 0, 'R2_new_critic_steps': 0,
                         'inherited_actor_steps': 3, 'inherited_critic_steps': 3,
                         'scope': 'R1 already completed the original 283 decisions and saved its update; R2 only restores that endpoint.'},
            'previous_attempt': {'run_root': str(prior_root), 'failure_preserved': True,
                                 'confirmation_progress': old_rows, 'worker_error': old_worker.get('error'),
                                 'references': {name: reference(prior_root / 'confirm_base' / name) for name in
                                                ('state.json', 'actual/report.json', 'actual/progress.json',
                                                 'actual/confirm-00-0/runtime.json')},
                                 'retry_binding': retry, 'failure_counted_as_zero': False,
                                 'assessment_reused_as_success': False},
            'confirmation': confirm, 'continuation': next_result, 'stages': stages,
            'counts': {'fixed_confirmation_slots': 12, 'fixed_continuation_slots': 2,
                       'R2_confirmation_started': len(confirm_progress), 'R2_continuation_started': next_result['started'],
                       'prior_confirmation_attempts': len(old_rows),
                       'cumulative_confirmation_attempts': len(old_rows)+len(confirm_progress),
                       'new_unique_situations_from_retry': 0},
            'accounting': {'previous_gpu_seconds': prior_gpu, 'prior_failed_confirmation_gpu_seconds': failed_cost,
                           'R2_gpu_seconds_by_stage': costs, 'R2_known_terminated_gpu_seconds': known_cost,
                           'R2_final_gpu_seconds': final_cost,
                           'cumulative_known_terminated_gpu_seconds': prior_gpu+known_cost,
                           'cumulative_final_gpu_seconds': prior_gpu+final_cost if final_cost is not None else None,
                           'R2_resource_caps': caps, 'R2_remaining_allocation_seconds': math.fsum(caps.values()),
                           'model_api_calls': 0,
                           'scope': 'R1 confirmation failure reduces the original 4.5-hour confirmation allocation; continuation retains one hour. No training budget is transferred. All loads, retries and failed stages remain additive.'},
            'references': {**{k: plan[k] for k in ('prior_supervisor', 'worker_plan', 'base_marker', 'checkpoint', 'failed_confirmation')},
                           'supervisor': reference(root / 'supervisor.json'), 'plan': supervisor['plan'],
                           'catalog': worker_plan['catalog'], 'reporter': reference(Path(__file__))},
            'scope': 'Read-only saved records, no world replay, scoring or tensor loading. Confirmation is descriptive at one post-update endpoint; no paired pre-update observations or supported configuration comparison establish learning improvement.'}


def markdown(r):
    c, n, a = r['confirmation'], r['continuation'], r['accounting']
    def show(value):
        return '未知' if value is None else str(value)

    lines = ['# v0.25 R2：完成更新后的确认与后继恢复', '',
             f"状态：`{r['report_kind']}`；执行已终止：{r['execution_terminal']}。", '',
             'R1 已完成原窗口 283 个决定并保存 actor/critic=3/3 的完整检查点。R2 仅恢复这个端点，执行原定 12 个确认槽和 2 个后继槽，新增训练、actor 更新和 critic 更新均为 0。', '',
             'R1 首个确认槽因临时目录空间不足而留下不可评分记录，原记录及成本完整保留。本次沿用相同槽、情境和随机种子重新执行；重试不增加独特情境数。临时目录迁移到本轮 data1 目录，工作语义、冻结模型与评价代码沿用 R1。', '',
             f"确认：可评分 {c['known']}/12，已启动但未知 {c['unknown_started']}，未运行 {c['not_started']}；完整职责 {c['complete_responsibilities']}。全 12 槽完成比例：{show(c['completed_fraction'])}。未知不填 0，未运行不记为失败。", '',
             '| 业务条件 | 可评分 / 计划 | 完整职责 |', '|---|---:|---:|']
    for label, value in c['business_conditions'].items():
        lines.append(f"| {label} | {value['known']}/{value['planned']} | {value['complete_responsibilities']} |")
    lines += ['', '| 确认槽 | 状态 | 完整职责 |', '|---|---|---|']
    for row in c['rows']:
        value = row['outcome']
        status = '可评分' if value['known'] else '未运行' if value.get('reason') == 'not_observed' else '已启动但未知'
        lines.append(f"| {row['slot_id']} | {status} | {show(value['value'])} |")
    lines += ['', f"后继：可评分 {n['known']}/2，已启动但未知 {n['unknown_started']}，未运行 {n['not_started']}；世界边界闭合 {n['closed_episode_boundaries']}/2。无额外更新的状态保护核验：{n['zero_extra_updates_verified']}。", '',
              '预定配置主点估计及参数学习收益均为 null。原窗口没有受支持的重配块，且这些确认槽没有更新前配对评价；本轮只能描述同一更新后端点的工作情况。', '',
              '| 资源成本 | GPU 小时 |', '|---|---:|',
              f"| 原 v0.25 与 R1 累计 | {a['previous_gpu_seconds']/3600:.6f} |",
              f"| 其中 R1 首次确认失败（已含在上一行） | {a['prior_failed_confirmation_gpu_seconds']/3600:.6f} |",
              f"| R2 已终止阶段成本 | {a['R2_known_terminated_gpu_seconds']/3600:.6f} |",
              f"| R2 完整成本 | {show(a['R2_final_gpu_seconds']/3600 if a['R2_final_gpu_seconds'] is not None else None)} |",
              f"| 累计完整成本 | {show(a['cumulative_final_gpu_seconds']/3600 if a['cumulative_final_gpu_seconds'] is not None else None)} |", '',
              f"R2 确认上限 {a['R2_resource_caps']['confirm_base']/3600:.6f} GPU 小时，后继上限 1 GPU 小时；前者已扣除 R1 确认失败的实际消耗，不转用闲置训练额度。", '',
              f"原失败确认：`{r['previous_attempt']['run_root']}/confirm_base`。本轮：`{r['run_root']}`。", '',
              f"监督器代码：`{r['source']['code_commit']}`；实际模型工作人员仍运行原冻结 R1 代码：`{r['worker_source']['code_commit']}`。", '',
              '报告只读取已保存的评价、状态保护和检查点元数据，不重新运行世界、不重新评分、不加载模型张量。逐槽证据、原失败、资源竞争和完整引用保存在同名 JSON。', '']
    return '\n'.join(lines)


def archive(root, plan_path):
    root, plan_path = Path(root).resolve(), Path(plan_path).resolve()
    plan = read_json(plan_path)
    r = report(root, plan_path)
    if not r['execution_terminal']:
        raise ValueError('R2 terminal archive requires both evaluation stages to have stopped')
    settings = plan['terminal_archive']
    checkout = Path(settings['checkout']).resolve()
    files = [settings['json'], settings['markdown']]
    if files != FILES:
        raise ValueError('R2 archive may write only its separate fixed report pair')
    outputs = [(checkout / p).resolve() for p in files]
    if any(not p.is_relative_to(checkout / 'docs/experiments') or p.exists() for p in outputs):
        raise ValueError('R2 reports must be new files, never overwrite previous reports')
    record = {'started_at': time.time(), 'status': 'writing_reports', 'files': files,
              'supervisor_source': r['source'], 'worker_source': r['worker_source'],
              'only_two_new_R2_reports_staged': True, 'previous_reports_overwritten': False}
    write(root / 'archive-status.json', record)
    try:
        outputs[0].parent.mkdir(parents=True, exist_ok=True)
        with outputs[0].open('x') as out:
            out.write(json.dumps(r, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
        with outputs[1].open('x') as out:
            out.write(markdown(r))
        record['status'] = 'reports_written'
        write(root / 'archive-status.json', record)
        if settings['git_commit_and_push']:
            env = {**os.environ, 'CUDA_VISIBLE_DEVICES': ''}
            branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=checkout, text=True, env=env).strip()
            if branch != 'main':
                raise ValueError('R2 archive will not switch or publish a different branch')
            subprocess.run(['git', 'add', '--', *files], cwd=checkout, env=env, check=True)
            subprocess.run(['git', 'diff', '--cached', '--check', '--', *files], cwd=checkout, env=env, check=True)
            subprocess.run(['git', 'commit', '--only', '-m', 'Archive v0.25 R2 frozen-endpoint evaluation and cumulative costs',
                            '--', *files], cwd=checkout, env=env, check=True, timeout=60)
            record['archive_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True, env=env).strip()
            subprocess.run(['git', 'push', 'origin', 'main'], cwd=checkout, env=env, check=True, timeout=120)
            record['status'] = 'committed_and_pushed'
    except BaseException as error:
        record.update(status='archive_failed', error={'type': type(error).__name__, 'message': str(error)})
    record['ended_at'] = time.time()
    write(root / 'archive-status.json', record)
    print(json.dumps(record, ensure_ascii=False), flush=True)
    return 0 if record['status'] in {'reports_written', 'committed_and_pushed'} else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    args = parser.parse_args()
    return archive(args.run, args.plan)


if __name__ == '__main__':
    raise SystemExit(main())
