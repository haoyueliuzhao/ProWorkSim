"""Independent managed schema fields and source-bound public-test status.

Keep v120's action, accounting and nullable/JSON-equivalence behavior. Only the
incorrect read_file.path description changes in the published tool inventory;
all mutable schema occurrences are copied independently before decoration.
"""
from __future__ import annotations

import copy
from types import FunctionType, SimpleNamespace

from . import software_benchmark_tooling_v120 as previous

VERSION = 'v130-independent-managed-schema-and-public-validation-status-r1'
PROJECT, MEMBERS = previous.PROJECT, previous.MEMBERS
validate_case, member_instruction = previous.validate_case, previous.member_instruction
PublicTestCallback = previous.PublicTestCallback
ToolFeedbackWorkerMixin = previous.ToolFeedbackWorkerMixin
CURSOR_TOOLS = previous.CURSOR_TOOLS
canonical_arguments = previous.canonical_arguments
NullableCursorExecutor = previous.NullableCursorExecutor
install_nullable_cursors = previous.install_nullable_cursors

PATH_DESCRIPTION = (
    'Exact repository-relative file path copied from list_files or search_repository, '
    'for example src/module.py. This is a file path, not a published patch ID. '
    'Omit patch_id to read the current workspace; use an actual published patch_id '
    'only when explicitly reading its fixed source tree.'
)


def schema_inventory_case():
    """Fresh minimal S1 inventory fixture, not an executable benchmark case."""
    return {'member_limits': {'max_live_members': 1, 'births_enabled': False}}


def _independent_tree(value):
    # deepcopy deliberately memoizes repeated object identities. Here each
    # occurrence needs its own mutable object, including within the same tool.
    if isinstance(value, dict):
        return {key: _independent_tree(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_independent_tree(child) for child in value]
    if isinstance(value, tuple):
        return tuple(_independent_tree(child) for child in value)
    return copy.deepcopy(value)


def _private(function, **bindings):
    result = FunctionType(function.__code__, {**function.__globals__, **bindings},
                          function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = dict(function.__kwdefaults__ or {})
    return result


def _isolated_base_definitions(case):
    return _independent_tree(previous.previous.public_world.tool_definitions(case))


_decorate_definitions = _private(previous.previous.tool_definitions,
    public_world=SimpleNamespace(tool_definitions=_isolated_base_definitions))


def tool_definitions(case):
    values = _decorate_definitions(case)
    read_file = next(tool for tool in values if tool['name'] == 'read_file')
    read_file['parameters']['properties']['path']['description'] = PATH_DESCRIPTION
    return values


class SoftwareCollaborationWorld(previous.previous.SoftwareCollaborationWorld):
    def _tool_definitions(self, project_id):
        if project_id == PROJECT:
            return tool_definitions(self._software()['case'])
        return super()._tool_definitions(project_id)

    def _validation_status_page(self, actor, page):
        """Surface only facts already stored in this actor's immutable report."""
        report_id = page.get('report_id')
        report = self._software()['test_reports'].get(report_id)
        if report is None or report.get('actor_id') != actor:
            raise ValueError('Public validation status requires the same authorized saved report')
        visible = report['visible_result']
        if page.get('source_reference') != visible.get('source_reference'):
            raise ValueError('Public validation status cannot describe another source version')
        execution = visible.get('public_execution', {}).get('execution', {})
        if 'validation_status' not in execution:
            # Existing CPU fixtures or historical reports have no structured
            # count evidence. Do not invent a status or turn execution into a pass.
            return page
        result = dict(page)
        result.update({key: copy.deepcopy(execution[key])
                       for key in ('validation_status', 'counts', 'test_evidence')
                       if key in execution})
        result['command_executed'] = execution.get('command_executed', execution.get('executed'))
        return result

    def _action_run_tests(self, actor, project_id, selection=None):
        page = super()._action_run_tests(actor, project_id, selection=selection)
        return self._validation_status_page(actor, page)

    def _action_read_test_result(self, actor, project_id, report_id, cursor=None):
        page = super()._action_read_test_result(actor, project_id, report_id, cursor=cursor)
        return self._validation_status_page(actor, page)


class SoftwareCollaborationPort(previous.SoftwareCollaborationPort):
    def observe(self):
        result = super().observe()
        result['tooling_revision'] = VERSION
        return result


# Run the original fresh-world construction with these explicit local bindings.
# The single callback is bound once to the new world before it is returned.
prepare_case = _private(previous.prepare_case,
    SoftwareCollaborationWorld=SoftwareCollaborationWorld,
    SoftwareCollaborationPort=SoftwareCollaborationPort,
    tool_definitions=tool_definitions, VERSION=VERSION)
