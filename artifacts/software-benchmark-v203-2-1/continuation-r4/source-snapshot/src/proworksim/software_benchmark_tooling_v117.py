"""Managed source navigation and actionable rejections, without inferred actions.

New worlds only. Source permissions, atomic mutations, unique replacements,
public-test accounting and explicit same-version delivery are inherited intact.
"""
from __future__ import annotations

import copy
from pathlib import Path, PurePosixPath

from . import software_benchmark_public_test_world_v110 as public_world
from . import software_benchmark_world_v054 as source_tools
from . import software_benchmark_world_v064 as source_world
from .software_benchmark_candidates_v054 import write_new
from .software_benchmark_public_tests_v110 import capabilities, normalize_selection, selected_entry
from .storage import digest, json_bytes
from .tool_outcomes import ToolRejection
from .work_interface import _schema_errors

VERSION = 'v117-managed-source-navigation-recovery-r1'
PROJECT, MEMBERS = public_world.PROJECT, public_world.MEMBERS
validate_case = public_world.validate_case
PublicTestCallback = public_world.PublicTestCallback

PATCH_DESCRIPTION = (
    'Optional immutable published patch ID copied from fix_patch or observation.all_fixed_patches, '
    'for example patch-1. Omit for your CURRENT workspace. It is NOT a directory, object_id, '
    'version_id or placeholder. An unknown ID is rejected, never treated as the workspace.'
)
NAVIGATION = (
    'list_files() lists the current workspace; list_files(path_prefix="tests") lists that '
    'directory. Omit patch_id unless inspecting an actual published patch. Paths are exact '
    'repository-relative names. Follow next_cursor unchanged with the same tool/query/source; '
    'restart without cursor after editing. read_test_result(report_id) restarts an existing '
    'saved report without rerunning tests; its cursors stay bound to that report even after edits. '
    'A failed action changes no source. Use create_file for a new path; replace_file needs one '
    'exact nonempty occurrence, including whitespace. Plain assistant text executes nothing: '
    'use one declared function, or staff_done(reason) when requesting completion.'
)
NO_TOOL_REASON = 'Exactly one native tool call; no-tool text is not implicit done'
NO_TOOL_RECOVERY = (
    NO_TOOL_REASON + '. No action or completion was performed. On a later allowed opportunity, '
    'send exactly one declared function call with JSON arguments. To request completion, call '
    'staff_done with a nonempty reason; to continue, call one permitted work tool. A prose '
    'statement that work is finished does not submit or end it. This rejection consumed the '
    'current decision and actual tokens; no automatic retry, test or submission occurs.'
)
CURSOR_TOOLS = frozenset({'list_files', 'read_file', 'search_file', 'diff_workspace',
                          'read_task', 'search_repository'})


def member_instruction(case):
    return public_world.member_instruction(case) + '\n' + NAVIGATION


def tool_definitions(case):
    values = public_world.tool_definitions(case)
    for tool in values:
        name, properties = tool['name'], tool['parameters']['properties']
        if name in {'list_files', 'read_file'}:
            properties['patch_id']['description'] = PATCH_DESCRIPTION
        if name == 'list_files':
            properties['path_prefix'] = {'type': 'string', 'minLength': 1,
                'description': 'Optional exact repository-relative file or directory; e.g. tests. '
                    'Omit for all entries. A trailing slash is allowed; no glob, absolute path or .. .'}
            tool['description'] = (
                'List at most 40 entries from your CURRENT workspace, optionally under path_prefix. '
                'Omit patch_id for current files; only an actual fixed patch ID selects a published tree. '
                'Follow next_cursor with the same path_prefix and patch_id. Editing the current tree '
                'invalidates its old cursors. No directory name belongs in patch_id.')
        elif name == 'read_file':
            tool['description'] += ' path must be an exact listed repository-relative file; omit patch_id for current source.'
        elif name == 'replace_file':
            tool['description'] = (
                'Replace exactly one nonempty literal occurrence in the current UTF-8 file. '
                'No regex or fuzzy matching. If zero matches, read current text; if multiple, '
                'include exact surrounding text to make old unique. A rejection performs no edit.')
        elif name == 'read_test_result':
            tool['parameters']['required'] = ['report_id']
            properties['cursor']['description'] = (
                'Copy page.next_cursor exactly from this saved report, or omit to restart its first '
                'page. Do not construct page numbers or reuse another report cursor. No tests run.')
            tool['description'] = (
                'Read one exact saved page of your own report. Omit cursor for its first page; '
                'copy page.next_cursor for continuation. Old reports remain readable after edits '
                'but do not prove the current version. Never reruns tests.')
    return values


def _reject(message, code, **context):
    raise ToolRejection(message, code=code, category='business_constraint',
                        context={'tooling_revision': VERSION, **context})


