"""Small, synthetic-only controls for explicit interrupted export recovery."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import repair_partial_export_v055_r1 as repair
from proworksim import software_benchmark_disk_stages_v055_r1 as stages


def rejects(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError('Unsafe control was not rejected')


def slots(count, family):
    return [{'slot': {'slot_id': f'{family}-{i}', 'instance_id': repair.INSTANCE, 'seed': i},
        'generation': {'status': 'pending'}, 'scores': [], 'environment_status': 'failed'} for i in range(count)]


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='v055-export-recovery-control-') as directory:
        root = Path(directory)
        old, state = {'rows': slots(3, 'v054')}, {'rows': slots(6, 'v055')}
        with patch.object(repair, 'ROOT', root), patch.object(repair, 'QROOT', root / 'primary'), \
                patch.object(repair.volumes, 'SECONDARY_ROOT', root / 'secondary'), \
                patch.object(repair.volumes, 'TERTIARY_ROOT', root / 'tertiary'):
            frozen_slots = repair.verify_unentered(old, state, None)
            assert len(frozen_slots) == 9
            bad = deepcopy(state)
            bad['rows'][0]['generation'] = {'status': 'closed'}
            rejects(lambda: repair.verify_unentered(old, bad, frozen_slots))
            bad = deepcopy(state)
            bad['rows'][0]['slot']['seed'] = 77
            rejects(lambda: repair.verify_unentered(old, bad, frozen_slots))
            claim = root / 'runs/software-benchmark-v055/episode-claims' / hashlib.sha256(b'v055-0').hexdigest()
            claim.mkdir(parents=True)
            rejects(lambda: repair.verify_unentered(old, state, frozen_slots))
            claim.rmdir()
            pending_dir = root / 'secondary/workers' / ('generation-' + repair.digest(b'v055-0-generation')[:24])
            pending_dir.mkdir(parents=True)
            rejects(lambda: repair.verify_unentered(old, state, frozen_slots))
            pending_dir.rmdir()
        checks.append('exact_nine_unentered_slots_only_reject_claim_preintent_and_seed_change')

        failed = {'readiness': {'status': 'failed'}, 'attempts': [], 'exception_recorded': True}
        state.update(preparation={repair.INSTANCE: failed}, status='running', exceptions=[{'old': 'environment failure'}],
            plan={'sha256': 'plan'}, active_host_revision={'sha256': 'host'}, budget={'halted': False, 'cap_cny': 2000},
            dispatch_stopped=False, ended_utc='old')
        plan = {'original_deepseek_preparation': deepcopy(failed), 'host_revision': state['active_host_revision'], 'queue_plan': state['plan']}
        updated = repair.recovery_state(state, plan, {}, {}, {'admitted': True}, {'receipt': 'new'})
        assert updated['rows'] == state['rows'] and updated['exceptions'] == state['exceptions']
        assert updated['budget'] == state['budget'] and updated['preparation'][repair.INSTANCE]['exception_recorded']
        assert state['preparation'][repair.INSTANCE] == failed
        assert updated['preparation'][repair.INSTANCE]['readiness']['status'] == 'preparing'
        checks.append('pure_adoption_preserves_all_rows_old_exception_budget_and_original_input')
        for change in ({'dispatch_stopped': True}, {'budget': {'halted': True}}, {'status': 'paused_technical_unknown'}):
            rejects(lambda change=change: repair.recovery_state({**state, **change}, plan, {}, {}, {}, {}))
        terminal = {**state, 'status': 'primary_finished_with_deferred_environment', 'ended_utc': 'prior'}
        reopened = repair.recovery_state(terminal, plan, {}, {}, {}, {})
        assert reopened['status'] == 'running' and 'ended_utc' not in reopened and terminal['ended_utc'] == 'prior'
        bad = deepcopy(terminal)
        bad['rows'].append({'slot': {'instance_id': 'another'}, 'generation': {'status': 'pending'}, 'scores': [], 'environment_status': 'failed'})
        rejects(lambda: repair.recovery_state(bad, plan, {}, {}, {}, {}))
        bad = deepcopy(terminal)
        bad['rows'][0]['scores'] = [{'status': 'running'}]
        rejects(lambda: repair.recovery_state(bad, plan, {}, {}, {}, {}))
        checks.append('exact_deferred_environment_terminal_can_resume_without_bypassing_halts_or_other_pending_work')

        stage, target = root / 'staging', root / 'canonical'
        (stage / 'rootfs').mkdir(parents=True)
        target.mkdir()
        payload = stage / 'rootfs/file'
        payload.write_bytes(b'same image bytes')
        payload_identity = (payload.stat().st_ino, payload.stat().st_size)
        (target / 'rootfs.tar').write_bytes(b'original truncated bytes')
        (target / 'preparation-failure.json').write_bytes(b'original failure')
        environment, mapping = {'public': 'only'}, {'sha256': 'mapping'}
        manifest = {'prepared_root': str(stage / 'rootfs'), 'image_id': repair.IMAGE_ID,
            'instance_id': repair.INSTANCE, 'baseline_mapping': mapping,
            'source_environment_sha256': repair.digest(repair.canonical(environment)),
            'numeric_ownership_equivalence_admitted': True, 'native_real_task_control_passed': False}
        repair.write_new(stage / 'rootfs-manifest.json', repair.canonical(manifest))
        repair.write_new(stage / 'public-environment.json', {'rootfs_manifest': str(stage / 'rootfs-manifest.json')})
        before = (stage / 'rootfs-manifest.json').read_bytes()
        publication = repair.publish_export(environment, mapping, stage, target)
        assert (stage / 'rootfs-manifest.json').read_bytes() == before
        assert repair.read(target / 'rootfs-manifest.json')['prepared_root'] == str(target / 'rootfs')
        assert repair.read(target / 'public-environment.json')['rootfs_manifest'] == str(target / 'rootfs-manifest.json')
        assert (target / 'rootfs/file').read_bytes() == b'same image bytes'
        assert (target / 'rootfs/file').stat().st_ino == payload_identity[0]
        assert (target / 'preparation-failure.json').read_bytes() == b'original failure'
        assert (target / 'rootfs.tar').read_bytes() == b'original truncated bytes'
        assert not (target / 'lazy-preparation.json').exists()
        assert publication['canonical_manifest_will_be_finalized_after_initialization']
        rejects(lambda: repair.publish_export(environment, mapping, stage, target))
        checks.append('same_payload_inode_canonical_paths_old_failure_tar_preserved_and_no_premature_qualification')
        with patch.object(repair, 'ENTRY', target), patch.object(repair.lazy, 'qualify_instance', side_effect=ValueError('controlled initialization failure')):
            rejects(lambda: repair.qualify_and_publish(environment, {'stdlib': 'fake'}, {}))
        assert not (target / 'lazy-preparation.json').exists()
        checks.append('initialization_failure_never_publishes_qualified_receipt')

        # The old disk stage helper can parse this custom worker's unmodified
        # request format, hence the normal queue accounts its reservation.
        worker = root / 'runs/software-benchmark-v055/queue-r1/workers/preparation-test'
        worker.mkdir(parents=True)
        request = repair.write_new(worker / 'request.json', {'instance_id': repair.INSTANCE,
            'cache_root': str(root / 'runs/software-benchmark-v054/native-lazy-cache'), 'baseline_mapping': mapping})
        job = repair.write_new(worker / 'job.json', {'instance_id': repair.INSTANCE,
            'argv': ['python', 'tool.py', 'run', '--request', request['path'], '--sha256', request['sha256']]})
        with patch.object(stages, 'ROOT', root):
            parsed = stages._preparation_request(repair.INSTANCE, {'worker': {'job': job, 'directory': str(worker)}}, {})
        assert parsed['reference'] == request
        checks.append('original_shared_disk_stage_parser_accepts_the_normal_request_and_job_schema')

        # Exercise the old completion collector, not an imitation of its logic.
        qualified = {'status': 'qualified', 'instance_id': repair.INSTANCE, 'receipt': {'sha256': 'qualified'}}
        repair.write_new(worker / 'completion.json', {'status': 'process_exited'})
        repair.write_new(worker / 'preparation-result.json', {'status': 'qualified'})
        observer = object.__new__(repair.queue.Coordinator)
        observer.state = {'preparation': {repair.INSTANCE: {'readiness': {'status': 'preparing'}, 'attempts': [],
            'exception_recorded': True, 'worker': {'status': 'running', 'directory': str(worker)}}},
            'exceptions': [{'prior': True}]}
        observer.registry = {repair.INSTANCE: {'baseline_mapping': mapping}}
        observer.template = {'lazy_native_preparation': {'cache_root': str(target)}}
        with patch('proworksim.software_benchmark_prewarm_v054.preparation_state', return_value=qualified):
            observer.refresh_preparation()
        assert observer.state['preparation'][repair.INSTANCE]['readiness'] == qualified
        assert len(observer.state['preparation'][repair.INSTANCE]['attempts']) == 1
        assert observer.state['exceptions'] == [{'prior': True}]
        checks.append('unchanged_r9_completion_path_adopts_qualified_result_preserving_old_exception')
    print(json.dumps({'version': repair.VERSION, 'passed': True, 'checks': checks,
        'model_calls': 0, 'GPU_loads': 0, 'Docker_calls': 0, 'services_modified': False,
        'actual_queue_state_written': False}, indent=2))


if __name__ == '__main__':
    main()
