"""Pinned scorer integration and cold/warm-portable parser manifest identity."""
from proworksim import software_benchmark_grading_v203_2_3_r4 as grading
from proworksim import software_benchmark_tcp_transport_v203_2_3_r4 as relay
from proworksim import software_benchmark_http_framing_v203_2_3_r4 as framing
from proworksim import software_benchmark_preparation_grading_v203_2_3_r4 as preparation
from proworksim.software_benchmark_candidates_v054 import reference


def test_r4_scorer_uses_bound_observed_private_transport_and_fixed_profile():
    policy=preparation.dispatch_view()
    value=grading.scorer(policy)
    transport=value.environment.tls.transport
    assert transport.__file__==relay.__file__
    assert transport.relay_many.__globals__['VERSION']==relay.VERSION
    assert transport.http_capture_context=={'path':None}
    assert value.environment.TLS_TASKS=={'psf__requests-1766'}
    manifest=value.environment.tls.environment_manifest()
    assert manifest['TLS_idle_timeout_exempted'] is False
    assert manifest['forwarded_bytes_or_timeouts_changed'] is False
    assert manifest['http_idle_requires_complete_framing_and_both_queues_empty'] is True
    assert manifest['http_framing_parser']==relay.portable_parser()
    assert all('path' not in row for row in manifest['http_framing_parser']['sources'])


def test_two_new_controls_and_full_frozen_parser_descriptor():
    plan=preparation.validate_control_plan(grading.scope.load(reference(preparation.CONTROL_PLAN_FILE)))
    assert set(plan['resources'])=={'control-r4-psf__requests-1766-gold','control-r4-psf__requests-1766-empty'}
    descriptor=framing.parser_descriptor()
    assert descriptor['version']==descriptor['required_version']=='0.16.0'
    assert descriptor['sources'] and all(row['sha256'] and row['bytes']>=0 for row in descriptor['sources'])
