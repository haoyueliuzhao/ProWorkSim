"""r8 all-arm budget/solver with locked future secondary-or-tertiary placement.

Only original pending generation slots can choose a new volume. All old intent
paths are checked under the original cross-host lock before selection; the same
lock covers admission, durable intent and the original worker builder.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import time

from . import software_benchmark_queue_native_host_v055_r8 as previous
from . import software_benchmark_disk_volumes_v055_r2 as volumes
from . import software_benchmark_preparation_priority_v055_r1 as priority
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_queue_v055 import ROOT, load, now
from .storage import digest

VERSION = 'v055-budget-r4-native-r3-three-volume-host-r9'
TARGETS = ('secondary', 'tertiary')
GENERATION_ROOTS = {'secondary': volumes.SECONDARY_ROOT, 'tertiary': volumes.TERTIARY_ROOT}


def qualification(ref):
    value = load(ref)
    zero_model = value.get('model_calls') == 0 or (
        value.get('real_API_calls') == 0 and value.get('formal_3000_claims') == 0
        and value.get('official_grader_calls') == 0)
    if (not (value.get('passed') is True or value.get('admitted') is True) or not zero_model
            or value.get('bind') != str(volumes.TERTIARY_ROOT)
            or value.get('primary_device') != 66306 or value.get('tertiary_device') != 66308
            or value.get('existing_data_moved') is not False):
        raise ValueError('Tertiary worker placement requires its actual zero-model lifecycle control')
    return value


def manifest_references(ref):
    manifest = load(ref)
    refs = [ref, manifest['helper_source']]
    for key in ('secondary_registration', 'tertiary_registration'):
        refs += [manifest[key], load(manifest[key])['marker']]
    return refs


def validate_revision(ref):
    value = load(ref)
    prior = load(value['predecessor_revision'])
    if (value.get('version') != VERSION or prior.get('version') != previous.VERSION
            or value.get('original_plan') != prior['original_plan'] or value.get('activation') != prior['activation']
            or value.get('budget_policy_sha256') != prior['budget_policy_sha256']
            or value['budget_policy_sha256'] != previous.runtime.policy_sha256()
            or value.get('disk_policy') != volumes.POLICY or value.get('disk_volume_policy') != volumes.VOLUME_POLICY
            or value.get('unused_ready_backlog_limit') != 8
            or value.get('existing_worker_directories_moved') is not False
            or value.get('automatic_model_replay') is not False):
        raise ValueError('Three-volume host cannot alter the r8 financial or scientific protocol')
    original_manifest = load(value['volume_manifest'])
    if original_manifest['secondary_registration'] != prior['volume_manifest']:
        raise ValueError('Original qualified secondary registration must remain identical')
    for item in value['files']:
        checked(item)
    qualification(value['tertiary_qualification'])
    previous.previous.check_qualification(prior['cross_volume_qualification'])
    return value


def select_generation_volume(snapshot, requested_bytes):
    """Pure selection: retain 100 GiB on both candidates and primary's old floor."""
    if snapshot.get('metadata_error'):
        return None, {'admitted': False, 'metadata_error': snapshot['metadata_error']}
    primary = snapshot['volumes']['primary']
    if not previous.original.disk_admission(primary['free_bytes'])['generation_disk_admitted']:
        return None, {'admitted': False, 'reason': 'primary_shared_infrastructure_floor',
                      'primary_available_bytes': primary['free_bytes']}
    gates = {}
    for name in TARGETS:
        target = snapshot['volumes'][name]
        gates[name] = volumes.admission(target['free_bytes'], target['active_peak_reserved_bytes'],
                                       requested_bytes, kind='generation')
        gates[name]['target_volume'] = name
    eligible = [name for name in TARGETS if gates[name]['admitted']]
    if not eligible:
        return None, {'admitted': False, 'reason': 'both_generation_volumes_below_floor', 'volume_candidates': gates}
    # Fixed tie order retains secondary; capacity alone decides, never outcomes.
    chosen = max(eligible, key=lambda name: gates[name]['estimated_unreserved_bytes_after_launch'])
    return chosen, {**gates[chosen], 'volume_candidates': gates,
                    'selection_basis': 'largest_available_after_live_reservations_and_new_request'}


def generation_directories(slot_id, primary_root):
    suffix = digest((slot_id + '-generation').encode())[:24]
    roots = {'primary': primary_root, **GENERATION_ROOTS}
    return {name: root / 'workers' / ('generation-' + suffix) for name, root in roots.items()}


