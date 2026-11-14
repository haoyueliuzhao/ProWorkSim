"""Strict r2-gold plus new r3-empty composition; no transport reinterpretation.

The existing validator's complete per-control body is preserved. Only the
container-plan namespace and single-component cardinality are parameterized;
this module separately requires exactly the predeclared gold/empty pair.
"""
import ast
import inspect
from pathlib import Path
from . import software_benchmark_grading_v105 as base
from . import software_benchmark_grading_v203_2_3 as initial
from . import software_benchmark_grading_v203_2_3_r2 as gold_scoring
from . import software_benchmark_grading_v203_2_3_r3 as empty_scoring
from . import software_benchmark_preparation_grading_v203_2_3_r2 as gold_scope
from . import software_benchmark_preparation_grading_v203_2_3_r3 as empty_scope
from . import software_benchmark_scope_v203_2_3 as formal_scope
from . import software_benchmark_environment_v203_2_3_r2 as environment
from .software_benchmark_candidates_v054 import reference

VERSION='v203.2.3-strict-empty-recovery-qualification-r3'
TASK=environment.TASK
OUT=formal_scope.ARTIFACT_ROOT/'grading-empty-recovery-r3'
QUALIFICATION=gold_scope.COORDINATOR_ROOT/'qualifications'/(TASK+'.json')
KINDS={'gold':(gold_scoring,gold_scope,'control-r2-'),
       'empty':(empty_scoring,empty_scope,'control-r3-')}
SEMANTIC_FIELDS=(*initial.RUNTIME_FIELDS,'adapter','environment_adapter','profile','scoring_CA_profile')


def component_source(prefix):
    if prefix not in ('control-r2-','control-r3-'):raise ValueError('Undeclared control namespace')
    original=inspect.getsource(base.original.validate_qualification)
    importer='from .software_benchmark_grading_qualification_v060 import validate_transport_evidence'
    count='len(value.get("controls", [])) != 2'
    key='"control-" + task + "-" + kind'
    if any(original.count(item)!=1 for item in (importer,count,key)):
        raise ValueError('Frozen component validation seam changed')
    changed=original.replace(importer,
        'from .software_benchmark_environment_v203_2_3_r2 import validate_transport_evidence')
    changed=changed.replace(count,'len(value.get("controls", [])) != 1')
    changed=changed.replace(key,repr(prefix)+' + task + "-" + kind')
    # Reverse these three administrative edits and verify the full AST.
    restored=changed.replace('from .software_benchmark_environment_v203_2_3_r2 import validate_transport_evidence',importer)
    restored=restored.replace('len(value.get("controls", [])) != 1',count)
    restored=restored.replace(repr(prefix)+' + task + "-" + kind',key)
    if ast.dump(ast.parse(restored),include_attributes=False)!=ast.dump(ast.parse(original),include_attributes=False):
        raise ValueError('A substantive per-control validation rule changed')
    return changed


def component_document(kind):
    scoring,scope,prefix=KINDS[kind]
    folder=scope.GRADING_ROOT/(prefix+TASK+'-'+kind)
    return {'version':scoring.VERSION,'instance_id':TASK,'passed':True,
        'plan':reference(scope.CONTROL_PLAN_FILE),'model_calls':0,
        'document_kind':'one strictly validated control component, not pair qualification',
        'controls':[{'patch_kind':kind,**{key:reference(folder/(key+'.json'))
            for key in ('receipt','quiescence','completion')},
            'initial_container':reference(folder/'official-output/initial-container.json')}]}


def validate_component(kind,ref,config):
    if kind not in KINDS:raise ValueError('Unexpected control kind')
    scoring,scope,prefix=KINDS[kind]
    supplied=formal_scope.load(ref)
    if supplied!=component_document(kind):raise ValueError('Control component provenance changed')
    value=scoring.scorer(scope.dispatch_view())
    namespace=value.validate_request.__globals__
    namespace=dict(namespace)
    compiled={}
    exec(compile(component_source(prefix),__file__+':unchanged-control-body','exec'),namespace,compiled)
    checked=compiled['validate_qualification'](ref,config,reference(scope.CONTROL_PLAN_FILE))
    if checked['controls'][0]['patch_kind']!=kind:raise ValueError('Gold/empty roles were interchanged')
    return checked


