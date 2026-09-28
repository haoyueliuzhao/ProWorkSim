"""Read-only v024 MC/Handoff-RTG report: no model, replay, grading or tensor load."""
import argparse
from collections import Counter
import copy
import json
import math
from pathlib import Path
import time

from proworksim.storage import digest, json_bytes
from scripts.report_domain_v022 import calls, pick, read, reference, resources
from scripts.report_learning_v023 import auxiliary, finite, index_progress, outcome, pinned, stage_terminal

VERSION = 'paired-temporal-credit-report-v0.24'
STAGES = ('eval_initial', 'common', 'train_mc', 'train_handoff_rtg', 'eval_mc', 'eval_handoff_rtg')
ENDPOINTS = ('initial', 'mc', 'handoff_rtg')
ARMS = {'mc': 'terminal_mc', 'handoff_rtg': 'joint_reward_to_go'}
TASKS = ('joint_a', 'joint_b', 'maintenance')
ACCEPTED = {'updated', 'zero_step_zero_actor_advantage_or_gradient', 'zero_step_no_admitted_own_actions'}


def validate_catalog(catalog):
    cases, slots = catalog['evaluation_cases'], catalog['evaluation_slots']
    if (len(cases) != 6 or len({c['case_id'] for c in cases}) != 6 or len(slots) != 12
            or len({s['slot_id'] for s in slots}) != 12
            or len({(s['case_id'], s['seed']) for s in slots}) != 12
            or Counter(c['task'] for c in cases) != Counter(dict.fromkeys(TASKS, 2))
            or [s['task'] for s in slots] != list(TASKS) * 4):
        raise ValueError('Six situations, twelve fixed interleaved slots and three equal structures required')
    for case in cases:
        rows = [s for s in slots if s['case_id'] == case['case_id']]
        if (len(rows) != 2 or {s['repeat_index'] for s in rows} != {0, 1}
                or any(s['task'] != case['task'] or s['seed'] != s['sampling_seed'] for s in rows)):
            raise ValueError('Exact situations require two declared seed repeats')
    windows = catalog['sampling_windows']
    if (len(windows) != 3 or {w['credit_arm'] for w in windows} != {'common', *ARMS}
            or len({w['window_id'] for w in windows}) != 3):
        raise ValueError('One common D0 and two separate second collections required')
    for window in windows:
        if (len(window['slots']) != 6 or len({s['slot_id'] for s in window['slots']}) != 6
                or Counter(s['task'] for s in window['slots']) != Counter(joint_a=2, joint_b=2, implement=1, review=1)):
            raise ValueError('Every collection keeps all six planned slots')
    return slots


def bounded_comparison(pairs):
    """Each known endpoint tightens its pair interval; unknown is never zero."""
    differences, lower, upper = [], [], []
    for pair in pairs:
        left, right = pair['left']['value'], pair['right']['value']
        a = [int(left)] if type(left) is bool else [0, 1]
        b = [int(right)] if type(right) is bool else [0, 1]
        options = [y - x for x in a for y in b]
        lower.append(min(options))
        upper.append(max(options))
        if pair['known_pair']:
            differences.append(pair['difference'])
    count = len(pairs)
    return {'planned_pairs': count, 'known_pairs': len(differences), 'unknown_pairs': count-len(differences),
            'mean_difference': math.fsum(differences)/count if count and len(differences) == count else None,
            'known_pair_mean_descriptive_only': math.fsum(differences)/len(differences) if differences else None,
            'full_denominator_compatible_bounds': [math.fsum(lower)/count, math.fsum(upper)/count] if count else None,
            'bounds_are_confidence_intervals': False}


