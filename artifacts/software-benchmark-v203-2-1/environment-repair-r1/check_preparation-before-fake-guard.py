"""Bound create/start controls using fake containers; never contacts Docker."""
from pathlib import Path
import hashlib
import io
import json
import sys
import tarfile
from types import SimpleNamespace
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from proworksim import software_benchmark_environment_passive_v203_2_1_r2 as repair
from proworksim import software_benchmark_grading_v203_2_1_r2 as grading
from proworksim import software_benchmark_scope_v203_2_1_r2 as scope
from proworksim.software_benchmark_candidates_v054 import reference

ART = Path(__file__).parent
CONTROL = ART / 'cpu-controls'
CONTROL.mkdir(exist_ok=False)


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


scorer = grading.scorer(scope.dispatch_view(lambda *args, **kwargs: {'CPU_only': True}))
namespace = scorer.validate_request.__globals__
class Timer:
    def __init__(self, *args, **kwargs):
        self.daemon = False
    def start(self):
        pass
namespace['threading'] = SimpleNamespace(Timer=Timer)
image = 'sha256:' + 'a' * 64
made = []
class Container:
    id = 'cpu-fake-container'
    def __init__(self, options):
        self.options, self.uploaded = options, {}
        self.attrs = {'Image': image, 'Config': {'Labels': options['labels'], 'Env': [key + '=' + value for key, value in options.get('environment', {}).items()]}, 'Mounts': [],
            'HostConfig': {'NetworkMode': options['network_mode'], 'Privileged': False, 'CapAdd': options['cap_add'],
                          'CapDrop': options['cap_drop'], 'SecurityOpt': options['security_opt'],
                          'CpusetCpus': options['cpuset_cpus'], 'Memory': options['mem_limit'], 'MemorySwap': options['memswap_limit'],
                          'NanoCpus': options['nano_cpus'], 'PidsLimit': options['pids_limit'], 'IpcMode': 'private',
                          'ExtraHosts': [key + ':' + value for key, value in options.get('extra_hosts', {}).items()]}}
    def reload(self):
        pass
    def put_archive(self, target, raw):
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
            for item in archive:
                self.uploaded[target + '/' + item.name] = archive.extractfile(item).read()
        return True
    def exec_run(self, argv):
        if argv[:3] == ['mkdir', '-p', repair.WHEELHOUSE]:
            return SimpleNamespace(exit_code=0, output=b'')
        assert argv[:3] == ['/opt/miniconda3/envs/testbed/bin/python', '-B', '-c']
        data = self.uploaded[repair.WHEELHOUSE + '/' + repair.WHEEL.name]
        return SimpleNamespace(exit_code=0, output=json.dumps({'python': '3.9.20', 'wheel_sha256': hashlib.sha256(data).hexdigest()}).encode())
class Delegate:
    def create(self, **options):
        item = Container(options)
        made.append(item)
        return item


records = {}
for index, task in enumerate([repair.REQUESTS_TASK, repair.PYLINT_TASK, 'django__django-15572']):
    claim = CONTROL / ('claim-' + str(index) + '.json')
    save(claim, {'key': 'cpu-only-' + task, 'docker_name': 'cpu-not-created-' + str(index),
                 'plan': {'sha256': 'b' * 64}})
    folder = CONTROL / task
    folder.mkdir()
    observation = {'mapping': {'instance_id': task, 'official_tree': 'c' * 40,
                               'public_python': '/opt/miniconda3/envs/testbed/bin/python'},
                   'image_id': image, 'cpuset_cpus': '0', 'capacity_claim': reference(claim),
                   'path': str(folder / 'initial-container.json')}
    tracking = {'owned_container_ids': []}
    factory = scorer.Containers(Delegate(), image, observation, tracking)
    container = factory.create(image=image)
    options = made[-1].options
    assert options['network_mode'] == 'none' and options['cap_drop'] == ['ALL']
    assert options['security_opt'] == ['no-new-privileges:true']
    assert not any(options.get(name) for name in ['ports', 'volumes', 'mounts', 'devices'])
    if task == repair.REQUESTS_TASK:
        assert options['cap_add'] == ['NET_ADMIN', 'NET_BIND_SERVICE']
        assert options['extra_hosts'] == {'httpbin.org': '127.0.0.1'}
        assert options['environment']['REQUESTS_CA_BUNDLE'] == '/opt/proworksim-test-fixtures/httpbin-certs/cacert.pem'
        assert isinstance(container, scorer.environment.offline.EnvironmentContainer)
    else:
        assert options['cap_add'] == [] and not options.get('extra_hosts')
        if task == repair.PYLINT_TASK:
            assert all(options['environment'][key] == value for key, value in repair.PIP_ENVIRONMENT.items())
            parent = type(container).__bases__[0]
            original_start = parent.start
            parent.start = lambda *args, **kwargs: 'fake_started_no_Docker'
            try:
                assert container.start() == 'fake_started_no_Docker'
            finally:
                parent.start = original_start
            assert made[-1].uploaded[repair.WHEELHOUSE + '/' + repair.WHEEL.name] == repair.WHEEL.read_bytes()
        else:
            assert 'PIP_NO_INDEX' not in options.get('environment', {})
    records[task] = {'caps': options['cap_add'], 'extra_hosts': options.get('extra_hosts', {}),
                     'environment': options.get('environment', {}), 'wrapper': type(container).__name__}

with zipfile.ZipFile(repair.WHEEL) as archive:
    code = compile(archive.read('appdirs.py'), str(repair.WHEEL) + '/appdirs.py', 'exec')
    module = {'__name__': 'appdirs_cpu_control'}
    exec(code, module)
    assert module['__version__'] == '1.4.4'
    assert module['user_cache_dir']('pylint').endswith('/.cache/pylint')

prepared = json.loads((ART / 'qualification-preparation.json').read_bytes())
assert len(prepared['controls']) == 4 and len(prepared['qualifications']) == 10
assert all(json.loads(Path(ref['path']).read_bytes())['instance_id'] in repair.REPAIR_TASKS for ref in prepared['controls'])
plan = json.loads(scope.PLAN_FILE.read_bytes())
assert set(prepared['qualifications']) == set(plan['qualification_reuse_from_previous']['tasks'])
requests = scorer.environment.offline.environment_manifest()
assert list(requests['profiles']) == [repair.REQUESTS_TASK] and requests['external_network'] is False
with tarfile.open(fileobj=io.BytesIO(scorer.environment.offline.archive_assets(requests)), mode='r:') as archive:
    assert archive.extractfile('serve_httpbin.py').read() == repair.original_offline.SERVER.encode()
summary = {'passed': True, 'fake_container_creation_paths': records, 'actual_Docker_objects': 0, 'network_calls': 0,
           'new_model_calls': 0, 'host_pip_installs': 0, 'actual_private_network_runtime_not_tested': True,
           'wheel_source_code_imported_without_installation': True, 'Pylint_upload_hash_preserved': True,
           'official_pip_command_and_task_bytes_unchanged': True,
           'complete_original_httpbin_application_used': True,
           'new_control_requests': len(prepared['controls']), 'strictly_reused_original_qualification_pairs': len(prepared['qualifications']),
           'real_gold_empty_admission_still_required': sorted(repair.REPAIR_TASKS),
           'source_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in [Path(repair.__file__), Path(grading.__file__)]}}
save(ART / 'cpu-controls-summary.json', summary)
print(json.dumps({'passed': True, 'new_controls': 4, 'reused_pairs': 10, 'Docker_objects': 0}))
