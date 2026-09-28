"""Exact branching of six real CPU worlds with explicit synthetic token records."""
import copy
from types import SimpleNamespace

import pytest

from proworksim.collaboration_training_v024 import (
    export_training_episode, training_admission, validate_window_declaration,
)
from proworksim.credit_consumption_v024 import prepare_common_consumption, save_common_origin
from proworksim.episode import begin_episode, finish_episode
from proworksim.online_collection import run_fragment
from proworksim.online_support import bind_rollout, declare_window
from proworksim.online_training import SharedActor, prepare_window, tensor_tree_digest
from proworksim.storage import digest, json_bytes
from proworksim.templates import retail_collaboration_v024 as world
from test_collaboration_training_v022 import ExplicitSyntheticTokenTransport


def test_exact_fresh_common_origin_two_credit_consumptions_keep_raw_identity_and_masks(tmp_path):
    torch = pytest.importorskip('torch')
    if not (world.DEFAULT_ASSETS / 'manifest.json').exists():
        pytest.skip('Pinned new v024 source materials required')

    class TinyActor(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.lora_logits = torch.nn.Parameter(torch.tensor([.2, .3]))
            self.config = SimpleNamespace(attention_dropout=0, use_cache=False)
            self.generation_config = SimpleNamespace(eos_token_id=99)
        def gradient_checkpointing_enable(self, **kwargs):
            pass

    class Owner(SharedActor):
        complete = ExplicitSyntheticTokenTransport.complete
        @property
        def transport(self):
            return self

    def make_owner(label):
        owner = Owner(TinyActor(), object(), output=tmp_path / label, device='cpu', torch_module=torch,
            recipe={'max_length': 16384, 'max_output_tokens': 2048},
            base_identity={'manifest': {'sha256': digest(b'explicit CPU fixture')}},
            inference_profile={'explicit_cpu_fixture': True})
        owner.requests, owner.responses, owner.counters, owner.task = [], [], {}, None
        return owner

    torch.manual_seed(17)
    source = make_owner('collector')
    catalog = world.registry()
    contract = catalog['sampling_windows'][0]
    admission = training_admission(catalog, world.PIN_PATH)
    identity = source.begin_window(contract['window_id'])
    pending, specs = [], []
    for slot in contract['slots']:
        folder = tmp_path / 'worlds' / slot['slot_id']
        prepared = world.build_case(slot['case_id'], folder)
        runtime, captured, _ = world.runtime(source, prepared, folder, episode_key=slot['sampling_seed'])
        specs.append({'slot_id': slot['slot_id'], 'xi_id': slot['case_id'],
            'xi_fingerprint': digest(json_bytes({'case': prepared.case,
                'initial': prepared.prefix['prepared_business_state_sha256']})),
            'active_members': list(prepared.active_roles), 'policies': runtime.policy_identities,
            'mapping_spec_id': 'explicit_CPU_projection_not_model_training'})
        pending.append((slot, prepared, folder, runtime, captured))
    declaration = declare_window(contract['window_id'], actor_identity=identity,
        gamma_identity={'harness': admission['harness'], 'credit_arm': 'common',
            'explicit_CPU_fixture': True, 'seeds': [s['sampling_seed'] for s in contract['slots']]},
        slot_specs=specs)
    entries = []
    for slot, prepared, folder, runtime, captured in pending:
        source.reseed(slot['sampling_seed'], label=slot['slot_id'])
        source.task, source.counters = slot['task'], {}
        episode = folder / 'episode'
        begin_episode(prepared.world, episode, experience=runtime.recorder.snapshot(),
                      work_ids=[world.WORK], scenario=prepared.scenario, policies=runtime.policy_identities)
        terminal = run_fragment(prepared, runtime)
        finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination=terminal)
        entry, proof = export_training_episode(prepared, episode, declaration=declaration,
                                              slot_id=slot['slot_id'], captured=captured, admission=admission)
        assert proof['has_complete_trainable_actual_members'] and proof['record_validity']
        entries.append(entry)
    raw_before = json_bytes(entries)
    origin = tmp_path / 'origin'
    record = save_common_origin(source, origin, entries, declaration, admission)
    assert source.phase == 'idle' and record['comparison']['target_changes']
    reports, prepared_arms = {}, {}
    for arm in ('mc', 'handoff_rtg'):
        branch = make_owner(arm)
        with torch.no_grad():
            for parameter in branch.critic.parameters():
                parameter.fill_(42)
        branch.actor_optimizer.param_groups[0]['lr'] = .99
        torch.manual_seed(999)
        report = prepare_common_consumption(branch, origin, entries, declaration, admission, arm)
        reports[arm] = report
        assert report['exact_common_state_restored']
        assert report['common_state_tensor_digest'] == record['checkpoint']['state_tensor_digest']
        assert branch.phase == 'collecting' and branch.window_id == contract['window_id']
        assert branch.actor_steps == branch.critic_steps == 0
        restored = branch._state_bundle()
        restored['recipe'] = source.recipe
        assert tensor_tree_digest(restored, torch) == record['checkpoint']['state_tensor_digest']
        projected = prepare_window(entries, branch.freeze_identity(), branch.window_id, branch.recipe)
        prepared_arms[arm] = projected
        assert projected['slot_count'] == 6
        for entry in entries:
            views = bind_rollout(declaration, entry['slot_id'], entry['rollout'])['member_views']
            for member in entry['active_members']:
                view = views[member]
                for decision in view['decisions']:
                    assert decision['loss_mask'] == [0] * 4 + [1, 1]
                    assert decision['labels'] == [-100] * 4 + decision['tokens']['output_ids']
                rows = [r for r in projected['decisions'] if r['slot_id'] == entry['slot_id'] and r['member_id'] == member]
                assert all(r['actor_denominator'] == 6 * len(entry['active_members']) * view['own_action_tokens'] for r in rows)
                assert all(r['critic_denominator'] == 6 * len(entry['active_members']) * len(view['decisions']) for r in rows)
        with pytest.raises(ValueError, match='fresh idle MC'):
            prepare_common_consumption(branch, origin, entries, declaration, admission, arm)
    assert reports['mc']['consumption_id'] != reports['handoff_rtg']['consumption_id']
    assert reports['mc']['common_state_tensor_digest'] == reports['handoff_rtg']['common_state_tensor_digest']
    assert raw_before == json_bytes(entries)
    assert {r['call_id'] for r in prepared_arms['mc']['decisions']} == {r['call_id'] for r in prepared_arms['handoff_rtg']['decisions']}
    # Missing evidence remains one of six slots; no favorable-row filtering.
    incomplete = copy.deepcopy(entries)
    incomplete[-1]['rollout'] = incomplete[-1]['reward'] = None
    prepared = prepare_window(incomplete, identity, contract['window_id'], source.recipe)
    assert prepared['slot_count'] == 6
    assert prepared['slots'][-1]['exclusions'] == ['episode_or_reward_record_missing']
    denominators = {r['call_id']: r['actor_denominator'] for r in prepared_arms['mc']['decisions']}
    assert all(r['actor_denominator'] == denominators[r['call_id']] for r in prepared['decisions'])
    altered = copy.deepcopy(declaration)
    altered['slots'][0]['xi_id'] = catalog['evaluation_cases'][0]['case_id']
    with pytest.raises(ValueError, match='order/cases'):
        validate_window_declaration(altered, admission)
    with pytest.raises(ValueError, match='unchanged actual D0'):
        prepare_common_consumption(make_owner('bad-origin'), origin, incomplete, declaration, admission, 'mc')
