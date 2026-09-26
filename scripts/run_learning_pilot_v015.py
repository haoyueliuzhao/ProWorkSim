"""Six fixed post-selection jobs; no model ranking, retries or resampling.

Initial execution schedules N0/software-initial, then gated N1 MC/RTG and each
completed condition's software-final. Children use independent sessions. Resume
observes existing attempts only, while never-attempted frozen successors may
start once their declared gate passes. It never signals a PID or retries a job.
"""
import argparse
import copy
import fcntl
import hashlib
import math
import os
from pathlib import Path
import subprocess
import sys
import time

if __package__:
    from .build_learning_pilot_v015 import build_protocols as build_pilot
    from .build_software_eval_v015 import build_protocols as build_software
    from .run_candidate_screen_v015 import pid_record, read, resolve, write
else:
    from build_learning_pilot_v015 import build_protocols as build_pilot
    from build_software_eval_v015 import build_protocols as build_software
    from run_candidate_screen_v015 import pid_record, read, resolve, write

VERSION = 'selected-learning-pilot-executor-v0.15'
NAMES = ('bridge', 'software-initial', 'pilot-mc', 'pilot-rtg', 'software-mc-final', 'software-rtg-final')
TERMINAL = {'complete', 'incomplete', 'blocked_dependency', 'launch_failed', 'outcome_unknown',
            'blocked_existing_artifacts', 'blocked_budget_record', 'blocked_source_changed'}
ACTIVE = {'launch_intent', 'running'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize_config(raw):
    config = copy.deepcopy(raw)
    config['project'] = str(Path(config['project']).resolve())
    for key in ('source', 'launcher', 'model_path', 'weight_manifest', 'selected_screen_protocol', 'selection_record'):
        config[key] = resolve(config['project'], config[key])
    for key in ('python', 'launcher_python'):
        value = config[key]
        # Do not resolve venv symlinks to their base interpreter.
        config[key] = os.path.abspath(value if os.path.isabs(value) else os.path.join(config['project'], value))
    config.setdefault('environment', {})
    config.setdefault('poll_seconds', 30)
    config.setdefault('budget_safety_factor', 1.25)
    if set(config['environment']) & {'CUDA_VISIBLE_DEVICES', 'PYTHONPATH'}:
        raise ValueError('GPU/source environment is controlled by the frozen executor')
    if not 1 <= config['poll_seconds'] <= 60:
        raise ValueError('Poll interval must be 1..60 seconds')
    if not isinstance(config['budget_safety_factor'], (int, float)) or not math.isfinite(config['budget_safety_factor']) or config['budget_safety_factor'] < 1:
        raise ValueError('Predeclare a finite budget safety factor >= 1')
    screen = read(config['selected_screen_protocol'])
    selection = read(config['selection_record'])
    if not screen or not selection or selection.get('status') != 'selected':
        raise ValueError('An explicit completed model selection is required')
    candidate = screen.get('candidate_id')
    selected_record = selection.get('selected', {})
    selected = selected_record.get('candidate_id')
    protocol_ref = selected_record.get('screen_protocol', {})
    recorded_sha = protocol_ref.get('sha256') if isinstance(protocol_ref, dict) else None
    if selected != candidate or recorded_sha != sha(config['selected_screen_protocol']):
        raise ValueError('Selection candidate/protocol SHA differs from explicit screen input')
    devices = {'qwen35-9b': 1, 'qwen38-27b': 3, 'qwen25-7b': 1}.get(candidate)
    if devices is None:
        raise ValueError('Explicit selection is not one of the registered candidate conditions')
    if screen.get('stage') != 'screen' or screen.get('mode') != 'evaluate':
        raise ValueError('Input must be the selected pure-evaluation screen protocol')
    runtime = screen['runtime']
    if runtime.get('kind') in {'qwen_hybrid', 'qwen_hybrid_chatstop'}:
        expected_internal = {'qwen35-9b': 'qwen3.5-9b', 'qwen38-27b': 'qwen3.8-27b'}.get(candidate)
        if runtime.get('profile', {}).get('candidate_id') != expected_internal:
            raise ValueError('Screen condition and native runtime candidate identities differ')
    elif runtime.get('kind') != 'qwen25_legacy' or candidate != 'qwen25-7b':
        raise ValueError('Unknown explicitly selected runtime; no fallback')
    declared_devices = runtime.get('profile', {}).get('devices', 1)
    if declared_devices != devices:
        raise ValueError('Selected runtime differs from the frozen candidate device count')
    for key, wanted in (('logprob_max_atol', .02), ('logprob_mean_atol', .002)):
        if screen['recipe'].get(key) != wanted:
            raise ValueError('Original probability engineering gate must remain 0.02 / 0.002')
    inventory = config['physical_gpus']
    if set(inventory) != {'mc', 'rtg'}:
        raise ValueError('Declare exactly physical_gpus.mc and physical_gpus.rtg')
    for allocation in inventory.values():
        if len(allocation) != devices or len(set(allocation)) != devices or any(type(gpu) is not int or gpu < 0 for gpu in allocation):
            raise ValueError('Each explicit lane must match the selected device count')
    if set(inventory['mc']) & set(inventory['rtg']):
        raise ValueError('The two concurrent lanes must use disjoint physical GPU sets')
    config['candidate_id'], config['devices_per_job'] = candidate, devices
    return config


def source_identity(config):
    source = Path(config['source'])
    if source != Path(__file__).resolve().parents[1]:
        raise ValueError('Run the executor from the declared frozen source checkout')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    if commit != config['source_commit']:
        raise ValueError('Frozen source commit must match exactly')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=source, text=True).strip():
        raise ValueError('Frozen source checkout must be clean')
    files = [config[key] for key in ('launcher', 'weight_manifest', 'selected_screen_protocol', 'selection_record')]
    files += [str(source / 'scripts' / name) for name in ('run_learning_pilot_v015.py', 'run_candidate_screen_v015.py',
              'build_learning_pilot_v015.py', 'build_software_eval_v015.py', 'online_learning_v015.py', 'software_model_v015.py')]
    return {'commit': commit, 'files': {path: sha(path) for path in sorted(files)}}


