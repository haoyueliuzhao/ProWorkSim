import pytest

from proworksim import software_benchmark_ref_budget_v064 as budget
from proworksim.software_benchmark_full_plan_v064 import group_profiles
from proworksim.software_benchmark_exact_transport_v054 import HTTPFailure, REF_MODEL
from proworksim.software_benchmark_match_v054 import AccountingFault


def condition(arm='REF', level='B7500K'):
    group = group_profiles()[f'QWEN_{arm}_{level}']
    return {**group, 'version': 'v064-full-comparison-condition-r1', 'single_agent': True,
            'thinking': True, 'training': False,
            'inference': {**group['inference'], 'automatic_retries': 0,
                'temperature': .6, 'top_p': .95, 'top_k': 20, 'min_p': 0.,
                'presence_penalty': 0., 'repetition_penalty': 1.,
                'chat_template_kwargs': {'enable_thinking': True}}}


class Wire:
    port = 18210

    def __init__(self, fail=False):
        self.sent, self.fail = 0, fail

    def post(self, path, payload):
        if path == '/tokenize':
            return {'tokens': list(range(10)), 'count': 10, 'max_model_len': 131072}
        self.sent += 1
        if self.fail:
            raise HTTPFailure('lost complete reply')
        return {'id': 'response-one', 'model': REF_MODEL,
                'usage': {'prompt_tokens': 10, 'completion_tokens': 7, 'total_tokens': 17},
                'choices': [{'index': 0, 'finish_reason': 'stop',
                             'message': {'role': 'assistant', 'content': 'done'}}]}


def adapter(tmp_path, *, arm='REF', fail=False):
    spec = condition(arm)
    identity = {'model_revision': 'c202236235762e1c871ad0ccb60c8ee5ba337b9a',
        'vllm_version': '0.32.0', 'raw_release': True, 'adapter_sha256': None,
        'model_manifest_sha256': '030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6',
        'context_limit': 131072, 'max_output_tokens': 32768, 'port': 18210,
        'service_admission_complete': True, 'deployment_version': 'v064-owned-user-ref-resident-r1'}
    return budget.PairedQwenAdapter(transport=Wire(fail), folder=tmp_path / 'ledger',
        slot_id=f"v064:task:{spec['condition_id']}:1", seed=1, service_identity=identity,
        condition=spec, allowed_tools={'fixture'})


def request(value):
    return value.request([{'role': 'user', 'content': 'fixture'}],
                         [{'type': 'function', 'function': {'name': 'fixture', 'parameters': {'type': 'object'}}}])


@pytest.mark.parametrize('arm', ['REF', 'PROJECT'])
def test_same_7500k_real_limits_and_actual_usage_for_both_interfaces(tmp_path, arm):
    value = adapter(tmp_path, arm=arm)
    assert value.limits['context_limit'] == 131072
    assert value.ledger.token_limit == 7_500_000
    value.complete(request(value), 'agent')
    assert value.ledger.snapshot()['per_usage_id']['agent'] == {'prompt_tokens': 10, 'completion_tokens': 7}
    assert value.ledger.actual == 17 and value.transport.sent == 1


def test_budget_cut_is_proven_before_send_not_unknown_usage(tmp_path):
    value = adapter(tmp_path)
    value.ledger.actual = value.ledger.token_limit - 32770
    with pytest.raises(budget.BeforeQwenDispatch):
        value.complete(request(value), 'agent')
    assert value.transport.sent == 0 and value.ledger.inflight is None and value.ledger.attempts == 0


def test_sent_unknown_reply_preserves_full_reservation(tmp_path):
    value = adapter(tmp_path, fail=True)
    with pytest.raises(AccountingFault):
        value.complete(request(value), 'agent')
    snapshot = value.ledger.snapshot()
    assert value.transport.sent == 1 and snapshot['complete_actual_tokens'] is None
    assert snapshot['uncertain_reserved_tokens'] == 32778


def test_old_hidden_limit_or_changed_sampling_cannot_be_admitted():
    for key, value in [('maximum_full_input', 18432), ('output_limit', 2048), ('temperature', .7)]:
        spec = condition('PROJECT')
        spec['inference'][key] = value
        with pytest.raises(ValueError):
            budget.validate_condition(spec)
