"""Publish only the two terminal pilot reports after all model stages have stopped."""
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
    settings = plan['terminal_archive']
    checkout = Path(settings['checkout']).resolve()
    files = [settings['json'], settings['markdown']]
    for relative in files:
        path = (checkout / relative).resolve()
        if not path.is_relative_to(checkout / 'docs/experiments') or path.exists():
            raise ValueError('Archive output must be new and within docs/experiments')
    record = {'started_at': time.time(), 'status': 'writing_reports', 'files': files,
              'experiment_source': summary['source'], 'only_two_reports_staged': True}
    write(root / 'archive-status.json', record)
    env = {**os.environ, 'CUDA_VISIBLE_DEVICES': ''}
    try:
        command = [sys.executable, '-m', 'scripts.report_credit_v024', '--run', str(root),
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
            subprocess.run(['git', 'commit', '--only', '-m', 'Archive the frozen v0.24 credit comparison outcomes and costs',
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