def _prefix(path_prefix):
    return None if path_prefix is None else source_tools._safe_path(path_prefix.rstrip('/'))


class SoftwareCollaborationWorld(public_world.SoftwareCollaborationWorld):
    def _tool_definitions(self, project_id):
        return tool_definitions(self._software()['case']) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _patch(self, patch_id):
        if patch_id not in self._software()['patches']:
            _reject('Unknown published patch. Omit patch_id for current files; use path_prefix '
                    'for a directory. Only copy a patch_id returned by fix_patch or all_fixed_patches.',
                    'published_patch_not_found', requested_patch_id=patch_id,
                    automatic_source_fallback=False,
                    recovery={'tool': 'list_files', 'arguments': {},
                              'purpose': 'Explicitly inspect your current workspace instead'})
        return super()._patch(patch_id)

    @staticmethod
    def _text_entry(bundle, path):
        source_tools._safe_path(path)
        if path not in bundle['files']:
            parent = str(PurePosixPath(path).parent)
            arguments = {} if parent == '.' else {'path_prefix': parent}
            _reject('Path is absent from this source version. Copy an exact path from list_files '
                    'or search_repository. To create a new file, explicitly use create_file; '
                    'write_file only replaces an existing file.', 'source_path_not_found',
                    requested_path=path, automatic_path_substitution=False,
                    recovery={'tool': 'list_files', 'arguments': arguments,
                              'purpose': 'Find actual names; omit path_prefix if the directory is absent'})
        return source_tools.SoftwareCollaborationWorld._text_entry(bundle, path)

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        # The inherited validator still owns member/schema/permission checks and
        # dispatches exactly once. Only known cursor failures gain recovery facts.
        try:
            return super()._tool_project_action(actor, project_id, tool, arguments, interface_profile)
        except ToolRejection as error:
            if (error.rejection['code'] == 'source_path_not_found'
                    and tool == 'read_file' and arguments.get('patch_id') is not None):
                context = copy.deepcopy(error.rejection['context'])
                context['recovery']['arguments']['patch_id'] = arguments['patch_id']
                raise ToolRejection(str(error), code=error.rejection['code'],
                    category=error.rejection['category'], context=context) from error
            raise
        except ValueError as error:
            if (tool not in {'list_files', 'read_file', 'search_file', 'search_repository',
                             'diff_workspace', 'read_task'} or str(error) not in {
                    'Cursor belongs to another operation or source version',
                    'Cursor is outside the saved content',
                    'Search cursor belongs to another member, query or source version'}):
                raise
            restart = {key: copy.deepcopy(value) for key, value in arguments.items() if key != 'cursor'}
            _reject(str(error) + '. Restart this same tool without cursor, then copy its returned '
                    'next_cursor exactly. Keep source and query unchanged between pages.',
                    'source_cursor_invalid', automatic_retry=False,
                    recovery={'tool': tool, 'arguments': restart})

    def _action_list_files(self, actor, project_id, patch_id=None, cursor=None, path_prefix=None):
        artifact, version, bundle = self._bundle(actor, patch_id=patch_id)
        reference = source_tools._reference(artifact, version)
        prefix = _prefix(path_prefix)
        identity = {'actor': actor, 'tool': 'list_files', 'source_reference': reference,
                    'path_prefix': prefix}
        paths = sorted(path for path in bundle['files']
                       if prefix is None or path == prefix or path.startswith(prefix + '/'))
        start = source_tools._position(cursor, identity, len(paths))
        policy = self._software()['case']['file_policy']
        rows = source_tools._bounded_rows({'path': path,
            'editable': not source_tools._readonly(path, policy), **bundle['entry_metadata'][path]}
            for path in paths[start:])
        stop = start + len(rows)
        return {'source_reference': reference, 'source_kind': 'published_patch' if patch_id else 'current_workspace',
                'patch_id': patch_id, 'path_prefix': prefix, 'files': rows, 'total_files': len(paths),
                'repository_total_files': len(bundle['files']),
                'next_cursor': source_tools._cursor(identity, stop) if stop < len(paths) else None,
                'complete': stop == len(paths)}

    def _action_replace_file(self, actor, project_id, path, old, new):
        artifact, version, bundle = self._bundle(actor, write=True)
        self._writable(path)
        text = self._text_entry(bundle, path)
        count = text.count(old) if old else 0
        if not old or count != 1:
            _reject('Replacement requires one exact nonempty occurrence; found ' + str(count) +
                    '. Read the current file, preserve whitespace, and add surrounding text if '
                    'multiple matches exist. No occurrence was selected and no edit was made.',
                    'replacement_not_unique', requested_path=path, exact_occurrences=count,
                    source_reference=source_tools._reference(artifact, version),
                    automatic_match_selection=False,
                    recovery={'tool': 'read_file', 'arguments': {'path': path}})
        return self._write_file(actor, path, text.replace(old, new, 1), artifact, version, bundle)

    def _action_read_test_result(self, actor, project_id, report_id, cursor=None):
        report = self._software()['test_reports'].get(report_id)
        # Never reveal a page/cursor from another member or unknown report.
        if report is None or report['actor_id'] != actor:
            return super()._action_read_test_result(actor, project_id, report_id, cursor)
        if cursor is not None and not any(page['cursor'] == cursor for page in report['pages']):
            _reject('The cursor does not identify a page of this saved report. Omit cursor to '
                    'restart this same report, then copy page.next_cursor. Do not rerun tests '
                    'to recover a page; edits do not invalidate saved report cursors.',
                    'test_report_cursor_invalid', report_id=report_id, test_rerun=False,
                    recovery={'tool': 'read_test_result', 'arguments': {'report_id': report_id}})
        return super()._action_read_test_result(actor, project_id, report_id, cursor)


