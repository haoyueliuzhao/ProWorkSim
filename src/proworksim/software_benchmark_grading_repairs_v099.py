"""New two-task scorer mechanism factory; authority remains the caller's scope."""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
from types import ModuleType

from . import software_benchmark_grading_repairs_v097 as probe
from . import software_benchmark_offline_flit_v099 as flit
from . import software_benchmark_test_reset_v099 as reset
from .software_benchmark_candidates_v054 import checked, reference, write_new

VERSION = 'v099-two-task-official-scoring-mechanisms-r1'


def bind_scorer(existing, instances, wheel_manifest, *, copy_to_container=None):
    instances = list(instances)
    if {row['instance_id'] for row in instances} != reset.TASKS or len(instances) != 2:
        raise ValueError('The mechanism revision requires exactly the two reviewed tasks')
    planned = json.loads(checked(wheel_manifest).read_bytes())
    if planned != flit.manifest(checked(planned['wheel'])):
        raise ValueError('Pinned offline build dependency manifest differs')
    if copy_to_container is None:
        def copy_to_container(container, source, destination):
            from swebench.harness.docker_utils import copy_to_container as official_copy
            return official_copy(container, source, destination)

    bound = probe.bind_scorer(existing)
    namespace = bound.score_request.__globals__  # Fresh private namespace from v097.
    namespace['diagnostics'] = reset.diagnostics_adapter(namespace['diagnostics'], instances)
    old_start = bound.ObservedContainer.start
    old_put_archive = bound.ObservedContainer.put_archive

    class ObservedContainer(bound.ObservedContainer):
        def start(self, *args, **kwargs):
            result = old_start(self, *args, **kwargs)
            task = self.preparation['mapping']['instance_id']
            if task == planned['instance_id']:
                actual = dict(row.split('=', 1) for row in self.delegate.attrs['Config'].get('Env', []) if '=' in row)
                if any(actual.get(key) != value for key, value in flit.PIP_ENVIRONMENT.items()):
                    raise ValueError('Created scorer lacks the exact offline pip environment')
                receipt = flit.stage_owned(self, owned_container_ids=self.v099_tracking['owned_container_ids'],
                    instance_id=task, manifest_ref=wheel_manifest, copy_to_container=copy_to_container)
                write_new(Path(self.preparation['path']).with_name('offline-build-wheel-v099.json'), receipt)
            return result

        def put_archive(self, path, data, **kwargs):
            if str(path) != str(Path(flit.TARGET).parent):
                return old_put_archive(self, path, data, **kwargs)
            if (kwargs or type(data) is not bytes
                    or self.preparation['mapping']['instance_id'] != planned['instance_id']
                    or self.delegate.id not in self.v099_tracking['owned_container_ids']):
                raise ValueError('Offline wheel archive outside the exact owned scorer')
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as source:
                members = source.getmembers()
                if (len(members) != 1 or not members[0].isfile()
                        or members[0].name != flit.WHEEL_NAME or members[0].size != flit.WHEEL_BYTES):
                    raise ValueError('Only the exact pinned offline wheel may be transferred')
                body = source.extractfile(members[0]).read()
                if hashlib.sha256(body).hexdigest() != flit.WHEEL_SHA256:
                    raise ValueError('Offline wheel transfer bytes changed')
                member = copy.copy(members[0])
            member.uid = member.gid = 0
            member.uname = member.gname = 'root'
            member.mode = 0o444
            member.pax_headers = {}
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode='w') as target:
                target.addfile(member, io.BytesIO(body))
            if self.delegate.put_archive(path, output.getvalue()) is not True:
                raise ValueError('Owned scorer rejected the exact offline wheel archive')
            return True

    parent_create = probe._bind(bound.Containers.create,
        {**bound.Containers.create.__globals__, **namespace, 'ObservedContainer': ObservedContainer})

    class Containers(bound.Containers):
        def create(self, **options):
            task = self.observation['mapping']['instance_id']
            if task not in reset.TASKS:
                raise ValueError('Scorer outside the two reviewed tasks')
            if task == planned['instance_id']:
                values = options.get('environment') or {}
                if isinstance(values, list):
                    values = dict(row.split('=', 1) for row in values)
                else:
                    values = dict(values)
                if any(key in values and values[key] != value for key, value in flit.PIP_ENVIRONMENT.items()):
                    raise ValueError('Conflicting caller pip environment')
                options['environment'] = {**values, **flit.PIP_ENVIRONMENT}
            result = parent_create(self, **options)
            result.v099_tracking = self.tracking
            return result

    inherited_manifest = bound.installation_manifest

    def installation_manifest():
        return {**inherited_manifest(), 'two_task_scoring_revision': VERSION,
            'test_reset_adapter': reference(reset.__file__), 'offline_dependency_adapter': reference(flit.__file__),
            'two_task_scorer_adapter': reference(__file__), 'offline_dependency': wheel_manifest,
            'tasks': sorted(reset.TASKS), 'official_test_patch_and_test_commands_changed': False,
            'test_reset_executor_changed': True, 'container_environment_changed': ['offline pip wheel search'],
            'runtime_qualified_by_CPU_controls': False}

    namespace.update(ObservedContainer=ObservedContainer, Containers=Containers,
                     installation_manifest=installation_manifest)
    result = ModuleType('proworksim.private_two_task_scorer_v099')
    result.__dict__.update(namespace)
    return result
