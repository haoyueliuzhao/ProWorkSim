"""Budget, case and seed accounting before any candidate is selected."""
from scripts.build_learning_pilot_v015 import build_protocols


def test_pilot_has_fixed_task_shares_fresh_starts_and_common_evaluations_counted_once():
    source = {'version': 'fixture', 'candidate_id': 'fixture', 'runtime': {}, 'recipe': {'seed': 11}}
    result = build_protocols(source)
    bridge, mc, rtg = [result[k] for k in ('bridge.json', 'pilot-mc.json', 'pilot-rtg.json')]
    assert [sum(len(w['slots']) for w in p['windows']) for p in (bridge, mc, rtg)] == [32, 104, 84]
    for p in (mc, rtg):
        training = [w for w in p['windows'] if w['mode'] == 'online']
        assert len(training) == 4 and all(len(w['slots']) == 16 for w in training)
        for w in training:
            assert sorted(s['task'] for s in w['slots']) == sorted(['implement', 'review', 'pair', 'chain'] * 4)
            assert len({s['case_id'] for s in w['slots']}) == 4
    assert sum(len(w['slots']) for p in (mc, rtg) for w in p['windows'] if w['mode'] == 'evaluate') == 60
    a = [w for w in mc['windows'] if w['mode'] == 'online']
    b = [w for w in rtg['windows'] if w['mode'] == 'online']
    assert [[(s['case_id'], s['sampling_seed']) for s in w['slots']] for w in a] == [[(s['case_id'], s['sampling_seed']) for s in w['slots']] for w in b]
    assert mc['recipe']['seed'] == rtg['recipe']['seed'] != bridge['recipe']['seed']
    assert source['recipe']['seed'] == 11
