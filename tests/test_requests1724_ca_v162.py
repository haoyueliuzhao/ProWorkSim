"""Real local SSL loading controls; no TLS network or container is started."""
import hashlib
from pathlib import Path
import ssl

import pytest
from proworksim import software_benchmark_requests1724_ca_v162 as ca


def test_exact_CA_redirection_preserves_verification_and_original_bytes(tmp_path,monkeypatch):
    public=ca.PUBLIC_CA_SOURCE.read_bytes()
    originals=[tmp_path/'source-ca.pem',tmp_path/'installed-ca.pem']
    for path in originals:path.write_bytes(public)
    combined=tmp_path/'combined-ca.pem';combined.write_bytes(public+b'\n'+public)
    source=ca.shim_source(hashlib.sha256(public).hexdigest(),hashlib.sha256(combined.read_bytes()).hexdigest(),
        allowed_paths=tuple(map(str,originals)),fixture_root=str(tmp_path))
    original_loader=ssl.SSLContext.load_verify_locations
    monkeypatch.setattr(ssl.SSLContext,'load_verify_locations',original_loader)
    namespace={};exec(compile(source,'cpu-python2-compatible-CA-shim','exec'),namespace)
    for path in originals:
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        before=context.verify_mode,context.check_hostname
        context.load_verify_locations(cafile=str(path))
        assert (context.verify_mode,context.check_hostname)==before==(ssl.CERT_REQUIRED,True)
        assert context.get_ca_certs()
        assert path.read_bytes()==public
    originals[0].write_bytes(public+b'changed')
    with pytest.raises(ssl.SSLError,match='original scoring CA file changed'):
        ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(cafile=str(originals[0]))
    originals[0].write_bytes(public);combined.write_bytes(public)
    with pytest.raises(ssl.SSLError,match='augmented scoring CA file changed'):
        ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(cafile=str(originals[0]))
