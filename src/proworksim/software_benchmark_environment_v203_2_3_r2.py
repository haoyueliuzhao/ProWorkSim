"""Frozen current httpbin IP; unchanged v116 scoring CA and bounded transport."""
from types import SimpleNamespace
from . import software_benchmark_scope_v203_2_3 as original_scope
from . import software_benchmark_environment_v116 as qualified
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_expansion_episode_v069 import clone_function

VERSION='v203.2.3-current-endpoint-scoring-environment-r2'
TASK='psf__requests-1766'
RESOLUTION=original_scope.BATCH_ROOT/'grading-r2/environments/current-resolution.json'
scope=SimpleNamespace(**{**vars(original_scope),'NETWORK_RESOLUTION_FILE':RESOLUTION})
validate_transport_evidence=clone_function(qualified.validate_transport_evidence,
    {**qualified.validate_transport_evidence.__globals__,'scope':scope})


def private_environment(policy, runtime_scope, parent):
    environment=parent(policy)
    from .software_benchmark_grading_ca_v116 import bind_tls
    from .software_benchmark_requests_tls_v068 import run_official
    bind_tls(environment.tls)
    environment.tls.run_official=run_official
    namespace=environment.request_fields.__globals__
    namespace.update(TASKS=frozenset({TASK}),TLS_TASKS=frozenset({TASK}),OFFLINE_TASKS=frozenset())
    def prepare():
        resolution=scope.load(reference(RESOLUTION))
        diagnostic=scope.load(resolution['diagnostic'])
        correction=scope.load(resolution['current_panel_binding_correction'])
        ip=resolution['selected_ip']
        if (resolution['ipv4']!=[ip] or ip!=diagnostic['selected_ip']
                or ip not in diagnostic['current_DNS_ipv4']
                or resolution.get('hostname')!='httpbin.org' or resolution.get('ports')!=[80,443]
                or resolution.get('automatic_retry') is not False
                or correction.get('probe')!=resolution['diagnostic']
                or correction.get('current_plan')!=reference(original_scope.PLAN_FILE)
                or not all(any(row['ip']==ip and row['port']==port and row.get('get_contract_valid') is True
                               for row in diagnostic['probes']) for port in (80,443))):
            raise ValueError('The single frozen current endpoint lacks its actual bounded probe')
        policy.validate_ipv4_targets([ip])
        folder=runtime_scope.GRADING_ROOT/'environments'
        return runtime_scope.retain(folder/'bindings.json',{'offline':None,
            'tls':runtime_scope.retain(folder/'requests1766-current-tls.json',environment.tls.environment_manifest()),
            'network_resolutions':{TASK:reference(RESOLUTION)}})
    namespace['prepare']=prepare
    environment.__dict__.update(namespace)
    return environment
