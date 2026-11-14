"""Fixed v104 organization rules with the v130 managed repository interface."""
from __future__ import annotations

import copy
from pathlib import Path
from types import FunctionType

from . import software_fixed_organization_rules_v131 as organization_world
from . import software_benchmark_tooling_v130 as tooling
from .software_benchmark_alignment_contract_v131 import GROUP_IDS, organization
from .software_benchmark_public_tests_v110 import capabilities, normalize_selection, selected_entry
from .software_benchmark_candidates_v054 import write_new
from .repository_sources_v054 import tree_manifest
from .scenarios import initial_business_state
from .storage import atomic_write, digest, json_bytes

VERSION = 'v131-fixed-organization-managed-world-r1'
PURPOSE = 'fixed_organization_frozen_model_evaluation_v131'
PROJECT = organization_world.PROJECT
MEMBER_POOL = ('member_001', 'member_002', 'member_003', 'member_004')


def _bind(function, **bindings):
    result = FunctionType(function.__code__, {**function.__globals__, **bindings},
                          function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = dict(function.__kwdefaults__ or {})
    return result


def case_spec(case_id, *, provider, organization_id, max_total_tokens,
              max_decisions=512, max_test_runs=512):
    if organization_id not in GROUP_IDS or (max_total_tokens, max_decisions, max_test_runs) != (5_000_000, 512, 512):
        raise ValueError('Only the explicitly frozen five organization/shared-budget conditions are allowed')
    value = organization_world.case_spec(case_id, provider=provider,
        organization_id=organization_id, max_total_tokens=max_total_tokens,
        max_decisions=max_decisions, max_test_runs=max_test_runs)
    if value['fixed_organization'] != organization(organization_id):
        raise ValueError('The organization contract differs from the frozen evaluation condition')
    value.update(version=VERSION, interface_revision=VERSION, purpose=PURPOSE,
        usage=PURPOSE, category=PURPOSE, split=PURPOSE,
        scheduling_protocol='v131-state-gated-fixed-member-opportunities',
        future_budget_selection='Frozen v131 total team budget; this constructor grants no external resources',
        runtime_authority='A separate v131 host grant is required; old offline switches are not used',
        public_test_selection_revision='v110-public-test-selection-r1',
        public_validation_revision='v130-public-test-execution-evidence-r1')
    return value


def validate_case(case, *, provider):
    expected = case_spec(case['case_id'], provider=provider,
        organization_id=case['fixed_organization']['id'],
        max_total_tokens=case['team_limits']['max_total_tokens'],
        max_decisions=case['team_limits']['max_decisions'],
        max_test_runs=case['team_limits']['max_test_runs'])
    if case != expected:
        raise ValueError('The fixed organization, source or shared team allowances changed')
    return case


def member_instruction(case, member):
    return (organization_world.member_instruction(case, member) + '\n' + tooling.previous.previous.NAVIGATION
        + '\nYour first staff_done request may receive one final self-review in this same private '
          'conversation, within the shared remaining team budget. An accepted staff_done ends only '
          'your current work; a later real visible event may wake your same session. It does not '
          'end the team, submit a patch, grant review authority or reset your review allowance.')


def tool_definitions(case):
    members = tuple(case['active_roles'])
    tools = [tool for tool in tooling.tool_definitions(case)
             if tool['name'] not in organization_world.previous.DYNAMIC_TOOLS]
    names = {tool['name'] for tool in tools}
    for tool in tools:
        for field in ('recipient', 'to_member'):
            prop = tool['parameters'].get('properties', {}).get(field)
            if isinstance(prop, dict):
                prop['enum'] = list(members)
        if tool['name'] == 'run_tests':
            tool['description'] += ' The 512 accepted public-test calls are shared by the entire fixed team.'
        elif tool['name'] == 'handoff_patch':
            tool['description'] += ' Only a declared communication edge is legal; this notice does not copy private edits or integrate code.'
    tools += [copy.deepcopy(tool) for tool in organization_world.tool_definitions(case)
              if tool['name'] not in names]
    return tooling._independent_tree(tools)


def schema_case(group):
    spec = organization(group)
    return {'fixed_organization': spec, 'active_roles': list(spec['fixed_members']),
            'team_limits': {'max_test_runs': 512},
            'member_limits': {'max_live_members': spec['member_count'], 'births_enabled': False}}


class SoftwareCollaborationWorld(organization_world.SoftwareCollaborationWorld,
                                 tooling.SoftwareCollaborationWorld):
    def _tool_definitions(self, project_id):
        return tool_definitions(self._software()['case']) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _action_run_tests(self, actor, project_id, selection=None):
        if getattr(self, '_active_public_test_actor', None) is not None:
            raise ValueError('Public execution must remain single-writer for this fixed team')
        self._active_public_test_actor = actor
        try:
            return tooling.SoftwareCollaborationWorld._action_run_tests(self, actor, project_id, selection)
        finally:
            self._active_public_test_actor = None

    def _action_submit_integration(self, actor, project_id, **arguments):
        # These are the same pure guards already used by the ordinary dispatch.
        # Freeze their exact pre-submit state, rather than reinterpreting a later
        # organization state after another review, task revision or private edit.
        self._org_guard_governance(actor, 'submit_integration', arguments)
        self._org_guard_flow(actor, 'submit_integration', arguments)
        facts = self._software()
        current = self.org_current_identity(actor)
        proof = {'version': VERSION, 'organization_id': self.org_kind(),
            'fixed_members': list(facts['case']['active_roles']), 'actor_id': actor,
            'source_reference': copy.deepcopy(current['source_reference']),
            'organization_state': copy.deepcopy(facts['organization_state']),
            'tasks': copy.deepcopy(facts['tasks']), 'patches': copy.deepcopy(facts['patches']),
            'fixed_organization': copy.deepcopy(facts['case']['fixed_organization']),
            'accepted_guard': 'unchanged_v104_governance_and_flow_submit_guards',
            'guard_state_sha256': digest(json_bytes([facts['organization_state'], facts['tasks'], facts['patches']]))}
        result = super()._action_submit_integration(actor, project_id, **arguments)
        delivery = self._software()['deliveries'][-1]
        if delivery['actor_id'] != actor or delivery['source_reference'] != proof['source_reference']:
            raise ValueError('Accepted delivery differs from its pre-submit organization proof')
        proof['delivery_id'] = delivery['delivery_id']
        self._software().setdefault('organization_delivery_proofs_v131', {})[delivery['delivery_id']] = proof
        return result


class SoftwareCollaborationPort(organization_world.SoftwareCollaborationPort):
    def observe(self):
        value = super().observe()
        world = self._session._world
        value.update(profile=VERSION, interface_revision=VERSION, purpose=PURPOSE,
            tooling_revision=tooling.VERSION,
            public_test_selection=capabilities(world.public_test_entry))
        value['tool_navigation']['source_selection'] = tooling.previous.previous.NAVIGATION
        value['scheduling']['protocol'] = 'v131-state-gated-fixed-member-opportunities'
        return value


_raw_build = _bind(organization_world._raw_build,
    VERSION=VERSION, PURPOSE=PURPOSE, case_spec=case_spec, validate_case=validate_case,
    member_instruction=member_instruction, SoftwareCollaborationWorld=SoftwareCollaborationWorld,
    SoftwareCollaborationPort=SoftwareCollaborationPort)


def build_software_collaboration_case(*args, **kwargs):
    prepared = _raw_build(*args, **kwargs)
    world = prepared.world
    with world.store.lock():
        world.state = world.store.load()
        group = world.org_kind()
        world._software()['organization_state'] = {
            'version': organization_world.VERSION, 'organization_id': group,
            'opportunities_consumed': 0,
            **organization_world.governance.initial_state(group),
            **organization_world.flow.initial_state(group)}
        world._software()['organization_delivery_proofs_v131'] = {}
        world.store.save(world.state)
    prepared.prefix['prepared_business_state_sha256'] = digest(json_bytes(initial_business_state(world)))
    prepared.prefix['organization_runtime_revision'] = VERSION
    atomic_write(Path(world.store.root).parent/'preparation.json', json_bytes(prepared.prefix))
    return prepared


class PublicTestCallback(tooling.PublicTestCallback):
    def __call__(self, *, files, entry_metadata, task, run_root, selection=None):
        if self.world is None or self.clock() >= self.hard_at:
            raise ValueError('The team public test requires its live original deadline')
        actor = getattr(self.world, '_active_public_test_actor', None)
        if actor not in self.world._software()['case']['active_roles']:
            raise ValueError('An actual scheduled member must own this public test')
        artifact, version, current = self.world._bundle(actor)
        tree = tree_manifest(files, entry_metadata)['tree_sha256']
        if tree_manifest(current['files'], current['entry_metadata'])['tree_sha256'] != tree:
            raise ValueError('Public test payload differs from this member private version')
        entry, chosen = selected_entry(self.entry, selection, files=files, entry_metadata=entry_metadata)
        self.calls += 1
        request = {'version': VERSION, 'instance_id': self.instance_id, 'actor_id': actor,
            'organization_id': self.world.org_kind(),
            'call_index': self.calls, 'source_reference': {'object_id': artifact['artifact_id'], 'version_id': version},
            'tree_sha256': tree, 'hard_deadline_monotonic': self.hard_at,
            'hidden_evaluation': False, 'arbitrary_command': False,
            'public_test_selection_revision': 'v110-public-test-selection-r1', 'public_test_selection': chosen}
        folder = self.folder/f'test-{self.calls:04d}'
        folder.mkdir(parents=True, exist_ok=False)
        write_new(folder/'request.json', request)
        result = self.callback(files=copy.deepcopy(files), entry_metadata=copy.deepcopy(entry_metadata),
                               request=copy.deepcopy(request))
        write_new(folder/'response.json', result)
        execution = result.get('execution', {})
        if (execution.get('input_tree_sha256') != tree or type(execution.get('executed')) is not bool
                or execution.get('actor_id') != actor
                or execution.get('organization_id') != self.world.org_kind()
                or execution.get('managed_request_sha256') != digest(json_bytes(request))
                or type(result.get('passed')) is not bool or not isinstance(result.get('groups'), dict)
                or execution.get('public_test_selection') != chosen
                or execution.get('public_test_selection_revision') != 'v110-public-test-selection-r1'
                or result['passed'] and not execution['executed']
                or execution['executed'] and execution.get('argv') != entry['argv']):
            raise ValueError('Team public-test receipt lost its exact source/selection/argv')
        return result


def prepare_case(source_manifest, folder, *, organization_id, max_total_tokens,
                 public_test_callback, deadline, public_test_entry, max_decisions=512, max_test_runs=512):
    provider = tooling.previous.previous.public_world.SelectedRepositorySources(source_manifest)
    if len(provider.case_ids) != 1 or public_test_entry.get('instance_id') != provider.case_ids[0]:
        raise ValueError('One team receives exactly one unchanged public task')
    selected_entry(public_test_entry, normalize_selection())
    callback = PublicTestCallback(public_test_callback, entry=public_test_entry,
        instance_id=provider.case_ids[0], hard_at=deadline.hard_at,
        folder=Path(folder).parent/'public-test-rpc', clock=deadline.clock)
    provider.runner = callback
    prepared = build_software_collaboration_case(provider.case_ids[0], folder, provider=provider,
        organization_id=organization_id, max_total_tokens=max_total_tokens,
        max_decisions=max_decisions, max_test_runs=max_test_runs)
    prepared.world.public_test_entry = copy.deepcopy(public_test_entry)
    callback.bind_world(prepared)
    write_new(Path(folder)/'team-public-test-selection.json', {'version': VERSION,
        'entry': public_test_entry, 'capabilities': capabilities(public_test_entry),
        'fixed_members': list(prepared.case['active_roles']), 'shared_test_limit': max_test_runs,
        'model_calls': 0, 'test_executions': 0})
    return prepared
