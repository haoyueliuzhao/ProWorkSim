"""Finite shared-model four-project evaluation, with no teacher or auto repair."""
import copy
import json
from pathlib import Path

from .core.work import current_id
from .episode import begin_episode, finish_episode
from .experience import ExperienceRecorder, capture_port
from .harness_port import HarnessPort
from .harness_runtime import SDKStaffRuntime
from .model_policy import ModelPolicy
from .online_collection import _config
from .retail_project_rewards import assess_project_episode
from .scenarios import ScenarioController
from .staff_runtime import StaffRuntime
from .storage import atomic_write, json_bytes
from .templates.retail_projects import ACTORS
from .templates.retail_projects_v017 import build_project_case

VERSION = 'retail-project-collection-v0.17'
TOOLS = {'read_alias', 'read_version', 'read_object', 'read_messages', 'send_message',
         'write_object', 'share', 'publish', 'adopt', 'adopt_version', 'sql_build', 'sql_query',
         'preflight_submission', 'submit', 'inspect_submission', 'withdraw', 'wait'}


class ProjectPort:
    """Allowlisted actual WorldCore operations; no evaluator/filesystem escape."""
    def __init__(self, session):
        self.session = session

    def tools(self):
        return [copy.deepcopy(t) for t in self.session.tools() if t['name'] in TOOLS]

    def observe(self):
        return self.session.observe()

    def call(self, action, request_key=None, **arguments):
        if action not in {t['name'] for t in self.tools()}:
            return {'ok': False, 'error': {'code': 'project_tool_not_available', 'message': 'Action not in this role managed project interface'}}
        return self.session.call(action, request_key=request_key, **arguments)



def reactivate_new_obligation(runtime, label, old_work, new_work):
    """Dispatch one actual successor to the same worker without resetting it.

    This finite project extension targets the pinned HarnessWorker done latch;
    it is not a general SDK restart API and never changes the running H1 adapter.
    """
    if old_work == new_work or runtime.roles[label]['status'] != 'completed':
        raise ValueError('Reactivation requires a stopped worker and a distinct real obligation')
    observation = runtime.ports[label].observe()
    work = observation['work_items'].get(new_work)
    if (not work or work.get('owner_role') != observation['actor_id']
            or work.get('is_current') is not True):
        raise ValueError('New obligation is not a current visible responsibility of this worker')
    worker = runtime.policies[label]
    before = worker.snapshot() if isinstance(runtime, SDKStaffRuntime) else copy.deepcopy(runtime.roles[label]['memory'])
    if isinstance(runtime, SDKStaffRuntime):
        if worker._in_step or not worker._done:
            raise ValueError('SDK new-obligation dispatch requires its prior explicit done boundary')
        # SDK send_message/run already resumes its PAUSED or FINISHED session.
        # Only the adapter's explicit old-task done latch is released here.
        worker._done = None
        worker.conversation.send_message(json.dumps({'environment_new_obligation': {
            'old_work': old_work, 'new_work': new_work, 'budget_reset': False,
            'instruction': 'Your current public workspace now contains a new responsibility. Existing role history and budget continue.'}}))
        after = worker.snapshot()
        if (after['conversation_id'] != before['conversation_id'] or after['meter'] != before['meter']
                or after['format_errors'] != before['format_errors']):
            raise ValueError('New-obligation dispatch changed conversation identity or reset counters')
        runtime.roles[label]['memory'] = after
    else:
        after = copy.deepcopy(runtime.roles[label]['memory'])
    runtime.roles[label]['status'] = 'ready'
    runtime.roles[label].pop('reason', None)
    runtime.recorder.record('new_obligation_reactivation', {'origin': 'declared_environment_obligation',
        'old_work': old_work, 'new_work': new_work, 'budget_reset': False,
        'private_memory_reset': False, 'before': before, 'after': after,
        'model_action_generated': False, 'business_action_executed': False}, label)


