"""Read-only paired work evidence and predeclared single-block decision."""
import copy
from pathlib import Path
import time

from proworksim.storage import digest, read_json
from scripts.evaluate_work_v022 import reference, write
from scripts.report_credit_v024 import bounded_comparison, evaluation_rows
from scripts.report_learning_v023 import auxiliary, index_progress, outcome


def checked(value):
    """Accept the two existing exact reference schemas, retaining byte checks."""
    if not isinstance(value, dict) or set(value) not in ({'path', 'sha256'}, {'path', 'sha256', 'bytes'}):
        raise ValueError('Unknown frozen reference schema')
    path = Path(value['path'])
    data = path.read_bytes()
    if digest(data) != value['sha256'] or ('bytes' in value and value['bytes'] != len(data)):
        raise ValueError('Frozen referenced bytes changed')
    return path


def endpoint(root, label, source):
    marker_path = Path(root) / 'checkpoints' / f'{label}.json'
    if not marker_path.exists():
        return {'available': False, 'actor_identity': None}
    marker = read_json(marker_path)
    saved = read_json(checked(marker['checkpoint']))
    limits = (2,) if label == 'origin' else (2, 3)
    if (marker['source'] != source or marker['label'] != label or marker['credit_assignment'] != 'terminal_mc'
            or marker['actor_identity'] != saved['actor_identity'] or saved['serialized_reload_exact'] is not True
            or saved['actor_steps'] not in limits or saved['critic_steps'] not in limits):
        raise ValueError('Current endpoint source, recipe, steps or saved identity mismatch')
    return {'available': True, 'actor_identity': marker['actor_identity'], 'saved_metadata': saved,
            'marker': marker, 'reference': reference(marker_path)}


def read_evaluations(root, stage, slots, actor):
    folder = Path(root) / stage / 'actual'
    rows = evaluation_rows(folder) if (folder / 'progress.json').exists() else []
    indexed = index_progress(rows, slots)
    result = []
    for slot in slots:
        row = indexed.get(slot['slot_id'])
        item = outcome(row, actor)
        result.append({**copy.deepcopy(slot), 'outcome': item,
            'initial_business_state_sha256': row.get('initial_business_state_sha256') if row else None,
            'assessment_reference': row.get('assessment_ref') if row else None,
            'auxiliary': auxiliary(row.get('assessment', {}) if row else {}, trusted=item['known'], task=slot['task'])})
    return {'stage': stage, 'rows': result, 'values': [r['outcome']['value'] for r in result],
            'known': sum(r['outcome']['known'] for r in result),
            'completed': sum(r['outcome']['value'] is True for r in result),
            'progress_reference': reference(folder / 'progress.json') if (folder / 'progress.json').exists() else None}


def paired_evaluations(left, right):
    pairs = []
    if len(left['rows']) != len(right['rows']):
        raise ValueError('Paired inventories differ')
    for a, b in zip(left['rows'], right['rows']):
        for field in ('slot_id', 'case_id', 'task', 'seed'):
            if a[field] != b[field]:
                raise ValueError('Paired fixed situation/seed differs')
        hashes = [a['initial_business_state_sha256'], b['initial_business_state_sha256']]
        if all(hashes) and hashes[0] != hashes[1]:
            raise ValueError('Same declared situation has different canonical preparation')
        known = a['outcome']['known'] and b['outcome']['known'] and bool(hashes[0]) and hashes[0] == hashes[1]
        pairs.append({'slot_id': a['slot_id'], 'case_id': a['case_id'], 'task': a['task'],
            'seed': a['seed'], 'left': a['outcome'], 'right': b['outcome'], 'known_pair': known,
            'difference': int(b['outcome']['value']) - int(a['outcome']['value']) if known else None,
            'initial_business_state_sha256': hashes})
    return {'overall': bounded_comparison(pairs),
            'structures': {task: bounded_comparison([p for p in pairs if p['task'] == task])
                           for task in ('joint_a', 'joint_b', 'maintenance')}, 'pairs': pairs}


def terminal(state):
    return state.get('status') not in {'waiting', 'running', 'launch_intent', None}


def maybe_decide(root, plan, states, source):
    """CPU decision before confirmation; absence and zero gain never become negative C."""
    from proworksim.composition_training_v025 import baseline_configuration, configure_from_development

    root = Path(root)
    path = root / 'configuration-decision.json'
    if path.exists():
        return read_json(path)
    marker_path = root / 'support-complete.json'
    if states['support']['status'] != 'complete' or not marker_path.exists():
        return None
    marker = read_json(marker_path)
    if marker['source'] != source:
        raise ValueError('Support and configuration source differ')
    support = read_json(checked(marker['support']))
    selected = support['selected_block']
    if selected is None:
        decision = {'q_by_xi': baseline_configuration(support['supports_by_xi']), 'changed': False,
            'reason': 'no_current_supported_member_block', 'development_complete': False,
            'development_required': False, 'contribution_estimate': None}
    else:
        if not all(terminal(states[k]) for k in ('dev_base', 'dev_probe')):
            return None
        catalog = read_json(checked(plan['catalog']))
        ends = {label: endpoint(root, label, source) for label in ('base', 'probe')}
        evidence = {label: read_evaluations(root, 'dev_' + label, catalog['development_slots'],
                    ends[label]['actor_identity']) for label in ends}
        pairs = paired_evaluations(evidence['base'], evidence['probe'])
        complete = (all(states[k]['status'] == 'complete' for k in ('dev_base', 'dev_probe'))
                    and pairs['overall']['known_pairs'] == 6)
        values = {k: v['values'] if complete else [None]*6 for k, v in evidence.items()}
        decision = configure_from_development(support['supports_by_xi'], selected, values['base'], values['probe'])
        decision.update(development_complete=complete, development_required=True,
                        development_evidence=evidence, development_pairs=pairs)
        if not complete and decision['changed']:
            raise ValueError('Unknown development cannot authorize a changed configuration')
    decision.update(version='frozen-single-block-decision-v0.25', decided_at=time.time(), source=source,
        selected_block=selected, support_reference=marker['support'], predeclared_coefficients=plan['composition'],
        confirmation_outcomes_used=False, previous_checkpoint_search=False)
    write(path, decision)
    return decision