def pair_evaluations(catalog, before, after, *, left_label, right_label, left_actor, right_actor):
    slots = validate_catalog(catalog)
    indexed = [index_progress(rows, slots) for rows in (before, after)]
    seen, pairs = {}, []
    for slot in slots:
        rows = [index.get(slot['slot_id']) for index in indexed]
        for row in rows:
            state = row.get('initial_business_state_sha256') if row else None
            if state:
                old = seen.setdefault(slot['case_id'], state)
                if old != state:
                    raise ValueError('Same declared situation changed initial canonical business state')
        first, last = outcome(rows[0], left_actor), outcome(rows[1], right_actor)
        hashes = [row.get('initial_business_state_sha256') if row else None for row in rows]
        known = first['known'] and last['known'] and bool(hashes[0]) and hashes[0] == hashes[1]
        pairs.append({**slot, 'left': first, 'right': last, 'known_pair': known,
                      'difference': int(last['value'])-int(first['value']) if known else None,
                      'initial_business_state_sha256': hashes,
                      'auxiliary': {label: auxiliary(row.get('assessment', {}) if row else {},
                                      trusted=valid['known'], task=slot['task'])
                                    for label, row, valid in [(left_label, rows[0], first), (right_label, rows[1], last)]}})
    return {'left_checkpoint': left_label, 'right_checkpoint': right_label,
            'overall': bounded_comparison(pairs),
            'structures': {task: bounded_comparison([p for p in pairs if p['task'] == task]) for task in TASKS},
            'cases': {case['case_id']: bounded_comparison([p for p in pairs if p['case_id'] == case['case_id']])
                      for case in catalog['evaluation_cases']}, 'pairs': pairs}


def checkpoint(root, label, frozen_source):
    marker = read(root / 'checkpoints' / f'{label}.json')
    if marker is None:
        return {'available': False, 'actor_identity': None, 'reference': None}
    saved = pinned(marker['checkpoint'])
    mode = ARMS.get(label, 'terminal_mc')
    if (marker.get('source') != frozen_source or marker.get('label') != label
            or marker.get('credit_assignment') != mode
            or saved.get('actor_identity') != marker.get('actor_identity')
            or saved.get('serialized_reload_exact') is not True):
        raise ValueError('Checkpoint label/source/recipe/actual saved identity differs: ' + label)
    expected_steps = (0, 0) if label == 'initial' else range(3)
    if (saved.get('actor_steps') not in expected_steps or saved.get('critic_steps') not in expected_steps):
        raise ValueError('Endpoint exceeds fresh/two-window parameter-step contract')
    return {'available': True, 'actor_identity': marker['actor_identity'], 'marker': marker,
            'saved_metadata': saved, 'reference': reference(root / 'checkpoints' / f'{label}.json'),
            'scope': 'Pinned actual checkpoint metadata and worker guards; no tensor reload in reporter.'}


def evaluation_rows(folder):
    rows = read(folder / 'progress.json', [])
    for row in rows:
        if row.get('status') == 'closed' and not row.get('assessment_ref'):
            raise ValueError('A closed evaluation needs its immutable original assessment reference')
        if row.get('assessment_ref') and pinned(row['assessment_ref']) != row.get('assessment'):
            raise ValueError('Embedded assessment changed from its original file')
        if row.get('status') == 'closed':
            preparation = read(folder / row['slot_id'] / 'preparation.json', {})
            if (preparation.get('prepared_business_state_sha256') != row.get('initial_business_state_sha256')
                    or preparation.get('prepared_business_state_hash_format') != 'canonical-keys-v024-all-original-business-fields-and-immutable-file-bytes'):
                raise ValueError('Evaluation canonical initial state differs from actual preparation evidence')
    return rows


def ledger_rows(entries):
    rows = []
    for entry in entries or []:
        reward, rollout = entry['reward'], entry['rollout']
        ledger = reward.get('ledger', {})
        events = ledger.get('events', [])
        amounts = [event.get('amount') for event in events]
        actual_sequences = {e['sequence'] for e in rollout['events']}
        total = math.fsum(amounts) if amounts and all(finite(x) for x in amounts) else None
        conserved = (finite(reward.get('reward')) and total is not None
                     and math.isclose(total, reward['reward'], rel_tol=1e-10, abs_tol=1e-10)
                     and ledger.get('total') == reward['reward'] and bool(actual_sequences)
                     and ledger.get('terminal_sequence') == max(actual_sequences)
                     and all(e.get('sequence') in actual_sequences for e in events)
                     and all(e['sequence'] == ledger['terminal_sequence'] for e in events if e.get('settlement') == 'terminal')
                     and reward == rollout.get('reward_eligibility'))
        rows.append({'slot_id': entry['slot_id'], 'episode_id': reward.get('episode_id'),
                     'manifest_sha256': reward.get('manifest_sha256'), 'terminal_reward': reward.get('reward'),
                     'ledger': ledger, 'ledger_sum': total, 'conserved_and_located': bool(conserved),
                     'negative_terminal_correction': any(e.get('settlement') == 'terminal' and finite(e.get('amount')) and e['amount'] < 0 for e in events)})
    return rows


