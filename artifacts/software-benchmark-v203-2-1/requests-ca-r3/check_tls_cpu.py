"""Native TLS MemoryBIO controls; no socket, Docker, package install or API."""
import hashlib
import json
from pathlib import Path
import runpy
import ssl
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from proworksim import software_benchmark_environment_passive_v203_2_1_r3 as repair
from proworksim.software_benchmark_candidates_v054 import checked, reference
ART = Path(__file__).parent
profile = json.loads((ROOT / 'runs/software-benchmark-v111/aligned-interface-r1/recovery-v116/ca-profile.json').read_bytes())
original_ref = profile['tasks']['psf__requests-1921']['original_CA']
original = checked(original_ref).read_bytes()
private = repair.PRIVATE_CA.read_bytes()
certificates = repair.PRIVATE_CA.parent


def handshake(context, name):
    incoming, outgoing, server_in, server_out = [ssl.MemoryBIO() for _ in range(4)]
    client = context.wrap_bio(incoming, outgoing, server_hostname=name)
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certificates / 'cert.pem', certificates / 'key.pem')
    server = server_context.wrap_bio(server_in, server_out, server_side=True)
    done = [False, False]
    for _ in range(128):
        for index, session in enumerate([client, server]):
            if done[index]:
                continue
            try:
                session.do_handshake()
                done[index] = True
            except ssl.SSLWantReadError:
                pass
        if outgoing.pending:
            server_in.write(outgoing.read())
        if server_out.pending:
            incoming.write(server_out.read())
        if all(done):
            return True
    raise AssertionError('MemoryBIO handshake did not finish')


def worker(mode):
    folder = ART / 'cpu-tls' / mode
    folder.mkdir(parents=True, exist_ok=False)
    sources = [folder / 'source-cacert.pem', folder / 'installed-cacert.pem']
    for path in sources:
        path.write_bytes(original)
    (folder / 'combined-ca.pem').write_bytes(original + b'\n' + private)
    original_sha = hashlib.sha256(original).hexdigest()
    combined_sha = hashlib.sha256(original + b'\n' + private).hexdigest()
    shim = repair.shim_source(original_sha, combined_sha, allowed_paths=tuple(map(str, sources)), fixture_root=str(folder))
    (folder / 'sitecustomize.py').write_bytes(shim)
    original_loader = ssl.SSLContext.load_verify_locations
    if mode != 'original-CA-rejects-private-server':
        runpy.run_path(str(folder / 'sitecustomize.py'))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    before = (int(context.verify_mode), context.check_hostname)
    selected = sources[1] if mode == 'installed-path-accepts-private-server' else sources[0]
    if mode == 'unrelated-path-not-augmented':
        selected = folder / 'unrelated-cacert.pem'
        selected.write_bytes(original)
    if mode == 'changed-original-rejected':
        sources[1].write_bytes(original + b'\n# changed')
    if mode == 'changed-combined-rejected':
        (folder / 'combined-ca.pem').write_bytes(original + b'\n' + private + b'\n# changed')
    failure = None
    try:
        context.load_verify_locations(cafile=str(selected))
        hostname = 'wrong-host.invalid' if mode == 'wrong-hostname-rejected' else 'httpbin.org'
        handshake(context, hostname)
    except ssl.SSLError as error:
        failure = {'type': type(error).__name__, 'message': str(error),
                   'verify_code': getattr(error, 'verify_code', None)}
    success_expected = mode in {'source-path-accepts-private-server', 'installed-path-accepts-private-server'}
    assert (failure is None) == success_expected, (mode, failure)
    assert (int(context.verify_mode), context.check_hostname) == before == (2, True)
    if mode == 'wrong-hostname-rejected':
        assert failure['verify_code'] == 62
    if mode in {'changed-original-rejected', 'changed-combined-rejected'}:
        assert 'changed' in failure['message']
    ssl.SSLContext.load_verify_locations = original_loader
    result = {'passed': True, 'mode': mode, 'TLS_handshake_accepted': failure is None,
              'failure': failure, 'verify_mode': 2, 'check_hostname': True,
              'TLS_verification_settings_unchanged': True, 'socket_calls': 0}
    (folder / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if len(sys.argv) > 1:
    def audit(event, arguments):
        if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'}:
            raise AssertionError('CPU TLS control forbids every socket operation')
    sys.addaudithook(audit)
    worker(sys.argv[1])
else:
    modes = ['original-CA-rejects-private-server', 'source-path-accepts-private-server',
             'installed-path-accepts-private-server', 'wrong-hostname-rejected',
             'unrelated-path-not-augmented', 'changed-original-rejected', 'changed-combined-rejected']
    results = []
    for mode in modes:
        result = subprocess.run([sys.executable, __file__, mode], capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise AssertionError(result.stderr)
        results.append(json.loads(result.stdout))
    summary = {'passed': True, 'controls': results, 'native_SSL_MemoryBIO': True,
               'generic_control_original_CA_source': original_ref,
               'control_CA_source_is_not_Requests2317_runtime_proof': True,
               'actual_Requests2317_original_roots_measured_in_future_owned_pinned_container': True,
               'private_CA': reference(repair.PRIVATE_CA), 'source': reference(repair.__file__),
               'model_API_calls': 0, 'socket_calls': 0, 'Docker_calls': 0, 'host_trust_modified': False}
    (ART / 'tls-cpu-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'passed': True, 'native_TLS_controls': len(results)}))
