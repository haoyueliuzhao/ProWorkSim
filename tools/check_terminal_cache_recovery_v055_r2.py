"""Necessary CPU-only refusal controls for the fresh-quiescence recovery."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'tools/reclaim_terminal_cache_v055_r2.py'
spec = importlib.util.spec_from_file_location('terminal_cache_recovery_control', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def run():
    claim = 'a' * 32
    scope = {'claim_id': claim, 'unit': 'proworksim-v054-episode-' + claim + '-actor.service',
        'manager': 'system', 'invocation_id': 'b' * 32,
        'cgroup': '/proworksimv054ep' + claim + '.slice/proworksim-v054-episode-' + claim + '-actor.service',
        'main': {'pid': 12345, 'start_ticks': 456},
        'outer_launcher': {'pid': 12344, 'start_ticks': 455}}
    state = {'LoadState': 'not-found', 'InvocationID': '', 'ControlGroup': '',
        'ActiveState': 'inactive', 'MainPID': '0'}
    base = SimpleNamespace(populated=lambda _: False, process_identity=lambda _: None)
    checks = []
    module.check_scope(scope, claim)
    module.verify_scope_quiet(base, scope, state)
    checks.append('garbage_collected_unit_with_all_exact_pids_gone_is_quiet')
    def refusal(label, callback):
        try:
            callback()
        except (RuntimeError, ValueError):
            checks.append(label)
        else:
            raise AssertionError('Required refusal absent: ' + label)
    refusal('foreign_claim_refused', lambda: module.check_scope(scope, 'c' * 32))
    bad = copy.deepcopy(scope)
    bad['main']['pid'] = 1
    refusal('namespace_pid_one_refused', lambda: module.check_scope(bad, claim))
    refusal('reused_invocation_refused', lambda: module.verify_scope_quiet(base, scope, {**state, 'InvocationID': 'c' * 32}))
    refusal('active_service_refused', lambda: module.verify_scope_quiet(base, scope, {**state, 'ActiveState': 'active'}))
    refusal('populated_scope_refused', lambda: module.verify_scope_quiet(SimpleNamespace(populated=lambda _: True, process_identity=lambda _: None), scope, state))
    refusal('original_main_pid_still_live_refused', lambda: module.verify_scope_quiet(SimpleNamespace(populated=lambda _: False, process_identity=lambda pid: scope['main'] if pid == 12345 else None), scope, state))
    refusal('original_outer_launcher_still_live_refused', lambda: module.verify_scope_quiet(SimpleNamespace(populated=lambda _: False, process_identity=lambda pid: scope['outer_launcher'] if pid == 12344 else None), scope, state))
    return {'version': module.VERSION + '-CPU-control', 'passed': True, 'checks': checks,
        'model_calls': 0, 'real_deletion_calls': 0, 'service_signals': 0,
        'original_safe_deleter_retested': False, 'source': module.original().ref(path)}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
