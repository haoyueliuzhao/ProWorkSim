"""CPU port/capture controls; synthetic transport is not a model experiment."""

import copy
import json

from proworksim.episode import begin_episode, finish_episode
from proworksim.experience import capture_port
from proworksim.member_views import member_view
from proworksim.model_policy import ModelPolicy
from proworksim.online_rewards import assess_online_reward
from proworksim.presentations import MARKER, response_matches_receipt
from proworksim.staff_runtime import StaffRuntime
from proworksim.storage import digest, json_bytes, read_json
from proworksim.team_validity import assess_record_permission
from proworksim.templates.online_work import build_online_case
from proworksim.work_interface import WorkInterface, V14_INTERFACE


def prepared(tmp_path):
    return build_online_case('development-w0-review', tmp_path / 'case')


def port_for(prep, tmp_path, presentation='compact_v14'):
    return WorkInterface(prep.world.session('reviewer', 'TEAM'), 'reviewer',
                         variant='v14', presentation=presentation, audit_dir=tmp_path / 'audit')


def inspection_arguments(port):
    work = port.observe()['work_items']['TEAM::build']
    return {'work_id': 'TEAM::build', 'submission_id': work['pending_submission_id']}


def test_same_new_tools_only_presentation_differs_and_old_schema_is_preserved(tmp_path):
    prep = prepared(tmp_path)
    compact = port_for(prep, tmp_path)
    full = port_for(prep, tmp_path, 'full_v14')
    assert full.tools() == compact.tools()
    assert compact.profile == V14_INTERFACE + ':reviewer'
    inspect = next(t for t in compact.tools() if t['name'] == 'inspect_submission')
    assert inspect['parameters']['properties']['include_contract']['type'] == 'boolean'
    assert 'include_contract' not in inspect['parameters']['required']
    old = WorkInterface(prep.world.session('reviewer', 'TEAM'), 'reviewer')
    old_inspect = next(t for t in old.tools() if t['name'] == 'inspect_submission')
    assert 'include_contract' not in old_inspect['parameters']['properties']
    args = inspection_arguments(compact)
    before = copy.deepcopy(prep.world.state['knowledge']['reviewer'])
    result = compact.call('inspect_submission', **args)
    raw = compact.response_projections[-1]['raw_response']
    assert result['result']['artifact_versions'] == raw['result']['artifact_versions']
    assert set(result['result']['artifact_versions'].values()) == {'v2'}
    assert len(json_bytes(result)) < 0.65 * len(json_bytes(raw))
    assert prep.world.state['knowledge']['reviewer'] == before
    assert result['result']['requirement_snapshot_complete'] is False
    retrieval = result['result']['read_full_inspection']
    complete = compact.call(retrieval['tool'], **retrieval['arguments'])
    assert complete['result'] == raw['result']
    assert MARKER not in complete
    assert prep.world.state['knowledge']['reviewer'] == before
    wrong = compact.call('inspect_submission', **args, include_contract='true')
    assert wrong['ok'] is False
    assert wrong['error']['rejection']['code'] == 'public_argument_schema'


def test_projection_receipt_cannot_be_forged_or_rebound(tmp_path):
    prep = prepared(tmp_path)
    port = port_for(prep, tmp_path)
    args = inspection_arguments(port)
    public = port.call('inspect_submission', **args)
    commit = prep.world.state['operation_commits'][public['command_id']]
    assert commit['public_result'] != public
    assert response_matches_receipt(commit, public, action='inspect_submission', arguments=args)
    for mutate in ('version', 'profile', 'raw_response_sha256', 'project_id'):
        changed = copy.deepcopy(public)
        changed[MARKER][mutate] = 'forged'
        assert not response_matches_receipt(commit, changed, action='inspect_submission', arguments=args)
    changed = copy.deepcopy(public)
    changed['result']['artifact_versions'] = {}
    assert not response_matches_receipt(commit, changed, action='inspect_submission', arguments=args)
    assert not response_matches_receipt(commit, public, action='read_alias', arguments=args)
    assert not response_matches_receipt(commit, public, action='inspect_submission', arguments={**args, 'include_contract': True})


def test_actual_read_bodies_remain_exact_and_both_projection_sides_are_saved(tmp_path):
    prep = prepared(tmp_path)
    port = port_for(prep, tmp_path)
    observation = port.observe()
    original = port.projections[-1]['raw_observation']
    for key, value in original.items():
        if key != 'projects':
            assert observation[key] == value
    assert observation['instance_id'] == original['instance_id']
    assert observation['branch_id'] == original['branch_id']
    response = port.call('read_alias', alias='audit_basis', work_id='TEAM::build')
    assert response['ok'] is True
    commit = prep.world.state['operation_commits'][response['command_id']]
    assert response == commit['public_result']
    exact = port.call('read_version', reference=response['result']['reference'], work_id='TEAM::build')
    assert exact['result'] == response['result']
    audit = read_json(tmp_path / 'audit/call-2.json')
    assert audit['raw_response'] == audit['public_response'] == exact
    assert audit['public_response_sha256'] == digest(json_bytes(exact))
    assert port.projections[-1]['selected_observation'] == observation


class InspectorTransport:
    """Returns predeclared inspect then done calls, never executes a model."""

    def __init__(self, arguments):
        self.arguments = arguments
        self.requests = []

    def complete(self, request, *, timeout_seconds):
        self.requests.append(copy.deepcopy(request))
        index = len(self.requests)
        name = 'inspect_submission' if index == 1 else 'staff_done'
        args = self.arguments if index == 1 else {'reason': 'CPU inspection control'}
        body = {
            'id': 'fixture-' + str(index), 'model': 'explicit-cpu-fixture',
            'choices': [{'message': {'role': 'assistant', 'content': None,
                'tool_calls': [{'id': 'call-' + str(index), 'type': 'function',
                    'function': {'name': name, 'arguments': json.dumps(args)}}]},
                'finish_reason': 'tool_calls'}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120},
        }
        return {'http_status': 200, 'body': body, 'raw_body': json.dumps(body)}


