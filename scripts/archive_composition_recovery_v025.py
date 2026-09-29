"""Archive only the two new R1 terminal reports; original v025 reports are immutable."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from proworksim.storage import read_json
from scripts.evaluate_work_v022 import write


def archive(root, plan_path):
    root, plan_path = Path(root).resolve(), Path(plan_path).resolve()
    plan, summary = read_json(plan_path), read_json(root / 'supervisor.json')
    if summary['status'] == 'running' or not summary.get('ended_at'):
        raise ValueError('Terminal reports require stopped model stages')
    from scripts.composition_evidence_v025 import checked
    if checked(summary['plan']).resolve() != plan_path:
        raise ValueError('Archive plan differs from the frozen R1 supervisor reference')
    settings = plan['terminal_archive']
    checkout = Path(settings['checkout']).resolve()
    files = [settings['json'], settings['markdown']]
    expected_files = ['docs/experiments/composition-pilot-v025-r1.json', 'docs/experiments/composition-pilot-v025-r1.md']
    if files != expected_files:
        raise ValueError('R1 archive may write only its separate predeclared report pair')
    original_report = Path(plan['original_report']['path']).resolve()
    for relative in files:
        path = (checkout / relative).resolve()
        if not path.is_relative_to(checkout / 'docs/experiments') or path.exists() or path in {original_report, original_report.with_suffix('.md')}:
            raise ValueError('Archive output must be new and within docs/experiments')
    record = {'started_at': time.time(), 'status': 'writing_reports', 'files': files,
              'experiment_source': summary['source'], 'only_two_new_R1_reports_staged': True, 'original_reports_overwritten': False}
    write(root / 'archive-status.json', record)
    env = {**os.environ, 'CUDA_VISIBLE_DEVICES': ''}
    try:
        command = [sys.executable, '-m', 'scripts.report_composition_recovery_v025', '--run', str(root),
                   '--output-json', str(checkout / files[0]), '--output-md', str(checkout / files[1]),
                   '--require-terminal']
        subprocess.run(command, env=env, check=True, timeout=300)
        record['status'] = 'reports_written'
        write(root / 'archive-status.json', record)
        if settings['git_commit_and_push']:
            branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=checkout, text=True).strip()
            if branch != 'main':
                raise ValueError('Archive will not switch or publish a different working branch')
            subprocess.run(['git', 'add', '--', *files], cwd=checkout, check=True)
            subprocess.run(['git', 'diff', '--cached', '--check', '--', *files], cwd=checkout, check=True)
            subprocess.run(['git', 'commit', '--only', '-m', 'Archive v0.25 R1 exact-window recovery, new work and cumulative costs',
                            '--', *files], cwd=checkout, check=True, timeout=60)
            record['archive_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip()
            subprocess.run(['git', 'push', 'origin', 'main'], cwd=checkout, check=True, timeout=120)
            record['status'] = 'committed_and_pushed'
    except BaseException as error:
        record.update(status='archive_failed', error={'type': type(error).__name__, 'message': str(error)})
    record['ended_at'] = time.time()
    write(root / 'archive-status.json', record)
    print(json.dumps(record), flush=True)
    return 0 if record['status'] in {'reports_written', 'committed_and_pushed'} else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(archive(args.run, args.plan))
