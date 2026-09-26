"""Run a fixed inventory of independent seed/credit jobs on declared GPUs.

No result-based replacement, no optimizer intervention, no unstarted failures.
"""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def write(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    source, project = args.source.resolve(), args.project.resolve()
    gpus = manifest['gpus']
    if len(gpus) != len(set(gpus)) or any(type(g) is not int or g < 0 for g in gpus):
        raise ValueError('Declare unique nonnegative physical GPU indices')
    jobs = [{**j, 'status': 'not_started'} for j in manifest['jobs']]
    running = {}
    report = {'version': 'learning-study-scheduler-v0.14', 'source': str(source),
              'manifest': manifest, 'started_at': time.time(), 'status': 'running',
              'jobs': jobs, 'scope': 'Fixed jobs and GPU inventory, no score-dependent retry or job replacement.'}
    record = args.output / 'scheduler.json'
    write(record, report)
    try:
        while running or any(j['status'] == 'not_started' for j in jobs):
            for gpu in gpus:
                if gpu in running:
                    continue
                job = next((j for j in jobs if j['status'] == 'not_started'), None)
                if job is None:
                    continue
                protocol = source / job['protocol']
                output = project / job['run']
                prefix = project / job['launch']
                prefix.parent.mkdir(parents=True, exist_ok=True)
                if output.exists() or prefix.with_suffix('.log').exists():
                    raise FileExistsError('Refuse overwriting a predeclared run: ' + job['run'])
                command = [str(project / '.venv/bin/python'), manifest['resource_launcher'], str(prefix),
                           str(project / '.train-venv/bin/python'), str(source / 'scripts/online_learning_v013.py'),
                           '--protocol', str(protocol), '--model', manifest['model'],
                           '--weight-manifest', str(project / manifest['weight_manifest']), '--output', str(output)]
                env = {**os.environ, 'CUDA_VISIBLE_DEVICES': str(gpu), 'PYTHONPATH': str(source / 'src')}
                log = (args.output / (job['name'] + '.supervisor.log')).open('x')
                process = subprocess.Popen(command, cwd=source, env=env, stdout=log,
                                           stderr=subprocess.STDOUT, start_new_session=True)
                job.update(status='running', gpu=gpu, supervisor_pid=process.pid,
                           started_at=time.time(), command=command)
                running[gpu] = process, log, job
                write(record, report)
                print(json.dumps({'event': 'launched', 'job': job['name'], 'gpu': gpu}), flush=True)
            for gpu, (process, log, job) in list(running.items()):
                if process.poll() is None:
                    continue
                log.close()
                result = project / job['run'] / 'online/report.json'
                online = json.loads(result.read_text()) if result.exists() else {}
                job.update(status='finished', ended_at=time.time(), exit_code=process.returncode,
                           online_status=online.get('status', 'no_online_report'),
                           actor_steps=online.get('actor_steps_total'), critic_steps=online.get('critic_steps_total'))
                del running[gpu]
                write(record, report)
                print(json.dumps({'event': 'finished', 'job': job['name'], 'online_status': job['online_status']}), flush=True)
            if running:
                time.sleep(2)
        report['status'] = 'complete' if all(j['online_status'] == 'complete' and j['exit_code'] == 0 for j in jobs) else 'finished_with_incomplete_jobs'
    except (KeyboardInterrupt, SystemExit):
        report['status'] = 'interrupted'
        # Only groups launched and owned by this supervisor are signalled.
        for process, _, job in running.values():
            os.killpg(process.pid, signal.SIGINT)
            job['interruption_sent_to_own_group'] = True
        raise
    except Exception as error:
        report.update(status='scheduler_error', error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        report['ended_at'] = time.time()
        write(record, report)
    return 0 if report['status'] == 'complete' else 1


if __name__ == '__main__':
    sys.exit(main())
