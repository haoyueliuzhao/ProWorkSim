"""New real CPU worlds plus explicitly synthetic tokens; never model support."""
import copy
import json
from pathlib import Path

import pytest

from proworksim.collaboration_training_v025 import (
    diagnose_support, export_training_episode, member_token_admission,
    records_from_entries, training_admission, validate_window_declaration,
)
from proworksim.episode import begin_episode, finish_episode
from proworksim.online_collection import run_fragment
from proworksim.online_support import declare_window
from proworksim.online_training import prepare_window, recipe_config
from proworksim.storage import digest, json_bytes
from proworksim.support_weights import build_support, materialize_weights
from proworksim.templates import retail_collaboration_v025 as world
from proworksim.work_methods_v025 import assess_complete_work, map_complete_method
from scripts.retail_work_controls_v025 import RouteProgramOwner


class ExplicitTokenFixture(RouteProgramOwner):
    recipe = recipe_config({'credit_assignment': 'terminal_mc', 'max_length': 16384, 'max_output_tokens': 2048, 'temperature': .7})
    window_id = 'v025-next-base'

    def freeze_identity(self):
        return {'version': 'shared-actor-identity-v0.13', 'policy_version': 'explicit-v025-token-fixture',
                'adapter_sha256': digest(b'fixture-adapter'), 'base_manifest_sha256': digest(b'fixture-base'),
                'inference_profile_sha256': digest(b'fixture-profile')}

    def complete(self, request, *, timeout_seconds):
        response = super().complete(request, timeout_seconds=timeout_seconds)
        body = response['body']
        if response['http_status'] != 200:
            return response
        tokens = [71, 72]
        body.update(model=request['model'], actor_identity=self.freeze_identity(),
                    system_fingerprint=self.freeze_identity()['policy_version'], online_window_id=self.window_id,
                    fixture_provenance='Explicit synthetic CPU IDs/logps, not model generation',
                    token_trace={'input_ids': [1, 2], 'output_ids': tokens, 'raw_output_ids': tokens,
                                 'input_mask': [0, 0], 'output_mask': [1, 1],
                                 'behavior_logprobs': [-.4, -.5], 'raw_behavior_logprobs': [-.4, -.5],
                                 'sampling_temperature': .7, 'sampling_top_p': 1, 'sampling_top_k': 0,
                                 'source': 'actual generation token IDs and sampling logits, not retokenized text'})
        body['usage'] = {'prompt_tokens': 2, 'completion_tokens': 2, 'total_tokens': 4}
        response['raw_body'] = json_bytes(body).decode()
        return response


def test_actual_continuation_projection_keeps_failed_own_tokens_and_M1_without_optimizer_targets(tmp_path):
    if not world.PIN_PATH.exists() or not (world.DEFAULT_ASSETS/'manifest.json').exists():
        pytest.skip('Pinned new v025 material required')
    catalog = world.registry()
    admission = training_admission(catalog, world.PIN_PATH, purpose='continuation_training')
    owners, pending, specs = [], [], []
    for slot in catalog['continuation_slots']:
        folder = tmp_path/slot['slot_id']
        prepared = world.build_case(slot['case_id'], folder)
        owner = ExplicitTokenFixture(prepared.case['task'], control='no_actions')
        runtime, capture, _ = world.runtime(owner, prepared, folder, episode_key=f"{slot['case_id']}:{slot['seed']}")
        owners.append(owner)
        specs.append({'slot_id': slot['slot_id'], 'xi_id': slot['case_id'],
                      'xi_fingerprint': digest(json_bytes({'case': prepared.case, 'initial': prepared.prefix['prepared_business_state_sha256']})),
                      'active_members': list(prepared.active_roles), 'policies': runtime.policy_identities,
                      'mapping_spec_id': admission['mapping_spec_id']})
        pending.append((slot, folder, prepared, runtime, capture))
    declaration = declare_window('v025-next-base', actor_identity=owners[0].freeze_identity(),
        gamma_identity={'harness': admission['harness'], 'purpose': admission['purpose'],
                        'seeds': [s['seed'] for s in catalog['continuation_slots']], 'explicit_cpu_fixture': True}, slot_specs=specs)
    validate_window_declaration(declaration, admission)
    entries, retained_decisions = [], []
    for slot, folder, prepared, runtime, capture in pending:
        episode = folder/'episode'
        begin_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), work_nodes=['TEAM::build'],
                      work_ids=[], scenario=copy.deepcopy(prepared.scenario), policies=runtime.policy_identities)
        terminal = run_fragment(prepared, runtime)
        finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination=terminal)
        entry, proof = export_training_episode(prepared, episode, declaration=declaration, slot_id=slot['slot_id'], captured=capture, admission=admission)
        assert proof['record_validity'] and proof['business_reward_known']
        assert proof['has_complete_trainable_actual_members']
        assert entry['reward']['reward'] == 0 and not entry['rollout']['work_validity']['value']
        assert entry['mapping']['status'] == 'unmapped'
        for view in proof['member_views'].values():
            assert view['complete_actor_trajectory']
            retained_decisions.extend(view['decisions'])
            for decision in view['decisions']:
                assert decision['loss_mask'] == [0, 0, 1, 1]
        entries.append(entry)
    assert len(retained_decisions) == 4
    assert sum(len(decision['tokens']['output_ids']) for decision in retained_decisions) == 8
    diag = diagnose_support(entries, declaration)
    assert diag['raw_slot_count'] == 2 and diag['raw_slots_per_situation'] == 1
    assert diag['selected_block'] is None and diag['optimizer_update_allowed'] is False
    assert all(block['M'] == 1 and not block['b'] and not any(block['base_actor_mask'].values())
               for support in diag['supports_by_xi'].values() for block in support['blocks'].values())
    prepared = prepare_window(entries, owners[0].freeze_identity(), 'v025-next-base', owners[0].recipe)
    # The declared continuation purpose retains evidence but forbids optimization.
    assert prepared['slot_count'] == 2 and prepared['decisions'] == []
    assert all('declared_scope_forbids_optimizer_update' in row['exclusions'] for row in prepared['slots'])
    records = records_from_entries(entries)
    assert all(r['rollout'] is e['rollout'] for r, e in zip(records, entries))
    with pytest.raises(ValueError, match='purpose|inventory'):
        validate_window_declaration(declaration, training_admission(catalog, world.PIN_PATH))