def compare_prepared(mc, rtg):
    if mc is None or rtg is None:
        return {'available': False, 'only_target_and_credit_differ': None}
    copies = []
    for value in (mc, rtg):
        item = copy.deepcopy(value)
        item['decisions'] = [{k: v for k, v in row.items() if k not in {'reward', 'credit'}} for row in item['decisions']]
        copies.append(item)
    same = copies[0] == copies[1]
    return {'available': True, 'only_target_and_credit_differ': same,
            'decision_counts': [len(x['decisions']) for x in (mc, rtg)],
            'common_projection_sha256': digest(json_bytes(copies[0])) if same else None,
            'target_changes': [{'slot_id': a['slot_id'], 'member_id': a['member_id'], 'call_id': a['call_id'],
                                'mc': a['reward'], 'handoff_rtg': b['reward']}
                               for a, b in zip(mc['decisions'], rtg['decisions']) if same and a['reward'] != b['reward']],
            'scope': 'Actual saved admission objects only; tokens, masks, row ordering, identities, features and all denominators retained.'}


def target_rows(entries, admission, update, mode):
    if admission is None:
        return {'available': False, 'actual_credit_mode_matches': None, 'rows': []}
    entries_by_slot = {e['slot_id']: e for e in entries or []}
    values, advantages = update.get('old_critic_values'), update.get('advantages')
    signed = (isinstance(values, list) and isinstance(advantages, list)
              and len(values) == len(advantages) == len(admission['decisions']))
    rows = []
    for index, decision in enumerate(admission['decisions']):
        entry = entries_by_slot.get(decision['slot_id'])
        expected = None
        if entry:
            reward = entry['reward']
            starts = [event for event in entry['rollout']['events'] if event['kind'] == 'model_call'
                      and event.get('worker_id') == decision['member_id']
                      and event['payload'].get('stage') == 'started'
                      and event['payload'].get('call_id') == decision['call_id']]
            if len(starts) == 1:
                expected = (float(reward['reward']) if mode == 'terminal_mc' else
                            math.fsum(e['amount'] for e in reward['ledger']['events'] if e['sequence'] >= starts[0]['sequence']))
        value, advantage = (values[index], advantages[index]) if signed else (None, None)
        matches = (expected is not None and finite(decision.get('reward')) and
                   math.isclose(decision['reward'], expected, abs_tol=1e-10, rel_tol=1e-10))
        advantage_matches = (math.isclose(decision['reward']-value, advantage, abs_tol=1e-10, rel_tol=1e-10)
                             if signed and finite(value) and finite(advantage) else None)
        rows.append({**pick(decision, ('slot_id', 'member_id', 'call_id', 'terminal_reward', 'credit',
                                       'actor_denominator', 'critic_denominator')),
                     'return_target': decision['reward'], 'expected_from_saved_ledger': expected,
                     'target_matches_saved_ledger': matches, 'critic_before': value, 'advantage': advantage,
                     'advantage_matches_target_minus_value': advantage_matches})
    return {'available': True, 'actual_credit_mode_matches': all(r['credit'].get('mode') == mode for r in rows),
            'targets_match_saved_ledger': all(r['target_matches_saved_ledger'] for r in rows),
            'signed_advantages_available': signed,
            'advantages_match_targets': all(r['advantage_matches_target_minus_value'] is True for r in rows) if signed else None,
            'rows': rows}


def collection(folder, contract):
    progress = read(folder / 'progress.json', [])
    index_progress(progress, contract['slots'])
    entries = read(folder / 'entries.json')
    if entries is not None and [e['slot_id'] for e in entries] != [s['slot_id'] for s in contract['slots']]:
        raise ValueError('Actual collection dropped, reordered or replaced scheduled slots')
    ledgers = ledger_rows(entries)
    closed = sum(row.get('status') == 'closed' for row in progress)
    complete = closed == 6 and len(ledgers) == 6 and all(r['conserved_and_located'] for r in ledgers)
    return {'collection_id': contract['collection_id'], 'credit_arm': contract['credit_arm'],
            'window_id': contract['window_id'], 'closed_new_episodes': closed, 'complete': complete,
            'observed_slots': progress, 'ledgers': ledgers,
            'references': {name: reference(folder / name) for name in ('entries.json', 'declaration.json', 'progress.json')}}, entries


