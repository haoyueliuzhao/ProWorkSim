"""Real CPU world paths plus explicit arithmetic controls; never training data."""
import copy

import pytest

from proworksim.episode import assess_historical_episode, begin_episode, finish_episode
from proworksim.experience import ExperienceRecorder, capture_port
from proworksim.handoff_credit_v024 import attach_ledger, first_applicable_handoff, ledger_from_evidence
from proworksim.online_signals import joint_return
from proworksim.retail_rewards import RetailEvidence
from proworksim.storage import digest, read_json
from proworksim.templates import retail_collaboration_v024 as world
from proworksim.templates.retail_work import witness_code
from scripts.retail_collaboration_experiment_v021 import Witness, a_path


class V24Witness(Witness):
    def finish(self):
        finish_episode(self.prepared.world, self.episode, experience=self.recorder.snapshot(),
                       termination={'status': 'explicit_CPU_control', 'origin': 'program_not_model'})
        result = world.assess_episode(self.episode)
        return {**result, 'spec': self.prepared.reward_spec,
                'episode_id': read_json(self.episode / 'manifest.json')['episode_id'],
                'manifest_sha256': digest((self.episode / 'manifest.json').read_bytes())}


def make(tmp_path, label):
    if not (world.DEFAULT_ASSETS / 'manifest.json').exists():
        pytest.skip('Exact newly pinned v024 source materials required')
    case = world.registry()['training_cases'][0]
    return V24Witness(world.build_case(case, tmp_path / label), tmp_path / label)


@pytest.mark.parametrize('outcome,expected', [('handoff', .2), ('build', .5), ('complete', 1.)])
def test_real_world_settlement_preserves_terminal_and_includes_producing_action(tmp_path, outcome, expected):
    w = make(tmp_path, outcome)
    a_path(w, 'delivered_unused')
    if outcome != 'handoff':
        refs = []
        for alias in ('data', 'basis'):
            ref = w.read('implementer', alias)['reference']
            w.call('implementer', 'adopt', alias=alias, **ref, policy='fixed', work_ids=[world.WORK])
            refs.append(ref)
        w.call('implementer', 'write_object', alias='code', data=witness_code(), dependencies=refs, work_id=world.WORK)
        w.call('implementer', 'sql_build', code_alias='code', output_alias='result',
               input_aliases=['data', 'basis'], work_id=world.WORK)
        if outcome == 'complete':
            w.call('implementer', 'submit', work_id=world.WORK, artifacts=['code', 'result'])
    reward = attach_ledger(w.finish(), w.episode)
    assert reward['eligible'] and reward['reward'] == expected
    early, terminal = reward['ledger']['events']
    assert early['amount'] == .2 and terminal['amount'] == round(expected - .2, 10)
    assert early['source']['action_sequence'] < early['sequence']
    events = w.recorder.events
    for sequence in (early['source']['action_sequence'], early['sequence']):
        assert joint_return(reward, sequence, 'joint_reward_to_go', events)[0] == expected
    assert joint_return(reward, early['sequence'] + 1, 'joint_reward_to_go', events)[0] == round(expected - .2, 10)
    assert joint_return(reward, early['sequence'] + 1, 'terminal_mc', events)[0] == expected
    assert early['source']['selection_uses_terminal_outcome'] is False


def test_repeat_preparation_and_real_late_revision_do_not_move_early_credit(tmp_path):
    w = make(tmp_path, 'duplicate-and-late-revision')
    a_path(w, 'delivered_unused')
    original_ref = w.read('provider', 'basis')['reference']
    for key in ('actual-policy', 'second-distinct-key'):
        w.call('provider', 'handoff_information', route_id='basis', work_id=world.WORK,
               handoff_key=key, reference=original_ref,
               body='Applicable exact reporting policy for your declared work.')
    w.call('implementer', 'read_messages')
    # Real authorized operator supersession, after the delivered fact. It is not
    # an actor call and must not be inserted into the actor's training history.
    reply = w.prepared.world.session('operator', 'TEAM').call(
        'revise', work_id=world.WORK, updates={'goal': 'Explicit late control requirement'},
        reason='CPU control: requirement superseded after actual delivery')
    assert reply['ok']
    reward = w.finish()
    e = RetailEvidence(w.episode, reward['spec'], assess_historical_episode(w.episode))
    event = first_applicable_handoff(e)
    assert event is not None
    ledger = ledger_from_evidence(e, reward)
    assert len([x for x in ledger['events'] if x['settlement'] == 'event']) == 1
    # Current frozen retail contract may retain its original historical term.
    # This is explicitly a stipulated terminal correction, not a grader score.
    correction = {**reward, 'reward': 0., 'explicit_mathematical_terminal_control': True}
    corrected = ledger_from_evidence(e, correction)
    assert corrected['events'][0] == event
    assert corrected['events'][-1]['amount'] == -.2
    assert joint_return({**correction, 'ledger': corrected}, event['sequence'] + 1,
                        'joint_reward_to_go', e.events)[0] == -.2
    assert sum(row['amount'] for row in corrected['events']) == 0
    # Changing all terminal-only outcome information cannot change event time.
    changed = copy.deepcopy(e)
    changed.state['handoffs'][event['source']['handoff_id']]['status'] = 'obsolete'
    changed.item['requirement_version'] += 99
    assert first_applicable_handoff(changed) == event

    # The same legal WorldCore handoff entirely before begin_episode earns no
    # credit in a later actor interval, even if another read is recorded there.
    prepared = make(tmp_path, 'prepared-delivery')
    a_path(prepared, 'delivered_unused')
    prepared.finish()
    recorder = ExperienceRecorder()
    second = tmp_path / 'prepared-delivery' / 'later-episode'
    begin_episode(prepared.prepared.world, second, experience=recorder.snapshot(), work_ids=[world.WORK],
                  scenario=prepared.prepared.scenario, policies=prepared.policies)
    capture = []
    port = capture_port(prepared.prepared.world.session('provider', 'TEAM'), capture)
    port.call('read_alias', alias='basis', work_id=world.WORK)
    recorder.record('tool_call', capture[-1]['payload'], 'provider')
    finish_episode(prepared.prepared.world, second, experience=recorder.snapshot(),
                   termination={'status': 'CPU_preparation_exclusion'})
    other = RetailEvidence(second, prepared.prepared.reward_spec, assess_historical_episode(second))
    assert first_applicable_handoff(other) is None
