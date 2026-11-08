"""Use the real retrying ledger and actual finish policy with CPU transport."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import pytest

from proworksim import software_communication_finish_v157 as old_finish
from proworksim import software_communication_finish_v159 as finish
from proworksim import software_benchmark_deepseek_api_v157 as api

spec=importlib.util.spec_from_file_location('budget_controls_v157_helpers',Path(__file__).with_name('test_communication_budget_v157.py'))
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)


def snapshot(book,row):
    provider=book.team_snapshot(row['slot_id'])
    with book.transaction() as db:
        records=[dict(r) for r in db.execute('SELECT * FROM requests WHERE slot_id=?',(row['slot_id'],))]
    provider=finish.retry_evidence(provider,records)
    return {'known_actual_tokens':provider['known_actual_tokens'],'complete_actual_tokens':None if provider['uncertain_reserved_tokens'] else provider['known_actual_tokens'],
        'uncertain_reserved_tokens':provider['uncertain_reserved_tokens'],'inflight':None,
        'token_limit':5_000_000,'all_model_attempt_limit':512,'agent_decision_limit':512,
        'attempts':provider['attempts'],'decisions':provider['decisions'],'authoritative_provider_snapshot':provider}


@pytest.mark.parametrize('purpose',['agent','condenser'])
def test_503_recovered_action_can_finish_with_all_unknown_reservations_retained(tmp_path,purpose):
    views,rows=helpers.setup(tmp_path);row=rows[1]
    failure=api.TransportFailure('complete_http_error_response',phase='complete_http_response',status=503)
    transport=helpers.Script([failure,helpers.body('recovered-'+purpose)])
    client=views['C1'].DeepSeekClient(api_key='unused',allowed_tool_names=(),transport=transport,sleep=lambda _:None,jitter=lambda:0)
    client.complete(helpers.wire(row,purpose),**helpers.args(row,purpose))
    before=client.ledger.snapshot();value=snapshot(client.ledger,row);copy=deepcopy(value)
    with pytest.raises(RuntimeError):old_finish.require_known_usage(value)
    finish.require_known_usage(value)
    policy=finish.FinishReviewPolicy(started={'started':0,'soft_at':21600,'hard_at':23400},
        limits={'agent_decisions':512,'all_model_attempts':512,'input_plus_output_tokens':5_000_000,
            'output_limit':32768,'soft_seconds':21600,'hard_seconds':23400},clock=lambda:1)
    offered=policy.offer(value,intent_id='original-finish-action',reason='work is complete')
    assert offered['permitted'] is True
    assert value==copy and value['complete_actual_tokens'] is None
    assert value['uncertain_reserved_tokens']==200
    assert client.ledger.snapshot()==before and before['unknown_tokens_upper']==200
    assert len(transport.calls)==2


def test_terminal_loss_inflight_and_wrong_logical_success_cannot_finish(tmp_path):
    views,rows=helpers.setup(tmp_path);row=rows[1];book=views['C1'].BudgetLedger()
    kw=helpers.args(row);first=book.reserve(logical_id=kw['request_id'],attempt_index=1,slot_id=row['slot_id'],
        member_id='member_001',condition=row['condition_id'],usage_id='agent',request_sha256='a'*64,
        prompt_upper_bound=100,max_output_tokens=100)
    with pytest.raises(RuntimeError):finish.require_known_usage(snapshot(book,row))
    book.failed(first,api.TransportFailure('complete_http_error_response',phase='complete_http_response',status=503))
    # A response to a different decision cannot cover this unfinished one.
    other=book.reserve(logical_id=row['slot_id']+':member_001:0002',attempt_index=1,slot_id=row['slot_id'],
        member_id='member_001',condition=row['condition_id'],usage_id='agent',request_sha256='b'*64,
        prompt_upper_bound=100,max_output_tokens=100)
    book.settle(other,helpers.body('unrelated-success'))
    with pytest.raises(RuntimeError):finish.require_known_usage(snapshot(book,row))
