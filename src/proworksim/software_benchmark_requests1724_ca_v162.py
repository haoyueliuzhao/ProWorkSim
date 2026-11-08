"""Frozen scoring-only CA augmentation compatible with the original Python2.

The task CA files and candidate bytes are never rewritten. A small sitecustomize
redirects only two exact, hash-checked CA paths to original+current trusted public
anchors. It leaves certificate requirements, hostname checks and all other SSL
arguments unchanged. No network, Docker or host configuration is touched by
preparation; staging requires a separately authorized newly owned container.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import ssl
import tarfile

from .software_benchmark_candidates_v054 import checked,reference
from .software_benchmark_environment_v141 import _retain as _retain_json

ROOT=Path(__file__).resolve().parents[2]
VERSION='v162-requests1724-python2-source-installed-CA-augmentation-r1'
TASK='psf__requests-1724'
ORIGINAL_CA='/testbed/requests/cacert.pem'
INSTALLED_CA='/opt/miniconda3/envs/testbed/lib/python2.7/site-packages/requests/cacert.pem'
ALLOWED_PATHS=(ORIGINAL_CA,INSTALLED_CA)
EXPECTED_ORIGINAL_SHA256='113be89390a3358988484f3e9fa903751abc168f3f4ba9e2ee899fc1b15b8216'
FIXTURE_ROOT='/pws-fixtures/ca-v162'
BATCH_ROOT=ROOT/'runs/software-benchmark-v162/requests1724-environment-r1'
PROFILE_FILE=BATCH_ROOT/'ca-profile.json'
ASSETS=ROOT/'artifacts/software-benchmark-v162/ca-profile-r1'
PUBLIC_CA_SOURCE=Path('/etc/ssl/certs/ca-certificates.crt')


def _sha(body):return hashlib.sha256(body).hexdigest()


def _retain(path,value):
    path=Path(path)
    if isinstance(value,bytes):
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            if path.read_bytes()!=value:raise ValueError('Frozen CA bytes changed')
        else:
            with path.open('xb') as out:out.write(value)
        return reference(path)
    return _retain_json(path,value)


def shim_source(original_sha,combined_sha,*,allowed_paths=ALLOWED_PATHS,fixture_root=FIXTURE_ROOT):
    """This source intentionally uses syntax and APIs common to Python2.7/3.x."""
    text='''import hashlib as _hashlib
import os as _os
import ssl as _ssl
PWS_CA_VERSION = %r
PWS_CA_TASK = %r
PWS_CA_ALLOWED_PATHS = %r
PWS_CA_ORIGINAL_SHA256 = %r
PWS_CA_COMBINED_PATH = %r
PWS_CA_COMBINED_SHA256 = %r
_original_loader = _ssl.SSLContext.load_verify_locations
if getattr(_original_loader, '_pws_scoring_ca_version', None) is not None:
    raise RuntimeError('A second scoring CA wrapper is not allowed')
def _sha(path):
    with open(path, 'rb') as stream:
        return _hashlib.sha256(stream.read()).hexdigest()
def _load_verify_locations(self, *args, **kwargs):
    if args and 'cafile' in kwargs:
        return _original_loader(self, *args, **kwargs)
    cafile = args[0] if args else kwargs.get('cafile')
    try:
        normalized = _os.path.abspath(cafile) if cafile is not None else None
    except (TypeError, ValueError):
        normalized = None
    forwarded_args, forwarded_kwargs = args, kwargs
    if normalized in PWS_CA_ALLOWED_PATHS:
        if _sha(normalized) != PWS_CA_ORIGINAL_SHA256:
            raise _ssl.SSLError('The exact original scoring CA file changed')
        if _sha(PWS_CA_COMBINED_PATH) != PWS_CA_COMBINED_SHA256:
            raise _ssl.SSLError('The frozen augmented scoring CA file changed')
        if args:
            forwarded_args = (PWS_CA_COMBINED_PATH,) + args[1:]
        else:
            forwarded_kwargs = dict(kwargs)
            forwarded_kwargs['cafile'] = PWS_CA_COMBINED_PATH
    before = (self.verify_mode, getattr(self, 'check_hostname', None))
    result = _original_loader(self, *forwarded_args, **forwarded_kwargs)
    if before != (self.verify_mode, getattr(self, 'check_hostname', None)):
        raise _ssl.SSLError('CA loading changed SSL verification settings')
    return result
_load_verify_locations._pws_scoring_ca_version = PWS_CA_VERSION
_load_verify_locations._pws_scoring_ca_task = PWS_CA_TASK
_load_verify_locations._pws_scoring_ca_bundle_sha256 = PWS_CA_COMBINED_SHA256
_ssl.SSLContext.load_verify_locations = _load_verify_locations
'''
    return (text%(VERSION,TASK,tuple(allowed_paths),original_sha,
                  fixture_root+'/combined-ca.pem',combined_sha)).encode()


def prepare_profile():
    old=ROOT/'runs/software-benchmark-v111/aligned-interface-r1/recovery-v116/ca-profile.json'
    old_value=json.loads(old.read_bytes())
    original_ref=old_value['tasks']['psf__requests-1766']['original_CA']
    original=checked(original_ref).read_bytes()
    observed_ref=reference(ROOT/'runs/software-benchmark-v160/requests1724-environment-r1/grading/control-psf__requests-1724-gold/official-output/initial-container.json')
    observed=json.loads(checked(observed_ref).read_bytes())
    if (observed.get('original_ca',{}).get('sha256')!=EXPECTED_ORIGINAL_SHA256
            or observed.get('original_ca',{}).get('path')!=ORIGINAL_CA
            or observed.get('working_tree_clean') is not True
            or _sha(original)!=EXPECTED_ORIGINAL_SHA256 or b'PRIVATE KEY' in original):
        raise ValueError('1724 actual original CA differs from the frozen source bytes')
    public=PUBLIC_CA_SOURCE.read_bytes()
    if not public or b'PRIVATE KEY' in public or b'BEGIN CERTIFICATE' not in public:
        raise ValueError('Only current public trusted CA certificates may be frozen')
    # Local parse only: no socket or TLS handshake.
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cadata=public.decode('ascii'))
    public_ref=_retain(ASSETS/'current-trusted-public-ca.pem',public)
    original_copy=_retain(ASSETS/'original1724-ca.pem',original)
    combined=original+b'\n'+public
    combined_ref=_retain(ASSETS/'combined-ca.pem',combined)
    shim_ref=_retain(ASSETS/'sitecustomize.py',shim_source(_sha(original),_sha(combined)))
    return _retain(PROFILE_FILE,{'version':VERSION,'instance_id':TASK,'original_CA':original_copy,
        'original_source_match':original_ref,'actual1724_CA_observation':observed_ref,
        'original_CA_sha256':EXPECTED_ORIGINAL_SHA256,'allowed_paths':list(ALLOWED_PATHS),
        'system_CA_snapshot':public_ref,'system_CA_observed_source':reference(PUBLIC_CA_SOURCE),
        'combined_CA':combined_ref,'sitecustomize':shim_ref,'container_fixture_root':FIXTURE_ROOT,
        'effective_CA_changed':True,'original_CA_files_changed':False,'original_is_exact_combined_prefix':True,
        'candidate_patch_changed':False,'official_test_patch_or_commands_changed':False,
        'certificate_verification_disabled':False,'hostname_verification_changed':False,
        'host_CA_or_other_configuration_changed':False,'network_calls':0,
        'fresh_gold_empty_controls_required':True})


def profile_manifest():
    value=json.loads(checked(reference(PROFILE_FILE)).read_bytes())
    if (value.get('version')!=VERSION or value.get('instance_id')!=TASK
            or value.get('allowed_paths')!=list(ALLOWED_PATHS)
            or value.get('original_CA_sha256')!=EXPECTED_ORIGINAL_SHA256):
        raise ValueError('Only the separately frozen1724 Python2 CA profile is accepted')
    original=checked(value['original_CA']).read_bytes();public=checked(value['system_CA_snapshot']).read_bytes()
    combined=checked(value['combined_CA']).read_bytes()
    if (_sha(original)!=EXPECTED_ORIGINAL_SHA256 or combined!=original+b'\n'+public
            or checked(value['sitecustomize']).read_bytes()!=shim_source(_sha(original),_sha(combined))):
        raise ValueError('1724 exact CA augmentation/shim bytes changed')
    return value


def fixture_environment(values):
    result=dict(x.split('=',1) for x in values) if isinstance(values,list) else dict(values or {})
    remainder=[x for x in result.get('PYTHONPATH','').split(':') if x and x!=FIXTURE_ROOT]
    result['PYTHONPATH']=':'.join([FIXTURE_ROOT,*remainder])
    return result


def _archive(profile):
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as archive:
        for name,key in [('combined-ca.pem','combined_CA'),('sitecustomize.py','sitecustomize')]:
            body=checked(profile[key]).read_bytes();info=tarfile.TarInfo(name)
            info.size,info.uid,info.gid,info.mode,info.mtime=len(body),0,0,0o444,0
            archive.addfile(info,io.BytesIO(body))
    return stream.getvalue()


def probe_source(profile):
    return '''import hashlib,json,ssl,sitecustomize
loader=ssl.SSLContext.load_verify_locations
assert getattr(loader,'_pws_scoring_ca_version',None)==%r
assert getattr(loader,'_pws_scoring_ca_task',None)==%r
assert getattr(loader,'_pws_scoring_ca_bundle_sha256',None)==%r
protocol=getattr(ssl,'PROTOCOL_TLSv1_2',ssl.PROTOCOL_SSLv23)
context=ssl.SSLContext(protocol)
context.verify_mode=ssl.CERT_REQUIRED
if hasattr(context,'check_hostname'):context.check_hostname=True
before=(context.verify_mode,getattr(context,'check_hostname',None))
context.load_verify_locations(cafile=%r)
assert (context.verify_mode,getattr(context,'check_hostname',None))==before
assert context.verify_mode==ssl.CERT_REQUIRED
print(json.dumps({'effective_CA_changed':True,'original_CA_file_unchanged':True,
 'verify_mode':int(context.verify_mode),'check_hostname':getattr(context,'check_hostname',None),
 'verification_settings_unchanged':True,'original_CA_sha256':hashlib.sha256(open(%r,'rb').read()).hexdigest(),
 'combined_CA_sha256':hashlib.sha256(open(%r,'rb').read()).hexdigest(),
 'shim_version':%r,'network_calls':0},sort_keys=True))
'''%(VERSION,TASK,profile['combined_CA']['sha256'],ORIGINAL_CA,ORIGINAL_CA,
      FIXTURE_ROOT+'/combined-ca.pem',VERSION)


def stage_owned(container, *, public_python, owned_ids):
    from .software_benchmark_requests_offline_v066 import checked_exec
    if container.id not in owned_ids:
        raise ValueError('The scoring trust augmentation requires an exact newly owned container')
    profile=profile_manifest()
    actual=dict(x.split('=',1) for x in container.attrs.get('Config',{}).get('Env',[]) if '=' in x)
    if actual.get('PYTHONPATH','').split(':')[0]!=FIXTURE_ROOT:
        raise ValueError('The actual scoring interpreter lacks the frozen shim path')
    checked_exec(container,['mkdir','-p',FIXTURE_ROOT],timeout_note='Owned scoring-only CA directory')
    if container.put_archive(FIXTURE_ROOT,_archive(profile)) is not True:
        raise ValueError('Owned1724 scoring container did not receive exact CA bytes')
    proof=json.loads(checked_exec(container,[public_python,'-B','-c',probe_source(profile)],
                                 timeout_note='Actual Python2 verification-preserving CA loader'))
    if (proof.get('original_CA_sha256')!=EXPECTED_ORIGINAL_SHA256
            or proof.get('combined_CA_sha256')!=profile['combined_CA']['sha256']
            or proof.get('verification_settings_unchanged') is not True or proof.get('verify_mode')!=2
            or proof.get('shim_version')!=VERSION or proof.get('network_calls')!=0):
        raise ValueError('Actual scoring CA loader failed its frozen integrity/TLS probe')
    return proof
