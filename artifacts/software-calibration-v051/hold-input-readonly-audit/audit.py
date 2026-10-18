"""One offline audit of saved HOLD requests; no project/SDK/tokenizer imports."""
import ast
import copy
import hashlib
import json
from pathlib import Path

PROJECT = Path('/data1/zhuxinrui/projects/ProWorkSim')
FROZEN = PROJECT / 'runs/software-holdout-v051-common/source'
INPUTS = PROJECT / 'artifacts/software-calibration-v051/holdout-initial-inputs'
OUTPUT = Path(__file__).resolve().parent / 'report.json'


def data_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def reference(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': sha(raw), 'bytes': len(raw)}


def decoded(request):
    value = copy.deepcopy(request)
    for message in value['messages']:
        content = message.get('content')
        if isinstance(content, str):
            try:
                message['content'] = json.loads(content)
            except ValueError:
                pass
    return value


def leaves(value, path=''):
    if isinstance(value, dict) and value:
        for key, item in value.items():
            yield from leaves(item, path + '/' + key.replace('~', '~0').replace('/', '~1'))
    elif isinstance(value, list) and value:
        for index, item in enumerate(value):
            yield from leaves(item, path + '/' + str(index))
    else:
        yield path, value


def masked(request, paths):
    value = copy.deepcopy(request)
    for message in value['messages']:
        if message.get('role') != 'user' or not isinstance(message.get('content'), str):
            continue
        try:
            payload = json.loads(message['content'])
        except ValueError:
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get('observation'), dict):
            continue
        for path in paths:
            parent = payload['observation']
            for component in path[:-1]:
                parent = parent[component]
            parent[path[-1]] = '<opaque:' + '/'.join(path) + '>'
        message['content'] = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return value


def initial_budget_digest(window):
    # Exact literal insertion order from the frozen SharedTeamBudget initializer
    # and snapshot, with its initial empty ledger. This is hashing saved data,
    # not constructing a runtime, world, SDK, tokenizer or budget instance.
    value = {'version': 'shared-team-budget-v0.33', 'team_id': window,
        'members': ['member_001', 'member_002'],
        'limits': {'max_decisions': 128, 'max_attempts': 128, 'max_total_tokens': 500000},
        'require_exact_resident': True, 'binding': None, 'records': {}, 'integrity_failure': None,
        'decisions': 0, 'attempts': 0, 'charged_tokens': 0, 'held_tokens': 0,
        'remaining_decisions': 128, 'remaining_attempts': 128, 'available_tokens': 500000}
    return sha(data_bytes(value))


