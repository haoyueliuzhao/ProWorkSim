"""Explicit managed public selections on the unchanged source/version contract."""
from __future__ import annotations

import copy
from pathlib import Path

from . import software_benchmark_world_v064 as base
from . import software_benchmark_world_v054 as tools_base
from . import software_benchmark_managed_v064 as managed_base
from . import software_organization_v042 as pages
from .repository_sources_v054 import RepositorySources, tree_manifest
from .software_benchmark_candidates_v054 import write_new
from .software_benchmark_public_tests_v110 import (
    VERSION, SELECTION_SCHEMA, SELECTION_GUIDANCE, capabilities, normalize_selection, selected_entry,
)
from .storage import digest, json_bytes
from .tool_outcomes import ToolRejection

PROJECT, MEMBERS = base.PROJECT, base.MEMBERS
validate_case, member_instruction = base.validate_case, base.member_instruction


def tool_definitions(case):
    values = base.tool_definitions(case)
    for value in values:
        if value['name'] == 'run_tests':
            value['description'] = SELECTION_GUIDANCE
            value['parameters']['properties'] = {'selection': copy.deepcopy(SELECTION_SCHEMA)}
            value['parameters']['required'] = []
    return values


class SelectedRepositorySources(RepositorySources):
    def run_public_tests(self, case_id, files, *, run_root, entry_metadata=None, selection=None):
        self.validate_files(case_id, files, entry_metadata=entry_metadata)
        if not isinstance(self.runner, PublicTestCallback):
            raise ValueError('The public selection callback is not bound')
        result = self.runner(files=copy.deepcopy(files), entry_metadata=copy.deepcopy(entry_metadata),
            task=self.runner_spec(case_id), run_root=Path(run_root), selection=selection)
        if result.get('execution', {}).get('input_tree_sha256') != tree_manifest(files, entry_metadata)['tree_sha256']:
            raise ValueError('Public test execution belongs to another complete source version')
        return result


class SoftwareCollaborationWorld(base.SoftwareCollaborationWorld):
    def _tool_definitions(self, project_id):
        return tool_definitions(self._software()['case']) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _action_run_tests(self, actor, project_id, selection=None):
        artifact, version, bundle = self._bundle(actor)
        try:
            _, chosen = selected_entry(self.public_test_entry, selection,
                files=bundle['files'], entry_metadata=bundle['entry_metadata'])
        except ValueError as error:
            raise ToolRejection(str(error), code='public_test_selection_invalid',
                                category='business_constraint') from error
        self.test_budget.consume(actor)
        public = self.source_provider.run_public_tests(self._software()['case']['case_id'], bundle['files'],
            entry_metadata=bundle['entry_metadata'], run_root=self.store.root/'software-execution/public',
            selection=chosen)
        source = tools_base._reference(artifact, version)
        result = {'groups': copy.deepcopy(public['groups']), 'public_execution': public,
            'public_diagnostics': {}, 'repository_collection_errors': public.get('repository_collection_errors', []),
            'passed': public['passed'], 'executed': public['execution']['executed'],
            'source_reference': source, 'source_sha256': digest(json_bytes(bundle)),
            'files_sha256': digest(json_bytes(bundle['files'])),
            'entry_metadata_sha256': digest(json_bytes(bundle['entry_metadata'])),
            'suite': VERSION, 'public_test_selection': chosen,
            'untested': [] if public['execution']['executed'] else ['public_repository_tests'],
            'scope': 'Model-selected public tests only; no hidden evaluator or unrestricted command',
            'independent_acceptance': 'not_run_by_public_tool', 'fixed_submission_is_acceptance': False,
            'team_test_budget': self.test_budget.snapshot()}
        event = self._event(actor, 'test', **result)
        identity = {key: self.state[key] for key in ('world_id', 'instance_id', 'branch_id')}
        identity.update(project_id=project_id, actor_id=actor, test_event_sequence=event['sequence'],
                        operation_id=event['operation_id'])
        report = pages.build_test_report(result, actor_id=actor, event_identity=identity)
        self._software()['test_reports'][report['report_id']] = report
        self._event(actor, 'test_report_saved', report_id=report['report_id'],
            test_event_sequence=event['sequence'], body_sha256=report['body_sha256'],
            source_reference=source, files_sha256=result['files_sha256'])
        return tools_base._bounded_test_page(pages.test_result_page(report))


