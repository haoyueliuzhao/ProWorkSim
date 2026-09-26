"""Finite scheduler fixtures with fake PIDs/launches; no sampling, GPU or tensor."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.run_learning_pilot_v015 import PilotExecutor, commands, normalize_config, sha, write


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    write(path, value)


class Processes:
    def __init__(self):
        self.calls, self.live = [], {}

    def popen(self, command, **kwargs):
        assert kwargs['start_new_session'] is True
        output = Path(command[command.index('--output') + 1])
        if output.name in {'pilot-mc', 'pilot-rtg'}:
            assert (output.parent.parent / 'resource-budget.json').is_file()
        pid = 4000 + len(self.calls)
        self.live[pid] = {'pid': pid, 'command': command, 'start_ticks': str(pid)}
        self.calls.append({'command': command, **kwargs})
        return SimpleNamespace(pid=pid)

    def pid(self, pid):
        return self.live.get(pid)


def config(tmp_path):
    screen = {'version': 'fixture', 'stage': 'screen', 'mode': 'evaluate', 'candidate_id': 'qwen35-9b',
              'runtime': {'kind': 'qwen_hybrid_chatstop', 'profile': {'devices': 1, 'candidate_id': 'qwen3.5-9b'}},
              'recipe': {'seed': 1, 'logprob_max_atol': .02, 'logprob_mean_atol': .002}}
    save(tmp_path / 'screen.json', screen)
    save(tmp_path / 'selection.json', {'status': 'selected', 'selected': {'candidate_id': 'qwen35-9b',
          'screen_protocol': {'path': str(tmp_path / 'screen.json'), 'sha256': sha(tmp_path / 'screen.json')}}})
    save(tmp_path / 'weights.json', {'fixture': 'not loaded'})
    return {'project': str(tmp_path), 'source': str(tmp_path / 'source'), 'source_commit': 'fixture',
            'python': '/fixture/model-python', 'launcher_python': '/fixture/launcher-python',
            'launcher': '/fixture/launcher.py', 'environment': {}, 'model_path': str(tmp_path / 'model'),
            'weight_manifest': 'weights.json', 'selected_screen_protocol': 'screen.json', 'selection_record': 'selection.json',
            'physical_gpus': {'mc': [0], 'rtg': [1]}, 'poll_seconds': 1}


def executor(tmp_path, cfg, processes, *, resume=False, now=lambda: 0):
    return PilotExecutor(cfg, tmp_path / 'pilot', resume=resume, now=now,
                         popen=processes.popen, pid_fn=processes.pid,
                         identity_fn=lambda _: {'commit': 'fixture', 'files': {}})


def finish_meta(q, name, *, exit_code=0, elapsed=320):
    job = q.state['jobs'][name]
    _, child = commands(q.config, job)
    save(Path(job['launch']).with_suffix('.launch.json'), {'command': child, 'cwd': q.config['source'],
         'CUDA_VISIBLE_DEVICES': ','.join(map(str, job['gpus'])), 'PYTHONPATH': str(Path(q.config['source']) / 'src'),
         'pid': 9000, 'exit_code': exit_code, 'end': 999, 'elapsed': elapsed})


def finish_online(q, name, *, complete=True, bad_gate=False):
    job = q.state['jobs'][name]
    protocol = json.loads(Path(job['protocol']).read_text())
    root = Path(job['run'])
    save(root / 'online/protocol.json', protocol)
    records = []
    for wi, window in enumerate(protocol['windows']):
        records.append({'window_id': window['window_id'], 'mode': window['mode'], 'status': 'complete'})
        if complete:
            for si, _ in enumerate(window['slots']):
                save(root / f'online/window-{wi}/collection/slot-{si}/episode/manifest.json', {'status': 'closed'})
        if name == 'bridge':
            folder = root / f'online/window-{wi}/update'
            save(folder / 'report.json', {'status': 'updated', 'admitted_decisions': 1,
                                        'actor_optimizer_steps': 1, 'critic_optimizer_steps': 1})
            for gate in ('behavior', 'gradient'):
                save(folder / (gate + '-probability-check.json'), [{'call_id': 'fixture', 'passed': True,
                      'max_abs_delta': .03 if bad_gate and wi == 1 else .001, 'mean_abs_delta': .0001}])
    save(root / 'online/initial-checkpoint/checkpoint.json', {'actor_steps': 0, 'critic_steps': 0})
    count = 2 if name == 'bridge' else 4
    save(root / 'online/report.json', {'status': 'complete' if complete else 'stopped_probability_mismatch',
         'windows': records, 'actor_steps_total': count, 'critic_steps_total': count})
    finish_meta(q, name, exit_code=0 if complete else 1)


def finish_software(q, name, *, complete=True):
    job = q.state['jobs'][name]
    protocol = json.loads(Path(job['protocol']).read_text())
    rows = []
    if complete:
        for episode in protocol['episodes']:
            root = Path(job['run']) / episode['episode_id']
            save(root / 'episode/manifest.json', {'status': 'closed'})
            save(root / 'result.json', {'assessment': {'R': 0}, 'termination': {'status': 'opportunity_limit'}})
            rows.append({**episode, 'evaluation_guard': {'learning_unchanged': True, 'rng_restored_exactly': True}})
    save(Path(job['run']) / 'report.json', {'status': 'complete' if complete else 'interrupted',
         'episodes': rows, 'actual_optimizer_steps': {'actor': 0, 'critic': 0}})
    finish_meta(q, name, exit_code=0 if complete else 1, elapsed=90)


def test_fixed_workflow_budget_before_n1_and_one_software_failure_does_not_block_other_lane(tmp_path):
    cfg, proc = config(tmp_path), Processes()
    q = executor(tmp_path, cfg, proc)
    try:
        assert not q.tick() and len(proc.calls) == 2
        finish_online(q, 'bridge')
        q.tick()
        assert len(proc.calls) == 2 and (q.output / 'resource-budget.json').is_file()
        finish_software(q, 'software-initial', complete=False)
        q.tick()
        assert len(proc.calls) == 4
        budget = json.loads((q.output / 'resource-budget.json').read_text())
        assert budget['observed_N0']['closed_episodes'] == 32
        assert budget['planned_N1']['total'] == 188 and budget['planned_software']['evaluation'] == 9
        assert budget['planned_N1']['process_seconds_estimate'] == 320 / 32 * 188 * 1.25
        for name in ('pilot-mc', 'pilot-rtg'):
            assert '--restore-checkpoint' not in q.state['jobs'][name]['child_command']
            protocol = json.loads(Path(q.state['jobs'][name]['protocol']).read_text())
            assert protocol['shared_initialization'] == {'directory': str(q.output / 'initialization'),
                'participant': name.split('-')[1], 'participants': ['mc', 'rtg'], 'timeout_seconds': 1800}
        save(q.output / 'initialization/fixture-comparison.json', {'all_equal': True, 'kind': 'CPU fixture'})
        finish_online(q, 'pilot-mc')
        finish_online(q, 'pilot-rtg', complete=False)
        q.tick()
        assert len(proc.calls) == 5
        assert q.state['jobs']['software-rtg-final']['status'] == 'blocked_dependency'
        final = q.state['jobs']['software-mc-final']
        assert '--restore-checkpoint' in final['child_command'] and 'window-7/checkpoint' in final['restore_checkpoint']
        finish_software(q, 'software-mc-final')
        assert q.tick()
        report = json.loads((q.output / 'study-report.json').read_text())
        assert report['planned_counts']['total_episodes'] == 229
        assert report['uci_readonly']['status'] == 'readonly_error'  # minimal fixtures lack full business provenance
        assert Path(report['uci_readonly']['path'], 'readonly-error.json').is_file()
        manifest = json.loads((q.output / 'uci-study.json').read_text())
        references = manifest['baseline_references']
        assert len(references) == 1 and references[0]['consumer_run'] == 'pilot-rtg'
        assert references[0]['source_window_ids'] == ['pilot-common-initial-development', 'pilot-common-initial-locked']
        assert references[0]['measurement_counted_once'] is True
        assert 'Requires actual equal' in references[0]['reuse_validity']
        assert report['shared_initialization']['records'][0]['data']['all_equal'] is True
        assert next(r for r in report['jobs'] if r['name'] == 'software-rtg-final')['outcome']['not_started_episodes'] == 3
        q.tick()
        assert len(proc.calls) == 5  # no failed-stage retry
    finally:
        q.close()


@pytest.mark.parametrize('failure', ['gate', 'budget_tamper'])
def test_probability_or_budget_integrity_failure_blocks_n1(tmp_path, failure):
    cfg, proc = config(tmp_path), Processes()
    q = executor(tmp_path, cfg, proc)
    try:
        q.tick()
        finish_online(q, 'bridge', bad_gate=failure == 'gate')
        if failure == 'budget_tamper':
            q.tick()
            budget = q.output / 'resource-budget.json'
            assert len(proc.calls) == 2 and budget.is_file()
            budget.write_text(budget.read_text() + '\n')  # still parses, but frozen bytes changed
        finish_software(q, 'software-initial')
        assert q.tick()
        assert len(proc.calls) == 2
        if failure == 'gate':
            assert not q.state['jobs']['bridge']['outcome']['n0_gate_passed']
            assert all(q.state['jobs'][name]['status'] == 'blocked_dependency' for name in ('pilot-mc', 'pilot-rtg', 'software-mc-final', 'software-rtg-final'))
            assert not (q.output / 'resource-budget.json').exists()
        else:
            assert q.state['jobs']['bridge']['outcome']['n0_gate_passed']
            assert all(q.state['jobs'][name]['status'] == 'blocked_budget_record' for name in ('pilot-mc', 'pilot-rtg'))
            assert all(q.state['jobs'][name]['status'] == 'blocked_dependency' for name in ('software-mc-final', 'software-rtg-final'))
    finally:
        q.close()


def test_resume_never_retries_existing_attempt_but_launches_untouched_gated_successors(tmp_path):
    cfg, proc = config(tmp_path), Processes()
    q = executor(tmp_path, cfg, proc)
    q.tick()
    q.close()
    q = executor(tmp_path, cfg, proc, resume=True)
    try:
        q.tick()
        assert len(proc.calls) == 2
        finish_online(q, 'bridge')
        finish_software(q, 'software-initial')
        q.tick()
        assert len(proc.calls) == 4
        assert q.state['jobs']['pilot-mc']['status'] == q.state['jobs']['pilot-rtg']['status'] == 'running'
    finally:
        q.close()
    changed = copy.deepcopy(cfg)
    changed['physical_gpus']['mc'] = [7]
    with pytest.raises(ValueError, match='Resume must retain exact config'):
        executor(tmp_path, changed, proc, resume=True)


def test_unknown_reused_pid_does_not_adopt_or_restart_and_selection_is_not_inferred(tmp_path):
    cfg, proc = config(tmp_path), Processes()
    q = executor(tmp_path, cfg, proc)
    try:
        q.tick()
        job = q.state['jobs']['software-initial']
        _, child = commands(q.config, job)
        job['child_process'] = {'pid': 777, 'start_ticks': 'original', 'command': child}
        proc.live[777] = {'pid': 777, 'start_ticks': 'reused', 'command': child}
        save(Path(job['launch']).with_suffix('.launch.json'), {'command': child, 'cwd': q.config['source'], 'pid': 777,
             'CUDA_VISIBLE_DEVICES': '1', 'PYTHONPATH': str(Path(q.config['source']) / 'src')})
        finish_online(q, 'bridge')
        q.tick()
        assert job['status'] == 'outcome_unknown'
        assert q.state['jobs']['pilot-mc']['status'] == 'blocked_dependency'
        assert q.state['jobs']['pilot-rtg']['status'] == 'blocked_dependency'
        assert len(proc.calls) == 2
    finally:
        q.close()
    selection = json.loads((tmp_path / 'selection.json').read_text())
    selection['status'] = 'not_selected'
    save(tmp_path / 'selection.json', selection)
    with pytest.raises(ValueError, match='explicit completed model selection'):
        normalize_config(cfg)
