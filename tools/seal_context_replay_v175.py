"""Seal P0/P1 inputs and the local Python dependency closure before paid replay."""
import ast
import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.software_context_runtime_v175 import managed_actor,public_file_bindings
from proworksim import software_benchmark_managed_actor_v141 as old_actor
from proworksim import software_benchmark_public_test_evidence_v175 as evidence

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'runs/software-benchmark-v175/context-replay-r1'
OUT=ROOT/'artifacts/software-benchmark-v175/p0-gate-r2'


def closure(seeds):
    pending=list(seeds);seen=set()
    while pending:
        path=pending.pop().resolve()
        if path in seen:continue
        seen.add(path)
        if path.suffix!='.py':continue
        package=(['proworksim'] if path.parent==ROOT/'src/proworksim' else [])
        for node in ast.walk(ast.parse(path.read_text())):
            names=[]
            if isinstance(node,ast.Import):names=[alias.name for alias in node.names]
            elif isinstance(node,ast.ImportFrom):
                prefix=(package[:len(package)-node.level+1] if node.level else [])
                base=prefix+(node.module.split('.') if node.module else [])
                names=['.'.join(base),*['.'.join(base+[a.name]) for a in node.names]]
            for name in names:
                if not name.startswith('proworksim'):continue
                candidate=ROOT/'src'/Path(*name.split('.'))
                if candidate.with_suffix('.py').is_file():pending.append(candidate.with_suffix('.py'))
                elif (candidate/'__init__.py').is_file():pending.append(candidate/'__init__.py')
    return [reference(p) for p in sorted(seen)]


def main():
    if (RUN/'api-ledger.sqlite').exists():raise ValueError('Do not reseal after paid work has started')
    OUT.mkdir(parents=True,exist_ok=True)
    actor=managed_actor()
    assert actor.ManagedOperationSession.execute.__globals__['run_public_entry'] is evidence.run_public_entry
    assert old_actor.ManagedOperationSession.execute.__globals__['run_public_entry'] is not evidence.run_public_entry
    file_bindings=public_file_bindings()
    cpu={
        'public_test_and_delivery':('/tmp/proworksim-v175-repair-tests-r2.log',5),
        'context_views':('/tmp/proworksim-v175-view-tests-r2.log',4),
        'cash_admission':('/tmp/proworksim-v175-cash-tests.log',3),
        'actual_replay_entry_and_changed_retry':('/tmp/proworksim-v175-entry-tests.log',3),
    }
    controls={}
    for name,(filename,count) in cpu.items():
        text=Path(filename).read_text()
        if f'{count} passed' not in text:raise ValueError('A required targeted CPU control did not pass')
        controls[name]={'log':reference(filename),'result':text.strip().splitlines()[-1]}
    corpus=json.loads((ROOT/'artifacts/software-benchmark-v175/p0-corpus-r1/summary.json').read_bytes())
    flask=json.loads((ROOT/'artifacts/software-benchmark-v175/flask-public-control-r1/summary.json').read_bytes())
    views=json.loads((ROOT/'artifacts/software-benchmark-v175/offline-comparison-r2/summary.json').read_bytes())
    assert corpus['counts']['requests']==5523 and corpus['local_unknown_fraction']<=.02
    assert flask['passed'] and views['exact_recall_controls_passed']
    tests=[reference(p) for p in sorted((ROOT/'tests').glob('test_context_*v175.py'))]
    gate={'admitted_stage':'P1 fixed-decision API replay only','passed':True,
        'estimated_source_accounting_only':True,'new_full_task_or_multiagent_episodes':0,
        'CPU_controls':controls,'unique_CPU_tests':14,'one_changed_retry_test_repeated':True,'test_sources':tests,
        'actual_flask_control':reference(ROOT/'artifacts/software-benchmark-v175/flask-public-control-r1/summary.json'),
        'flask_cleanup':reference(ROOT/'artifacts/software-benchmark-v175/flask-public-control-r1/cleanup.json'),
        'corpus':reference(ROOT/'artifacts/software-benchmark-v175/p0-corpus-r1/summary.json'),
        'future_runtime_binding_checked':True,'frozen_original_actor_mutated':False,'public_files':file_bindings,
        'method_revision':'source-aware-r2-before-first-paid-call',
        'method_revision_reason':'Mask older user-role JSON environment observations as well as tool messages; points unchanged',
        'M2_selection_unit':'complete_original_environment_or_tool_observation',
        'M2_is_query_conditioned':False,'M3_maximum_core_summary_points':33,
        'r1_sampling_plan_is_immutable':True,'r1_tool_only_method_views_are_preparation_history':True,
        'new_API_budget_CNY':250,'cash_admission_only':True,
        'protocol':reference(ROOT/'docs/experiments/software-benchmark-v175-context-compression-protocol.md')}
    gate_ref=write_new(OUT/'decision.json',gate)
    seeds=[ROOT/'tools/run_context_replay_v175.py',Path(__file__),
        *(ROOT/'src/proworksim').glob('*v175.py'),*(ROOT/'tools').glob('*v175.py')]
    files=closure(seeds)
    source={'version':'v175-frozen-context-replay-runtime-r2','files':files,
        'plan':reference(RUN/'plan.json'),
        'views':reference(ROOT/'artifacts/software-benchmark-v175/offline-comparison-r2/summary.json'),
        'gate':gate_ref,'authority':reference(ROOT/'artifacts/software-benchmark-v175/user-amendment-r1/authorization.json'),
        'tokenizer':reference(ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'),
        'no_dynamic_shared_host_operations':True}
    ref=write_new(RUN/'runtime-sources.json',source)
    write_new(OUT/'runtime-sources.json',source)
    print(json.dumps({'sealed':True,'runtime_sources':ref,'source_files':len(files),'gate':gate_ref}))


if __name__=='__main__':main()
