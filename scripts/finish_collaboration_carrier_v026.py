"""Run the existing bounded supervisor once, then persist a verified end report.

Invoke this module from the frozen checkout with the frozen interpreter and
plan. It changes no GPU admission, queue deadline, worker cap or recovery rule;
it never starts a successor and does not commit or push repository changes.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import signal

from proworksim.storage import atomic_write, json_bytes, read_json
from scripts import report_collaboration_carrier_v026 as reporting
from scripts import run_collaboration_carrier_v026 as supervisor

VERSION = 'reciprocal-carrier-finish-wrapper-v0.26'


def _error(error):
    return {'type': type(error).__name__, 'message': str(error)}


def _supervisor_observation(root):
    """Diagnostic snapshot only: it cannot establish a validated terminal report."""
    try:
        value = read_json(root / 'supervisor.json')
    except (OSError, ValueError) as error:
        return {'available': False, 'read_error': _error(error)}
    if not isinstance(value, dict):
        return {'available': False, 'read_error': {'type': 'InvalidSupervisorSnapshot',
                                                  'message': 'Supervisor snapshot is not an object'}}
    return {'available': True, **{key: value[key] for key in ('status', 'started_at', 'ended_at', 'error') if key in value}}


def _unavailable_markdown(report):
    wrapper = report['finish_wrapper']
    return '\n'.join([
        '# v0.26 C1：终态报告未能验证', '',
        '尚未取得可验证的终态实验报告。本文件是归档故障记录，不代表实验完成，也不提供工作分数或学习结论。', '',
        f"运行目录：`{report['run_root']}`。", '',
        '监督器原文件及 worker 状态未由本封装修改；没有重试、自动恢复或新增实验。', '',
        '观察到的监督器状态与原错误：', '',
        '```json', json.dumps({'observed_supervisor': report['observed_supervisor'],
                              'supervisor_error': wrapper['supervisor_error'],
                              'report_error': wrapper['report_error']}, ensure_ascii=False, indent=2), '```', '',
        '状态可能尚未终止，也可能已经停止但证据验证失败；以原运行目录的受管记录为准。', '',
    ])


def finish(plan, run_root, output_json, output_md):
    """One supervisor call, one terminal-only report attempt, then durable files."""
    plan, root = Path(plan).resolve(), Path(run_root).resolve()
    output_json, output_md = Path(output_json).resolve(), Path(output_md).resolve()
    if output_json == output_md or plan in {output_json, output_md}:
        raise ValueError('Report destinations must differ from one another and the frozen plan')
    if root / 'supervisor.json' in {output_json, output_md}:
        raise ValueError('Report destination must not overwrite the original supervisor state')
    wrapper = {'version': VERSION, 'started_at_utc': datetime.now(timezone.utc).isoformat(),
               'source_directory': str(Path(__file__).resolve().parents[1]), 'plan_path': str(plan),
               'supervisor_invocations': 1, 'automatic_recovery': False, 'automatic_successors': [],
               'supervisor_return_status': None, 'supervisor_error': None, 'report_error': None,
               'terminal_report_verified': False}
    try:
        result = supervisor.run(plan, root)
        if isinstance(result, dict):
            wrapper['supervisor_return_status'] = result.get('status')
            wrapper['supervisor_error'] = result.get('error')
    except BaseException as error:
        # The existing supervisor owns cleanup and terminal transitions. An
        # exception before/after its managed section never licenses fabrication
        # of a terminal state, retry, or intervention in other GPU processes.
        wrapper['supervisor_error'] = _error(error)
    try:
        report = reporting.load_run(root, require_terminal=True)
        if report.get('terminal') is not True:
            raise ValueError('Terminal-only report reader did not verify a terminal archive')
        wrapper['terminal_report_verified'] = True
        report['finish_wrapper'] = wrapper
        rendered = reporting.markdown(report)
    except Exception as error:
        wrapper['terminal_report_verified'] = False
        wrapper['report_error'] = _error(error)
        report = {'version': VERSION, 'run_root': str(root), 'run_status': 'terminal_report_unavailable',
                  'terminal': False, 'finish_wrapper': wrapper,
                  'observed_supervisor': _supervisor_observation(root),
                  'scope': 'Archive failure only; no invented episode status, reward, completion or model execution.'}
        rendered = _unavailable_markdown(report)
    wrapper['ended_at_utc'] = datetime.now(timezone.utc).isoformat()
    if wrapper['terminal_report_verified']:
        rendered += '\n终态归档由一次性封装调用原监督器及原只读报告器生成；无自动恢复或后继。\n'
        if wrapper['supervisor_error'] is not None:
            rendered += '\n监督器原错误（完整终态结果仍以报告正文和原记录为准）：\n\n```json\n'
            rendered += json.dumps(wrapper['supervisor_error'], ensure_ascii=False, indent=2) + '\n```\n'
    # Both files are atomically replaced only after rendering has succeeded.
    atomic_write(output_json, json_bytes(report))
    atomic_write(output_md, rendered.encode('utf-8'))
    return report


def exit_code(report):
    if report['finish_wrapper']['terminal_report_verified'] is not True:
        return 3
    if report.get('run_status') == 'complete' and report['finish_wrapper']['supervisor_error'] is None:
        return 0
    return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--output-json', type=Path, required=True)
    parser.add_argument('--output-md', type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    report = finish(args.plan, args.run_root, args.output_json, args.output_md)
    print(json.dumps({'status': report['run_status'], 'terminal': report['terminal'],
                      'terminal_report_verified': report['finish_wrapper']['terminal_report_verified'],
                      'json': str(args.output_json.resolve()), 'markdown': str(args.output_md.resolve())}, ensure_ascii=False))
    return exit_code(report)


if __name__ == '__main__':
    raise SystemExit(main())
