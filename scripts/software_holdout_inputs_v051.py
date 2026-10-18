"""Gated initial SDK/request qualification; never loads weights or generates.

Execute only from the common implementation frozen before HOLD content access.
Each role is captured in a separate untouched world, with the frozen first
member retained in the case. Stop at SDK budget preparation before dispatch.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from proworksim.repository_sources_holdout_v051 import HOLD_IDS, PURPOSE, RepositorySources
from proworksim.software_calibration_runtime_v051 import prepare_native_input
from proworksim.software_context_v034 import observation_messages
from proworksim.software_context_v048 import SoftwareContextTransport, project_software_request
from proworksim.software_holdout_collector_v051 import NATIVE_CONTRACT, build_runtime
from proworksim.software_holdout_world_v051 import MEMBERS, build_software_collaboration_case, case_spec
from proworksim.software_organization_runtime_v038 import close_runtime
from proworksim.storage import digest, json_bytes
from scripts.software_holdout_sources_v051 import checked, read, release_gate, source_ref, write
from scripts.software_holdout_v051 import inventory

VERSION = 'v051-holdout-initial-input-qualification-v1'
OPAQUE_PATHS = (
    ('instance_id',), ('workspace_reference', 'object_id'),
    ('member_registry', 'member_001', 'initial_source_reference', 'object_id'),
    ('member_registry', 'member_002', 'initial_source_reference', 'object_id'),
    ('team_model_budget', 'state_sha256'),
)


def validate_source_summary(source, *, release_ref, common_ref):
    if (source.get('version') != 'v051-holdout-source-qualification-v1'
            or source.get('fixture_only') is not False or source.get('completed') is not True
            or source.get('source_access_release') != release_ref
            or source.get('common_implementation_freeze') != common_ref):
        raise ValueError('A complete formal source qualification bound to the same release/freeze is required')
    qualified, blocked = source.get('qualified_case_ids'), source.get('blocked_case_ids')
    if (not isinstance(qualified, list) or qualified != [case for case in HOLD_IDS if case in qualified]
            or blocked != [case for case in HOLD_IDS if case not in qualified]):
        raise ValueError('Source qualification must partition the unchanged eight-task inventory')
    return qualified


def gate(project_root, release_path, source_path, inventory_path):
    admitted = release_gate(project_root, release_path)
    common, snapshot = admitted['common'], Path(admitted['common']['source_root']).resolve()
    script = Path(__file__).resolve()
    if (not script.is_relative_to(snapshot)
            or digest(script.read_bytes()) != common['source_files'].get(str(script.relative_to(snapshot)))):
        raise ValueError('Run initial qualification from the sealed common implementation')
    release, source = read(release_path), read(source_path)
    inventory_ref = source_ref(inventory_path)
    if release.get('inventory') != inventory_ref:
        raise ValueError('Initial shapes must use the source-release-bound static inventory')
    qualified = validate_source_summary(source, release_ref=admitted['source_access_release'],
                                        common_ref=admitted['common_implementation_freeze'])
    metadata = read(checked(inventory_ref))
    rows = inventory(metadata)
    # All referenced source documents remain immutable; no test or task body is
    # opened until the explicit release and common-code gate above has passed.
    checked(source['adapter_manifest'])
    return {**admitted, 'source': source, 'source_qualification': source_ref(source_path),
            'inventory': inventory_ref, 'metadata': metadata, 'rows': rows, 'qualified': qualified}


class ExactTokenizer:
    """Cache identical byte strings and call arguments, never similar inputs."""
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
        self.encodings = self.renders = self.encoding_hits = self.render_hits = 0
        self._encodings, self._renders = {}, {}

    def __call__(self, text, **kwargs):
        key = json_bytes([text, kwargs])
        if key not in self._encodings:
            self._encodings[key] = self.tokenizer(text, **kwargs)
            self.encodings += 1
        else:
            self.encoding_hits += 1
        return copy.deepcopy(self._encodings[key])

    def apply_chat_template(self, messages, **kwargs):
        key = json_bytes([messages, kwargs])
        if key not in self._renders:
            self._renders[key] = self.tokenizer.apply_chat_template(messages, **kwargs)
            self.renders += 1
        else:
            self.render_hits += 1
        return copy.deepcopy(self._renders[key])


class MetadataOwner:
    """SDK configuration metadata only: no model, optimizer, tensors or RNG."""
    def __init__(self, authorization, slot_id, tokenizer):
        self.recipe = {'max_length': 18432, 'max_output_tokens': 2048, 'temperature': .7}
        self.contract = copy.deepcopy(NATIVE_CONTRACT)
        self.window_id = 'holdout-v051:' + slot_id
        self.tokenizer = tokenizer
        self.identity = copy.deepcopy(authorization['actor_identity'])
        self.identity.update(checkpoint=copy.deepcopy(authorization['checkpoint']),
            source_actor_identity=copy.deepcopy(authorization['actor_identity']),
            retained_state_authorization=copy.deepcopy(authorization))
        self.native = {}

    def freeze_identity(self):
        return copy.deepcopy(self.identity)

    def prepare_request(self, request):
        key = json_bytes(request)
        if key not in self.native:
            self.native[key] = prepare_native_input(self.tokenizer, request, self.contract)
        record = self.native[key]
        return record['rendered_prompt'], record['actual_prompt_messages'], copy.deepcopy(record)


class InitialCaptured(BaseException):
    """Deliberate qualification-only stop, outside SDK error/retry handling."""


class CaptureTransport(SoftwareContextTransport):
    def __init__(self, owner, directory):
        super().__init__(owner, directory, evidence_kind='cpu_programmed_fixture')
        self.captured = None

    def prepare_for_budget(self, request):
        if self.captured is not None or self._turn is None:
            raise ValueError('Capture exactly one member-bound initial SDK request')
        self.captured = {'request': copy.deepcopy(request), 'runner_turn': copy.deepcopy(self._turn)}
        raise InitialCaptured()

    def complete(self, request, **kwargs):
        raise AssertionError('Initial qualification cannot dispatch a generation')


def capture_initial(provider, row, member, authorization, tokenizer, destination):
    destination = Path(destination)
    prepared = build_software_collaboration_case(case_spec(row['task_id'], provider=provider,
        first_member=row['first_member']), destination / 'prepared', provider=provider)
    owner = MetadataOwner(authorization, row['slot_id'], tokenizer)
    owner.transport = CaptureTransport(owner, destination / 'transport')
    runtime, _, _ = build_runtime(owner, prepared, destination / 'sdk')
    before = prepared.world.store.load()
    try:
        runtime.cursor = runtime.labels.index(member)
        try:
            runtime.step()
        except InitialCaptured:
            pass
        else:
            raise ValueError('SDK did not reach the pre-dispatch initial request boundary')
        captured = owner.transport.captured
        if (captured is None or captured['runner_turn']['member_id'] != member
                or prepared.world.store.load() != before
                or runtime.team_budget.snapshot()['attempts'] != 0):
            raise ValueError('Initial capture changed business state or dispatched an attempt')
        write(destination / 'original-request.json', captured['request'])
        write(destination / 'capture.json', {'runner_turn': captured['runner_turn'],
            'actor_authorization_metadata_only': authorization, 'online_window_id': owner.window_id,
            'selected_role': member, 'frozen_first_member': row['first_member'],
            'stable_sessions_created': list(runtime.labels), 'generation_attempts': 0,
            'world_unchanged': True, 'no_parameter_or_rng_guard_claimed': True,
            'scope': 'Pristine role view before partner work; not a simulated partner turn'})
        return captured['request'], owner
    finally:
        close_runtime(runtime)


def business_projection(request):
    """Compare full public inputs with only these explicit opaque fields masked.

    This is an audit comparison, never input editing or tokenization reuse.
    Unknown differences remain different and block the fixed task.
    """
    value, opaque = copy.deepcopy(request), []
    observations = list(observation_messages(value))
    if not observations:
        raise ValueError('Actual SDK request lacks its initial observation envelope')
    for index, payload in observations:
        observation = payload['observation']
        for path in OPAQUE_PATHS:
            parent = observation
            for component in path[:-1]:
                parent = parent[component]
            original = parent[path[-1]]
            if not isinstance(original, str) or not original:
                raise ValueError('Expected a nonempty explicit opaque identity field')
            opaque.append({'message_index': index, 'path': '/observation/' + '/'.join(path), 'value': original})
            parent[path[-1]] = '<opaque:' + '/'.join(path) + '>'
        value['messages'][index]['content'] = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return value, opaque


def evaluate_request(request, owner, member, cache):
    # Member binding enters feedback projection; reuse requires both exact input
    # bytes and identical member. Empty initial feedback is fixed by construction.
    key = json_bytes([member, request])
    reused = key in cache
    if not reused:
        selected, projection = project_software_request(request, render=owner.prepare_request,
            tokenizer=owner.tokenizer, context_limit=18432, member_id=member)
        cache[key] = {'selected': selected, 'projection': projection,
                      'native': list(owner.native.values())}
    return copy.deepcopy(cache[key]), reused


def qualify(project_root, release_path, source_path, inventory_path, model_path, output):
    admitted = gate(project_root, release_path, source_path, inventory_path)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'version': VERSION, 'purpose': PURPOSE, 'fixture_only': False, 'completed': False,
        'source_access_release': admitted['source_access_release'],
        'common_implementation_freeze': admitted['common_implementation_freeze'],
        'source_qualification': admitted['source_qualification'], 'inventory': admitted['inventory'],
        'qualified_case_ids': [], 'blocked_case_ids': [], 'rows': [], 'tasks': [],
        'logical_role_shapes': 2 * len(admitted['qualified']), 'maximum_identity_shapes': 8 * len(admitted['qualified']),
        'actual_sdk_initial_requests': 0, 'unique_request_projections': 0,
        'actual_model_generations': 0, 'programmed_responses': 0, 'repository_test_executions': 0,
        'weights_loaded': False, 'GPU_workers': 0, 'new_parameter_updates': 0,
        'future_opaque_identifier_capacity_guaranteed': False,
        'formal_runtime_hard_capacity_gate_preserved': True,
        'qualification_scope': 'Actual initial identity instances; no universal future-ID bound or added margin'}
    write(output / 'declaration.json', report)
    tokenizer, provider, cache = None, None, {}
    if admitted['qualified']:
        from transformers import AutoTokenizer
        model = Path(model_path).resolve()
        # These are the static original actor/tokenizer metadata, not weights.
        binding = admitted['common']['tokenizer']
        if Path(binding['model_path']).resolve() != model:
            raise ValueError('Use the retained actors original common tokenizer directory')
        expected_files = {model / 'tokenizer.json', model / 'tokenizer_config.json'}
        if (model / 'chat_template.jinja').is_file():
            expected_files.add(model / 'chat_template.jinja')
        if {checked(ref) for ref in binding['files']} != expected_files:
            raise ValueError('Exact tokenizer/config/template files must match the common freeze')
        report['tokenizer_files'] = copy.deepcopy(binding['files'])
        tokenizer = ExactTokenizer(AutoTokenizer.from_pretrained(model, local_files_only=True))

        def no_test(**kwargs):
            raise AssertionError('Initial qualification cannot execute repository tests')

        source = admitted['source']
        provider = RepositorySources(source['source_root'], runner=no_test,
            expected_manifest_sha256=source['adapter_manifest']['sha256'])
        if list(provider.case_ids) != admitted['qualified']:
            raise ValueError('Provider qualification differs from the source summary')
    for case_id in HOLD_IDS:
        if case_id not in admitted['qualified']:
            report['blocked_case_ids'].append(case_id)
            report['tasks'].append({'task_id': case_id, 'status': 'not_run_source_blocked'})
            continue
        signatures, case_rows, issues = {}, [], []
        for row in [r for r in admitted['rows'] if r['task_id'] == case_id]:
            for member in MEMBERS:
                folder = output / row['slot_id'] / member
                request, owner = capture_initial(provider, row, member,
                    admitted['metadata']['states'][row['condition']], tokenizer, folder)
                report['actual_sdk_initial_requests'] += 1
                measured, reused = evaluate_request(request, owner, member, cache)
                business, opaque = business_projection(request)
                signature = digest(json_bytes(business))
                signatures.setdefault(member, []).append(signature)
                write(folder / 'projection.json', measured)
                write(folder / 'opaque-identities.json', opaque)
                p = measured['projection']
                record = {'task_id': case_id, 'condition': row['condition'], 'member_id': member,
                    'original_request': source_ref(folder / 'original-request.json'),
                    'projection': source_ref(folder / 'projection.json'),
                    'opaque_identities': source_ref(folder / 'opaque-identities.json'),
                    'public_business_contract_sha256': signature, 'exact_request_projection_reused': reused,
                    **{key: p[key] for key in ('original_prompt_tokens', 'selected_prompt_tokens',
                        'protected_prompt_tokens', 'reserved_output_tokens', 'context_limit', 'fits')}}
                case_rows.append(record)
                report['rows'].append(record)
                if not p['fits']:
                    issues.append({'condition': row['condition'], 'member_id': member, 'reason': 'initial_hard_capacity'})
        same = all(len(set(signatures[member])) == 1 for member in MEMBERS)
        if not same:
            issues.append({'reason': 'public_business_or_tool_contract_differs_across_actor_states'})
        qualified = not issues
        report['qualified_case_ids' if qualified else 'blocked_case_ids'].append(case_id)
        report['tasks'].append({'task_id': case_id, 'status': 'qualified' if qualified else 'input_blocked',
            'identity_shapes': len(case_rows), 'business_contract_equal_across_states': same, 'issues': issues})
        write(output / (case_id + '-progress.json'), report)
    report.update(completed=True, passed=not report['blocked_case_ids'], unique_request_projections=len(cache),
        tokenizer_encoding_calls=tokenizer.encodings if tokenizer else 0,
        tokenizer_encoding_exact_cache_hits=tokenizer.encoding_hits if tokenizer else 0,
        native_template_renders=tokenizer.renders if tokenizer else 0,
        native_template_exact_cache_hits=tokenizer.render_hits if tokenizer else 0)
    write(output / 'summary.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('project-root', 'release', 'source-qualification', 'inventory', 'model', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    qualify(args.project_root, args.release, args.source_qualification, args.inventory, args.model, args.output)


if __name__ == '__main__':
    main()
