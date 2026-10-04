"""CPU-only actual SDK/native-template controls for the fixed three candidates.

Six development cases per model execute scripted public read/error/done actions.
No weights, sampled model output, token_trace, trainable rollout or GPU is used.
"""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'runs/v030-runtime-deps'), str(ROOT / 'src'), str(ROOT)]
os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
os.environ.setdefault('OPENHANDS_SUPPRESS_BANNER', '1')

from proworksim.audit import code_identity  # noqa: E402
from proworksim.candidate_runtime_v030 import (  # noqa: E402
    DenseCandidateActor, MistralNativeTokenizer, candidate_profile,
)
from proworksim.deterministic_work_v024 import DeterministicCandidateActor  # noqa: E402
from proworksim.software_collaboration_v030 import (  # noqa: E402
    CASE_IDS, build_software_collaboration_case, case_spec,
)
from proworksim.software_context_v028 import (  # noqa: E402
    VERSION as CONTEXT_POLICY, project_software_request,
)
from proworksim.software_learning_v029 import CRITIC_MEMBERS  # noqa: E402
from proworksim.software_runtime_v030 import build_runtime, close_runtime, run_fragment  # noqa: E402
from proworksim.storage import atomic_write, digest, json_bytes, read_json  # noqa: E402

VERSION = 'native-code-template-sdk-cpu-qualification-v0.30'
CONTEXT, OUTPUT = 16384, 2048
CANDIDATES = ('current-9b', 'swe-next-14b', 'devstral-small-2507')
MISSING = 'cpu_native_template_definitely_missing_v030.py'
REQUIRED_SOURCE = [
    'scripts/qualify_code_templates_v030.py',
    'src/proworksim/candidate_runtime_v030.py',
    'src/proworksim/candidate_runtime_v015.py',
    'src/proworksim/candidate_runtime_v017.py',
    'src/proworksim/collaboration_actor_v022.py',
    'src/proworksim/deterministic_work_v024.py',
    'src/proworksim/local_model_service.py',
    'src/proworksim/training.py',
    'src/proworksim/online_collection.py',
    'src/proworksim/software_tasks_v030.py',
    'src/proworksim/software_collaboration_v027.py',
    'src/proworksim/software_collaboration_v028.py',
    'src/proworksim/software_collaboration_v029.py',
    'src/proworksim/software_collaboration_v030.py',
    'src/proworksim/software_runtime_v030.py',
    'src/proworksim/software_context_v028.py',
    'src/proworksim/harness_sdk.py',
    'src/proworksim/harness_port.py',
    'src/proworksim/harness_runtime.py',
    'src/proworksim/world_core.py',
    'src/proworksim/experience.py',
    'src/proworksim/storage.py',
]


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest(path.read_bytes())}


def write(path, value):
    atomic_write(Path(path), json_bytes(value))


def native_xml(name, arguments):
    parameters = '\n'.join('<parameter=' + key + '>\n' + (
        value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)) + '\n</parameter>'
        for key, value in arguments.items())
    return '<tool_call>\n<function=' + name + '>\n' + parameters + '\n</function>\n</tool_call><|im_end|>'


def scripted_native_output(candidate, renderer, name, arguments):
    if candidate == 'devstral-small-2507':
        from mistral_common.protocol.instruct.messages import AssistantMessage
        from mistral_common.protocol.instruct.tool_calls import FunctionCall, ToolCall
        assistant = AssistantMessage(tool_calls=[ToolCall(id='cpu000001',
            function=FunctionCall(name=name, arguments=json.dumps(arguments, ensure_ascii=False)))])
        ids = renderer.tokenizer.native.instruct_tokenizer.encode_assistant_message(
            assistant, is_before_last_user_message=False, continue_message=False)
        return renderer.tokenizer.decode(ids), ids, 'official_mistral_common_v13_assistant_encoder'
    if candidate == 'swe-next-14b':
        raw = '<tool_call>\n' + json.dumps({'name': name, 'arguments': arguments}, ensure_ascii=False) + '\n</tool_call><|im_end|>'
        kind = 'official_qwen2_json_tool_call_grammar'
    else:
        raw, kind = native_xml(name, arguments), 'official_qwen35_xml_tool_call_grammar'
    return raw, renderer.tokenizer(raw, add_special_tokens=False)['input_ids'], kind