def equivalence():
    refs={kind:reference(scope.COORDINATOR_ROOT/'scorer-manifest.json')
          for kind,(_,scope,_) in KINDS.items()}
    manifests={kind:formal_scope.load(ref) for kind,ref in refs.items()}
    if any(manifests['gold'].get(key)!=manifests['empty'].get(key) for key in SEMANTIC_FIELDS):
        raise ValueError('Official scoring code, dependency, resource or environment semantics changed')
    identities={}
    for kind,(_,scope,prefix) in KINDS.items():
        receipt=formal_scope.load(reference(scope.GRADING_ROOT/(prefix+TASK+'-'+kind)/'receipt.json'))
        identities[kind]=formal_scope.load(receipt['identity'])
    if identities['gold']['network_resolution']!=identities['empty']['network_resolution'] or identities['gold']['network_resolution']!=reference(environment.RESOLUTION):
        raise ValueError('Recovery changed the frozen endpoint')
    envs={kind:formal_scope.load(value['environment_revision']) for kind,value in identities.items()}
    if envs['gold']!=envs['empty']:raise ValueError('Recovery environment manifests differ')
    for key in ('dataset','image','baseline_mapping','limits'):
        if identities['gold'][key]!=identities['empty'][key]:raise ValueError('Control input identity changed: '+key)
    return {'scorer_manifests':refs,'unchanged_fields':list(SEMANTIC_FIELDS),
        'environment_manifests_exactly_equal':True,'network_resolution':reference(environment.RESOLUTION),
        'official_scorer_source':reference(base.original.__file__),
        'complete_per_control_validation_body_unchanged':True}


def expected_qualification():
    plan_ref=reference(formal_scope.PLAN_FILE)
    plan=formal_scope.validate_plan(formal_scope.load(plan_ref))
    config=formal_scope.load(plan['environments'][TASK]['configuration'])
    refs={kind:reference(OUT/'components'/(kind+'.json')) for kind in ('gold','empty')}
    for kind,ref in refs.items():validate_component(kind,ref,config)
    same=equivalence()
    return {'version':VERSION,'instance_id':TASK,'passed':True,'plan':plan_ref,
        'configuration':plan['environments'][TASK]['configuration'],'components':refs,
        'equivalence':same,'profile':reference(environment.RESOLUTION),
        'CA_profile':reference(formal_scope.CA_PROFILE_FILE),'model_calls':0,
        'gold_reexecuted':False,'new_empty_control_identity':'control-r3-'+TASK+'-empty',
        'prior_unknown_empty_preserved':reference(gold_scope.GRADING_ROOT/('control-r2-'+TASK+'-empty')/'receipt.json'),
        'idle_timeout_reclassified':False,'transport_gate_relaxed':False,'source':reference(__file__)}


def validate_qualification(ref,config,plan_ref):
    if plan_ref!=reference(formal_scope.PLAN_FILE) or Path(ref['path']).resolve()!=QUALIFICATION:
        raise ValueError('Recovery qualification requires its original formal plan and unique unconsumed target')
    plan=formal_scope.load(plan_ref)
    if config!=formal_scope.load(plan['environments'][TASK]['configuration']):
        raise ValueError('Recovery requires the exact original canonical task environment')
    expected=expected_qualification()
    if formal_scope.load(ref)!=expected:raise ValueError('Recovery pair proof changed')
    return expected


def qualify():
    for kind in ('gold','empty'):
        formal_scope.retain(OUT/'components'/(kind+'.json'),component_document(kind))
    value=expected_qualification()
    return formal_scope.retain(QUALIFICATION,value)
