"""Native pinned OpenHands Agent/Conversation with one shared raw native provider.

Only provider dispatch, bounded terminal execution and evidence are adapted.
The official Agent owns actions, observations, history, stuck handling and finish.
No managed HarnessWorker or mini-SWE loop is used.
"""
from __future__ import annotations

import copy
from functools import lru_cache
import hashlib
import importlib
from importlib.metadata import version
import importlib.util
import inspect
import json
import os
import sys
from pathlib import Path
import time
from types import SimpleNamespace
import uuid

from .storage import atomic_write, digest, json_bytes

VERSION = 'software-bridge-openhands-v0.52'
SDK_VERSION = '1.49.6'
SDK_COMMIT = 'fcc102a697874d54a357e36004e02c95040dbdc0'
PUBLIC_TEST_COMMAND = 'bridge_run_tests'
TERMINAL_DESCRIPTION = '''Execute one self-contained bash command in a confined repository.
Each command starts a fresh noninteractive bash at the original workspace directory.
File edits persist, but cd/export/shell variables and background jobs never carry
between commands. is_input=True, reset=True and empty polling commands are rejected
without execution. timeout is a hard bounded command limit clamped to 1..60 seconds;
no interactive continuation exists. Only the defective worktree and declared read-only
runtime are accessible; external network and other experiment files are denied.
Run exactly bridge_run_tests, without arguments, for the complete original tests
through the shared frozen evaluator. Other shell commands are exploratory only.
Original readonly tests/config/support are restored in every authoritative test tree.
The result is the official terminal observation with the real exit code.''' 
CONDITION = 'OH_ref'
EXPECTED = {'context_limit': 18432, 'max_output_tokens': 2048,
            'enable_thinking': False, 'preserve_thinking': False, 'temperature': .7,
            'top_p': 1., 'top_k': 0, 'max_generation_seconds': 600}
_ACTIVE_OVERLAY = None
MODULES = (
    'openhands.sdk.agent.agent', 'openhands.sdk.agent.base',
    'openhands.sdk.agent.response_dispatch', 'openhands.sdk.agent.utils',
    'openhands.sdk.conversation.impl.local_conversation',
    'openhands.sdk.context.prompts.presets', 'openhands.sdk.llm.message',
    'openhands.sdk.tool.tool', 'openhands.sdk.tool.builtins.finish',
    'openhands.tools.terminal.definition', 'openhands.tools.terminal.descriptions',
)


