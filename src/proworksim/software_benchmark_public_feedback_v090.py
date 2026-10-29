"""Public native observations with explicit failure and repeated-result feedback.

No command execution, admission decision, test selection, hidden material,
candidate scoring, synthetic exit code, or automatic retry occurs here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from .software_benchmark_public_context_v062 import project_terminal_feedback

VERSION = 'v090-public-execution-evidence-feedback-r1'
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
TEST_COMMAND = re.compile(r'(?i)(?:\bpytest\b|\bunittest\b|(?:^|[/\s])runtests\.py\b|\bmanage\.py\s+test\b)')
FAILED = re.compile(r'(?mi)^FAILED(?:\s|$)|^ERROR(?:\s|:)|\b[1-9]\d*\s+(?:failed|errors?)\b')
IMPORT_ERROR = re.compile(r'(?mi)(?:^|\s)(?:ModuleNotFoundError|ImportError):|^ERROR: (?:not found|file or directory not found)|ERROR collecting ')
ZERO = re.compile(r'(?mi)\bRan 0 tests?\b|\bcollected 0 items\b|\bno tests ran\b')
COUNTS = re.compile(r'(?mi)\bRan (\d+) tests?\b|\b(\d+) passed\b')


def public_command_identity(command):
    """Ignore only a simple final head/tail filter when comparing evidence.

    This is an advisory comparison key, never a shell program to execute.
    Complex substitutions, heredocs and quoting uncertainties keep the full
    command. Removing an output filter does not prove equivalent execution.
    """
    if any(token in command for token in ('`', '$(', '<<', '\n')):
        return command, 'exact_command'
    quote, escaped, pipe = None, False, None
    for i, character in enumerate(command):
        if escaped:
            escaped = False
        elif character == '\\' and quote != "'":
            escaped = True
        elif quote:
            if character == quote:
                quote = None
        elif character in ('"', "'"):
            quote = character
        elif character == '|' and (i == 0 or command[i-1] != '|') and (i+1 == len(command) or command[i+1] != '|'):
            pipe = i
    if quote or escaped or pipe is None:
        return command, 'exact_command'
    if re.fullmatch(r'\s*(?:head|tail)(?:\s+-\d+|\s+-n\s*\d+)?\s*', command[pipe+1:]):
        return command[:pipe].rstrip(), 'simple_final_output_filter_ignored_for_advice_only'
    return command, 'exact_command'


def observation_text(response):
    blocks = response.get('observation', {}).get('content', [])
    if not isinstance(blocks, list):
        return ''
    return ANSI.sub('', ''.join(block.get('text', '') for block in blocks
        if isinstance(block, dict) and block.get('type') == 'text' and isinstance(block.get('text'), str)))


def public_test_status(command, response):
    """Interpret visible runner markers without asserting hidden correctness."""
    observation = response.get('observation', {})
    text = observation_text(response)
    if not TEST_COMMAND.search(command):
        return None
    counts = [int(a or b) for a, b in COUNTS.findall(text)]
    status = 'no_conclusive_test_summary'
    if IMPORT_ERROR.search(text):
        status = 'import_or_collection_error'
    elif ZERO.search(text):
        status = 'zero_tests_observed'
    elif FAILED.search(text):
        status = 'failure_reported'
    elif counts and (re.search(r'(?m)^OK\s*$', text) or re.search(r'\b\d+ passed\b', text)):
        status = 'success_reported_in_visible_output'
    # Arbitrary shell programs can hide the actual test status. A pipeline's
    # final exit code and a test runner's exit code are not interchangeable.
    pipeline_possible = '|' in command
    return {'kind': status, 'reported_test_counts': counts,
        'shell_exit_code': observation.get('exit_code'),
        'test_process_exit_code': None if pipeline_possible else observation.get('exit_code'),
        'test_exit_code_verified': False,
        'pipeline_syntax_possible': pipeline_possible,
        'output_may_be_partial': pipeline_possible,
        'official_correctness_inferred': False}


class PublicExecutionFeedback:
    """Retain exact public observations and append small, non-binding notes.

    Revision proofs are optional trusted integration inputs, never tool action
    arguments. Without before/after identity this reports repeated observations,
    not unchanged source. Existing native persisted-output links are retained.
    """
    def __init__(self):
        self.results = {}
        self.previous = {}
        self.notified = set()

    def observe(self, tool, action, raw, *, revision_before=None, revision_after=None):
        response = copy.deepcopy(raw)
        request_id = raw.get('id')
        # Keep original native content available by exact request ID for
        # trusted history projection. This is not a new model-facing tool.
        self.results[request_id] = raw
        if tool != 'terminal' or raw.get('type') != 'observation' or raw.get('tool') != 'terminal':
            return {'response': response, 'events': []}
        command = action.get('command')
        if not isinstance(command, str) or not command:
            return {'response': response, 'events': []}
        text = observation_text(raw)
        status = public_test_status(command, raw)
        stable_revision = (revision_before if isinstance(revision_before, str) and revision_before
                           and revision_before == revision_after else None)
        if status and status['kind'] != 'no_conclusive_test_summary':
            command_key, comparison = public_command_identity(command)
            signature = {k: status[k] for k in ('kind', 'reported_test_counts')}
        else:
            command_key, comparison = command, 'exact_command'
            signature = {'text': text, 'exit_code': raw.get('observation', {}).get('exit_code')}
        result_signature = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
        key = (command_key, result_signature)
        previous = self.previous.get(key)
        notes, events = [], []
        if status:
            kind = status['kind']
            if kind == 'import_or_collection_error':
                notes.append('The visible output reports an import or collection error. This is not a passing test; inspect the public runner, module name and dependencies before choosing a corrected command.')
            elif kind == 'zero_tests_observed':
                notes.append('The visible runner reports zero tests. Shell success or an OK line does not establish that the intended behavior was tested.')
            elif kind == 'failure_reported':
                notes.append('The visible test output reports failure; preserve that result even if the shell exit code is zero.')
            if status['pipeline_syntax_possible']:
                notes.append('This command contains pipe syntax. The observed shell exit code does not establish the test process exit code, and filtered output may omit results. Inspect the existing complete native output if available; for a future necessary run, preserve the runner status and log before filtering.')
            if notes:
                events.append({**status, 'kind': 'public_test_status', 'observed_status': kind,
                               'request_id': request_id})
        if previous is not None:
            same_revision = stable_revision is not None and previous['stable_revision'] == stable_revision
            note_key = (key, stable_revision, 'repeated_result')
            if note_key not in self.notified:
                if same_revision:
                    claim = 'The trusted before/after source identity is unchanged.'
                else:
                    claim = 'This observation does not prove the source or execution environment is unchanged.'
                identity = ('This exact command' if command == previous['command'] else
                            'The same command before a simple final head/tail output filter')
                notes.append(f'{identity} already produced the same visible result summary at request {previous["request_id"]}. {claim} Consult that observation or its native saved-output link. Repetition remains available when needed for a specific change, missing evidence or nondeterminism; public test success alone is not a completion requirement.')
                events.append({'kind': 'repeated_public_result', 'request_id': request_id,
                    'previous_request_id': previous['request_id'], 'same_source_revision_proved': same_revision,
                    'commands_identical': command == previous['command'], 'comparison_basis': comparison,
                    'command_rejected': False, 'automatic_retry': False})
                self.notified.add(note_key)
        self.previous[key] = {'request_id': request_id, 'stable_revision': stable_revision, 'command': command}
        # Error guidance is emitted once per unchanged command/result, while
        # all native output remains visible on every execution.
        status_key = (key, stable_revision, 'status')
        if status_key in self.notified:
            notes = [note for note in notes if note.startswith(('This exact command', 'The same command before'))]
            events = [event for event in events if event['kind'] != 'public_test_status']
        elif status:
            self.notified.add(status_key)
        if notes:
            response.setdefault('llm_content', []).append({'type': 'text',
                'text': '[v090 public execution feedback] ' + ' '.join(notes)})
        return {'response': response, 'events': events}

    def read_observation(self, request_id):
        """Trusted history access; no invented actor-readable host file path."""
        return copy.deepcopy(self.results[request_id])


def feedback_rpc_class(base):
    """Drop-in RPC wrapper; execute the original action exactly once."""
    class FeedbackRPC(base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.feedback_events, self.feedback_projections = [], []
            self.public_feedback = PublicExecutionFeedback()

        def request(self, tool, action, *, timeout_seconds=None):
            probe = getattr(self, 'public_revision_probe', lambda: None)
            before = probe()
            raw = super().request(tool, action, timeout_seconds=timeout_seconds)
            after = probe()
            if getattr(self, 'raw_sink', None) is not None:
                self.raw_sink(self.transcript[-1])
            original = project_terminal_feedback(raw, public_python=self.public_python)
            projected = self.public_feedback.observe(tool, action, raw,
                revision_before=before, revision_after=after)
            # Keep the original native format/interpreter advice as well.
            extra = original['response'].get('llm_content', [])[len(raw.get('llm_content', [])):]
            projected['response'].setdefault('llm_content', []).extend(extra)
            events = original['events'] + projected['events']
            self.feedback_events.extend(events)
            if events:
                evidence = {'version': VERSION, 'request_id': raw.get('id'), 'events': events,
                    'model_visible_llm_content': projected['response']['llm_content']}
                self.feedback_projections.append(evidence)
                if getattr(self, 'feedback_sink', None) is not None:
                    self.feedback_sink(evidence)
            return projected['response']
    return FeedbackRPC
