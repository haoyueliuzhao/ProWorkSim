"""Four-task routing with the existing scoring-only CA fix for Requests1766.

No DNS, network call, container, or old authorization is opened by preparation.
The original endpoint identity is retained, not represented as a current probe.
Solver containers never acquire this scoring-only transport.
The original repository CA bytes stay intact; the qualified v116 adapter adds
its frozen trust anchors only in the new independent scoring containers.
"""
from .software_benchmark_candidates_v054 import reference
from . import software_benchmark_scope_v203_2_3 as scope
from . import software_benchmark_environment_v116 as qualified_ca_environment
from .software_benchmark_expansion_episode_v069 import clone_function

VERSION = 'v203.2.3-four-task-scoring-environment-r1'
TLS_TASK = 'psf__requests-1766'


def private_environment(policy, scope, parent):
    environment = parent(policy)
    from .software_benchmark_grading_ca_v116 import bind_tls
    from .software_benchmark_requests_tls_v068 import run_official
    bind_tls(environment.tls)
    environment.tls.run_official = run_official
    namespace = environment.request_fields.__globals__
    namespace.update(TLS_TASKS=frozenset({TLS_TASK}), OFFLINE_TASKS=frozenset(),
                     TASKS=frozenset({TLS_TASK}))

    def prepare():
        # Exact existing resolution already included in the validated v066
        # control identities; no fresh DNS or implied current-health witness.
        old_binding = scope.load(reference(scope.ROOT /
            'runs/software-benchmark-v066/v064-continuation-r3/grading/environments/bindings.json'))
        historical_ref = old_binding['network_resolutions'][TLS_TASK]
        resolution = scope.load(historical_ref)
        addresses = policy.validate_ipv4_targets(resolution['ipv4'])
        if (resolution.get('hostname') != 'httpbin.org' or resolution.get('ports') != [80, 443]
                or resolution.get('selected_ip') != addresses[0]
                or resolution.get('automatic_retry') is not False):
            raise ValueError('The original numeric HTTP/TLS destination is not bounded')
        resolution_ref = scope.retain(scope.NETWORK_RESOLUTION_FILE, {
            **resolution, 'source': VERSION, 'original_resolution': historical_ref,
            'current_DNS_claimed': False, 'fresh_gold_empty_controls_required': True})
        folder = scope.GRADING_ROOT / 'environments'
        return scope.retain(folder / 'bindings.json', {
            'offline': None,
            'tls': scope.retain(folder / 'requests1766-existing-tls.json', environment.tls.environment_manifest()),
            'network_resolutions': {TLS_TASK: resolution_ref}})

    namespace['prepare'] = prepare
    environment.__dict__.update(namespace)
    return environment


# Preserve the mature actual CA-loader, strict certificate/hostname, original
# file identity, byte relay, and cleanup proof checks under this batch's paths.
validate_transport_evidence = clone_function(
    qualified_ca_environment.validate_transport_evidence,
    {**qualified_ca_environment.validate_transport_evidence.__globals__, 'scope': scope})


def compare_task_environment(old_identity, current_fields, *, task, load):
    """Compare actual qualified task environment, excluding only scope owners."""
    if old_identity.get('network_resolution') != current_fields.get('network_resolution'):
        raise ValueError('Qualified numeric HTTP/TLS endpoint identity changed')
    old_ref = old_identity.get('environment_revision')
    new_ref = current_fields.get('environment_revision')
    if old_ref is None or new_ref is None:
        if old_ref != new_ref:
            raise ValueError('An ordinary task acquired an environment modification')
        return {'environment_revision': None, 'network_resolution': None}
    old, new = load(old_ref), load(new_ref)
    administrative = {'policy', 'dispatch_guard', 'authorization_bound_by'}
    if ({k: v for k, v in old.items() if k not in administrative}
            != {k: v for k, v in new.items() if k not in administrative}):
        raise ValueError('Qualified fixture packages, CA, transport, or resource profile changed')
    if task != TLS_TASK or old.get('original_ca_changed') is not False or new.get('tls_verification_changed') is not False:
        raise ValueError('Only the unchanged Requests1766 scoring TLS profile is admitted')
    return {'original_environment': old_ref, 'current_environment': new_ref,
            'network_resolution': current_fields['network_resolution'],
            'scope_owner_fields_only': sorted(administrative),
            'current_endpoint_health_claimed': False}
