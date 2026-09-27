"""Bounded real-world/native-adapter controls, with an explicitly fake model."""
import argparse
import copy
import json
from pathlib import Path

from proworksim.episode import begin_episode, finish_episode
from proworksim.online_collection import run_fragment
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.templates import retail_collaboration_v022 as world
from proworksim.work_view_v022 import runtime


class FakeOwner:
    """No model/API/GPU; responses exercise real ModelPolicy and WorldCore."""
    recipe = {'temperature': .7, 'max_output_tokens': 2048, 'max_length': 16384}

    def __init__(self):
        self.requests = []
        self.transport = self

    def freeze_identity(self):
        return {'policy_version': 'explicit-cpu-fake-v022'}

    def complete(self, request, *, timeout_seconds):
        self.requests.append(copy.deepcopy(request))
        index = len(self.requests) - 1
        message = json.loads(request['messages'][-1]['content'])
        observation = message['observation']
        aliases = observation['workspaces']['TEAM']
        wid = world.WORK
        sid = observation['work_items'][wid]['pending_submission_id']
        operations = [
            ('staff_wait', {'reason': 'Explicit CPU wait control, no world effect'}),
            None,
            ('inspect_submission', {'work_id': wid, 'submission_id': sid, 'include_contract': True}),
            ('read_version', {'work_id': wid, 'reference': {'object_id': aliases['code'], 'version_id': 'v2'}}),
            ('read_version', {'work_id': wid, 'reference': {'object_id': aliases['result'], 'version_id': 'v2'}}),
            ('read_version', {'work_id': wid, 'reference': {'object_id': aliases['data'], 'version_id': 'v1'}}),
            ('read_version', {'work_id': wid, 'reference': {'object_id': aliases['audit_basis'], 'version_id': 'v1'}}),
            ('raise_issue', {'work_id': wid, 'submission_id': sid, 'issue_key': 'cpu-actual-count-disagreement',
                             'object_id': aliases['result'], 'version_id': 'v2', 'locator': ['tables', 'metrics', 'rows', 0, 2],
                             'description': 'CPU negative/positive contract control: prepared count cell disagrees with exact invoice grain.',
                             'evidence': [{'object_id': aliases['data'], 'version_id': 'v1'}, {'object_id': aliases['audit_basis'], 'version_id': 'v1'}]}),
            ('staff_done', {'reason': 'Explicit CPU control finished'}),
        ]
        operation = operations[index]
        if operation is None:
            answer = {'role': 'assistant', 'content': 'EXPLICIT_FAKE_TRUNCATED_OUTPUT ' * 40}
            finish = 'length'
        else:
            name, args = operation
            answer = {'role': 'assistant', 'content': 'EXPLICIT_FAKE_PREAMBLE ' * 40,
                      'tool_calls': [{'id': 'cpu-call-' + str(index), 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}
            finish = 'tool_calls'
        body = {'choices': [{'message': answer, 'finish_reason': finish}], 'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}
        return {'http_status': 200, 'body': body, 'raw_body': json.dumps(body), 'headers': {}}


def run_control(output, arm):
    output = Path(output)
    case = world.registry()['situations'][3]
    prepared = world.build_case(case, output)
    owner = FakeOwner()
    runner, capture, _ = runtime(owner, prepared, output, arm)
    episode = output / 'episode'
    begin_episode(prepared.world, episode, experience=runner.recorder.snapshot(), work_ids=[world.WORK], scenario=prepared.scenario, policies=runner.policy_identities)
    boundary = run_fragment(prepared, runner)
    finish_episode(prepared.world, episode, experience=runner.recorder.snapshot(), termination=boundary)
    score = world.assess_episode(episode)
    memory = runner.roles['reviewer']['memory']
    original = json_bytes(memory)
    selected, audit = runner.policies['reviewer']._select_messages(memory)
    if json_bytes(memory) != original:
        raise AssertionError('Presentation changed original role memory')
    calls = [e for e in runner.recorder.events if e['kind'] == 'tool_call']
    format_events = [e for e in runner.recorder.events if e['kind'] == 'model_format_feedback']
    result = {'arm': arm, 'scope': 'Explicit fake responses, actual ModelPolicy/StaffRuntime/WorldCore. Not real model support or a W1 target-model episode.',
              'model_calls': 0, 'fake_transport_calls': len(owner.requests), 'world_actions': len(calls),
              'actual_wait_recorded': any(e['kind'] == 'policy_decision' and e['payload']['decision']['kind'] == 'wait' for e in runner.recorder.events),
              'format_failure_retained': len(format_events) == 1 and format_events[0]['payload']['feedback']['world_action_executed'] is False,
              'closed': boundary, 'assessment': score, 'request_bytes': [len(json_bytes(r)) for r in owner.requests],
              'initial_business_state_sha256': prepared.prefix['prepared_business_state_sha256'],
              'memory_unchanged_by_selection': True, 'final_selection': audit,
              'selected_tool_messages_unchanged': all(message in memory['messages'] for message in selected if message.get('role') == 'tool')}
    result['passed'] = bool(score['eligible'] and score['reward'] == 1 and result['actual_wait_recorded'] and result['format_failure_retained'] and result['selected_tool_messages_unchanged'] and len(calls) == 6)
    atomic_write(output / 'capture.json', json_bytes(capture))
    atomic_write(output / 'requests.json', json_bytes(owner.requests))
    atomic_write(output / 'control.json', json_bytes(result))
    return result


def main(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    rows = [run_control(output / arm, arm) for arm in world.ARMS]
    report = {'version': 'work-view-cpu-controls-v0.22', 'arms': rows,
              'same_initial_business_state': rows[0]['initial_business_state_sha256'] == rows[1]['initial_business_state_sha256'],
              'source_manifest_sha256': digest(world.PIN_PATH.read_bytes()), 'model_calls': 0,
              'passed': all(r['passed'] for r in rows) and rows[0]['initial_business_state_sha256'] == rows[1]['initial_business_state_sha256']}
    atomic_write(output / 'report.json', json_bytes(report))
    print(json.dumps({'passed': report['passed'], 'arms': [{'arm': r['arm'], 'score': r['assessment']['reward'], 'requests': r['fake_transport_calls'], 'max_request_bytes': max(r['request_bytes']), 'exclusions': r['assessment']['exclusions']} for r in rows]}))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    raise SystemExit(0 if main(args.output)['passed'] else 1)
