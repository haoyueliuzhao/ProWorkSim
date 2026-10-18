"""Twelve real SDK initial inputs after independent release; zero generation.

PS1 retains its first-step decision bookkeeping. OH uses the official SDK
adapter's initial_capture boundary. Their inputs are intentionally different;
no cross-framework equality test or opaque-ID rewriting is performed.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from proworksim.software_bridge_sources_v052 import RepositorySources, TASK_IDS, checked, ref, write_new
from proworksim.software_calibration_collector_v051 import build_runtime
from proworksim.software_calibration_runtime_v051 import prepare_native_input, validate_native_input
from proworksim.software_calibration_world_v051 import case_spec, build_software_collaboration_case
from proworksim.software_organization_runtime_v038 import close_runtime
from proworksim.storage import digest, json_bytes
from scripts.software_bridge_v052 import CONTRACT, inventory
from scripts.software_holdout_inputs_v051 import ExactTokenizer, CaptureTransport, InitialCaptured, evaluate_request

VERSION = 'v052-actual-initial-input-qualification-v1'
PURPOSE = 'native_openhands_managed_s1_bridge'
SDK_VERSION = '1.49.6'
SDK_COMMIT = 'fcc102a697874d54a357e36004e02c95040dbdc0'


def read(path):
    return json.loads(Path(path).read_bytes())


def validate_records(release, source, design, reference_runtime):
    if (release.get('version') != 'v052-initial-input-execution-release-v1' or release.get('released') is not True
            or release.get('maximum_initial_SDK_requests') != 12):
        raise ValueError('Root must release the one finite twelve-request initial qualification')
    if (source.get('version') != 'v052-shared-source-qualification-v1' or source.get('passed') is not True
            or source.get('fixture_only') is not False or source.get('completed') is not True
            or source.get('qualified_case_ids') != list(TASK_IDS) or source.get('blocked_case_ids') != []
            or source.get('runtime_manifest') != release['test_runtime']):
        raise ValueError('All six tasks must qualify under the exact final shared runtime before any SDK capture')
    if (reference_runtime.get('version') != 'v052-openhands-reference-runtime-v1'
            or reference_runtime.get('sdk_version') != SDK_VERSION or reference_runtime.get('sdk_commit') != SDK_COMMIT
            or reference_runtime.get('tools_version') != SDK_VERSION):
        raise ValueError('The stable official OpenHands Agent/Conversation and tools identity is required')
    rows = inventory(design)
    if len(rows) != 12:
        raise ValueError('Capture exactly one OH_ref and PS1 request for each original task')
    return rows


def gate(release_path):
    release = read(release_path)
    if release.get('version') != 'v052-initial-input-execution-release-v1' or release.get('released') is not True:
        raise ValueError('Initial SDK/tokenizer work is not released')
    required = ('design', 'source_qualification', 'test_runtime', 'reference_runtime', 'raw_owner_metadata', 'model_manifest')
    paths = {key: checked(release[key]) for key in required}
    source, design, reference_runtime = (read(paths[key]) for key in ('source_qualification', 'design', 'reference_runtime'))
    rows = validate_records(release, source, design, reference_runtime)
    if not release.get('implementation_sources') or not release.get('control_refs'):
        raise ValueError('Frozen implementations and their finite controls must precede actual inputs')
    for reference in release['implementation_sources'].values():
        checked(reference)
    if ref(__file__) not in release['implementation_sources'].values():
        raise ValueError('This actual initial-input script must be included in the source freeze')
    for reference in release['control_refs']:
        result = read(checked(reference))
        if result.get('passed') is not True:
            raise ValueError('Every bound prerequisite control summary must have closed successfully')
    for reference in reference_runtime['modules'].values():
        checked(reference)
    checked(source['adapter_manifest'])
    return release, source, rows


class MetadataOwner:
    """Recorded raw-owner identity only, without tensors, a model or RNG guard."""
    def __init__(self, metadata, *, metadata_reference, model_manifest, slot_id, tokenizer):
        identity = copy.deepcopy(metadata['actor_identity'])
        profile = metadata['inference_profile']
        if (identity.get('raw_release') is not True or identity.get('trained_adapter_loaded') is not False
                or identity.get('checkpoint') is not None or identity.get('adapter_sha256') is not None
                or identity.get('base_manifest') != model_manifest or not identity.get('policy_version')
                or profile.get('path') != 'project' or profile.get('contract') != CONTRACT):
            raise ValueError('Initial metadata must bind the same raw release and project numerical provider')
        self.recipe = {'max_length': 18432, 'max_output_tokens': 2048, 'temperature': .7}
        self.contract, self.identity = copy.deepcopy(CONTRACT), identity
        self.path = 'project'
        self.window_id = 'calibration-v051:' + slot_id
        self.tokenizer, self.native = tokenizer, {}
        self.metadata_reference = metadata_reference
        self.inference_profile = copy.deepcopy(profile)

    def freeze_identity(self):
        return copy.deepcopy(self.identity)

    def prepare_request(self, request):
        key = json_bytes(request)
        if key not in self.native:
            self.native[key] = prepare_native_input(self.tokenizer, request, self.contract)
        record = self.native[key]
        return record['rendered_prompt'], record['actual_prompt_messages'], copy.deepcopy(record)


def validate_capture_counters(condition, counters, *, unchanged=True):
    if not unchanged:
        raise ValueError('Initial request capture cannot alter the initial business tree/state')
    if any(counters.get(key) != 0 for key in
           ('attempts', 'reservation_tokens', 'responses', 'tool_actions', 'model_generations')):
        raise ValueError('Capture must stop before reservation/dispatch/response/tool effects')
    if condition == 'PS1' and (counters.get('harness_decisions') != 1 or counters.get('team_decisions') != 1):
        raise ValueError('Preserve the real first PS1 opportunity bookkeeping, without a shim or rollback')
    if condition == 'OH_ref' and counters.get('native_SDK_LLM_entries') != 1:
        raise ValueError('Require one actual official SDK initial LLM entry')
    return True


def capture_ps1(provider, row, owner, destination):
    destination = Path(destination)
    prepared = build_software_collaboration_case(case_spec(row['task_id'], provider=provider),
        destination / 'prepared', provider=provider)
    owner.transport = CaptureTransport(owner, destination / 'transport')
    runtime, _, _ = build_runtime(owner, prepared, destination / 'sdk')
    before = prepared.world.store.load()
    try:
        try:
            runtime.step()
        except InitialCaptured:
            pass
        else:
            raise ValueError('PS1 SDK failed to reach its first pre-reservation request boundary')
        captured = owner.transport.captured
        if captured is None or captured['runner_turn']['member_id'] != 'member_001' or runtime.labels != ['member_001']:
            raise ValueError('The actual single-member initial SDK request was not captured')
        meter = runtime.policies['member_001'].meter
        budget = runtime.team_budget.snapshot()
        counters = {'harness_decisions': meter['decisions'], 'team_decisions': budget['decisions'],
            'adapter_decisions': None, 'adapter_decisions_status': 'not_applicable_PS1',
            'attempts': budget['attempts'], 'reservation_tokens': budget['held_tokens'],
            'charged_tokens': budget['charged_tokens'], 'responses': runtime.policies['member_001']._completions,
            'tool_actions': runtime.actions, 'model_generations': 0}
        unchanged = prepared.world.store.load() == before
        validate_capture_counters('PS1', counters, unchanged=unchanged)
        if counters['charged_tokens'] != 0 or meter['http_attempts'] != 0:
            raise ValueError('No generation cost or native attempt is allowed during capture')
        write_new(destination / 'original-request.json', captured['request'])
        write_new(destination / 'capture.json', {'version': VERSION, 'condition': 'PS1',
            'runner_turn': captured['runner_turn'], 'capture_counters': counters, 'team_budget': budget,
            'world_unchanged': unchanged, 'raw_owner_metadata': owner.metadata_reference,
            'model_weights_loaded': False, 'new_guard_pass_claimed': False,
            'qualification_bookkeeping_transferred_to_formal_episode': False,
            'scope': 'Real first SDK opportunity, stopped before prepare_for_budget returns; one CPU bookkeeping decision, no model generation.'})
        return captured['request'], counters
    finally:
        close_runtime(runtime)


def capture_oh(provider, row, owner, destination, reference_runtime):
    from proworksim.software_bridge_openhands_v052 import collect_episode

    destination = Path(destination)
    worktree = destination / 'worktree'
    worktree.mkdir(parents=True, exist_ok=False)
    case = provider.build_case(row['task_id'])
    for name, text in case['files'].items():
        path = worktree / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode('utf-8'))
    case.update(runner_spec=provider.runner_spec(row['task_id']), reference_runtime=reference_runtime)
    captured = []
    def callback(request, native):
        if captured:
            raise ValueError('The official initial provider may be captured once only')
        captured.append((copy.deepcopy(request), copy.deepcopy(native)))
    result = collect_episode(owner=owner, task_source=case, provider=provider, slot_id=row['slot_id'],
        sampling_seed=row['seed'], worktree=worktree, episode_folder=destination / 'episode',
        initial_capture=callback, allow_cpu_fixture=False)
    if result.get('status') != 'initial_request_captured' or len(captured) != 1:
        raise ValueError('Official Agent/Conversation did not produce one complete initial provider request')
    counters = result['capture_counters']
    current = {str(path.relative_to(worktree)): path.read_bytes().decode('utf-8')
               for path in sorted(worktree.rglob('*')) if path.is_file() and '__pycache__' not in path.parts and '.git' not in path.parts}
    validate_capture_counters('OH_ref', counters, unchanged=current == case['files'])
    request, native = captured[0]
    write_new(destination / 'original-request.json', request)
    write_new(destination / 'capture.json', {'version': VERSION, 'condition': 'OH_ref', 'capture_counters': counters,
        'original_adapter_result': result, 'raw_owner_metadata': owner.metadata_reference,
        'model_weights_loaded': False, 'new_guard_pass_claimed': False,
        'qualification_bookkeeping_transferred_to_formal_episode': False})
    return request, native, counters


def native_capacity(native, contract):
    fits = validate_native_input(native, contract)
    return {'original_prompt_tokens': native['prompt_tokens'], 'selected_prompt_tokens': native['prompt_tokens'],
        'protected_prompt_tokens': native['prompt_tokens'], 'reserved_output_tokens': contract['max_output_tokens'],
        'context_limit': contract['context_limit'], 'fits': fits,
        'scope': 'Original official OH request; no PS1 Gamma1 projection or cross-framework normalization applied'}


def qualify(*, release_path, output):
    release, source, rows = gate(release_path)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'version': VERSION, 'purpose': PURPOSE, 'fixture_only': False, 'completed': False, 'passed': False,
        'design': release['design'], 'source_qualification': release['source_qualification'],
        'test_runtime': release['test_runtime'], 'reference_runtime': release['reference_runtime'],
        'input_release': ref(release_path), 'raw_owner_metadata': release['raw_owner_metadata'],
        'actual_initial_SDK_requests': 0, 'maximum_initial_SDK_requests': 12, 'rows': [],
        'new_model_calls': 0, 'programmed_responses': 0, 'repository_test_executions': 0,
        'weights_loaded': False, 'GPU_workers': 0, 'new_parameter_updates': 0,
        'cross_framework_input_equality_required': False, 'opaque_identifier_normalization': False,
        'future_identifier_or_later_input_capacity_guaranteed': False}
    write_new(output / 'declaration.json', report)
    tokenizer_spec = release['tokenizer']
    model = Path(tokenizer_spec['model_path']).resolve()
    expected = {model / 'tokenizer.json', model / 'tokenizer_config.json'}
    if (model / 'chat_template.jinja').is_file():
        expected.add(model / 'chat_template.jinja')
    if {checked(reference) for reference in tokenizer_spec['files']} != expected:
        raise ValueError('Bind all exact tokenizer/config/template files before encoding')
    if checked(release['model_manifest']) != model / 'proworksim-manifest.json':
        raise ValueError('Raw model metadata and tokenizer must belong to the same frozen assets')
    from transformers import AutoTokenizer
    tokenizer = ExactTokenizer(AutoTokenizer.from_pretrained(model, local_files_only=True))
    metadata = read(checked(release['raw_owner_metadata']))
    def no_tests(**kwargs):
        raise AssertionError('Initial input qualification cannot run business tests')
    provider = RepositorySources(source['source_root'], runtime_manifest=checked(release['test_runtime']),
        expected_manifest_sha256=source['adapter_manifest']['sha256'], runner=no_tests)
    cache = {}
    for row in rows:
        if provider._entry(row['task_id'])['row']['row_sha256'] != row['source_row_sha256']:
            raise ValueError('Original task row identity differs from the predeclared bridge design')
        folder = output / row['slot_id']
        owner = MetadataOwner(metadata, metadata_reference=release['raw_owner_metadata'],
            model_manifest=release['model_manifest'], slot_id=row['slot_id'], tokenizer=tokenizer)
        if Path(owner.identity['model_path']).resolve() != model:
            raise ValueError('Recorded raw owner metadata must use the same model assets')
        if row['condition'] == 'PS1':
            request, counters = capture_ps1(provider, row, owner, folder)
            measured, reused = evaluate_request(request, owner, 'member_001', cache)
            projection = measured['projection']
            selected = measured['selected']
            natives = measured['native']
            native = next(item for item in natives if item['request_sha256'] == digest(json_bytes(selected)))
            validate_native_input(native, owner.contract)
            if native['prompt_tokens'] != projection['selected_prompt_tokens']:
                raise ValueError('Gamma1 selected token count differs from the exact native input')
        else:
            request, native, counters = capture_oh(provider, row, owner, folder, release['reference_runtime'])
            projection, selected, natives, reused = native_capacity(native, owner.contract), request, [native], False
        report['actual_initial_SDK_requests'] += 1
        write_new(folder / 'selected-request.json', selected)
        write_new(folder / 'projection.json', projection)
        write_new(folder / 'native-inputs.json', natives)
        write_new(folder / 'selected-native-input.json', native)
        case = provider.build_case(row['task_id'])
        record = {'slot_id': row['slot_id'], 'task_id': row['task_id'], 'condition': row['condition'],
            'member_id': 'member_001', 'source_row_sha256': row['source_row_sha256'],
            'initial_files_sha256': case['initial_binding']['initial_files_sha256'],
            'problem_sha256': digest(case['root_goal'].encode()), 'model_manifest': release['model_manifest'],
            'raw_actor_identity_metadata_only': owner.freeze_identity(), 'window_id': owner.window_id,
            'capture_counters': counters, 'exact_request_projection_reused': reused,
            **{key: projection[key] for key in ('original_prompt_tokens', 'selected_prompt_tokens',
                'protected_prompt_tokens', 'reserved_output_tokens', 'context_limit', 'fits')},
            'original_request': ref(folder / 'original-request.json'), 'selected_request': ref(folder / 'selected-request.json'),
            'projection': ref(folder / 'projection.json'), 'native_input': ref(folder / 'selected-native-input.json'),
            'all_native_inputs': ref(folder / 'native-inputs.json'), 'capture': ref(folder / 'capture.json')}
        report['rows'].append(record)
        write_new(output / (row['slot_id'] + '-progress.json'), report)
    paired = {case: [row for row in report['rows'] if row['task_id'] == case] for case in TASK_IDS}
    same_sources = all(len(items) == 2 and len({(row['source_row_sha256'], row['initial_files_sha256'], row['problem_sha256'])
        for row in items}) == 1 for items in paired.values())
    report.update(completed=True, passed=len(report['rows']) == 12 and same_sources and all(row['fits'] for row in report['rows']),
        same_task_source_and_assets_bound=same_sources, tokenizer_files=copy.deepcopy(tokenizer_spec['files']),
        tokenizer_encoding_calls=tokenizer.encodings, tokenizer_encoding_exact_cache_hits=tokenizer.encoding_hits,
        native_template_renders=tokenizer.renders, native_template_exact_cache_hits=tokenizer.render_hits,
        PS1_harness_decisions=sum(row['capture_counters']['harness_decisions'] for row in report['rows'] if row['condition'] == 'PS1'),
        PS1_team_decisions=sum(row['capture_counters']['team_decisions'] for row in report['rows'] if row['condition'] == 'PS1'),
        model_generations=0, qualification_bookkeeping_transferred_to_formal_episode=False)
    write_new(output / 'summary.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = qualify(release_path=args.release, output=args.output)
    print(json.dumps({key: result[key] for key in ('version', 'passed', 'actual_initial_SDK_requests', 'new_model_calls')}))


if __name__ == '__main__':
    main()
