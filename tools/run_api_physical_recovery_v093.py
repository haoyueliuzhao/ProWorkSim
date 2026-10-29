"""Run only the sealed 44 fresh administrative recovery attempts."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import importlib.util
import json
import threading
import time
from types import SimpleNamespace

from proworksim import software_benchmark_api_scope_v093 as scope
from proworksim.software_benchmark_recovery_runtime_v093 import bindings
from proworksim.software_benchmark_recovery_runtime_v093 import grading as grading_adapter
from proworksim import software_benchmark_deepseek_budget_v089 as amended
from proworksim.software_benchmark_recovery_runtime_v093 import build_api_runtime, pressure_module
from proworksim.software_benchmark_startup_gate_v093 import StartupHealthGate
from proworksim.software_benchmark_fd_v085 import FDGuard
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_deepseek_runtime_v069 import private_function
from proworksim.storage import atomic_write, json_bytes

VERSION = 'v093-unentered-pressure-recovery-asynchronous-runner-r1'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, scope.ROOT/'tools'/filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


helpers = module('v093_adaptive_helpers', 'run_adaptive_v076.py')
prior = module('v093_admission_helpers', 'run_api_recovery_v088.py')


class Admission(prior.Admission):
    unrestricted_limit = private_function(prior.Admission.limit, scope=scope)

    def limit(self):
        resource_ceiling = self.unrestricted_limit()
        gated = self.health.limit(resource_ceiling, self.active)
        self.observation.update(resource_generation_ceiling=resource_ceiling,
            effective_generation_limit=gated, startup_health_gate=self.health.state())
        return gated

    def record(self, kind, **values):
        super().record(kind, **values)
        self.health.record(kind, **values)


class Recorder(helpers.base.UsageRecorder):
    def save_record(self, row, record):
        record = {**record, 'original_slot_id': row['original_slot_id'],
            'recovery_attempt': row['recovery_attempt'], 'counts_as_original_first_run': False}
        path = scope.API_ROOT/'usage-records'/f"{row['slot_index']}.json"
        atomic_write(path, json_bytes(record))
        self.remember_record(row, record, reference(path))

    def flush(self, *, final=False):
        if not final and time.monotonic()-self.last_write < 60:
            return
        groups = {}
        for group_id, total in Counter(row['group_id'] for row in self.matrix['rows']).items():
            records = [v for v in self.records.values() if v['group_id'] == group_id]
            complete = [v for v in records if v['generation_state'] in ('closed', 'technical_unknown')
                        and v['usage_capture_complete'] and not v['uncertain_reserved_tokens']]
            total_known = sum(v['prompt_tokens_known']+v['completion_tokens_known'] for v in records)
            final_tokens = sum(v['prompt_tokens_known']+v['completion_tokens_known'] for v in complete)
            groups[group_id] = {'planned_recovery_attempts': total,
                'entered': sum(v['entered'] for v in records), 'usage_final_attempts': len(complete),
                'known_actual_tokens_lower_bound': total_known,
                'actual_mean_complete_usage_subset': final_tokens/len(complete) if complete else None,
                'actual_mean_full_recovery_group': final_tokens/total if len(complete) == total else None,
                'original_first_run_rate_changed': False}
        atomic_write(scope.API_ROOT/'actual-usage-summary.json', json_bytes({'version': VERSION,
            'unix': time.time(), 'final': final, 'groups': groups, 'recovery_attempts': 44,
            'original_panel_denominator': 1000, 'mix_with_original_first_attempts': False,
            'original_costs_not_readded_to_recovery_token_sum': True,
            'global_cash_includes_all_original_and_recovery_costs': self.api_runtime.budget_status()}))
        if final:
            write_new(scope.API_ROOT/'actual-usage-records.json', {
                'version': VERSION, 'record_files': {k: v['record'] for k, v in self.records.items()},
                'original_costs_counted_once_in_shared_cash_ledger': True})
        self.last_write = time.monotonic()


def run():
    from proworksim.software_benchmark_async_queue_v082 import factory as queue_factory
    scope.require_allowed()
    actual = scope.verify_host_limits()
    amendment = amended.require_amendment()
    parent = scope.parent_module()
    inventory_ref = reference(scope.INVENTORY_FILE)
    inventory = scope.load(inventory_ref)
    rows = inventory['rows']
    if len(rows) != 44:
        raise ValueError('Only the full 44 administrative-recovery attempts may run')
    if (scope.API_ROOT/'execution-started.json').exists():
        raise ValueError('No automatic coordinator replay')
    stop, registry = threading.Event(), None

    def snapshot(name, value):
        atomic_write(scope.API_ROOT/name, json_bytes({'version': VERSION, 'unix': time.time(), **value}))

    def event(kind, **values):
        with (scope.API_ROOT/'events.jsonl').open('a') as stream:
            stream.write(json.dumps({'unix': time.time(), 'kind': kind, **values}, ensure_ascii=False)+'\n')

    registry = helpers.EpisodeRegistry(event)
    fd_guard = FDGuard()
    pressure = pressure_module()
    probe = pressure.owner_probe
    with ExitStack() as cleanup:
        watchdog = pressure.PressureWatchdog(registry.snapshot, registry.abort,
            observe=lambda value: snapshot('pressure.json', value), require_parent=True,
            parent_probe=parent.pressure_probe, coordinator_probe=probe)
        cleanup.callback(watchdog.close)
        watchdog.start()
        policy = bindings.policy(scope.require_allowed, watchdog_guard=watchdog.admission,
            authorization_ref=reference(scope.AUTH_FILE), qwen_target=private_function(prior.qwen_target, scope=scope))
        episode_impl = bindings.episode(policy)
        grading_watchdog = pressure.PressureWatchdog(lambda: [], lambda *_: None,
            observe=lambda value: snapshot('grading-pressure.json', value),
            require_parent=False, coordinator_probe=probe)
        cleanup.callback(grading_watchdog.close)
        grading_watchdog.start()
        grading = grading_adapter.factory(watchdog_guard=grading_watchdog.admission)
        lease = scope.reserve_api_coordinator()
        cleanup.callback(scope.release_api_coordinator, lease)
        api = build_api_runtime(rows=rows, fd_guard=fd_guard,
            identity_file=scope.API_ROOT/'api-runtime/identity.json')
        api.initialize_for_run()
        health = StartupHealthGate(rows, stop_event=stop, event=event,
            snapshot=lambda value: snapshot('startup-health-gate.json', value))
        rows = health.ordered_rows(rows)
        matrix = {'rows': rows, 'groups': {row['group_id']: {} for row in rows}}
        recorder = Recorder(matrix, api)
        history = SimpleNamespace(old_owned=set(), new_allowed={row['slot_id'] for row in rows},
                                  rows={row['slot_id']: row for row in rows}, snapshot=lambda: {})
        admission = Admission(policy, watchdog, history, event)
        admission.health = health
        state = helpers.state_for(rows, inventory, inventory_ref)

        def episode(row, resident, **kwargs):
            if row['slot_id'] not in history.new_allowed:
                raise PermissionError('A first attempt or historical unknown is outside this recovery phase')
            health.require_launch(row['slot_id'])
            local = registry.add(row)
            kwargs['stop_event'] = helpers.LocalStop(kwargs['stop_event'], local)
            try:
                value = episode_impl.run_episode(row, resident, **kwargs)
            finally:
                registration = registry.remove(row['slot_id'])
            return helpers.pressure_result(value, registration, scope.API_ROOT, row)

        def progress(value):
            snapshot('progress.json', {**value, **admission.observation,
                'startup_health_gate': health.state(),
                'API_inflight_requests': api.budget_status().get('inflight_count'),
                'fd_pressure': fd_guard.snapshot(), 'recovery_attempts_planned': 44,
                'original_panel_denominator': 1000, 'mix_with_original_first_attempts': False})

        write_new(scope.API_ROOT/'execution-started.json', {'version': VERSION, 'unix': time.time(),
            'authorization': reference(scope.AUTH_FILE), 'inventory': inventory_ref,
            'host_limits': actual, 'budget_amendment': amendment, 'fresh_recovery_attempts': 44,
            'exact_checkpoint_resume': False, 'original_first_attempts_overwritten': False,
            'Qwen_lifecycle_operations': 0})
        handlers = helpers.base._handle_termination(stop)
        cleanup.callback(helpers.base._restore_termination, handlers)
        queue = queue_factory(job_root=scope.API_ROOT/'async-grading-jobs',
            heartbeat_sink=lambda value: snapshot('heartbeat.json', value))
        result = queue(rows, controls=[], qualifications=inventory['qualifications'], grading=grading,
            runtime=helpers.api_base.NoQwenRuntime(), run_episode=episode, api_runtime=api,
            stop_event=stop, progress_sink=progress, event_sink=admission.record,
            cursor_sink=lambda value: snapshot('cursor.json', value), result_sink=recorder,
            initial_state=state, model_exhausted=lambda _: False,
            generation_limit=fd_guard.admission(admission.limit, active=lambda: len(admission.active)),
            disk_check=lambda: helpers.base.check_disk_boundary(helpers.base.load(reference(
                scope.original.COORDINATOR_RUN_ROOT/'coordinator-plan.json'))['disk_boundary']))
        result.update(version=VERSION, finished_unix=time.time(), recovery_phase='44_administrative_cutoffs',
            original_first_attempts_overwritten=False, original_panel_denominator=1000,
            physical_launch_attempt=2, prior_physical_failure_audit=scope.require_physical_audit(),
            startup_health_gate=health.state())
        recorder.flush(final=True)
        final = write_new(scope.API_ROOT/'run-summary.json', result)
        # This is a real ordered next-stage worklist, not permission to launch
        # 205 additional models or to treat a classified cause as a resolution.
        write_new(scope.BATCH_ROOT/'after-recovery-technical-worklist.json', {
            'version': VERSION, 'recovery_summary': final,
            'recovery_phase_all_terminal': len(result['generation']) == 44,
            'historical_technical_unknowns': inventory['later_technical_unknown_queue'],
            'historical_scoring_unknowns': inventory['later_scoring_unknown_queue'],
            'new_recovery_unknowns': [slot for slot, value in result['generation'].items()
                                      if value.get('status') == 'technical_unknown'],
            'automatic_additional_generation_started': False,
            'cash_cap_CNY': '1700.00', 'all_prior_costs_and_uncertainty_retained': True})
        snapshot('progress.json', {'phase': 'closed' if result.get('failure') is None else 'review_required',
            'failure': result.get('failure'), 'generation_status_counts': dict(Counter(
                value['status'] for value in result['generation'].values())), 'active_generation': 0,
            'recovery_attempts_planned': 44, 'original_panel_denominator': 1000,
            'provider_failures': result.get('provider_failures'), 'api_status': api.budget_status(),
            'pending_grading_jobs': len(result.get('pending_grading_jobs', []))})
        try:
            if not parent.RELEASED.exists():
                event('owned_API_parent_release', receipt=parent.stop_empty())
        except Exception as error:
            event('owned_API_parent_cleanup_pending', error=str(error))
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', required=True, action='store_true')
    parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False))
