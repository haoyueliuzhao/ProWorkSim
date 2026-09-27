"""Real closed WorldCore episodes with explicitly synthetic CPU token fixtures.

These controls test only projection/identity/masks. They never load a model,
estimate model support, compute probabilities or update parameters.
"""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim.collaboration_training_v022 import (
    VERSION, export_training_episode, member_token_admission, training_admission,
)
from proworksim.episode import begin_episode, finish_episode
from proworksim.online_collection import run_fragment
from proworksim.online_support import bind_rollout, declare_window
from proworksim.online_training import prepare_window, recipe_config
from proworksim.storage import digest, json_bytes, read_json
from proworksim.templates import retail_collaboration_v022 as world
from proworksim.work_view_v022 import runtime


class ExplicitSyntheticTokenTransport:
    recipe = recipe_config({'credit_assignment': 'terminal_mc'})
    window_id = 'explicit-cpu-projection-window'

    def __init__(self):
        self.transport = self
        self.counters = {}
        self.responses = []
        self.requests = []
        self.task = None

    def freeze_identity(self):
        return {'version': 'shared-actor-identity-v0.13', 'policy_version': 'cpu-synthetic-v022',
                'adapter_sha256': digest(b'cpu-fixture-adapter'),
                'base_manifest_sha256': digest(b'cpu-fixture-base'),
                'inference_profile_sha256': digest(b'cpu-fixture-profile')}

    def complete(self, request, *, timeout_seconds):
        names = {tool['function']['name'] for tool in request['tools']}
        member = 'implementer' if 'write_object' in names else 'reviewer' if 'raise_issue' in names else 'provider'
        index = self.counters.get(member, 0)
        self.counters[member] = index + 1
        observation = json.loads(request['messages'][-1]['content'])['observation']
        if index == 0:
            message = {'role': 'assistant', 'content': 'EXPLICIT CPU MALFORMED OUTPUT FIXTURE'}
            finish = 'length'
        else:
            if index == 1:
                name, args = 'read_alias', {'alias': 'basis' if member == 'provider' else 'data'}
            elif member == 'provider' and index == 2:
                basis = observation['workspaces']['TEAM']['basis']
                name, args = 'handoff_information', {
                    'route_id': 'basis', 'work_id': world.WORK, 'handoff_key': 'cpu-fixture',
                    'reference': {'object_id': basis, 'version_id': 'v1'},
                    'body': 'EXPLICIT CPU COLLEAGUE INPUT FIXTURE; use only the exact delivered policy.'}
            elif member == 'implementer' and self.task == 'joint_a' and index == 2:
                name, args = 'staff_wait', {'reason': 'CPU fixture waits for actual delivery'}
            elif member == 'implementer' and self.task == 'joint_a' and index == 3:
                name, args = 'read_messages', {}
            else:
                name, args = 'staff_done', {'reason': 'CPU fixture ends without pretending a completed product'}
            message = {'role': 'assistant', 'content': 'EXPLICIT CPU TRANSPORT FIXTURE',
                       'tool_calls': [{'id': f'fixture-{len(self.responses)}', 'type': 'function',
                                       'function': {'name': name, 'arguments': json.dumps(args)}}]}
            finish = 'tool_calls'
        # Synthetic IDs/logps are explicit fixture data; never real model output.
        offset = {'provider': 1000, 'implementer': 2000, 'reviewer': 3000}[member] + index * 2
        tokens = [offset, offset + 1]
        body = {'id': f'explicit-fixture-completion-{len(self.responses)}', 'model': request['model'],
                'system_fingerprint': self.freeze_identity()['policy_version'],
                'actor_identity': self.freeze_identity(), 'online_window_id': self.window_id,
                'choices': [{'index': 0, 'message': message, 'finish_reason': finish}],
                'usage': {'prompt_tokens': 4, 'completion_tokens': 2, 'total_tokens': 6},
                'fixture_provenance': 'Explicit synthetic CPU tokens/logps, not real model generation',
                'token_trace': {
                    'input_ids': [11, 12, 13, 14], 'output_ids': tokens,
                    'raw_output_ids': tokens, 'input_mask': [0, 0, 0, 0], 'output_mask': [1, 1],
                    'behavior_logprobs': [-.7, -.9], 'raw_behavior_logprobs': [-.7, -.9],
                    'sampling_temperature': .7, 'sampling_top_p': 1, 'sampling_top_k': 0,
                    'source': 'actual generation token IDs and sampling logits, not retokenized text'}}
        self.requests.append(copy.deepcopy(request))
        self.responses.append({'member': member, 'body': copy.deepcopy(body)})
        return {'http_status': 200, 'body': body, 'raw_body': json_bytes(body).decode(), 'response_headers': {}}