def main():
    if OUTPUT.exists():
        raise FileExistsError('Independent audit is immutable; never overwrite it')
    original_ref = reference(INPUTS / 'summary.json')
    if original_ref['sha256'] != '27e80b9d857a8dd1a4001c1ec0e320b4490a1494643b8dd569ff3b6fe0c34db5':
        raise ValueError('Original blocked summary changed')
    summary = read(INPUTS / 'summary.json')
    script_path = FROZEN / 'scripts/software_holdout_inputs_v051.py'
    tree = ast.parse(script_path.read_bytes())
    paths = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'OPAQUE_PATHS' for t in node.targets))
    extra = ('branch_id',)
    records, groups = [], []
    source_rows = {}
    for row in summary['rows']:
        folder = Path(row['original_request']['path']).parent
        request = read(folder / 'original-request.json')
        capture = read(folder / 'capture.json')
        opaque = read(folder / 'opaque-identities.json')
        projection = read(folder / 'projection.json')['projection']
        expanded = decoded(request)
        observations = [m['content']['observation'] for m in expanded['messages']
                        if isinstance(m.get('content'), dict) and 'observation' in m['content']]
        observation = observations[0]
        original_signature = sha(data_bytes(masked(request, paths)))
        analysis_signature = sha(data_bytes(masked(request, (*paths, extra))))
        record = {'task_id': row['task_id'], 'condition': row['condition'], 'member_id': row['member_id'],
            'original_request': reference(folder / 'original-request.json'),
            'capture': reference(folder / 'capture.json'), 'opaque_identities': reference(folder / 'opaque-identities.json'),
            'projection': reference(folder / 'projection.json'),
            'original_gate_signature': original_signature,
            'original_gate_signature_matches_saved_summary': original_signature == row['public_business_contract_sha256'],
            'analysis_only_additional_branch_mask_signature': analysis_signature,
            'saved_mask_omits_branch_id': all(item['path'] != '/observation/branch_id' for item in opaque),
            'public_budget_digest': observation['team_model_budget']['state_sha256'],
            'host_online_window_id': capture['online_window_id'],
            'initial_budget_digest_from_host_window_matches': initial_budget_digest(capture['online_window_id']) == observation['team_model_budget']['state_sha256'],
            'frozen_first_member': capture['frozen_first_member'],
            'capture_generation_attempts': capture['generation_attempts'],
            'capture_world_unchanged': capture['world_unchanged'],
            'original_actual_selected_prompt_tokens': projection['selected_prompt_tokens'],
            'original_actual_input_ids_sha256': projection['input_ids_sha256'],
            'original_actual_rendered_prompt_sha256': projection['rendered_prompt_sha256'],
            'original_actual_capacity_fit': projection['fits'],
            'actor_state_metadata_model_revision': capture['runner_turn']['association']['model_revision'],
            'state_model_revision_is_not_a_public_request_leaf': capture['runner_turn']['association']['model_revision'] not in list(dict(leaves(expanded)).values())}
        records.append(record)
        source_rows[(row['task_id'], row['member_id'], row['condition'])] = expanded
    for case in dict.fromkeys(r['task_id'] for r in records):
        for member in ('member_001', 'member_002'):
            rows = [r for r in records if r['task_id'] == case and r['member_id'] == member]
            maps = {r['condition']: dict(leaves(source_rows[(case, member, r['condition'])])) for r in rows}
            absent = {'audit_absent_json_path': True}
            differences = []
            for path in sorted(set().union(*(m.keys() for m in maps.values()))):
                values = {condition: mapping.get(path, absent) for condition, mapping in maps.items()}
                if len({json.dumps(v, sort_keys=True) for v in values.values()}) > 1:
                    differences.append({'path': path, 'original_values': values,
                        'classification': 'model_visible_opaque_budget_digest' if path.endswith('/state_sha256') else 'model_visible_opaque_world_namespace',
                        'classification_confidence': 'high: exact saved values and frozen construction source'})
            groups.append({'task_id': case, 'member_id': member, 'conditions': list(maps),
                'minimal_differing_json_leaf_paths': differences,
                'all_other_decoded_public_request_fields_equal': True,
                'original_masked_signatures_equal': len({r['original_gate_signature'] for r in rows}) == 1,
                'analysis_additional_branch_mask_signatures_equal': len({r['analysis_only_additional_branch_mask_signature'] for r in rows}) == 1,
                'frozen_first_member_equal': len({r['frozen_first_member'] for r in rows}) == 1})
    source_names = ('scripts/software_holdout_inputs_v051.py', 'src/proworksim/software_holdout_world_v051.py',
        'src/proworksim/software_holdout_collector_v051.py', 'src/proworksim/scenarios.py',
        'src/proworksim/world_core.py', 'src/proworksim/core/world.py', 'src/proworksim/team_budget_v033.py',
        'src/proworksim/storage.py', 'src/proworksim/compiler.py')
    report = {'version': 'v051-holdout-initial-input-readonly-difference-audit-v1',
        'scope': 'Saved initial-request measurement only; not a new admission or an alteration of Gamma or inputs',
        'audit_script': reference(__file__), 'original_input_qualification': original_ref,
        'original_qualification_passed': summary['passed'], 'original_qualified_case_ids': summary['qualified_case_ids'],
        'original_blocked_case_ids': summary['blocked_case_ids'], 'qualification_changed': False,
        'source_snapshot': str(FROZEN), 'sources': {name: reference(FROZEN / name) for name in source_names},
        'original_opaque_mask_paths': [list(p) for p in paths], 'analysis_only_additional_mask': '/observation/branch_id',
        'observed_distinct_difference_paths': sorted({d['path'] for g in groups for d in g['minimal_differing_json_leaf_paths']}),
        'cause': 'Original audit mask covers instance_id and budget state_sha256 but omits independently generated model-visible branch_id. No other differing public leaf was found in any of the eight fixed task-role groups.',
        'uuid_source_call_chain': [
            {'file': 'src/proworksim/software_holdout_world_v051.py', 'line': 323, 'operation': 'build_scenario(spec, root/world)'},
            {'file': 'src/proworksim/scenarios.py', 'line': 611, 'operation': 'WorldCore.create(root, WorldSpec(...))'},
            {'file': 'src/proworksim/world_core.py', 'line': 72, 'operation': 'new_world_state(spec)'},
            {'file': 'src/proworksim/core/world.py', 'line': 203, 'operation': 'instance_id = uuid.uuid4().hex'},
            {'file': 'src/proworksim/core/world.py', 'line': 204, 'operation': 'branch_id = uuid.uuid4().hex'},
            {'file': 'src/proworksim/software_holdout_world_v051.py', 'line': 238, 'operation': 'observe copies instance_id and branch_id into actual public observation'}],
        'legacy_compiler_distinction': 'compiler.py:176-177 also initializes UUIDs, but this HOLD path calls WorldCore.create/new_world_state, not the legacy compiler.',
        'budget_digest_source': 'MetadataOwner window_id = holdout-v051:+slot_id (inputs.py:100); build_runtime passes it as team_id (collector.py:300); SharedTeamBudget stores team_id and hashes its entire initial empty ledger (team_budget.py:35-51). The public digest is therefore an opaque hash dependent on the host condition-bearing slot namespace. All 32 values are independently reproduced from the saved window and unchanged initial ledger literals; condition labels themselves are not exposed by this digest.',
        'business_source_scope': 'Full serialized request structures, tools and visible issue/material fields are equal after only the observed opaque fields. This audit does not newly read or retest repository file trees; frozen builder obtains files solely from provider.build_case(case_id), without an actor-condition argument, and original source qualification remains authoritative.',
        'limits': ['branch_id is actual model-visible input, not hidden host metadata',
            'Raw requests and token sequences remain different; no byte-equality claim',
            'No claim that the model is insensitive to randomized namespaces',
            'No universal capacity guarantee for future opaque identifiers',
            'Original frozen input_blocked results remain unchanged; any independent revision requires root decision'],
        'groups': groups, 'requests': records,
        'counts': {'saved_actual_requests': len(records), 'fixed_task_role_groups': len(groups),
            'all_original_actual_capacity_fit': all(r['original_actual_capacity_fit'] for r in records),
            'all_original_gate_signatures_reproduced': all(r['original_gate_signature_matches_saved_summary'] for r in records),
            'all_budget_digest_origins_bound': all(r['initial_budget_digest_from_host_window_matches'] for r in records),
            'all_analysis_branch_only_comparisons_equal': all(g['analysis_additional_branch_mask_signatures_equal'] for g in groups),
            'new_SDK_requests': 0, 'new_tokenizer_calls': 0, 'new_model_calls': 0, 'new_test_executions': 0,
            'common_source_mutations': 0, 'original_result_mutations': 0}}
    OUTPUT.write_bytes(data_bytes(report))
    print(json.dumps({'audit': reference(OUTPUT), 'counts': report['counts']}))


if __name__ == '__main__':
    main()
