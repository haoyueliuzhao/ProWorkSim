"""Declared v24 host identifiers; raw world identities and actions remain distinct.

No token generation, world solver, permission or numerical learner changes.
Only host-created nonbusiness names and mapping serialization are deterministic.
"""
import copy
import json
import types
import uuid
from pathlib import Path

from .collaboration_actor_v022 import FunctionalCandidateActor
from .core.journal import canonical_digest
from .experience import ExperienceRecorder, capture_port
from .online_collection import _config
from .staff_runtime import StaffRuntime
from .storage import atomic_write, digest, json_bytes
from .work_interface import WorkInterface
from .work_view_v022 import CompactWorkModelPolicy

VERSION = 'deterministic-visible-identifiers-v0.24'


def canonical(value):
    """Keep all values and list order; only mapping key order changes."""
    if isinstance(value, dict):
        return {k: canonical(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [canonical(v) for v in value]
    return value


def deterministic_tool_ids(message, request, raw):
    result = copy.deepcopy(message)
    # Actual role-local input and parsed action, not policy/checkpoint ID or
    # freeform preamble. Original raw output, arguments and token IDs are intact.
    context = {'messages': request['messages'], 'tools': request.get('tools', [])}
    for index, call in enumerate(result.get('tool_calls') or []):
        function = call['function']
        semantic_call = {'name': function['name'], 'arguments': json.loads(function['arguments'])}
        call['id'] = 'call_' + canonical_digest([VERSION, context, index, semantic_call])[:32]
    return result


class DeterministicCandidateActor(FunctionalCandidateActor):
    def parse_response(self, raw, request):
        message, error = super().parse_response(raw, request)
        return deterministic_tool_ids(message, request, raw), error


class DeterministicCompactWorkModelPolicy(CompactWorkModelPolicy):
    def __init__(self, *args, visible_namespace, **kwargs):
        super().__init__(*args, **kwargs)
        self.visible_namespace = visible_namespace

    def decide(self, context):
        # Runtime has already enforced the true instance/branch binding and
        # recorded the original public observation. Only model-visible context
        # gets stable nonbusiness names. Object/version/actor/project untouched.
        context = copy.deepcopy(context)
        for key in ('instance_id', 'branch_id'):
            context['observation'][key] = key + ':' + canonical_digest([VERSION, self.visible_namespace, key])[:24]
        context['observation'] = canonical(context['observation'])
        return super().decide(context)


def _operation_identity(self, actor, action, arguments, request_key):
    from .world_core import WorldCore
    if request_key is None:
        request_key = 'v024-host-' + canonical_digest([self._v024_namespace, self.state['state_revision'], actor, action, arguments])
    return WorldCore._operation_identity(self, actor, action, arguments, request_key)


CANONICAL_RECEIPT_VERSION = 'work-presentation-v0.24-canonical'


def canonical_response(raw, *, action, arguments, profile, project_id):
    from .presentations import MARKER, project_response
    selected, _ = project_response(raw, action=action, arguments=arguments,
                                  profile=profile, project_id=project_id, presentation='compact_v14')
    if MARKER in selected:
        selected[MARKER]['version'] = CANONICAL_RECEIPT_VERSION
        selected[MARKER]['raw_response_sha256'] = canonical_digest(raw)
    return canonical(selected)


class DeterministicWorkInterface(WorkInterface):
    def call(self, action, request_key=None, **arguments):
        super().call(action, request_key=request_key, **arguments)
        record = self.response_projections[-1]
        selected = canonical_response(record['raw_response'], action=action, arguments=arguments,
                                      profile=self.profile, project_id=self._session.project_id)
        record.update(version=CANONICAL_RECEIPT_VERSION, public_response=copy.deepcopy(selected),
                      public_response_sha256=digest(json_bytes(selected)), public_bytes=len(json_bytes(selected)),
                      raw_response_canonical_sha256=canonical_digest(record['raw_response']))
        record['reasons'].append('v24 canonical mapping keys and canonical raw receipt hash; all values and list order retained.')
        if self.audit_dir is not None:
            atomic_write(self.audit_dir / ('call-' + str(len(self.response_projections)) + '.json'), json_bytes(record))
        return selected


def runtime(owner, prepared, folder, arm='compact_work', *, episode_key=None):
    if arm != 'compact_work' or episode_key is None:
        raise ValueError('v24 requires compact_work and a predeclared same-case/seed episode_key')
    folder = Path(folder)
    namespace = [VERSION, prepared.case['case_id'], episode_key]
    prepared.world._v024_namespace = namespace
    prepared.world._operation_identity = types.MethodType(_operation_identity, prepared.world)
    policies, ports, captures, interfaces = {}, {}, {}, {}
    for role in prepared.scenario['roles']:
        label = role['role_id']
        variant = 'v23_maintenance' if prepared.case['task'] == 'maintenance' and label == 'implementer' else 'v14'
        interface = DeterministicWorkInterface(prepared.world.session(role['actor'], role['project']), label,
                                  audit_dir=folder/'public-projections'/label,
                                  variant=variant, presentation='compact_v14')
        interfaces[label] = interface
        ports[label] = capture_port(interface, captures.setdefault(label, []))
        config = _config(owner, label, role['config']['task'], prepared.case['role_decision_limits'])
        policies[label] = DeterministicCompactWorkModelPolicy(config, visible_namespace=namespace,
                           transport=owner.transport, audit_dir=folder/'model-calls'/label)
        role.update(policy='model', config=copy.deepcopy(policies[label].config))
    runtime = StaffRuntime(ports, policies, recorder=ExperienceRecorder(),
                           run_id='v024-' + canonical_digest(namespace)[:24])
    # This storage/run marker remains fresh even for paired checkpoints; the
    # actual world/branch IDs and later begin_episode UUID are never overwritten.
    record = {'version': VERSION, 'visible_namespace': namespace, 'visible_runtime_id': runtime.run_id,
              'actual_run_id': uuid.uuid4().hex, 'actual_instance_id': prepared.world.state['instance_id'],
              'actual_branch_id': prepared.world.state['branch_id'], 'storage_directory': str(folder.resolve()),
              'scope': 'Same public role history/actions yield stable host IDs. Exact object/version/permission distinctions remain; no hardware bit-determinism claim.'}
    atomic_write(folder/'visible-identity.json', json_bytes(record))
    return runtime, captures, interfaces