@pytest.fixture(scope='module')
def projected_window(tmp_path_factory):
    if not world.PIN_PATH.exists() or not (world.DEFAULT_ASSETS / 'manifest.json').exists():
        pytest.skip('Pinned local v022 raw materials required; no synthetic source fallback')
    root = tmp_path_factory.mktemp('collaboration-projection')
    catalog = world.registry()
    owner = ExplicitSyntheticTokenTransport()
    admission = training_admission(catalog, world.PIN_PATH)
    prepared_rows, specs = [], []
    # Declare every scheduled slot before the first fake transport completion.
    for i, case in enumerate(catalog['reserved_training']):
        folder = root / f'slot-{i}'
        prepared = world.build_case(case, folder)
        runner, captured, _ = runtime(owner, prepared, folder, 'compact_work')
        slot_id = f'fixture-slot-{i}'
        specs.append({'slot_id': slot_id, 'xi_id': case['case_id'],
                      'xi_fingerprint': digest(json_bytes({
                          'case': case, 'initial_business_sha256': prepared.prefix['prepared_business_state_sha256']})),
                      'active_members': list(prepared.active_roles), 'policies': runner.policy_identities,
                      'mapping_spec_id': VERSION + ':unmapped'})
        prepared_rows.append((slot_id, folder, prepared, runner, captured))
    declaration = declare_window(owner.window_id, actor_identity=owner.freeze_identity(),
                                 gamma_identity={'harness': admission['harness'], 'explicit_cpu_fixture': True},
                                 slot_specs=specs)
    entries, diagnostics, closures = [], [], []
    for slot_id, folder, prepared, runner, captured in prepared_rows:
        owner.counters, owner.task = {}, prepared.case['task']
        episode = folder / 'episode'
        begin_episode(prepared.world, episode, experience=runner.recorder.snapshot(),
                      work_ids=[world.WORK], scenario=prepared.scenario, policies=runner.policy_identities)
        boundary = run_fragment(prepared, runner)
        finish_episode(prepared.world, episode, experience=runner.recorder.snapshot(), termination=boundary)
        entry, diagnostic = export_training_episode(prepared, episode, declaration=declaration,
                                                   slot_id=slot_id, captured=captured, admission=admission)
        entries.append(entry)
        diagnostics.append(diagnostic)
        closures.append((slot_id, episode, prepared, captured))
    return SimpleNamespace(root=root, owner=owner, admission=admission, declaration=declaration,
                           entries=entries, diagnostics=diagnostics, closures=closures, specs=specs)


def test_reserved_real_world_projection_keeps_own_masks_zero_rewards_and_four_slots(projected_window):
    fixture = projected_window
    assert len(fixture.entries) == 4
    assert all(read_json(episode / 'manifest.json')['status'] == 'closed'
               for _, episode, _, _ in fixture.closures)
    assert all(d['has_complete_trainable_actual_members'] and d['has_actual_trainable_tokens']
               and d['actual_trainable_token_count'] > 0 for d in fixture.diagnostics)
    assert all(d['record_validity'] is True and d['business_reward_known'] is True
               for d in fixture.diagnostics)
    assert [e['reward']['reward'] for e in fixture.entries[:2]] == [0, 0]
    assert all(d['assessment']['preparation_credited'] is False for d in fixture.diagnostics)
    assert any(e['kind'] == 'tool_call' and e['payload']['action'] == 'handoff_information'
               for e in fixture.entries[2]['rollout']['events'])
    assert any('EXPLICIT CPU COLLEAGUE INPUT FIXTURE' in json_bytes(request).decode()
               for request in fixture.owner.requests)
    assert all(entry['rollout']['work_validity']['components']['basis']['value'] is None
               and entry['rollout']['work_validity']['components']['delivery']['value'] is None
               for entry in fixture.entries)
    for diagnostic in fixture.diagnostics:
        for member, view in diagnostic['member_views'].items():
            assert view['complete_actor_trajectory']
            assert view['decisions'][0]['actual_response']['choices'][0]['finish_reason'] == 'length'
            assert view['decisions'][0]['actor_trainable']  # failed format remains a target
            allowed = {token for row in fixture.owner.responses if row['member'] == member
                       for token in row['body']['token_trace']['output_ids']}
            for decision in view['decisions']:
                assert decision['labels'] == [-100] * 4 + decision['tokens']['output_ids']
                assert decision['loss_mask'] == [0] * 4 + [1, 1]
                assert set(decision['tokens']['output_ids']) <= allowed
                assert not set(decision['tokens']['output_ids']) & {11, 12, 13, 14}
                assert 'fixture' in decision['actual_response']['fixture_provenance'].lower() or 'synthetic' in decision['actual_response']['fixture_provenance'].lower()
    prepared = prepare_window(fixture.entries, fixture.owner.freeze_identity(), fixture.owner.window_id, fixture.owner.recipe)
    assert prepared['slot_count'] == 4 and len(prepared['slots']) == 4 and prepared['decisions']
    for decision in prepared['decisions']:
        index = int(decision['slot_id'].rsplit('-', 1)[-1])
        view = fixture.diagnostics[index]['member_views'][decision['member_id']]
        member_count = len(fixture.entries[index]['active_members'])
        assert decision['actor_denominator'] == 4 * member_count * view['own_action_tokens']
        assert decision['critic_denominator'] == 4 * member_count * len(view['decisions'])
    # A missing scheduled trajectory remains in the denominator; never shrink it.
    partial = copy.deepcopy(fixture.entries)
    partial[-1]['rollout'] = partial[-1]['reward'] = None
    retained = prepare_window(partial, fixture.owner.freeze_identity(), fixture.owner.window_id, fixture.owner.recipe)
    assert retained['slot_count'] == 4
    assert retained['slots'][-1]['exclusions'] == ['episode_or_reward_record_missing']
    assert {d['actor_denominator'] for d in retained['decisions']} <= {d['actor_denominator'] for d in prepared['decisions']}