class SoftwareCollaborationPort(public_world.SoftwareCollaborationPort):
    def observe(self):
        value = super().observe()
        value['tooling_revision'] = VERSION
        value['tool_navigation']['source_selection'] = NAVIGATION
        return value


class _NullableCursorExecutor:
    def __init__(self, delegate, worker, name, schema):
        self.delegate, self.worker, self.name = delegate, worker, name
        self.schema = copy.deepcopy(schema)

    def __call__(self, action, conversation=None):
        pending = self.worker._pending
        if pending is None or self.worker._executions != 0 or pending['name'] != self.name:
            return self.delegate(action, conversation)
        original = pending['arguments']
        errors = _schema_errors(self.schema, original)
        if errors:
            raise ValueError('Pending arguments violate the declared schema: ' + '; '.join(errors))
        projected = action.model_dump(mode='json', by_alias=True,
                                      exclude_unset=True, exclude_computed_fields=True)
        if json_bytes(projected) != json_bytes(original):
            if ('cursor' not in original or original['cursor'] is not None or 'cursor' in projected
                    or json_bytes(projected) != json_bytes({key: value for key, value in original.items()
                                                           if key != 'cursor'})):
                raise ValueError('SDK changed managed arguments beyond omission of an admitted cursor:null')
            action = type(action).model_validate(copy.deepcopy(original))
            restored = action.model_dump(mode='json', by_alias=True,
                                         exclude_unset=True, exclude_computed_fields=True)
            if json_bytes(restored) != json_bytes(original):
                raise RuntimeError('Nullable cursor restoration changed original managed arguments')
            self.worker._emit('sdk_explicit_null_cursor_restored', {'version': VERSION,
                'tool': self.name, 'model_tool_call_id': pending['tool_call_id'],
                'restored_field': 'cursor', 'original_value': None,
                'other_arguments_changed': False, 'world_action_executed': False,
                'original_gateway_comparison_still_required': True})
        return self.delegate(action, conversation)

    def close(self):
        return self.delegate.close()


def install_nullable_cursors(worker):
    """Unify all six declared nullable cursor tools on a fresh actual worker.

    The substrate has four older instance-local wrappers. Verify and replace
    those exact wrappers, then wrap the two previously uncovered tools. Never
    patch old globals, relax the gateway or guess a missing non-null argument.
    """
    from .harness_sdk import HarnessWorker, _GatewayExecutor
    from jsonschema import Draft202012Validator
    from .software_benchmark_managed_v103 import _CursorExecutorLifecycle
    from .software_benchmark_nullable_cursor_v090 import (
        CURSOR_TOOLS as old_tools, _NullableCursorExecutor as OldCursorExecutor,
    )
    if (not isinstance(worker, HarnessWorker) or hasattr(worker, '_nullable_cursor_v117')
            or worker.meter['decisions'] != 0 or worker._pending is not None or worker._executions != 0):
        raise ValueError('Bind nullable cursor restoration once before any managed decision')
    definitions = {row['name']: row['parameters'] for row in worker.definitions}
    worker.conversation._ensure_agent_ready()
    agent = worker.conversation.agent
    tools, replacements, schemas = agent.tools_map, {}, {}
    for name in sorted(CURSOR_TOOLS):
        if name not in tools or name not in definitions:
            raise ValueError('Require the six published nullable cursor tools')
        schema, tool = definitions[name], tools[name]
        Draft202012Validator.check_schema(schema)
        cursor = schema.get('properties', {}).get('cursor', {})
        if (schema.get('type') != 'object' or schema.get('additionalProperties') is not False
                or 'cursor' in schema.get('required', []) or cursor.get('type') != ['string', 'null']
                or set(cursor) - {'type', 'description'} or tool.response_schema is not None):
            raise ValueError('Require the exact declared optional string/null cursor contract')
        executor = tool.executor
        if name in old_tools:
            if not isinstance(executor, _CursorExecutorLifecycle):
                raise ValueError('The original cursor lifecycle binding changed')
            executor = executor.repaired_executor
            if (not isinstance(executor, OldCursorExecutor) or executor.worker is not worker
                    or executor.name != name or executor.schema != schema):
                raise ValueError('The original fresh-worker cursor binding changed')
            executor = executor.delegate
        if not isinstance(executor, _GatewayExecutor) or executor.worker is not worker or executor.name != name:
            raise ValueError('Require the original bound managed gateway executor')
        replacements[name] = tool.set_executor(_NullableCursorExecutor(executor, worker, name, schema))
        schemas[name] = digest(json_bytes(schema))
    with agent._tools_lock:
        if set(agent._tools) != set(tools) or any(agent._tools[key] is not value for key, value in tools.items()):
            raise RuntimeError('Tool binding changed during fresh cursor installation')
        object.__setattr__(agent, '_tools', {**agent._tools, **replacements})
    worker._nullable_cursor_v117 = {'version': VERSION, 'tools': sorted(CURSOR_TOOLS),
        'schema_sha256': schemas, 'SDK_globals_changed': False, 'raw_arguments_rewritten': False}
    return copy.deepcopy(worker._nullable_cursor_v117)


