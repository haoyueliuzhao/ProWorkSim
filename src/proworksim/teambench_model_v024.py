"""Narrow D2 public-contract and verification measurement revision.

The pinned generator and named grader are unchanged. Trusted content assessment
runs the grader's eight existing table predicates against verifier stdout, never
rerunning the actor or returning oracle assessment to the verifier. This module
has no automatic launch or GPU allocation entrypoint.
"""
from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .model_policy import ModelPolicy
from .online_collection import _config
from .staff_runtime import StaffRuntime
from .storage import digest
from .teambench_model_v023 import (
    D2Episode as PreviousEpisode, D2Port, ROLE_LIMITS, TASKS, file_sha, regular,
    write,
)

VERSION = 'd2-real-role-adapter-v0.24'
SEEDS = (20261101, 20261102, 20261103)
CHECKPOINTS = ('initial', 'mc_final', 'handoff_rtg_final')
PUBLIC_CLARIFICATION = '''

## Missing numeric values (explicit D2 contract)
A missing numeric cell (empty string or N/A) is retained and replaced with
MISSING. It is exempt from the ordinary numeric 0–100 range filter; a missing
numeric value alone is not grounds to drop its row. For the existing descending
numeric sort, treat MISSING as -1: it sorts AFTER all ordinary values 0–100.
The existing name-ascending tie rule still applies, including ties between
missing numeric values. All other rules, including deduplication and department
correction, remain as specified above.
'''
PREDICATE_NAMES = (
    'wrong_columns', 'wrong_row_count', 'duplicate_ids', 'range_check_fail',
    'missing_values_not_replaced', 'dedup_higher_score_fail', 'sort_order_wrong',
    'department_correction_fail',
)


def table_valid(table):
    return (isinstance(table, dict) and set(table) == {'columns', 'rows'}
            and isinstance(table['columns'], list) and len(table['columns']) == 4
            and all(isinstance(value, str) for value in table['columns'])
            and isinstance(table['rows'], list)
            and all(isinstance(row, list) and len(row) == 4
                    and all(isinstance(value, str) for value in row)
                    for row in table['rows']))


def assess_verification_table(table, *, grader, expected, expected_sha):
    """Controller-only exact reuse of eight pinned table checks, without actor.

    This is finite predicate coverage, not full cellwise equality to an oracle
    table, generic pipeline correctness, or independent mental reasoning.
    """
    from scripts.teambench_admission_v021 import validate_d2_expected
    from scripts.teambench_isolation_v022 import D2_GRADE_SHA
    if not table_valid(table):
        raise ValueError('Content assessment requires a structurally valid table')
    if file_sha(grader) != D2_GRADE_SHA:
        raise ValueError('Content predicates must come from the pinned D2 variant')
    validate_d2_expected(Path(expected), expected_sha)
    source = Path(grader).read_text()
    extracted = re.findall(r'check "python3 -c \\"\n(.*?)\n\\"" "([^"]+)"', source, re.S)
    if tuple(name for _, name in extracted) != PREDICATE_NAMES:
        raise ValueError('Pinned D2 content predicate extraction changed')
    rows = []
    with tempfile.TemporaryDirectory(prefix='proworksim-d2-v024-') as folder:
        root = Path(folder)
        table_path, expected_path = root / 'table.csv', root / 'expected.json'
        with table_path.open('w', newline='') as stream:
            writer = csv.writer(stream, lineterminator='\n')
            writer.writerow(table['columns'])
            writer.writerows(table['rows'])
        shutil.copyfile(regular(expected), expected_path)
        for code, name in extracted:
            program = code.replace('\\"', '"').replace('$EXPECTED', str(expected_path)).replace('$RESULT', str(table_path))
            result = subprocess.run(['/usr/bin/python3', '-I', '-B', '-S', '-c', program],
                                    capture_output=True, text=True, timeout=10,
                                    env={'LANG': 'C.UTF-8'}, check=False)
            rows.append({'predicate': name, 'passed': result.returncode == 0,
                         'predicate_source_sha256': digest(code.encode()),
                         'returncode': result.returncode})
    return {'status': 'checked', 'content_correct': all(row['passed'] for row in rows),
            'checks_passed': sum(row['passed'] for row in rows), 'checks_total': len(rows),
            'predicates': rows, 'grader_sha256': D2_GRADE_SHA,
            'expected_sha256': expected_sha, 'actor_reruns': 0,
            'scope': 'Eight unchanged pinned D2 table predicates on this returned table; controller-only, not an oracle tool response.'}