def tool_rounds(messages):
    rows = []
    for index, message in enumerate(messages[:-1]):
        calls = message.get('tool_calls') or []
        result = messages[index + 1]
        if (message['role'] != 'assistant' or len(calls) != 1 or result['role'] != 'tool'
                or result['tool_call_id'] != calls[0]['id']):
            continue
        function = calls[0]['function']
        rows.append({'assistant_index': index, 'tool_index': index + 1,
                     'tool_call_id': calls[0]['id'], 'name': function['name'],
                     'arguments': json.loads(function['arguments']) if isinstance(function['arguments'], str)
                     else function['arguments'], 'response': json.loads(result['content'])})
    return rows


def native_messages_carry_exact_response(messages, expected):
    """Find the unmodified real response inside an explicit native tool envelope."""
    def contains(value):
        if value == expected:
            return True
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except (ValueError, TypeError):
                return False
            return contains(decoded) if decoded != value else False
        if isinstance(value, dict):
            return any(contains(item) for item in value.values())
        if isinstance(value, list):
            return any(contains(item) for item in value)
        return False
    return any(message['role'] == 'tool' and contains(message.get('content')) for message in messages)


class FixtureOwner:
    """A declared response program using real tokenizer IDs, never token_trace."""
    software_context_policy = CONTEXT_POLICY

    def __init__(self, candidate, renderer, scripts, output, window_id):
        self.candidate, self.renderer, self.scripts = candidate, renderer, scripts
        self.output, self.window_id = Path(output), window_id
        self.output.mkdir(parents=True, exist_ok=False)
        self.calls, self.measurements = Counter(), []
        self.recipe = {'temperature': 0.7, 'max_output_tokens': OUTPUT,
                       'max_length': CONTEXT, 'members': list(CRITIC_MEMBERS)}
        self.identity = {'version': 'shared-actor-identity-v0.13',
            'policy_version': 'cpu-v030-native-template-fixture:' + candidate,
            'adapter_sha256': digest(b'no-adapter-explicit-CPU-fixture'),
            'base_manifest_sha256': digest(b'no-weights-loaded-explicit-CPU-fixture'),
            'inference_profile_sha256': digest(json_bytes(renderer.inference_profile))}
        self.transport = self

    def freeze_identity(self):
        return copy.deepcopy(self.identity)

    def complete(self, request, **_):
        observation = next(json.loads(message['content'])['observation']
                           for message in reversed(request['messages']) if message['role'] == 'user'
                           and 'observation' in json.loads(message['content']))
        member = observation['actor_id']
        phase, name, arguments = self.scripts[member][self.calls[member]]
        self.calls[member] += 1
        folder = self.output / f'request-{len(self.measurements):03d}'
        folder.mkdir()
        write(folder / 'original-request.json', request)
        if request['max_tokens'] != OUTPUT:
            raise ValueError('The actual SDK output reservation changed')
        selected, projection = project_software_request(request, render=self.renderer.prepare_request,
            tokenizer=self.renderer.tokenizer, context_limit=CONTEXT)
        rendered, normalized, native_projection = self.renderer.prepare_request(selected)
        input_ids = self.renderer.tokenizer(rendered, add_special_tokens=False)['input_ids']
        raw, output_ids, encoding_kind = scripted_native_output(
            self.candidate, self.renderer, name, arguments)
        parsed, error = self.renderer.parse_response(raw, selected)
        calls = parsed.get('tool_calls') or []
        roundtrip = (error is None and len(calls) == 1 and calls[0]['function']['name'] == name
                     and json.loads(calls[0]['function']['arguments']) == arguments)
        original_rounds, selected_rounds = tool_rounds(request['messages']), tool_rounds(selected['messages'])
        original_errors = [row for row in original_rounds if row['name'] == 'read_file'
                           and row['arguments'].get('path') == MISSING and row['response'].get('ok') is False]
        selected_errors = [row for row in selected_rounds if row['name'] == 'read_file'
                           and row['arguments'].get('path') == MISSING and row['response'].get('ok') is False]
        native_tool_responses_preserved = all(native_messages_carry_exact_response(normalized, row['response'])
                                              for row in selected_rounds)
        native_error_preserved = bool(selected_errors) and all(
            native_messages_carry_exact_response(normalized, row['response']) for row in selected_errors)
        for filename, value in [('selected-request.json', selected), ('projection.json', projection),
                               ('normalized-messages.json', normalized), ('native-projection.json', native_projection),
                               ('input-ids.json', input_ids), ('scripted-output-ids.json', output_ids),
                               ('parsed-scripted-action.json', {'message': parsed, 'error': error}),
                               ('actual-input-tool-rounds.json', original_rounds)]:
            write(folder / filename, value)
        atomic_write(folder / 'rendered-prompt.txt', rendered.encode())
        atomic_write(folder / 'scripted-output.txt', raw.encode())
        measurement = {'member': member, 'phase': phase, 'scripted_action': name,
            'scripted_arguments': copy.deepcopy(arguments), 'prompt_tokens': len(input_ids),
            'original_prompt_tokens': projection['original_prompt_tokens'], 'reserved_output_tokens': OUTPUT,
            'remaining_context_after_output_reservation': CONTEXT - OUTPUT - len(input_ids),
            'fits_context': projection['fits'], 'removed_indices': projection['removed_indices'],
            'retained_messages_unchanged': projection['retained_messages_unchanged'],
            'scripted_output_tokens': len(output_ids), 'native_codec_roundtrip': roundtrip,
            'output_encoding_kind': encoding_kind, 'actual_error_seen_in_original': bool(original_errors),
            'actual_error_retained_in_selected': bool(selected_errors),
            'actual_error_retained_in_native_messages': native_error_preserved,
            'actual_tool_responses_preserved_in_native_messages': native_tool_responses_preserved,
            'actual_error_feedback': copy.deepcopy(selected_errors),
            'original_request': reference(folder / 'original-request.json'),
            'projection': reference(folder / 'projection.json'),
            'native_input_ids': reference(folder / 'input-ids.json'),
            'native_projection': reference(folder / 'native-projection.json'),
            'scope': 'Actual SDK request and real native tokenizer IDs; scripted actions, zero model generation.'}
        self.measurements.append(measurement)
        write(folder / 'measurement.json', measurement)
        if not projection['fits'] or len(input_ids) + OUTPUT > CONTEXT:
            raise ValueError('Native SDK context does not fit the unchanged 16K/2048 profile')
        if not roundtrip or len(output_ids) > OUTPUT:
            raise ValueError('Native scripted action did not preserve exact public arguments/output cap')
        if not native_tool_responses_preserved:
            raise ValueError('The native renderer did not preserve a selected real tool response')
        if phase == 'after_actual_world_error' and not native_error_preserved:
            raise ValueError('Real WorldCore error was not retained in the next native-encoded request')
        body = {'id': self.window_id + '-' + member + '-' + str(self.calls[member]),
            'model': 'explicit-CPU-native-template-response-program',
            'system_fingerprint': self.identity['policy_version'], 'actor_identity': self.freeze_identity(),
            'online_window_id': self.window_id, 'choices': [{'message': parsed, 'finish_reason': 'tool_calls'}],
            'usage': {'prompt_tokens': len(input_ids), 'completion_tokens': len(output_ids),
                      'total_tokens': len(input_ids) + len(output_ids)},
            'fixture_only': True, 'generation_started': False,
            'qualification_provenance': 'CPU_scripted_SDK_transport_no_model_no_logits_no_token_trace'}
        assert 'token_trace' not in body
        envelope = {'http_status': 200, 'body': body, 'raw_body': json_bytes(body).decode()}
        write(folder / 'scripted-response.json', envelope)
        return envelope