def training(root, catalog, endpoints):
    contracts = {w['credit_arm']: w for w in catalog['sampling_windows']}
    common_folder = root / 'common/actual/collection'
    common, common_entries = collection(common_folder, contracts['common'])
    marker = read(root / 'common-complete.json')
    if marker:
        if pinned(marker['entries']) != common_entries:
            raise ValueError('Common completion marker does not bind actual D0 entries')
        declaration = pinned(marker['declaration'])
        raw_admission = pinned(marker['admission'])
        pinned(marker['initial_checkpoint'])
        if read(Path(marker['origin_dir']) / 'consumption-origin.json') != marker['origin']:
            raise ValueError('Common origin marker differs from actual saved origin')
    collections, arms, prepared = {'common': common}, {}, {}
    for arm, mode in ARMS.items():
        folder = root / f'train_{arm}/actual'
        progress = read(folder / 'training-progress.json', [])
        if len(progress) > 2 or [row['window_index'] for row in progress] != list(range(len(progress))):
            raise ValueError('Only two ordered updates per arm are declared')
        consumption = read(folder / 'common-consumption.json')
        windows = []
        collections[arm], own_entries = collection(folder / 'window-1', contracts[arm])
        for index in range(2):
            row = progress[index] if index < len(progress) else {}
            here = folder / f'window-{index}'
            entries = read(here / 'entries.json')
            if row.get('entries') and pinned(row['entries']) != entries:
                raise ValueError('Training progress changed its original entries')
            if index == 0 and entries is not None and entries != common_entries:
                raise ValueError('A D0 consumer changed raw original episodes')
            if index == 1 and entries is not None and entries != own_entries:
                raise ValueError('Second collection differs from own branch entries')
            if row and (row.get('credit_arm') != arm or row.get('new_collection') is not (index == 1)):
                raise ValueError('Training branch or fresh-versus-common identity differs')
            admission = read(here / 'update/admission.json')
            if index == 0:
                prepared[arm] = admission
            update, signals = read(here / 'update/report.json', {}), read(here / 'work-signals.json')
            actual_mode = mode if consumption and consumption.get('credit_assignment') == mode else None
            targets = target_rows(entries, admission, update, mode)
            if signals and signals.get('credit_assignment') != mode:
                raise ValueError('Work signals mislabeled the actual branch credit')
            collected = common if index == 0 else collections[arm]
            complete = (row.get('status') == 'closed' and update.get('status') in ACCEPTED and collected['complete']
                        and actual_mode == mode and targets.get('actual_credit_mode_matches') is True
                        and targets.get('targets_match_saved_ledger') is True
                        and all(update.get(k) in (0, 1) for k in ('actor_optimizer_steps', 'critic_optimizer_steps')))
            windows.append({'window_index': index, 'credit_arm': arm, 'actual_credit_assignment': actual_mode,
                'status': row.get('status', 'not_observed'), 'complete': complete,
                'new_collection': index == 1, 'episode_consumptions_started': 6 if admission is not None else 0,
                'update': pick(update, ('status', 'stage', 'actor_optimizer_steps', 'critic_optimizer_steps',
                    'actor_steps_total', 'critic_steps_total', 'before_actor_identity', 'after_actor_identity',
                    'backward_decisions_completed', 'admitted_decisions', 'admitted_output_tokens', 'changed_actor_elements')),
                'last_persisted_step_counts_are_terminal': complete, 'targets_and_advantages': targets,
                'work_signals': signals, 'post_update_probability': read(here / 'update/post-update-sampled-policy.json'),
                'references': {name: reference(here / name) for name in ('entries.json', 'declaration.json', 'work-signals.json',
                    'update/report.json', 'update/admission.json', 'update/losses.json', 'checkpoint/checkpoint.json')}})
        checkpoint_steps = endpoints[arm].get('saved_metadata', {})
        steps_match = None
        if checkpoint_steps and all(w['complete'] for w in windows):
            steps_match = all(checkpoint_steps[k] == sum(w['update'][uk] for w in windows)
                              for k, uk in [('actor_steps', 'actor_optimizer_steps'), ('critic_steps', 'critic_optimizer_steps')])
        arms[arm] = {'windows': windows, 'complete_windows': sum(w['complete'] for w in windows),
                     'terminal_steps_match_windows': steps_match,
                     'common_consumption': consumption, 'actual_terminal_actor_steps': checkpoint_steps.get('actor_steps'),
                     'actual_terminal_critic_steps': checkpoint_steps.get('critic_steps'),
                     'references': {'consumption': reference(folder / 'common-consumption.json'),
                                    'training_progress': reference(folder / 'training-progress.json')}}
    comparison = compare_prepared(prepared.get('mc'), prepared.get('handoff_rtg'))
    proofs = [arms[arm]['common_consumption'] for arm in ARMS]
    common_proof = None
    if all(proofs) and marker:
        origin = marker['origin']
        common_proof = all(
            p.get('exact_common_state_restored') is True and p.get('only_recipe_field_changed') == 'credit_assignment'
            and p.get('new_model_calls') == 0 and p.get('raw_trajectory_ids_rewritten') is False
            and p.get('entries_sha256') == digest(json_bytes(common_entries))
            and p.get('declaration_sha256') == digest(json_bytes(declaration))
            and p.get('admission_sha256') == digest(json_bytes(raw_admission))
            and p.get('common_state_tensor_digest') == origin['checkpoint']['state_tensor_digest']
            and p.get('recipe_after') == {**p['recipe_before'], 'credit_assignment': ARMS[arm]}
            and p.get('comparison') == origin.get('comparison')
            for arm, p in zip(ARMS, proofs))
        common_proof = common_proof and proofs[0]['recipe_before'] == proofs[1]['recipe_before']
    comparison['matches_common_origin_projection'] = (comparison.get('common_projection_sha256') == marker['origin']['comparison']['common_projection_without_target_credit_sha256']
        if marker and comparison['available'] else None)
    if comparison['available'] and marker:
        comparison['actual_prepared_hashes_match_origin'] = all(
            digest(json_bytes(prepared[arm])) == marker['origin']['comparison']['prepared_sha256'][arm] for arm in ARMS)
    return {'collections': collections, 'arms': arms, 'complete_windows': sum(a['complete_windows'] for a in arms.values()),
            'actual_new_training_episodes_closed': sum(c['closed_new_episodes'] for c in collections.values()),
            'actual_episode_consumptions_started': sum(w['episode_consumptions_started'] for a in arms.values() for w in a['windows']),
            'common_state_proof_matches_saved_origin': common_proof, 'actual_D0_prepared_comparison': comparison,
            'common_complete_reference': reference(root / 'common-complete.json'),
            'scope': 'D0 is collected once, consumed twice. Each second window is newly collected by its own branch. No old v023 replay, teacher data, deleted failures or ID-VTDO weighting.'}


