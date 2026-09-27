"""B1 controller/qualification controls; explicitly fake owner, no GPU/model."""
import copy
import sys
from types import SimpleNamespace

import pytest

from proworksim import bridge_admission_v022 as admission
from proworksim.functional_qwen_v022 import CONTRACT
from proworksim.storage import digest, json_bytes, read_json
from scripts import bridge_work_v022 as bridge
from scripts import run_bounded_v022 as bounded


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))
    return {'path': str(path.resolve()), 'sha256': digest(path.read_bytes())}


def qualification_fixture(tmp_path, monkeypatch):
    actor = {'version': 'explicit-cpu-fake-identity', 'policy_version': 'fake-fixed'}
    owner_ref = save(tmp_path / 'owner-plan.json', {'explicit_fixture': True})
    responses = []
    for i, (inputs, outputs) in enumerate(((8473, 146), (4251, 308), (13275, 2048))):
        trace = {'input_ids': [1]*inputs, 'output_ids': [2]*outputs, 'raw_output_ids': [2]*outputs,
                 'behavior_logprobs': [-.5]*outputs, 'raw_behavior_logprobs': [-.5]*outputs}
        responses.append(save(tmp_path / f'response-{i}.json', {
            'fixture': 'Synthetic token evidence, not real generation', 'status': 200,
            'actor_identity': actor, 'response': {'actor_identity': actor, 'token_trace': trace}}))
    n_plan = {'version': 'functional-state-N1-heldout-selection-v0.22', 'candidate_count': 1,
              'new_sampling': False, 'optimizer_steps': 0, 'actual_backward_required': True,
              'auto_retry_or_new_candidate': False, 'probability_gate': {'max_abs_logp': .02, 'mean_abs_logp': .002},
              'owner_plan_ref': owner_ref, 'development_response': responses[0],
              'heldout_requests': [{'response': responses[1], 'input_tokens': 4251, 'output_tokens': 308},
                                   {'response': responses[2], 'input_tokens': 13275, 'output_tokens': 2048}]}
    source = {'code_commit': '1'*40, 'code_dirty': False}
    n = {'version': 'functional-state-N1-experiment-v0.22', 'status': 'qualified_fixed_list',
         'qualification_passed': True, 'candidate_contract': CONTRACT, 'planned_requests': 3,
         'actual_backward_calls': 3, 'backward_calls_attempted': 3, 'new_sampling': False,
         'actor_steps': 0, 'critic_steps': 0, 'parameter_steps': 0, 'initial_actor_identity': actor,
         'final_actor_identity': actor, 'actor_identity_unchanged': True,
         'learning_state_guard': {'learning_unchanged': True, 'rng_restored_exactly': True},
         'source_before': source, 'source_after': source, 'source_unchanged': True,
         'plan': save(tmp_path / 'n-plan.json', n_plan), 'rows': []}
    for i, (name, inputs, outputs) in enumerate((('development', 8473, 146), ('heldout-0', 4251, 308), ('heldout-1', 13275, 2048))):
        n['rows'].append({'request': name, 'record': responses[i], 'input_tokens': inputs, 'output_tokens': outputs,
                         'status': 'complete', 'actual_backward': True, 'finite_gradients': True,
                         'nonzero_gradient_elements': 1, 'parameter_steps': 0, 'actor_identity_unchanged': True,
                         'raw_tokens_and_behavior_preserved': True, 'all_output_targets_included': outputs,
                         'probability': {'passed': True, 'actual_behavior_logprobs': [-.5]*outputs,
                                         'recomputed_logprobs': [-.5]*outputs, 'signed_delta': [0]*outputs,
                                         'max_abs_delta': 0.0, 'mean_abs_delta': 0.0}})
    catalog = save(tmp_path / 'catalog.json', {'explicit_fixture': True})
    work_files = {path: digest((admission.ROOT/path).read_bytes()) for path in admission.WORK_FILES}
    projection = save(tmp_path / 'projection.json', {'passed': True, 'tests_passed': 5,
        'source_files': {path: digest((admission.ROOT/path).read_bytes()) for path in admission.PROJECTION_FILES}})
    w_plan = save(tmp_path / 'w-plan.json', {'version': 'paired-work-presentation-v0.22',
        'parameter_updates': 0, 'model_api_calls': 0, 'catalog': catalog,
        'prior_model_plan': owner_ref, 'initial_identity_response': responses[0]})
    controls = save(tmp_path / 'work-controls.json', {
        'version': 'work-view-cpu-controls-v0.22', 'passed': True, 'same_initial_business_state': True,
        'model_calls': 0, 'arms': [{'arm': arm, 'passed': True} for arm in ('original_history', 'compact_work')],
        'source_manifest_sha256': work_files['examples/retail-collaboration-v22/source-manifest.json']})
    b = {'initial_identity_response': responses[0], 'prior_model_plan': owner_ref, 'catalog': catalog,
         'qualified_functional_module': bounded.reference(admission.ROOT / admission.FUNCTIONAL_PATH),
         'token_projection_qualification': projection,
         'work_protocol_qualification': {'source_commit': '1'*40, 'source_files': work_files,
             'w1_plan': w_plan, 'w1_initial_identity': save(tmp_path / 'w-owner.json', {'initial_actor_identity': actor}),
             'cpu_work_controls': controls}}
    looked_up = []
    def git_file(commit, relative):
        admission._commit(commit)
        looked_up.append((commit, relative))
        return (admission.ROOT / relative).read_bytes()
    monkeypatch.setattr(admission, '_git_file', git_file)
    def seal():
        supervisor = {'version': bounded.VERSION, 'line': 'B1', 'budget_seconds': bounded.CAPS['B1'],
                      'limits': bounded.LIMITS, 'gpu_pool': [2, 3, 4, 5, 6], 'module': bounded.MODULES['B1'],
                      'allow_parameter_updates': True, 'N1_qualification': save(tmp_path / 'n-report.json', n)}
        b['supervisor_qualification'] = copy.deepcopy(supervisor)
        supervisor['experiment_plan'] = save(tmp_path / 'b-plan.json', b)
        return supervisor
    return n, b, seal, looked_up