def largest_source_read(files):
    candidates = []
    for path, text in files.items():
        if not path.startswith('src/marshmallow/') or not path.endswith('.py'):
            continue
        lines = text.splitlines()
        for index in range(len(lines)):
            candidates.append((len('\n'.join(lines[index:index + 180])), path, index + 1))
    characters, path, start = max(candidates)
    return {'path': path, 'start_line': start, 'max_lines': 180}, characters


def qualify_case(candidate, renderer, case_id, output):
    output.mkdir(parents=True, exist_ok=False)
    initial = case_spec(case_id)
    spec = case_spec(case_id, role_decision_limits=dict.fromkeys(initial['active_roles'], 3))
    prepared = build_software_collaboration_case(spec, output / 'case')
    first = spec['active_roles'][0]
    files = prepared.world._bundle(first)[2]['files']
    if MISSING in files:
        raise ValueError('The deliberately absent public path unexpectedly exists')
    read, characters = largest_source_read(files)
    scripts = {member: [
        ('initial', 'read_file', read),
        ('after_successful_source_read', 'read_file', {'path': MISSING, 'start_line': 1, 'max_lines': 1}),
        ('after_actual_world_error', 'staff_done', {'reason': 'Explicit CPU native-template fixture complete; no model work'}),
    ] for member in spec['active_roles']}
    owner = FixtureOwner(candidate, renderer, scripts, output / 'requests', 'CPU-v030-' + candidate + '-' + case_id)
    runtime, captured, _ = build_runtime(owner, prepared, output / 'runtime')
    if owner.measurements:
        raise ValueError('Constructing the actual SDK invoked the fixture transport')
    try:
        boundary = run_fragment(prepared, runtime)
        write(output / 'scripted-actions.json', scripts)
        write(output / 'boundary.json', boundary)
        write(output / 'captures.json', captured)
        write(output / 'experience.json', runtime.recorder.snapshot())
        tools = [(member, event['payload']) for member, events in captured.items() for event in events
                 if event['kind'] == 'tool_call' and event['payload']['action'] == 'read_file']
        reads, errors = [], []
        for member, payload in tools:
            response = payload['response']
            if response.get('ok') is True:
                reads.append({'member': member, 'response': response})
            else:
                errors.append({'member': member, 'response': response})
        after_error = [row for row in owner.measurements if row['phase'] == 'after_actual_world_error']
        feedback_matches = all(any(error['member'] == row['member']
                                  and error['response'] == feedback['response']
                                  for feedback in row['actual_error_feedback'] for error in errors)
                               for row in after_error)
        count = len(spec['active_roles'])
        report = {'candidate': candidate, 'case_id': case_id, 'active_members': spec['active_roles'],
            'case_category': spec['category'], 'model_calls': 0,
            'scripted_sdk_transport_attempts': sum(owner.calls.values()),
            'scripted_sdk_transport_calls': len(owner.measurements),
            'training_eligible': False, 'training_token_traces': 0, 'trainable_rollouts_created': 0,
            'read_arguments': read, 'selected_source_page_characters': characters,
            'long_read_successes': reads, 'actual_world_errors': errors,
            'error_feedback_next_request_count': len(after_error),
            'next_native_request_feedback_equals_actual_world_response': feedback_matches,
            'boundary_status': boundary['status'], 'measurements': owner.measurements,
            'minimum_remaining_margin_tokens': min(row['remaining_context_after_output_reservation']
                                                   for row in owner.measurements),
            'projected_request_count': sum(bool(row['removed_indices']) for row in owner.measurements),
            'forced_baseline_public_test': prepared.prefix['forced_initial_public_test'],
            'scope': 'Finite CPU public-tool protocol fixture, not model repair, business success or learning probability qualification.'}
        report['passed'] = (len(owner.measurements) == 3 * count and len(reads) == len(errors) == count
            and len(after_error) == count and feedback_matches and boundary['status'] == 'workers_done'
            and all(row['fits_context'] and row['native_codec_roundtrip'] and row['retained_messages_unchanged']
                    and row['actual_tool_responses_preserved_in_native_messages']
                    and row['remaining_context_after_output_reservation'] >= 0 for row in owner.measurements))
        write(output / 'summary.json', report)
        return report
    finally:
        close_runtime(runtime)


