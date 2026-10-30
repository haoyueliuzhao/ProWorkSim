import ast
import io
import json
import os
from pathlib import Path
import tarfile
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_grading_repairs_v099 as repair
from proworksim import software_benchmark_offline_flit_v099 as flit
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from test_grading_repairs_v097 import private_fixture, observation

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'artifacts/software-benchmark-v099/offline-build-dependency-r1/manifest.json'
ROWS = [row for row in json.loads((ROOT / 'artifacts/software-benchmark-v054/source/trusted-evaluation.json').read_bytes())
        if row['instance_id'] in repair.reset.TASKS]


def official_copy_function():
    path = ROOT / 'runs/software-benchmark-v054/scorer-venv/lib/python3.12/site-packages/swebench/harness/docker_utils.py'
    node = next(node for node in ast.parse(path.read_bytes()).body
                if isinstance(node, ast.FunctionDef) and node.name == 'copy_to_container')
    namespace = {'os': os, 'tarfile': tarfile, 'Path': Path, 'Container': object}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['copy_to_container']


def instance(tmp_path):
    base, old, events, initial = private_fixture(tmp_path, observation())
    bound = repair.bind_scorer(base, ROWS, reference(MANIFEST), copy_to_container=official_copy_function())
    item = object.__new__(bound.ObservedContainer)
    item.preparation = dict(old.preparation)
    item.preparation['mapping'] = {**old.preparation['mapping'], 'instance_id': 'sphinx-doc__sphinx-11510'}
    item.delegate = old.delegate
    item.delegate.id = 'owned-fixture'
    item.delegate.attrs['Config'] = {'Env': [key + '=' + value for key, value in flit.PIP_ENVIRONMENT.items()]}
    item.v099_tracking = {'owned_container_ids': ['owned-fixture']}
    copied = []
    item.delegate.put_archive = lambda path, data: copied.append((path, data)) or True
    real_probe = item.delegate.exec_run
    item.delegate.exec_run = lambda argv, **kw: (
        SimpleNamespace(exit_code=0, output=b'') if isinstance(argv, str) else real_probe(argv, **kw))
    return bound, item, copied, initial


def test_actual_start_and_original_copy_helper_preserve_wheel_bytes_and_owned_metadata(tmp_path):
    bound, item, copied, initial = instance(tmp_path)
    assert item.start() == 'started'
    assert len(copied) == 1 and copied[0][0] == '/pws-v099-build-wheels'
    with tarfile.open(fileobj=io.BytesIO(copied[0][1]), mode='r:') as archive:
        entry = archive.getmembers()[0]
        assert (entry.name, entry.uid, entry.gid, entry.mode) == (flit.WHEEL_NAME, 0, 0, 0o444)
        assert repair.hashlib.sha256(archive.extractfile(entry).read()).hexdigest() == flit.WHEEL_SHA256
    assert json.loads(initial.with_name('offline-build-wheel-v099.json').read_bytes())['container_id'] == item.delegate.id
    assert bound.diagnostics is bound._score.__globals__['diagnostics']
    assert bound._score.__globals__['Containers'] is bound.Containers


def test_missing_offline_environment_or_foreign_ownership_rejects_transfer(tmp_path):
    _, item, copied, _ = instance(tmp_path)
    item.delegate.attrs['Config']['Env'] = []
    with pytest.raises(ValueError, match='offline pip environment'):
        item.start()
    assert copied == []
    with pytest.raises(ValueError, match='exact owned scorer'):
        flit.stage_owned(SimpleNamespace(id='foreign'), owned_container_ids=['owned-fixture'],
            instance_id='sphinx-doc__sphinx-11510', manifest_ref=reference(MANIFEST),
            copy_to_container=lambda *args: copied.append(args))
    assert copied == []


def test_unplanned_archive_member_is_rejected_without_forwarding(tmp_path):
    _, item, copied, _ = instance(tmp_path)
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w') as archive:
        member = tarfile.TarInfo('other.whl')
        member.size = 1
        archive.addfile(member, io.BytesIO(b'x'))
    with pytest.raises(ValueError, match='exact pinned offline wheel'):
        item.put_archive('/pws-v099-build-wheels', data.getvalue())
    assert copied == []


def test_actual_containers_create_binds_owned_wrapper_and_offline_environment(tmp_path):
    bound, prepared, _, _ = instance(tmp_path)
    claim = write_new(tmp_path / 'claim.json', {'key': 'control-fixture',
        'plan': {'sha256': 'frozen-plan'}, 'docker_name': 'owned-cpu-fixture'})
    created = []

    def create(**options):
        created.append(options)
        prepared.delegate.attrs['Config']['Env'] = [key + '=' + value for key, value in options['environment'].items()]
        return prepared.delegate

    containers = object.__new__(bound.Containers)
    containers.observation = {**prepared.preparation, 'capacity_claim': claim}
    containers.image_id = prepared.preparation['image_id']
    containers.tracking = {'owned_container_ids': []}
    containers.delegate = SimpleNamespace(create=create)
    try:
        value = containers.create(image=containers.image_id)
        assert isinstance(value, bound.ObservedContainer)
        assert value.v099_tracking is containers.tracking
        assert created[0]['environment'] == flit.PIP_ENVIRONMENT
        assert created[0]['network_mode'] == 'none' and created[0]['cap_drop'] == ['ALL']
        assert containers.tracking['owned_container_ids'] == [prepared.delegate.id]
    finally:
        timer = containers.tracking.get('deadline_timer')
        if timer:
            timer.cancel()
            timer.join(timeout=1)
