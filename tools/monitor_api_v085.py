"""Read-only API/Qwen monitoring: 30-second samples for 30 minutes by default."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import time
import types

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('v085_readonly_monitor_base', ROOT/'tools/monitor_rolling_api_v083.py')
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)


def ledger_snapshot():
    """Read aggregate counters only and close even when policy/SELECT fails."""
    db = None
    try:
        db = sqlite3.connect(base.LEDGER.as_uri()+'?mode=ro', uri=True, timeout=2)
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
            'api_keys_or_request_content_read': False, 'connection_explicitly_closed': True}
    except (OSError, ValueError, TypeError, sqlite3.Error) as exc:
        return base.error(exc)
    finally:
        if db is not None:
            db.close()


_base_sample = types.FunctionType(base.sample.__code__,
    {**base.sample.__globals__, 'ledger_snapshot': ledger_snapshot}, base.sample.__name__)


def process_fds(pid, *, proc_root=Path('/proc')):
    if type(pid) is not int or pid <= 0:
        return {'qualified': False, 'process_alive': False, 'error_type': 'NoLiveMainPID'}
    try:
        folder = proc_root/str(pid)
        before = (folder/'stat').read_text().rsplit(')', 1)[1].split()
        count = len(os.listdir(folder/'fd'))
        line = next(line for line in (folder/'limits').read_text().splitlines() if line.startswith('Max open files'))
        soft, hard = line.split()[3:5]
        soft = int(soft) if soft != 'unlimited' else None
        hard = int(hard) if hard != 'unlimited' else None
        after = (folder/'stat').read_text().rsplit(')', 1)[1].split()
        if before[19] != after[19]:
            raise ValueError('Observed PID was recycled during sample')
        return {'qualified': True, 'pid': pid, 'process_start_ticks': int(after[19]),
            'process_alive': after[0] not in {'Z', 'X'}, 'fd_used': count,
            'soft_limit': soft, 'hard_limit': hard,
            'fd_free': max(0, soft-count) if soft is not None else None,
            'low_free_threshold': 512, 'below_512': soft is not None and soft-count < 512,
            'limit_is_expected_16384': soft == hard == 16384}
    except FileNotFoundError:
        return {'qualified': False, 'pid': pid, 'process_alive': False, 'error_type': 'ProcessDisappeared'}
    except (OSError, ValueError, StopIteration, IndexError) as exc:
        return {'qualified': False, 'pid': pid, 'process_alive': None, **base.error(exc)}


def alerts(value):
    result = []
    if value['api_unit'].get('unit_and_process_running') is not True or value['fd'].get('process_alive') is not True:
        result.append('API_owner_stopped_or_liveness_unverified')
    if value['fd'].get('qualified') is not True:
        result.append('API_FD_observation_unverified')
    elif value['fd'].get('limit_is_expected_16384') is not True:
        result.append('API_actual_NOFILE_differs_from_16384')
    if value['fd'].get('below_512'):
        result.append('API_FD_free_below_512')
    progress = value['progress'].get('data', {})
    heartbeat = value['heartbeat'].get('data', {})
    if progress.get('phase') not in {'closed', 'stopped'}:
        if value['progress'].get('age_seconds', float('inf')) > 60:
            result.append('main_progress_stale_over_60_seconds')
        if heartbeat.get('scheduler_cycle_age_seconds', 0) > 60:
            result.append('scheduler_stale_over_60_seconds_despite_heartbeat')
    if progress.get('failure') is not None:
        result.append('API_reported_hard_failure')
    for name in ('owner', 'parent'):
        if value[name].get('memory_events', {}).get('oom_kill', 0):
            result.append(name+'_oom_kill_counter_nonzero')
    ledger = value['ledger']
    if ledger.get('halted') or ledger.get('remaining_CNY', 0) < 0:
        result.append('API_money_ledger_hard_halt_or_over_cap')
    if ledger.get('cap_is_1500') is not True:
        result.append('API_money_1500_cap_unverified')
    return result


def sample(args, previous):
    value = _base_sample(args, previous)
    value['fd'] = process_fds(value['api_unit'].get('MainPID'))
    value['qwen_unit'] = base.unit_snapshot(args.qwen_unit)
    value['alerts'] = alerts(value)
    return value


def summary(samples):
    report = base.summary(samples)
    values = [item['fd']['fd_used'] for item in samples if item['fd'].get('qualified')]
    report.update(version='v085-read-only-FD-monitor-r1',
        fd_used_min=min(values) if values else None, fd_used_max=max(values) if values else None,
        alert_counts=dict(Counter(item for value in samples for item in value['alerts'])),
        monitor_sqlite_connections_explicitly_closed=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-root', type=Path,
        default=ROOT/'runs/software-benchmark-v085/api-fd-recovery-r1/api-coordinator')
    parser.add_argument('--qwen-root', type=Path,
        default=ROOT/'runs/software-benchmark-v084/qwen-binding-recovery-r1/primary-coordinator')
    parser.add_argument('--unit', default='proworksim-v085-api.service')
    parser.add_argument('--qwen-unit', default='proworksim-v084-primary.service')
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/software-benchmark-v085/live-monitor-r1')
    parser.add_argument('--interval', type=float, default=30)
    parser.add_argument('--duration', type=float, default=1800)
    args = parser.parse_args()
    if not 1 <= args.interval <= 60 or not 0 <= args.duration <= 3600:
        parser.error('Interval 1..60 seconds and duration 0..3600 seconds are required')
    args.output.mkdir(parents=True, exist_ok=True)
    start, samples, next_print = time.monotonic(), [], 0.0
    with (args.output/'samples.jsonl').open('x') as stream:
        while True:
            value = sample(args, samples[-1] if samples else None)
            samples.append(value)
            stream.write(json.dumps(value, ensure_ascii=False)+'\n')
            stream.flush()
            base.write_summary(args.output/'summary.json', summary(samples))
            elapsed = time.monotonic()-start
            brief = {'elapsed_seconds': round(elapsed), 'samples': len(samples),
                'alive': value['api_unit'].get('unit_and_process_running'),
                'API_actor_claims': value['claims']['counts'].get('API_actor', 0),
                'API_inflight': value['ledger'].get('inflight_count'),
                'finished_generation': value['progress'].get('data', {}).get('finished_generation'),
                'fd_used': value['fd'].get('fd_used'), 'fd_free': value['fd'].get('fd_free'),
                'fd_soft': value['fd'].get('soft_limit'), 'fd_hard': value['fd'].get('hard_limit'),
                'qwen_alive': value['qwen_unit'].get('unit_and_process_running')}
            if value['alerts']:
                print('ALERT '+json.dumps({**brief, 'alerts': value['alerts']}, ensure_ascii=False), flush=True)
            if elapsed >= next_print or elapsed >= args.duration:
                print(json.dumps({**brief, 'anomalies': value['anomalies']}, ensure_ascii=False), flush=True)
                next_print += 60
            if elapsed >= args.duration:
                break
            next_sample = start+len(samples)*args.interval
            time.sleep(max(0, min(next_sample, start+args.duration)-time.monotonic()))


if __name__ == '__main__':
    main()