def test_b1_qualification_binds_full_numeric_source_projection_and_actual_w_initialization(tmp_path, monkeypatch):
    n, b, seal, looked_up = qualification_fixture(tmp_path, monkeypatch)
    supervisor = seal()
    assert bounded.validate(supervisor) == 'B1'
    proof = admission.validate_bridge_qualification(supervisor)
    assert proof['passed'] and proof['W1_outcomes_required_or_read'] is False
    assert {path for _, path in looked_up} == admission.WORK_FILES | {admission.FUNCTIONAL_PATH}
    # A mutable flag cannot replace the last held-out request/backward.
    n['rows'][-1]['actual_backward'] = False
    with pytest.raises(ValueError, match='request/backward inventory'):
        admission.validate_bridge_qualification(seal())
    n['rows'][-1]['actual_backward'] = True
    # A real-looking W1 owner with another initial policy is not transferable.
    b['work_protocol_qualification']['w1_initial_identity'] = save(tmp_path / 'wrong-owner.json', {'initial_actor_identity': {'policy_version': 'different'}})
    with pytest.raises(ValueError, match='resident initialization'):
        admission.validate_bridge_qualification(seal())
    b['work_protocol_qualification']['w1_initial_identity'] = save(tmp_path / 'right-owner.json', {'initial_actor_identity': n['initial_actor_identity']})
    actual_git = admission._git_file
    monkeypatch.setattr(admission, '_git_file', lambda commit, path: b'not-the-qualified-module' if path == admission.FUNCTIONAL_PATH else actual_git(commit, path))
    with pytest.raises(ValueError, match='actual N1 frozen Git source'):
        admission.validate_bridge_qualification(seal())
    with pytest.raises(ValueError, match='40-hex'):
        admission._commit('HEAD; untrusted-shell-text')


