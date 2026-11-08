import hashlib as _hashlib
import os as _os
import ssl as _ssl
PWS_CA_VERSION = 'v162-requests1724-python2-source-installed-CA-augmentation-r1'
PWS_CA_TASK = 'psf__requests-1724'
PWS_CA_ALLOWED_PATHS = ('/testbed/requests/cacert.pem', '/opt/miniconda3/envs/testbed/lib/python2.7/site-packages/requests/cacert.pem')
PWS_CA_ORIGINAL_SHA256 = '113be89390a3358988484f3e9fa903751abc168f3f4ba9e2ee899fc1b15b8216'
PWS_CA_COMBINED_PATH = '/pws-fixtures/ca-v162/combined-ca.pem'
PWS_CA_COMBINED_SHA256 = '619a0f92708bfde76701eb034a54907083bdc09f1bacb4d99eb886e7a848ef71'
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
