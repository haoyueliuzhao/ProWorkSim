from __future__ import annotations

import pytest

from proworksim.software_communication_runtime_v156 import (
    AccountingConflict, AuditedRequestGateway, BudgetStopped, SharedTeamPool,
)


def usage(prompt=10, completion=2):
    return {'prompt_tokens': prompt, 'completion_tokens': completion,
            'total_tokens': prompt + completion,
            'prompt_cache_hit_tokens': 3, 'prompt_cache_miss_tokens': prompt - 3}


def test_members_summary_and_compressor_share_one_budget(tmp_path):
    pool = SharedTeamPool(tmp_path, 'team', token_limit=60)
    for request, purpose in [('a', 'agent'), ('b', 'condenser'), ('c', 'compressor')]:
        pool.reserve(request, purpose, 15, 5, identity={'decision_id': 'decision-a'})
        pool.settle(request, usage())
    view = pool.snapshot()
    assert view['known_actual_tokens'] == 36
    assert view['agent_decisions'] == 1 and view['physical_attempts'] == 3
    assert sum(v['total_tokens'] for v in view['per_purpose'].values()) == 36
    assert view['available_tokens'] == 24  # Cached input was not added twice.
    with pytest.raises(BudgetStopped):
        pool.reserve('too-large', 'compressor', 20, 5)


def test_uncertain_retries_retained_and_recovery_idempotent(tmp_path):
    pool = SharedTeamPool(tmp_path, 'team', token_limit=50, attempt_limit=2)
    identity = {'decision_id': 'decision-a'}
    pool.reserve('a-1', 'agent', 15, 5, identity=identity)
    pool.uncertain('a-1', {'http_status': 503})
    pool = SharedTeamPool(tmp_path, 'team', token_limit=50, attempt_limit=2)
    pool.reserve('a-2', 'agent', 15, 5, identity=identity)
    pool.settle('a-2', usage())
    pool.settle('a-2', usage())
    snapshot = pool.snapshot()
    assert snapshot['known_actual_tokens'] == 12
    assert snapshot['unresolved_reserved_tokens'] == 20
    assert snapshot['agent_decisions'] == 1
    assert snapshot['physical_attempts'] == 2
    with pytest.raises(BudgetStopped):
        pool.reserve('a-3', 'agent', 1, 1, identity=identity)
    with pytest.raises(AccountingConflict):
        pool.reserve('a-2', 'compressor', 15, 5)


def test_actual_overrun_is_not_erased_and_stops_future_dispatch(tmp_path):
    pool = SharedTeamPool(tmp_path, 'team')
    pool.reserve('a', 'compressor', 10, 1)
    with pytest.raises(AccountingConflict):
        pool.settle('a', usage())
    pool.uncertain('a', {'post_response_validation_failed': True})
    assert pool.snapshot()['known_actual_tokens'] == 12
    with pytest.raises(AccountingConflict):
        pool.reserve('b', 'compressor', 10, 1)


def test_usage_conflict_cannot_corrupt_completed_book(tmp_path):
    pool = SharedTeamPool(tmp_path, 'team')
    pool.reserve('a', 'compressor', 20, 10)
    pool.settle('a', usage())
    with pytest.raises(AccountingConflict):
        pool.settle('a', usage(11))
    assert pool.snapshot()['known_actual_tokens'] == 12
    with pytest.raises(AccountingConflict):
        SharedTeamPool(tmp_path, 'another-team')


def test_p0_cannot_construct_live_network_gateway(tmp_path):
    pool = SharedTeamPool(tmp_path/'pool', 'team')
    with pytest.raises(PermissionError):
        AuditedRequestGateway(tmp_path/'audit', pool, lambda *_: None)


def test_physical_dispatch_claim_survives_new_instance_and_directory(tmp_path):
    pool = SharedTeamPool(tmp_path/'shared', 'team')
    pool.reserve('a', 'compressor', 20, 10)
    second = SharedTeamPool(tmp_path/'shared', 'team')
    pool.claim_dispatch('a', 'a'*64)
    with pytest.raises(AccountingConflict):
        second.claim_dispatch('a', 'a'*64)
    pool.settle('a', usage())
    with pytest.raises(AccountingConflict):
        second.claim_dispatch('a', 'b'*64)
    assert second.snapshot()['physical_attempts'] == 1
