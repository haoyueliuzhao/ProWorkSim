"""Release only the stopped v107 manager's exact local reservation after proof."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import time

from proworksim import software_benchmark_scope_v107 as previous
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

VERSION = 'v108-stopped-v107-manager-reservation-reconciliation-r1'
OUTPUT = previous.ROOT/'artifacts/software-benchmark-v108/physical-cleanup-r1/coordinator-release.json'


def reconcile(*, inspect_unit=None, validate_physical=None):
    previous.require_allowed('v066.run')
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Only the original ordinary-user owner may reconcile capacity')
    if OUTPUT.exists():
        proof = previous.load(reference(OUTPUT))
        if proof.get('claim') != reference(previous.CLAIM_FILE) or proof.get('released') is not True:
            raise ValueError('An existing reconciliation names another owner')
        return proof
    if validate_physical is None:
        from proworksim.software_benchmark_physical_cleanup_v108 import validate_original_reconciliations
        validate_physical = validate_original_reconciliations
    physical = validate_physical()
    if inspect_unit is None:
        def inspect_unit():
            value = subprocess.run(['systemctl', '--user', 'show', previous.API_UNIT, '--no-pager',
                '--property=ActiveState,SubState,MainPID'], env=user_manager_environment(),
                capture_output=True, text=True, timeout=15)
            if value.returncode:
                raise RuntimeError('The original user unit state could not be verified')
            return dict(line.split('=', 1) for line in value.stdout.splitlines() if '=' in line)
    observed = inspect_unit()
    if observed.get('ActiveState') != 'inactive' or observed.get('MainPID') != '0':
        raise ValueError('The original same-name coordinator must be inactive before capacity release')
    claim_ref = reference(previous.CLAIM_FILE)
    claim = previous.load(claim_ref)
    if (claim.get('spec') != {'role': 'auxiliary_coordinator', 'unit': previous.API_UNIT}
            or claim.get('lease') != str(previous.LEASE_FILE)
            or claim.get('authorization') != reference(previous.AUTH_FILE)):
        raise ValueError('Only the exact stopped v107 owner reservation can be released')
    with (previous.LEASE_FILE.parent/'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        active = list(previous.LEASE_FILE.parent.glob('active-actor-*.json'))
        active += list(previous.LEASE_FILE.parent.glob('active-grader-*.json'))
        if active:
            raise ValueError('Owned generation or grading capacity is still reserved')
        if previous.LEASE_FILE.exists():
            if previous.LEASE_FILE.read_bytes() != checked(claim_ref).read_bytes():
                raise ValueError('The original owner lease bytes changed')
            previous.LEASE_FILE.unlink()
        else:
            marker = previous.API_ROOT/'coordinator-capacity-released.json'
            if not marker.exists() or previous.load(reference(marker)) != {'claim': claim_ref, 'released': True}:
                raise ValueError('A missing old lease has no matching prior release receipt')
        release_ref = previous.retain(previous.API_ROOT/'coordinator-capacity-released.json',
                                       {'claim': claim_ref, 'released': True})
        proof = {'version': VERSION, 'unix': time.time(), 'claim': claim_ref, 'release': release_ref,
            'observed_unit': observed, 'physical_grading_reconciliation': physical,
            'released': True, 'old_results_overwritten': False, 'Docker_mutations': 0,
            'service_mutations': 0, 'model_calls': 0, 'new_resource_identities': 0}
        write_new(OUTPUT, proof)
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(reconcile(), ensure_ascii=False))