def collect_project_episode(owner, case_id, output_dir, *, harness):
    """Caller provides an already selected shared owner; no model is loaded here.

    Native/SDK choice must be frozen externally before these four evaluation
    episodes. Caller must use capture_evaluation_state, begin_window/reseed,
    then finish_evaluation and finish_evaluation_guard as in software_model_v015.
    This interface never changes weights or selects a better run.
    """
    if harness not in {'native_v15', 'openhands_v16'}:
        raise ValueError('Explicit selected native/SDK harness required')
    output = Path(output_dir)
    prepared = build_project_case(case_id, output)
    identity = owner.freeze_identity()
    captured, ports, workers, holder = {}, {}, {}, {}
    recorder = ExperienceRecorder()
    for role in prepared.scenario['roles']:
        label = role['role_id']
        base = capture_port(ProjectPort(prepared.world.session(role['actor'], role['project'])), captured.setdefault(label, []))
        config = _config(owner, label, role['config']['task'], prepared.case['role_decision_limits'])
        config['budget']['max_total_tokens'] = prepared.case['role_decision_limits'][label] * owner.recipe['max_length']
        if prepared.case['changed']:
            config['task'] += ' One client-contract change is announced for after the initial project deliveries. Be available to handle the new obligation; each edition still requires your own real reads, edits, builds and submission.'
        if harness == 'native_v15':
            ports[label] = base
            workers[label] = ModelPolicy(config, transport=owner.transport, audit_dir=output / 'model-calls' / label)
        else:
            from .harness_sdk import HarnessWorker
            config['context_policy'] = 'full_history'
            ports[label] = HarnessPort(base, label, project_id=role['project'],
                public_sink=lambda kind, payload, label=label: recorder.record(kind, payload, worker_id=label),
                world_sink=lambda payload, association, label=label: holder['runtime'].record_world_call(label, payload, association),
                harness_sink=lambda payload, association, label=label: holder['runtime'].record_harness_call(label, payload, association))
            workers[label] = HarnessWorker(label, ports[label].tools(), config, transport=owner.transport,
                execute=lambda name, arguments, association, label=label: holder['runtime'].execute(label, name, arguments, association),
                event_sink=lambda kind, payload, label=label: recorder.record(kind, payload, worker_id=label),
                directory=output / 'sdk-conversations' / label)
    runtime = (SDKStaffRuntime if harness == 'openhands_v16' else StaffRuntime)(ports, workers, recorder=recorder)
    holder['runtime'] = runtime
    if any(e['kind'] in {'model_call', 'tool_call'} for e in recorder.events):
        raise ValueError('Collection initialization must not generate or act')
    recorder.events.clear()
    for rows in captured.values():
        rows.clear()
    controller = ScenarioController(prepared.deployment, recorder=recorder)
    controller.record_environment()
    episode = output / 'episode'
    begin_episode(prepared.world, episode, experience=recorder.snapshot(), work_ids=[],
                  work_nodes=[p + '::build' for p in ACTORS], scenario=prepared.scenario,
                  policies=runtime.policy_identities)
    stopped, stopped_at, results = {}, {}, []

    def current_work(label):
        base = label + '::build'
        project = prepared.world.state['projects'][label]
        return current_id(prepared.world.state, project.get('maintenance_heads', {}).get(base, base))

    termination = {'status': 'finite_project_deadline', 'untriggered_events': []}
    try:
        for sweep in range(max(prepared.case['role_decision_limits'].values()) + 1):
            effects = controller.tick()
            if any(e['status'] != 'executed' for e in effects):
                termination = {'status': 'environment_error', 'reason': 'Declared contract event rejected'}
                break
            for label in runtime.labels:
                assert runtime.labels[runtime.cursor % len(runtime.labels)] == label
                if label in stopped:
                    # A new explicit business obligation may reactivate a worker
                    # without resetting its memory, generation counter or budget.
                    if stopped[label] == 'completed' and current_work(label) != stopped_at[label]:
                        reactivate_new_obligation(runtime, label, stopped_at[label], current_work(label))
                        del stopped[label]
                    else:
                        runtime.cursor += 1
                        continue
                result = runtime.step()
                results.append(result)
                controller.record_environment()
                if result['status'] in {'completed', 'model_budget_exhausted', 'model_service_error', 'model_format_error', 'model_usage_missing', 'binding_mismatch', 'environment_error', 'policy_error'}:
                    stopped[label], stopped_at[label] = result['status'], current_work(label)
                effects = controller.tick()
                if any(e['status'] != 'executed' for e in effects):
                    raise ValueError('Declared controller effect rejected')
            response = prepared.world.session('operator').call('wait', ticks=1)
            recorder.record('controller_action', {'origin': 'environment', 'tool': 'wait', 'response': response})
            controller.record_environment()
            if not response['ok']:
                raise ValueError('Environment clock action rejected')
            atomic_write(output / 'runtime.json', json_bytes(runtime.snapshot()))
            if len(stopped) == len(runtime.labels) and all(current_work(p) == stopped_at[p] for p in stopped):
                break
        if len(stopped) == len(runtime.labels) and all(status == 'completed' for status in stopped.values()):
            termination['status'] = 'workers_done'
        termination.update(role_stops=stopped, opportunities=runtime.opportunities,
                           untriggered_events=[e['event_id'] for e in prepared.scenario['events'] if e['event_id'] not in controller.fired],
                           controller=controller.snapshot())
        finish_episode(prepared.world, episode, experience=recorder.snapshot(), termination=termination)
        assessment = assess_project_episode(episode)
        if any(s in {'model_service_error', 'model_format_error', 'model_usage_missing', 'environment_error', 'binding_mismatch', 'policy_error'} for s in stopped.values()) or termination['status'] == 'environment_error':
            assessment.update(eligible=False, reward=None, completed=None, reason='model_or_environment_execution_incomplete')
        result = {'version': VERSION, 'model_identity': identity, 'harness': harness, 'case': prepared.case,
                  'termination': termination, 'assessment': assessment,
                  'opportunities': runtime.opportunities, 'actions': runtime.actions,
                  'training_admission': 'Not implemented by this evaluation collector; no cross-project actor/critic projection claim.'}
        atomic_write(output / 'result.json', json_bytes(result))
        return result
    finally:
        atomic_write(output / 'capture.json', json_bytes(captured))
        atomic_write(output / 'runtime.json', json_bytes(runtime.snapshot()))
        if harness == 'openhands_v16':
            for worker in workers.values():
                worker.close()