def commands(config, job):
    script = 'software_model_v015.py' if job['kind'] == 'software' else 'online_learning_v015.py'
    child = [config['python'], str(Path(config['source']) / 'scripts' / script), '--protocol', job['protocol'],
             '--model', config['model_path'], '--weight-manifest', config['weight_manifest'], '--output', job['run']]
    if job.get('restore_checkpoint'):
        child += ['--restore-checkpoint', job['restore_checkpoint']]
    return [config['launcher_python'], config['launcher'], job['launch'], *child], child


def online_outcome(job, exit_code):
    root = Path(job['run'])
    protocol = read(job['protocol']) or {}
    saved = read(root / 'online/report.json') or {}
    expected = protocol.get('windows', [])
    records = saved.get('windows', [])
    started = closed = 0
    for wi, window in enumerate(expected):
        for si, _ in enumerate(window['slots']):
            manifest = read(root / f'online/window-{wi}/collection/slot-{si}/episode/manifest.json')
            started += bool(manifest)
            closed += bool(manifest and manifest.get('status') == 'closed')
    planned = sum(len(window['slots']) for window in expected)
    matching = (len(records) == len(expected) and all(row.get('window_id') == spec['window_id']
                 and row.get('mode') == spec['mode'] and row.get('status') == 'complete' for row, spec in zip(records, expected)))
    frozen_protocol = read(root / 'online/protocol.json')
    result = {'exit_code': exit_code, 'online_status': saved.get('status'), 'planned_episodes': planned,
              'started_episodes': started, 'closed_episodes': closed, 'not_started_episodes': planned - started,
              'open_episodes': started - closed, 'actor_steps': saved.get('actor_steps_total'),
              'critic_steps': saved.get('critic_steps_total'), 'matching_windows': matching,
              'execution_complete': exit_code == 0 and saved.get('status') == 'complete' and matching
                                    and closed == planned and frozen_protocol == protocol,
              'interruption': read(root / 'interruption.json')}
    if job['name'] != 'bridge':
        return result
    gates = []
    for index in range(2):
        folder = root / f'online/window-{index}/update'
        update = read(folder / 'report.json') or {}
        checks = {}
        for name in ('behavior', 'gradient'):
            rows = read(folder / (name + '-probability-check.json')) or []
            checks[name] = bool(rows) and len(rows) == update.get('admitted_decisions') and all(
                row.get('passed') is True and type(row.get('max_abs_delta')) in (int, float)
                and type(row.get('mean_abs_delta')) in (int, float)
                and 0 <= row['max_abs_delta'] <= .02 and 0 <= row['mean_abs_delta'] <= .002 for row in rows)
        gates.append({'window': index, 'probability': checks,
                      'actor_steps': update.get('actor_optimizer_steps'), 'critic_steps': update.get('critic_optimizer_steps'),
                      'updated': update.get('status') == 'updated' and update.get('actor_optimizer_steps') == 1
                                 and update.get('critic_optimizer_steps') == 1})
    initial = read(root / 'online/initial-checkpoint/checkpoint.json') or {}
    gate = (result['execution_complete'] and planned == 32 and len(expected) == 2
            and all(window.get('mode') == 'online' and len(window['slots']) == 16 for window in expected)
            and result['actor_steps'] == result['critic_steps'] == 2
            and initial.get('actor_steps') == initial.get('critic_steps') == 0
            and not (root / 'restored-checkpoint.json').exists()
            and all(row['updated'] and all(row['probability'].values()) for row in gates))
    result.update(n0_gate_passed=gate, bridge_window_gates=gates,
                  gate_scope='Actual 32 closed episodes, two fresh online windows, two actor and critic updates, both original probability gates; no outcome-based refill.')
    return result