def test_projection_rejects_w1_mutable_flags_sources_and_shortened_inventory(projected_window, tmp_path):
    fixture = projected_window
    changed = copy.deepcopy(world.registry())
    changed['reserved_training'][0]['model_training_eligible'] = True
    with pytest.raises(ValueError, match='catalog'):
        training_admission(changed, world.PIN_PATH)
    pin = read_json(world.PIN_PATH)
    pin['transformation_fixture_tamper'] = True
    other = tmp_path / 'different-source.json'
    other.write_bytes(json_bytes(pin))
    with pytest.raises(ValueError, match='template frozen material'):
        training_admission(world.registry(), other)
    slot_id, episode, prepared, captured = fixture.closures[0]
    wrong_case = copy.copy(prepared)
    wrong_case.case = world.registry()['situations'][0]
    with pytest.raises(ValueError, match='actual reserved case|newly reserved'):
        export_training_episode(wrong_case, episode, declaration=fixture.declaration, slot_id=slot_id,
                                captured=captured, admission=fixture.admission)
    altered = copy.copy(prepared)
    altered.case = {**prepared.case, 'model_training_eligible': True}
    with pytest.raises(ValueError, match='newly reserved'):
        export_training_episode(altered, episode, declaration=fixture.declaration, slot_id=slot_id,
                                captured=captured, admission=fixture.admission)
    short = declare_window(fixture.owner.window_id, actor_identity=fixture.owner.freeze_identity(),
                           gamma_identity=fixture.declaration['gamma_identity'], slot_specs=fixture.specs[:1])
    with pytest.raises(ValueError, match='four scheduled'):
        export_training_episode(prepared, episode, declaration=short, slot_id=slot_id,
                                captured=captured, admission=fixture.admission)
    forged = {**fixture.admission, 'max_actor_steps': 999}
    with pytest.raises(ValueError, match='canonical frozen binding'):
        export_training_episode(prepared, episode, declaration=fixture.declaration, slot_id=slot_id,
                                captured=captured, admission=forged)


@pytest.mark.parametrize('field,value', [
    ('actor_identity', {'policy_version': 'not-the-fixture-actor'}),
    ('online_window_id', 'different-window'),
])
def test_actual_response_actor_or_window_mismatch_rejected(projected_window, field, value):
    fixture = projected_window
    entry = copy.deepcopy(fixture.entries[0])
    for event in entry['rollout']['events']:
        if event['kind'] == 'model_response':
            event['payload']['response'][field] = copy.deepcopy(value)
        elif event['kind'] == 'model_attempt' and event['payload'].get('stage') == 'finished':
            event['payload']['response']['body'][field] = copy.deepcopy(value)
    with pytest.raises(ValueError, match='another policy/adapter/profile/window'):
        bind_rollout(fixture.declaration, entry['slot_id'], entry['rollout'])
    with pytest.raises(ValueError, match='Behavior actor identity/window'):
        prepare_window([entry, *fixture.entries[1:]], fixture.owner.freeze_identity(),
                       fixture.owner.window_id, fixture.owner.recipe)


def test_missing_actual_tokens_do_not_turn_known_zero_into_trainable_zero(projected_window):
    from proworksim.member_views import member_view

    fixture = projected_window
    entries = copy.deepcopy(fixture.entries)
    entry = entries[0]
    assert entry['reward']['eligible'] is True and entry['reward']['reward'] == 0
    for event in entry['rollout']['events']:
        if event['kind'] == 'model_response':
            event['payload']['response'].pop('token_trace', None)
        elif event['kind'] == 'model_attempt' and event['payload'].get('stage') == 'finished':
            event['payload']['response']['body'].pop('token_trace', None)
    view = member_view(entry['rollout'], 'implementer')
    qualification = member_token_admission({'implementer': view})
    assert qualification['has_complete_trainable_actual_members'] is False
    assert qualification['has_actual_trainable_tokens'] is False
    assert qualification['token_projection_members']['implementer']['status'] == 'incomplete_or_unknown_tokens'
    prepared = prepare_window(entries, fixture.owner.freeze_identity(), fixture.owner.window_id, fixture.owner.recipe)
    assert prepared['slot_count'] == 4
    assert prepared['slots'][0]['reward']['reward'] == 0
    assert prepared['slots'][0]['members']['implementer']['exclusions'] == ['complete_current_target_trajectory_unavailable']
    assert all(row['slot_id'] != entry['slot_id'] for row in prepared['decisions'])
