"""Fixed download -> S0 -> pure evaluation S1 queue, with no sampling retries.

Downstream processes have independent sessions. Interrupting this observer never
signals them. --resume observes exact prior commands/PIDs/results, not reruns.
"""
import argparse
import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

VERSION = 'candidate-screen-queue-v0.15'
INVENTORY = {'qwen35-9b': {'candidate': 'qwen3.5-9b', 'gpus': [0]},
             'qwen38-27b': {'candidate': 'qwen3.8-27b', 'gpus': [1, 2, 3]}}
FINAL = {'complete', 'screen_incomplete', 'preflight_failed', 'download_timeout',
         'blocked_existing_artifacts', 'launch_outcome_unknown', 'launch_failed', 'download_identity_mismatch'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def read(path):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        # External download/launcher writers may be between writes. Do not act
        # on a partial file; retain waiting or last known state.
        return None


def write(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def resolve(root, path):
    value = Path(path)
    return str((value if value.is_absolute() else Path(root) / value).resolve())


def pid_record(pid):
    if type(pid) is not int or pid <= 0:
        return None
    try:
        stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if stat[0] == 'Z':
            return None
        command = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        return {'pid': pid, 'start_ticks': stat[19], 'command': [x.decode() for x in command if x]}
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None


def pid_matches(record):
    current = pid_record((record or {}).get('pid'))
    return bool(current and current['start_ticks'] == record.get('start_ticks')
                and current['command'] == record.get('command'))


def normalize_config(raw):
    config = copy.deepcopy(raw)
    config['project'] = str(Path(config['project']).resolve())
    config['source'] = resolve(config['project'], config['source'])
    # Preserve venv interpreter symlinks: resolving them to /usr/bin/python
    # would silently discard the selected environment and its dependencies.
    for key in ('python', 'launcher_python'):
        value = config[key]
        config[key] = os.path.abspath(value if os.path.isabs(value) else os.path.join(config['project'], value))
    config['launcher'] = resolve(config['project'], config['launcher'])
    config.setdefault('poll_seconds', 30)
    config.setdefault('download_wait_seconds', 172800)
    config.setdefault('environment', {})
    config.setdefault('external_runs', [])
    if type(config['poll_seconds']) not in (int, float) or not 1 <= config['poll_seconds'] <= 60:
        raise ValueError('Poll interval must be 1..60 seconds')
    if type(config['download_wait_seconds']) not in (int, float) or not math.isfinite(config['download_wait_seconds']) or config['download_wait_seconds'] <= 0:
        raise ValueError('Declare a finite positive download wait budget')
    if set(config['environment']) & {'CUDA_VISIBLE_DEVICES', 'PYTHONPATH'}:
        raise ValueError('GPU/source environment is fixed by this queue')
    jobs = config['candidates']
    if {j['name'] for j in jobs} != set(INVENTORY) or len(jobs) != 2:
        raise ValueError('This fixed queue accepts exactly the two registered new candidates')
    occupied = set()
    for job in jobs:
        expected = INVENTORY[job['name']]
        if job['candidate'] != expected['candidate'] or job['gpus'] != expected['gpus']:
            raise ValueError('Candidate and physical GPU inventory differ from the frozen mapping')
        if job.get('devices', len(job['gpus'])) != len(job['gpus']):
            raise ValueError('Logical device count must match fixed GPU inventory')
        job['devices'] = len(job['gpus'])
        if job['dtype'] not in {'float32', 'bfloat16'}:
            raise ValueError('Declare the numeric profile, no fallback dtype')
        for key in ('download_manifest', 'model_path', 'weight_manifest', 'preflight_output', 'screen_output', 'preflight_launch', 'screen_launch'):
            job[key] = resolve(config['project'], job[key])
        job['screen_protocol'] = resolve(config['source'], job['screen_protocol'])
        if Path(job['weight_manifest']) != Path(job['model_path']) / 'proworksim-manifest.json':
            raise ValueError('Use the completed model directory weight manifest')
        for key in ('preflight_output', 'screen_output', 'preflight_launch', 'screen_launch'):
            if job[key] in occupied:
                raise ValueError('Stage outputs and launch prefixes must be unique')
            occupied.add(job[key])
    for job in config['external_runs']:
        job['run'] = resolve(config['project'], job['run'])
    return config


def source_identity(config):
    source = config['source']
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    if not head.startswith(config['source_commit']):
        raise ValueError('Frozen checkout differs from declared source commit')
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=source, text=True).strip()
    if dirty:
        raise ValueError('Frozen source checkout must be clean')
    paths = [Path(source)/'scripts/candidate_preflight_v015.py', Path(source)/'scripts/online_learning_v015.py', Path(config['launcher'])]
    paths += [Path(j['screen_protocol']) for j in config['candidates']]
    return {'commit': head, 'files': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def validate_protocols(config):
    for job in config['candidates']:
        protocol = read(job['screen_protocol'])
        if not protocol or protocol.get('mode') != 'evaluate':
            raise ValueError('S1 is strictly pure evaluation')
        windows = protocol.get('windows', [])
        if sum(len(w.get('slots', [])) for w in windows) != 36 or not windows:
            raise ValueError('Each candidate has exactly 36 fixed S1 slots')
        if any(w.get('mode', protocol['mode']) != 'evaluate' for w in windows):
            raise ValueError('No online update window may enter screening')
        profile = protocol['runtime']['profile']
        if any(profile.get(k) != job[k] for k in ('dtype', 'devices')) or profile.get('candidate_id') != job['candidate']:
            raise ValueError('S0 and S1 must use the same declared candidate/numeric profile')


def stage_commands(config, job, stage):
    source = Path(config['source'])
    if stage == 'preflight':
        child = [config['python'], str(source/'scripts/candidate_preflight_v015.py'),
                 '--model-path', job['model_path'], '--manifest', job['weight_manifest'],
                 '--candidate', job['candidate'], '--devices', str(job['devices']), '--dtype', job['dtype'],
                 '--output', job['preflight_output']]
    else:
        child = [config['python'], str(source/'scripts/online_learning_v015.py'),
                 '--protocol', job['screen_protocol'], '--model', job['model_path'],
                 '--weight-manifest', job['weight_manifest'], '--output', job['screen_output']]
    wrapper = [config['launcher_python'], config['launcher'], job[stage+'_launch'], *child]
    return wrapper, child


def preflight_outcome(output, exit_code):
    output = Path(output)
    report = read(output/'report.json')
    generations = []
    for path in sorted((output/'owner/calls').glob('*.json')):
        ledger = read(path) or {}
        body = ledger.get('response') or {}
        trace = body.get('token_trace') or {}
        if ledger.get('status') == 200 and body.get('choices') and isinstance(trace.get('output_ids'), list) and trace['output_ids']:
            generations.append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                'response_id': body.get('id'), 'output_tokens': len(trace['output_ids'])})
    statuses = (report or {}).get('statuses', [])
    inference_ready = exit_code == 0 and (report or {}).get('inference_ready') is True and 200 in statuses and bool(generations)
    checks = (report or {}).get('probability_checks') or []
    backward = (report or {}).get('backward') or {}
    numerical_ok = bool(checks) and all(c.get('passed') is True for c in checks)
    backward_ok = backward.get('executed') is True and backward.get('gradient_finite_nonzero') is True
    checkpoint_ok = ((report or {}).get('checkpoint') or {}).get('serialized_reload_exact') is True and (report or {}).get('checkpoint_restored') is True
    return {'inference_ready_for_screen': inference_ready,
            'training_ready': bool((report or {}).get('training_ready') is True and inference_ready and numerical_ok and backward_ok and checkpoint_ok and not (report or {}).get('errors')),
            'probability_gate_passed': numerical_ok, 'backward_gate_passed': backward_ok,
            'checkpoint_serialized_reload_exact': checkpoint_ok, 'exit_code': exit_code,
            'report_present': bool(report), 'reported_statuses': statuses, 'actual_generations': generations,
            'recorded_errors': (report or {}).get('errors'),
            'scope': 'Inference readiness admits pure S1; training readiness is separate. This is not a work ability score.'}


