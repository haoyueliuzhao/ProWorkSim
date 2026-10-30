"""Restore only pre-existing locked managed candidate artifacts, without models."""
import argparse
import json
import os

from proworksim.software_benchmark_managed_recovery_v095 import recover

if __name__ == '__main__':
    if os.geteuid() == 0:
        raise PermissionError('Offline artifact recovery uses ordinary-user files only')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(recover(args.index)))