def summarize(run):
    root = Path(run).resolve()
    supervisor = read(root / 'supervisor.json')
    if supervisor is None:
        raise ValueError('A pinned supervisor declaration is required')
    plan = pinned(supervisor['plan'])
    catalog = pinned(plan['catalog'])
    validate_catalog(catalog)
    if plan.get('internal_gpu_seconds') != 129600 or plan.get('external_gpu_seconds') != 0:
        raise ValueError('Report requires the declared 36 GPU-hour internal-only budget')
    source = supervisor['source']
    closed = supervisor.get('ended_at') is not None and supervisor.get('status') in {'complete', 'closed_with_incomplete_stages', 'supervisor_error'}
    stages, costs = {}, {}
    for name in STAGES:
        folder = root / name
        state, worker = read(folder / 'state.json', {}), read(folder / 'actual/report.json', {})
        terminal = stage_terminal(state, closed)
        elapsed = state.get('elapsed_gpu_seconds')
        if finite(elapsed) and elapsed < 0:
            raise ValueError('Negative GPU accounting')
        costs[name] = elapsed if terminal and finite(elapsed) else 0 if terminal and state.get('attempted') is False else None
        if worker.get('source_before') and worker['source_before'] != source:
            raise ValueError('Worker does not match frozen experimental source')
        stages[name] = {'terminal': terminal, 'state': state, 'worker_status': worker.get('status'),
            'source_unchanged': worker.get('source_unchanged') is True and worker.get('source_after') == source,
            'actual_final_actor_identity': worker.get('final_actor_identity'),
            'references': {part: reference(folder / part) for part in ('state.json', 'actual/report.json', 'model.log')},
            'resources': resources(folder / 'resources.jsonl', state), 'resident_calls': calls(folder / 'actual')}
    terminal = closed and all(stage['terminal'] for stage in stages.values())
    endpoints = {label: checkpoint(root, label, source) for label in ENDPOINTS}
    rows = {label: evaluation_rows(root / f'eval_{label}/actual') for label in ENDPOINTS}
    comparisons = {}
    for left, right, name in [('mc', 'handoff_rtg', 'credit'), ('initial', 'mc', 'mc_vs_initial'), ('initial', 'handoff_rtg', 'handoff_rtg_vs_initial')]:
        comparisons[name] = pair_evaluations(catalog, rows[left], rows[right], left_label=left, right_label=right,
            left_actor=endpoints[left]['actor_identity'], right_actor=endpoints[right]['actor_identity'])
    train = training(root, catalog, endpoints)
    protocol = (terminal and train['complete_windows'] == 4 and train['common_state_proof_matches_saved_origin'] is True
                and train['actual_D0_prepared_comparison']['only_target_and_credit_differ'] is True
                and train['actual_D0_prepared_comparison']['matches_common_origin_projection'] is True
                and train['actual_D0_prepared_comparison'].get('actual_prepared_hashes_match_origin') is True
                and all(a['terminal_steps_match_windows'] is True for a in train['arms'].values())
                and all(stages[f'eval_{label}']['actual_final_actor_identity'] == endpoints[label]['actor_identity'] for label in ENDPOINTS)
                and all(c['overall']['known_pairs'] == 12 for c in comparisons.values())
                and all(s['worker_status'] == 'complete' and s['source_unchanged'] is True
                        and s['state'].get('status') == 'complete' for s in stages.values()))
    total = math.fsum(costs.values()) if terminal and all(c is not None for c in costs.values()) else None
    return {'version': VERSION, 'generated_at_epoch': time.time(), 'run_root': str(root),
        'report_kind': 'final_complete' if protocol else 'closed_incomplete' if terminal else 'snapshot',
        'execution_terminal': terminal, 'protocol_complete': bool(protocol),
        'planned_primary_credit_difference': comparisons['credit']['overall']['mean_difference'] if protocol else None,
        'planned_primary_estimate_reason': None if protocol else 'Complete terminal two-window methods and all planned endpoint pairs required; partial observations are descriptive only.',
        'planned_counts': {'new_training_episodes': 18, 'evaluation_episodes': 36, 'internal_new_episodes': 54,
                          'training_episode_consumptions': 24, 'window_updates': 4, 'external_started': 0},
        'evaluations': comparisons, 'training': train, 'endpoints': endpoints, 'stages': stages,
        'accounting': {'terminal_gpu_seconds_by_stage': costs, 'known_terminated_gpu_seconds': math.fsum(v for v in costs.values() if v is not None),
                       'final_gpu_seconds': total, 'planned_gpu_seconds': 129600, 'actual_plan': plan,
                       'scope': 'Every declared stage including failed work/load time counted once; overlapping one-GPU stages are additive. No restoration or external GPU stage is declared.'},
        'source_and_artifacts': {'source': source, 'plan': supervisor['plan'], 'catalog': plan['catalog'],
            'source_pin': plan.get('source_pin'), 'supervisor': reference(root / 'supervisor.json'),
            'reporter': reference(Path(__file__))},
        'interpretation': 'Same terminal contract and realized member-token denominator, two temporal-credit surrogates. No unbiased-equivalence, action-causal credit, significance, learning-gain or ID-VTDO claim follows merely from changed targets/advantages.',
        'metadata_policy': 'v024 predeclares deterministic nonbusiness host identifiers for equal role-visible history/actions; actual storage, episode and branch identities remain distinct. This is not a guarantee of GPU bitwise or all-trajectory equality.',
        'scope': 'Only existing pinned assessments and metadata are read. No replay, grading, reward rewrite, model or checkpoint tensor loading. Six situations with two repeats are not twelve independent tasks; one training initialization and two updates per arm limit attribution.'}