def assert_controller_stopped(unit):
    if not re.fullmatch(r'proworksim-[A-Za-z0-9_.-]+\.service', unit):
        raise ValueError('Unexpected predecessor controller unit')
    result = subprocess.run(['systemctl', '--user', 'show', unit, '--property=ActiveState,MainPID'],
                            capture_output=True, text=True, timeout=20, check=False)
    state = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if state.get('ActiveState') not in {'inactive', 'failed'} or state.get('MainPID') != '0':
        raise ValueError('Previous controller must stop; old workers must remain untouched')


class NativeHostCoordinator(previous.NativeHostCoordinator):
    def __init__(self, revision_ref):
        self.three_volume_ref = revision_ref
        self.three_volume_revision = validate_revision(revision_ref)
        assert_controller_stopped(self.three_volume_revision['previous_controller_unit'])
        volumes.configure(self.three_volume_revision['volume_manifest'])
        # Keep the old r8 activation validation, BudgetLedger r4 binding and
        # all-arm materialize/direct-command contexts exactly as implemented.
        super().__init__(self.three_volume_revision['predecessor_revision'])
        before = json.dumps(self.state['rows'], sort_keys=True)
        self.revision_ref = revision_ref
        # self.revision and self.predecessor intentionally remain the r8/r7
        # financial activation pair used by the inherited load_activation.
        history = self.state.setdefault('host_revision_history', [])
        if not history or history[-1]['revision'] != revision_ref:
            history.append({'revision': revision_ref, 'adopted_utc': now(),
                            'existing_worker_jobs_unchanged': True, 'entered_slots_replayed': 0})
        self.state['active_host_revision'] = revision_ref
        self.state['future_generation_volume'] = {'names': list(TARGETS),
            'roots': {k: str(v) for k, v in GENERATION_ROOTS.items()},
            'manifest': self.three_volume_revision['volume_manifest'],
            'queue_state_and_ledger_remain_primary': True, 'cross_volume_preintent_guard': True}
        if json.dumps(self.state['rows'], sort_keys=True) != before:
            raise AssertionError('Three-volume adoption changed a formal row')
        self.save()

    def disk_snapshot(self):
        self._priority_demand = None
        try:
            old = json.loads((ROOT / 'runs/software-benchmark-v054/formal-queue-r1/state.json').read_bytes())
            snapshot = volumes.shared_disk_snapshot(v055_state=self.state, v054_state=old,
                cache=self._manifest_costs, target_volume=self._target_volume)
            self._priority_demand = priority.preparation_demand(old, self.state)
            self.state['shared_preparation_demand'] = self._priority_demand
            snapshot['preparation_priority'] = self._priority_demand
            return snapshot
        except (OSError, ValueError, KeyError, TypeError) as error:
            snapshot = volumes.shared_disk_snapshot(v055_state=self.state, cache=self._manifest_costs,
                                                    target_volume=self._target_volume)
            snapshot['metadata_error'] = {'type': type(error).__name__, 'message': str(error)}
            return snapshot

    def launch(self, row, record, *, kind, request=None):
        if kind != 'generation':
            return super().launch(row, record, kind=kind, request=request)
        if record['status'] != 'pending':
            raise ValueError('New volume placement cannot replay an entered generation')
        if self._generation_disk_closed:
            return
        saved_root, saved_target, saved_arm = self.root, self._target_volume, self._candidate_arm
        sentinel = object()
        saved_runtime = record.get('runtime_revision', sentinel)
        project = row['slot']['arm'] == 'PROJECT'
        if project:
            record['runtime_revision'] = self.activation_ref
        self._candidate_arm = row['slot']['arm']
        try:
            with volumes.disk_dispatch_lock():
                paths = generation_directories(row['slot']['slot_id'], saved_root)
                existing = {name: str(path) for name, path in paths.items() if path.exists() or path.is_symlink()}
                if existing:
                    record['three_volume_preintent_conflicts'] = existing
                    self.defer(row, record, 'preexisting_generation_directory_on_registered_volume_requires_explicit_recovery')
                    self.save()
                    return
                snapshot = self.disk_snapshot()
                self.state['disk_reservation_status'] = snapshot
                if snapshot.get('metadata_error'):
                    self.state['last_disk_dispatch_admission'] = {'admitted': False,
                        'instance_id': row['slot']['instance_id'], 'observed_utc': now(),
                        'metadata_error': snapshot['metadata_error'], 'scope': 'shared_volume_observation'}
                    self._generation_disk_closed = True
                    return
                try:
                    estimate = self.template_reservation(row['slot']['instance_id'])
                except (OSError, ValueError, KeyError, TypeError) as error:
                    gate = {'admitted': False, 'instance_id': row['slot']['instance_id'], 'observed_utc': now(),
                            'metadata_error': {'type': type(error).__name__, 'message': str(error)},
                            'scope': 'single_task_template_estimate', 'model_calls': 0}
                    record['disk_metadata_failure'] = gate
                    self.state['last_disk_dispatch_admission'] = gate
                    self.defer(row, record, 'generation_template_disk_metadata_unavailable')
                    self.save()
                    return
                chosen, gate = select_generation_volume(snapshot, estimate['peak_bytes'])
                gate.update(instance_id=row['slot']['instance_id'], observed_utc=now(), estimate=estimate,
                            preparation_priority=self._priority_demand,
                            primary_preparation_priority_not_charged_to_generation_volume=True)
                if self._priority_demand is None:
                    chosen = None
                    gate.update(admitted=False, priority_observation_missing=True)
                self.state['last_disk_dispatch_admission'] = gate
                if chosen is None:
                    self._generation_disk_closed = True
                    return
                self.root, self._target_volume = GENERATION_ROOTS[chosen], chosen
                record['disk_reservation'] = {'host_revision': self.three_volume_ref, **gate}
                # Directly reuse the unchanged original r2 builder while keeping
                # r8's already-installed all-arm budget routes. Its durable save
                # and systemd launch execute before releasing this same flock.
                return previous.builder.NativeHostCoordinator.launch(self, row, record, kind=kind, request=request)
        finally:
            self.root, self._target_volume, self._candidate_arm = saved_root, saved_target, saved_arm
            if project and record['status'] == 'pending':
                if saved_runtime is sentinel:
                    record.pop('runtime_revision', None)
                else:
                    record['runtime_revision'] = saved_runtime


