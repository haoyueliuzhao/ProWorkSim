"""Pure CPU controls for the future-only host supervisor identity-exit overlay."""
from __future__ import annotations

import argparse
import errno
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import supervision_proc_exit_overlay_v054_r1 as overlay

sys.path.insert(0, str(overlay.ROOT / 'src'))
from proworksim import software_benchmark_supervision_v054 as original
import run_qwen_supervision_v054_r7 as host

SCOPE = {'unit': 'proworksim-v054-episode-' + 'a' * 32 + '-model.service',
         'invocation_id': 'invocation-one', 'main': {'pid': 7654321, 'start_ticks': 12345},
         'cgroup': '/user.slice/test.service', 'manager': 'user', 'stop_seconds': 5}


def missing(path='/proc/7654321/stat'):
    return FileNotFoundError(errno.ENOENT, 'No such file or directory', path)


def state(*, active=True, invocation='invocation-one', pid=7654321, collected=False):
    return {'InvocationID': '' if collected else invocation, 'ControlGroup': '' if collected else SCOPE['cgroup'],
            'MainPID': str(pid if active else 0), 'ActiveState': 'active' if active else 'inactive',
            'LoadState': 'not-found' if collected else 'loaded', 'KillMode': 'control-group', 'Result': 'success'}


class Controls(unittest.TestCase):
    def test_exact_pid_exit_then_collected_uses_full_quiet_check(self):
        with (patch.object(original, 'properties', side_effect=[state(), state(active=False, collected=True),
                    state(active=False, collected=True)]) as properties,
              patch.object(original, 'process_identity', side_effect=missing()) as identity,
              patch.object(original, '_populated', return_value=False) as populated,
              patch.object(original, '_systemctl') as signal):
            result = overlay.bounded_stop(original.stop_owned, SCOPE)
        self.assertEqual(properties.call_count, 3)
        self.assertEqual(identity.call_count, 2)
        populated.assert_called_once_with(SCOPE['cgroup'])
        signal.assert_not_called()
        self.assertTrue(result['registered_main_exited'])
        self.assertEqual(result['proc_exit_identity_retry']['attempts'], 2)
        self.assertEqual(result['proc_exit_identity_retry']['failures'][0]['filename'], '/proc/7654321/stat')

    def test_descendants_require_original_stop_and_quiet(self):
        with (patch.object(original, 'properties', side_effect=[state(), state(pid=0), state(active=False)]),
              patch.object(original, 'process_identity', side_effect=missing()),
              patch.object(original, '_populated', return_value=False) as populated,
              patch.object(original, '_systemctl') as signal):
            result = overlay.bounded_stop(original.stop_owned, SCOPE)
        signal.assert_called_once_with('stop', '--no-block', SCOPE['unit'], manager='user')
        populated.assert_called_once_with(SCOPE['cgroup'])
        self.assertFalse(result['populated'])

    def test_new_unit_invocation_is_rejected(self):
        with (patch.object(original, 'properties', side_effect=[state(), state(invocation='replacement')]),
              patch.object(original, 'process_identity', side_effect=missing()),
              patch.object(original, '_systemctl') as signal):
            with self.assertRaisesRegex(ValueError, 'different invocation'):
                overlay.bounded_stop(original.stop_owned, SCOPE)
        signal.assert_not_called()

    def test_pid_reuse_is_rejected(self):
        with (patch.object(original, 'properties', return_value=state()),
              patch.object(original, 'process_identity', side_effect=[missing(), {'pid': 7654321, 'start_ticks': 99999}]),
              patch.object(original, '_systemctl') as signal):
            with self.assertRaisesRegex(ValueError, 'identity changed'):
                overlay.bounded_stop(original.stop_owned, SCOPE)
        signal.assert_not_called()

    def test_other_errors_are_not_retried(self):
        for error in (missing('/tmp/unrelated'), PermissionError(errno.EACCES, 'denied', '/proc/7654321/stat'),
                      RuntimeError('live descendant')):
            with self.subTest(type=type(error).__name__, filename=getattr(error, 'filename', None)):
                calls = []
                def fail(scope):
                    calls.append(scope)
                    raise error
                with self.assertRaises(type(error)):
                    overlay.bounded_stop(fail, SCOPE)
                self.assertEqual(len(calls), 1)

    def test_repeat_bound_and_window(self):
        calls = []
        def fail(scope):
            calls.append(scope)
            raise missing()
        with self.assertRaises(FileNotFoundError):
            overlay.bounded_stop(fail, SCOPE, clock=lambda: 1)
        self.assertEqual(len(calls), 3)
        calls.clear()
        clock = iter([1, 1.3])
        with self.assertRaises(FileNotFoundError):
            overlay.bounded_stop(fail, SCOPE, clock=lambda: next(clock))
        self.assertEqual(len(calls), 1)

    def test_live_descendant_is_not_declared_quiet(self):
        with (patch.object(original, 'properties', side_effect=[state(), state(active=False, collected=True),
                    state(active=False, collected=True)]),
              patch.object(original, 'process_identity', side_effect=missing()),
              patch.object(original, '_populated', return_value=True),
              patch.object(original, '_systemctl') as signal):
            with self.assertRaisesRegex(RuntimeError, 'descendant'):
                overlay.bounded_stop(original.stop_owned, SCOPE)
        signal.assert_not_called()

    def test_routes_keep_original_entry_payload_and_gpu6_env(self):
        ref = {'path': '/sealed/overlay.json', 'sha256': 'a' * 64}
        handoff = {'path': '/sealed/r5.json', 'sha256': 'b' * 64}
        revision = {'episode_wrapper': str(overlay.ENTRIES['canonical']),
                    'pool_overlay': {'path': '/sealed/pool.json', 'sha256': 'c' * 64}}
        args = ['--config', '/original/config.json', '--output', '/original/episode']
        canonical = [str(host.base.HOST_PYTHON), str(overlay.ROOT / 'tools/run_benchmark_episode_v054.py'), *args]
        result, mode = host.route(canonical, kind='generation', overlay_ref=ref,
                                 handoff_ref=handoff, handoff_revision=revision)
        self.assertEqual(mode, 'canonical')
        self.assertEqual(result[-4:], args)
        self.assertIn('--host-revision', result)
        self.assertIn('/sealed/pool.json', result)
        kernel = ['/usr/bin/env', 'PYTHONPATH=' + str(overlay.KERNEL / 'src') + ':' + str(overlay.KERNEL),
                  str(host.base.HOST_PYTHON), str(overlay.ENTRIES['kernel']), *args]
        result, mode = host.route(kernel, kind='generation', overlay_ref=ref,
                                 handoff_ref=handoff, handoff_revision=revision)
        self.assertEqual(mode, 'kernel')
        self.assertEqual(result[:3], kernel[:3])
        self.assertEqual(result[-4:], args)
        self.assertEqual(host.route(kernel, kind='score', overlay_ref=ref,
            handoff_ref=handoff, handoff_revision=revision), (kernel, None))
        with self.assertRaisesRegex(ValueError, 'Unrecognized'):
            host.route(['wrong-source'], kind='generation', overlay_ref=ref,
                       handoff_ref=handoff, handoff_revision=revision)

    def test_parent_and_child_hooks_preserve_spec(self):
        # Construction only: Popen is replaced and original watchdog never runs.
        from types import SimpleNamespace
        module = SimpleNamespace(stop_owned=lambda scope: {'quiet': True})
        value = {'sources': {'canonical': {'supervision': {'path': '/original/supervision.py'}}}}
        ref = {'path': '/sealed/overlay.json', 'sha256': 'a' * 64}
        with (patch.object(overlay, 'validate', return_value=value),
              patch.object(overlay, 'original_module', return_value=module),
              patch.dict(sys.modules, {k: v for k, v in sys.modules.items()
                                       if k not in {'proworksim.software_benchmark_runner_v054',
                                                    'proworksim.software_benchmark_episode_v054'}}, clear=True),
              patch.object(overlay.subprocess, 'Popen') as spawn,
              tempfile.TemporaryDirectory() as directory):
            overlay.install_parent(ref, 'canonical')
            spec = {'claim_id': 'a' * 32, 'hard_at': 123.0, 'scopes': [SCOPE]}
            module.start_watchdog(spec, directory)
            self.assertEqual(json.loads((Path(directory) / 'watchdog-spec.json').read_text()), spec)
            argv = spawn.call_args.args[0]
            self.assertEqual(argv[2:4], [str(overlay.TOOL), 'watch'])
            self.assertIn('--sha256', argv)
            self.assertTrue(module.stop_owned(SCOPE)['quiet'])
            spawn.call_args.kwargs['stderr'].close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        overlay.write_new(args.output, {'passed': result.wasSuccessful(), 'controls': result.testsRun,
            'errors': len(result.errors), 'failures': len(result.failures),
            'model_calls': 0, 'services_mutated': False, 'real_subprocesses_started': 0,
            'sources': [overlay.reference(x) for x in (overlay.TOOL, overlay.ENTRY, overlay.HOST, __file__)]})
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