def verification_metrics(verifications, attestation, *, submission_id,
                         complete_reads, fixed_workspace_unchanged, attempted):
    """Any-attempt facts and the one final binding are deliberately separate."""
    bound = next((row for row in verifications if attestation and
                  row['verification_id'] == attestation['verification_id'] and
                  row['submission_id'] == submission_id), None)
    valid = [row for row in verifications if row['valid_expected_table']]
    assessed = [row for row in valid if row.get('content_assessment', {}).get('status') == 'checked']
    final_computation = bool(bound and bound['execution_succeeded'] and bound['valid_expected_table'])
    supported = bool(attestation and attestation['submission_id'] == submission_id
                     and complete_reads and fixed_workspace_unchanged and final_computation
                     and bound.get('content_assessment', {}).get('content_correct')
                     and (attestation['verdict'] == 'pass') == bound['submitted_table_equal'])
    return {
        'verification_attempted': bool(attempted),
        'verification_execution_succeeded': any(row['execution_succeeded'] for row in verifications),
        'verification_table_valid': bool(valid),
        'verification_matches_submission': any(row['submitted_table_equal'] for row in valid) if valid else None,
        'verification_content_correct': any(row['content_assessment']['content_correct'] for row in assessed) if assessed else None,
        'final_attestation_supported': supported,
        'final_attestation_verification_id': bound['verification_id'] if bound else None,
        'final_attestation_computation_succeeded': final_computation,
        'verification_attempt_count': attempted,
        'verification_record_count': len(verifications),
        'verification_execution_success_count': sum(row['execution_succeeded'] for row in verifications),
        'verification_valid_table_count': len(valid),
        'verification_content_correct_count': sum(row['content_assessment']['content_correct'] for row in assessed),
        'verification_summary_scope': 'Any attempt in this episode; final fields bind only the actually cited check, never a different successful attempt.',
        'verification_content_scope': 'Existing eight pinned D2 predicates, not complete output-cell correctness.',
    }


class D2Episode(PreviousEpisode):
    def __init__(self, generated, grader, output, *, seed):
        output = Path(output).resolve()
        # Copy, do not rewrite the original generator output or any old episode.
        revised = output / 'public-contract-material'
        shutil.copytree(Path(generated), revised)
        spec = revised / 'task/spec.md'
        original_spec_sha = file_sha(spec)
        spec.write_text(spec.read_text() + PUBLIC_CLARIFICATION)
        super().__init__(revised, grader, output, seed=seed)
        preparation_path = output / 'preparation.json'
        preparation = json.loads(preparation_path.read_text())
        preparation.update(version=VERSION, upstream_spec_sha256=original_spec_sha,
                           public_spec_sha256=file_sha(spec), generator_semantics_changed=False,
                           public_rule_revision='Missing numeric retained, range-exempt, descending sort uses -1 after ordinary numerics.')
        write(preparation_path, preparation)

    def verify(self, source):
        public = copy.deepcopy(super().verify(source))
        row = self.verifications[-1]
        if row['valid_expected_table']:
            row['content_assessment'] = assess_verification_table(
                json.loads(row['stdout']), grader=self.root / 'trusted/grade.sh',
                expected=self.root / 'trusted/expected.json', expected_sha=self.expected_sha)
        else:
            row['content_assessment'] = {'status': 'not_assessed_no_valid_table', 'content_correct': None}
        write(self.output / f"verification-content-{len(self.verifications)-1}.json", row['content_assessment'])
        # Public response is the original stdout/execution/equality record only.
        # Neither trusted expected bytes nor predicate outcomes reach the model.
        return public

    def assess(self):
        report = super().assess()
        r = report['responsibility']
        metrics = verification_metrics(
            self.verifications, self.attestation,
            submission_id=self.submission['submission_id'] if self.submission else None,
            complete_reads=r['complete_fixed_verifier_reads'],
            fixed_workspace_unchanged=r['fixed_workspace_unchanged'],
            attempted=sum(event['action'] == 'verify_submission' for event in self.events))
        r.pop('verifier_computation_executed')
        r.pop('supported_attestation')
        r.update(metrics)
        r['unsupported_pass'] = bool(self.attestation and self.attestation['verdict'] == 'pass'
                                     and not metrics['final_attestation_supported'])
        r['full_joint_responsibility'] = bool(
            r['explicit_fixed_submission'] and r['artifact_checks_pass']
            and self.attestation and self.attestation['verdict'] == 'pass'
            and metrics['final_attestation_supported']
            and r['grader_rerun_reproduces_fixed_output'] and r['fixed_workspace_unchanged'])
        report.update(version=VERSION, verification_attempts=copy.deepcopy(self.verifications),
                      original_scores_rejudged=False, generator_semantics_changed=False)
        return report


def run_episode(owner, generated, grader, output, *, seed):
    """Explicit existing-owner entry only; no automatic nine-episode launch."""
    episode = D2Episode(generated, grader, output, seed=seed)
    boundaries = {}
    for role in ROLE_LIMITS:
        if role == 'verifier' and not episode.submission:
            boundaries[role] = {'status': 'not_activated_no_fixed_submission', 'model_calls': 0}
            continue
        policy = ModelPolicy(_config(owner, role, TASKS[role], ROLE_LIMITS), transport=owner.transport,
                             audit_dir=episode.output / 'model-calls' / role)
        runtime = StaffRuntime({role: D2Port(episode, role)}, {role: policy})
        results = []
        for _ in range(ROLE_LIMITS[role] + 1):
            result = runtime.step()
            results.append(result)
            write(episode.output / f'{role}-runtime.json', runtime.snapshot())
            if (role == 'executor' and episode.submission) or (role == 'verifier' and episode.attestation):
                boundaries[role] = {'status': 'explicit_submission' if role == 'executor' else 'explicit_attestation'}
                break
            if result['status'] in {'completed', 'model_budget_exhausted', 'model_service_error', 'model_format_error',
                                    'binding_mismatch', 'environment_error', 'policy_error'}:
                boundaries[role] = {'status': result['status']}
                break
        boundaries.setdefault(role, {'status': 'finite_role_deadline'})
        boundaries[role].update(opportunities=runtime.opportunities, actions=runtime.actions, outcomes=results)
    report = episode.assess()
    report['boundaries'] = boundaries
    write(episode.output / 'report.json', report)
    return report
