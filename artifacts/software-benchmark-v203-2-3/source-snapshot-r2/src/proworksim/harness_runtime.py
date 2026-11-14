"""One real SDK worker step at a time; only its Executor may call the gateway."""
import copy

from .staff_runtime import StaffRuntime, PolicyBoundaryError
from .storage import digest, json_bytes
from .tool_outcomes import classify_tool_result, port_exception

VERSION = 'sdk-staff-runtime-v0.16'


class SDKStaffRuntime(StaffRuntime):
    def __init__(self, ports, workers, *, recorder=None):
        super().__init__(ports, workers, recorder=recorder)
        self._active = None

    def snapshot(self):
        result = super().snapshot()
        result.update(harness_version=VERSION,
            worker_conversations={role: worker.snapshot() for role, worker in self.policies.items()},
            workbenches={role: port.snapshot() for role, port in self.ports.items()})
        return result

    def emit(self, label, kind, payload):
        # Callback binding chooses the role; a model cannot name another role.
        if self._active and self._active['label'] != label:
            raise ValueError('A paused/other SDK worker attempted to emit in this role opportunity')
        payload = copy.deepcopy(payload)
        if self._active and isinstance(payload, dict) and kind not in {'public_tools', 'public_observation'}:
            payload.setdefault('opportunity_id', self._active['opportunity_id'])
        self.recorder.record(kind, payload, worker_id=label)

    def record_world_call(self, label, payload, association):
        self._check_active(label, association)
        record = {**copy.deepcopy(payload), **self._association(association),
                  'opportunity_id': self._active['opportunity_id']}
        self.recorder.record('tool_call', record, worker_id=label)
        response = payload.get('response', {})
        self.recorder.record('model_action_link', {**self._association(association),
            'opportunity_id': self._active['opportunity_id'], 'request_key': payload['request_key'],
            'world_action_id': response.get('action_id'), 'world_command_id': response.get('command_id'),
            'world_response': copy.deepcopy(response)}, worker_id=label)

    def record_harness_call(self, label, payload, association):
        self._check_active(label, association)
        self.recorder.record('harness_tool_call', {**copy.deepcopy(payload), **self._association(association),
            'opportunity_id': self._active['opportunity_id'],
            'scope': 'Role-private memory or declared mechanical edit; formal world calls are separately recorded'}, worker_id=label)

    @staticmethod
    def _association(association):
        return {key: association[key] for key in ('model_call_id', 'model_tool_call_id', 'decision_id') if key in association}

    def _check_active(self, label, association):
        if not self._in_step or not self._active or self._active['label'] != label:
            raise ValueError('SDK executor is outside its scheduled worker opportunity')
        if not association.get('model_call_id') or not association.get('decision_id'):
            raise ValueError('An actual model decision must precede every SDK execution')

    def execute(self, label, name, arguments, association):
        self._check_active(label, association)
        if self._active['executed']:
            raise ValueError('One opportunity cannot execute a second SDK tool')
        self._active['executed'] = True
        if (not isinstance(arguments, dict) or set(arguments) & {'request_key', 'action'}):
            raise ValueError('SDK executor received invalid public argument keys')
        decision = {'kind': {'staff_wait': 'wait', 'staff_done': 'done'}.get(name, 'act'),
                    'action': name, 'arguments': copy.deepcopy(arguments), **self._association(association)}
        self.recorder.record('policy_decision', {'decision': decision,
            'memory_before_sha256': digest(json_bytes(self.roles[label]['memory'])),
            'harness': VERSION}, worker_id=label)
        if name in {'staff_wait', 'staff_done'}:
            response = {'ok': True, 'worker_state': decision['kind'], 'reason': arguments.get('reason', ''), 'world_effect': False}
            self.record_harness_call(label, {'action': name, 'arguments': arguments,
                'response': response, 'request_key': None}, association)
        else:
            self.actions += 1
            self.roles[label]['actions'] += 1
            key = f'staff-{self.run_id}-{self.actions}'
            response = self.ports[label].call(name, request_key=key, association=association, **arguments)
        self.roles[label]['last_action'] = {'action': name, 'arguments': copy.deepcopy(arguments)}
        self.roles[label]['last_result'] = copy.deepcopy(response)
        self._active.update(decision=decision, response=copy.deepcopy(response))
        return response

    def _step(self):
        label = self.labels[self.cursor % len(self.labels)]
        self.cursor += 1
        self.opportunities += 1
        role = self.roles[label]
        role['opportunities'] += 1
        opportunity_id = f'staff-opportunity-{self.run_id}-{self.opportunities}'
        self._active = {'label': label, 'opportunity_id': opportunity_id, 'executed': False}
        try:
            try:
                tools, observation = self.ports[label].tools(), self.ports[label].observe()
                self.emit(label, 'harness_public_tools', tools)
                self.emit(label, 'harness_public_observation', observation)
            except Exception as error:
                failure = port_exception(error, operation='observation', context={'worker_id': label})
                self.emit(label, 'interface_error', failure)
                return self._finish(label, 'environment_error', 'Public interface failed', error=failure)
            identity = {key: observation.get(key) for key in ('world_id', 'instance_id', 'branch_id', 'actor_id')}
            identity['project_ids'] = sorted(observation.get('projects', {}))
            if any(not isinstance(identity[k], str) or not identity[k] for k in ('world_id', 'instance_id', 'branch_id', 'actor_id')):
                return self._finish(label, 'binding_mismatch', 'Public identity missing')
            if role['identity'] is not None and role['identity'] != identity:
                return self._finish(label, 'binding_mismatch', 'Public identity changed')
            role['identity'] = identity
            try:
                result = self.policies[label].step(observation,
                    opportunity={'run_id': self.run_id, 'worker_id': label, 'opportunity_id': opportunity_id,
                                 'opportunity_index': self.opportunities},
                    model_identity=self.policies[label].config.get('weight_identity'))
                role['memory'] = copy.deepcopy(result['memory'] if 'memory' in result else self.policies[label].snapshot())
                if result.get('kind') == 'protocol_rejection':
                    return self._finish(label, 'model_format_feedback', result.get('reason', 'Original model response rejected'), decision_consumed=True)
                if not self._active['executed']:
                    if result.get('kind') in {'done', 'wait'}:
                        self.emit(label, 'policy_decision', {'decision': {k: v for k, v in result.items() if k != 'memory'}})
                        return self._finish(label, 'completed' if result['kind'] == 'done' else 'worker_waiting', result.get('reason', 'SDK control return'))
                    raise ValueError('SDK step returned without a matched execution or declared control')
            except PolicyBoundaryError as error:
                role['memory'] = copy.deepcopy(error.memory)
                self.emit(label, 'model_boundary_error', {'type': type(error).__name__, 'status': error.status,
                    'message': str(error), **error.details})
                return self._finish(label, error.status, str(error), action_performed=self._active['executed'])
            except Exception as error:
                self.emit(label, 'interface_error', {'type': type(error).__name__, 'message': str(error),
                    'action_already_performed': self._active['executed']})
                return self._finish(label, 'environment_error', 'SDK integration failed; recorded effects retained',
                                    action_performed=self._active['executed'])
            decision, response = self._active['decision'], self._active['response']
            if decision['kind'] in {'done', 'wait'}:
                return self._finish(label, 'completed' if decision['kind'] == 'done' else 'worker_waiting', response.get('reason', decision['kind']))
            if not isinstance(response, dict) or type(response.get('ok')) is not bool:
                status = 'environment_error'
            else:
                status = ('running' if response['ok'] else 'action_rejected'
                          if response.get('error', {}).get('code') == 'harness_tool_rejected'
                          else classify_tool_result(response)['status'])
            role['status'] = status
            return {'worker_id': label, 'status': status, 'action_performed': True,
                    'response': response, 'decision': decision}
        finally:
            self._active = None
