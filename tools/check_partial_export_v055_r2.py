"""Only the changed kernel boundary and r1-failure continuation need new controls."""
from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import repair_partial_export_v055_r2 as repair


def rejects(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError('Expected unsafe condition to fail closed')


def main():
    checks = []
    old = ast.parse((repair.ROOT / 'tools/repair_partial_export_v055_r1.py').read_text())
    new = ast.parse(repair.TOOL.read_text())
    before = {x.name: x for x in old.body if isinstance(x, ast.FunctionDef)}
    after = {x.name: x for x in new.body if isinstance(x, ast.FunctionDef)}
    unchanged = ('verify_unentered', 'archive_identity', 'validate_original', 'recovery_state',
        'publish_export', 'qualify_and_publish', 'stopped_controller')
    for name in unchanged:
        assert ast.dump(before[name], include_attributes=False) == ast.dump(after[name], include_attributes=False)
    cpu = deepcopy(after['cpu_run'])
    cpu.name = 'run'
    assert ast.dump(before['run'], include_attributes=False) == ast.dump(cpu, include_attributes=False)
    checks.append('unchanged_slot_state_publication_initializer_and_failure_bodies_reuse_r1_seven_controls')

    def reader(path):
        return repair.LIMITS[path.name]
    good = repair.check_kernel_limits('/system.slice/' + repair.SYSTEM_UNIT, reader)
    assert good['limits_verified_from_kernel'] and good['manager'] == 'system'
    rejects(lambda: repair.check_kernel_limits('/user.slice/user@1021.service/' + repair.UNIT, reader))
    rejects(lambda: repair.check_kernel_limits('/system.slice/unrelated.service', reader))
    rejects(lambda: repair.check_kernel_limits('/system.slice/' + repair.SYSTEM_UNIT,
        lambda path: 'max 100000' if path.name == 'cpu.max' else reader(path)))
    rejects(lambda: repair.check_kernel_limits('/system.slice/' + repair.SYSTEM_UNIT,
        lambda path: 'max' if path.name == 'memory.max' else reader(path)))
    checks.append('only_exact_system_unit_with_actual_cpu_memory_pid_hardlimits_is_admitted')

    with tempfile.TemporaryDirectory(prefix='v055-export-recovery-r2-control-') as directory:
        root = Path(directory)
        result = {'status': 'deferred_environment_failure', 'error': {'type': 'FileNotFoundError',
            'message': "[Errno 2] No such file or directory: '/sys/fs/cgroup/user.slice/user-1021.slice/user@1021.service/app.slice/proworksim-v055-preparation-export-recovery-8adea6639c45b4199b775fd1.service/cpu.max'"},
            'model_calls': 0, 'formal_claims': 0, 'grader_calls': 0}
        def fake_ref(path):
            return {'path': str(path), 'sha256': repair.PRIOR_SOURCE_SHA}
        with patch.object(repair, 'ENTRY', root / 'original'), patch.object(repair, 'reference', fake_ref), \
                patch.object(repair.queue, 'load', return_value=result):
            assert repair.prior_failure()['zero_additional_exports']
            bad = {**result, 'additional_exports': 1}
            with patch.object(repair.queue, 'load', return_value=bad):
                rejects(repair.prior_failure)
        checks.append('only_specific_zero_export_r1_kernel_failure_permits_one_new_revision')

        for status in ('qualified', 'missing'):
            worker = root / status
            worker.mkdir()
            request = {'recovery_plan': {'sha256': 'plan'}}
            request_ref = repair.write_new(worker / 'request.json', request)
            if status == 'qualified':
                expected = repair.write_new(worker / 'preparation-result.json', {
                    'status': 'qualified', 'request': request_ref, 'recovery_plan': request['recovery_plan']})
            commands = []
            def launched(command, **kwargs):
                commands.append(command)
                return SimpleNamespace(returncode=0, stdout='', stderr='')
            with patch.object(repair, 'WORKER', worker), \
                    patch.object(repair, 'load_plan', return_value={'kernel_limits': repair.LIMITS}), \
                    patch.object(repair.subprocess, 'run', side_effect=launched):
                observed = repair.run(request_ref)
            command = commands[0]
            assert command[:3] == ['sudo', '-n', '/usr/bin/systemd-run']
            assert '--uid=1021' in command and '--gid=1022' in command and '--pipe' in command and '--wait' in command
            assert '--property=CPUQuota=400%' in command and '--property=RuntimeMaxSec=3540' in command
            assert 'cpu-run' in command and '--unit=' + repair.SYSTEM_UNIT in command
            if status == 'qualified':
                assert observed == expected
            else:
                outcome = repair.read(observed['path'])
                assert outcome['status'] == 'deferred_environment_failure' and outcome['model_calls'] == 0
            assert (worker / 'bounded-system-intent.json').exists()
            assert (worker / 'bounded-system-completion.json').exists()
        checks.append('user_wrapper_waits_for_bounded_uid1021_system_worker_and_missing_result_stays_deferred')
    print(json.dumps({'version': repair.VERSION, 'passed': True, 'checks': checks,
        'model_calls': 0, 'GPU_loads': 0, 'Docker_calls': 0, 'services_modified': False,
        'actual_queue_state_written': False, 'real_export_started': False}, indent=2))


if __name__ == '__main__':
    main()