class ToolFeedbackWorkerMixin:
    """Add explicit recovery at the actual adapter rejection; no new attempt."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            install_nullable_cursors(self)
        except BaseException:
            self.close()
            raise

    def _fail(self, status, reason, **details):
        body = getattr(self, '_last_body', None)
        choices = body.get('choices') if isinstance(body, dict) else None
        message = choices[0].get('message') if isinstance(choices, list) and len(choices) == 1 else None
        parser_failure = details.get('parser_failure', {})
        no_tool_boundary = (reason in {NO_TOOL_REASON,
            'No-tool response must be an exact explicit JSON wait/done control'}
            or isinstance(parser_failure, dict) and parser_failure.get('stage') == 'adapter_json_control')
        if (status == 'model_format_error' and no_tool_boundary
                and isinstance(message, dict) and message.get('role') == 'assistant'
                and not message.get('tool_calls')
                and choices[0].get('finish_reason', 'stop') in {'stop', 'tool_calls'}):
            details = copy.deepcopy(details)
            details['managed_tool_recovery'] = {'version': VERSION,
                'original_reason': reason, 'automatic_retry': False, 'world_action_executed': False}
            if isinstance(details.get('parser_failure'), dict):
                details['parser_failure']['original_reason'] = details['parser_failure'].get('reason')
                details['parser_failure']['reason'] = NO_TOOL_RECOVERY
            reason = NO_TOOL_RECOVERY
        return super()._fail(status, reason, **details)


def prepare_case(source_manifest, folder, *, max_total_tokens, public_test_callback,
                 deadline, public_test_entry):
    """Build the new world before binding its one public callback; no rebind."""
    provider = public_world.SelectedRepositorySources(source_manifest)
    if len(provider.case_ids) != 1:
        raise ValueError('One managed controller receives exactly one public task')
    task = provider.case_ids[0]
    if public_test_entry.get('instance_id') != task:
        raise ValueError('The selected-test entry belongs to another task')
    selected_entry(public_test_entry, normalize_selection())
    callback = PublicTestCallback(public_test_callback, entry=public_test_entry, instance_id=task,
        hard_at=deadline.hard_at, folder=Path(folder).parent/'public-test-rpc', clock=deadline.clock)
    provider.runner = callback
    prepared = source_world.build_software_collaboration_case(task, folder, provider=provider,
                                                            max_total_tokens=max_total_tokens)
    previous = prepared.world
    world = SoftwareCollaborationWorld(previous.store.root)
    world.source_provider, world.test_budget = provider, previous.test_budget
    world.public_test_entry = copy.deepcopy(public_test_entry)
    prepared.deployment.world = world
    prepared.port_factory = SoftwareCollaborationPort
    callback.bind_world(prepared)
    write_new(Path(folder)/'public-test-selection.json', {'version': public_world.VERSION,
        'entry': public_test_entry, 'capabilities': capabilities(public_test_entry),
        'model_calls': 0, 'test_executions': 0, 'hidden_evaluation_calls': 0})
    write_new(Path(folder)/'managed-tooling.json', {'version': VERSION,
        'tool_schema_sha256': digest(json_bytes(tool_definitions(prepared.case))),
        'automatic_actions': 0, 'permissions_changed': False, 'one_callback_binding': True})
    return prepared
