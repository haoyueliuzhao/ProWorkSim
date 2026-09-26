"""Freeze the selected candidate's new-source bridge and bounded online pilot.

Creates new files only. Never selects a candidate, runs a model, or changes a
case using observed outcomes; select and document the input candidate first.
"""
import argparse
import copy
import json
from pathlib import Path

TASKS = ('implement', 'review', 'pair', 'chain')


def slots(pool, facts, repeats, *, seed_base, label):
    result = []
    for fact in facts:
        for task_index, task in enumerate(TASKS):
            for repeat in range(repeats):
                result.append({'slot_id': f'{label}-f{fact}-{task}-r{repeat}',
                    'case_id': f'uci-{pool}-f{fact}-{task}', 'task': task, 'fact_position': fact,
                    'repeat': repeat, 'sampling_seed': seed_base + fact * 100 + task_index * 10 + repeat})
    return result


def window(name, mode, phase, node, batch, stage):
    return {'window_id': name, 'mode': mode, 'stage': stage, 'phase': phase, 'node': node,
            'template': 'retail_work', 'interface': 'v14', 'presentation': 'compact_v14',
            'external_tick_per_sweep': 1, 'min_class_count': 2, 'slots': batch}


def build_protocols(screen):
    common = {key: copy.deepcopy(screen[key]) for key in ('version', 'candidate_id', 'runtime', 'recipe')}
    common['mode'] = 'online'
    common['selection_parent_scope'] = 'Fresh same public base; no screening or bridge weights restored'
    result = {}
    bridge = copy.deepcopy(common)
    bridge.update(stage='bridge', condition='terminal_mc', windows=[])
    bridge['recipe'].update(seed=2026092911, diagnostic_max_groups=16, post_update_max_decisions=4,
                            credit_assignment='terminal_mc')
    for i in range(2):
        name = 'bridge-' + str(i)
        batch = slots('train', [i], 4, seed_base=2026102000 + i * 1000, label=name)
        bridge['windows'].append(window(name, 'online', 'training', str(i), batch, 'bridge'))
    result['bridge.json'] = bridge
    for condition, credit in [('mc', 'terminal_mc'), ('rtg', 'joint_reward_to_go')]:
        protocol = copy.deepcopy(common)
        protocol.update(stage='pilot', condition=condition, replicate_index=0, windows=[])
        protocol['recipe'].update(seed=2026092929, credit_assignment=credit,
                                  diagnostic_max_groups=0, post_update_max_decisions=0)
        if condition == 'mc':
            for pool, facts, node, seed in [('development', [0, 1], 'initial-development', 2026110000),
                                           ('locked', [0, 1, 2], 'initial-locked', 2026120000)]:
                name = 'pilot-common-' + node
                protocol['windows'].append(window(name, 'evaluate', pool, node,
                    slots(pool, facts, 1, seed_base=seed, label=name), 'pilot'))
        for i, fact in enumerate([0, 1, 2, 0]):
            name = f'pilot-{condition}-train-{i}'
            protocol['windows'].append(window(name, 'online', 'training', str(i),
                slots('train', [fact], 4, seed_base=2026130000 + i * 1000, label=name), 'pilot'))
            if i == 1:
                name = f'pilot-{condition}-after2-development'
                protocol['windows'].append(window(name, 'evaluate', 'development', 'after2',
                    slots('development', [0, 1], 1, seed_base=2026110000, label=name), 'pilot'))
        name = f'pilot-{condition}-final-locked'
        protocol['windows'].append(window(name, 'evaluate', 'locked', 'final',
            slots('locked', [0, 1, 2], 1, seed_base=2026120000, label=name), 'pilot'))
        result[f'pilot-{condition}.json'] = protocol
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selected-screen-protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    screen = json.loads(args.selected_screen_protocol.read_text())
    result = build_protocols(screen)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, protocol in result.items():
        (args.output / name).write_text(json.dumps(protocol, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({name: {'episodes': sum(len(w['slots']) for w in p['windows']),
        'train': sum(len(w['slots']) for w in p['windows'] if w['mode'] == 'online')}
        for name, p in result.items()}))


if __name__ == '__main__':
    main()
