"""Read-only task-specific1724 qualification; official scoring is unchanged.

The original v162 gold/empty artifacts remain untouched. This module changes
only our extra admission requirement that the empty control must fail F2P.
Here the official added regression test is classified P2P, and it alone
separates gold from empty. Both raw test-group assignments and official resolved
values are retained. This module cannot launch Docker, model calls or a network.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path
import sys

from . import software_benchmark_scope_v162 as control_scope
from . import software_benchmark_grading_v162 as control_grading
from .software_benchmark_grading_v105 import environment_identity
from .software_benchmark_candidates_v054 import checked, reference

VERSION='v164-requests1724-official-regression-control-qualification-r1'
TASK='psf__requests-1724'
TARGET='test_requests.py::RequestsTestCase::test_unicode_method_name'
ROOT=control_scope.ROOT
OUTPUT=ROOT/'artifacts/software-benchmark-v164/requests1724-qualification-r1'
OVERLAY_FILE=OUTPUT/'qualified-overlay.json'
EVIDENCE_FILE=OUTPUT/'discrepancy-evidence.json'
DATASET=ROOT/'artifacts/software-benchmark-v054/source/trusted-evaluation.json'


def _load(ref):return json.loads(checked(ref).read_bytes())


def _sha(value):
    body=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    return hashlib.sha256(body).hexdigest()


def validate_discriminating_reports(instance,gold,empty):
    """No test or grouping is relabeled; require the one observed regression."""
    f2p,p2p=instance['FAIL_TO_PASS'],instance['PASS_TO_PASS']
    if (instance['instance_id']!=TASK or not isinstance(f2p,list) or not isinstance(p2p,list)
            or TARGET not in p2p or TARGET in f2p or len(f2p)!=6
            or len(f2p)!=len(set(f2p)) or len(p2p)!=len(set(p2p))):
        raise ValueError('1724 original sixF2P/P2P metadata differs')
    additions=[(n,line) for n,line in enumerate(instance['test_patch'].splitlines(),1)
               if line.startswith('+') and line[1:].strip()=='def test_unicode_method_name(self):']
    if len(additions)!=1 or '+++ b/test_requests.py' not in instance['test_patch']:
        raise ValueError('The discriminating test is not the unique official patch addition')
    for result in (gold,empty):
        if result.get('patch_successfully_applied') is not True or result.get('infra_failure') is not False:
            raise ValueError('Both official controls must execute without infrastructure failure')
        if result['tests_status']['FAIL_TO_PASS']!={'success':f2p,'failure':[]}:
            raise ValueError('Do not hide another F2P result or alter its original grouping')
    if (gold.get('resolved') is not True or empty.get('resolved') is not False
            or gold['tests_status']['PASS_TO_PASS']!={'success':p2p,'failure':[]}
            or empty['tests_status']['PASS_TO_PASS']!={'success':[test for test in p2p if test!=TARGET],
                                                     'failure':[TARGET]}):
        raise ValueError('Only the exact added Unicode regression may distinguish these controls')
    return {'instance_id':TASK,'target_test':TARGET,'official_patch_added_definition_line':additions[0][0],
        'official_patch_added_definition_text':additions[0][1],
        'gold_official_resolved':True,'empty_official_resolved':False,
        'gold_target_passed':True,'empty_target_failed':True,'target_original_group':'PASS_TO_PASS',
        'FAIL_TO_PASS_passed_in_both':list(f2p),'official_groups_unchanged':True,
        'official_resolved_rule_or_values_changed':False}


def _actual_control_validator(scoring):
    """Retain every original identity/cleanup/report check except the one gate."""
    source=inspect.getsource(control_grading.original.validate_qualification)
    begin=source.index('        if task in environment.TASKS:')
    end=source.index('        report = receipt["official_result"]',begin)
    source=source[:begin]+'''        environment.validate_control_environment(observed, identity)
        environment.validate_transport_evidence(receipt, quiet, observed, identity, folder)
'''+source[end:]
    old='            or not report.get("tests_status", {}).get("FAIL_TO_PASS", {}).get("failure")'
    if source.count(old)!=1:
        raise ValueError('The original extra F2P-only admission gate changed')
    replacement=('            or report.get("tests_status", {}).get("PASS_TO_PASS", {}).get("failure") != ['+repr(TARGET)+']\n'
                 '            or report.get("tests_status", {}).get("FAIL_TO_PASS", {}).get("failure") != []')
    source=source.replace(old,replacement)
    ns=dict(scoring.score_request.__globals__);compiled={}
    exec(compile(source,__file__+':only-1724-empty-control-gate','exec'),ns,compiled)
    return compiled['validate_qualification'],_sha(source.encode())


def build_evidence():
    plan_ref=reference(control_scope.PLAN_FILE);plan=_load(plan_ref)
    config=_load(plan['environments'][TASK]['configuration'])
    dataset_ref=reference(DATASET)
    if config['scorer_request_base']['dataset']!=dataset_ref:
        raise ValueError('Controls are not tied to the exact trusted official dataset')
    instance=next(row for row in _load(dataset_ref) if row['instance_id']==TASK)
    manifest_ref=reference(control_scope.COORDINATOR_ROOT/'scorer-manifest.json')
    scoring=control_grading.scorer(control_scope.dispatch_view(control_scope.require_grading_allowed),
                                  manifest_provider=lambda:_load(manifest_ref))
    validator,validator_sha=_actual_control_validator(scoring)
    proposal_ref=reference(control_scope.COORDINATOR_ROOT/'qualifications'/(TASK+'-proposal.json'))
    proposal=validator(proposal_ref,config,plan_ref)
    records={};reports={};identities={}
    for control in proposal['controls']:
        kind=control['patch_kind'];receipt=_load(control['receipt']);identity=_load(receipt['identity'])
        report=receipt['official_result'][1][TASK]
        folder=Path(control['initial_container']['path']).parent
        report_files=list(folder.rglob('report.json'));outputs=list(folder.rglob('test_output.txt'))
        if len(report_files)!=1 or len(outputs)!=1 or _load(reference(report_files[0]))[TASK]!=report:
            raise ValueError('Original official report file and retained receipt differ')
        expected_patch=instance['patch'].encode() if kind=='gold' else b''
        if identity.get('patch_sha256')!=_sha(expected_patch) or identity.get('patch_bytes')!=len(expected_patch):
            raise ValueError('Control prediction bytes differ from exact gold/empty')
        records[kind]={**copy.deepcopy(control),'identity':receipt['identity'],
            'official_report':reference(report_files[0]),'official_test_output':reference(outputs[0]),
            'transport':receipt['transport_result'],'official_resolved':report['resolved'],
            'actual_test_counts':{group:{bucket:len(items) for bucket,items in result.items()}
                                 for group,result in report['tests_status'].items()}}
        reports[kind]=report;identities[kind]=identity
    if set(reports)!={'gold','empty'}:
        raise ValueError('Exactly the original two controls are required')
    common=('image','dataset','baseline_mapping','scorer_manifest','limits','environment_revision','network_resolution')
    if any(identities['gold'].get(key)!=identities['empty'].get(key) for key in common):
        raise ValueError('Gold and empty used different actual scoring environments')
    difference=validate_discriminating_reports(instance,reports['gold'],reports['empty'])
    empty_text=checked(records['empty']['official_test_output']).read_text()
    if ('UnicodeDecodeError' not in empty_text or "method=u'POST'" not in empty_text
            or '/python2.7/httplib.py' not in empty_text):
        raise ValueError('The empty failure lacks actual original Unicode/Python2 execution evidence')
    return {'version':VERSION,'instance_id':TASK,'read_only':True,'passed':True,
        'official_dataset':dataset_ref,'source_control_plan':plan_ref,'source_control_manifest':manifest_ref,
        'original_qualification_proposal':proposal_ref,
        'original_qualification_rejection':reference(control_scope.COORDINATOR_ROOT/'environment-result.json'),
        'original_qualification_artifacts_changed':False,'actual_environment_identity':environment_identity(config),
        'environment_revision':identities['gold']['environment_revision'],
        'network_resolution':identities['gold']['network_resolution'],
        'official_metadata':{'FAIL_TO_PASS':instance['FAIL_TO_PASS'],'PASS_TO_PASS':instance['PASS_TO_PASS'],
            'FAIL_TO_PASS_sha256':_sha(instance['FAIL_TO_PASS']),
            'PASS_TO_PASS_sha256':_sha(instance['PASS_TO_PASS']),
            'list_hash_encoding':'UTF-8 canonical JSON; list order retained',
            'test_patch_sha256':_sha(instance['test_patch'].encode()),
            'test_patch_bytes':len(instance['test_patch'].encode())},
        'controls':records,'discriminating_regression':difference,
        'empty_failure_type':'UnicodeDecodeError in original Python2.7 httplib handling Unicode POST method',
        'qualification_gate_change':{'scope':TASK,'former_extra_requirement':'empty must contain FAIL_TO_PASS failure',
            'new_requirement':'gold official resolved=True; empty official resolved=False solely at the exact official added Unicode test; both complete under the same verified environment',
            'official_test_grouping_changed':False,'official_test_patch_changed':False,
            'official_resolved_or_candidate_selection_changed':False,
            'reason':'The official patch-added discriminating test is in the original PASS_TO_PASS metadata'},
        'new_control_validator_source_sha256':validator_sha,
        'model_calls':0,'Docker_operations':0,'new_network_connections':0,
        'root_instruction':'Task-specific interpretation explicitly approved; no new model/scoring run or budget expansion'}


def qualified_overlay(evidence=None):
    if evidence is None:
        evidence=build_evidence()
    return {'version':VERSION,'instance_id':TASK,'status':'qualified','passed':True,
        'evidence':reference(EVIDENCE_FILE),'source_control_plan':evidence['source_control_plan'],
        'source_control_manifest':evidence['source_control_manifest'],
        'actual_environment_identity':evidence['actual_environment_identity'],
        'environment_revision':evidence['environment_revision'],'network_resolution':evidence['network_resolution'],
        'gold_official_resolved':True,'empty_official_resolved':False,'target_test':TARGET,
        'task_specific_extra_gate_exception':True,'official_scoring_unchanged':True,
        'new_model_or_scoring_calls':0,'grants_Docker_or_network_permission':False}


def prepare():
    evidence=build_evidence()
    evidence_ref=control_scope.retain(EVIDENCE_FILE,evidence)
    overlay=qualified_overlay(evidence)
    return {'evidence':evidence_ref,'qualified_overlay':control_scope.retain(OVERLAY_FILE,overlay),
            'new_model_calls':0,'new_controls':0,'Docker_operations':0}


def validate_qualification(ref,config,plan_ref):
    """Future scorer seam: validate evidence and bind to the same exact task/env."""
    evidence=build_evidence()
    if Path(ref['path']).resolve()!=OVERLAY_FILE.resolve() or _load(ref)!=qualified_overlay(evidence):
        raise ValueError('Only the exact new1724 task-specific qualification overlay is admitted')
    if _load(reference(EVIDENCE_FILE))!=evidence:
        raise ValueError('The original controls or metadata discrepancy evidence changed')
    plan=_load(plan_ref)
    if config.get('instance_id')!=TASK or TASK not in plan.get('environments',{}):
        raise ValueError('This proof cannot qualify another task or unplanned dataset')
    expected=_load(plan['environments'][TASK]['configuration'])
    identity=_load(ref)['actual_environment_identity']
    if environment_identity(config)!=identity or environment_identity(expected)!=identity:
        raise ValueError('1724 image/dataset/baseline/official scoring inputs changed')
    return {**_load(ref),'target_plan':plan_ref,'target_environment_exact':True}


def bind_qualification(existing):
    """Bind only a new private scorer object; never mutate a running module/file."""
    if sys.modules.get(getattr(existing,'__name__',None)) is existing:
        raise ValueError('Use a newly constructed private scorer namespace')
    ns=existing.score_request.__globals__;original=existing.validate_qualification
    def validate(ref,config,plan_ref):
        if config.get('instance_id')==TASK and _load(ref).get('version')==VERSION:
            proof=validate_qualification(ref,config,plan_ref)
            fields=existing.environment.request_fields(TASK)
            if fields!={k:proof[k] for k in ('environment_revision','network_resolution')}:
                raise ValueError('The future scorer must reuse the exact qualified1724 provider')
            return proof
        return original(ref,config,plan_ref)
    ns['validate_qualification']=validate
    existing.validate_qualification=validate
    return existing
