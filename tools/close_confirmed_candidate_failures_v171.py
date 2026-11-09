"""Resolve two overbroad unknown labels from existing real official executions.

No test/model re-execution, patch edit, score change or environment mutation.
The original official false result and its advisory infra flag remain intact.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference,checked,write_new

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v171/confirmed-candidate-failures-r1'
CASES=((161,'independent-technical-recovery-r1',16100,'astropy/units/format/cds.py'),
       (169,'communication-wave2-r2',15745,'seaborn/_core/scales.py'))


def read(ref):return json.loads(checked(ref).read_bytes())


def inspect(version,directory,index,changed_path):
    root=ROOT/f'runs/software-benchmark-v{version}/{directory}'
    folder=root/f'grading/score-{index}'
    request_ref=reference(folder/'request.json');request=read(request_ref)
    receipt_ref=reference(folder/'receipt.json');receipt=read(receipt_ref)
    identity=read(receipt['identity']);lock=read(request['candidate_lock'])
    patch_ref=lock['patch_receipt']['patch'];patch=checked(patch_ref).read_bytes()
    task=request['instance_id'];official=receipt['official_result'][1][task]
    qualification=read(request['qualification'])
    if (identity['request']!=request_ref or identity['candidate_lock']!=request['candidate_lock']
        or identity['patch_sha256']!=hashlib.sha256(patch).hexdigest()
        or official.get('resolved') is not False or official.get('infra_failure_reason')!='network_unreachable'
        or receipt['status']!='technical_unknown' or qualification.get('passed') is not True
        or lock.get('lock_before_grading') is not True or lock['patch_receipt']['round_trip_verified'] is not True):
        raise ValueError('Original request, candidate, official false result or environment evidence differs')
    modifications=lock['patch_receipt']
    if (modifications['modified_paths']!=[changed_path] or modifications['added_paths']
            or modifications['deleted_paths']):
        raise ValueError('The diagnosis requires the exact single-file frozen candidate')
    original=read(lock['baseline']);candidate=read(lock['candidate'])
    before=original['files'][changed_path];after=candidate['files'][changed_path]
    logs=list((folder/'official-output/logs/run_evaluation').glob('*/*/*/test_output.txt'))
    if len(logs)!=1:raise ValueError('The exact real test output is ambiguous')
    output=logs[0].read_text();execution=logs[0].with_name('run_instance.log')
    execution_text=execution.read_text()
    applied_input=logs[0].with_name('patch.diff')
    if ('>>>>> Start Test Output' not in output or '>>>>> Applied Patch:' not in execution_text
            or applied_input.read_bytes()!=patch
            or f'Applied patch {changed_path} cleanly.' not in execution_text):
        raise ValueError('The actual evaluator did not prove application and test invocation')
    if index==16100:
        classes=lambda text:[n.name for n in ast.parse(text).body if isinstance(n,ast.ClassDef)]
        module='astropy/units/format/__init__.py'
        if (classes(before)!=['CDS'] or 'CDS' in classes(after) or 'Cds' not in classes(after)
            or original['files'][module]!=candidate['files'][module]
            or not any(isinstance(n,ast.ImportFrom) and n.module=='cds' and any(a.name=='CDS' for a in n.names)
                       for n in ast.parse(candidate['files'][module]).body)
            or "ImportError: cannot import name 'CDS'" not in output):
            raise ValueError('The exact introduced CDS import failure was not established')
        cause='Required CDS export renamed to Cds while the unchanged importer still requires CDS'
        evidence={'original_classes':classes(before),'candidate_classes':classes(after),
            'actual_exception':"ImportError: cannot import name 'CDS'"}
    else:
        field_calls=lambda text:[n.lineno for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Call)
            and isinstance(n.func,ast.Name) and n.func.id=='field']
        if (field_calls(before) or field_calls(after)!=[158]
            or after.splitlines()[157].strip()!='_pipeline: Pipeline = field(default_factory=list)'
            or 'seaborn/_core/scales.py:158: in Nominal' not in output
            or "E   NameError: name 'field' is not defined" not in output):
            raise ValueError('The exact introduced field NameError was not established')
        cause='Candidate introduced field(default_factory=list) without defining/importing field'
        evidence={'introduced_call_lines':field_calls(after),'actual_exception':"NameError: name 'field' is not defined"}
    delivery_ref=reference(root/f'grading-coordinator/delivery-endpoints/{index}.json')
    delivery=read(delivery_ref)
    # Delivery was independently recorded before this classification; do not
    # infer its state from a different terminal workspace version.
    if delivery.get('status')!='no_legal_delivery' or delivery.get('resolved') is not False:
        raise ValueError('The prior independent delivery endpoint changed')
    original_slot=lock['slot']['slot_id'].split(':independent-technical-recovery-r1')[0]
    return {'slot_index':index,'instance_id':task,'original_slot_id':original_slot,
        'attempt_slot_id':lock['slot']['slot_id'],'status':'confirmed_candidate_execution_failure',
        'R_code':False,'R_delivery':False,'score_authority':'original_official_resolved_false',
        'per_test_status_available':False,'cause':cause,'evidence':evidence,
        'request':request_ref,'original_receipt':receipt_ref,'candidate_lock':request['candidate_lock'],
        'qualification':request['qualification'],'test_output':reference(logs[0]),
        'actual_applied_patch_log':reference(execution),'prior_delivery_endpoint':delivery_ref,
        'actual_applied_patch_input':reference(applied_input),
        'candidate_file_sha256':hashlib.sha256(after.encode()).hexdigest(),
        'original_infra_advisory_preserved':True,'original_resolved_value_changed':False,
        'model_calls':0,'new_test_executions':0,'Docker_operations':0,'candidate_changed':False}


def main():
    grading=ROOT/'runs/software-benchmark-v054/scorer-venv/lib/python3.12/site-packages/swebench/harness/grading.py'
    infra=grading.with_name('infra_failure.py')
    if 'Advisory only -- `resolved` stays False' not in grading.read_text() or 'It is advisory.' not in infra.read_text():
        raise ValueError('The installed official advisory semantics require review')
    rows=[inspect(*case) for case in CASES]
    OUT.mkdir(parents=True,exist_ok=True)
    value={'version':'v171-confirmed-existing-candidate-failure-classification-r1','rows':rows,
        'official_advisory_semantics':[reference(grading),reference(infra)],
        'official_reports_rewritten':False,'actual_tests_already_executed':True,
        'normal_official_per_test_report_fabricated':False,'new_API_cost_CNY':0,
        'model_calls':0,'new_test_executions':0,'Docker_operations':0,
        'interpretation':'The project unknown label is corrected using exact candidate-induced failures observed by actual official test execution; official resolved=false is unchanged.'}
    result=write_new(OUT/'canonical-overlay.json',value)
    print(json.dumps({'overlay':result,'confirmed_code_failures':len(rows),'model_calls':0,'new_test_executions':0}))


if __name__=='__main__':main()
