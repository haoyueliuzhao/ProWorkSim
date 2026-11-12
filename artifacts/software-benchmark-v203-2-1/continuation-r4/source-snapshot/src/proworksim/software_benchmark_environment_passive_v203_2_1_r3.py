"""Independent Requests2317 scorer trust augmentation; sealed r2 stays intact.

Legacy Session.send ignores REQUESTS_CA_BUNDLE. Map only the two measured,
unchanged Requests CA paths to their original roots plus the existing private
httpbin CA. Certificate and hostname verification remain unchanged. No actor,
repository, installed Requests file, host trust store or network is modified.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace

from . import software_benchmark_environment_passive_v203_2_1_r2 as previous
from . import software_benchmark_grading_ca_v116 as legacy_ca
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_function

VERSION = 'v203.2.1-requests2317-verification-preserving-private-CA-r3'
TASK = previous.REQUESTS_TASK
FIXTURE_ROOT = '/opt/proworksim-passive-score-ca-r3'
ORIGINAL_CA_PATHS = ('/testbed/requests/cacert.pem',
    '/opt/miniconda3/envs/testbed/lib/python3.9/site-packages/requests/cacert.pem')
PRIVATE_CA = previous.original_offline.ASSETS / 'certs/httpbin.org/cacert.pem'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def shim_source(original_sha256, combined_sha256, *, allowed_paths=ORIGINAL_CA_PATHS,
                fixture_root=FIXTURE_ROOT):
    build = clone_function(legacy_ca._shim_source, {**legacy_ca._shim_source.__globals__, 'VERSION': VERSION})
    return build(TASK, original_sha256, combined_sha256,
                 allowed_paths=allowed_paths, fixture_root=fixture_root)


def ca_environment(values):
    result = dict(row.split('=', 1) for row in values) if isinstance(values, list) else dict(values or {})
    paths = [part for part in result.get('PYTHONPATH', '').split(':') if part and part != FIXTURE_ROOT]
    result['PYTHONPATH'] = ':'.join([FIXTURE_ROOT, *paths])
    return result


def manifest():
    return {'version': VERSION, 'instance_id': TASK, 'adapter': reference(__file__),
            'unchanged_private_fixture_adapter': reference(previous.__file__),
            'loader_implementation_source': reference(legacy_ca.__file__),
            'existing_private_httpbin_CA': reference(PRIVATE_CA),
            'allowed_original_CA_paths': list(ORIGINAL_CA_PATHS), 'container_fixture_root': FIXTURE_ROOT,
            'original_CA_identity': 'measured from both paths in each pinned clean baseline before any patch',
            'original_paths_must_have_identical_bytes': True,
            'effective_trust_change': 'retain every original root and append only the existing private httpbin CA',
            'SSL_CA_loader_environment_mapping': True,
            'fully_unadapted_native_environment': False,
            'unchanged_native_SSL_loader_called_after_exact_path_and_hash_selection': True,
            'Requests_or_test_code_monkeypatch': False,
            'original_CA_files_changed': False, 'verify_mode_changed': False,
            'hostname_verification_changed': False, 'unmatched_cafile_capath_cadata_unchanged': True,
            'source_and_installed_CA_hashes_rechecked_on_every_mapped_load': True,
            'external_network': False, 'host_trust_changed': False,
            'candidate_or_gold_or_test_bytes_changed': False, 'runtime_qualified': False,
            'fresh_control_kinds': ['gold', 'empty'], 'old_r2_qualification_not_upgraded': True}


def archive_bytes(files):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for name, body in files.items():
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode, entry.uid, entry.gid, entry.mtime = len(body), 0o444, 0, 0, 0
            archive.addfile(entry, io.BytesIO(body))
    return stream.getvalue()


def _measure_source():
    return '''import base64,hashlib,json
paths=%r
values={p:open(p,'rb').read() for p in paths}
assert all(0<len(b)<2*1024*1024 for b in values.values())
assert len(set(values.values()))==1, 'Original source/installed CA differ; no inferred substitution'
body=values[paths[0]]
assert b'PRIVATE KEY' not in body
print(json.dumps({'original_sha256':hashlib.sha256(body).hexdigest(),
 'original_bytes':len(body),'original_base64':base64.b64encode(body).decode(),
 'paths_sha256':{p:hashlib.sha256(b).hexdigest() for p,b in values.items()}}))
''' % (ORIGINAL_CA_PATHS,)


def _probe_source(original_sha, combined_sha, shim_sha):
    return '''import hashlib,json,ssl,sys,sitecustomize
loader=ssl.SSLContext.load_verify_locations
assert getattr(loader,'_pws_scoring_ca_version',None)==%r
assert getattr(loader,'_pws_scoring_ca_task',None)==%r
assert getattr(loader,'_pws_scoring_ca_bundle_sha256',None)==%r
context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
context.verify_mode=ssl.CERT_REQUIRED;context.check_hostname=True
before=(int(context.verify_mode),context.check_hostname)
for path in %r: context.load_verify_locations(cafile=path)
assert (int(context.verify_mode),context.check_hostname)==before==(2,True)
paths=%r
actual={p:hashlib.sha256(open(p,'rb').read()).hexdigest() for p in paths}
assert actual==paths
print(json.dumps({'python':'.'.join(map(str,sys.version_info[:3])),
 'verify_mode':int(context.verify_mode),'check_hostname':context.check_hostname,
 'verification_settings_unchanged':True,'files_sha256':actual,'network_calls':0}))
''' % (VERSION, TASK, combined_sha, ORIGINAL_CA_PATHS,
       {**{path: original_sha for path in ORIGINAL_CA_PATHS},
        FIXTURE_ROOT + '/combined-ca.pem': combined_sha,
        FIXTURE_ROOT + '/sitecustomize.py': shim_sha})


def stage(container, preparation):
    """Only the original newly owned Requests scorer wrapper calls this after startup."""
    if preparation['mapping']['instance_id'] != TASK:
        raise ValueError('Private CA augmentation is exclusive to Requests2317 scoring')
    execute = previous.original_offline.checked_exec
    python = preparation['mapping']['public_python']
    actual_env = dict(item.split('=', 1) for item in container.attrs.get('Config', {}).get('Env', []))
    if actual_env.get('PYTHONPATH', '').split(':')[0] != FIXTURE_ROOT:
        raise ValueError('Actual scorer lacks its exclusive private CA loader path')
    # -S excludes sitecustomize while measuring the original pinned image.
    measured = json.loads(execute(container, [python, '-S', '-c', _measure_source()],
                                  timeout_note='Original source and installed Requests CA identity'))
    original = base64.b64decode(measured.pop('original_base64'), validate=True)
    if (sha(original) != measured['original_sha256'] or len(original) != measured['original_bytes']
            or measured['paths_sha256'] != {p: sha(original) for p in ORIGINAL_CA_PATHS}):
        raise ValueError('Original CA byte receipt did not match its two exact paths')
    private = checked(manifest()['existing_private_httpbin_CA']).read_bytes()
    combined = original + b'\n' + private
    shim = shim_source(sha(original), sha(combined))
    files = {'combined-ca.pem': combined, 'sitecustomize.py': shim}
    execute(container, ['mkdir', '-p', FIXTURE_ROOT], timeout_note='Private scorer CA overlay directory')
    if container.put_archive(FIXTURE_ROOT, archive_bytes(files)) is not True:
        raise ValueError('New scorer did not receive exact private CA overlay bytes')
    probe = json.loads(execute(container, [python, '-B', '-c', _probe_source(sha(original), sha(combined), sha(shim))],
                               timeout_note='Verification-preserving actual Python3 CA loader'))
    if (probe.get('python') != '3.9.20' or probe.get('verify_mode') != 2
            or probe.get('check_hostname') is not True or probe.get('verification_settings_unchanged') is not True):
        raise ValueError('Original interpreter or strict TLS settings changed')
    evidence_folder = Path(preparation['path']).parent / 'requests2317-private-ca-r3'
    evidence_folder.mkdir(exist_ok=False)
    for name, data in files.items():
        (evidence_folder / name).write_bytes(data)
    proof = {'version': VERSION, 'container_id': container.id, 'instance_id': TASK,
             'baseline_CA': measured, 'manifest': manifest(), 'actual_TLS_probe': probe,
             'combined_CA': reference(evidence_folder / 'combined-ca.pem'),
             'sitecustomize': reference(evidence_folder / 'sitecustomize.py'),
             'original_bytes_are_exact_combined_prefix': True,
             'only_existing_private_CA_appended': True, 'original_files_changed': False,
             'official_patch_test_and_score_logic_changed': False, 'network_calls': 0}
    write_new(evidence_folder / 'preflight.json', proof)
    return proof


def verify_final(container, proof, python):
    expected = proof['actual_TLS_probe']['files_sha256']
    code = "import hashlib,json;paths=" + repr(expected) + ";print(json.dumps({p:hashlib.sha256(open(p,'rb').read()).hexdigest() for p in paths}))"
    actual = json.loads(previous.original_offline.checked_exec(container, [python, '-S', '-c', code],
                                                               timeout_note='Final unchanged scorer CA and loader identity'))
    if actual != expected:
        raise ValueError('Official evaluation changed original CA or frozen loader bytes')
    return {'valid': True, 'files_sha256': actual, 'network_calls': 0}


def private_environment(policy, scope, parent_factory):
    router = previous.private_environment(policy, scope, parent_factory)
    offline = router.offline
    namespace = offline.validate_environment.__globals__
    original_manifest = offline.environment_manifest
    original_environment = namespace['fixture_environment']
    original_wrapper = offline.EnvironmentContainer

    def current_manifest():
        return {**original_manifest(), 'version': VERSION, 'adapter': reference(__file__),
                'private_CA_augmentation': manifest(), 'candidate_CA_compatibility_verified': False}

    def fixture_environment(profile, values):
        return ca_environment(original_environment(profile, values))

    class AugmentedCAContainer(original_wrapper):
        def start(self, *args, **kwargs):
            result = super().start(*args, **kwargs)
            self._r3_ca_proof = stage(self.delegate, self.preparation)
            return result
        def verify_final_CA(self):
            if not hasattr(self, '_r3_ca_proof'):
                return {'valid': False, 'reason': 'CA_preflight_did_not_complete'}
            return verify_final(self.delegate, self._r3_ca_proof, self.preparation['mapping']['public_python'])
        def _before_stop(self):
            if not hasattr(self, '_r3_final_CA'):
                try:
                    self._r3_final_CA = self.verify_final_CA()
                except Exception as error:
                    self._r3_final_CA = {'valid': False, 'error': type(error).__name__ + ': ' + str(error)}
        def stop(self, *args, **kwargs):
            self._before_stop()
            return self.delegate.stop(*args, **kwargs)
        def remove(self, *args, **kwargs):
            self._before_stop()
            return self.delegate.remove(*args, **kwargs)

    namespace.update(environment_manifest=current_manifest, fixture_environment=fixture_environment,
                     EnvironmentContainer=AugmentedCAContainer)
    offline.__dict__.update(environment_manifest=current_manifest, fixture_environment=fixture_environment,
                            EnvironmentContainer=AugmentedCAContainer)
    offline.__file__ = __file__

    def prepare():
        return scope.retain(scope.GRADING_ROOT / 'environments/bindings.json', {
            'offline': scope.retain(scope.GRADING_ROOT / 'environments/requests2317-offline-ca-r3.json', current_manifest()),
            'tls': None, 'network_resolutions': {}})
    def request_fields(task):
        if task != TASK:
            raise ValueError('Independent r3 scoring environment accepts only Requests2317')
        bindings = json.loads(checked(reference(scope.GRADING_ROOT / 'environments/bindings.json')).read_bytes())
        return {'environment_revision': bindings['offline'], 'network_resolution': None}
    def validate_request(request, task):
        expected = request_fields(task)
        if any(request.get(key) != value for key, value in expected.items()):
            raise ValueError('Independent Requests2317 CA environment reference changed')
        offline.validate_environment(expected['environment_revision'])
        return offline
    # provider retains the private routing namespace; the replacement validation
    # closure itself lives in the immutable r2 module and must not be mutated.
    route_namespace = router.provider.__globals__
    route_namespace.update(prepare=prepare, request_fields=request_fields, validate_request=validate_request)
    router.__dict__.update(prepare=prepare, request_fields=request_fields, validate_request=validate_request)
    router.__file__ = __file__
    return router


def bind_scorer_environment(scorer):
    previous.bind_scorer_environment(scorer)
    namespace = scorer.validate_request.__globals__
    prior_containers, prior_cleanup = namespace['Containers'], namespace['cleanup']
    prior_diagnostics = namespace['diagnostics']
    def diagnostic_factory(*args, **kwargs):
        evaluator, provenance = prior_diagnostics.make_repaired_run_instance(*args, **kwargs)
        private = dict(evaluator.__globals__)
        original_cleanup = private['cleanup_container']
        def measured_cleanup(client, container, logger):
            # Upstream cleanup uses Docker CLI rather than container.stop().
            # Measure while the exact returned wrapper is still alive, then
            # retain its original cleanup behavior even on a trust fault.
            if container is not None and hasattr(container, '_before_stop'):
                container._before_stop()
            return original_cleanup(client, container, logger)
        private['cleanup_container'] = measured_cleanup
        return clone_function(evaluator, private), {**provenance,
            'Requests2317_CA_measured_before_original_cleanup': True,
            'original_official_evaluator_code_unchanged': True}
    class Containers(prior_containers):
        def create(self, **options):
            if self.observation['mapping']['instance_id'] != TASK:
                raise ValueError('Independent Requests2317 scorer cannot create another task')
            result = super().create(**options)
            self.tracking['requests2317_CA_wrapper'] = result
            return result
    def cleanup(request, tracking):
        wrapper = tracking.get('requests2317_CA_wrapper')
        try:
            if wrapper is not None:
                wrapper._before_stop()
                trust = wrapper._r3_final_CA
            else:
                trust = {'valid': False, 'reason': 'no_owned_CA_wrapper'}
        except Exception as error:
            trust = {'valid': False, 'error': type(error).__name__ + ': ' + str(error)}
        # Preserve physical cleanup even if trust measurement failed. Qualification
        # explicitly rejects a false CA witness; resource removal is not hidden.
        result = prior_cleanup(request, tracking)
        result['requests2317_final_CA'] = trust
        return result
    namespace.update(Containers=Containers, cleanup=cleanup,
        diagnostics=SimpleNamespace(**{**vars(prior_diagnostics), 'make_repaired_run_instance': diagnostic_factory}))
    scorer.Containers, scorer.cleanup = Containers, cleanup
    return scorer
