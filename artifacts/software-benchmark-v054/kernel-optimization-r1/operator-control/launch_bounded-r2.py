"""Launch only the fixed synthetic kernel control, bounded to physical GPU5."""
import argparse
import base64
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
STAGE = Path('/tmp/v054-kernel-control-r1')


def query(arguments):
    return subprocess.check_output(['nvidia-smi', '--id=5', *arguments,
        '--format=csv,noheader,nounits'], text=True, timeout=10)


def own_memory(session):
    total, processes = 0, []
    for line in query(['--query-compute-apps=pid,used_memory']).splitlines():
        if not line.strip():
            continue
        raw_pid, raw_memory = (value.strip() for value in line.split(','))
        pid = int(raw_pid)
        try:
            if os.getsid(pid) != session:
                continue
        except ProcessLookupError:
            continue
        memory = int(raw_memory)
        total += memory
        processes.append({'pid': pid, 'used_mib': memory})
    return total, processes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--family', choices=['delta', 'convolution'], required=True)
    parser.add_argument('--overlay', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads((STAGE / 'plan.json').read_bytes())
    resources = plan['resources']
    args.output.mkdir(parents=True, exist_ok=False)
    observation = query(['--query-gpu=index,uuid,memory.free,memory.total,utilization.gpu,name']).strip()
    columns = [value.strip() for value in observation.split(',')]
    if columns[0] != '5' or int(columns[2]) < resources['minimum_free_mib']:
        (args.output / 'host-receipt.json').write_text(json.dumps({'status': 'capacity_not_ready',
            'observation': observation, 'model_loads': 0, 'GPU_launches': 0}, indent=2))
        return 75
    script = base64.b64encode((STAGE / 'check_kernels.py').read_bytes()).decode()
    encoded_plan = base64.b64encode((STAGE / 'plan.json').read_bytes()).decode()
    bootstrap = ('import base64,sys\nfrom pathlib import Path\n'
        "p=Path('/tmp/v054-kernel-control-r1');p.mkdir()\n"
        "(p/'plan.json').write_bytes(base64.b64decode(" + repr(encoded_plan) + '))\n'
        "sys.argv=['check_kernels.py','--plan',str(p/'plan.json'),'--output',str(p/'output'),'--family',"
        + repr(args.family) + ']\n'
        'exec(compile(base64.b64decode(' + repr(script) + "),'<sealed-kernel-control>','exec'),{'__name__':'__main__'})\n")
    cache = ROOT / ('runs/software-benchmark-v054/kernel-optimization-r1/control-cache-' + args.family)
    cache.mkdir(parents=True, exist_ok=True)
    env = ['PYTHONPATH=' + str(args.overlay) + ':' + str(ROOT / 'src') + ':' + str(ROOT),
        'USE_HUB_KERNELS=NO', 'FLA_DISABLE_TENSOR_CACHE=1', 'HF_HUB_OFFLINE=1',
        'HF_DATASETS_OFFLINE=1', 'TRANSFORMERS_OFFLINE=1', 'TRITON_CACHE_DIR=' + str(cache),
        'PYTORCH_CUDA_ALLOC_CONF=backend:native', 'OMP_NUM_THREADS=2', 'MKL_NUM_THREADS=2',
        'OPENBLAS_NUM_THREADS=2', 'MAX_JOBS=2', 'HTTP_PROXY=', 'HTTPS_PROXY=', 'ALL_PROXY=',
        'http_proxy=', 'https_proxy=', 'all_proxy=', 'NO_PROXY=*', 'no_proxy=*']
    argv = ['/bin/bash', str(ROOT / 'tools/run_ref_preparation_v054.sh'), '--write-project', '--gpu', '5',
            '/usr/bin/env', *env, str(ROOT / 'runs/v016-sdk/resident-venv/bin/python'), '-B', '-']
    start = time.monotonic()
    record = {'version': 'v054-kernel-bounded-launch-r1', 'family': args.family,
        'initial_observation': observation, 'physical_gpu': 5, 'gpu_uuid': columns[1],
        'maximum_owned_gpu_mib': resources['maximum_owned_GPU_process_mib'],
        'deadline_seconds': resources['maximum_elapsed_seconds'], 'model_loads': 0,
        'official_scoring_calls': 0, 'memory_samples': [], 'argv': argv}
    termination = None
    with (args.output / 'stdout.log').open('xb') as stdout, (args.output / 'stderr.log').open('xb') as stderr:
        child = subprocess.Popen(argv, cwd=ROOT, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                 start_new_session=True)
        record['owned_session'] = child.pid
        child.stdin.write(bootstrap.encode())
        child.stdin.close()
        try:
            while child.poll() is None:
                elapsed = time.monotonic() - start
                memory, processes = own_memory(child.pid)
                record['memory_samples'].append({'elapsed_seconds': elapsed, 'owned_gpu_mib': memory,
                                                  'processes': processes})
                if elapsed > resources['maximum_elapsed_seconds']:
                    termination = 'wall_clock_deadline'
                elif memory > resources['maximum_owned_GPU_process_mib']:
                    termination = 'owned_process_memory_limit'
                if termination:
                    break
                time.sleep(resources['host_monitor_interval_seconds'])
        except BaseException as error:
            termination = type(error).__name__ + ': ' + str(error)
        finally:
            if termination and child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
            record['returncode'] = child.wait()
    record.update(elapsed_seconds=time.monotonic() - start, termination=termination,
        peak_observed_owned_gpu_mib=max((x['owned_gpu_mib'] for x in record['memory_samples']), default=0),
        status='completed' if record['returncode'] == 0 and termination is None else 'failed')
    for line in (args.output / 'stdout.log').read_text().splitlines():
        if line.startswith('V054_KERNEL_RECEIPT '):
            (args.output / 'receipt.json').write_text(json.dumps(json.loads(line.split(' ', 1)[1]), indent=2) + '\n')
        elif line.startswith('V054_KERNEL_PROGRESS '):
            (args.output / 'last-progress.json').write_text(json.dumps(json.loads(line.split(' ', 1)[1]), indent=2) + '\n')
    (args.output / 'host-receipt.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({key: record[key] for key in ['status', 'returncode', 'elapsed_seconds',
          'peak_observed_owned_gpu_mib', 'termination']}))
    return record['returncode'] or (1 if termination else 0)


if __name__ == '__main__':
    raise SystemExit(main())
