"""Real SDK + real world, explicit fake language-model response fixture only."""
import json

import pytest

pytest.importorskip('openhands.sdk')

from proworksim.harness_collection import collect_window  # noqa: E402
from proworksim.member_views import member_view  # noqa: E402
from proworksim.storage import read_json  # noqa: E402
from test_online_collection_v013 import FakeOwner  # noqa: E402


class Owner(FakeOwner):
    def complete(self, request, **kwargs):
        response = super().complete(request, **kwargs)
        count = self.calls['implementer']
        name, args = [('work_note', {'key': 'plan', 'text': 'CPU fixture note'}),
                      ('read_alias', {'alias': 'code', 'work_id': 'TEAM::build'}),
                      ('staff_done', {'reason': 'CPU fixture finished'})][count-1]
        call = response['body']['choices'][0]['message']['tool_calls'][0]
        call['function'] = {'name': name, 'arguments': json.dumps(args)}
        response['raw_body'] = json.dumps(response['body'])
        return response


def test_sdk_collector_preserves_actual_world_capture_and_original_member_trace(tmp_path):
    owner = Owner()
    owner.recipe["max_length"] = 16384
    spec = {'window_id': owner.window_id, 'harness': 'openhands_v16', 'stage': 'H0_cpu_fixture',
            'slots': [{'slot_id': 'sdk', 'case_id': 'uci-harness-f0-implement', 'sampling_seed': 55}]}
    entries = collect_window(owner, spec, tmp_path/'collect')
    assert len(entries) == 1 and entries[0]['rollout'] is not None
    rollout = entries[0]['rollout']
    assert entries[0]['reward']['eligible'] and entries[0]['reward']['reward'] == 0
    assert rollout['work_validity']['components']['record']['value'] is True
    assert rollout['work_validity']['components']['permission']['value'] is True
    view = member_view(rollout, 'implementer')
    assert len(view['decisions']) == 3
    assert all(r['tokens']['output_ids'] == [3] for r in view['decisions'])
    events = rollout['events']
    assert len([e for e in events if e['kind'] == 'tool_call']) == 1
    assert len([e for e in events if e['kind'] == 'harness_tool_call']) == 2
    runtime = read_json(tmp_path/'collect/slot-0/runtime.json')
    assert runtime['workbenches']['implementer']['notes'] == {'plan': 'CPU fixture note'}
    assert runtime['worker_conversations']['implementer']['sdk_events']


def test_sdk_policy_registration_requires_its_explicit_harness_and_current_actor():
    from proworksim.online_support import _policies
    owner = Owner()
    identity = owner.freeze_identity()
    policy = {'implementer': {'implementation': 'proworksim.harness_sdk.HarnessWorker',
              'config': {'weight_identity': identity, 'model_revision': identity['policy_version']}}}
    assert _policies(policy, ['implementer'], identity, harness='openhands_v16') == policy
    with pytest.raises(ValueError):
        _policies(policy, ['implementer'], identity, harness='native_v15')
    policy['implementer']['config']['model_revision'] = 'other-policy'
    with pytest.raises(ValueError):
        _policies(policy, ['implementer'], identity, harness='openhands_v16')
