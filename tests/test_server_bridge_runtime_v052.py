"""Finite identity contracts; no historical repository tests or model execution."""
import copy
import json

import pytest

from proworksim import server_bridge_runtime_v052 as server
from proworksim.software_bridge_sources_v052 import (
    HELPER_SHA, RUNNER_SHA, evaluation_identity, ref, runtime_binding, write_new,
)


@pytest.fixture
def declared_runtime(tmp_path, monkeypatch):
    sources = {}
    for key, name in server.SOURCE_FILENAMES:
        path = tmp_path / name
        path.write_text("# synthetic " + key)
        sources[key] = path
    backend = tmp_path / "namespace.py"
    backend.write_text("# synthetic namespace backend")
    python = tmp_path / "python"
    python.write_text("synthetic executable; never run")
    environment = tmp_path / "environment.json"
    environment.write_text('{}')
    site = tmp_path / "site-packages"
    site.mkdir()
    original = {
        "version": server.LEGACY_VERSION, "fixture_only": False,
        "runner": {"path": "/unread/frozen/runner.py", "sha256": RUNNER_SHA, "bytes": 1},
        "shell_helper": {"path": "/unread/frozen/helper.py", "sha256": HELPER_SHA, "bytes": 1},
        "python_invocation": str(python), "python_executable": ref(python),
        "original_environment": ref(environment), "python_version": "original-version",
        "pip_freeze": ["original-package==1"], "site_packages": [str(site)],
        "runtime_file_trees": {"/unread/original/tree": {"historical": "preserved"}},
        "os_library_refs": [], "target_packages_installed": False,
    }
    original_path = tmp_path / "original.json"
    write_new(original_path, original)
    monkeypatch.setattr(server, "current_sources", lambda: {key: ref(path) for key, path in sources.items()})
    monkeypatch.setattr(server, "current_host_policy", lambda: {
        "kernel": {"system": "Linux", "release": "5.15-fixture", "version": "fixture", "machine": "x86_64"},
        "filesystem_policy": {"version": "server-filesystem-policy-v1", "landlock_abi": 1,
            "filesystem_backend": "user_mount_namespace", "landlock_enforced": False,
            "backend_source": ref(backend)},
    })
    output = tmp_path / "new-runtime.json"
    receipt = server.prepare_runtime(original_runtime=original_path, output=output)
    return original_path, original, output, receipt, sources, backend


def test_new_manifest_preserves_environment_and_has_new_identity(declared_runtime):
    original_path, original, output, receipt, _, _ = declared_runtime
    runtime, runtime_ref = runtime_binding(output)
    assert json.loads(original_path.read_bytes()) == original
    assert all(runtime[key] == original[key] for key in server.ENVIRONMENT_FIELDS)
    assert receipt['new_test_executions'] == receipt['new_model_calls'] == 0
    assert receipt['old_task_resume_authorized'] is False
    assert runtime['environment_verification']['runtime_file_trees_rehashed'] is False
    task = {'bridge_runtime_ref': runtime_ref, 'cpu_python': original['python_invocation']}
    files = {'example.py': 'VALUE = 1\n'}
    old_identity = evaluation_identity(files, task)
    protocol = server.execution_protocol(runtime)
    task['bridge_execution_protocol'] = protocol
    server.require_task_protocol(task, runtime)
    new_identity = evaluation_identity(files, task)
    assert new_identity != old_identity
    for key in ('runner', 'shell_helper'):
        altered = copy.deepcopy(task)
        altered['bridge_execution_protocol']['sources'][key]['sha256'] = 'changed'
        assert evaluation_identity(files, altered) != new_identity
    altered = copy.deepcopy(task)
    altered['bridge_execution_protocol']['filesystem_policy']['backend_source']['sha256'] = 'changed'
    assert evaluation_identity(files, altered) != new_identity
    altered = copy.deepcopy(task)
    altered['bridge_execution_protocol']['kernel']['release'] = 'different-kernel'
    assert evaluation_identity(files, altered) != new_identity
    with pytest.raises(ValueError, match='own source/kernel/filesystem identity'):
        server.require_task_protocol({'bridge_runtime_ref': runtime_ref}, runtime)


@pytest.mark.parametrize('changed', ['runner', 'shell_helper', 'backend'])
def test_new_manifest_rejects_source_drift(declared_runtime, changed):
    _, _, output, _, sources, backend = declared_runtime
    path = backend if changed == 'backend' else sources[changed]
    path.write_text('# changed after manifest preparation')
    with pytest.raises(ValueError, match='source changed|policy changed'):
        runtime_binding(output)


def test_old_manifest_still_requires_frozen_hashes(declared_runtime, tmp_path):
    _, original, output, _, _, _ = declared_runtime
    old = copy.deepcopy(original)
    old['runner']['sha256'] = json.loads(output.read_bytes())['runner']['sha256']
    bad = tmp_path / 'old-version-with-new-source.json'
    write_new(bad, old)
    with pytest.raises(ValueError, match='immutable final r3'):
        runtime_binding(bad)


def test_new_manifest_rejects_changed_environment(declared_runtime):
    _, _, output, _, _, _ = declared_runtime
    runtime = json.loads(output.read_bytes())
    runtime['pip_freeze'] = ['different-package==2']
    output.write_text(json.dumps(runtime))
    with pytest.raises(ValueError, match='environment declaration changed'):
        runtime_binding(output)
