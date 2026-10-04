"""Own the fixed three-model queue, then archive only its two report files."""

import argparse
from pathlib import Path
import os
import subprocess
import sys
import time

from scripts.run_ne_v021 import write


def run(plan, run_root, report_repo, publish=False):
    source = Path(__file__).resolve().parents[1]
    state_path = run_root.parent / (run_root.name + '-finish.json')
    state = {'status': 'supervising', 'started_at': time.time(), 'run_root': str(run_root),
             'source_directory': str(source), 'report_repository': str(report_repo),
             'fixed_report_paths': ['docs/experiments/software-model-selection-v030.md',
                                    'docs/experiments/software-model-selection-v030.json']}
    write(state_path, state)
    process = subprocess.run([sys.executable, '-m', 'scripts.software_model_selection_v030', 'supervise',
                              '--plan', str(plan), '--output', str(run_root)], cwd=source, check=False)
    state['supervisor_exit_code'] = process.returncode
    write(state_path, state)
    if not (run_root / 'supervisor.json').exists():
        state.update(status='failed_before_run_archive', ended_at=time.time())
        write(state_path, state)
        return state
    result = subprocess.run([sys.executable, '-m', 'scripts.report_software_model_selection_v030',
                             '--run-root', str(run_root), '--output-dir', str(report_repo / 'docs/experiments')],
                             cwd=source, check=False)
    state.update(report_exit_code=result.returncode, status='reported' if result.returncode == 0 else 'report_failed')
    write(state_path, state)
    if publish and result.returncode == 0:
        paths = state['fixed_report_paths']
        branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=report_repo, text=True).strip()
        if branch != 'main':
            state['publish_status'] = 'not_published_repository_branch_changed'
        else:
            subprocess.run(['git', 'add', '--', *paths], cwd=report_repo, check=True)
            difference = subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--', *paths], cwd=report_repo)
            if difference.returncode == 1:
                subprocess.run(['git', 'commit', '--only', '-m', 'docs: archive bounded v0.30 model selection outcomes', '--', *paths], cwd=report_repo, check=True)
            elif difference.returncode != 0:
                raise RuntimeError('Cannot determine report change set')
            state['report_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=report_repo, text=True).strip()
            # The preceding report push established direct reachability to this
            # same configured origin. Do not depend on a vanished localhost proxy.
            push_env = {key: value for key, value in os.environ.items()
                        if key.lower() not in {'http_proxy', 'https_proxy', 'all_proxy'}}
            attempts = []
            for attempt in range(3):
                pushed = subprocess.run(['git', 'push', 'origin', 'main'], cwd=report_repo, env=push_env,
                                        text=True, capture_output=True, timeout=90)
                attempts.append({'returncode': pushed.returncode, 'stdout': pushed.stdout, 'stderr': pushed.stderr})
                if pushed.returncode == 0:
                    break
                if attempt < 2:
                    time.sleep(10)
            state.update(publish_status='pushed' if attempts[-1]['returncode'] == 0 else 'push_failed', push_attempts=attempts)
    state['ended_at'] = time.time()
    write(state_path, state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--report-repo', type=Path, required=True)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    run(args.plan.resolve(), args.run_root.resolve(), args.report_repo.resolve(), args.publish)


if __name__ == '__main__':
    main()
