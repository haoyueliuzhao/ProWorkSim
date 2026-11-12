# Frozen scoring fixture. Effective CA trust changes; repository bytes do not.
import hashlib as _hashlib
import os as _os
import ssl as _ssl

PWS_CA_VERSION = 'v203.2.1-requests2317-verification-preserving-private-CA-r3'
PWS_CA_TASK = 'psf__requests-2317'
PWS_CA_ALLOWED_PATHS = ('/data0/zhuxinrui/projects/ProWorkSim/artifacts/software-benchmark-v203-2-1/requests-ca-r3/cpu-tls/unrelated-path-not-augmented/source-cacert.pem', '/data0/zhuxinrui/projects/ProWorkSim/artifacts/software-benchmark-v203-2-1/requests-ca-r3/cpu-tls/unrelated-path-not-augmented/installed-cacert.pem')
PWS_CA_ORIGINAL_SHA256 = '6a4eeafeaf28cc7750f5f7f6ed4f84d6f08dacb8ac151412332f732647694253'
PWS_CA_COMBINED_PATH = '/data0/zhuxinrui/projects/ProWorkSim/artifacts/software-benchmark-v203-2-1/requests-ca-r3/cpu-tls/unrelated-path-not-augmented/combined-ca.pem'
PWS_CA_COMBINED_SHA256 = '4e81836de55c8c52e42f2bd19b077928b4de8ef284997a55d222e79cf334cef6'
_original_loader = _ssl.SSLContext.load_verify_locations

def _sha(path):
    with open(path, 'rb') as stream:
        return _hashlib.sha256(stream.read()).hexdigest()

def _load_verify_locations(self, cafile=None, capath=None, cadata=None):
    selected = cafile
    if cafile is not None:
        try:
            normalized = _os.path.abspath(_os.fsdecode(_os.fspath(cafile)))
        except (TypeError, ValueError):
            normalized = None
        if normalized in PWS_CA_ALLOWED_PATHS:
            for original_path in PWS_CA_ALLOWED_PATHS:
                if _sha(original_path) != PWS_CA_ORIGINAL_SHA256:
                    raise _ssl.SSLError('An allowed original scoring CA file changed; trust augmentation refused')
            if _sha(PWS_CA_COMBINED_PATH) != PWS_CA_COMBINED_SHA256:
                raise _ssl.SSLError('The frozen scoring CA bundle changed; trust augmentation refused')
            selected = PWS_CA_COMBINED_PATH
    # capath/cadata and context security settings are never rewritten.
    return _original_loader(self, cafile=selected, capath=capath, cadata=cadata)

_load_verify_locations._pws_scoring_ca_version = PWS_CA_VERSION
_load_verify_locations._pws_scoring_ca_task = PWS_CA_TASK
_load_verify_locations._pws_scoring_ca_bundle_sha256 = PWS_CA_COMBINED_SHA256
if getattr(_original_loader, '_pws_scoring_ca_version', None) is not None:
    raise RuntimeError('A second scoring CA wrapper is not allowed')
_ssl.SSLContext.load_verify_locations = _load_verify_locations
