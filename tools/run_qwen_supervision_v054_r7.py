"""Future-only host supervision wrapper over the sealed three-volume r6 host."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import run_qwen_three_volumes_v054_r6 as previous
import supervision_proc_exit_overlay_v054_r1 as overlay
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

base = previous.base
VERSION = 'v054-future-supervision-host-r7'


def route(argv, *, kind, overlay_ref, handoff_ref, handoff_revision):
    argv = list(argv)
    if kind != 'generation':
        return argv, None
    canonical = [str(base.HOST_PYTHON), str(base.ROOT / 'tools/run_benchmark_episode_v054.py')]
    kernel = ['/usr/bin/env', 'PYTHONPATH=' + str(overlay.KERNEL / 'src') + ':' + str(overlay.KERNEL),
              str(base.HOST_PYTHON), str(overlay.ENTRIES['kernel'])]
    if argv[:2] == canonical:
        routed, changed = previous.previous.route_new_worker(argv, kind=kind,
            revision_ref=handoff_ref, revision=handoff_revision)
        if not changed or routed[1] != str(overlay.ENTRIES['canonical']):
            raise ValueError('Original REF handoff route was not preserved')
        prefix, args, mode = routed[:1], routed[2:], 'canonical'
    elif argv[:4] == kernel:
        prefix, args, mode = argv[:3], argv[4:], 'kernel'
    else:
        raise ValueError('Unrecognized future generation source route')
    return [*prefix, str(overlay.ENTRY), '--overlay', overlay_ref['path'],
            '--sha256', overlay_ref['sha256'], '--source', mode, '--', *args], mode


def validate_revision(ref, *, initial=False):
    value = base.load_ref(ref)
    if (value.get('version') != VERSION or value.get('queue_root') != str(base.QUEUE)
            or value.get('previous_controller_unit') != 'proworksim-v054-formal-queue-three-volumes-r6.service'
            or value.get('scientific_bindings_changed') is not False
            or value.get('entered_generation_replayed') is not False
            or value.get('model_reload') is not False):
        raise ValueError('Unknown future supervision host revision')
    previous.validate_revision(value['predecessor_host'], initial=initial)
    overlay.validate(value['supervision_overlay'])
    if value.get('source') != reference(__file__):
        raise ValueError('Future supervision host source changed')
    return value


def freeze(predecessor, output):
    pred = reference(predecessor)
    previous.validate_revision(pred, initial=True)
    state = base.read(base.QUEUE / 'state.json')
    if state.get('three_volume_host', {}).get('revision') != pred or state.get('status') != 'running':
        raise ValueError('Freeze only over the running original r6 host')
    output = Path(output).resolve()
    if not output.parent.is_relative_to(base.ROOT / 'runs/software-benchmark-v054'):
        raise ValueError('Host evidence must remain in the original run root')
    output.parent.mkdir(parents=True, exist_ok=False)
    patch = write_new(output.parent / 'overlay.json', {
        'version': overlay.VERSION, 'maximum_attempts': overlay.MAX_ATTEMPTS,
        'retry_window_seconds': overlay.RETRY_WINDOW_SECONDS,
        'full_original_quiet_checks_retained': True, 'original_stop_seconds_unchanged': True,
        'model_calls': 0, 'sources': overlay.source_refs(),
        'files': [reference(x) for x in (overlay.TOOL, overlay.ENTRY, overlay.HOST)]})
    result = write_new(output, {'version': VERSION, 'created_utc': base.now(),
        'queue_root': str(base.QUEUE), 'evidence_root': str(output.parent),
        'previous_controller_unit': 'proworksim-v054-formal-queue-three-volumes-r6.service',
        'predecessor_host': pred, 'supervision_overlay': patch, 'source': reference(__file__),
        'scientific_bindings_changed': False, 'entered_generation_replayed': False,
        'model_reload': False, 'old_unknowns_reclassified': False,
        'future_generations_only': True, 'old_r5_handoff_and_gpu6_source_roots_preserved': True})
    validate_revision(result, initial=True)
    return result


class SupervisionCoordinator(previous.ThreeVolumeCoordinator):
    def __init__(self, revision_ref):
        self.supervision_ref = revision_ref
        self.supervision_revision = validate_revision(revision_ref, initial=True)
        if base.Systemd().active(self.supervision_revision['previous_controller_unit']):
            raise ValueError('Only the prior manager must stop; workers and GPUs remain untouched')
        super().__init__(self.supervision_revision['predecessor_host'])
        before = json.dumps(self.state['rows'], sort_keys=True)
        prior = self.state.get('supervision_host')
        if prior is not None and prior['revision'] != revision_ref:
            self.lease.close()
            raise ValueError('Another supervision revision already owns the queue')
        path = Path(self.supervision_revision['evidence_root']) / 'host-adoption.json'
        if path.exists():
            proof = reference(path)
            if base.load_ref(proof)['revision'] != revision_ref:
                raise ValueError('Existing supervision adoption differs')
        else:
            proof = write_new(path, {'version': VERSION, 'utc': base.now(), 'revision': revision_ref,
                'predecessor_host': self.supervision_revision['predecessor_host'],
                'existing_formal_rows_preserved': True, 'model_calls': 0, 'GPU_loads': 0,
                'workers_signalled': False, 'original_adoptions_repeated': False})
        self.state['supervision_host'] = {'revision': revision_ref, 'adoption': proof}
        if json.dumps(self.state['rows'], sort_keys=True) != before:
            raise AssertionError('Supervision adoption changed a formal row')
        self.save()

    def validate_state(self):
        super().validate_state()
        validate_revision(self.supervision_ref)

    def start_job(self, record, *, kind, directory, argv):
        if kind == 'generation' and (record.get('status') != 'pending' or record.get('claimed') is not False):
            raise ValueError('Supervision wrapper cannot adopt an entered generation')
        routed, mode = route(argv, kind=kind,
            overlay_ref=self.supervision_revision['supervision_overlay'],
            handoff_ref=self.handoff_revision_ref, handoff_revision=self.handoff_revision)
        if mode:
            record['supervision_host_revision'] = self.supervision_ref
            record['supervision_overlay'] = self.supervision_revision['supervision_overlay']
            record['supervision_source_mode'] = mode
            if mode == 'canonical':
                record['ref_handoff_host_revision'] = self.handoff_revision_ref
                record['ref_handoff_pool_overlay'] = self.handoff_revision['pool_overlay']
        return super().start_job(record, kind=kind, directory=directory, argv=routed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    p = commands.add_parser('freeze')
    p.add_argument('--predecessor', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p = commands.add_parser('run')
    p.add_argument('--revision', required=True, type=Path)
    p.add_argument('--sha256', required=True)
    args = parser.parse_args()
    if args.operation == 'freeze':
        print(json.dumps(freeze(args.predecessor, args.output)))
        return
    ref = reference(args.revision)
    if ref['sha256'] != args.sha256:
        raise ValueError('Supervision host SHA differs')
    checked(ref)
    coordinator = SupervisionCoordinator(ref)
    try:
        return coordinator.run()
    finally:
        coordinator.lease.close()


if __name__ == '__main__':
    main()
