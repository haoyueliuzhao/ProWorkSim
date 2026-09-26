"""CPU protocol fixture: paired software probes, no model selection/execution."""
import copy
import json

from scripts.build_learning_pilot_v015 import build_protocols as build_pilot
from scripts.build_software_eval_v015 import INITIAL_SEED, SAMPLING_SEEDS, build_protocols, main


def test_three_nodes_share_runtime_seeds_and_n1_init_without_bridge_weights(tmp_path):
    screen = {'version': 'fixture-screen', 'candidate_id': 'explicit-fixture',
              'runtime': {'kind': 'fixture-only', 'profile': {'temperature': 0.7, 'max_output_tokens': 2048}},
              'recipe': {'seed': 11, 'temperature': 0.7, 'max_output_tokens': 2048, 'max_length': 16384,
                         'credit_assignment': 'terminal_mc', 'lora': {'r': 8, 'target_modules': ['q_proj', 'v_proj']}}}
    original = copy.deepcopy(screen)
    protocols, study = build_protocols(screen)
    pilot = build_pilot(screen)
    assert screen == original
    assert study['planned_evaluation_episodes'] == 9 and study['planned_training_episodes'] == 0
    assert study['planned_optimizer_steps'] == {'actor': 0, 'critic': 0}
    assert study['reporter']['uci_reporter_compatible'] is False
    assert study['max_total_opportunities'] == 9 * 18
    assert INITIAL_SEED == pilot['pilot-mc.json']['recipe']['seed'] == pilot['pilot-rtg.json']['recipe']['seed']
    assert INITIAL_SEED != pilot['bridge.json']['recipe']['seed']
    all_ids = []
    for filename, protocol in protocols.items():
        assert protocol['runtime'] == screen['runtime']
        assert protocol['mode'] == 'evaluate'
        assert protocol['role_decision_limits'] == {'implementer': 18}
        assert [episode['sampling_seed'] for episode in protocol['episodes']] == list(SAMPLING_SEEDS)
        assert all(set(episode) == {'episode_id', 'sampling_seed'} for episode in protocol['episodes'])
        assert protocol['fixed_case']['case_id'] == 'marshmallow-v15-strip-implement'
        all_ids.extend(episode['episode_id'] for episode in protocol['episodes'])
        counterpart = 'pilot-rtg.json' if filename == 'software-rtg-final.json' else 'pilot-mc.json'
        assert protocol['recipe'] == pilot[counterpart]['recipe']
        assert 'N0_bridge_actor' in protocol['checkpoint_binding']['forbidden_sources']
        assert protocol['checkpoint_binding']['restore_checkpoint_required'] == (filename != 'software-initial.json')
    assert len(all_ids) == len(set(all_ids)) == 9
    initial = protocols['software-initial.json']['checkpoint_binding']
    assert initial['kind'] == 'fresh_selected_base' and initial['restore_checkpoint_forbidden']
    # Mutating one output cannot mutate another protocol or the caller's runtime.
    protocols['software-initial.json']['runtime']['profile']['temperature'] = 0.1
    assert protocols['software-mc-final.json']['runtime']['profile']['temperature'] == 0.7
    assert screen == original
    source = tmp_path / 'explicit-selected.json'
    source.write_text(json.dumps(screen))
    output = tmp_path / 'frozen'
    main(['--selected-screen-protocol', str(source), '--output', str(output)])
    frozen = json.loads((output / 'software-study.json').read_text())
    assert len(frozen['jobs']) == 3 and frozen['selected_screen_protocol']['sha256']
    assert {p.name for p in output.iterdir()} == {'software-study.json', *protocols}