def renderer_for(candidate, prior, assets):
    from transformers import AutoTokenizer
    if candidate == 'current-9b':
        root = Path(prior['model']).resolve()
        renderer = object.__new__(DeterministicCandidateActor)
        renderer.inference_profile = copy.deepcopy(prior['runtime_profile'])
        if (renderer.inference_profile['max_context_tokens'] != CONTEXT
                or renderer.inference_profile['max_output_tokens'] != OUTPUT
                or renderer.inference_profile['chat_template_kwargs']['enable_thinking'] is not False):
            raise ValueError('The current 9B profile is not the frozen nonthinking 16K/2048 combination')
    else:
        renderer = object.__new__(DenseCandidateActor)
        renderer.inference_profile = candidate_profile(candidate)
        root = Path(assets) / (candidate + '-' + renderer.inference_profile['revision'][:12])
    renderer.tokenizer = (MistralNativeTokenizer(root) if candidate == 'devstral-small-2507' else
                         AutoTokenizer.from_pretrained(root, local_files_only=True, trust_remote_code=False))
    names = ('tekken.json', 'config.json') if candidate == 'devstral-small-2507' else (
        'tokenizer.json', 'tokenizer_config.json', 'chat_template.jinja', 'vocab.json', 'merges.txt',
        'config.json', 'added_tokens.json', 'special_tokens_map.json')
    return renderer, {name: reference(root / name) for name in names if (root / name).exists()}


