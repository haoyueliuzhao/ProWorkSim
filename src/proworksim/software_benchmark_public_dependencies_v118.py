"""Freeze v118 public localhost fixture certificates without host trust changes."""
from __future__ import annotations

import base64
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import ssl

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'artifacts/software-benchmark-v117/public-dependencies-r1'
OUTPUT = ROOT / 'artifacts/software-benchmark-v118/public-dependencies-r1'
VERSION = 'v118-public-requests-localhost-fixture-r1'
TASK = 'psf__requests-2931'
ACTOR_ROOT = '/opt/pws-runtime/public-dependencies/v118'


def reference(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def _handshake(cert, key, ca, hostname):
    """Actual OpenSSL chain/hostname validation via memory BIO, without sockets."""
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(str(cert), str(key))
    client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client.load_verify_locations(cafile=str(ca))
    si, so, ci, co = (ssl.MemoryBIO() for _ in range(4))
    left = client.wrap_bio(ci, co, server_hostname=hostname)
    right = server.wrap_bio(si, so, server_side=True)
    left_done = right_done = False
    for _ in range(32):
        if not left_done:
            try:
                left.do_handshake()
                left_done = True
            except ssl.SSLWantReadError:
                pass
        if co.pending:
            si.write(co.read())
        if not right_done:
            try:
                right.do_handshake()
                right_done = True
            except ssl.SSLWantReadError:
                pass
        if so.pending:
            ci.write(so.read())
        if left_done and right_done:
            assert client.verify_mode == ssl.CERT_REQUIRED and client.check_hostname
            return {'verified': True, 'hostname': hostname, 'protocol': left.version(),
                    'verify_mode': int(client.verify_mode), 'check_hostname': client.check_hostname,
                    'network_connections': 0, 'listeners': 0}
    raise RuntimeError('The bounded in-memory TLS handshake did not complete')


def prepare():
    """New immutable payload; CA signing key exists only in this CPU process."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    import ipaddress
    manifest_path = OUTPUT / 'manifest.json'
    if manifest_path.exists():
        return reference(manifest_path)
    if OUTPUT.exists():
        raise ValueError('Refuse to merge into a partially prepared public fixture')
    prior = json.loads((SOURCE / 'manifest.json').read_bytes())
    if prior['instance_id'] != TASK or prior['certificates_replaced'] is not False:
        raise ValueError('Expected the frozen unchanged v117 public dependency input')
    files = {}
    for name, expected in prior['files'].items():
        path = SOURCE / 'site' / name
        raw = path.read_bytes()
        if path.is_symlink() or len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
            raise ValueError('Frozen v117 payload changed: ' + name)
        files[name] = raw
    prefix = 'pytest_httpbin/certs/'
    old_leaf = x509.load_pem_x509_certificate(files[prefix+'cert.pem'])
    old_ca = x509.load_pem_x509_certificate(files[prefix+'cacert.pem'])
    old_key = serialization.load_pem_private_key(files[prefix+'key.pem'], password=None)
    def public(key):
        return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    has_ca_key = public(old_key.public_key()) == public(old_ca.public_key())
    if has_ca_key:
        raise ValueError('A CA signing key was unexpectedly present; review before changing the chosen strategy')
    if public(old_key.public_key()) != public(old_leaf.public_key()):
        raise ValueError('The legacy fixture key does not identify its leaf certificate')
    ca_key, leaf_key = (rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2))
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ProWorkSim v118 public localhost test CA')])
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    before, after = datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2036, 1, 1, tzinfo=timezone.utc)
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(before).not_valid_after(after)
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
              data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
              encipher_only=False, decipher_only=False), critical=True).sign(ca_key, hashes.SHA256()))
    leaf = (x509.CertificateBuilder().subject_name(leaf_name).issuer_name(ca_name).public_key(leaf_key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(before).not_valid_after(after)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'), x509.IPAddress(ipaddress.ip_address('127.0.0.1')),
                                                       x509.IPAddress(ipaddress.ip_address('::1'))]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    files[prefix+'cacert.pem'] = ca.public_bytes(serialization.Encoding.PEM)
    files[prefix+'cert.pem'] = leaf.public_bytes(serialization.Encoding.PEM)
    files[prefix+'key.pem'] = leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                                    serialization.NoEncryption())
    record_name = 'pytest_httpbin-0.0.7.dist-info/RECORD'
    records = list(csv.reader(io.StringIO(files[record_name].decode())))
    updated = set()
    for row in records:
        if row[0] in {prefix+'cacert.pem', prefix+'cert.pem', prefix+'key.pem'}:
            raw = files[row[0]]
            row[1:] = ['sha256='+base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('='), str(len(raw))]
            updated.add(row[0])
    if len(updated) != 3:
        raise ValueError('The wheel RECORD does not cover all three fixture certificates')
    stream = io.StringIO(newline='')
    csv.writer(stream, lineterminator='\n').writerows(records)
    files[record_name] = stream.getvalue().encode()
    OUTPUT.mkdir(parents=True)
    for name, raw in files.items():
        path = OUTPUT / 'site' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    cert_dir = OUTPUT / 'site' / prefix
    checks = [_handshake(cert_dir/'cert.pem', cert_dir/'key.pem', cert_dir/'cacert.pem', hostname)
              for hostname in ('127.0.0.1', 'localhost', '::1')]
    negatives = []
    for label, trust, hostname in [('wrong_hostname', cert_dir/'cacert.pem', 'not-localhost.invalid'),
                                    ('old_CA_cannot_trust_new_leaf', SOURCE/'site'/prefix/'cacert.pem', '127.0.0.1')]:
        try:
            _handshake(cert_dir/'cert.pem', cert_dir/'key.pem', trust, hostname)
            raise AssertionError('A negative TLS control was accepted')
        except ssl.SSLCertVerificationError as error:
            negatives.append({'kind': label, 'rejected': True, 'error': str(error)})
    changed = [name for name, raw in files.items() if hashlib.sha256(raw).hexdigest() != prior['files'][name]['sha256']]
    if set(changed) != updated | {record_name}:
        raise ValueError('A noncertificate dependency file changed')
    revision = {'scope': 'private-localhost-public-fixture-only', 'legacy_leaf_expired_at': old_leaf.not_valid_after.isoformat()+'Z',
                'bundled_CA_signing_key_available': False, 'generated_new_test_CA': True,
                'CA_signing_private_key_retained': False, 'server_key_is_test_fixture_only': True,
                'not_before': before.isoformat(), 'not_after': after.isoformat(),
                'subject_alt_names': ['localhost', '127.0.0.1', '::1'], 'signature': 'RSA2048-SHA256',
                'repository_requests_CA_changed': False, 'host_trust_store_changed': False,
                'verify_false_used': False, 'changed_files': changed,
                'certificate_files': {name: reference(OUTPUT/'site'/name) for name in sorted(updated)}}
    manifest = {**prior, 'version': VERSION, 'actor_root': ACTOR_ROOT, 'source_v117_manifest': reference(SOURCE/'manifest.json'),
                'files': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)} for name, raw in files.items()},
                'certificates_replaced': True, 'certificate_revision': revision,
                'known_limits': ['Original task interpreter Python3.9 and pytest7.4.4 stay unchanged.',
                                 'Only this private localhost fixture trust has changed; repository and host trust remain unchanged.',
                                 'A real private-container HTTP/HTTPS diagnostic is still required before first model use.']}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    control = {'version': 'v118-public-localhost-certificate-memory-BIO-controls-r1', 'passed': True,
               'manifest': reference(manifest_path), 'positive_controls': checks, 'negative_controls': negatives,
               'only_expected_four_files_changed': True, 'model_calls': 0, 'network_connections': 0,
               'listeners': 0, 'Docker_operations': 0, 'host_CA_changes': 0, 'production_python39_and_fixture_server_not_executed': True}
    folder = ROOT / 'artifacts/software-benchmark-v118/public-fixture-certificate-controls-r1'
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'summary.json').write_text(json.dumps(control, ensure_ascii=False, indent=2)+'\n')
    return reference(manifest_path)