def test_known_no_actions_does_not_convert_missing_tokens_to_zero_targets():
    empty = {'decisions': [], 'diagnostics': [], 'no_own_actions': True,
             'own_action_tokens': 0, 'complete_actor_trajectory': False}
    result = member_token_admission({'member': empty})
    assert result['has_complete_trainable_actual_members']
    assert result['token_projection_members']['member']['status'] == 'known_no_own_actions'
    missing = copy.deepcopy(empty)
    missing['diagnostics'] = [{'reason': 'actual_token_trace_missing'}]
    assert not member_token_admission({'member': missing})['has_complete_trainable_actual_members']


def test_support_residuals_and_low_frequency_do_not_renormalize_or_pool():
    window = {'window_id': 'explicit-fixture', 'xi_id': 'one-exact-xi', 'xi_fingerprint': 'xi',
              'gamma_fingerprint': 'gamma', 'team_policy_fingerprint': 'policy'}
    slots = []
    for index in range(8):
        rid, sid = f'fixture-episode-{index}', f's{index}'
        validity = index != 5
        mapped = index != 6
        category = 'a_active_handoff' if index < 3 else 'a_requested_handoff'
        rollout = {'rollout_id': rid, 'window': window, 'members': {'implementer': {'origin': 'target_model'}},
                   'reward_eligibility': {'eligible': True},
                   'work_validity': {'spec_id': 'explicit-finite-test', 'value': validity,
                                     'components': {'record': {'value': True}}}}
        view = {'window': window, 'rollout_id': rid, 'member_id': 'implementer', 'own_action_count': 1,
                'complete_actor_trajectory': index != 7, 'complete_semantic_trajectory': True}
        slots.append({'slot_id': sid, 'window': window, 'rollout': rollout,
                      'member_views': {'implementer': view},
                      'mapping': {'rollout_id': rid, 'spec_id': 'explicit-mapper', 'class_id': category if mapped else None,
                                  'status': 'mapped' if mapped else 'unmapped'}})
    support = build_support(slots, window=window, member_ids=['implementer'], min_class_count=2)
    block = support['blocks']['implementer']
    assert block['M'] == 8 and block['n_positive'] == 5 and block['v'] == 5/8
    weights = materialize_weights(support, {'implementer': {'a_active_handoff': .3, 'a_requested_handoff': .7}})['members']['implementer']
    assert weights['eligible_branch_weight'] == 5 and weights['total_slot_weight'] == 8
    assert [weights['weights'][f's{i}'] for i in (5, 6, 7)] == [1, 1, 1]
    assert weights['actor_mask']['s5'] and weights['actor_mask']['s6'] and not weights['actor_mask']['s7']
    slots[4]['mapping']['status'] = 'unmapped'
    sparse = build_support(slots, window=window, member_ids=['implementer'], min_class_count=2)
    assert sparse['blocks']['implementer']['n_by_class'] == {'a_active_handoff': 3}
    other = copy.deepcopy(slots)
    other[0]['window']['xi_id'] = 'different-situation'
    with pytest.raises(ValueError, match='merge'):
        build_support(other, window=window, member_ids=['implementer'], min_class_count=2)


def test_read_only_actual_program_routes_and_reward_flag_cannot_replace_evidence():
    roots = [Path('runs/retail-work-v025-initial/case-00-active_handoff'),
             Path('runs/retail-work-v025-initial/case-00-request_bound_handoff'),
             Path('runs/retail-work-v025-compact-preparation/case-01-self_inspection_repair')]
    if not all((root/'episode/manifest.json').exists() for root in roots):
        pytest.skip('Preexisting explicit CPU route witnesses required')
    for root, category in zip(roots, ['a_active_handoff', 'a_requested_handoff', 'b_self_repair']):
        manifest = json.loads((root/'episode/manifest.json').read_text())
        members = {r['role_id']: {'actor_id': r['actor'], 'origin': 'rule'} for r in manifest['scenario']['roles']}
        result = assess_complete_work(root/'episode', members=members, independent_capture=json.loads((root/'capture.json').read_text()))
        assert all(c['value'] is True for c in result['validity']['components'].values())
        rollout = {'rollout_id': manifest['episode_id'], 'manifest_sha256': result['semantic_evidence']['manifest_sha256'],
                   'work_validity': result['validity'], 'reward_eligibility': {'reward': 1, 'completed': True}}
        assert map_complete_method(rollout, result['semantic_evidence'])['class_id'] == category
        # A high scalar return cannot repair a missing independently certified basis.
        wrong = copy.deepcopy(rollout)
        wrong['work_validity']['value'] = False
        wrong['work_validity']['components']['basis']['value'] = False
        assert map_complete_method(wrong, result['semantic_evidence'])['status'] == 'unmapped'