def qualify(output, prior_model_plan, asset_root):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    prior_path = Path(prior_model_plan).resolve()
    prior = read_json(prior_path)
    source_files = {name: reference(ROOT / name) for name in REQUIRED_SOURCE}
    from proworksim import software_tasks_v030 as tasks
    assets = {str(path.relative_to(ROOT)): reference(path)
              for path in sorted(tasks.ASSETS.rglob('*')) if path.is_file()}
    source_manifest = read_json(tasks.ASSETS / 'source-manifest.json')
    upstream_root = ROOT / source_manifest['source']['source_relative_path']
    upstream_assets = {str((upstream_root / name).relative_to(ROOT)): reference(upstream_root / name)
                       for name in source_manifest['source']['files_sha256']}
    report = {'version': VERSION, 'started_at': datetime.now(timezone.utc).isoformat(),
        'passed': False, 'model_calls': 0, 'model_weights_loaded': False, 'gpu_used': False,
        'optimizer_updates': 0, 'training_token_traces': 0, 'trainable_rollouts_created': 0,
        'max_context_tokens': CONTEXT, 'reserved_output_tokens': OUTPUT,
        'context_policy': CONTEXT_POLICY, 'source': code_identity(),
        'required_source_files': source_files, 'required_development_assets': assets,
        'required_upstream_source_files': upstream_assets,
        'prior_model_plan': reference(prior_path), 'tokenizer_files': {},
        'runtime_versions': {name: importlib.metadata.version(name) for name in ('transformers', 'mistral-common')},
        'controls': [], 'candidate_count': len(CANDIDATES), 'case_count': len(CASE_IDS),
        'scope': 'CPU native tokenization and actual SDK/WorldCore read/error feedback only; scripted outputs are not model capability, inference or training qualification.'}
    write(output / 'qualification.json', report)
    try:
        renderers = {}
        for candidate in CANDIDATES:
            renderer, refs = renderer_for(candidate, prior, asset_root)
            renderers[candidate] = renderer
            report['tokenizer_files'][candidate] = refs
        write(output / 'qualification.json', report)

        # One real Devstral read/error/done sequence admits the shared native
        # role envelope before the remaining bounded matrix is constructed.
        first_dev = qualify_case('devstral-small-2507', renderers['devstral-small-2507'],
                                 CASE_IDS[0], output / 'devstral-small-2507' / CASE_IDS[0])
        report['native_integration_probe'] = reference(output / 'devstral-small-2507' / CASE_IDS[0] / 'summary.json')
        report['native_integration_probe_passed'] = first_dev['passed']
        write(output / 'qualification.json', report)
        print(json.dumps({'stage': 'devstral_actual_sdk_native_probe', 'passed': first_dev['passed'],
                          'scripted_sdk_calls': first_dev['scripted_sdk_transport_calls']}), flush=True)
        if not first_dev['passed']:
            raise ValueError('Devstral actual SDK/native probe failed; remaining matrix not started')

        def model_controls(candidate):
            rows = [first_dev] if candidate == 'devstral-small-2507' else []
            for case_id in CASE_IDS:
                if candidate == 'devstral-small-2507' and case_id == CASE_IDS[0]:
                    continue
                row = qualify_case(candidate, renderers[candidate], case_id, output / candidate / case_id)
                rows.append(row)
                print(json.dumps({'candidate': candidate, 'case_id': case_id, 'passed': row['passed'],
                    'scripted_sdk_calls': row['scripted_sdk_transport_calls'],
                    'minimum_margin': row['minimum_remaining_margin_tokens']}), flush=True)
            return rows
        with ThreadPoolExecutor(max_workers=3) as pool:
            for controls in pool.map(model_controls, CANDIDATES):
                report['controls'].extend(controls)
                write(output / 'qualification.json', report)
        measurements = [row for control in report['controls'] for row in control['measurements']]
        report.update(combination_count=len(report['controls']),
            scripted_sdk_transport_attempts=sum(row['scripted_sdk_transport_attempts'] for row in report['controls']),
            scripted_sdk_transport_calls=sum(row['scripted_sdk_transport_calls'] for row in report['controls']),
            native_roundtrip_count=sum(row['native_codec_roundtrip'] for row in measurements),
            actual_world_error_count=sum(len(row['actual_world_errors']) for row in report['controls']),
            error_feedback_next_request_count=sum(row['error_feedback_next_request_count'] for row in report['controls']),
            minimum_remaining_margin_tokens=min(row['remaining_context_after_output_reservation'] for row in measurements),
            maximum_selected_prompt_tokens=max(row['prompt_tokens'] for row in measurements),
            maximum_original_prompt_tokens=max(row['original_prompt_tokens'] for row in measurements),
            projected_request_count=sum(bool(row['removed_indices']) for row in measurements),
            source_after=code_identity())
        report['required_files_unchanged'] = all(reference(ref['path']) == ref for ref in [
            *source_files.values(), *assets.values(), *upstream_assets.values(),
            *(ref for files in report['tokenizer_files'].values() for ref in files.values())])
        report['whole_source_tree_unchanged'] = report['source']['source_tree_sha256'] == report['source_after']['source_tree_sha256']
        report['source_scope_note'] = 'Direct required source/assets/tokenizers must remain unchanged; all-source identities also recorded, including unrelated parallel edits.'
        torch = sys.modules.get('torch')
        report['torch_cuda_initialized'] = bool(torch is not None and torch.cuda.is_initialized())
        report['passed'] = (len(CASE_IDS) == 6 and report['combination_count'] == 18
            and report['scripted_sdk_transport_calls'] == report['native_roundtrip_count'] == 72
            and report['actual_world_error_count'] == report['error_feedback_next_request_count'] == 24
            and report['required_files_unchanged'] and not report['torch_cuda_initialized']
            and all(row['passed'] for row in report['controls']))
    except BaseException as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        report['ended_at'] = datetime.now(timezone.utc).isoformat()
        write(output / 'qualification.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prior-model-plan', type=Path, default=ROOT / 'runs/domain-v0201-p1-9b/plan.json')
    parser.add_argument('--asset-root', type=Path, default=ROOT / 'runs/assets/models')
    args = parser.parse_args()
    report = qualify(args.output, args.prior_model_plan, args.asset_root)
    print(json.dumps({key: report[key] for key in ('passed', 'combination_count', 'model_calls',
        'scripted_sdk_transport_calls', 'native_roundtrip_count', 'actual_world_error_count',
        'minimum_remaining_margin_tokens', 'maximum_selected_prompt_tokens', 'projected_request_count')}))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