def ref(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def checked(reference):
    path = Path(reference['path'])
    if not path.is_absolute() or ref(path) != reference:
        raise ValueError('Changed or nonabsolute OH evidence reference')
    return path


def write(path, value):
    atomic_write(Path(path), json_bytes(value))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(json_bytes(value))
    return ref(path)


def activate_tools_overlay(path):
    """Append only the independent tools layer; never override existing numerical libraries."""
    global _ACTIVE_OVERLAY
    path = Path(path).resolve()
    if not (path / 'openhands/tools/terminal/definition.py').is_file():
        raise ValueError('The explicit pinned OpenHands tools overlay is absent')
    if _ACTIVE_OVERLAY is not None and _ACTIVE_OVERLAY != path:
        raise ValueError('Do not swap the reference tools layer inside a worker')
    if str(path) not in sys.path:
        sys.path.append(str(path))
    _ACTIVE_OVERLAY = path
    return path


def sdk_provenance(*, tools_overlay=None):
    """Actual official modules and the standalone same-commit tools package layer."""
    path = tools_overlay or _ACTIVE_OVERLAY
    if path is None:
        path = Path(__file__).resolve().parents[2] / 'artifacts/software-bridge-v052/openhands-tools-runtime'
    overlay = activate_tools_overlay(path)
    if version('openhands-sdk') != SDK_VERSION or version('openhands-tools') != SDK_VERSION:
        raise ValueError('Use the pinned SDK and tools 1.49.6 without upgrading PS1')
    modules = {name: ref(inspect.getfile(importlib.import_module(name))) for name in MODULES}
    terminal_path = Path(modules['openhands.tools.terminal.definition']['path'])
    if not terminal_path.is_relative_to(overlay):
        raise ValueError('A different tools package shadowed the declared reference layer')
    files = {str(p.relative_to(overlay)): digest(p.read_bytes()) for p in sorted(overlay.rglob('*'))
             if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    dependencies = {}
    for name in ('libtmux', 'binaryornot', 'chardet'):
        module = importlib.import_module(name)
        dependencies[name] = {'version': version(name), 'module': ref(module.__file__)}
    return {'version': 'v052-openhands-reference-runtime-v1', 'sdk_version': SDK_VERSION,
            'sdk_commit': SDK_COMMIT, 'tools_version': SDK_VERSION,
            'modules': modules, 'tools_overlay': {'path': str(overlay), 'files': files},
            'imported_tool_dependencies': dependencies,
            'overlay_activation': 'append sys.path before tools import; existing SDK/numerical paths retain priority',
            'official_loop_modified': False, 'managed_worker_loop_used': False,
            'preset': 'official_Agent_Conversation_TerminalTool_FinishTool_confined_executor',
            'full_default_preset': False, 'terminal_description_override': TERMINAL_DESCRIPTION,
            'terminal_description_sha256': digest(TERMINAL_DESCRIPTION.encode()),
            'official_terminal_action_and_observation_retained': True}


def bind_sdk(reference):
    declared = json.loads(checked(reference).read_bytes())
    # The manifest gives the absolute overlay even when this adapter runs from a frozen source copy.
    actual = sdk_provenance(tools_overlay=declared['tools_overlay']['path'])
    for key in ('version', 'sdk_version', 'sdk_commit', 'tools_version', 'modules',
                'tools_overlay', 'imported_tool_dependencies', 'terminal_description_sha256'):
        if declared.get(key) != actual[key]:
            raise ValueError('Pinned official OpenHands source binding differs: ' + key)
    return actual


class LocalStop(BaseException):
    def __init__(self, reason):
        self.reason = reason


class InitialRequestCaptured(BaseException):
    pass


@lru_cache(maxsize=1)
def sdk_types():
    from openhands.sdk import LLM
    from openhands.sdk.tool import ToolExecutor
    from pydantic import PrivateAttr

    class NativeBridgeLLM(LLM):
        _bridge: object = PrivateAttr(default=None)

        def resolve_runtime_metadata(self):
            # No external LiteLLM endpoint, fallback provider or metadata query.
            return None

        def completion(self, messages, tools=None, **kwargs):
            return self._bridge.completion(messages, tools or [], kwargs)

    class ConfinedTerminalExecutor(ToolExecutor):
        def __init__(self, bridge):
            self.bridge = bridge

        def __call__(self, action, conversation=None):
            return self.bridge.terminal(action)

    return NativeBridgeLLM, ConfinedTerminalExecutor


def validate_owner(owner, *, metadata_only, allow_cpu_fixture):
    from .software_calibration_runtime_v051 import CalibrationActor
    formal = isinstance(owner, CalibrationActor)
    identity = owner.freeze_identity()
    if (owner.path != 'project' or identity.get('raw_release') is not True
            or identity.get('checkpoint') or identity.get('adapter_sha256')):
        raise ValueError('OH_ref requires the same raw/no-adapter project provider as PS1')
    if any(owner.contract.get(key) != value for key, value in EXPECTED.items()):
        raise ValueError('OH_ref decoder/context differs from the frozen shared provider')
    if not formal and not (metadata_only or allow_cpu_fixture):
        raise ValueError('Programmed CPU owners cannot enter a formal OH episode')
    return identity, formal


def read_worktree(worktree):
    # Pure UTF-8 byte-faithful snapshot only; no mini tool/history/loop is used.
    from .software_calibration_v051_mini import read_worktree as read_files
    return read_files(worktree)


def task_prompt(case, task):
    from .software_calibration_v051_mini import production_domain
    return (case['root_goal'] + '\n\n' + production_domain(task)
        + '\nWork directly in the current repository. The official terminal tool uses a confined '
          'fresh bash process for each command: cd/export and interactive jobs do not persist. '
          'Use one self-contained command, anchored at the repository root. File edits persist. '
          'For the complete authoritative original repository tests, run exactly bridge_run_tests '
          'with no arguments. This command restores the original test/configuration/support files '
          'in a separate evaluation tree and uses the same frozen interpreter and sandbox as PS1. '
          'Other shell commands are exploratory and are recorded separately. External network and '
          'files outside this repository and the declared runtime are inaccessible. '
          'Use the native finish tool when done. Only the one final production tree at closure '
          'will be evaluated; there is no project fixed-submit contract for this condition.')


class Bridge:
    def __init__(self, *, owner, identity, formal, task_source, provider, slot_id, sampling_seed,
                 worktree, folder, initial_capture):
        self.owner, self.identity, self.formal = owner, identity, formal
        self.task_source, self.provider = copy.deepcopy(task_source), provider
        self.worktree, self.folder = Path(worktree).resolve(), Path(folder).resolve()
        self.initial_capture, self.started = initial_capture, time.monotonic()
        self.window = 'openhands-bridge-v052:' + slot_id
        self.binding = {'version': VERSION, 'condition': CONDITION, 'slot_id': slot_id,
                        'task_id': task_source['task_id'], 'sampling_seed': sampling_seed,
                        'window_id': self.window, 'actor_identity': copy.deepcopy(identity)}
        self.decisions = self.attempts = self.complete = self.actual = 0
        self.prompt_tokens = self.output_tokens = 0
        self.inflight, self.stop_reason = None, None
        self.calls, self.rejections, self.commands, self.events = [], [], [], []
        self.captured = None
        self.save()

    def snapshot(self):
        return {'version': VERSION, 'condition': CONDITION, 'episode_binding': self.binding,
                'decisions': self.decisions, 'attempts': self.attempts, 'complete_responses': self.complete,
                'known_actual_tokens': self.actual, 'prompt_tokens': self.prompt_tokens,
                'completion_tokens': self.output_tokens, 'inflight': self.inflight,
                'uncertain_reservation_tokens': self.inflight['reservation'] if self.inflight else 0,
                'complete_actual_tokens': self.actual if self.inflight is None else None,
                'token_limit': 500000, 'decision_limit': 128, 'attempt_limit': 128,
                'calls': self.calls, 'preexecution_rejections': self.rejections,
                'stop_reason': self.stop_reason, 'automatic_model_retries': False,
                'formal_native_provider': self.formal, 'local_dollar_cost_estimate': None}

    def save(self):
        write(self.folder / 'ledger.json', self.snapshot())

    def stop(self, reason, native=None):
        self.stop_reason = reason
        receipt = {**self.binding, 'reason': reason, 'generation_started': False,
                   'new_tool_side_effect': False, 'decisions': self.decisions,
                   'attempts': self.attempts, 'remaining_tokens': 500000 - self.actual,
                   'elapsed_seconds': time.monotonic() - self.started, 'native_input': native}
        self.rejections.append(write_new(self.folder / f'rejection-{len(self.rejections):03d}.json', receipt))
        self.save()
        raise LocalStop(reason)

    def on_event(self, event):
        value = event.model_dump(mode='json')
        self.events.append(value)
        with (self.folder / 'sdk-events.jsonl').open('ab') as stream:
            stream.write(json_bytes(value) + b'\n')

    def completion(self, messages, tools, kwargs):
        from litellm.types.utils import ModelResponse
        from openhands.sdk.llm import Message
        from openhands.sdk.llm.llm_response import LLMResponse
        from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage
        from .candidate_runtime_v017 import parse_candidate_generated
        from .deterministic_work_v024 import deterministic_tool_ids
        if self.decisions >= 128 or self.attempts >= 128:
            self.stop('decision_or_attempt_limit')
        if time.monotonic() - self.started >= 5400:
            self.stop('administrative_soft_deadline')
        wire = [message.to_chat_dict(cache_enabled=False, vision_enabled=False,
                    function_calling_enabled=True, force_string_serializer=True,
                    send_reasoning_content=True) for message in messages]
        request = {'model': 'raw-qwen3.5-9b-v052', 'messages': wire,
                   'tools': [dict(tool.to_openai_tool(add_security_risk_prediction=
                              bool(kwargs.get('add_security_risk_prediction', False)))) for tool in tools],
                   'temperature': .7, 'max_tokens': 2048, 'stream': False, 'tool_choice': 'auto'}
        if {tool['function']['name'] for tool in request['tools']} != {'terminal', 'finish'}:
            raise ValueError('The native reference has exactly official terminal and finish tools')
        _, _, native = self.owner.prepare_request(request)
        if self.initial_capture is not None:
            self.captured = {'original_request': write_new(self.folder / 'original-request.json', request),
                             'native_input': write_new(self.folder / 'native-input.json', native)}
            self.initial_capture(copy.deepcopy(request), copy.deepcopy(native))
            raise InitialRequestCaptured()
        self.decisions += 1
        request_ref = write_new(self.folder / f'request-{self.decisions:03d}.json',
                               {**self.binding, 'request': request, 'native_input': native})
        if not native['fits']:
            self.stop('full_native_context_preexecution_rejection', native)
        reservation = native['prompt_tokens'] + 2048
        if reservation > 500000 - self.actual:
            self.stop('full_request_token_reservation_insufficient', native)
        self.attempts += 1
        self.inflight = {'attempt': self.attempts, 'reservation': reservation, 'request': request_ref}
        self.save()
        result = self.owner.generate_native(native)
        usage = result['usage']
        if (result.get('actor_identity') != self.identity or result.get('input') != native
                or any(type(usage.get(k)) is not int for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
                or usage['prompt_tokens'] != native['prompt_tokens']
                or usage['completion_tokens'] != len(result['output_ids'])
                or usage['total_tokens'] != usage['prompt_tokens'] + usage['completion_tokens']
                or not 0 < usage['total_tokens'] <= reservation):
            raise ValueError('Native actual request/identity/usage cannot settle its reservation')
        if any(call['native_attempt_id'] == result['attempt_id'] for call in self.calls):
            raise ValueError('Native attempt ID was reused')
        self.actual += usage['total_tokens']
        self.prompt_tokens += usage['prompt_tokens']
        self.output_tokens += usage['completion_tokens']
        self.complete += 1
        self.inflight = None
        message, parse_error = parse_candidate_generated(result['raw_generated_text'], request)
        message = deterministic_tool_ids(message, request, result['raw_generated_text'])
        body = {'id': 'oh-' + result['attempt_id'], 'object': 'chat.completion',
                'model': request['model'], 'choices': [{'index': 0, 'message': message,
                'finish_reason': 'tool_calls' if message.get('tool_calls') else 'stop'}], 'usage': usage}
        response_ref = write_new(self.folder / f'response-{self.attempts:03d}.json',
            {**self.binding, 'native_result': result, 'sdk_response': body,
             'protocol_parse_error': parse_error, 'native_finish_reason': result['finish_reason']})
        self.calls.append({'native_attempt_id': result['attempt_id'], 'request': request_ref,
                           'response': response_ref, 'usage': copy.deepcopy(usage),
                           'native_input_sha256': native['sha256']})
        self.save()
        raw = ModelResponse(**body)
        return LLMResponse(message=Message.from_llm_chat_message(raw.choices[0].message),
                           raw_response=raw, metrics=MetricsSnapshot(model_name=request['model'],
                           accumulated_token_usage=TokenUsage(model=request['model'],
                               prompt_tokens=self.prompt_tokens, completion_tokens=self.output_tokens)))

    def terminal(self, action):
        from openhands.tools.terminal.definition import TerminalObservation
        from openhands.tools.terminal.metadata import CmdOutputMetadata
        from .software_bridge_sources_v052 import run_native_public_tests
        if time.monotonic() - self.started >= 6000:
            self.stop('administrative_hard_deadline_before_tool')
        index = len(self.commands)
        if action.is_input or action.reset or not action.command.strip():
            result = {'returncode': 2, 'output': 'This disclosed confined executor has no persistent interactive session; use one self-contained command.',
                      'execution_kind': 'unsupported_interactive_request', 'side_effect': False}
        elif action.command.strip() == PUBLIC_TEST_COMMAND:
            execution = run_native_public_tests(provider=self.provider, task_id=self.task_source['task_id'],
                candidate_files=read_worktree(self.worktree), run_root=self.folder / 'tests' / f'{index:03d}')
            result = {'returncode': execution.get('returncode'),
                      'output': json.dumps(execution, ensure_ascii=False),
                      'execution_kind': 'shared_authoritative_public_test_entry',
                      'execution': execution, 'side_effect': True}
            if type(result['returncode']) is not int:
                raise ValueError('Shared test runner lacks its real exit code')
        else:
            task = self.task_source['runner_spec']
            runtime = json.loads(checked(task['bridge_runtime_ref']).read_bytes())
            from .server_bridge_runtime_v052 import VERSION as SERVER_VERSION, require_task_protocol
            if runtime.get('version') == SERVER_VERSION:
                from .software_bridge_sources_v052 import runtime_binding
                runtime, _ = runtime_binding(task['bridge_runtime_ref']['path'])
                require_task_protocol(task, runtime)
            elif 'bridge_execution_protocol' in task:
                raise ValueError('The frozen OH helper cannot use a new server execution identity')
            helper = checked(runtime['shell_helper'])
            spec = importlib.util.spec_from_file_location('v052_oh_frozen_shell', helper)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            python = Path(task['cpu_python'])
            result = module.run_bounded_shell(action.command, worktree=self.worktree,
                python_executable=python, python_prefix=python.parent.parent,
                evidence_root=self.folder / 'shell', timeout_seconds=min(60, max(1, action.timeout or 30)))
            result['execution_kind'] = 'confined_exploratory_shell'
        receipt = {'version': VERSION, 'episode_binding': self.binding, 'index': index,
                   'action': action.model_dump(mode='json'), 'result': result,
                   'native_decision': self.decisions, 'elapsed_seconds': time.monotonic() - self.started}
        self.commands.append(write_new(self.folder / f'command-{index:03d}.json', receipt))
        code = result['returncode']
        # A timed-out shell has been killed/reaped; do not advertise an interactive job.
        if code == -1:
            code = 124
        return TerminalObservation.from_text(text=result['output'], command=action.command,
                    exit_code=code, timeout=code == 124,
                    metadata=CmdOutputMetadata(exit_code=code, working_dir=str(self.worktree),
                                                py_interpreter_path=self.task_source['runner_spec']['cpu_python']))


def collect_episode(*, owner, task_source, provider, slot_id, sampling_seed, worktree,
                    episode_folder, initial_capture=None, allow_cpu_fixture=False):
    """Run the official native loop once; no weights are loaded by this adapter.

    initial_capture(request, native_input) runs before decisions/reservations/
    generation/tools. A metadata-only owner is accepted only in that branch.
    """
    worktree, folder = Path(worktree).resolve(), Path(episode_folder).resolve()
    if not worktree.is_dir() or folder.exists() or folder.is_relative_to(worktree):
        raise ValueError('Use an existing isolated buggy tree and fresh external episode directory')
    if task_source['task_id'] != task_source['runner_spec']['task_id']:
        raise ValueError('Task source and runner identity differ')
    if read_worktree(worktree) != dict(sorted(task_source['files'].items())):
        raise ValueError('Native episode must start from the exact original defective tree')
    folder.mkdir(parents=True)
    # Before SDK import: keep user SOUL/config outside the reference experiment.
    persistence = folder / 'sdk-config'
    persistence.mkdir()
    os.environ['OH_PERSISTENCE_DIR'] = str(persistence)
    sdk = bind_sdk(task_source['reference_runtime'])
    from openhands.sdk import Agent, Conversation
    from openhands.sdk.agent import base as official_base
    from openhands.sdk.tool import Tool, register_tool
    from openhands.tools.terminal import TerminalTool
    if official_base._SOUL_PATH.exists():
        raise ValueError('Do not import a user SOUL.md into the native reference prompt')
    identity, formal = validate_owner(owner, metadata_only=initial_capture is not None,
                                      allow_cpu_fixture=allow_cpu_fixture)
    task_ref = write_new(folder / 'task-source.json', task_source)
    bridge = Bridge(owner=owner, identity=identity, formal=formal, task_source=task_source,
                    provider=provider, slot_id=slot_id, sampling_seed=sampling_seed,
                    worktree=worktree, folder=folder, initial_capture=initial_capture)
    llm_type, executor_type = sdk_types()
    executor = executor_type(bridge)
    registration = 'v052_native_terminal_' + uuid.uuid4().hex

    # This pinned release registers an instance or subclass, not the callable
    # factory accepted by some newer documentation examples. The official
    # factory only reads the concrete workspace path when executor is supplied.
    creation_state = SimpleNamespace(workspace=SimpleNamespace(working_dir=str(worktree)))
    terminal = TerminalTool.create(creation_state, executor=executor)[0]
    terminal = terminal.model_copy(update={'description': TERMINAL_DESCRIPTION})
    register_tool(registration, terminal)
    llm = llm_type(model='openai/raw-qwen3.5-9b-v052', usage_id='OH_ref', num_retries=0,
                   stream=False, caching_prompt=False, max_input_tokens=18432,
                   max_output_tokens=2048, temperature=.7)
    llm._bridge = bridge
    agent = Agent(llm=llm, tools=[Tool(name=registration)], include_default_tools=['FinishTool'],
                  mcp_config={}, condenser=None, agent_context=None, tool_concurrency_limit=1)
    conversation = Conversation(agent=agent, workspace=worktree, persistence_dir=folder / 'conversations',
                    callbacks=[bridge.on_event], plugins=[], max_iteration_per_run=128,
                    stuck_detection=True, visualizer=None, delete_on_close=False)
    before = owner.capture_evaluation_state() if initial_capture is None else None
    guard = None
    error = None
    captured = False
    status = 'closed'
    try:
        if initial_capture is None:
            owner.begin_window(bridge.window)
            owner.reseed(sampling_seed, label=slot_id)
        conversation.send_message(task_prompt(task_source, task_source['runner_spec']))
        conversation.run()  # The sole official loop invocation; no managed stepping.
    except InitialRequestCaptured:
        captured = True
        status = 'initial_request_captured'
    except LocalStop as stop:
        bridge.stop_reason = stop.reason
        status = 'safe_local_stop'
    except Exception as exc:
        status = 'execution_fault'
        error = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        sdk_status = str(conversation.state.execution_status.value)
        conversation.close()
        if initial_capture is None:
            owner.finish_evaluation([], folder / 'owner-evaluation')
            guard = owner.finish_evaluation_guard(before)
            guard.update(actor_identity_unchanged=owner.freeze_identity() == identity,
                         software_binding_unchanged=sdk_provenance() == sdk)
            write(folder / 'evaluation-guard.json', guard)
    if captured:
        return {**bridge.binding, 'status': status, **bridge.captured,
                'decisions': 0, 'attempts': 0, 'tool_executions': 0,
                'model_generations': 0, 'guard_claimed': False, 'sdk_provenance': sdk,
                'capture_counters': {'harness_decisions': None, 'team_decisions': None,
                    'not_applicable_reason': 'Native OH has no ProWorkSim harness or team meter',
                    'native_SDK_LLM_entries': 1, 'adapter_decisions': bridge.decisions,
                    'attempts': bridge.attempts, 'reservation_tokens': 0, 'responses': bridge.complete,
                    'tool_actions': len(bridge.commands), 'model_generations': bridge.attempts}}
    if initial_capture is not None:
        raise ValueError('Official initial capture did not stop at the native prepare boundary')
    bridge.save()
    candidate = write_new(folder / 'candidate-files.json', read_worktree(worktree))
    lock = write_new(folder / 'export-lock.json', {'version': 'v052-OH-unique-final-export-v1',
                     'episode_binding': bridge.binding, 'candidate_files': candidate,
                     'selection_after_scoring': False, 'export_count': 1})
    # Official error/confirmation exits are evidence, not silently treated as finish.
    if status == 'closed' and sdk_status not in ('finished',):
        if bridge.decisions == 128 and bridge.inflight is None:
            status, bridge.stop_reason = 'safe_local_stop', 'decision_or_attempt_limit'
        else:
            status = 'execution_fault'
            error = {'type': 'UnexpectedSDKExit', 'message': sdk_status}
    bridge.save()
    result = {**bridge.binding, 'status': status, 'sdk_execution_status': sdk_status,
        'error': error, 'stop_reason': bridge.stop_reason, 'ledger': bridge.snapshot(),
        'ledger_source': ref(folder / 'ledger.json'), 'candidate_files': candidate,
        'candidate_lock': lock, 'task_source': task_ref, 'sdk_provenance': sdk,
        'sdk_events': ref(folder / 'sdk-events.jsonl'), 'tool_commands': bridge.commands,
        'episode_guard': guard, 'evaluation_guard': ref(folder / 'evaluation-guard.json'),
        'formal_native_provider': formal, 'fixture_only': not formal,
        'project_delivery_endpoint': 'not_applicable', 'R_joint': None,
        'elapsed_seconds': time.monotonic() - bridge.started,
        'new_actor_steps': 0, 'new_critic_steps': 0, 'new_backward_calls': 0}
    write_new(folder / 'result.json', result)
    return result


def measure_closed(result, *, row, owner_identity, accounting):
    """Read-only binding of official SDK requests, native usages and unique export.

    Host separately binds every native provider receipt and performs R_code once.
    No success score is used as an execution or source gate.
    """
    issues, missing = [], []
    try:
        if (result['condition'] != CONDITION or row['condition'] != CONDITION
                or result['slot_id'] != row['slot_id'] or result['task_id'] != row['task_id']
                or result['sampling_seed'] != row['seed']
                or result['window_id'] != 'openhands-bridge-v052:' + row['slot_id']
                or result['actor_identity'] != owner_identity):
            issues.append('episode_or_raw_actor_binding')
        ledger = json.loads(checked(result['ledger_source']).read_bytes())
        if ledger != result['ledger'] or ledger['inflight'] is not None:
            issues.append('ledger_changed_or_unsettled')
        for left, right in [('attempts', 'started_generations'), ('complete_responses', 'complete_generations'),
                            ('known_actual_tokens', 'known_actual_tokens'),
                            ('uncertain_reservation_tokens', 'uncertain_reservation_tokens')]:
            if ledger[left] != accounting[right]:
                issues.append('native_accounting_mismatch:' + left)
        if accounting['integrity_errors']:
            issues.append('native_accounting_integrity')
        if result['status'] not in ('closed', 'safe_local_stop'):
            missing.append('official_conversation_not_safely_closed')
        if result['fixture_only'] or result['formal_native_provider'] is not True:
            missing.append('CPU_fixture_is_not_formal_native_evidence')
        for key in ('learning_unchanged', 'rng_restored_exactly', 'software_binding_unchanged', 'actor_identity_unchanged'):
            if result['episode_guard'].get(key) is not True:
                issues.append('episode_guard:' + key)
        if json.loads(checked(result['evaluation_guard']).read_bytes()) != result['episode_guard']:
            issues.append('episode_guard_source_binding')
        checked(result['sdk_events'])
        lock = json.loads(checked(result['candidate_lock']).read_bytes())
        if lock['candidate_files'] != result['candidate_files'] or lock['export_count'] != 1 or lock['selection_after_scoring']:
            issues.append('unique_final_export_binding')
        checked(result['candidate_files'])
        if result['R_joint'] is not None or result['project_delivery_endpoint'] != 'not_applicable':
            issues.append('OH_fixed_submit_endpoint_is_not_applicable')
        ids, total = set(), 0
        for call in ledger['calls']:
            request = json.loads(checked(call['request']).read_bytes())
            response = json.loads(checked(call['response']).read_bytes())
            native = response['native_result']
            if (request['window_id'] != result['window_id'] or request['actor_identity'] != owner_identity
                    or native['input'] != request['native_input'] or native['actor_identity'] != owner_identity
                    or call['usage'] != native['usage'] or response['sdk_response']['usage'] != native['usage']
                    or native['attempt_id'] != call['native_attempt_id'] or native['attempt_id'] in ids):
                issues.append('SDK_native_request_response_binding')
            ids.add(native['attempt_id'])
            total += native['usage']['total_tokens']
        if len(ids) != ledger['complete_responses'] or total != ledger['known_actual_tokens']:
            issues.append('unique_response_cost_binding')
        for command in result['tool_commands']:
            receipt = json.loads(checked(command).read_bytes())
            if receipt['episode_binding']['window_id'] != result['window_id']:
                issues.append('terminal_episode_binding')
    except (KeyError, FileNotFoundError, TypeError) as exc:
        missing.append(type(exc).__name__ + ':' + str(exc))
    except ValueError as exc:
        issues.append(str(exc))
    return {'version': 'v052-OH-readonly-measurement-v1',
            'decision': 'global_pause' if issues else 'pending' if missing else 'continue',
            'issues': issues, 'unresolved': missing, 'score_used_for_gate': False,
            'new_model_calls': 0, 'new_test_executions': 0}
