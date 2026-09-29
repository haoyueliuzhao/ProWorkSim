"""Bounded per-device telemetry for a new v25 recovery supervisor.

Queries are read-only; this module never signals workers or changes an existing
run. Resource/task/wall/RSS/artifact limits remain the supervisor's responsibility.
"""
import copy
import csv
import io
import math
from pathlib import Path
import subprocess
import time

VERSION = 'target-device-telemetry-v0.25-recovery'
GPU_QUERY = '--query-gpu=index,uuid,name,memory.free,memory.total,utilization.gpu'
PROCESS_QUERY = '--query-compute-apps=gpu_uuid,pid,used_gpu_memory,process_name'


def _text(value):
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return value or ''


def worker_identity(worker_pid):
    """OS process existence/start identity, distinct from a CUDA context row."""
    result = {'pid': worker_pid, 'available': False, 'alive': None, 'start_ticks': None}
    try:
        stat = Path(f'/proc/{worker_pid}/stat').read_text()
        fields = stat[stat.rfind(')') + 2:].split()
        result.update(available=True, alive=fields[0] not in {'Z', 'X'},
                      state=fields[0], start_ticks=int(fields[19]))
    except (FileNotFoundError, ProcessLookupError) as error:
        result.update(alive=False, error={'type': type(error).__name__, 'message': str(error)})
    except (OSError, ValueError, IndexError) as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
    return result


def _query(query, selector, timeout_seconds, *, runner, clock):
    command = ['nvidia-smi', '--id=' + str(selector), query, '--format=csv,noheader,nounits']
    started = clock()
    result = {'command': command, 'started_at': started, 'timeout_seconds': timeout_seconds}
    try:
        completed = runner(command, text=True, capture_output=True, timeout=timeout_seconds, check=False)
        result.update(returncode=completed.returncode, stdout=_text(completed.stdout), stderr=_text(completed.stderr))
    except subprocess.TimeoutExpired as error:
        result.update(returncode=None, stdout=_text(error.stdout), stderr=_text(error.stderr),
                      error={'type': type(error).__name__, 'message': str(error),
                             'timeout_seconds': error.timeout,
                             'stdout': _text(error.stdout), 'stderr': _text(error.stderr)})
    except OSError as error:
        result.update(returncode=None, stdout='', stderr=str(error),
                      error={'type': type(error).__name__, 'message': str(error)})
    result['ended_at'] = clock()
    result['elapsed_seconds'] = max(0.0, result['ended_at'] - started)
    return result


def target_resources(gpu_index_or_uuid, *, worker_pid, gpu_timeout_seconds=5,
                     process_timeout_seconds=5, runner=subprocess.run, clock=time.time):
    """Each query is capped at 5 or 10 seconds and targets only the bound card.

    `time` is recorded BEFORE both queries, so a failed query consumes the grace
    interval. Preserve old gpus/processes returncode/stdout/stderr report keys.
    """
    if gpu_timeout_seconds not in (5, 10) or process_timeout_seconds not in (5, 10):
        raise ValueError('Only declared 5/10-second telemetry query deadlines are supported')
    sample = {'time': clock(), 'version': VERSION,
              'scope': {'kind': 'target_gpu', 'gpu_selector': str(gpu_index_or_uuid)}}
    sample['gpus'] = _query(GPU_QUERY, gpu_index_or_uuid, gpu_timeout_seconds, runner=runner, clock=clock)
    sample['processes'] = _query(PROCESS_QUERY, gpu_index_or_uuid, process_timeout_seconds, runner=runner, clock=clock)
    sample['worker_identity'] = worker_identity(worker_pid)
    sample['finished_at'] = clock()
    return sample


def _number(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError('Resource value must be finite and nonnegative')
    return number


def _rows(sample, key, errors):
    result = sample.get(key)
    if not isinstance(result, dict) or result.get('returncode') != 0:
        errors.append({'kind': 'query_failed', 'query': key, 'result': copy.deepcopy(result)})
        return None
    if not isinstance(result.get('stdout'), str):
        errors.append({'kind': 'invalid_query_output', 'query': key})
        return None
    try:
        return [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(result['stdout']), strict=True) if row]
    except csv.Error as error:
        errors.append({'kind': 'invalid_csv', 'query': key, 'message': str(error)})
        return None