def software_outcome(job, exit_code):
    root = Path(job['run'])
    protocol = read(job['protocol']) or {}
    report = read(root / 'report.json') or {}
    started = closed = 0
    rows = []
    for spec in protocol.get('episodes', []):
        folder = root / spec['episode_id']
        manifest, result = read(folder / 'episode/manifest.json'), read(folder / 'result.json')
        started += bool(manifest)
        is_closed = bool(manifest and manifest.get('status') == 'closed')
        closed += is_closed
        rows.append({'episode_id': spec['episode_id'], 'sampling_seed': spec['sampling_seed'],
                     'state': 'closed' if is_closed else 'open' if manifest else 'not_started',
                     'saved_assessment': (result or {}).get('assessment'),
                     'termination': (result or {}).get('termination')})
    guards = report.get('episodes', [])
    matched = len(guards) == len(rows) and all(row.get('episode_id') == spec['episode_id']
                and row.get('sampling_seed') == spec['sampling_seed']
                and row.get('evaluation_guard', {}).get('learning_unchanged') is True
                and row.get('evaluation_guard', {}).get('rng_restored_exactly') is True
                for row, spec in zip(guards, protocol.get('episodes', [])))
    return {'exit_code': exit_code, 'status': report.get('status'), 'planned_episodes': 3,
            'started_episodes': started, 'closed_episodes': closed, 'open_episodes': started - closed,
            'not_started_episodes': 3 - started, 'episodes': rows,
            'execution_complete': exit_code == 0 and report.get('status') == 'complete' and closed == 3 and matched
                                  and report.get('actual_optimizer_steps') == {'actor': 0, 'critic': 0}}


