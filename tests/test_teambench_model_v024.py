"""Focused measurement tests; no expanded OS matrix or held-out model work."""
import copy
import json
from pathlib import Path

import pytest

from proworksim.teambench_isolation_v022 import facility_probe
from proworksim.teambench_model_v024 import (
    PUBLIC_CLARIFICATION, run_episode, verification_metrics,
)
from scripts.teambench_model_v023 import ExplicitFakeOwner


def record(*, success=True, content=True, equal=True, identity='check-0'):
    return {'verification_id': identity, 'submission_id': 'submission',
            'execution_succeeded': success, 'valid_expected_table': success,
            'submitted_table_equal': equal if success else None,
            'content_assessment': {'status': 'checked' if success else 'not_assessed_no_valid_table',
                                   'content_correct': content if success else None}}


def metrics(records, attest=None):
    return verification_metrics(records, attest, submission_id='submission',
                                complete_reads=True, fixed_workspace_unchanged=True, attempted=len(records))


def attestation(check='check-0'):
    return {'verification_id': check, 'submission_id': 'submission', 'verdict': 'pass'}


def test_successful_execution_without_final_attestation_is_not_lost():
    row = metrics([record()])
    assert row['verification_attempted']
    assert row['verification_execution_succeeded'] and row['verification_table_valid']
    assert row['verification_matches_submission'] and row['verification_content_correct']
    assert not row['final_attestation_supported']
    assert not row['final_attestation_computation_succeeded']


def test_equal_jointly_wrong_and_failed_final_check_cannot_support_pass():
    wrong = metrics([record(content=False)], attestation())
    assert wrong['verification_matches_submission']
    assert not wrong['verification_content_correct'] and not wrong['final_attestation_supported']
    failed = metrics([record(success=False)], attestation())
    assert not failed['verification_execution_succeeded'] and not failed['verification_table_valid']
    assert failed['verification_matches_submission'] is None
    assert failed['verification_content_correct'] is None
    assert not failed['final_attestation_supported']
    mixed = metrics([record(), record(success=False, identity='check-1')], attestation('check-1'))
    assert mixed['verification_execution_succeeded'] and mixed['verification_content_correct']
    assert not mixed['final_attestation_computation_succeeded'] and not mixed['final_attestation_supported']


def test_revised_public_rule_and_actual_model_port_preserve_private_assessment(tmp_path):
    assets = Path('runs/teambench-v022-os-isolation-verified')
    if not assets.exists() or not facility_probe()['available']:
        pytest.skip('Existing pinned development fixture and role isolation required')
    owner = ExplicitFakeOwner('correct')
    initial_requests = copy.deepcopy(owner.requests)
    report = run_episode(owner, assets / 'generated/seed0',
                         assets / 'reviewed-source/tasks/D2_data_quality/grade.sh', tmp_path / 'episode', seed=0)
    assert initial_requests == []
    assert report['responsibility']['full_joint_responsibility']
    assert report['responsibility']['verification_content_correct']
    assert 'verifier_computation_executed' not in report['responsibility']
    assert all('expected.json' not in str(request) and 'content_assessment' not in str(request)
               for request in owner.requests)
    rendered_rules = [json.dumps(PUBLIC_CLARIFICATION, ensure_ascii=ascii_mode)[1:-1]
                      for ascii_mode in (False, True)]
    assert any(rule in str(message.get('content', ''))
               for rule in [PUBLIC_CLARIFICATION, *rendered_rules]
               for request in owner.requests for message in request['messages'])
    assert report['verification_attempts'][0]['content_assessment']['actor_reruns'] == 0
