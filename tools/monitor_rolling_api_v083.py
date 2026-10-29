"""Read-only 30-second observations of the v083 API continuation; no control calls."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
GIB = 1024**3
API_ROOT = ROOT/'runs/software-benchmark-v083/rolling-api-async-r1/api-coordinator'
CLAIMS = ROOT/'runs/software-benchmark-v066/v064-continuation-r3/resource-claims'
LEDGER = ROOT/'runs/software-benchmark-v064/full-verified-r1/api-budget/ledger.sqlite3'
PROGRESS_KEYS = ('phase', 'finished_generation', 'finished_code_scores', 'combined_code_score_records',
    'active_generation', 'actual_generation_futures', 'pending_generation', 'active_grading', 'pending_scores',
    'own_API_actor_count', 'old_API_actor_count', 'effective_generation_limit', 'configured_generation_limit',
    'API_inflight_requests', 'ramp_ceiling', 'async_grading_stages', 'groups', 'external_running',
    'predecessor_history_final', 'failure', 'isolated_exception_count')


def error(exc):
    # Exception messages may embed arbitrary database values; only type is saved.
    return {'error_type': type(exc).__name__}


def json_snapshot(path, keys=None):
    try:
        raw = json.loads(path.read_bytes())
        age = max(0, time.time()-float(raw.get('unix', path.stat().st_mtime)))
        return {'age_seconds': age, 'data': {key: raw[key] for key in keys if key in raw} if keys else raw}
    except (OSError, ValueError, TypeError) as exc:
        return error(exc)


def unit_snapshot(name):
    env = dict(os.environ, XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',
               DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    try:
        response = subprocess.run(['systemctl', '--user', 'show', name, '--no-pager',
            '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup,Result'],
            env=env, capture_output=True, text=True, timeout=4, check=True)
        props = dict(line.split('=', 1) for line in response.stdout.splitlines() if '=' in line)
        pid = int(props.get('MainPID', '0'))
        alive = False
        if pid > 0:
            stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
            alive = stat[0] not in {'Z', 'X'}
        return {**props, 'MainPID': pid, 'process_alive': alive,
                'unit_and_process_running': props.get('ActiveState') == 'active' and alive}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {**error(exc), 'process_alive': None, 'unit_and_process_running': None}


def cgroup_snapshot(path):
    try:
        numbers = {key: int(value) for key, value in
                   (line.split() for line in (path/'memory.stat').read_text().splitlines())}
        current = int((path/'memory.current').read_text())
        maximum = (path/'memory.max').read_text().strip()
        reclaimable = max(0, min(numbers['inactive_file'], numbers['file'])
                          - numbers['file_dirty']-numbers['file_writeback'])
        events = {key: int(value) for key, value in
                  (line.split() for line in (path/'memory.events').read_text().splitlines())}
        cpu = {key: int(value) for key, value in
               (line.split() for line in (path/'cpu.stat').read_text().splitlines())}
        return {'path': str(path), 'raw_current_bytes': current,
                'max_bytes': int(maximum) if maximum != 'max' else None,
                'file_bytes': numbers['file'], 'inactive_file_bytes': numbers['inactive_file'],
                'anon_bytes': numbers['anon'], 'file_dirty_bytes': numbers['file_dirty'],
                'file_writeback_bytes': numbers['file_writeback'],
                'conservative_reclaimable_file_bytes': min(current, reclaimable),
                'working_set_bytes': max(0, current-reclaimable), 'memory_events': events, 'cpu_stat': cpu}
    except (OSError, KeyError, ValueError) as exc:
        return error(exc)


def active_claims():
    counts, issues = Counter(), 0
    ready = Counter()
    for path in CLAIMS.glob('active-*.json'):
        try:
            value = json.loads(path.read_bytes())
            spec = value.get('spec', {})
            model = 'API' if ':DEEPSEEK_' in spec.get('slot_id', '') else 'QWEN' if ':QWEN_' in spec.get('slot_id', '') else 'other'
            role = spec.get('role', 'unknown')
            counts[f'{model}_{role}'] += 1
            if role == 'actor' and str(value.get('key', '')).startswith('actor-'):
                index = value['key'][len('actor-'):]
                if index.isdigit():
                    marker = CLAIMS.parent/'episodes'/index/'controller-ready.json'
                    observed = json_snapshot(marker)
                    if observed.get('data', {}).get('trusted_SDK_imports_complete') is True:
                        ready[model] += 1
        except (OSError, ValueError, TypeError):
            issues += 1
    return {'counts': dict(counts), 'materialized_actor_claims': dict(ready),
            'observation_errors': issues,
            'meaning': 'Actual active resource reservations; materialized marker is not per-process liveness'}


def ledger_snapshot():
    """SQLite mode=ro, query_only, bounded SELECTs; never initialize a ledger."""
    try:
        with sqlite3.connect(LEDGER.as_uri()+'?mode=ro', uri=True, timeout=2) as db:
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            policy = json.loads(db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0])
            committed, settled, uncertain, inflight, attempts = db.execute('''SELECT
                COALESCE(SUM(COALESCE(settled_nanoyuan,reserved_nanoyuan)),0),
                COALESCE(SUM(CASE WHEN status='settled' THEN settled_nanoyuan ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='uncertain' THEN reserved_nanoyuan ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='reserved' THEN 1 ELSE 0 END),0), COUNT(*) FROM requests''').fetchone()
            halted = db.execute("SELECT 1 FROM metadata WHERE name='halted'").fetchone() is not None
        cap = policy.get('cap_nanoyuan')
        return {'cap_CNY': cap/1e9 if isinstance(cap, int) else None,
            'cap_is_1500': cap == 1_500_000_000_000, 'committed_upper_CNY': committed/1e9,
            'settled_upper_CNY': settled/1e9, 'uncertain_reserved_CNY': uncertain/1e9,
            'remaining_CNY': (cap-committed)/1e9 if isinstance(cap, int) else None,
            'inflight_count': inflight, 'attempts': attempts, 'halted': halted,
            'api_keys_or_request_content_read': False}
    except (OSError, ValueError, TypeError, sqlite3.Error) as exc:
        return error(exc)


def host_snapshot(previous=None):
    try:
        memory = {key.rstrip(':'): int(value)*1024 for key, value, *_ in
                  (line.split() for line in Path('/proc/meminfo').read_text().splitlines())}
        cpu = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
        total, idle = sum(cpu), cpu[3]+cpu[4]
        old = (previous or {}).get('host', {})
        old_total, old_idle = old.get('cpu_total_jiffies'), old.get('cpu_idle_jiffies')
        idle_fraction = ((idle-old_idle)/(total-old_total)
                         if old_total is not None and total > old_total else None)
        return {'memory_available_bytes': memory['MemAvailable'], 'memory_total_bytes': memory['MemTotal'],
            'cpu_count': os.cpu_count(), 'cpu_total_jiffies': total, 'cpu_idle_jiffies': idle,
            'cpu_idle_fraction_interval': idle_fraction, 'load_average': list(os.getloadavg())}
    except (OSError, ValueError, KeyError) as exc:
        return error(exc)


def anomalies(sample):
    output = []
    unit, progress, heartbeat = sample['api_unit'], sample['progress'], sample['heartbeat']
    phase = progress.get('data', {}).get('phase')
    if unit.get('unit_and_process_running') is False and phase not in {'closed', 'stopped'}:
        output.append('API_process_not_running_progress_is_not_liveness_proof')
    if unit.get('unit_and_process_running') is None:
        output.append('API_unit_liveness_unknown')
    if phase not in {'closed', 'stopped'}:
        if progress.get('age_seconds', float('inf')) > 5:
            output.append('main_progress_older_than_5_seconds')
        age = heartbeat.get('data', {}).get('scheduler_cycle_age_seconds')
        if isinstance(age, (int, float)) and age > 5:
            output.append('heartbeat_fresh_but_scheduler_stalled' if heartbeat.get('age_seconds', 999) <= 5
                          else 'heartbeat_and_scheduler_stale')
        if heartbeat.get('age_seconds', float('inf')) > 5:
            output.append('heartbeat_unavailable_or_stale')
    ledger = sample['ledger']
    if ledger.get('cap_is_1500') is not True:
        output.append('API_ledger_cap_unverified_or_changed')
    if ledger.get('halted'):
        output.append('API_ledger_halted')
    if ledger.get('remaining_CNY', 0) < 0:
        output.append('API_ledger_commitment_exceeds_cap')
    if sample['claims']['observation_errors']:
        output.append('active_claim_snapshot_partially_unknown')
    for name in ('owner', 'parent'):
        value = sample[name]
        if value.get('memory_events', {}).get('oom_kill', 0):
            output.append(name+'_oom_kill_counter_nonzero')
        if value.get('error_type'):
            output.append(name+'_memory_observation_unavailable')
    return output


def sample(args, previous):
    unit = unit_snapshot(args.unit)
    cg = unit.get('ControlGroup')
    snapshot = {'unix': time.time(), 'utc': datetime.now(timezone.utc).isoformat(),
        'api_unit': unit, 'progress': json_snapshot(args.api_root/'progress.json', PROGRESS_KEYS),
        'heartbeat': json_snapshot(args.api_root/'heartbeat.json',
            ('heartbeat_only', 'scheduler_cycle_age_seconds', 'scheduler_stale', 'heartbeat_unix', 'phase')),
        'pressure': json_snapshot(args.api_root/'pressure.json',
            ('fresh', 'admit', 'reason', 'owner_pressure', 'available_bytes', 'parent_pressure')),
        'qwen_progress': json_snapshot(args.qwen_root/'progress.json', PROGRESS_KEYS),
        'claims': active_claims(), 'ledger': ledger_snapshot(), 'host': host_snapshot(previous),
        'owner': cgroup_snapshot(Path('/sys/fs/cgroup')/cg.lstrip('/')) if cg else {'error_type': 'MissingControlGroup'},
        'parent': cgroup_snapshot(Path('/sys/fs/cgroup/proworksimv076api.slice'))}
    snapshot['anomalies'] = anomalies(snapshot)
    return snapshot


def summary(samples):
    first, last = samples[0], samples[-1]
    elapsed = last['unix']-first['unix']
    def numbers(key):
        return [item['progress'].get('data', {}).get(key) for item in samples
                if isinstance(item['progress'].get('data', {}).get(key), (int, float))]
    def rate(key):
        values = numbers(key)
        return ((values[-1]-values[0])*3600/elapsed if len(values) > 1 and elapsed > 0 else None)
    actors = [item['claims']['counts'].get('API_actor', 0) for item in samples]
    return {'samples': len(samples), 'observed_seconds': elapsed, 'start_utc': first['utc'], 'end_utc': last['utc'],
        'generation_completions_per_hour': rate('finished_generation'),
        'code_score_records_per_hour': rate('combined_code_score_records'),
        'API_actor_claims_min': min(actors), 'API_actor_claims_max': max(actors),
        'API_actor_claims_mean': statistics.mean(actors),
        'API_inflight_max': max(item['ledger'].get('inflight_count', 0) for item in samples),
        'anomaly_counts': dict(Counter(issue for item in samples for issue in item['anomalies'])),
        'last': last, 'read_only': True, 'service_control_or_Docker_or_model_calls': 0,
        'claim_count_is_not_container_process_liveness': True}


def write_summary(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-root', type=Path, default=API_ROOT)
    parser.add_argument('--qwen-root', type=Path,
        default=ROOT/'runs/software-benchmark-v080/qwen-json-recovery-r1/primary-coordinator')
    parser.add_argument('--unit', default='proworksim-v083-api.service')
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/software-benchmark-v083/live-monitor-r1')
    parser.add_argument('--interval', type=float, default=30)
    parser.add_argument('--duration', type=float, default=600)
    args = parser.parse_args()
    if not 1 <= args.interval <= 60 or not 0 <= args.duration <= 3600:
        parser.error('Interval must be 1..60 seconds; duration 0..3600 seconds')
    args.output.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    samples, next_print = [], 0.0
    with (args.output/'samples.jsonl').open('x') as stream:
        while True:
            value = sample(args, samples[-1] if samples else None)
            samples.append(value)
            stream.write(json.dumps(value, ensure_ascii=False)+'\n')
            stream.flush()
            report = summary(samples)
            write_summary(args.output/'summary.json', report)
            elapsed = time.monotonic()-start
            if elapsed >= next_print or elapsed >= args.duration:
                print(json.dumps({'elapsed_seconds': round(elapsed), 'samples': len(samples),
                    'alive': value['api_unit'].get('unit_and_process_running'),
                    'API_actor_claims': value['claims']['counts'].get('API_actor', 0),
                    'API_inflight': value['ledger'].get('inflight_count'),
                    'finished_generation': value['progress'].get('data', {}).get('finished_generation'),
                    'owner_working_set_GiB': round(value['owner'].get('working_set_bytes', 0)/GIB, 2),
                    'anomalies': value['anomalies']}, ensure_ascii=False), flush=True)
                next_print += 60
            if elapsed >= args.duration:
                break
            next_sample = start + len(samples)*args.interval
            time.sleep(max(0, min(next_sample, start+args.duration)-time.monotonic()))


if __name__ == '__main__':
    main()