def markdown(report):
    def show(value):
        return '未知/未完成' if value is None else str(value)
    lines = ['# v0.24 同终局合同的时间信用对照', '',
             f"状态：`{report['report_kind']}`；所有执行已终止：{report['execution_terminal']}。未完成协议不会被写成仍在运行。", '',
             '计划 18 条新训练经历＋36 次评价＝54 个内部新运行。共同 D0 的六条经历分别被两臂消费，合计 24 次 episode 级训练消费、最多四次窗口更新；不把 D0 重复消费当新采样。', '',
             f"实际已闭合新训练经历 {report['training']['actual_new_training_episodes_closed']}/18；完整更新窗 {report['training']['complete_windows']}/4。",
             f"预定主比较 Handoff-RTG − MC：{show(report['planned_primary_credit_difference'])}。", '',
             '| 比较 | 已知配对 / 12 | 全部槽点估计 | 已知配对描述均值 | 有限样本兼容界 |', '|---|---:|---:|---:|---|']
    for name, comparison in report['evaluations'].items():
        v = comparison['overall']
        lines.append(f"| {name} | {v['known_pairs']}/12 | {show(v['mean_difference'])} | {show(v['known_pair_mean_descriptive_only'])} | {v['full_denominator_compatible_bounds']} |")
    lines += ['', '上表算术值仅在完整协议满足时作为预定主比较；失败保留 false，未知保留 null。兼容界利用每个已知端点收紧，不是置信区间或填补结果。', '',
              '| 主比较结构 | 已知配对 / 4 | 差值 | 兼容界 |', '|---|---:|---:|---|']
    for task, row in report['evaluations']['credit']['structures'].items():
        lines.append(f"| {task} | {row['known_pairs']}/4 | {show(row['mean_difference'])} | {row['full_denominator_compatible_bounds']} |")
    lines += ['', f"共同 actor/critic/两 optimizer/RNG 起点证明：{show(report['training']['common_state_proof_matches_saved_origin'])}；实际 D0 admission 除目标与信用字段外一致：{show(report['training']['actual_D0_prepared_comparison']['only_target_and_credit_differ'])}。", '',
              '| 方法 / 窗口 | 状态 | actor / critic 步数 | 信用配方 |', '|---|---|---:|---|']
    for arm, data in report['training']['arms'].items():
        for window in data['windows']:
            update = window['update']
            lines.append(f"| {arm} / {window['window_index']+1} | {window['status']} | {show(update['actor_optimizer_steps'])} / {show(update['critic_optimizer_steps'])} | {show(window['actual_credit_assignment'])} |")
    lines += ['', 'JSON 保留每条真实经历的事件账本、总和守恒、负终点补差、实际目标和优势，以及两臂共同窗口的原件 SHA。优势分布改变不等于工作改善；两种配方在相同随机长度分母下是不同 surrogate，不声称无偏等价。', '',
              f"终止阶段已结算 GPU 秒：{report['accounting']['known_terminated_gpu_seconds']:.3f}；完整成本：{show(report['accounting']['final_gpu_seconds'])}；预算 129600 秒（36 GPU 小时）。失败、加载和并行各卡占用均计入。",
              '外部 D2 本轮仅合同与 CPU 准入修订；九例提案未启动，不计入内部预算。', '',
              '可控的非业务标识按同情境/种子、相同可见历史和动作确定生成；真实实验身份保持独立。该规则不承诺 GPU 逐位确定，也不能将两次重复和单共同起点解释为稳定总体效应。', '',
              f"原实验目录：`{report['run_root']}`。本报告只读取原始证据，不重新评分；源码、计划、catalog、checkpoint、逐阶段资源与原始产物引用见同名 JSON。", '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output-json', type=Path, required=True)
    parser.add_argument('--output-md', type=Path, required=True)
    parser.add_argument('--require-terminal', action='store_true')
    args = parser.parse_args()
    outputs = [args.output_json.resolve(), args.output_md.resolve()]
    if len(set(outputs)) != 2 or any(path.is_relative_to(args.run.resolve()) for path in outputs):
        raise ValueError('Reporting outputs must be distinct and outside raw experiment artifacts')
    report = summarize(args.run)
    if args.require_terminal and not report['execution_terminal']:
        raise ValueError('A declared stage may still run; refusing a terminal report')
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    outputs[0].write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
    outputs[1].write_text(markdown(report))
    print(json.dumps(pick(report, ('report_kind', 'execution_terminal', 'planned_primary_credit_difference'))))


if __name__ == '__main__':
    main()
