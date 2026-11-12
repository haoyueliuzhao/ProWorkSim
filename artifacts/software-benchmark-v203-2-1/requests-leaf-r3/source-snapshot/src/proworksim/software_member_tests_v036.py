"""New member-script completion protocol; historical sandbox behavior is unchanged.

Normal scripts still have to return normally. Only an observed successful,
nonempty standard unittest run may account for unittest.main's own exit(0).
This is execution evidence for optional member tests, not task acceptance.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import secrets

from .software_sandbox import run_isolated
from .storage import digest

VERSION = "member-script-completion-v0.36"
MARKER = "PROWORKSIM_MEMBER_COMPLETION_V036:"

# This controller driver executes inside the unchanged isolated worker. The
# observer wraps original stdlib methods, never replaces their test behavior.
# The outer sandbox prints its original completion nonce only after this driver
# returns, so an arbitrary member exit(0) cannot complete the driver.
DRIVER = r'''
import json
import runpy
import unittest

_program_run = unittest.TestProgram.runTests
_runner_run = unittest.TextTestRunner.run
_call_method = unittest.TestCase._callTestMethod
_result_type = unittest.TestResult
_was_successful = unittest.TestResult.wasSuccessful
_programs, _active_runners, _runs = [], [], []
_program_count = 0
_qualifying_exit = None
_completion = 'not_completed'
_abrupt_exit = None

def _observed_method(case, method):
    active = _active_runners[-1] if _active_runners else None
    if active is not None:
        active['test_methods_started'] += 1
    try:
        return _call_method(case, method)
    finally:
        if active is not None:
            active['test_methods_finished'] += 1

def _observed_runner(runner, suite):
    record = {'program': _programs[-1] if _programs else None,
              'test_methods_started': 0, 'test_methods_finished': 0,
              'runner_returned': False, 'result': None}
    _runs.append(record)
    _active_runners.append(record)
    try:
        result = _runner_run(runner, suite)
        record['result'] = result
        record['runner_returned'] = True
        return result
    finally:
        _active_runners.pop()

def _run_evidence(record):
    result = record['result']
    actual_result = isinstance(result, _result_type)
    tests_run = getattr(result, 'testsRun', None) if actual_result else None
    successful = bool(_was_successful(result)) if actual_result else False
    positive_execution = (type(tests_run) is int and tests_run > 0
                          and record['test_methods_started'] > 0
                          and record['test_methods_started'] == record['test_methods_finished'])
    return {'runner_returned': record['runner_returned'],
            'actual_unittest_result': actual_result,
            'tests_run': tests_run,
            'test_methods_started': record['test_methods_started'],
            'test_methods_finished': record['test_methods_finished'],
            'successful': successful,
            'failures': len(result.failures) if actual_result else None,
            'errors': len(result.errors) if actual_result else None,
            'skipped': len(getattr(result, 'skipped', [])) if actual_result else None,
            'unexpected_successes': len(getattr(result, 'unexpectedSuccesses', [])) if actual_result else None,
            'qualifies': record['runner_returned'] and actual_result and successful and positive_execution}

def _observed_program(program):
    global _program_count, _qualifying_exit
    _program_count += 1
    _programs.append(program)
    try:
        return _program_run(program)
    except SystemExit as error:
        tail = error.__traceback__
        while tail.tb_next is not None:
            tail = tail.tb_next
        matching = [record for record in _runs
                    if record['program'] is program
                    and record['result'] is getattr(program, 'result', None)]
        if (type(error.code) is int and error.code == 0
                and tail.tb_frame.f_code is _program_run.__code__
                and len(matching) == 1 and _run_evidence(matching[0])['qualifies']):
            _qualifying_exit = error
        raise
    finally:
        _programs.pop()

unittest.TestCase._callTestMethod = _observed_method
unittest.TextTestRunner.run = _observed_runner
unittest.TestProgram.runTests = _observed_program
try:
    runpy.run_path('test_member.py', run_name='__main__')
    _completion = 'normal_script_return'
except SystemExit as error:
    _abrupt_exit = {'type': 'SystemExit', 'code': repr(error.code)}
    if error is _qualifying_exit:
        _completion = 'verified_unittest_main_exit_zero'
    else:
        _completion = 'unverified_system_exit'
        raise
except BaseException as error:
    _completion = 'script_exception'
    _abrupt_exit = {'type': type(error).__name__}
    raise
finally:
    unittest.TestCase._callTestMethod = _call_method
    unittest.TextTestRunner.run = _runner_run
    unittest.TestProgram.runTests = _program_run
    _evidence = [_run_evidence(record) for record in _runs]
    _framework_valid = (all(record['qualifies'] for record in _evidence)
                        and (not _program_count or bool(_evidence)))
    _report = {'version': 'member-script-completion-v0.36',
               'completion': _completion, 'unittest_programs_started': _program_count,
               'unittest_runs': _evidence, 'abrupt_exit': _abrupt_exit,
               'passed': _completion in ('normal_script_return', 'verified_unittest_main_exit_zero')
                         and _framework_valid}
    print(__REPORT_PREFIX__ + json.dumps(_report, sort_keys=True), flush=True)
'''


def specification():
    return {
        "version": VERSION,
        "implementation_sha256": digest(Path(__file__).read_bytes()),
        "driver_sha256": digest(DRIVER.encode()),
        "normal_script": "Must return normally through the unchanged sandbox completion marker",
        "unittest_exit_zero": "Original TestProgram.runTests exit only, with matching completed standard TextTestRunner result and at least one executed TestCase method",
        "zero_or_only_skipped_unittest_tests": "failed",
        "arbitrary_exit_zero": "failed",
        "missing_completion_evidence": "failed",
        "test_discovery": False,
        "scope": "Optional member-script execution; explicit synchronous stdlib unittest runner evidence. No task score or independent acceptance change, and no claim to certify arbitrary custom frameworks or hostile runtime mutation.",
    }


def _completion_report(execution, prefix):
    matches = [line[len(prefix):] for line in execution.get("output", "").splitlines() if line.startswith(prefix)]
    if len(matches) != 1:
        return None, "missing_or_ambiguous"
    try:
        value = json.loads(matches[0])
    except (ValueError, TypeError):
        return None, "malformed"
    if (not isinstance(value, dict) or value.get("version") != VERSION
            or type(value.get("passed")) is not bool or not isinstance(value.get("unittest_runs"), list)):
        return None, "malformed"
    return value, "recorded"


def member_test_feedback(files, *, run_root):
    """Run one optional member script with a new, explicitly bound protocol."""
    code = files.get("test_member.py", "")
    try:
        body = ast.parse(code).body
        substantive = [node for node in body if not isinstance(node, ast.Pass)
                       and not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                                and isinstance(node.value.value, str))]
    except SyntaxError:
        substantive = [True]
    if not substantive:
        return {"version": VERSION, "status": "untested", "executed": False, "passed": None,
                "reason": "No executable member test script", "test_discovery": False}
    prefix = MARKER + secrets.token_hex(24) + ":"
    driver = DRIVER.replace("__REPORT_PREFIX__", repr(prefix))
    execution = run_isolated(files, driver, run_root=run_root)
    evidence, evidence_status = _completion_report(execution, prefix)
    passed = (execution.get("driver_completed") is True and execution.get("returncode") == 0
              and evidence is not None and evidence["passed"] is True)
    executed = execution.get("executed") is True
    return {"version": VERSION, "status": ("passed" if passed else "failed") if executed else "untested",
            "executed": executed, "passed": passed if executed else None,
            "execution": execution, "completion_evidence": evidence,
            "completion_evidence_status": evidence_status,
            "scope": "Member script completion or verified nonempty standard unittest completion; not task acceptance or arbitrary test discovery",
            "test_discovery": False}
