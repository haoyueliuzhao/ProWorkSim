"""Independent offline scorer execution r6; official grading rules unchanged.

Admit exactly four visible CPUs, one pinned requests build-duplicate inventory,
and an optional lossless UTF8 patch transport. Original candidate locks, images,
requests and scorer receipts are never rewritten. Supports v054 and v055.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re

from . import software_benchmark_scorer_v054 as base
from . import software_benchmark_scorer_v055 as deep
from . import software_benchmark_scorer_r5_v054 as qwen
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_baseline_v054 import validate_mapping

ROOT = Path(__file__).resolve().parents[2]
VERSION = 'software-benchmark-independent-scorer-r6'
REVISION = 'v055-exception-scoring-execution-r6'
LIMITS = {'network_mode': 'none', 'nano_cpus': 4000000000, 'memory_bytes': 17179869184,
    'pids_limit': 16384, 'timeout_seconds': 1800}
AUDIT = ROOT / 'artifacts/software-benchmark-v055/exception-reconciliation-r1/requests-official-untracked-build-audit.json'
REVISION_PATH = ROOT / 'runs/software-benchmark-v055/exception-reconciliation-r1/scorer-r6/revision.json'


def load(ref):
    return json.loads(checked(ref).read_bytes())


def cpus(text):
    if not isinstance(text, str) or re.fullmatch(r'\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*', text) is None:
        raise ValueError('Explicit numeric CPU set required')
    result = []
    for block in text.split(','):
        ends = [int(x) for x in block.split('-')]
        first, last = ends[0], ends[-1]
        if last < first or last - first > 256:
            raise ValueError('Invalid bounded CPU interval')
        result.extend(range(first, last + 1))
    if len(result) != 4 or len(set(result)) != 4:
        raise ValueError('Exactly four distinct visible CPUs are required')
    return sorted(result)


def freeze_revision():
    value = {'version': REVISION, 'adapter': reference(__file__), 'original_limits': LIMITS,
        'visible_cpu_count': 4, 'untracked_build_audit': reference(AUDIT),
        'maximum_additional_attempts_per_endpoint': 1, 'model_calls': 0, 'harness_changed': False,
        'patch_transport_allowed': True, 'original_candidate_and_image_unchanged': True}
    REVISION_PATH.parent.mkdir(parents=True, exist_ok=True)
    if REVISION_PATH.exists():
        if json.loads(REVISION_PATH.read_bytes()) != value:
            raise ValueError('A different scorer execution revision is already sealed')
        return reference(REVISION_PATH)
    return write_new(REVISION_PATH, value)


def validate_request(request):
    revision = load(request['scoring_execution_revision'])
    if (revision.get('version') != REVISION or revision.get('adapter') != reference(__file__)
            or revision.get('original_limits') != LIMITS or revision.get('visible_cpu_count') != 4
            or revision.get('maximum_additional_attempts_per_endpoint') != 1
            or revision.get('model_calls') != 0 or revision.get('harness_changed') is not False
            or revision.get('original_candidate_and_image_unchanged') is not True
            or request.get('limits') != LIMITS):
        raise ValueError('Unknown independently sealed same-budget scoring execution revision')
    original = load(request['original_scoring_request'])
    extra = {'original_scoring_request', 'scoring_execution_revision', 'scoring_cpuset_cpus', 'patch_transport'}
    expected = dict(original, attempt=2, receipt_output=request['receipt_output'])
    if (original.get('attempt', 1) != 1 or request.get('attempt') != 2
            or {key: value for key, value in request.items() if key not in extra} != expected
            or request['receipt_output'] == original.get('receipt_output')
            or original.get('actor_feedback') is not False or original.get('preparation_only') is not False):
        raise ValueError('Only execution metadata, distinct pointer and first additional attempt may change')
    selected = cpus(request['scoring_cpuset_cpus'])
    if not set(selected) <= os.sched_getaffinity(0):
        raise ValueError('Requested CPUs are outside the scorer host affinity')
    parent = deep if 'condition_id' in original else qwen
    parent.check_candidate(original)
    return revision, original, parent


def selected_patch(request, original):
    old = checked(original['patch']).read_bytes()
    if not request.get('patch_transport'):
        old.decode('utf-8')
        return old, None
    receipt = load(request['patch_transport'])
    lock = load(original['native_candidate_lock'])
    exported = lock['patch_receipt']
    if (receipt.get('version') != 'v055-locked-patch-utf8-transport-r1'
            or receipt.get('original_request') != request['original_scoring_request']
            or receipt.get('original_patch') != original['patch']
            or receipt.get('original_native_lock') != original['native_candidate_lock']
            or receipt.get('candidate_reselected') is not False or receipt.get('files_excluded') != 0
            or receipt.get('new_model_calls') != 0
            or not all(receipt.get(key) is True for key in ('original_patch_round_trip_verified',
                'replacement_patch_round_trip_verified', 'utf8'))
            or any(receipt.get(key) != exported[key] for key in ('base_git_tree', 'candidate_git_tree',
                'base_tree_sha256', 'candidate_tree_sha256'))
            or receipt['base_tree_sha256'] != original['baseline_tree_sha256']
            or receipt['candidate_tree_sha256'] != original['candidate_tree_sha256']):
        raise ValueError('UTF8 transport lacks exact original request/lock/base/candidate round-trip proof')
    checked(receipt['source'])
    patch = checked(receipt['replacement_patch']).read_bytes()
    patch.decode('utf-8')
    return patch, receipt['replacement_patch']


def execution_identity(request, instance, manifest, patch, replacement):
    identity, _ = base.make_identity(instance=instance, arm=request['arm'], endpoint=request['endpoint'], patch=patch,
        candidate_tree_sha256=request['candidate_tree_sha256'], baseline_tree_sha256=request['baseline_tree_sha256'],
        dataset_reference=request['dataset'], scorer_manifest=manifest, image_record=request['image'],
        config_sha256=request['config_sha256'], limits=request['limits'], preparation_only=False, attempt=2)
    identity.update(version=VERSION, baseline_mapping=request['baseline_mapping'],
        original_scoring_request=request['original_scoring_request'], original_patch=request['patch'],
        scoring_execution_revision=request['scoring_execution_revision'],
        cpuset_cpus=request['scoring_cpuset_cpus'], visible_cpu_count=4,
        patch_transport=request.get('patch_transport'), replacement_patch=replacement)
    if 'condition_id' in request:
        identity.update(deep.condition_identity(request))
    return identity


def output_paths(request, identity):
    digest = base.sha256(base.canonical(identity))
    family = 'v055' if 'condition_id' in request else 'v054'
    condition = request.get('condition_id', request['arm'])
    run_id = f'{family}-r6-{condition}-{request["endpoint"]}-{digest[:40]}'
    root, pointer = Path(request['trusted_output_root']).resolve(), Path(request['receipt_output']).resolve()
    if (not root.is_relative_to(ROOT / ('runs/software-benchmark-' + family))
            or not pointer.is_relative_to(ROOT / 'runs/software-benchmark-v055/exception-reconciliation-r1')):
        raise ValueError('Independent r6 output or pointer escaped its experiment roots')
    return run_id, root / run_id, pointer, digest


def allowed_untracked(mapping, image_id, revision):
    audit = load(revision['untracked_build_audit'])
    expected = [{key: row[key] for key in ('path', 'bytes', 'sha256')}
                for row in mapping.get('removed_public_build_duplicates', [])]
    expected.sort(key=lambda row: row['path'])
    if (mapping.get('instance_id') != 'psf__requests-1142' or len(expected) != 65
            or audit.get('expected_count') != 65 or audit.get('matches_recorded_build_duplicates') is not True
            or audit.get('official_image') != image_id or audit.get('official_tree') != mapping['official_tree']
            or sorted(audit['files'], key=lambda row: row['path']) != expected):
        raise ValueError('Only the audited 65 official requests build duplicates may be admitted')
    for row in expected:
        path = PurePosixPath(row['path'])
        if path.is_absolute() or '..' in path.parts or not row['path'].startswith('build/'):
            raise ValueError('Untracked allowlist path escaped the fixed build directory')
    return expected


UNTRACKED_INSPECTION = '''import hashlib,json,os,stat,subprocess
prefix=['git','-c','safe.directory=/testbed','-C','/testbed']
status=subprocess.check_output(prefix+['status','--porcelain']).decode('utf-8')
tracked=subprocess.check_output(prefix+['diff','--name-only']).decode('utf-8')
index=subprocess.check_output(prefix+['diff','--cached','--name-only']).decode('utf-8')
paths=subprocess.check_output(prefix+['ls-files','--others','--exclude-standard','-z']).split(b'\\0')
rows=[]
for raw in paths:
 if not raw: continue
 name=raw.decode('utf-8')
 if not name.startswith('build/') or '..' in name.split('/') or name.startswith('/'): raise ValueError('untracked path outside build')
 path='/testbed/'+name
 info=os.lstat(path)
 if not stat.S_ISREG(info.st_mode): raise ValueError('untracked object is not a regular file')
 h=hashlib.sha256()
 with open(path,'rb') as f:
  while True:
   data=f.read(1048576)
   if not data: break
   h.update(data)
 rows.append({'path':name,'bytes':info.st_size,'sha256':h.hexdigest()})
print(json.dumps({'status':status,'tracked_diff':tracked,'index_diff':index,'files':sorted(rows,key=lambda row:row['path'])}))
'''


class ObservedContainer(base.PreparationObservedContainer):
    def start(self, *args, **kwargs):
        result = super().start(*args, **kwargs)
        path = Path(self.preparation['path'])
        evidence = json.loads(path.read_bytes())
        mapping, revision = self.preparation['mapping'], self.preparation['revision']
        if evidence['head_git_tree'] != mapping['official_tree']:
            raise ValueError('Official initial tracked Git tree differs from the frozen mapping')
        host = self.delegate.attrs['HostConfig']
        expected_cpus = cpus(self.preparation['cpuset_cpus'])
        if (cpus(host.get('CpusetCpus', '')) != expected_cpus or host.get('NanoCpus') != LIMITS['nano_cpus']
                or host.get('Memory') != LIMITS['memory_bytes'] or host.get('PidsLimit') != LIMITS['pids_limit']
                or host.get('NetworkMode') != 'none'):
            raise ValueError('Actual container resource settings differ from the r6 bound request')
        observed = self.delegate.exec_run(['/bin/bash', '-c',
            'while IFS= read -r line; do case "$line" in Cpus_allowed_list:*) printf "%s\\n" "$line";; esac; done < /proc/self/status'])
        if observed.exit_code != 0:
            raise ValueError('Container CPU affinity could not be observed')
        affinity = observed.output.decode('ascii').strip().split(':', 1)[1].strip()
        if cpus(affinity) != expected_cpus:
            raise ValueError('The actual test process boundary does not expose exactly the requested four CPUs')
        evidence.update(cpuset_cpus=host['CpusetCpus'], observed_cpu_affinity=affinity,
            scoring_execution_revision=self.preparation['revision_reference'])
        if evidence['working_tree_clean'] is not True:
            expected = allowed_untracked(mapping, self.preparation['image_id'], revision)
            observed = self.delegate.exec_run([mapping['public_python'], '-c', UNTRACKED_INSPECTION])
            if observed.exit_code != 0:
                raise ValueError('Official untracked build inventory could not be verified')
            actual = json.loads(observed.output)
            if (actual['status'] != '?? build/\n' or actual['tracked_diff'] or actual['index_diff']
                    or actual['files'] != expected):
                raise ValueError('Unexpected initial working-tree changes or changed build-duplicate bytes')
            evidence.update(untracked_build_duplicates_admitted=True, untracked_build_inventory=actual,
                untracked_build_audit=revision['untracked_build_audit'], build_files_deleted=False)
        evidence.update(dataset_base=mapping['dataset_base'], dataset_base_tree=mapping['base_tree'],
            official_setup_head=mapping['official_head'], official_setup_tree=mapping['official_tree'],
            actor_head=mapping['actor_head'], actor_tree=mapping['actor_tree'],
            mapping_sha256=self.preparation['mapping_reference']['sha256'], official_setup_mapping_verified=True)
        path.write_bytes(base.canonical(evidence))
        return result


class Containers(base.LocalContainers):
    def __init__(self, delegate, image, limits, observation):
        super().__init__(delegate, image, limits)
        self.observation = observation

    def create(self, **kwargs):
        kwargs['cpuset_cpus'] = self.observation['cpuset_cpus']
        return ObservedContainer(super().create(**kwargs), self.observation)


def score_request(request):
    revision, original, parent = validate_request(request)
    old_manifest = load(request['scorer_manifest'])
    if old_manifest != parent.installation_manifest():
        raise ValueError('The original frozen scorer installation changed')
    manifest = {'version': VERSION, 'parent_scorer_manifest': request['scorer_manifest'],
        'adapter': reference(__file__), 'execution_revision': request['scoring_execution_revision']}
    patch, replacement = selected_patch(request, original)
    instance = base.read_local_dataset(request['dataset'])[request['instance_id']]
    mapping = validate_mapping(load(request['baseline_mapping']), instance=instance, image=request['image'])
    identity = execution_identity(request, instance, manifest, patch, replacement)
    run_id, output, pointer, identity_sha = output_paths(request, identity)
    socket = Path(request['docker_socket']).resolve()
    if not socket.is_socket():
        raise ValueError('Private Docker socket is not present')
    base.install_offline_guard(socket)
    import docker
    from swebench.harness.run_evaluation import run_instance
    from swebench.harness.utils import make_test_spec
    spec = make_test_spec(instance)
    if any(spec.image_assets.values()):
        raise ValueError('External grading assets require separately pinned preparation')
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    (output / 'identity.json').write_bytes(base.canonical(identity))
    os.umask(0o077)
    os.chdir(output)
    for key in ('DOCKER_CONTEXT', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'):
        os.environ.pop(key, None)
    os.environ['DOCKER_HOST'] = 'unix://' + str(socket)
    cli = base.checked_file(request['docker_cli'])
    os.environ['PATH'] = str(cli.parent) + os.pathsep + '/usr/bin:/bin'
    spec.image = request['image']['image_id']
    prediction = {'instance_id': request['instance_id'], 'model_name_or_path': request.get('condition_id', request['arm']),
        'model_patch': patch.decode('utf-8')}
    client = docker.DockerClient(base_url=os.environ['DOCKER_HOST'], timeout=1800)
    try:
        observation = {'path': str(output / 'initial-container.json'), 'base_commit': mapping['official_head'],
            'mapping': mapping, 'mapping_reference': request['baseline_mapping'], 'image_id': spec.image,
            'revision': revision, 'revision_reference': request['scoring_execution_revision'],
            'cpuset_cpus': request['scoring_cpuset_cpus']}
        restricted = base.LocalDocker(client, spec.image, request['limits'])
        restricted.containers = Containers(client.containers, spec.image, request['limits'], observation)
        restricted.images.get(spec.image)
        result = run_instance(spec, prediction, restricted, run_id, timeout=1800, rewrite_reports=False,
            skip_patch=not patch, task_repo=None)
        report = result[1].get(instance['instance_id'], {}) if result else {}
        determinate = (result is not None and report.get('patch_successfully_applied') is True
            and not report.get('infra_failure', False) and type(report.get('resolved')) is bool)
        receipt = {'version': VERSION, 'run_id': run_id, 'identity_sha256': identity_sha,
            'status': 'official_report' if determinate else 'technical_unknown',
            'resolved': report['resolved'] if determinate else None, 'official_result': result,
            'model_calls': 0, 'actor_feedback': False, 'preparation_only': False,
            'execution_revision': request['scoring_execution_revision'], 'cpuset_cpus': request['scoring_cpuset_cpus'],
            'original_request': request['original_scoring_request'], 'patch_transport': request.get('patch_transport')}
        (output / 'receipt.json').write_bytes(base.canonical(receipt))
        with pointer.open('xb') as stream:
            stream.write(base.canonical({'receipt': reference(output / 'receipt.json'), 'identity': reference(output / 'identity.json')}))
        return receipt
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', required=True, type=Path)
    args = parser.parse_args()
    receipt = score_request(json.loads(args.request.read_bytes()))
    print(json.dumps({key: receipt[key] for key in ('run_id', 'status', 'preparation_only')}))


if __name__ == '__main__':
    main()
