"""Reuse the sealed r1 cache collector unchanged, with a 10-second idle cadence."""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
VERSION = 'v055-cache-watcher-cadence-r2'
WAIT_SECONDS = 10
BATCH_SIZE = 4
COLLECTOR_SHA = 'add7b61e57b7518f130eda86294b225a30dadacec70ad549dd6ed94649e300de'


def reference(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {'path':str(path),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}


def run_loop(collector, *, cycle=None, sleep=None):
    cycle = collector.cycle if cycle is None else cycle
    sleep = time.sleep if sleep is None else sleep
    while True:
        cycle(BATCH_SIZE, None, COLLECTOR_SHA)
        sleep(WAIT_SECONDS)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seal',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    args=parser.parse_args()
    if reference(args.seal)['sha256'] != args.sha256:
        raise ValueError('Watcher revision seal mismatch')
    seal=json.loads(args.seal.read_bytes())
    if (seal['version'] != VERSION or seal['cycle_wait_seconds'] != WAIT_SECONDS
            or seal['maximum_helper_attempts_per_cycle'] != BATCH_SIZE
            or seal['source'] != reference(__file__) or os.geteuid() != 1021):
        raise ValueError('Only the sealed project-user cadence wrapper is admitted')
    source=ROOT/'tools/reclaim_benchmark_cache_v055_r1.py'
    if seal['collector'] != reference(source) or seal['collector']['sha256'] != COLLECTOR_SHA:
        raise ValueError('The authorized r1 collector and privileged helper must be unchanged')
    if seal['original_policy'] != reference(seal['original_policy']['path']):
        raise ValueError('The original collector policy evidence changed')
    spec=importlib.util.spec_from_file_location('v055_original_cache_collector_r1',source)
    collector=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    if collector.ROOT != collector.EXPECTED_ROOT or collector.ROOT != ROOT:
        raise ValueError('Collector workspace changed')
    collector.OUTPUT.mkdir(exist_ok=True)
    # Same singleton lock and same finite privileged helper as r1. No child concurrency.
    with (collector.OUTPUT/'collector.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        run_loop(collector)


if __name__=='__main__':
    main()