def screen_outcome(output, exit_code):
    output = Path(output)
    online = read(output/'online/report.json') or {}
    protocol = read(output/'online/protocol.json') or read(output/'launch-protocol.json') or {}
    closed, started = 0, 0
    for wi, window in enumerate(protocol.get('windows', [])):
        for si, _ in enumerate(window.get('slots', [])):
            manifest = read(output/f'online/window-{wi}/collection/slot-{si}/episode/manifest.json')
            started += bool(manifest)
            closed += bool(manifest and manifest.get('status') == 'closed')
    return {'exit_code': exit_code, 'online_status': online.get('status', 'no_online_report'),
            'closed_episodes': closed, 'started_episodes': started, 'open_episodes': started-closed,
            'not_started_episodes': 36-started, 'planned_episodes': 36,
            'actor_steps': online.get('actor_steps_total'), 'critic_steps': online.get('critic_steps_total'),
            'interruption': read(output/'interruption.json'),
            'execution_complete': exit_code == 0 and online.get('status') == 'complete' and closed == 36
                                  and online.get('actor_steps_total') == 0 and online.get('critic_steps_total') == 0,
            'scope': 'Process exit is not work success. No missing slot is assigned reward zero; full work metrics require the original read-only report.'}


class CandidateQueue:
    def __init__(self, config, output, *, resume=False, popen=subprocess.Popen,
                 now=time.time, identity_fn=source_identity, pid_fn=pid_record):
        self.config, self.output = normalize_config(config), Path(output).resolve()
        self.popen, self.now, self.identity_fn, self.pid_fn = popen, now, identity_fn, pid_fn
        validate_protocols(self.config)
        source = identity_fn(self.config)
        if resume:
            if not self.output.is_dir():
                raise FileNotFoundError('Resume requires an existing queue output')
        else:
            self.output.mkdir(parents=True, exist_ok=False)
        self.lock = (self.output/'queue.lock').open('a')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        record = self.output/'scheduler.json'
        if resume:
            self.state = read(record)
            if not self.state or self.state.get('config') != self.config or self.state.get('source_identity') != source:
                self.lock.close()
                raise ValueError('Resume config/source differs from original fixed queue')
        else:
            self.state = {'version': VERSION, 'config': self.config, 'source_identity': source,
                          'created_at': self.now(), 'status': 'running', 'jobs': [], 'supervisor_history': [],
                          'scope': 'Fixed inventory, independent process sessions, no outcome-driven resampling or profile fallback; interrupting supervisor never signals downstream.'}
            for job in self.config['candidates']:
                self.state['jobs'].append({'name': job['name'], 'status': 'waiting_download', 'training_ready': None,
                                          'screen_planned': 36, 'preflight': {'status': 'not_started'}, 'screen': {'status': 'not_started'}})
            write(self.output/'config.json', self.config)
        self.state['supervisor_history'].append({'pid': os.getpid(), 'at': self.now(), 'resume': resume})
        self.state['status'] = 'running'
        self.persist()

    def persist(self):
        self.state['observed_at'] = self.now()
        write(self.output/'scheduler.json', self.state)

    def close(self):
        self.lock.close()

    def _meta(self, job, stage):
        return read(Path(job[stage+'_launch']).with_suffix('.launch.json'))

    def _meta_matches(self, job, stage, meta):
        _, child = stage_commands(self.config, job, stage)
        return (meta.get('command') == child and meta.get('cwd') == self.config['source']
                and meta.get('CUDA_VISIBLE_DEVICES') == ','.join(map(str, job['gpus']))
                and meta.get('PYTHONPATH') == str(Path(self.config['source'])/'src'))

    def _launch(self, job, state, stage):
        entry = state[stage]
        prefix, out = Path(job[stage+'_launch']), Path(job[stage+'_output'])
        meta = self._meta(job, stage)
        if meta:
            if not self._meta_matches(job, stage, meta):
                state.update(status='blocked_existing_artifacts', blocked_reason='Existing launch metadata differs from fixed command')
                return
            entry.update(status='running', adopted_existing=True, launch_meta=meta)
            self.persist()
            return
        if out.exists() or any(prefix.with_suffix(s).exists() for s in ('.log', '.resources.jsonl', '.launch.json')):
            state.update(status='blocked_existing_artifacts', blocked_reason='Existing output lacks matching launch evidence; refuse overwrite/restart')
            self.persist()
            return
        if self.identity_fn(self.config) != self.state['source_identity']:
            raise ValueError('Frozen source changed while awaiting download')
        command, child = stage_commands(self.config, job, stage)
        environment = {**os.environ, **self.config['environment'],
                       'CUDA_VISIBLE_DEVICES': ','.join(map(str, job['gpus'])),
                       'PYTHONPATH': str(Path(self.config['source'])/'src')}
        entry.update(status='launch_intent', intended_at=self.now(), command=command, child_command=child,
                     cwd=self.config['source'], assigned_gpus=job['gpus'])
        self.persist()  # Any crash after this is ambiguous and never authorizes retry.
        try:
            with (self.output/(job['name']+'-'+stage+'.supervisor.log')).open('x') as log:
                process = self.popen(command, cwd=self.config['source'], env=environment, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            entry.update(status='running', started_at=self.now(), launcher_pid=process.pid,
                         launcher_process=self.pid_fn(process.pid))
        except Exception as error:
            entry.update(status='launch_failed', error={'type': type(error).__name__, 'message': str(error)})
            state['status'] = 'launch_failed'
        self.persist()

    def _observe(self, job, state, stage):
        entry = state[stage]
        meta = self._meta(job, stage)
        if meta:
            if not self._meta_matches(job, stage, meta):
                state.update(status='blocked_existing_artifacts', blocked_reason='Launch metadata no longer matches fixed command')
                return
            entry['launch_meta'] = meta
            if meta.get('exit_code') is not None:
                entry.pop('missing_process_since', None)
                entry.update(status='finished', exit_code=meta['exit_code'], ended_at=meta.get('end', self.now()))
                return
            child = self.pid_fn(meta.get('pid'))
            _, expected = stage_commands(self.config, job, stage)
            if child and child.get('command') == expected:
                entry.pop('missing_process_since', None)
                entry['child_process'] = child
                entry['status'] = 'running'
                return
        launcher = entry.get('launcher_process')
        current = self.pid_fn((launcher or {}).get('pid'))
        if launcher and current and current == launcher:
            entry.pop('missing_process_since', None)
            return
        # Existing launcher metadata is not atomically written. Give its final
        # write a bounded observation grace, never another launch attempt.
        entry.setdefault('missing_process_since', self.now())
        if self.now()-entry['missing_process_since'] < 60:
            return
        # No completion code can be recovered after an orphaned launcher. We
        # keep the raw output, leave S1 unstarted, and never infer exit zero.
        state.update(status='launch_outcome_unknown', blocked_reason=f'{stage} has no live matched process and no finalized exit record; no retry')
        entry['status'] = 'outcome_unknown'

    def tick(self):
        for job, state in zip(self.config['candidates'], self.state['jobs']):
            if state['status'] in FINAL:
                continue
            if state['preflight']['status'] == 'not_started':
                download = read(job['download_manifest'])
                state['download_observation'] = {'path': job['download_manifest'], 'status': (download or {}).get('status'),
                                                'model_manifest_exists': Path(job['weight_manifest']).is_file()}
                if download and download.get('model_path') and str(Path(download['model_path']).resolve()) != job['model_path']:
                    state['status'] = 'download_identity_mismatch'
                    continue
                if not download or download.get('status') != 'complete' or not Path(job['weight_manifest']).is_file():
                    if self.now()-self.state['created_at'] >= self.config['download_wait_seconds']:
                        state['status'] = 'download_timeout'
                    continue
                self._launch(job, state, 'preflight')
                if state['status'] in FINAL:
                    continue
                state['status'] = 'preflight_running'
            if state['preflight']['status'] in {'running', 'launch_intent'}:
                self._observe(job, state, 'preflight')
            if state['status'] in FINAL:
                continue
            if state['preflight']['status'] != 'finished':
                continue
            if 'outcome' not in state['preflight']:
                outcome = preflight_outcome(job['preflight_output'], state['preflight']['exit_code'])
                state['preflight']['outcome'] = outcome
                state['training_ready'] = outcome['training_ready']
            if not state['preflight']['outcome']['inference_ready_for_screen']:
                state['status'] = 'preflight_failed'
                continue
            if state['screen']['status'] == 'not_started':
                self._launch(job, state, 'screen')
                if state['status'] in FINAL:
                    continue
                state['status'] = 'screen_running'
            if state['screen']['status'] in {'running', 'launch_intent'}:
                self._observe(job, state, 'screen')
            if state['status'] in FINAL:
                continue
            if state['screen']['status'] == 'finished':
                result = screen_outcome(job['screen_output'], state['screen']['exit_code'])
                state['screen']['outcome'] = result
                state['status'] = 'complete' if result['execution_complete'] else 'screen_incomplete'
        self.state['external_runs'] = []
        for job in self.config['external_runs']:
            report = read(Path(job['run'])/'online/report.json') or {}
            self.state['external_runs'].append({**job, 'online_status': report.get('status', 'unrecorded_or_running'),
                                                'actor_steps': report.get('actor_steps_total'), 'scope': 'Read only; never started/stopped by this queue'})
        done = all(j['status'] in FINAL for j in self.state['jobs'])
        if done:
            self.state['status'] = 'complete' if all(j['status'] == 'complete' for j in self.state['jobs']) else 'finished_with_incomplete_jobs'
            self.state['ended_at'] = self.now()
        self.persist()
        return done


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    queue = CandidateQueue(read(args.config), args.output, resume=args.resume)
    try:
        while not queue.tick():
            time.sleep(queue.config['poll_seconds'])
    except (KeyboardInterrupt, SystemExit):
        queue.state.update(status='observer_detached', detached_at=time.time(),
                           detach_scope='Downstream sessions are intentionally left running; --resume only observes prior attempts.')
        queue.persist()
        return 130
    except Exception as error:
        queue.state.update(status='observer_error', error={'type': type(error).__name__, 'message': str(error)},
                           detach_scope='No downstream process was signalled or restarted.')
        queue.persist()
        raise
    finally:
        queue.close()
    return 0 if queue.state['status'] == 'complete' else 1


if __name__ == '__main__':
    sys.exit(main())