class SoftwareCollaborationPort(base.SoftwareCollaborationPort):
    def observe(self):
        value = super().observe()
        value['public_test_selection'] = capabilities(self._session._world.public_test_entry)
        return value


class PublicTestCallback(managed_base.PublicTestCallback):
    def __init__(self, callback, *, entry, **kwargs):
        super().__init__(callback, **kwargs)
        self.entry = copy.deepcopy(entry)

    def __call__(self, *, files, entry_metadata, task, run_root, selection=None):
        if self.world is None or self.clock() >= self.hard_at:
            raise ValueError('Only the live bounded public callback may run selected tests')
        artifact, version, bundle = self.world._bundle(MEMBERS[0])
        tree = tree_manifest(files, entry_metadata)['tree_sha256']
        if tree_manifest(bundle['files'], bundle['entry_metadata'])['tree_sha256'] != tree:
            raise ValueError('Selected public tests must use the exact current managed source version')
        entry, chosen = selected_entry(self.entry, selection, files=files, entry_metadata=entry_metadata)
        self.calls += 1
        request = {'version': VERSION, 'instance_id': self.instance_id, 'call_index': self.calls,
            'source_reference': {'object_id': artifact['artifact_id'], 'version_id': version},
            'tree_sha256': tree, 'hard_deadline_monotonic': self.hard_at,
            'hidden_evaluation': False, 'arbitrary_command': False,
            'public_test_selection_revision': VERSION, 'public_test_selection': chosen}
        folder = self.folder/f'test-{self.calls:04d}'
        folder.mkdir(parents=True, exist_ok=False)
        write_new(folder/'request.json', request)
        result = self.callback(files=copy.deepcopy(files), entry_metadata=copy.deepcopy(entry_metadata),
                               request=copy.deepcopy(request))
        write_new(folder/'response.json', result)
        execution = result.get('execution', {})
        if (execution.get('input_tree_sha256') != tree or type(execution.get('executed')) is not bool
                or type(result.get('passed')) is not bool or not isinstance(result.get('groups'), dict)
                or execution.get('public_test_selection') != chosen
                or execution.get('public_test_selection_revision') != VERSION
                or result['passed'] and not execution['executed']
                or execution['executed'] and execution.get('argv') != entry['argv']):
            raise ValueError('Selected public-test receipt lost its exact source, selection or actual argv')
        return result


def prepare_case(source_manifest, folder, *, max_total_tokens, public_test_callback,
                 deadline, public_test_entry):
    """Prepare a fresh managed world only; no model, tests or submission occurs."""
    provider = SelectedRepositorySources(source_manifest)
    if len(provider.case_ids) != 1:
        raise ValueError('One managed controller receives exactly one public task')
    task = provider.case_ids[0]
    if public_test_entry.get('instance_id') != task:
        raise ValueError('The selected-test entry belongs to another task')
    selected_entry(public_test_entry, normalize_selection())
    callback = PublicTestCallback(public_test_callback, entry=public_test_entry, instance_id=task,
        hard_at=deadline.hard_at, folder=Path(folder).parent/'public-test-rpc', clock=deadline.clock)
    provider.runner = callback
    prepared = base.build_software_collaboration_case(task, folder, provider=provider,
                                                    max_total_tokens=max_total_tokens)
    prior = prepared.world
    world = SoftwareCollaborationWorld(prior.store.root)
    world.source_provider, world.test_budget = provider, prior.test_budget
    world.public_test_entry = copy.deepcopy(public_test_entry)
    prepared.deployment.world = world
    prepared.port_factory = SoftwareCollaborationPort
    callback.bind_world(prepared)
    write_new(Path(folder)/'public-test-selection.json', {
        'version': VERSION, 'entry': public_test_entry, 'capabilities': capabilities(public_test_entry),
        'model_calls': 0, 'test_executions': 0, 'hidden_evaluation_calls': 0})
    return prepared
