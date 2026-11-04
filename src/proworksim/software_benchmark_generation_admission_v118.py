"""Prespecified zero-model Requests2931 public-fixture admission contract."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = 'psf__requests-2931'
VERSION = 'v118-private-localhost-public-fixture-diagnostic-r1'
HELPER = ROOT / 'tools/public_fixture_diagnostic_v118.py'
ACTOR_HELPER = '/opt/pws-runtime/public-fixture-diagnostic.py'
MANIFEST = ROOT / 'artifacts/software-benchmark-v118/public-dependencies-r1/manifest.json'


def diagnostic_descriptor():
    """Preparation only: no process, listener, container or model is started."""
    raw = MANIFEST.read_bytes()
    manifest = json.loads(raw)
    if manifest['instance_id'] != TASK or manifest['certificates_replaced'] is not True:
        raise ValueError('The new public localhost fixture must be frozen first')
    return {'version': VERSION, 'instance_id': TASK, 'diagnostic_id': 'v118-project-requests2931-public-fixture',
            'profile_manifest_sha256': hashlib.sha256(raw).hexdigest(),
            'helper_sha256': hashlib.sha256(HELPER.read_bytes()).hexdigest(),
            'helper_path': ACTOR_HELPER, 'maximum_wall_seconds': 90,
            'expected_python_major_minor': [3, 9], 'expected_pytest': '7.4.4',
            'network_scope': 'private_container_loopback_only', 'maximum_loopback_connections': 32,
            'model_calls': 0, 'hidden_material_used': False, 'official_scoring': False}


def qualification_valid(value, descriptor):
    """Only the same diagnostic/profile may qualify a future formal task."""
    return (isinstance(value, dict) and value.get('version') == VERSION
            and value.get('instance_id') == TASK and value.get('diagnostic_id') == descriptor['diagnostic_id']
            and value.get('profile_manifest_sha256') == descriptor['profile_manifest_sha256']
            and value.get('passed') is True and value.get('status') == 'qualified'
            and value.get('model_calls') == 0 and value.get('hidden_material_used') is False
            and value.get('network_scope') == descriptor['network_scope']
            and value.get('fixture_parent_binding_verified') is True
            and value.get('tests') == {'test_http_public_fixture': 'passed', 'test_https_public_fixture': 'passed'}
            and value.get('repository_CA_and_public_baseline_unchanged') is True)
