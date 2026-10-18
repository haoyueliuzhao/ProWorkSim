"""Only new initial-input gate/cache controls; no SDK replay or HOLD content."""
import copy
import json
from types import SimpleNamespace

import pytest

from scripts import software_holdout_inputs_v051 as inputs


def request(identity='opaque-1', contract='Synthetic issue'):
    obs = {'instance_id': identity, 'workspace_reference': {'object_id': identity, 'version_id': 'v1'},
        'member_registry': {m: {'initial_source_reference': {'object_id': identity, 'version_id': 'v1'}}
                            for m in inputs.MEMBERS},
        'team_model_budget': {'state_sha256': identity}, 'contract': contract}
    return {'model': 'shared-local-actor', 'messages': [{'role': 'user',
        'content': json.dumps({'role_task': 'Synthetic role', 'observation': obs})}],
        'tools': [], 'max_tokens': 2048, 'temperature': .7}


def test_source_gate_retains_blocked_inventory_and_never_reads_past_denial(monkeypatch):
    release, common = {'path': 'release'}, {'path': 'common'}
    source = {'version': 'v051-holdout-source-qualification-v1', 'fixture_only': False,
        'completed': True, 'passed': False, 'source_access_release': release,
        'common_implementation_freeze': common, 'qualified_case_ids': [],
        'blocked_case_ids': list(inputs.HOLD_IDS)}
    assert inputs.validate_source_summary(source, release_ref=release, common_ref=common) == []
    source['qualified_case_ids'] = [inputs.HOLD_IDS[0]]
    source['blocked_case_ids'] = list(inputs.HOLD_IDS[1:])
    assert inputs.validate_source_summary(source, release_ref=release, common_ref=common) == [inputs.HOLD_IDS[0]]
    for key, value in [('fixture_only', True), ('completed', False), ('common_implementation_freeze', {})]:
        bad = {**source, key: value}
        with pytest.raises(ValueError):
            inputs.validate_source_summary(bad, release_ref=release, common_ref=common)
    with pytest.raises(ValueError):
        inputs.validate_source_summary({**source, 'blocked_case_ids': []}, release_ref=release, common_ref=common)
    def denied(*args):
        raise ValueError('no content release')
    monkeypatch.setattr(inputs, 'release_gate', denied)
    monkeypatch.setattr(inputs, 'read', lambda path: pytest.fail('No later source read after denial'))
    with pytest.raises(ValueError, match='no content release'):
        inputs.gate('project', 'release', 'source', 'inventory')


def test_exact_byte_cache_and_audit_mask_do_not_reuse_different_public_inputs(monkeypatch):
    class Tokenizer:
        def __call__(self, text, **kwargs):
            return {'input_ids': list(text.encode())}
        def apply_chat_template(self, messages, **kwargs):
            return json.dumps(messages)
    tokenizer = inputs.ExactTokenizer(Tokenizer())
    assert tokenizer('x', add_special_tokens=False) == tokenizer('x', add_special_tokens=False)
    tokenizer('y', add_special_tokens=False)
    tokenizer('x', add_special_tokens=True)
    assert (tokenizer.encodings, tokenizer.encoding_hits) == (3, 1)
    tokenizer.apply_chat_template([{'content': 'x'}], tokenize=False)
    tokenizer.apply_chat_template([{'content': 'x'}], tokenize=False)
    assert (tokenizer.renders, tokenizer.render_hits) == (1, 1)
    first, second = request(), request('opaque-2')
    normalized_a, opaque_a = inputs.business_projection(first)
    normalized_b, opaque_b = inputs.business_projection(second)
    assert normalized_a == normalized_b and opaque_a != opaque_b and first != second
    changed, _ = inputs.business_projection(request('opaque-2', contract='Changed real business'))
    assert changed != normalized_a
    projections = []
    def project(value, **kwargs):
        projections.append(copy.deepcopy(value))
        return value, {'fits': True}
    monkeypatch.setattr(inputs, 'project_software_request', project)
    owner = SimpleNamespace(prepare_request=None, tokenizer=tokenizer, native={})
    cache = {}
    assert inputs.evaluate_request(first, owner, inputs.MEMBERS[0], cache)[1] is False
    assert inputs.evaluate_request(copy.deepcopy(first), owner, inputs.MEMBERS[0], cache)[1] is True
    assert inputs.evaluate_request(second, owner, inputs.MEMBERS[0], cache)[1] is False
    assert inputs.evaluate_request(first, owner, inputs.MEMBERS[1], cache)[1] is False
    assert len(projections) == 3


def test_capture_stops_before_projection_or_dispatch_and_binds_role(tmp_path):
    owner = SimpleNamespace()
    transport = inputs.CaptureTransport(owner, tmp_path)
    association = {'worker_id': inputs.MEMBERS[1], 'call_id': 'synthetic-call'}
    transport.bind_turn(inputs.MEMBERS[1], association)
    actual = request()
    with pytest.raises(inputs.InitialCaptured):
        transport.prepare_for_budget(actual)
    assert transport.captured == {'request': actual, 'runner_turn': {
        'member_id': inputs.MEMBERS[1], 'association': association}}
    assert transport.counter == 0 and transport._prepared is None
    with pytest.raises(ValueError, match='exactly one'):
        transport.prepare_for_budget(actual)
    transport.unbind_turn(inputs.MEMBERS[1], association)
    with pytest.raises(AssertionError, match='cannot dispatch'):
        transport.complete(actual)