def test_b1_zero_step_and_update_both_close_owner_before_two_fresh_post_windows(tmp_path, monkeypatch):
    from proworksim import collaboration_actor_v022
    from proworksim.templates import retail_collaboration_v022 as world

    catalog = {'reserved_training': [{'case_id': f't{i}'} for i in range(4)],
               'reserved_bridge': [{'case_id': 'post0'}, {'case_id': 'post1'}]}
    source = {'code_commit': '2'*40, 'code_dirty': False}
    monkeypatch.setattr(bridge, 'code_identity', lambda: source)
    monkeypatch.setattr(bounded, 'validate', lambda _: 'B1')
    monkeypatch.setattr(admission, 'validate_bridge_qualification', lambda _: {'passed': True, 'explicit_fake': True})
    monkeypatch.setattr(bridge, 'training_admission', lambda *a, **k: {'explicit_fake': True})
    monkeypatch.setattr(world, 'registry', lambda: catalog)
    monkeypatch.setattr(world, 'build_case', lambda case, folder, **kwargs: SimpleNamespace(
        world=object(), scenario={}, case=case, active_roles=['implementer', 'reviewer']))
    monkeypatch.setattr(world, 'assess_episode', lambda _: {'eligible': True, 'reward': 0})
    runtime = SimpleNamespace(recorder=SimpleNamespace(snapshot=lambda: {}), policy_identities={}, snapshot=lambda: {})
    monkeypatch.setattr(bridge, 'fragment_runtime', lambda *a: (runtime, {}, {}))
    monkeypatch.setattr(bridge, 'begin_episode', lambda *a, **k: None)
    monkeypatch.setattr(bridge, 'finish_episode', lambda *a, **k: None)
    monkeypatch.setattr(bridge, 'run_fragment', lambda *a, **k: {'explicit_fixture_boundary': True})
    monkeypatch.setenv('CUDA_VISIBLE_DEVICES', '2')  # checked string only; no CUDA calls.

    class FakeOwner:
        recipe = {'credit_assignment': 'terminal_mc'}
        def __init__(self, update):
            self.update = update
            self.phase, self.actor_steps, self.critic_steps = 'idle', 0, 0
            self.used = []
        def freeze_identity(self): return {'policy_version': f'explicit-fake-{self.actor_steps}'}
        def _make_identity(self): return self.freeze_identity()
        def begin_window(self, name):
            assert self.phase == 'idle' and name not in self.used
            self.used.append(name)
            self.phase = 'collecting'
            return self.freeze_identity()
        def reseed(self, *a, **k): assert self.phase == 'collecting'
        def update_window(self, entries, output):
            assert self.phase == 'collecting' and len(entries) == 4
            self.actor_steps = self.critic_steps = int(self.update)
            self.phase = 'idle'
            return {'status': 'updated' if self.update else 'zero_step_zero_actor_advantage_or_gradient'}
        def save_checkpoint(self, output):
            assert self.phase == 'idle'
            return {'explicit_fake_checkpoint': True, 'actor_identity': self.freeze_identity()}
        def capture_evaluation_state(self):
            assert self.phase == 'idle'
            return self.freeze_identity()
        def finish_evaluation(self, entries, output):
            assert self.phase == 'collecting'
            self.phase = 'idle'
        def finish_evaluation_guard(self, before):
            assert self.phase == 'idle' and before == self.freeze_identity()
            return {'learning_unchanged': True, 'rng_restored_exactly': True}

    def train(owner, *args):
        owner.begin_window('v022-b1-train')
        return [{'slot_id': str(i)} for i in range(4)], [{'status': 'closed'} for _ in range(4)]
    monkeypatch.setattr(bridge, 'train_window', train)
    for updated in (False, True):
        folder = tmp_path / str(updated)
        owner = FakeOwner(updated)
        monkeypatch.setattr(collaboration_actor_v022.FunctionalCandidateActor, 'from_candidate', classmethod(lambda cls, *a, **k: owner))
        model_plan = save(folder / 'prior.json', {'model': 'explicit-fake', 'manifest': save(folder / 'manifest.json', {}),
                                                'runtime_profile': {}, 'recipe': owner.recipe})
        plan = {'version': bridge.VERSION, 'per_active_role_opportunities': 4, 'max_actor_steps': 1,
                'max_critic_steps': 1, 'model_api_calls': 0, 'supervisor_qualification': {},
                'catalog': save(folder / 'catalog.json', catalog),
                'qualified_functional_module': bounded.reference(admission.ROOT / admission.FUNCTIONAL_PATH),
                'source_pin': save(folder / 'pin.json', {}), 'prior_model_plan': model_plan,
                'initial_identity_response': save(folder / 'identity.json', {'response': {'actor_identity': owner.freeze_identity()}}),
                'assets_root': str(folder / 'no-assets-needed')}
        plan_ref = save(folder / 'plan.json', plan)
        monkeypatch.setattr(sys, 'argv', ['bridge', '--plan', plan_ref['path'], '--output', str(folder / 'run')])
        assert bridge.main() == 0
        report = read_json(folder / 'run/report.json')
        assert report['status'] == 'complete' and owner.phase == 'idle'
        assert owner.used == ['v022-b1-train', 'v022-b1-post-0', 'v022-b1-post-1']
        assert report['actor_steps'] == report['critic_steps'] == int(updated)
        assert all(row['actor_identity'] == report['after_update_actor_identity'] for row in report['post_rows'])
        assert (report['initial_actor_identity'] != report['after_update_actor_identity']) is updated
        assert report['learner_execution_profile'] == CONTRACT
