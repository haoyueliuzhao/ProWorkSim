"""No-model controls for public-only proposal sampling."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sampling_v156', ROOT/'tools/prepare_communication_pilot_v156.py')
sampling = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sampling)


class SamplingControls(unittest.TestCase):
    def test_fixed_draw_precedence_duplicate_identity_and_no_scores(self):
        def row(n, repo='r/a'):
            return {'instance_id': f'{repo.replace("/", "__")}-{n}', 'repo': repo,
                    'base_commit': str(n), 'problem_statement': f'issue {n}', 'image': 'recorded'}
        rows = [row(i) for i in range(8)]
        duplicate = dict(rows[0], instance_id='duplicate-record')
        one, excluded = sampling.candidates(rows+[duplicate], {rows[1]['instance_id']},
                                            {r['instance_id'] for r in rows[1:]})
        two, _ = sampling.candidates(list(reversed(rows+[duplicate])), {rows[1]['instance_id']},
                                     {r['instance_id'] for r in rows[1:]})
        self.assertEqual(one, two)
        self.assertEqual(len(one['r/a']), 8)
        self.assertEqual(len(excluded), 1)
        self.assertEqual(one['r/a'][-1]['instance_id'], rows[1]['instance_id'])

    def test_balanced_condition_orders_and_pending_deviation_are_explicit(self):
        import json
        root = ROOT/'artifacts/software-benchmark-v156/communication-design-r1'
        d = json.loads((root/'recommended-24-candidate.json').read_text())
        self.assertEqual(d['distinct_tasks'], 24)
        self.assertEqual(len({r['instance_id'] for r in d['tasks']}), 24)
        self.assertEqual(len(d['rows']), 72)
        self.assertFalse(d['dispatch_enabled'])
        self.assertFalse(d['frozen_for_model_execution'])
        self.assertEqual(d['constraints_not_met'], ['per_repository_max_2', 'wave_2_covers_12_repositories'])
        self.assertEqual([w['tasks'] for w in d['waves']], [12, 12])
        self.assertEqual([w['repositories'] for w in d['waves']], [12, 11])
        for wave in d['waves']:
            self.assertEqual(sorted(wave['condition_orders'].values()), [2]*6)
        for task in d['tasks']:
            group = [r for r in d['rows'] if r['instance_id'] == task['instance_id']]
            self.assertEqual({r['condition'] for r in group}, {'C0', 'C1', 'C2'})
            self.assertEqual(len({r['seed'] for r in group}), 1)
        h = json.loads((root/'history-exposure.json').read_text())
        self.assertEqual(h['positive_execution_identity_count'], 500)
        self.assertFalse(h['scores_or_patch_content_read'])


if __name__ == '__main__':
    unittest.main()
