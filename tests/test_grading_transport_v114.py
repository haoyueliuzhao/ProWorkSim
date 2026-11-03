"""Exercise the actual fresh qualification -> approved CA validation callsite."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_grading_recovery_v114 as grading
from proworksim import software_benchmark_environment_v114 as environment
from proworksim import software_benchmark_grading_ca_v114 as ca
from proworksim import software_benchmark_grading_qualification_v060 as legacy
from proworksim.software_benchmark_candidates_v054 import reference, write_new


@pytest.mark.parametrize('change,expected', [('valid', True), ('missing_profile', False), ('verification_off', False)])
def test_real_fresh_control_validator_calls_separate_ca_evidence(tmp_path, monkeypatch, change, expected):
    task = 'psf__requests-1766'
    plan_ref = write_new(tmp_path/'plan.json', {'CPU_ONLY_control_fixture': True})
    mapping_ref = write_new(tmp_path/'mapping.json', {'official_tree': 'a'*40})
    coordinator = tmp_path/'coordinator'
    coordinator.mkdir()
    scorer_manifest = write_new(coordinator/'scorer-manifest.json', {'CPU_ONLY_manifest': True})
    config = {'instance_id': task, 'scorer_request_base': {'dataset': {'CPU_ONLY': 'dataset'},
              'image': {'image_id': 'sha256:'+'b'*64}, 'baseline_mapping': mapping_ref}}
    policy = SimpleNamespace(GRADING_ROOT=tmp_path/'grading', COORDINATOR_RUN_ROOT=coordinator)
    caps = ['NET_ADMIN', 'NET_BIND_SERVICE']
    provider = SimpleNamespace(TASKS={task}, TLS_TASKS={task}, capabilities=lambda _: caps,
                               validate_request=lambda identity, instance: None)
    namespace = {**vars(grading.previous.original), 'VERSION': grading.VERSION,
                 'policy': policy, 'environment': provider}
    validate = grading.fresh_qualification_validator(namespace)
    profile = ca.profile_manifest()
    resolution_ref = reference(environment.scope.NETWORK_RESOLUTION_FILE)
    resolution = environment.scope.load(resolution_ref)
    original_ca = {'path': '/testbed/requests/cacert.pem',
                   'sha256': profile['tasks'][task]['original_CA_sha256']}
    controls = []
    for kind in ('gold', 'empty'):
        key = grading.control_key(task, kind)
        folder = policy.GRADING_ROOT/key
        (folder/'official-output').mkdir(parents=True)
        observed = {'CPU_ONLY_evidence_fixture': True, 'head_git_tree': 'a'*40,
            'working_tree_clean': True, 'effective_network_mode': 'none',
            'namespace_evidence': {'all_distinct': True}, 'environment_revision': {'CPU_ONLY': 'environment'},
            'task_files_changed': False, 'timeout_route': {'real_connect_timeout': True},
            'actual_capabilities': caps, 'actual_dropped_capabilities': ['ALL'],
            'original_ca': original_ca, 'original_ca_changed': False,
            'scoring_CA_profile': reference(environment.scope.CA_PROFILE_FILE),
            'effective_CA_changed': True, 'original_CA_file_unchanged': True,
            'tls_verification_changed': True, 'resolution': resolution_ref,
            'scoring_CA_loader_probe': {'actual_SSL_loader_probe': True, 'effective_CA_changed': True,
                'original_CA_file_unchanged': True, 'verify_mode': 2, 'check_hostname': True, 'network_calls': 0}}
        if change == 'missing_profile':
            observed.pop('scoring_CA_profile')
        elif change == 'verification_off':
            observed['scoring_CA_loader_probe'].update(verify_mode=0, check_hostname=False)
        transport_ref = write_new(folder/'official-output/transport.json', {
            'CPU_ONLY_evidence_fixture': True, 'ok': True, 'status': 'completed', 'ready': True,
            'network_errors': [], 'cleanup_errors': [], 'error': None, 'thread_finished': True,
            'exec_finished': True, 'exec_exit_code': 0, 'original_ca_unchanged': True,
            'original_ca_before': original_ca, 'original_ca_after': original_ca,
            'target_ip': resolution['selected_ip'], 'target_hostname': 'httpbin.org', 'listen_ports': [80,443],
            'connection_attempts': 1, 'max_active_observed': 1, 'application_payload_bytes': 200})
        identity = {'plan': plan_ref, 'resource_key': key, **config['scorer_request_base'],
            'scorer_manifest': scorer_manifest, 'limits': grading.previous.original.LIMITS,
            'patch_kind': kind, 'actor_feedback': False, 'model_calls': 0,
            'environment_revision': {'CPU_ONLY': 'environment'}, 'network_resolution': resolution_ref}
        identity_ref = write_new(folder/'official-output/identity.json', identity)
        report = {'patch_successfully_applied': True, 'resolved': kind == 'gold',
                  'tests_status': {'FAIL_TO_PASS': {'failure': [] if kind == 'gold' else ['CPU_fixture_test']}}}
        receipt = {'version': grading.VERSION, 'status': 'official_report', 'resource_key': key,
            'instance_id': task, 'identity': identity_ref, 'actor_feedback': False, 'model_calls': 0,
            'transport_result': transport_ref, 'resolved': kind == 'gold', 'official_result': [task, {task: report}]}
        quiet = {'resource_key': key, 'quiescent': True, 'cleanup_errors': [], 'create_result_unknown': False,
                 'deadline_reached': False, 'transport_result': transport_ref}
        controls.append({'patch_kind': kind,
            'receipt': write_new(folder/'receipt.json', receipt),
            'quiescence': write_new(folder/'quiescence.json', quiet),
            'completion': write_new(folder/'completion.json', {'returncode': 0}),
            'initial_container': write_new(folder/'official-output/initial-container.json', observed)})
    qualification = {'version': grading.VERSION, 'instance_id': task, 'passed': True,
                     'plan': plan_ref, 'controls': controls}
    ref = write_new(tmp_path/'qualification.json', qualification)
    seen = []
    real = environment.validate_transport_evidence
    def called(*args, **kwargs):
        seen.append(args[0]['resource_key'])
        return real(*args, **kwargs)
    def old_called(*_args, **_kwargs):
        raise AssertionError('The old unchanged-effective-CA validator must not run')
    monkeypatch.setattr(environment, 'validate_transport_evidence', called)
    monkeypatch.setattr(legacy, 'validate_transport_evidence', old_called)
    if expected:
        assert validate(ref, config, plan_ref) == qualification
        assert len(seen) == 2
    else:
        with pytest.raises(ValueError, match='separately proven'):
            validate(ref, config, plan_ref)
        assert len(seen) == 1
