"""New zero-model public-environment gate; old S1/TLS-only proofs never qualify."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = 'psf__requests-2931'
VERSION = 'v131-private-localhost-public-fixture-diagnostic-r1'
HELPER = ROOT/'tools/public_fixture_diagnostic_v131.py'
ACTOR_HELPER = '/opt/pws-runtime/public-fixture-diagnostic.py'
MANIFEST = ROOT/'artifacts/software-benchmark-v130/public-dependencies-r1/manifest.json'
MEMBERS = ['member_001','member_002','member_003','member_004']
TESTS = {name: 'passed' for name in ('test_http_public_fixture','test_https_public_fixture',
    'test_conflicting_post_params','test_cookie_removed_on_expire')}


def diagnostic_descriptor():
    raw = MANIFEST.read_bytes()
    manifest = json.loads(raw)
    if (manifest.get('instance_id') != TASK or manifest.get('version') != 'v130-public-requests-compatibility-r1'
            or manifest.get('public_compatibility', {}).get('exception_or_failure_suppression') is not False):
        raise ValueError('The repaired public dependency profile must be frozen first')
    return {'version': VERSION, 'instance_id': TASK, 'organization_id': 'CHIEF',
        'fixed_members': list(MEMBERS), 'diagnostic_id': 'v131-CHIEF4-requests2931-public-environment',
        'profile_manifest_sha256': hashlib.sha256(raw).hexdigest(),
        'helper_sha256': hashlib.sha256(HELPER.read_bytes()).hexdigest(),
        'observer_sha256': hashlib.sha256((ROOT/'tools/public_test_evidence_v130.py').read_bytes()).hexdigest(),
        'execution_sha256': hashlib.sha256((ROOT/'tools/public_test_execution_v130.py').read_bytes()).hexdigest(),
        'helper_path': ACTOR_HELPER, 'maximum_wall_seconds': 90,
        'expected_python_major_minor': [3,9], 'expected_pytest': '7.4.4',
        'network_scope': 'private_container_loopback_only', 'maximum_loopback_connections': 32,
        'model_calls': 0, 'hidden_material_used': False, 'official_scoring': False}


def qualification_valid(value, descriptor):
    if (not isinstance(value, dict) or not isinstance(descriptor, dict)
            or descriptor.get('version') != VERSION or descriptor.get('instance_id') != TASK
            or descriptor.get('organization_id') != 'CHIEF' or descriptor.get('fixed_members') != MEMBERS):
        return False
    expected = ('version','instance_id','diagnostic_id','profile_manifest_sha256',
                'helper_sha256','observer_sha256','execution_sha256',
                'organization_id','fixed_members','model_calls','hidden_material_used','network_scope')
    if any(value.get(key) != descriptor.get(key) for key in expected):
        return False
    counts = value.get('socket_and_process_counts', {})
    evidence = value.get('public_test_evidence', {})
    positive, empty, skipped = (evidence.get(key,{}) for key in ('positive','no_tests','all_skipped'))
    return (value.get('passed') is True and value.get('status') == 'qualified'
        and value.get('fixture_parent_binding_verified') is True and value.get('tests') == TESTS
        and value.get('repository_CA_and_public_baseline_unchanged') is True
        and value.get('new_count_semantics_verified') is True
        and value.get('actual_pytest') == descriptor['expected_pytest']
        and str(value.get('actual_python','')).startswith('3.9.')
        and value.get('pytest_returncode') == 0
        and positive.get('passed') is True and positive.get('counts',{}).get('passed') == 4
        and positive.get('counts',{}).get('tests_run') == 4
        and empty.get('passed') is False and empty.get('validation_status') == 'no_tests'
        and empty.get('counts',{}).get('collected') == 0
        and skipped.get('passed') is False and skipped.get('validation_status') == 'all_skipped_or_xfailed'
        and skipped.get('counts',{}).get('skipped') == 1
        and counts.get('nonloopback_attempts') == 0 and counts.get('child_process_attempts') == 0
        and type(counts.get('loopback_connections')) is int and 0 < counts['loopback_connections'] <= 32
        and type(counts.get('loopback_binds')) is int and 0 < counts['loopback_binds'] <= 4)


def require_qualified(value, descriptor=None):
    descriptor = diagnostic_descriptor() if descriptor is None else descriptor
    if not qualification_valid(value, descriptor):
        raise ValueError('The new public fixture/count protocol lacks its own actual zero-model actor qualification')
    return value
