"""Native five-tool actor with an initially verified public-test convenience entry.

The actor still has the native terminal capability. Its public files are not an
immutable authorization boundary; PROJECT instead pins its policy in PID1.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from proworksim import software_benchmark_public_tests_v110 as public_tests
from proworksim.software_benchmark_public_dependency_runtime_v118 import validate_descriptor


def legacy_module():
    entry = Path(__file__).resolve()
    here = entry.parent
    source = (here/'project/tools/run_native_worker_docker_v066.py'
              if entry.name == 'worker.py' else here/'run_native_worker_docker_v066.py')
    spec = importlib.util.spec_from_file_location(__name__+'.original', source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_legacy = legacy_module()
IMPLEMENTATION = _legacy.IMPLEMENTATION
install_lifecycle_deadline = _legacy.install_lifecycle_deadline
_original_validate = _legacy.validate_config
_original_seal = _legacy.seal_actor
_verified = None


def validate_config(config):
    global _verified
    public = _original_validate(config)
    contract = public_tests.read_actor_contract(config)
    files = {}
    for name, key in (('public-test-library.py', 'public_test_library_sha256'),
                      ('public-test.py', 'public_test_launcher_sha256'),
                      ('public-test-dependencies.py', 'public_test_dependency_helper_sha256')):
        path = Path('/opt/pws-runtime')/name
        if path.is_symlink() or not path.is_file():
            raise ValueError('The exact public test convenience files must be installed')
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != config.get(key):
            raise ValueError('The initial public test convenience source differs from its bound bytes')
        files[name] = observed
    descriptor = config.get('public_test_dependencies')
    recorded = json.loads(Path('/pws/control/public-test-dependencies.json').read_bytes())
    if recorded != descriptor:
        raise ValueError('Public dependency descriptor differs from the admitted actor config')
    baseline_files = ({name: (Path('/testbed')/name).read_text()
                       for name in ('requirements.txt', 'test_requests.py')}
                      if descriptor is not None else None)
    dependency_profile = validate_descriptor(descriptor, instance_id=config['instance_id'],
                                             baseline_files=baseline_files)
    _verified = {'public_dependency_profile': dependency_profile, 'contract': contract, 'contract_sha256': config['public_test_contract_sha256'],
                 'public_files': files, 'initial_deployment_only': True,
                 'native_terminal_remains_available': True, 'immutable_permission_boundary': False,
                 'selection_capabilities': public_tests.capabilities(contract['entry'])}
    return public


def seal_actor(public):
    if _verified is None:
        raise ValueError('The public convenience entry must be validated before actor sealing')
    value = _original_seal(public)
    for name, expected in _verified['public_files'].items():
        if hashlib.sha256((Path('/opt/pws-runtime')/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Public entry source changed during private runtime cleanup')
    value['public_test_convenience'] = {key: item for key, item in _verified.items() if key != 'contract'}
    return value


def serve(config):
    original_emit = _legacy.native.emit
    def emit(value):
        if value.get('type') == 'ready':
            value = {**value, 'public_test_selection_revision': public_tests.VERSION,
                'public_test_contract_sha256': _verified['contract_sha256'],
                'public_test_capabilities': _verified['selection_capabilities'],
                'public_test_launcher_is_permission_boundary': False,
                'public_dependency_admission_checked': True,
                'public_dependency_profile': _verified['public_dependency_profile']}
        original_emit(value)
    _legacy.validate_config, _legacy.seal_actor = validate_config, seal_actor
    _legacy.native.emit = emit
    try:
        return _legacy.serve(config)
    finally:
        _legacy.native.emit = original_emit
        _legacy.validate_config, _legacy.seal_actor = _original_validate, _original_seal


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    config = json.loads(parser.parse_args().config.read_bytes())
    install_lifecycle_deadline(config)
    serve(config)
