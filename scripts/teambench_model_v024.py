"""Explicit CPU D2 controls only: no model, API, GPU, or evaluation queue."""
import argparse
import json
from pathlib import Path

from proworksim.teambench_model_v023 import file_sha, write
from proworksim.teambench_model_v024 import (
    D2Episode, SEEDS, VERSION, assess_verification_table,
)
from scripts.teambench_admission_v021 import D2_WITNESS
from scripts.teambench_model_v023 import CHECKER

VARIANTS = ('correct', 'successful_check_no_attestation', 'equal_but_jointly_wrong',
            'failed_check_then_pass', 'success_then_failed_check_final_pass')


def missing_numeric_control(output, grader):
    """Small explicit table example, not a new generator/model evaluation seed."""
    output = Path(output)
    output.mkdir(parents=True)
    columns = ['id', 'name', 'score', 'dept']
    table = {'columns': columns, 'rows': [
        ['h', 'High', '100', 'sales'], ['z', 'Zero', '0', 'sales'],
        ['m1', 'Alpha', 'MISSING', 'sales'], ['m2', 'Zulu', 'MISSING', 'sales']]}
    expected = {'columns': columns, 'row_count': 4, 'score_col': 'score', 'dept_col': 'dept',
                'dup_ids': [], 'dup_winner_scores': {}, 'out_of_range_ids': ['dropped'],
                'missing_ids': ['m1', 'm2'], 'low_score_missing_dept_id': None,
                'correct_fill': 'MISSING', 'review_needed_id': None}
    # Required schema uses a string for the low-score witness even when this
    # manual table does not contain a department-correction witness.
    expected['low_score_missing_dept_id'] = ''
    expected['review_needed_id'] = ''
    expected_path = output / 'expected.json'
    write(expected_path, expected)
    frozen = file_sha(expected_path)
    result = assess_verification_table(table, grader=grader, expected=expected_path, expected_sha=frozen)
    before_numeric = {**table, 'rows': table['rows'][2:] + table['rows'][:2]}
    wrong_order = assess_verification_table(before_numeric, grader=grader, expected=expected_path, expected_sha=frozen)
    dropped_missing = {**table, 'rows': table['rows'][:2]}
    dropped = assess_verification_table(dropped_missing, grader=grader, expected=expected_path, expected_sha=frozen)
    row = {'kind': 'explicit_manual_table_not_generator_seed', 'table': table,
           'correct': result, 'missing_before_numeric': wrong_order, 'missing_dropped': dropped,
           'passed': result['content_correct'] and not wrong_order['content_correct'] and not dropped['content_correct']}
    write(output / 'report.json', row)
    return row


def cpu_controls(output, development_assets):
    output, assets = Path(output).resolve(), Path(development_assets).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write(output / 'declaration.json', {'version': VERSION, 'model_calls': 0, 'api_calls': 0,
          'gpu_seconds': 0, 'parameter_updates': 0, 'seed': 0, 'explicit_program_controls': True,
          'variants': list(VARIANTS), 'held_out_seeds_used': False})
    original_generated = assets / 'generated/seed0'
    grader = assets / 'reviewed-source/tasks/D2_data_quality/grade.sh'
    original = {str(path.relative_to(original_generated)): file_sha(path)
                for path in original_generated.rglob('*') if path.is_file()}
    rows = []
    for variant in VARIANTS:
        episode = D2Episode(original_generated, grader, output / variant, seed=0)
        code = D2_WITNESS
        checker = CHECKER
        if variant == 'equal_but_jointly_wrong':
            # The same explicit mistake in both independently executed programs.
            insertion = "clean = [row for row in clean if row[score] != 'MISSING']\nclean.sort("
            code = code.replace('clean.sort(', insertion)
            checker = checker.replace('clean.sort(', insertion)
        for action, args in [
                ('write_pipeline', {'source': code}), ('run_pipeline', {}), ('submit', {})]:
            if not episode.call('executor', action, **args)['ok']:
                raise ValueError('CPU executor program control did not complete')
        for material in ('spec', 'code', 'input', 'output'):
            if not episode.call('verifier', 'read_material', material=material)['ok']:
                raise ValueError('CPU verifier read control did not complete')
        responses = []
        denied_program = "from pathlib import Path;Path('data/output/clean.csv').write_text('forbidden')"
        if variant == 'failed_check_then_pass':
            checker = denied_program
        responses.append(episode.call('verifier', 'verify_submission', source=checker))
        final_id = 'check-0'
        if variant == 'success_then_failed_check_final_pass':
            responses.append(episode.call('verifier', 'verify_submission', source=denied_program))
            final_id = 'check-1'
        if variant != 'successful_check_no_attestation':
            episode.call('verifier', 'attest', verdict='pass', reason='Explicit CPU program fixture',
                         submission_id=episode.submission['submission_id'], verification_id=final_id)
        result = episode.assess()
        write(output / variant / 'report.json', result)
        evidence = result['responsibility']
        passed = (evidence['verification_attempted']
                  and evidence['final_attestation_supported'] is (variant == 'correct')
                  and evidence['full_joint_responsibility'] is (variant == 'correct')
                  and evidence['fixed_workspace_unchanged']
                  and evidence['verification_execution_succeeded'] is (variant != 'failed_check_then_pass')
                  and evidence['verification_table_valid'] is (variant != 'failed_check_then_pass'))
        if variant == 'equal_but_jointly_wrong':
            passed = passed and evidence['verification_matches_submission'] and not evidence['verification_content_correct']
        if variant == 'success_then_failed_check_final_pass':
            passed = passed and not evidence['final_attestation_computation_succeeded'] and evidence['verification_content_correct']
        no_oracle = all('content_assessment' not in str(response) and 'content_correct' not in str(response)
                        and 'expected.json' not in str(response) for response in responses)
        rows.append({'variant': variant, 'matches_declared_expectation': bool(passed and no_oracle),
                     'oracle_metrics_not_returned_to_verifier': no_oracle, 'result': result})
    pinned = output / 'correct/roles-world/trusted/grade.sh'
    numeric = missing_numeric_control(output / 'missing-numeric-table', pinned)
    after = {str(path.relative_to(original_generated)): file_sha(path)
             for path in original_generated.rglob('*') if path.is_file()}
    report = {'version': VERSION, 'status': 'complete', 'controls': rows,
              'missing_numeric_control': numeric, 'original_development_material_unchanged': original == after,
              'all_declared_controls_passed': all(row['matches_declared_expectation'] for row in rows) and numeric['passed'] and original == after,
              'model_calls': 0, 'model_episodes': 0, 'api_calls': 0, 'gpu_seconds': 0,
              'proposed_model_seeds': list(SEEDS), 'proposed_model_seeds_generated': False,
              'external_model_status': 'not_started',
              'scope': 'Five explicit CPU program episodes on old seed 0, plus one manual table; not new model results or a repeated OS matrix.'}
    write(output / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--development-assets', type=Path, default=Path('runs/teambench-v022-os-isolation-verified'))
    args = parser.parse_args()
    report = cpu_controls(args.output, args.development_assets)
    print(json.dumps({key: report[key] for key in ('status', 'all_declared_controls_passed', 'model_calls', 'gpu_seconds', 'external_model_status')}))
    if not report['all_declared_controls_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
