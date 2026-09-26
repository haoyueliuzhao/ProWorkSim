"""Pure scheduler fixtures: Popen/PIDs are fake; no GPU or sampling runs."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.run_candidate_screen_v015 import CandidateQueue, normalize_config, stage_commands, write


class Processes:
    def __init__(self):
        self.calls, self.live = [], {}

    def popen(self, command, **kwargs):
        pid = 500 + len(self.calls)
        self.calls.append({'command': command, **kwargs})
        self.live[pid] = {'pid': pid, 'start_ticks': str(pid), 'command': command}
        assert kwargs['start_new_session'] is True
        return SimpleNamespace(pid=pid)

    def pid(self, pid):
        return self.live.get(pid)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def config(tmp_path):
    source = tmp_path/'source'
    source.mkdir()
    candidates = []
    for name, candidate, gpus in [('qwen35-9b', 'qwen3.5-9b', [0]), ('qwen38-27b', 'qwen3.8-27b', [1, 2, 3])]:
        protocol = {'mode': 'evaluate', 'runtime': {'profile': {'candidate_id': candidate, 'dtype': 'float32', 'devices': len(gpus)}},
                    'windows': [{'window_id': name, 'mode': 'evaluate', 'slots': [{'slot_id': str(i)} for i in range(36)]}]}
        save(source/(name+'.json'), protocol)
        candidates.append({'name': name, 'candidate': candidate, 'gpus': gpus, 'dtype': 'float32',
                           'download_manifest': 'download/'+name+'.json', 'model_path': 'models/'+name,
                           'weight_manifest': 'models/'+name+'/proworksim-manifest.json',
                           'preflight_output': 'runs/s0-'+name, 'screen_output': 'runs/s1-'+name,
                           'preflight_launch': 'launch/s0-'+name, 'screen_launch': 'launch/s1-'+name,
                           'screen_protocol': name+'.json'})
    return {'project': str(tmp_path), 'source': str(source), 'source_commit': 'fixture',
            'python': '/fixture/model-python', 'launcher_python': '/fixture/launcher-python', 'launcher': '/fixture/launcher.py',
            'poll_seconds': 1, 'download_wait_seconds': 100, 'candidates': candidates,
            'external_runs': [{'name': 'external-old7b', 'run': 'runs/old7b'}]}


def identity(_):
    return {'commit': 'fixture', 'files': {}}


def queue(tmp_path, cfg, processes, *, resume=False, now=lambda: 0):
    return CandidateQueue(cfg, tmp_path/'supervisor', resume=resume, popen=processes.popen,
                          now=now, identity_fn=identity, pid_fn=processes.pid)


def downloaded(q, index=0, *, manifest=True):
    job = q.config['candidates'][index]
    save(Path(job['download_manifest']), {'status': 'complete', 'model_path': job['model_path']})
    if manifest:
        save(Path(job['weight_manifest']), {'fixture': 'not loaded'})


def finish(q, stage, *, index=0, exit_code=0, probability=False, trace=True):
    job = q.config['candidates'][index]
    _, child = stage_commands(q.config, job, stage)
    meta = {'command': child, 'cwd': q.config['source'], 'CUDA_VISIBLE_DEVICES': ','.join(map(str, job['gpus'])),
            'PYTHONPATH': str(Path(q.config['source'])/'src'), 'pid': 999, 'exit_code': exit_code, 'end': 12}
    save(Path(job[stage+'_launch']).with_suffix('.launch.json'), meta)
    if stage == 'preflight':
        output = Path(job['preflight_output'])
        save(output/'report.json', {'inference_ready': True, 'training_ready': probability, 'statuses': [200],
                                   'probability_checks': [{'passed': probability}], 'errors': [],
                                   'backward': {'executed': probability, 'gradient_finite_nonzero': probability},
                                   'checkpoint': {'serialized_reload_exact': probability}, 'checkpoint_restored': probability})
        if trace:
            save(output/'owner/calls/one.json', {'status': 200, 'response': {'id': 'actual-fixture-response', 'choices': [{}],
                                                                     'token_trace': {'output_ids': [7, 8]}}})


def test_waits_for_both_download_markers_then_numeric_failure_still_screens(tmp_path):
    cfg, proc = config(tmp_path), Processes()
    q = queue(tmp_path, cfg, proc)
    try:
        q.tick()
        assert not proc.calls
        downloaded(q, manifest=False)
        q.tick()
        assert not proc.calls
        downloaded(q)
        q.tick()
        assert len(proc.calls) == 1
        assert proc.calls[0]['env']['CUDA_VISIBLE_DEVICES'] == '0'
        q.tick()
        assert len(proc.calls) == 1  # observing cannot resample
        finish(q, 'preflight', probability=False)
        report_path = Path(q.config['candidates'][0]['preflight_output'])/'report.json'
        reported = json.loads(report_path.read_text())
        reported['training_ready'] = True  # Deliberately contradictory saved boolean.
        save(report_path, reported)
        q.tick()
        assert len(proc.calls) == 2
        state = q.state['jobs'][0]
        assert state['training_ready'] is False and state['status'] == 'screen_running'
        assert q.state['jobs'][1]['screen']['status'] == 'not_started'
        job = q.config['candidates'][0]
        save(Path(job['screen_output'])/'online/report.json', {'status': 'error', 'actor_steps_total': 0, 'critic_steps_total': 0})
        finish(q, 'screen')
        q.tick()
        assert state['status'] == 'screen_incomplete'  # exit0 != completed study
        assert state['screen']['outcome']['not_started_episodes'] == 36
        q.tick()
        assert len(proc.calls) == 2
    finally:
        q.close()


def test_actual_generation_required_and_future_slots_not_filled(tmp_path):
    cfg, proc = config(tmp_path), Processes()
    q = queue(tmp_path, cfg, proc)
    try:
        downloaded(q)
        q.tick()
        finish(q, 'preflight', probability=True, trace=False)
        q.tick()
        state = q.state['jobs'][0]
        assert state['status'] == 'preflight_failed'
        assert state['screen_planned'] == 36 and state['screen']['status'] == 'not_started'
        assert len(proc.calls) == 1
        assert 'reward' not in state
    finally:
        q.close()


def test_resume_observes_same_pid_without_relaunch_and_unknown_exit_never_retries(tmp_path):
    cfg, proc = config(tmp_path), Processes()
    q = queue(tmp_path, cfg, proc)
    downloaded(q)
    q.tick()
    assert len(proc.calls) == 1
    q.close()
    clock = [0]
    q = queue(tmp_path, cfg, proc, resume=True, now=lambda: clock[0])
    try:
        q.tick()
        assert len(proc.calls) == 1 and q.state['jobs'][0]['status'] == 'preflight_running'
        proc.live.clear()
        q.tick()
        assert q.state['jobs'][0]['status'] == 'preflight_running'
        clock[0] = 61
        q.tick()
        assert q.state['jobs'][0]['status'] == 'launch_outcome_unknown'
        q.tick()
        assert len(proc.calls) == 1
    finally:
        q.close()


def test_existing_unattributed_output_refused_and_wait_deadline_is_bounded(tmp_path):
    cfg, proc = config(tmp_path), Processes()
    clock = [0]
    q = queue(tmp_path, cfg, proc, now=lambda: clock[0])
    try:
        downloaded(q)
        Path(q.config['candidates'][0]['preflight_output']).mkdir(parents=True)
        q.tick()
        assert q.state['jobs'][0]['status'] == 'blocked_existing_artifacts' and not proc.calls
        clock[0] = 101
        assert q.tick()
        assert q.state['jobs'][1]['status'] == 'download_timeout'
    finally:
        q.close()


def test_original_config_and_source_required_for_resume(tmp_path):
    cfg, proc = config(tmp_path), Processes()
    q = queue(tmp_path, cfg, proc)
    q.close()
    cfg['candidates'][0]['dtype'] = 'bfloat16'
    # Change both protocol and config to remain locally valid, but differ from queue freeze.
    p=tmp_path/'source/qwen35-9b.json'
    protocol = json.loads(p.read_text())
    protocol['runtime']['profile']['dtype'] = 'bfloat16'
    write(p, protocol)
    with pytest.raises(ValueError, match='Resume config/source differs'):
        queue(tmp_path, cfg, proc, resume=True)


def test_selected_venv_python_symlink_is_not_resolved_to_system_interpreter(tmp_path):
    cfg = config(tmp_path)
    executable = tmp_path/'model-venv/bin/python'
    executable.parent.mkdir(parents=True)
    executable.symlink_to('/usr/bin/python3')
    cfg['python'] = 'model-venv/bin/python'
    normalized = normalize_config(cfg)
    assert normalized['python'] == str(executable)
    assert normalized['python'] != str(executable.resolve())