class PilotExecutor:
    def __init__(self, config, output, *, resume=False, popen=subprocess.Popen, now=time.time,
                 identity_fn=source_identity, pid_fn=pid_record):
        self.config, self.output = normalize_config(config), Path(output).resolve()
        self.resume, self.popen, self.now = resume, popen, now
        self.identity_fn, self.pid_fn = identity_fn, pid_fn
        identity = identity_fn(self.config)
        if resume:
            if not self.output.is_dir():
                raise FileNotFoundError('Resume requires the existing executor directory')
        else:
            self.output.mkdir(parents=True, exist_ok=False)
        self.lock = (self.output / 'executor.lock').open('a')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if resume:
            self.state = read(self.output / 'scheduler.json')
            if not self.state or self.state['config'] != self.config or self.state['source_identity'] != identity:
                self.lock.close()
                raise ValueError('Resume must retain exact config, selected inputs and frozen source')
        else:
            self.state = {'version': VERSION, 'config': self.config, 'source_identity': identity,
                          'created_at': now(), 'status': 'running', 'jobs': {}, 'supervisors': []}
            self._prepare()
        self.state['supervisors'].append({'pid': os.getpid(), 'at': now(), 'resume_existing_attempts_only': resume})
        self.persist()

    def _prepare(self):
        protocols = self.output / 'protocols'
        protocols.mkdir(exist_ok=False)
        selected = read(self.config['selected_screen_protocol'])
        generated = build_pilot(selected)
        for condition in ('mc', 'rtg'):
            generated[f'pilot-{condition}.json']['shared_initialization'] = {
                'directory': str(self.output / 'initialization'), 'participant': condition,
                'participants': ['mc', 'rtg'], 'timeout_seconds': 1800}
        software, study = build_software(selected)
        generated.update(software)
        for name, protocol in generated.items():
            write(protocols / name, protocol)
        uci_jobs = []
        for name in NAMES:
            kind = 'software' if name.startswith('software-') else 'online'
            lane = 'rtg' if name in {'software-initial', 'pilot-rtg', 'software-rtg-final'} else 'mc'
            protocol = protocols / (name + '.json')
            run = self.output / 'runs' / name
            job = {'name': name, 'kind': kind, 'lane': lane, 'gpus': self.config['physical_gpus'][lane],
                   'protocol': str(protocol), 'protocol_sha256': sha(protocol), 'run': str(run), 'launch': str(self.output / 'launch' / name),
                   'status': 'not_started', 'planned_episodes': 3 if kind == 'software' else (32 if name == 'bridge' else 104 if name == 'pilot-mc' else 84)}
            if name.startswith('software-') and name != 'software-initial':
                condition = name.split('-')[1]
                pilot = generated[f'pilot-{condition}.json']
                job['restore_checkpoint'] = str(self.output / 'runs' / f'pilot-{condition}' / 'online'
                    / ('window-' + str(len(pilot['windows']) - 1)) / 'checkpoint')
            self.state['jobs'][name] = job
            if kind == 'online':
                uci_jobs.append({'name': name, 'protocol': str(protocol), 'protocol_sha256': sha(protocol), 'run': str(run), 'condition': generated[name + '.json']['condition'],
                                 'candidate_id': self.config['candidate_id'], 'launch': job['launch']})
        for job in study['jobs']:
            own = self.state['jobs'][job['name']]
            job.update(protocol=own['protocol'], run=own['run'], launch=own['launch'],
                       protocol_relative_to='absolute', run_relative_to='absolute')
        write(self.output / 'software-study.json', study)
        write(self.output / 'uci-study.json', {
            'version': 'learning-study-v0.15', 'stage': 'post_selection', 'jobs': uci_jobs,
            'baseline_references': [{'consumer_run': 'pilot-rtg', 'source_run': 'pilot-mc',
                'source_window_ids': ['pilot-common-initial-development', 'pilot-common-initial-locked'],
                'measurement_counted_once': True,
                'reuse_validity': 'Requires actual equal shared-initialization evidence; this declaration does not verify reuse.',
                'shared_initialization_directory': str(self.output / 'initialization')}],
        })
        write(self.output / 'config.json', self.config)
        (self.output / 'launch').mkdir()

    def persist(self):
        self.state['observed_at'] = self.now()
        write(self.output / 'scheduler.json', self.state)

    def close(self):
        self.lock.close()

    def _matches_meta(self, job, meta):
        _, child = commands(self.config, job)
        return (meta.get('command') == child and meta.get('cwd') == self.config['source']
                and meta.get('CUDA_VISIBLE_DEVICES') == ','.join(map(str, job['gpus']))
                and meta.get('PYTHONPATH') == str(Path(self.config['source']) / 'src'))

    def _launch(self, job):
        if job['status'] != 'not_started' or 'intended_at' in job:
            raise ValueError('Only a never-attempted frozen stage may be launched')
        prefix, output = Path(job['launch']), Path(job['run'])
        if output.exists() or any(prefix.with_suffix(ext).exists() for ext in ('.launch.json', '.log', '.resources.jsonl')):
            job.update(status='blocked_existing_artifacts', reason='No adoption or overwrite of preexisting stage outputs')
            return
        if (self.identity_fn(self.config) != self.state['source_identity']
                or sha(job['protocol']) != job['protocol_sha256']):
            job.update(status='blocked_source_changed', reason='Frozen source or selected inputs changed')
            return
        command, child = commands(self.config, job)
        environment = {**os.environ, **self.config['environment'], 'CUDA_VISIBLE_DEVICES': ','.join(map(str, job['gpus'])),
                       'PYTHONPATH': str(Path(self.config['source']) / 'src')}
        job.update(status='launch_intent', command=command, child_command=child, intended_at=self.now())
        self.persist()  # A crash after intent never authorizes another attempt.
        try:
            with (self.output / (job['name'] + '.supervisor.log')).open('x') as log:
                process = self.popen(command, cwd=self.config['source'], env=environment, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            job.update(status='running', started_at=self.now(), launcher_pid=process.pid,
                       launcher_process=self.pid_fn(process.pid))
        except Exception as error:
            job.update(status='launch_failed', error={'type': type(error).__name__, 'message': str(error)})
        self.persist()

    @staticmethod
    def _parent_pid(pid):
        try:
            return int(Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            return None

    def _observe(self, job):
        meta = read(Path(job['launch']).with_suffix('.launch.json'))
        if meta:
            if not self._matches_meta(job, meta):
                job.update(status='blocked_existing_artifacts', reason='Launch command/cwd/GPU/source no longer matches')
                return
            job['launch_meta'] = meta
            if meta.get('exit_code') is not None:
                job.update(status='finished', exit_code=meta['exit_code'], ended_at=meta.get('end', self.now()))
                return
            current = self.pid_fn(meta.get('pid'))
            saved = job.get('child_process')
            if current and current['command'] == job['child_command']:
                if saved is not None and current != saved:
                    job.update(status='outcome_unknown', reason='Child PID/startticks/command identity changed; do not adopt reused PID')
                    return
                launcher = job.get('launcher_process')
                if saved is not None or (launcher and self.pid_fn(launcher['pid']) == launcher
                                         and self._parent_pid(current['pid']) == launcher['pid']):
                    job['child_process'] = current
                    job.pop('missing_process_since', None)
                    return
        saved = job.get('launcher_process')
        if saved is not None and self.pid_fn(saved['pid']) == saved:
            job.pop('missing_process_since', None)
            return
        job.setdefault('missing_process_since', self.now())
        if self.now() - job['missing_process_since'] >= 60:
            job.update(status='outcome_unknown', reason='No exact live process or final launcher exit record; no retry')

    def _budget(self):
        path = self.output / 'resource-budget.json'
        if path.exists():
            bound = self.state.get('resource_budget')
            return bool(bound and bound.get('path') == str(path) and bound.get('sha256') == sha(path) and read(path))
        bridge = self.state['jobs']['bridge']
        elapsed = bridge.get('launch_meta', {}).get('elapsed')
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed <= 0:
            return False
        devices, factor = len(bridge['gpus']), self.config['budget_safety_factor']
        initial = self.state['jobs']['software-initial']
        own = initial.get('launch_meta', {}).get('elapsed')
        actual_software = initial.get('outcome', {}).get('execution_complete') and type(own) in (int, float) and own > 0
        per_software = own / 3 if actual_software else elapsed / 32
        record = {'version': 'selected-pilot-resource-budget-v0.15', 'frozen_at': self.now(),
                  'observed_N0': {'closed_episodes': 32, 'launcher_observed_process_seconds': elapsed,
                                  'allocated_devices': devices, 'allocated_device_seconds': elapsed * devices,
                                  'physical_gpus': bridge['gpus'], 'launch_metadata': str(Path(bridge['launch']).with_suffix('.launch.json'))},
                  'safety_factor': factor, 'planned_N1': {'training': 128, 'evaluation': 60, 'total': 188,
                        'process_seconds_estimate': elapsed / 32 * 188 * factor,
                        'allocated_device_seconds_estimate': elapsed / 32 * 188 * factor * devices,
                        'formula': 'N0 elapsed / 32 * 188 * safety_factor; device-time additionally * devices_per_job'},
                  'planned_software': {'evaluation': 9, 'training': 0,
                        'process_seconds_estimate': per_software * 9 * factor,
                        'allocated_device_seconds_estimate': per_software * 9 * factor * devices,
                        'formula': ('software initial elapsed / 3' if actual_software else 'N0 elapsed / 32') + ' * 9 * safety_factor',
                        'basis': 'actual_initial_software_3' if actual_software else 'explicit_cross_source_planning_proxy_software_initial_not_complete'},
                  'raw_resource_logs': [j['launch'] + '.resources.jsonl' for j in self.state['jobs'].values()],
                  'limitations': 'Planning extrapolation, not a cost guarantee or GPU compute measurement. N0 includes training/startup/CPU/I/O; evaluation and software trajectories differ. Device-time is allocation count times observed process duration, not FLOPs. Parallel wall time cannot be obtained by summing jobs. No claim that N0 peaks bound N1 peaks. Raw per-device samples retain external process competition.',
                  'admission': 'N0 numerical/update gate only; neither business success nor the cost estimate selects or resamples episodes.'}
        write(path, record)
        self.state['resource_budget'] = {'path': str(path), 'sha256': sha(path)}
        self.persist()
        return True

    def _dependencies(self, job):
        if job['name'] in {'bridge', 'software-initial'}:
            return True
        if job['name'] in {'pilot-mc', 'pilot-rtg'}:
            parent = self.state['jobs']['bridge']
            if parent['status'] in TERMINAL and not parent.get('outcome', {}).get('n0_gate_passed'):
                job.update(status='blocked_dependency', reason='N0 did not complete the fixed numerical/two-update gate')
            if parent.get('outcome', {}).get('n0_gate_passed'):
                if not self._budget():
                    job.update(status='blocked_budget_record', reason='N0 elapsed/resource metadata unavailable; no budget record before N1')
                    return False
                initial_software = self.state['jobs']['software-initial']
                peer_name = 'pilot-rtg' if job['name'] == 'pilot-mc' else 'pilot-mc'
                peer = self.state['jobs'][peer_name]
                if initial_software['status'] in {'outcome_unknown', 'blocked_existing_artifacts'} or peer['status'] in TERMINAL - {'complete'}:
                    job.update(status='blocked_dependency', reason='Both N1 lanes must be available to establish the common initialization barrier')
                    return False
                if initial_software['status'] in ACTIVE:
                    return False
                return True
            return False
        parent = self.state['jobs']['pilot-' + job['name'].split('-')[1]]
        if parent['status'] in TERMINAL and parent['status'] != 'complete':
            job.update(status='blocked_dependency', reason='Corresponding N1 condition did not complete; no substitute final checkpoint')
        return parent['status'] == 'complete'

    def final_report(self):
        rows = []
        for job in self.state['jobs'].values():
            outcome = job.get('outcome') or (software_outcome(job, job.get('exit_code')) if job['kind'] == 'software'
                                          else online_outcome(job, job.get('exit_code')))
            rows.append({'name': job['name'], 'status': job['status'], 'kind': job['kind'], 'gpus': job['gpus'],
                         'run': job['run'], 'protocol': job['protocol'], 'outcome': outcome,
                         'launcher_process': job.get('launcher_process'), 'child_process': job.get('child_process'),
                         'launch_meta': job.get('launch_meta'), 'reason': job.get('reason')})
        report = {'version': VERSION + '-readonly', 'executor_status': self.state['status'], 'jobs': rows,
                  'planned_counts': {'N0_training': 32, 'N1_training': 128, 'N1_evaluation': 60, 'software_evaluation': 9,
                                     'total_episodes': 229},
                  'missing': [{'job': row['name'], 'not_started': row['outcome']['not_started_episodes'],
                               'open': row['outcome']['open_episodes']} for row in rows
                              if row['outcome']['not_started_episodes'] or row['outcome']['open_episodes']],
                  'resource_budget': read(self.output / 'resource-budget.json'),
                  'shared_initialization': {'directory': str(self.output / 'initialization'),
                      'records': [{'path': str(path), 'sha256': sha(path), 'data': read(path)}
                                  for path in sorted((self.output / 'initialization').glob('*.json'))]},
                  'scope': 'Reads frozen protocol, actual saved manifests/reports and launcher records only. Does not load models/tensors, invoke graders, execute SQL/code or change world/learner state. No missing reward is filled with zero.'}
        detailed_output = self.output / ('readonly-uci-' + str(time.time_ns()))
        detailed = {'path': str(detailed_output)}
        try:
            from scripts.learning_report_v015 import build_report, write_report
            measurements = build_report(self.output / 'uci-study.json',
                                        project_root=self.config['project'], source_root=self.config['source'])
            write_report(measurements, detailed_output)
            detailed.update(status='complete', report_json=str(detailed_output / 'report.json'),
                            report_markdown=str(detailed_output / 'report.md'))
        except Exception as error:
            detailed.update(status='readonly_error', error={'type': type(error).__name__, 'message': str(error)},
                            scope='Original stage counts and missing records retained; no model retry, grading or world execution.')
            detailed_output.mkdir(parents=True, exist_ok=True)
            write(detailed_output / 'readonly-error.json', detailed)
        report['uci_readonly'] = detailed
        write(self.output / 'study-report.json', report)
        return report

    def tick(self):
        for job in self.state['jobs'].values():
            if job['status'] in ACTIVE:
                self._observe(job)
            if job['status'] == 'finished':
                outcome = software_outcome(job, job['exit_code']) if job['kind'] == 'software' else online_outcome(job, job['exit_code'])
                job['outcome'] = outcome
                complete = outcome.get('n0_gate_passed') if job['name'] == 'bridge' else outcome['execution_complete']
                job['status'] = 'complete' if complete else 'incomplete'
        for job in self.state['jobs'].values():
            if job['status'] != 'not_started':
                continue
            ready = self._dependencies(job)
            busy = any(other['status'] in ACTIVE and set(other['gpus']) & set(job['gpus']) for other in self.state['jobs'].values())
            uncertain_lane = any(other['status'] in {'outcome_unknown', 'blocked_existing_artifacts'}
                                 and set(other['gpus']) & set(job['gpus']) for other in self.state['jobs'].values())
            if ready and uncertain_lane:
                job.update(status='blocked_dependency', reason='Prior lane occupancy is unresolved; do not start a replacement process on it')
            elif ready and not busy:
                self._launch(job)
        done = all(job['status'] in TERMINAL for job in self.state['jobs'].values())
        if done:
            self.state['status'] = 'complete' if all(job['status'] == 'complete' for job in self.state['jobs'].values()) else 'finished_with_missing_or_failed_jobs'
        if done:
            self.state['ended_at'] = self.now()
        self.persist()
        if done:
            self.final_report()
        return done


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args(argv)
    executor = PilotExecutor(read(args.config), args.output, resume=args.resume)
    try:
        while not executor.tick():
            time.sleep(executor.config['poll_seconds'])
    except (KeyboardInterrupt, SystemExit):
        executor.state.update(status='observer_detached', detached_at=time.time(),
                              detach_scope='No child was signalled; resume observes old attempts and may first-launch only untouched frozen successors.')
        executor.persist()
        executor.final_report()
        return 130
    except Exception as error:
        executor.state.update(status='observer_error', error={'type': type(error).__name__, 'message': str(error)},
                              detach_scope='No child was signalled or restarted.')
        executor.persist()
        executor.final_report()
        raise
    finally:
        executor.close()
    return 0 if executor.state['status'] == 'complete' else 1


if __name__ == '__main__':
    sys.exit(main())
