"""New resource scope, unchanged v116 scoring-only CA and bounded TLS mechanism."""
from __future__ import annotations

from . import software_benchmark_environment_v116 as previous
from . import software_benchmark_scope_v126 as scope
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_expansion_episode_v069 import clone_namespace

# Ordinary function bodies are rebound explicitly; original module globals and
# the frozen two-path CA profile are not patched or regenerated.
_namespace = clone_namespace(previous, scope=scope,
    VERSION='v126-current-public-httpbin-source-and-installed-CA-r1', __file__=__file__)
globals().update({key: value for key, value in _namespace.items() if not key.startswith('__')})


def bind_environment(existing, policy):
    """Use this batch's real current probe, never relabel historical DNS evidence."""
    from .software_benchmark_grading_ca_v116 import bind_tls
    bind_tls(existing.tls)

    def prepare():
        resolution_ref = reference(scope.NETWORK_RESOLUTION_FILE)
        resolution = scope.load(resolution_ref)
        addresses = policy.validate_ipv4_targets(resolution['ipv4'])
        if (resolution.get('hostname') != 'httpbin.org' or resolution.get('ports') != [80, 443]
                or resolution.get('selected_ip') != addresses[0]
                or resolution.get('automatic_retry') is not False
                or resolution.get('source') != 'v118_current_DNS_and_bounded_endpoint_probe'):
            raise ValueError('Only the new batch current public endpoint is admitted')
        proof = scope.load(resolution['diagnostic'])
        if (addresses[0] not in proof['current_DNS_ipv4']
                or not all(any(row['ip'] == addresses[0] and row['port'] == port
                               and row.get('get_contract_valid') is True
                               for row in proof['probes']) for port in (80, 443))):
            raise ValueError('The selected public IP lacks its current pre-score health evidence')
        folder = existing.policy.GRADING_ROOT/'environments'
        values = {'offline': scope.retain(folder/'offline.json', existing.offline.environment_manifest()),
            'tls': scope.retain(folder/'tls.json', existing.tls.environment_manifest()),
            'network_resolutions': {task: resolution_ref for task in sorted(existing.TLS_TASKS)}}
        return scope.retain(folder/'bindings.json', values)

    existing.prepare = prepare
    # Existing request_fields/validate_request call this namespace, not merely
    # the ModuleType attribute; retain their actual new preparation binding.
    namespace = existing.request_fields.__globals__
    namespace['prepare'] = prepare
    return existing


def freeze_resolution_from_probe():
    raise ValueError('v118 requires its own explicitly recorded current endpoint probe; no old DNS auto-reuse')
