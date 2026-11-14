"""Freeze current grading-only httpbin routing; never reuse historical DNS forever."""
from __future__ import annotations

import json
from pathlib import Path
import re

from . import software_benchmark_scope_v116 as scope
from .software_benchmark_candidates_v054 import reference,checked

VERSION='v116-current-public-httpbin-installed-CA-scoring-r1'


def validate_transport_evidence(receipt,quiet,observed,identity,folder,*,transport_directory=None,
                                require_usage=True):
    """Validate original file integrity and the separately approved effective CA."""
    from .software_benchmark_grading_ca_v116 import profile_manifest
    profile=profile_manifest()
    task=receipt.get('instance_id')
    entry=profile['tasks'].get(task)
    probe=observed.get('scoring_CA_loader_probe',{})
    if (entry is None or observed.get('scoring_CA_profile')!=reference(scope.CA_PROFILE_FILE)
            or observed.get('effective_CA_changed') is not True
            or observed.get('original_CA_file_unchanged') is not True
            or observed.get('tls_verification_changed') is not True
            or probe.get('actual_SSL_loader_probe') is not True
            or probe.get('effective_CA_changed') is not True
            or probe.get('original_CA_file_unchanged') is not True
            or probe.get('verify_mode')!=2 or probe.get('check_hostname') is not True
            or probe.get('network_calls')!=0
            or observed.get('original_ca',{}).get('sha256')!=entry['original_CA_sha256']):
        raise ValueError('The original CA file and approved scoring trust set are not separately proven')
    ref=receipt.get('transport_result')
    directory=folder/'official-output' if transport_directory is None else Path(transport_directory)
    if (not isinstance(ref,dict) or Path(ref.get('path','')).resolve()!=(directory/'transport.json').resolve()
            or quiet.get('transport_result')!=ref or quiet.get('deadline_reached') is not False):
        raise ValueError('Transport evidence belongs to another control or exceeded its deadline')
    result=scope.load(ref)
    if (result.get('ok') is not True or result.get('status')!='completed' or result.get('ready') is not True
            or result.get('network_errors')!=[] or result.get('cleanup_errors')!=[] or result.get('error') is not None
            or result.get('thread_finished') is not True or result.get('exec_finished') is not True
            or result.get('exec_exit_code')!=0 or result.get('original_ca_unchanged') is not True
            or result.get('original_ca_before')!=observed.get('original_ca')
            or result.get('original_ca_after')!=observed.get('original_ca')
            or observed['original_ca'].get('path')!='/testbed/requests/cacert.pem'
            or re.fullmatch(r'[0-9a-f]{64}',observed['original_ca'].get('sha256','')) is None
            or observed.get('original_ca_changed') is not False):
        raise ValueError('Bounded transport or the unchanged repository CA file did not qualify')
    resolution_ref=identity.get('network_resolution')
    if observed.get('resolution')!=resolution_ref or resolution_ref!=reference(scope.NETWORK_RESOLUTION_FILE):
        raise ValueError('Control does not bind the newly frozen DNS identity')
    resolution=scope.load(resolution_ref)
    addresses=scope.original.validate_ipv4_targets(resolution.get('ipv4'))
    if (resolution.get('selected_ip')!=addresses[0] or resolution.get('hostname')!='httpbin.org'
            or resolution.get('ports')!=[80,443] or resolution.get('automatic_retry') is not False
            or result.get('target_ip')!=addresses[0] or result.get('target_hostname')!='httpbin.org'
            or result.get('listen_ports')!=[80,443]):
        raise ValueError('Transport target differs from the current admitted public endpoint')
    minimum=1 if require_usage else 0
    for key,maximum in (('connection_attempts',512),('max_active_observed',16),
                        ('application_payload_bytes',64*1024**2)):
        if type(result.get(key)) is not int or not minimum<=result[key]<=maximum:
            raise ValueError('Transport use exceeds the approved bounds')
    return result


def bind_environment(existing,policy):
    from .software_benchmark_grading_ca_v116 import bind_tls
    bind_tls(existing.tls)
    namespace=existing.prepare.__globals__
    def prepare():
        resolution_ref=reference(scope.NETWORK_RESOLUTION_FILE)
        resolution=scope.load(resolution_ref)
        addresses=policy.validate_ipv4_targets(resolution['ipv4'])
        if (resolution.get('hostname')!='httpbin.org' or resolution.get('ports')!=[80,443]
                or resolution.get('selected_ip')!=addresses[0]
                or resolution.get('automatic_retry') is not False
                or resolution.get('source')!='v114_current_DNS_and_bounded_endpoint_probe'):
            raise ValueError('Only the newly frozen current public endpoint is admitted')
        proof=scope.load(resolution['diagnostic'])
        if (addresses[0] not in proof['current_DNS_ipv4']
                or not all(any(row['ip']==addresses[0] and row['port']==port
                               and row.get('get_contract_valid') is True
                               for row in proof['probes']) for port in (80,443))):
            raise ValueError('The selected public IP lacks its fixed pre-score health evidence')
        folder=existing.policy.GRADING_ROOT/'environments'
        values={'offline':scope.retain(folder/'offline.json',existing.offline.environment_manifest()),
                'tls':scope.retain(folder/'tls.json',existing.tls.environment_manifest()),
                'network_resolutions':{task:resolution_ref for task in sorted(existing.TLS_TASKS)}}
        return scope.retain(folder/'bindings.json',values)
    existing.prepare=prepare
    namespace['prepare']=prepare
    return existing


def freeze_resolution_from_probe():
    path=scope.ROOT/'artifacts/software-benchmark-v114/httpbin-direct-diagnostic-r1.json'
    proof=json.loads(checked(reference(path)).read_bytes())
    # Choose the first address in the prespecified lexical DNS order that was
    # probed on both ports. This uses environment evidence, never model scores.
    selected=sorted(proof['current_DNS_ipv4'])[0]
    if not all(any(row['ip']==selected and row['port']==port and row.get('get_contract_valid') is True
                   for row in proof['probes']) for port in (80,443)):
        raise ValueError('No healthy prespecified DNS endpoint; do not silently switch candidates')
    return scope.retain(scope.NETWORK_RESOLUTION_FILE,{'hostname':'httpbin.org','ports':[80,443],
        'ipv4':[selected],'selected_ip':selected,'automatic_retry':False,
        'version':VERSION,'source':'v114_current_DNS_and_bounded_endpoint_probe',
        'all_observed_DNS_ipv4':proof['current_DNS_ipv4'],'diagnostic':reference(path),
        'historical_endpoint_reused':False,'actor_network_unchanged':True})
