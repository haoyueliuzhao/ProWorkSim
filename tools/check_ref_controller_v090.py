"""CPU-only entrypoint exercising the complete v090 REF session factory."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]


def control(output):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("Ordinary-user scripted CPU control only")
    output = Path(output).resolve()
    if not (output.is_relative_to(Path('/tmp')) or output.is_relative_to(ROOT / 'runs/software-benchmark-v090')):
        raise ValueError("Use only a new local control output directory")
    output.mkdir(parents=True, exist_ok=False)
    forbidden = {"network": 0, "gpu": 0, "weights": 0, "subprocess": 0}

    def audit(event, values):
        kind = None
        if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"}:
            kind = 'network'
        elif event in {'subprocess.Popen', 'os.system', 'os.fork', 'os.posix_spawn', 'os.exec'}:
            kind = 'subprocess'
        elif event == 'open' and values and isinstance(values[0], (str, bytes)):
            path = os.fsdecode(values[0])
            if path.startswith(('/dev/nvidia', '/dev/dri/')):
                kind = 'gpu'
            elif path.endswith(('.safetensors', '.gguf')) or 'pytorch_model' in path:
                kind = 'weights'
        if kind:
            forbidden[kind] += 1
            raise AssertionError('Forbidden operation in CPU controller control: ' + kind)
    sys.addaudithook(audit)
    from proworksim.software_benchmark_candidates_v054 import reference, write_new
    from proworksim.software_benchmark_exact_transport_v054 import REF_MODEL, exact_measure
    from proworksim.software_benchmark_native_control_v090 import FINISH_REVIEW, WORKFLOW_GUIDANCE
    from proworksim.software_benchmark_ref_budget_v064 import BeforeQwenDispatch, BudgetLedger
    from proworksim.software_benchmark_ref_controller_v090 import run_scripted_session
    from proworksim.storage import atomic_write, json_bytes

    condition = json.loads((ROOT / 'runs/software-benchmark-v064/full-verified-r1/conditions/QWEN_REF_B5000K.json').read_bytes())
    ready = json.loads((ROOT / 'runs/software-benchmark-v066/sdk-bundle-r1/probe-native-interface.json').read_bytes())
    result = {'passed': False, 'model_calls': 0, 'API_calls': 0, 'real_repository_tool_calls': 0,
              'Docker_operations': 0, 'official_scoring_calls': 0, 'cases': [],
              'synthetic_tokens_not_model_measurement': True}

    class ScriptedRPC:
        scripted_cpu_only = True

        def __init__(self, label):
            self.ready, self.session_id = ready, 'v090_cpu_controller_' + label
            self._bound, self.transcript, self.closed = False, [], False

        def request(self, tool, action, *, timeout_seconds=None):
            if self.closed or tool != 'terminal':
                raise AssertionError('Only the declared terminal observations are allowed')
            text = ('ImportError: No module named missing_tests\n' if 'missing_tests' in action['command']
                    else 'Ran 2 tests in 0.1s\nOK\n')
            code = 1 if 'ImportError' in text else 0
            response = {'id': len(self.transcript) + 1, 'type': 'observation', 'tool': tool,
                        'observation': {'is_error': False, 'exit_code': code,
                            'metadata': {'exit_code': code, 'py_interpreter_path': '/synthetic/bin/python'},
                            'content': [{'type': 'text', 'text': text}]},
                        'llm_content': [{'type': 'text', 'text': text}]}
            self.transcript.append({'request': {'id': response['id'], 'tool': tool, 'action': action},
                                    'response': copy.deepcopy(response)})
            return response

        def close(self, *, timeout_seconds=None):
            if not self.closed:
                self.closed = True
                self.transcript.append({'type': 'closed', 'scripted_cpu_only': True,
                                        'official_terminal_close_returned': True})

    class ScriptedAdapter:
        scripted_cpu_only = True
        maximum_input_tokens, maximum_output_tokens, temperature = 98304, 32768, .6
        request_defaults = {'model': REF_MODEL, 'max_tokens': 32768, 'temperature': .6,
                            'stream': False, 'chat_template_kwargs': {'enable_thinking': True}}

        def __init__(self, label, sequence, folder):
            self.condition, self.ledger = condition, BudgetLedger(condition)
            self.slot_id = 'v064:QWEN_REF_B5000K:scripted-' + label + ':0'
            self.sequence, self.folder, self.requests = list(sequence), folder, []
            folder.mkdir()

        def count(self, request):
            return exact_measure(request, list(range(256)), context_limit=131072,
                                 backend='scripted_cpu_units_not_actual_tokenizer')

        def complete(self, request, usage_id):
            if not self.sequence or usage_id != 'agent':
                raise AssertionError('Unexpected additional scripted request')
            action = self.sequence.pop(0)
            self.requests.append(copy.deepcopy(request))
            if action == 'resource':
                raise BeforeQwenDispatch('full_input_and_output_reservation_insufficient')
            n = len(self.requests)
            self.ledger.reserve(self.count(request), usage_id,
                                write_new(self.folder / f'request-{n:04d}.json', request))
            if action == 'failure':
                atomic_write(self.folder / 'ledger.json', json_bytes(self.ledger.snapshot()))
                raise RuntimeError('Scripted transport failure with retained unknown reservation')
            calls = []
            if action in {'missing', 'pass'}:
                command = 'python -m unittest ' + ('missing_tests' if action == 'missing' else 'tests.focused')
                calls = [{'id': f'call-{n}', 'type': 'function', 'function': {'name': 'terminal',
                    'arguments': json.dumps({'command': command, 'timeout': 10})}}]
            elif action == 'finish':
                calls = [{'id': f'call-{n}', 'type': 'function', 'function': {'name': 'finish',
                    'arguments': json.dumps({'message': 'Scripted finish, correctness not measured.'})}}]
            elif action != 'length':
                raise AssertionError('Unknown scripted action')
            completion = 32768 if action == 'length' else 16
            body = {'id': f'cpu-{self.folder.parent.name}-{n}', 'object': 'chat.completion', 'created': 0,
                    'model': REF_MODEL, 'choices': [{'index': 0,
                        'finish_reason': 'length' if action == 'length' else 'tool_calls',
                        'message': {'role': 'assistant', 'content': None, 'tool_calls': calls,
                                    'reasoning': 'Synthetic CPU reasoning'}}],
                    'usage': {'prompt_tokens': 256, 'completion_tokens': completion,
                              'total_tokens': completion + 256,
                              'completion_tokens_details': {'reasoning_tokens': completion if action == 'length' else 0}}}
            self.ledger.settle(body, write_new(self.folder / f'response-{n:04d}.json', body))
            atomic_write(self.folder / 'ledger.json', json_bytes(self.ledger.snapshot()))
            return body

    def message_text(request):
        return '\n'.join(content if isinstance(content, str) else
            '\n'.join(part.get('text', '') for part in content if isinstance(part, dict))
            for message in request['messages'] for content in [message.get('content', [])])

    try:
        for label, sequence in [('feedback_truncation', ['missing', 'pass', 'pass', 'length']),
                                ('native_finish', ['finish', 'finish']),
                                ('technical_failure', ['failure']), ('resource_boundary', ['resource'])]:
            case = output / label
            case.mkdir()
            workspace = case / 'workspace'
            workspace.mkdir()
            adapter = ScriptedAdapter(label, sequence, case / 'raw')
            start = time.monotonic()
            value = run_scripted_session(delegate=adapter, native_rpc_type=ScriptedRPC,
                native_rpc_kwargs={'label': label}, condition=condition,
                public_task='Scripted public issue: validate the controller call path.',
                public_context='Public execution facts: synthetic CPU fixture only.',
                public_python='/synthetic/bin/python', output=case / 'controller', workspace=workspace,
                started={'started': start, 'soft_at': start + 120, 'hard_at': start + 180,
                         'guard_path': str(case / 'controller/guard.json')})
            assert not value['production_dispatch_authorized']
            assert not value['candidate_exported'] and not value['official_scoring_performed']
            assert value['code_resolved'] is None and not value['process_tree_quiescence_proven']
            assert value['writer_shutdown_requested']
            assert WORKFLOW_GUIDANCE in message_text(adapter.requests[0])
            if label == 'feedback_truncation':
                assert value['status'] == 'closed' and len(adapter.requests) == 4
                assert value['terminal_boundary']['kind'] == 'settled_output_truncation'
                assert not value['normal_completion'] and not value['native_finished']
                assert 'reports an import or collection error' in message_text(adapter.requests[1])
                assert 'already produced the same visible result summary' in message_text(adapter.requests[3])
                assert value['ledger']['complete_actual_tokens'] == 33840
                assert value['truncation_policy']['observed_responses']['reasoning_only:length'] == 1
                assert not any('Your last response did not include a function call or a message.' in p.read_text()
                               for p in (case / 'controller/native-conversation').rglob('*.json'))
                public_events = json.loads((case / 'controller/public-feedback-events.json').read_bytes())
                assert any(e['kind'] == 'repeated_public_result' for e in public_events)
            elif label == 'native_finish':
                assert value['status'] == 'closed' and value['native_finished'] and value['normal_completion']
                assert 'terminal_boundary' not in value and len(adapter.requests) == 2
                assert FINISH_REVIEW in message_text(adapter.requests[1])
            elif label == 'technical_failure':
                assert value['status'] == 'technical_unknown' and len(adapter.requests) == 1
                assert value['ledger']['complete_actual_tokens'] is None
                assert value['ledger']['uncertain_reserved_tokens'] > 0
                assert 'terminal_boundary' not in value
            else:
                assert value['status'] == 'closed' and value['terminal_boundary']['kind'] == 'original_resource_boundary'
                assert value['ledger']['attempts'] == 0 and not value['normal_completion']
            result['cases'].append({'case': label, 'status': value['status'],
                'native_finished': value['native_finished'], 'normal_completion': value['normal_completion'],
                'code_resolved': value['code_resolved'], 'scripted_request_count': len(adapter.requests),
                'boundary_kind': value.get('terminal_boundary', {}).get('kind'),
                'controller_result': reference(case / 'controller/controller-result.json')})
        assert not any(forbidden.values())
        result['passed'] = True
    except BaseException as error:
        result.update(error={'type': type(error).__name__, 'message': str(error)}, traceback=traceback.format_exc())
    result['forbidden_operations'] = forbidden
    write_new(output / 'result.json', result)
    print(json.dumps({'passed': result['passed'], 'cases': len(result['cases']), 'error': result.get('error')}))
    return 0 if result['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    return control(parser.parse_args().output)


if __name__ == '__main__':
    raise SystemExit(main())