class TelemetryGuard:
    """Deterministic observation state machine; no process signals or OS reads.

    Admission must independently obtain a complete all-device snapshot. Bind the
    selected UUID/index and actual worker start ticks before the first observe.
    Only a complete fresh target GPU+process sample resets the failure timer.
    """
    def __init__(self, target_gpu_index, target_gpu_uuid, expected_worker_start_ticks,
                 *, grace_seconds=120, worker_pid=None):
        if (type(target_gpu_index) is not int or target_gpu_index < 0
                or not isinstance(target_gpu_uuid, str) or not target_gpu_uuid
                or type(expected_worker_start_ticks) is not int or expected_worker_start_ticks < 0
                or grace_seconds != 120):
            raise ValueError('Bind a physical GPU and worker identity with exactly120s grace')
        self.target_gpu_index = target_gpu_index
        self.target_gpu_uuid = target_gpu_uuid
        self.expected_worker_start_ticks = expected_worker_start_ticks
        self.worker_pid = worker_pid
        self.grace_seconds = grace_seconds
        self.failure_since = None
        self.consecutive_failures = 0
        self.failures_total = 0
        self.last_success = None
        self.last_observed_at = None
        self.last_sample_time = None

    def observe(self, sample, now, worker_pid, gpu_index=None, *, own_memory_limit_mib=None):
        if not isinstance(sample, dict) or not math.isfinite(now):
            raise ValueError('A timestamped telemetry sample and finite current time are required')
        errors, identity_reason = [], None
        if self.worker_pid is None:
            self.worker_pid = worker_pid
        if self.worker_pid != worker_pid:
            identity_reason = 'worker_identity_changed'
        worker = sample.get('worker_identity', {})
        if not isinstance(worker, dict):
            worker = {}
        if worker.get('alive') is False:
            identity_reason = identity_reason or 'worker_lost'
        elif not worker.get('available') or worker.get('alive') is not True:
            identity_reason = identity_reason or 'worker_identity_unavailable'
        elif worker.get('pid') != worker_pid or worker.get('start_ticks') != self.expected_worker_start_ticks:
            identity_reason = identity_reason or 'worker_identity_changed'
        if identity_reason:
            errors.append({'kind': identity_reason, 'observed_identity': copy.deepcopy(worker)})
        if gpu_index is not None and gpu_index != self.target_gpu_index:
            identity_reason = identity_reason or 'gpu_identity_changed'
            errors.append({'kind': 'gpu_index_argument_mismatch', 'observed_gpu_index': gpu_index})
        scope = sample.get('scope', {})
        if not isinstance(scope, dict):
            scope = {}
        if scope.get('kind') != 'target_gpu' or scope.get('gpu_selector') not in {str(self.target_gpu_index), self.target_gpu_uuid}:
            identity_reason = identity_reason or 'gpu_identity_changed'
            errors.append({'kind': 'query_scope_mismatch', 'scope': copy.deepcopy(scope)})
        sampled_at = sample.get('time')
        timestamp_valid = (type(sampled_at) in (int, float) and math.isfinite(sampled_at)
                           and sampled_at <= now
                           and (self.last_sample_time is None or sampled_at > self.last_sample_time)
                           and (self.last_observed_at is None or now >= self.last_observed_at))
        if not timestamp_valid:
            errors.append({'kind': 'nonfresh_or_invalid_sample_time', 'sample_time': sampled_at, 'now': now})
        timely = timestamp_valid and now - sampled_at < self.grace_seconds
        if timestamp_valid and not timely:
            errors.append({'kind': 'stale_sample_age', 'sample_age_seconds': now - sampled_at})
        gpu_rows = _rows(sample, 'gpus', errors)
        gpu_complete = False
        if gpu_rows is not None:
            try:
                if len(gpu_rows) != 1 or len(gpu_rows[0]) != 6:
                    raise ValueError('Target query must return exactly one complete GPU row')
                index, uuid, name, free, total, utilization = gpu_rows[0]
                if int(index) != self.target_gpu_index or uuid != self.target_gpu_uuid:
                    identity_reason = identity_reason or 'gpu_identity_changed'
                    raise ValueError('Target index/UUID differs from the admission binding')
                if not name or _number(free) > _number(total) or _number(utilization) > 100:
                    raise ValueError('Invalid GPU resource values')
                gpu_complete = True
            except (ValueError, TypeError) as error:
                errors.append({'kind': 'invalid_gpu_rows', 'message': str(error)})
        process_rows = _rows(sample, 'processes', errors)
        processes_complete, own_memory, own_lower_bound = False, None, None
        if process_rows is not None:
            # A valid own-PID row already above the ceiling remains a lower-
            # bound breach even when an unrelated process row is malformed.
            # Do not sum duplicated own rows or turn a partial list into zero.
            observed_own = []
            for row in process_rows:
                try:
                    if len(row) == 4 and row[0] == self.target_gpu_uuid and int(row[1]) == worker_pid and row[3]:
                        observed_own.append(_number(row[2]))
                except (ValueError, TypeError):
                    pass
            if len(observed_own) == 1 and timely and identity_reason is None:
                own_lower_bound = observed_own[0]
            try:
                measured, seen_pids = 0.0, set()
                for row in process_rows:
                    if len(row) != 4:
                        raise ValueError('Incomplete compute process row')
                    uuid, pid, memory, name = row
                    if uuid != self.target_gpu_uuid:
                        identity_reason = identity_reason or 'gpu_identity_changed'
                        raise ValueError('Compute process row escapes the bound physical GPU')
                    pid = int(pid)
                    if pid <= 0 or pid in seen_pids or not name:
                        raise ValueError('Invalid or duplicate compute PID row')
                    seen_pids.add(pid)
                    memory = _number(memory)
                    if pid == worker_pid:
                        measured += memory
                processes_complete = True
                if timely and identity_reason is None:
                    own_memory = measured
            except (ValueError, TypeError) as error:
                errors.append({'kind': 'incomplete_process_measurement', 'message': str(error)})
        if identity_reason is not None:
            own_lower_bound = None
        elif own_memory is not None:
            own_lower_bound = own_memory
        fresh = bool(gpu_complete and processes_complete and timely and identity_reason is None)
        recovered_after = None
        if fresh:
            if self.failure_since is not None:
                recovered_after = max(0.0, now - self.failure_since)
            self.failure_since, self.consecutive_failures = None, 0
            self.last_success = {'sample_time': sampled_at, 'observed_at': now,
                                 'own_gpu_memory_mib': own_memory, 'worker_pid': worker_pid,
                                 'gpu_index': self.target_gpu_index, 'gpu_uuid': self.target_gpu_uuid}
        else:
            self.failures_total += 1
            self.consecutive_failures += 1
            if self.failure_since is None:
                # The first failing query's start counts; not its return time.
                self.failure_since = sampled_at if timestamp_valid else now
        failure_seconds = max(0.0, now - self.failure_since) if self.failure_since is not None else 0.0
        reason = identity_reason
        if own_memory_limit_mib is not None:
            limit = _number(own_memory_limit_mib)
            if own_lower_bound is not None and own_lower_bound >= limit:
                reason = reason or 'own_gpu_memory_limit'
        if not fresh and failure_seconds >= self.grace_seconds:
            reason = reason or 'telemetry_unavailable_budget'
        self.last_observed_at = now
        if timestamp_valid:
            self.last_sample_time = sampled_at
        return {'sample': copy.deepcopy(sample), 'version': VERSION,
                'target_gpu_index': self.target_gpu_index, 'target_gpu_uuid': self.target_gpu_uuid,
                'worker_pid': worker_pid, 'expected_worker_start_ticks': self.expected_worker_start_ticks,
                'fresh': fresh, 'stale': not fresh and self.last_success is not None,
                'own_gpu_memory_mib': own_memory, 'own_memory_mib': own_memory,
                'own_memory_fresh': own_memory is not None,
                'own_memory_observed_lower_bound_mib': own_lower_bound,
                'own_memory_lower_bound_fresh': own_lower_bound is not None,
                'gpu_query_complete': gpu_complete, 'process_query_complete': processes_complete,
                'last_success_reference_only': not fresh,
                'last_success': copy.deepcopy(self.last_success),
                'consecutive_failures': self.consecutive_failures, 'failures_total': self.failures_total,
                'failure_since': self.failure_since, 'failure_seconds': failure_seconds,
                'grace_seconds': self.grace_seconds, 'recovered_after_seconds': recovered_after,
                'errors': errors, 'stop_reason': reason}