def test_native_input_independent_capture_permission_and_reward_follow_public_return(tmp_path):
    prep = prepared(tmp_path)
    interface = port_for(prep, tmp_path)
    args = inspection_arguments(interface)
    captured = []
    transport = InspectorTransport(args)
    policy = ModelPolicy({'task': 'Inspect this fixed submission.', 'action_protocol': 'native_tools',
                          'context_policy': 'latest_observation'}, transport=transport)
    runtime = StaffRuntime({'reviewer': capture_port(interface, captured)}, {'reviewer': policy})
    episode = tmp_path / 'episode'
    begin_episode(prep.world, episode, experience=runtime.recorder.snapshot(), work_nodes=['TEAM::build'],
                  work_ids=[], scenario=prep.scenario, policies=runtime.policy_identities)
    first = runtime.step()
    assert first['action_performed'], first
    assert runtime.step()['status'] == 'completed'
    finish_episode(prep.world, episode, experience=runtime.recorder.snapshot(),
                   termination={'status': 'workers_done', 'kind': 'finite_horizon_task_terminal'})
    public = next(e['payload']['response'] for e in captured if e['kind'] == 'tool_call')
    tool_message = next(m for m in transport.requests[1]['messages'] if m['role'] == 'tool')
    assert json.loads(tool_message['content']) == public
    assert MARKER in public
    assert 'public_format' not in public['result']['requirement_snapshot']['requirements']
    raw = interface.response_projections[0]['raw_response']
    assert json.dumps(raw, ensure_ascii=False, allow_nan=False) != tool_message['content']
    members = {'reviewer': {'actor_id': 'reviewer', 'origin': 'target_model'}}
    validity = assess_record_permission(episode, members=members,
                                       independent_capture={'reviewer': captured}, spec_id='compact-cpu')
    assert validity['components']['record']['value'] is True
    assert validity['components']['permission']['value'] is True
    reward = assess_online_reward(episode, prep.reward_spec)
    assert reward['eligible'] and reward['reward'] == 0
    assert not reward['completed']
    rollout = {'rollout_id': 'cpu-only', 'window': {}, 'members': members,
               'manifest': read_json(episode / 'manifest.json'), 'events': runtime.recorder.events}
    view = member_view(rollout, 'reviewer')
    assert view['complete_semantic_trajectory']
    assert view['decisions'][1]['actual_input'] == transport.requests[1]
    assert not view['complete_actor_trajectory'], 'This fixture has no actual model token trace'


def test_compact_submit_can_retrieve_full_contract_without_changing_real_reward(tmp_path):
    from scripts.online_work_experiment_v013 import Witness, implement

    rewards = []
    for presentation in ("full_v14", "compact_v14"):
        root = tmp_path / presentation
        prep = build_online_case("development-w0-implement", root / "case")
        interface = WorkInterface(prep.world.session("implementer", "TEAM"), "implementer",
                                  variant="v14", presentation=presentation)
        alternative = WorkInterface(prep.world.session("implementer", "TEAM"), "implementer",
                                    variant="v14", presentation="compact_v14")
        assert interface.tools() == alternative.tools()
        assert "inspect_submission" in {t["name"] for t in interface.tools()}
        old = WorkInterface(prep.world.session("implementer", "TEAM"), "implementer")
        assert "inspect_submission" not in {t["name"] for t in old.tools()}
        witness = Witness(prep)
        witness.ports["implementer"] = capture_port(interface, witness.capture["implementer"])
        episode = root / "episode"
        begin_episode(prep.world, episode, experience=witness.recorder.snapshot(), work_ids=["TEAM::build"],
                      scenario=prep.scenario, policies={"implementer": {"implementation": "explicit_rule_witness"}})
        submission = implement(witness)
        original = interface.response_projections[-1]["raw_response"]
        public = interface.response_projections[-1]["public_response"]
        assert submission["artifact_versions"] == original["result"]["artifact_versions"]
        assert response_matches_receipt(prep.world.state["operation_commits"][public["command_id"]], public,
                                        action="submit", arguments={"work_id": "TEAM::build", "artifacts": ["code", "result"]})
        if presentation == "compact_v14":
            assert MARKER in public
            assert submission["requirement_snapshot_complete"] is False
            assert len(json_bytes(public)) < len(json_bytes(original))
            readback = submission["read_full_inspection"]
        else:
            assert public == original
            readback = {"tool": "inspect_submission", "arguments": {
                "work_id": "TEAM::build", "submission_id": submission["submission_id"], "include_contract": True}}
        full = witness.call("implementer", readback["tool"], **readback["arguments"])
        assert full == original["result"]
        finish_episode(prep.world, episode, experience=witness.recorder.snapshot(), termination={"status": "cpu_rule_control"})
        reward = assess_online_reward(episode, prep.reward_spec)
        assert reward["eligible"] and reward["completed"]
        rewards.append(reward["reward"])
        validity = assess_record_permission(episode,
                    members={"implementer": {"actor_id": "implementer", "origin": "rule"}},
                    independent_capture=witness.capture, spec_id="submit-projection-cpu")
        assert validity["components"]["record"]["value"] is True
        assert validity["components"]["permission"]["value"] is True
    assert rewards == [1.0, 1.0]
