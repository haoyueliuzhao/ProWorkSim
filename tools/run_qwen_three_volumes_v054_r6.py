"""Qwen r5 REF handoff host with independently sealed three-volume accounting.

The inherited recovery, planning adoption, pool overlay and worker wrapper keep
their original identities. Only this host process's disk facade is extended.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import run_qwen_ref_handoff_v054_r5 as previous
from proworksim import software_benchmark_disk_volumes_v055_r2 as volumes
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

base = previous.base
phase = previous.previous.phase
VERSION = 'v054-ref-handoff-three-volume-host-r6'
TOOL = 'tools/run_qwen_three_volumes_v054_r6.py'


def manifest_references(manifest_ref):
    value = base.load_ref(manifest_ref)
    refs = [manifest_ref, value['helper_source']]
    for key in ('secondary_registration', 'tertiary_registration'):
        refs.append(value[key])
        refs.append(base.load_ref(value[key])['marker'])
    return refs


def validate_revision(ref, *, initial=False):
    value = base.load_ref(ref)
    if (value.get('version') != VERSION or value.get('queue_root') != str(base.QUEUE)
            or value.get('Qwen_target_volume') != 'primary'
            or value.get('original_recovery_adoption_repeated') is not False
            or value.get('model_reload') is not False or value.get('inflight_directories_moved') is not False
            or value.get('original_ref_handoff_wrapper_preserved') is not True
            or value.get('volume_policy') != volumes.VOLUME_POLICY):
        raise ValueError('Unknown Qwen three-volume host revision')
    predecessor = previous.validate_revision(value['predecessor_host'], initial=initial)
    if value['pool_overlay'] != predecessor['pool_overlay']:
        raise ValueError('Three-volume host changed the existing REF handoff overlay')
    expected = {str(base.ROOT / TOOL), str(Path(volumes.__file__).resolve()), value['predecessor_host']['path']}
    expected |= {item['path'] for item in manifest_references(value['volume_manifest'])}
    if not expected <= {row['reference']['path'] for row in value['files']}:
        raise ValueError('Three-volume source or original handoff binding is missing')
    for row in value['files']:
        if initial:
            checked(row['reference'])
        if base.stat_id(row['reference']['path']) != row['stat']:
            raise ValueError('Three-volume host source or volume registration changed')
    return value


def freeze(predecessor, manifest, output, previous_controller):
    predecessor_ref, manifest_ref = reference(predecessor), reference(manifest)
    prior = previous.validate_revision(predecessor_ref, initial=True)
    volumes.configure(manifest_ref)
    state = base.read(base.QUEUE / 'state.json')
    if state.get('ref_handoff_host', {}).get('revision') != predecessor_ref:
        raise ValueError('The active REF handoff must match the explicit predecessor')
    output = Path(output).resolve()
    if not output.parent.is_relative_to(base.ROOT / 'runs/software-benchmark-v054'):
        raise ValueError('Qwen host evidence must remain inside its run root')
    refs = [row['reference'] for row in prior['files']]
    refs += [predecessor_ref, reference(base.ROOT / TOOL), reference(volumes.__file__), *manifest_references(manifest_ref)]
    refs = list({x['path']: x for x in refs}.values())
    output.parent.mkdir(parents=True, exist_ok=False)
    result = write_new(output, {'version': VERSION, 'created_utc': base.now(), 'queue_root': str(base.QUEUE),
        'evidence_root': str(output.parent), 'previous_controller_unit': previous_controller,
        'predecessor_host': predecessor_ref, 'pool_overlay': prior['pool_overlay'],
        'volume_manifest': manifest_ref, 'volume_policy': volumes.VOLUME_POLICY, 'Qwen_target_volume': 'primary',
        'files': [{'reference': x, 'stat': base.stat_id(x['path'])} for x in refs],
        'original_ref_handoff_wrapper_preserved': True, 'original_recovery_adoption_repeated': False,
        'original_resource_planning_identity_preserved': True, 'model_reload': False,
        'inflight_directories_moved': False, 'entered_generation_replayed': False,
        'scientific_configuration_changed': False, 'model_calls': 0})
    validate_revision(result, initial=True)
    return result


class ThreeVolumeCoordinator(previous.HandoffCoordinator):
    def __init__(self, revision_ref):
        self.three_volume_ref = revision_ref
        self.three_volume_revision = validate_revision(revision_ref, initial=True)
        if base.Systemd().active(self.three_volume_revision['previous_controller_unit']):
            raise ValueError('Previous Qwen coordinator must stop; workers and models remain untouched')
        volumes.configure(self.three_volume_revision['volume_manifest'])
        # The unchanged parent preserves r5's wrapper, overlay and old adoption.
        super().__init__(self.three_volume_revision['predecessor_host'])
        phase.previous.shared_disk = phase.StageDelegate(volumes)
        phase.original.disk = phase.previous.PlanningDiskFacade()
        rows_before = json.dumps(self.state['rows'], sort_keys=True)
        prior = self.state.get('three_volume_host')
        if prior is not None and prior.get('revision') != revision_ref:
            self.lease.close()
            raise ValueError('Another three-volume host already owns the queue')
        path = Path(self.three_volume_revision['evidence_root']) / 'host-adoption.json'
        if path.exists():
            proof = reference(path)
            if base.load_ref(proof)['revision'] != revision_ref:
                raise ValueError('Existing three-volume adoption differs')
        else:
            proof = write_new(path, {'version': VERSION, 'utc': base.now(), 'revision': revision_ref,
                'predecessor_host': self.three_volume_revision['predecessor_host'],
                'volume_manifest': self.three_volume_revision['volume_manifest'],
                'resource_recovery_preserved': self.state['resource_recovery'],
                'resource_planning_revision_preserved': self.state['resource_planning_revision'],
                'ref_handoff_host_preserved': self.state['ref_handoff_host'],
                'inflight_generations_preserved': [r['slot']['slot_id'] for r in self.state['rows']
                                                 if r['generation']['status'] in base.ACTIVE],
                'controller_lock_owned': True, 'original_adoptions_repeated': False,
                'model_calls': 0, 'GPU_loads': 0, 'formal_claims': 0,
                'worker_processes_signalled': False, 'inflight_directories_moved': False})
        self.state['three_volume_host'] = {'revision': revision_ref, 'adoption': proof}
        if json.dumps(self.state['rows'], sort_keys=True) != rows_before:
            raise AssertionError('Three-volume host adoption changed a formal row')
        self.save()

    def validate_state(self):
        super().validate_state()
        validate_revision(self.three_volume_ref)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    p = commands.add_parser('freeze')
    for name in ('predecessor', 'volumes', 'output'):
        p.add_argument('--' + name, required=True, type=Path)
    p.add_argument('--previous-controller', required=True)
    p = commands.add_parser('run')
    p.add_argument('--revision', required=True, type=Path)
    p.add_argument('--sha256', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if args.operation == 'freeze':
        print(json.dumps(freeze(args.predecessor, args.volumes, args.output, args.previous_controller)))
        return
    ref = reference(args.revision)
    if ref['sha256'] != args.sha256:
        raise ValueError('Three-volume Qwen host SHA differs')
    coordinator = ThreeVolumeCoordinator(ref)
    try:
        return coordinator.run()
    finally:
        coordinator.lease.close()


if __name__ == '__main__':
    main()
