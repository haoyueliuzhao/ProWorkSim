"""Read preserved official failures without rerunning generation or evaluation."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'artifacts/software-benchmark-v102/deepseek-final-accounting-r1/original-panel-1000.json'
OUTPUT = ROOT / 'artifacts/software-benchmark-v103/deepseek-failures-r1'


def read(path):
    return json.loads(Path(path).read_text())


def short_error(outcome):
    error = outcome.get('response', {}).get('error', {})
    return str(error.get('message', ''))


def official_report(receipt, instance):
    report = receipt['official_result']
    if isinstance(report, list):
        report = report[1]
    return report[instance]


def public_execution_evidence(controller_path, source_reference):
    """Read the already-recorded last public test, without executing anything."""
    paths = sorted((controller_path.parent / 'public-test-rpc').glob('test-*/response.json'))
    if not paths:
        return {'available': False}
    path = paths[-1]
    value = read(path)
    execution = value.get('execution', {})
    output = value.get('groups', {}).get('public_repository_tests', {}).get('output', '')
    clean = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', output)
    django_counts = re.findall(r'Ran (\d+) tests? in ', clean)
    pytest_counts = re.findall(r'(\d+) passed', clean)
    return {
        'available': True, 'response_path': str(path),
        'response_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'passed': value.get('passed'), 'executed': execution.get('executed'),
        'same_source_reference': execution.get('source_reference') == source_reference,
        'argv': execution.get('argv'), 'returncode': execution.get('returncode'),
        'timed_out': execution.get('timed_out'), 'wall_seconds': execution.get('wall_seconds'),
        'django_reported_test_count': int(django_counts[-1]) if django_counts else None,
        'pytest_reported_pass_count': int(pytest_counts[-1]) if pytest_counts else None,
        'repository_collection_errors': value.get('repository_collection_errors'),
        'scope': 'Repository public suite before official evaluator adds its prescribed tests',
    }


def analyze(row):
    code = row['code']
    result = read(code['generation_result']['path'])
    controller_path = Path(result['controller_result']['path'])
    controller = read(controller_path)
    report = official_report(read(code['receipt']['path']), row['instance_id'])
    lock = read(code['candidate_lock']['path'])
    patch = lock['patch_receipt']
    tests = report.get('tests_status', {})
    f2p = tests.get('FAIL_TO_PASS', {})
    p2p = tests.get('PASS_TO_PASS', {})
    boundary = result.get('managed_boundary', controller.get('managed_boundary', {}))
    outcomes = boundary.get('outcomes', [])
    test_actions = [o for o in outcomes if o.get('decision', {}).get('action') == 'run_tests']
    executed = [o for o in test_actions if o.get('response', {}).get('result', {}).get('executed') is True]
    error_text = '\n'.join(short_error(o) for o in outcomes)
    action_errors = Counter(o.get('decision', {}).get('action', 'no_action') for o in outcomes
                            if o.get('response', {}).get('ok') is False)
    stops = list(boundary.get('role_stops', {}).values())
    halt = result.get('adapter_halted')
    native_status = controller.get('sdk_execution_status')
    failure = controller.get('error')
    terminal = controller.get('terminal_boundary')
    terminal_source = controller.get('project_closure', {}).get('terminal_source_reference')
    last_test_source = executed[-1]['response']['result'].get('source_reference') if executed else None
    flags = {
        'managed_sync_permission_error': ('Operation not permitted' in error_text
                                          and 'CMakeLists.txt' in error_text),
        'managed_test_channel_error': any(s in error_text for s in
                                           ('closed or failed', 'transport is closed', 'transport has failed')),
        'managed_no_test_executed': bool(test_actions) and not executed,
        'managed_no_test_requested': row['arm'] == 'PROJECT' and not test_actions,
        'managed_any_public_test_pass': any(o['response']['result'].get('passed') is True for o in executed),
        'managed_last_public_test_pass': bool(executed) and executed[-1]['response']['result'].get('passed') is True,
        'managed_last_public_test_pass_final_version': (bool(executed)
                                                       and executed[-1]['response']['result'].get('passed') is True
                                                       and last_test_source == terminal_source
                                                       and terminal_source is not None),
        'native_budget_stop_explicit': (row['arm'] == 'REF' and isinstance(terminal, dict)
                                       and terminal.get('reason') == 'episode_token_reservation_exhausted'),
    }
    native_file = controller_path.parent / 'native-rpc-transcript.json'
    native = []
    if row['arm'] == 'REF' and native_file.exists():
        transcript = read(native_file)
        if not isinstance(transcript, list):
            raise ValueError(f'Unexpected transcript: {native_file}')
        for item in transcript:
            req = item.get('request', {})
            obs = item.get('response', {}).get('observation', {})
            if req.get('tool') != 'terminal':
                continue
            command = str(req.get('action', {}).get('command', ''))
            # This identifies commands for a descriptive count, not proof of test coverage.
            test_like = any(marker in command for marker in ('pytest', 'runtests.py', 'unittest', 'tox '))
            text = '\n'.join(str(x.get('text', '')) for x in obs.get('content', []) if isinstance(x, dict))
            native.append({'test_like': test_like, 'exit_code': obs.get('exit_code'),
                           'timeout': obs.get('timeout') is True,
                           'missing_module_trace': 'ModuleNotFoundError:' in text,
                           'import_error_trace': 'ImportError:' in text,
                           'network_error_trace': any(s in text for s in ('Network is unreachable', 'Temporary failure in name resolution'))})
    ledger = result.get('ledger', {})
    patch_paths = list(dict.fromkeys(patch.get('added_paths', []) + patch.get('deleted_paths', []) + patch.get('modified_paths', [])))
    return {
        'slot_index': row['slot_index'], 'slot_id': row['slot_id'], 'instance_id': row['instance_id'],
        'arm': row['arm'], 'repo': row['repo'], 'code_resolved': False,
        'source_batch': code.get('source_batch'),
        'official': {'patch_applied': report.get('patch_successfully_applied'),
                     'infra_failure': report.get('infra_failure'),
                     'f2p_success': len(f2p.get('success', [])), 'f2p_failure': len(f2p.get('failure', [])),
                     'p2p_success': len(p2p.get('success', [])), 'p2p_failure': len(p2p.get('failure', [])),
                     'failing_tests_sample': (f2p.get('failure', []) + p2p.get('failure', []))[:8]},
        'patch_bytes': patch.get('patch', {}).get('bytes'),
        'patch_path_count': len(patch_paths),
        'patch_cache_file_count': sum('__pycache__/' in p or p.endswith(('.pyc', '.pyo')) for p in patch_paths),
        'known_tokens': ledger.get('known_actual_tokens'), 'model_attempts': ledger.get('attempts'),
        'native_status': native_status, 'adapter_halted': halt, 'controller_error': failure,
        'native_terminal_boundary': terminal,
        'terminal_source_reference': terminal_source,
        'last_public_test_source_reference': last_test_source,
        'last_passing_public_execution': (public_execution_evidence(controller_path, terminal_source)
                                          if flags['managed_last_public_test_pass'] else None),
        'role_stops': stops, 'terminal_details': boundary.get('terminal_details', {}),
        'managed_action_errors': dict(action_errors),
        'managed_test_calls': len(test_actions), 'managed_tests_executed': len(executed),
        'managed_test_errors': [short_error(o)[:450] for o in test_actions if o.get('response', {}).get('ok') is False][:4],
        'managed_submit_calls': sum(o.get('decision', {}).get('action') == 'submit_integration' for o in outcomes),
        'managed_submit_errors': [short_error(o)[:450] for o in outcomes
                                  if o.get('decision', {}).get('action') == 'submit_integration'
                                  and o.get('response', {}).get('ok') is False],
        'flags': flags,
        'native_terminal_calls': len(native),
        'native_test_like_calls': sum(x['test_like'] for x in native),
        'native_test_like_nonzero_exits': sum(x['test_like'] and isinstance(x['exit_code'], int)
                                            and x['exit_code'] != 0 for x in native),
        'native_test_like_trace_flags': {key: sum(x['test_like'] and x[key] for x in native)
                                         for key in ('timeout', 'missing_module_trace', 'import_error_trace', 'network_error_trace')},
        'evidence': {'generation': code['generation_result'], 'score_receipt': code['receipt'],
                     'candidate_lock': code['candidate_lock'], 'controller_result': str(controller_path)},
    }


def summarize(rows, panel, arm):
    chosen = [r for r in rows if r['arm'] == arm]
    outcome_counts = Counter()
    for r in chosen:
        a, b = r['official']['f2p_failure'] > 0, r['official']['p2p_failure'] > 0
        outcome_counts['both' if a and b else 'f2p_only' if a else 'p2p_only' if b else 'neither'] += 1
    return {
        'official_failed_tasks': len(chosen),
        'official_test_failure_categories': dict(outcome_counts),
        'official_infra_failure_true': sum(r['official']['infra_failure'] is True for r in chosen),
        'patch_not_applied': sum(r['official']['patch_applied'] is False for r in chosen),
        'empty_patch': sum(r['patch_bytes'] == 0 for r in chosen),
        'role_stops': dict(Counter(x for r in chosen for x in r['role_stops'])),
        'native_statuses': dict(Counter(str(r['native_status']) for r in chosen)),
        'adapter_halted': dict(Counter(json.dumps(r['adapter_halted'], sort_keys=True) for r in chosen)),
        'flags_task_counts': {k: sum(r['flags'][k] for r in chosen) for k in chosen[0]['flags']},
        'native_test_like_trace_task_counts': {k: sum(r['native_test_like_trace_flags'][k] > 0 for r in chosen)
                                               for k in chosen[0]['native_test_like_trace_flags']},
        'repository_counts': [{'repo': repo, 'failed': sum(r['repo'] == repo for r in chosen),
                               'known_scored': sum(r['arm'] == arm and r['repo'] == repo
                                                   and isinstance(r['code']['resolved'], bool) for r in panel)}
                              for repo in sorted({r['repo'] for r in chosen})],
    }


def selected_diagnostics(rows):
    """Keep three manually inspected examples separate from aggregate flags."""
    examples = []
    chosen = {
        402: ('AssertionError: Lists differ:',
              'Django 15957: public tests passed on final version, but official slicing/prefetch cases return incorrect object lists; the task behavior is not fully repaired.'),
        2972: ('Arrays are not equal',
               'scikit-learn 25747: public pytest passed on final version, but the official output-container test detects that the transformer output index is not preserved.'),
        999: ('AssertionError: Tuples differ:',
              'Django 11239: official SSL test reaches an assertion: the candidate uses command-line SSL options where the test expects PGSSL environment variables. A generation-time missing-psycopg2 trace is not the final scoring failure.'),
    }
    for row in rows:
        if row['slot_index'] not in chosen:
            continue
        needle, interpretation = chosen[row['slot_index']]
        folder = Path(row['evidence']['score_receipt']['path']).parent / 'official-output'
        paths = list(folder.glob('logs/run_evaluation/*/*/*/test_output.txt'))
        if len(paths) != 1:
            raise ValueError(f'Expected one official test log: {folder}')
        path = paths[0]
        raw = path.read_bytes()
        lines = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', raw.decode(errors='replace')).splitlines()
        locations = [i for i, line in enumerate(lines) if needle in line]
        if not locations:
            raise ValueError(f'Inspected assertion missing: {path}')
        index = locations[0]
        examples.append({
            'slot_index': row['slot_index'], 'instance_id': row['instance_id'], 'arm': row['arm'],
            'interpretation': interpretation, 'official_test_log': str(path),
            'official_test_log_sha256': hashlib.sha256(raw).hexdigest(),
            'first_matching_line_1based': index + 1,
            'assertion_excerpt': '\n'.join(lines[max(0, index - 3):index + 6]),
            'candidate_and_score_unchanged': True,
        })
    native = [r for r in rows if r['arm'] == 'REF' and r['native_status'] == 'running']
    public = [r for r in rows if r['flags']['managed_last_public_test_pass']]
    return {
        'version': 'v103-deepseek-failure-evidence-followup-r1',
        'native_running_count': len(native),
        'native_running_all_explicit_episode_budget_reservation_stop': all(
            r['flags']['native_budget_stop_explicit'] for r in native),
        'native_running_slots': [r['slot_index'] for r in native],
        'public_pass_but_official_failure_count': len(public),
        'all_public_pass_same_final_version': all(
            r['flags']['managed_last_public_test_pass_final_version'] for r in public),
        'public_suite_evidence': [
            {'slot_index': r['slot_index'], 'instance_id': r['instance_id'],
             'public_execution': r['last_passing_public_execution']}
            for r in public
        ],
        'public_suite_interpretation': (
            'All six pass on the final source version. Five Django runs execute 15824–16104 public tests; '
            'the scikit-learn run reports 26767 passed. These are full repository entrypoints, not smoke-only '
            'checks. They do not contain the evaluator-only prescribed regression tests; passing them does '
            'not certify the requested issue or hidden acceptance behavior.'),
        'representative_assertion_failures': examples,
        'limits': [
            'These three manually inspected failures establish concrete code/requirement gaps, not a semantic classification of all 134 failures.',
            'ModuleNotFoundError/ImportError/network markers in generation transcripts may come from attempted reproductions, optional dependencies, or deliberate error-handling tests; they are not sufficient to relabel official outcomes.',
            'An explicit budget stop is an execution boundary, not proof that more tokens would fix the task.',
            'Official infra_failure=false does not prove every environment is flawless; old outcomes remain unchanged.',
        ],
        'model_calls': 0, 'containers_started': 0, 'scoring_calls': 0,
    }


def main():
    panel = read(SOURCE)
    rows = [analyze(r) for r in panel if r['code']['resolved'] is False]
    by_arm = {
        arm: {r['instance_id']: r['code']['resolved'] for r in panel
              if r['arm'] == arm and isinstance(r['code']['resolved'], bool)}
        for arm in ('REF', 'PROJECT')
    }
    common = set(by_arm['REF']) & set(by_arm['PROJECT'])
    pairs = Counter((by_arm['REF'][task], by_arm['PROJECT'][task]) for task in common)
    summary = {
        'version': 'v103-deepseek-official-failure-readonly-audit-r1',
        'scope': 'Original 5M panel only; independent recovery attempts excluded',
        'source': str(SOURCE.relative_to(ROOT)),
        'model_calls': 0, 'containers_started': 0, 'scoring_calls': 0,
        'arms': {arm: summarize(rows, panel, arm) for arm in ('REF', 'PROJECT')},
        'both_arms_officially_scored_same_task_pairs': {
            'tasks': len(common), 'both_pass': pairs[(True, True)],
            'both_fail': pairs[(False, False)], 'only_REF_pass': pairs[(True, False)],
            'only_PROJECT_pass': pairs[(False, True)],
            'scope': 'Auxiliary common-known subset; original attempts only; not a full 500-task estimate',
        },
        'limitations': [
            'Flags can overlap and are observations, not exclusive causes.',
            'A passing public test does not establish coverage of official hidden requirements.',
            'Native test-like command and trace markers are diagnostic signals, not adjudicated environment failures.',
            'Existing official infra_failure=false is a grader field, not proof that every test environment is ideal.',
            'No results, final candidates, or past delivery records are changed.',
        ],
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, value in [('summary.json', summary), ('rows.json', rows),
                        ('failure-findings.json', selected_diagnostics(rows))]:
        (OUTPUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