def freeze(predecessor, manifest, control, output, previous_controller):
    oldref, manifest_ref, control_ref = reference(predecessor), reference(manifest), reference(control)
    prior = load(oldref)
    if prior['version'] != previous.VERSION:
        raise ValueError('Require the exact currently active r8 financial host')
    qualification(control_ref)
    volumes.configure(manifest_ref)
    refs = [reference(__file__), reference(ROOT / 'tools/run_deepseek_queue_native_host_v055_r9.py'),
            oldref, control_ref, reference(volumes.__file__), *manifest_references(manifest_ref), *prior['files']]
    refs = list({x['path']: x for x in refs}.values())
    output = Path(output).resolve()
    if not output.parent.is_relative_to(ROOT / 'runs/software-benchmark-v055'):
        raise ValueError('Three-volume host evidence must remain inside the original experiment')
    output.parent.mkdir(parents=True, exist_ok=False)
    result = write_new(output, {'version': VERSION, 'created_utc': now(), 'predecessor_revision': oldref,
        'original_plan': prior['original_plan'], 'activation': prior['activation'],
        'budget_policy_sha256': prior['budget_policy_sha256'], 'budget_cap_cny': 2000,
        'disk_policy': volumes.POLICY, 'disk_volume_policy': volumes.VOLUME_POLICY,
        'volume_manifest': manifest_ref, 'tertiary_qualification': control_ref,
        'unused_ready_backlog_limit': 8, 'previous_controller_unit': previous_controller, 'files': refs,
        'existing_worker_directories_moved': False, 'automatic_model_replay': False,
        'financial_adapter_r4_and_native_solver_r3_unchanged': True,
        'queue_ledger_scoring_and_preparation_stay_primary': True,
        'same_shared_lock_covers_selection_intent_and_launch': True, 'model_calls': 0})
    validate_revision(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    p = commands.add_parser('freeze')
    for name in ('predecessor', 'volumes', 'qualification', 'output'):
        p.add_argument('--' + name, required=True, type=Path)
    p.add_argument('--previous-controller', required=True)
    p = commands.add_parser('run')
    p.add_argument('--revision', required=True, type=Path)
    p.add_argument('--sha256', required=True)
    args = parser.parse_args()
    if args.operation == 'freeze':
        print(json.dumps(freeze(args.predecessor, args.volumes, args.qualification, args.output, args.previous_controller)))
        return
    ref = reference(args.revision)
    if ref['sha256'] != args.sha256:
        raise ValueError('Three-volume DeepSeek host SHA differs')
    coordinator = NativeHostCoordinator(ref)
    try:
        while not coordinator.tick():
            time.sleep(5)
    finally:
        coordinator.close_bindings()
        coordinator.lease.close()


if __name__ == '__main__':
    main()
