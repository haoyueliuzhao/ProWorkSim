"""Read-only adjudication of one proven candidate-caused collection failure.

The official report is retained verbatim. Its `patch_successfully_applied`
field also covers missing parseable test output; it is not direct git-apply
telemetry. This narrow predicate does not change the candidate or evaluator.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re

from .software_benchmark_candidates_v054 import checked, reference, changed_paths
from .software_benchmark_native_artifact_v054 import decode_native_entry
from .storage import digest

VERSION = 'v122-proven-candidate-collection-failure-adjudication-r1'
TASK = 'pylint-dev__pylint-4604'
PATH = 'pylint/checkers/variables.py'
PATCH_SHA256 = '53b4056f0cf756280287a704ef591e97bc418bd744f1d08c9aa069a7761f8565'
ASSIGNMENT = 'SPECIAL_OBJ'


def load(ref):
    return json.loads(checked(ref).read_bytes())


def missing_binding_evidence(before, after):
    """Only inspect the exact original static import/assignment pattern."""
    baseline, candidate = ast.parse(before), ast.parse(after)
    def locate(module):
        matches = [node for node in module.body if isinstance(node, ast.Assign)
                   and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                   and node.targets[0].id == ASSIGNMENT]
        if len(matches) != 1:
            raise ValueError('The exact failing top-level assignment is required')
        return matches[0]
    old, new = locate(baseline), locate(candidate)
    value = new.value
    if (ast.dump(old.value) != ast.dump(value) or not isinstance(value, ast.Call)
            or not isinstance(value.func, ast.Attribute) or value.func.attr != 'compile'
            or not isinstance(value.func.value, ast.Name) or value.func.value.id != 're'
            or len(value.args) != 1 or not isinstance(value.args[0], ast.Constant)
            or not isinstance(value.args[0].value, str) or value.keywords):
        raise ValueError('The original harmless re.compile literal expression changed')
    prefix = candidate.body[:candidate.body.index(new)]
    for node in prefix:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.Import):
            names = [item.asname or item.name.split('.')[0] for item in node.names]
        elif isinstance(node, ast.ImportFrom) and all(item.name != '*' for item in node.names):
            names = [item.asname or item.name for item in node.names]
        else:
            raise ValueError('Dynamic or ambiguous preceding code cannot establish an unbound import')
        if 're' in names:
            raise ValueError('The candidate still defines the alleged missing import')
    if not any(isinstance(node, ast.Import) and any(item.name == 're' and item.asname in (None, 're')
               for item in node.names) for node in baseline.body[:baseline.body.index(old)]):
        raise ValueError('The baseline did not define the claimed missing import')
    expression = ast.Expression(body=value)
    compiled = compile(ast.fix_missing_locations(expression), '<bound-literal-expression>', 'eval')
    try:
        eval(compiled, {'__builtins__': {}})
    except NameError as error:
        if str(error) != "name 're' is not defined":
            raise ValueError('The isolated expression failed for another reason') from error
    else:
        raise ValueError('The isolated expression did not reproduce the recorded missing symbol')
    pattern = eval(compiled, {'__builtins__': {}, 're': re})
    if not isinstance(pattern, re.Pattern):
        raise ValueError('The baseline import did not satisfy the same literal expression')
    return {'path': PATH, 'candidate_line': new.lineno, 'unbound_symbol': 're',
        'exception_type': 'NameError', 'exception_message': "name 're' is not defined",
        'baseline_import_present': True, 'candidate_import_absent': True,
        'literal_assignment_expression_unchanged': True,
        'isolated_expression_reproduced': True, 'whole_candidate_module_executed_on_host': False,
        'baseline_lines': len(before.splitlines()), 'candidate_lines': len(after.splitlines())}


def derive_resolution(request_ref, cpu_proof_ref):
    request, proof = load(request_ref), load(cpu_proof_ref)
    if (request.get('instance_id') != TASK or request.get('resource_key') != 'score-8039'
            or proof.get('version') != VERSION or proof.get('passed') is not True
            or proof.get('request') != request_ref or proof.get('candidate_lock') != request['candidate_lock']
            or proof.get('exact_patch_application_verified') is not True
            or proof.get('candidate_bytes_changed') is not False):
        raise ValueError('Only the exact original request and its completed CPU proof may be adjudicated')
    folder = Path(request['directory'])
    if Path(request_ref['path']).resolve() != (folder/'request.json').resolve():
        raise ValueError('The original request is outside its own scoring directory')
    receipt_ref = reference(folder/'receipt.json')
    receipt = load(receipt_ref)
    identity = load(receipt['identity'])
    completion, quiet = load(reference(folder/'completion.json')), load(reference(folder/'quiescence.json'))
    lock = load(request['candidate_lock'])
    raw_patch = checked(lock['patch_receipt']['patch']).read_bytes()
    if (digest(raw_patch) != PATCH_SHA256 or identity.get('patch_sha256') != PATCH_SHA256
            or identity.get('request') != request_ref or identity.get('candidate_lock') != request['candidate_lock']
            or receipt.get('slot_id') != request['slot_id'] or receipt.get('instance_id') != TASK
            or lock['slot']['slot_id'] != request['slot_id'] or lock.get('lock_before_grading') is not True
            or lock.get('endpoint') != 'terminal_code' or lock['patch_receipt'].get('round_trip_verified') is not True
            or proof.get('original_patch') != lock['patch_receipt']['patch']):
        raise ValueError('Candidate provenance or immutable patch bytes differ')
    if (receipt.get('status') != 'technical_unknown' or receipt.get('candidate_changed') is not False
            or receipt.get('actor_feedback') is not False or receipt.get('model_calls') != 0
            or completion.get('returncode') != 0 or quiet.get('quiescent') is not True
            or quiet.get('cleanup_errors') != [] or quiet.get('create_result_unknown') is not False
            or quiet.get('deadline_reached') is not False):
        raise ValueError('Interrupted scoring or uncertain cleanup cannot become a model failure')
    official = receipt.get('official_result')
    if not isinstance(official, list) or len(official) != 2 or official[0] != TASK:
        raise ValueError('The original official report is absent')
    report = official[1].get(TASK, {})
    required = {'patch_is_None': False, 'patch_exists': True,
                'patch_successfully_applied': False, 'resolved': False, 'infra_failure': False}
    if any(report.get(key) is not value for key, value in required.items()):
        raise ValueError('The original report is not the narrow unresolved, non-infra no-results case')
    before, after = load(lock['baseline']), load(lock['candidate'])
    if changed_paths(before, after) != {'added_paths': [], 'deleted_paths': [], 'modified_paths': [PATH]}:
        raise ValueError('Only the one exact code modification has been causally inspected')
    base_bytes = decode_native_entry(PATH, before['files'][PATH], before['entry_metadata'][PATH])
    candidate_bytes = decode_native_entry(PATH, after['files'][PATH], after['entry_metadata'][PATH])
    if (proof.get('baseline_file_sha256') != digest(base_bytes)
            or proof.get('candidate_file_sha256') != digest(candidate_bytes)
            or proof.get('applied_file_sha256') != digest(candidate_bytes)):
        raise ValueError('The CPU patch application does not reach the original locked file')
    missing = missing_binding_evidence(base_bytes.decode('utf-8'), candidate_bytes.decode('utf-8'))
    if proof.get('missing_binding') != missing:
        raise ValueError('The proof no longer describes this exact missing import')
    logs = folder/'official-output/logs/run_evaluation'/receipt['run_id']/request['resource_key']/TASK
    if (logs/'patch.diff').read_bytes() != raw_patch:
        raise ValueError('The grader did not receive the exact original patch')
    run_log = (logs/'run_instance.log').read_text()
    output = (logs/'test_output.txt').read_text()
    expected_trace = f'{PATH}:{missing["candidate_line"]}: in <module>'
    if ('>>>>> Applied Patch:' not in run_log or f'Applied patch {PATH} cleanly.' not in run_log
            or '>>>>> Patch Apply Failed' in run_log or '>>>>> Failed to Apply Patch' in run_log
            or expected_trace not in output or 'E   NameError: '+missing['exception_message'] not in output
            or "ImportError while loading conftest '/testbed/tests/conftest.py'" not in output
            or '>>>>> Start Test Output' not in output or '>>>>> End Test Output' not in output
            or '>>>>> Test Exit Code: 4' not in output):
        raise ValueError('Actual official execution does not prove this candidate-caused collection failure')
    if (proof.get('official_no_parseable_tests_reproduced') is not True
            or proof.get('official_log') != reference(logs/'test_output.txt')):
        raise ValueError('The official parser behavior was not bound to this original test log')
    checked(proof['official_parser_source'])
    return {'version': VERSION, 'status': 'adjudicated_candidate_code_failure', 'resolved': False,
        'instance_id': TASK, 'slot_id': request['slot_id'], 'resource_key': request['resource_key'],
        'original_request': request_ref, 'original_receipt': receipt_ref, 'candidate_lock': request['candidate_lock'],
        'original_status': 'technical_unknown', 'original_report': report,
        'original_report_changed': False, 'candidate_bytes_changed': False,
        'actual_patch_application_succeeded': True, 'candidate_caused_collection_failure': True,
        'cause': missing, 'evidence': {'CPU_proof': cpu_proof_ref,
            'run_instance_log': reference(logs/'run_instance.log'), 'test_output': reference(logs/'test_output.txt'),
            'completion': reference(folder/'completion.json'), 'quiescence': reference(folder/'quiescence.json')},
        'prior_explanation_corrected': 'The patch applied; patch_successfully_applied=false also encoded missing parseable test output. Calling it a patch-transfer/application failure was incorrect.',
        'measurement_revision_only': True, 'official_scoring_rerun': False,
        'new_gold_empty_controls_needed': False, 'new_candidate_scoring_needed': False,
        'model_calls': 0, 'Docker_operations': 0, 'official_tests_executed_by_adjudicator': 0}
