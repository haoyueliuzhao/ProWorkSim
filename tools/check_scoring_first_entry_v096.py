"""Real cold scorer request validation using explicitly synthetic temporary metadata."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]


def tool(name):
    spec=importlib.util.spec_from_file_location('v096_scoring_CPU_'+name,ROOT/'tools'/name)
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def child(folder):
    # The child uses exactly the same clean scorer loader and module factory as
    # production. No Docker client or external network is permitted.
    blocked=[]
    def audit(event,values):
        if event in {'socket.connect','socket.getaddrinfo','socket.sendto','socket.bind'}:
            blocked.append(event)
            raise AssertionError('No network or Docker socket in scorer CPU fixture')
        if event=='open' and values and isinstance(values[0],(str,bytes)):
            p=os.fsdecode(values[0])
            if p.startswith(('/dev/nvidia','/dev/dri/')) or p.endswith(('.safetensors','.gguf')):
                raise AssertionError('No GPU or model weights in scorer CPU fixture')
    sys.addaudithook(audit)
    folder=Path(folder).resolve()
    if not folder.is_relative_to(Path('/tmp')):
        raise ValueError('Only an explicitly temporary CPU fixture may be validated')
    from proworksim import software_benchmark_api_scope_v096 as scope
    from proworksim import software_benchmark_runtime_v096 as runtime
    from proworksim import software_benchmark_grading_v096 as grading
    from proworksim.software_benchmark_candidates_v054 import reference,write_new
    from proworksim.software_benchmark_deepseek_runtime_v069 import private_function
    from proworksim.software_benchmark_rescore_v095 import host_limits
    setup=tool('check_api_first_entry_v096.py')
    guard_root=folder/'guard'
    guard_root.mkdir()
    guard,auth,sources,_=setup.fixture_guard(guard_root,scope,runtime)
    cpu_scope=SimpleNamespace(**{**vars(scope),'AUTH_FILE':Path(auth['path']),'SOURCE_FILE':Path(sources['path'])})
    policy=private_function(runtime.dispatch_view,scope=cpu_scope)(guard)
    batch=folder/'physical'
    ns=policy.claim_resource.__globals__
    ns.update(BATCH_ROOT=batch,GRADING_ROOT=batch/'grading')
    policy.BATCH_ROOT,policy.GRADING_ROOT=batch,batch/'grading'
    scored=grading.scorer(policy)
    data=json.loads((folder/'fixture.json').read_bytes())
    request=data['request']
    for entry in data['files']:
        target=Path(entry['path'])
        if not target.resolve().is_relative_to(folder):
            raise ValueError('CPU fixture file escapes its temporary root')
        target.parent.mkdir(parents=True,exist_ok=True)
        if 'text' in entry:
            target.write_text(entry['text'])
        else:
            write_new(target,entry['json'])
    # Real claim/CPU/output and request-byte checks, against temporary records.
    execution=scored.resolve_execution_request(request)
    before_limits={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmSize:','VmRSS:'))}
    sys.stderr.write('CPU memory before limits '+json.dumps(before_limits)+'\n')
    limits=host_limits(execution['cpuset_cpus'])
    try:
        scored.validate_request(execution)
    except MemoryError:
        status={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmSize:','VmRSS:','Threads:'))}
        cache=scope.original._FILE_CACHE
        biggest=sorted([(len(v[1]),str(k)) for k,v in cache.items()],reverse=True)[:5]
        sys.stderr.write('CPU memory failure '+json.dumps({'status':status,'cached_raw_bytes':sum(len(v[1]) for v in cache.values()),'largest_cache_files':biggest})+'\n')
        raise
    assert scope.load(request['scorer_manifest'])==scored.installation_manifest()
    rejected=[]
    for name,changed in [('manifest', {**execution,'scorer_manifest':reference(folder/'wrong-manifest.json')}),
                         ('foreign_slot', {**execution,'slot_id':'not-one-of-the-79'})]:
        try:
            scored.validate_request(changed)
        except (ValueError,PermissionError):
            rejected.append(name)
        else:
            raise AssertionError('Changed scoring identity/manifest was accepted')
    assert not blocked
    return {'passed':True,'actual_original_validate_request_executed':True,
        'resource_key':request['resource_key'],'host_limits':limits,'rejected':rejected,
        'manifest_equal':True,'synthetic_metadata_not_an_experiment':True,
        'memory_before_limit':before_limits,
        'memory_after_validation':{line.split(':',1)[0]:line.split(':',1)[1].strip() for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmSize:','VmRSS:','Threads:'))},
        'Docker_operations':0,'model_calls':0,'network_attempts':0}


def run():
    from proworksim import software_benchmark_api_scope_v096 as scope
    from proworksim import software_benchmark_grading_v096 as grading
    from proworksim.software_benchmark_candidates_v054 import reference
    from proworksim import software_benchmark_scorer_v066 as base
    # This imports no API counter; production manager contamination is checked
    # separately by calling the same cold_manifest after true API initialization.
    manifest=grading.cold_manifest()
    cases=[]
    with tempfile.TemporaryDirectory(prefix='v096-scorer-cpu-') as tmp:
        root=Path(tmp)
        for arm in ('REF','PROJECT'):
            folder=root/arm
            folder.mkdir()
            row=next(r for r in scope.load(reference(scope.INVENTORY_FILE))['rows'] if r['arm']==arm)
            config=scope.load(row['configuration'])
            batch=folder/'physical'
            episode=batch/'episodes'/str(row['slot_index'])
            key='score-'+str(row['slot_index'])
            out=batch/'grading'/key
            claims=batch/'resource-claims'
            files=[]
            def put(path,value=None,*,text=None):
                from proworksim.storage import json_bytes
                raw=text.encode() if text is not None else json_bytes(value)
                import hashlib
                files.append({'path':str(path),**({'text':text} if text is not None else {'json':value})})
                return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
            quiet=put(episode/'quiescence.json',{'quiescent':True,'cleanup_errors':[],
                'create_result_unknown':False,'CPU_fixture_only':True})
            patch=put(episode/'candidate.patch',text='')
            lock=put(episode/'candidate-lock.json',{'version':'software-benchmark-native-closure-v054',
                'slot':{k:config[k] for k in ('slot_id','instance_id','condition_id','seed','arm')},
                'endpoint':'terminal_code','measurement_kind':'full_verified_comparison',
                'lock_before_grading':True,'tree_sha256':'CPU_fixture_no_model_tree',
                'patch_receipt':{'round_trip_verified':True,'utf8_strict':True,
                    'candidate_content_changed':False,'candidate_tree_sha256':'CPU_fixture_no_model_tree','patch':patch},
                'CPU_fixture_only':True})
            result=put(episode/'result.json',{'status':'closed','slot_id':row['slot_id'],
                'configuration':row['configuration'],'source_slot_id':row['source_slot_id'],
                'measurement_kind':'full_verified_comparison','quiescence':quiet,'candidate_lock':lock,
                'CPU_fixture_only':True})
            mf=put(folder/'manifest.json',manifest)
            put(folder/'wrong-manifest.json',{'untrusted_fixture_manifest':True})
            qualification=scope.load(reference(scope.INVENTORY_FILE))['qualifications'][row['instance_id']]['qualification']
            request={'version':base.VERSION,'resource_key':key,'instance_id':row['instance_id'],
                'plan':reference(scope.PLAN_FILE),'configuration':row['configuration'],
                'candidate_lock':lock,'generation_result':result,'measurement_kind':row['measurement_kind'],
                'source_slot_id':row['source_slot_id'],'slot_id':row['slot_id'],'qualification':qualification,
                'limits':base.LIMITS,'scorer_manifest':mf,'cpuset_cpus':None,'directory':str(out),
                'patch_kind':None,'delivery_evidence':None,**base.environment.request_fields(row['instance_id'])}
            request_ref=put(out/'request.json',request)
            # Use the exact fixed global grader lane schema, but no real lease.
            spec=scope.load(reference(scope.PLAN_FILE))['resources'][key]
            claim={'version':'v096-original-first-entry-private-bindings-r1','key':key,
                'plan':request['plan'],'spec':spec,'lane':0,'lease':str(claims/'active-grader-0.json')}
            claim_ref=put(claims/(key+'.json'),claim)
            put(claims/'active-grader-0.json',claim)
            put(out/'capacity-claim.json',{'prepared_request':request_ref,'claim':claim_ref})
            (folder/'fixture.json').write_text(json.dumps({'request':request,'files':files}))
            argv=[str(scope.ROOT/'.venv/bin/python'),'-B',str(scope.ROOT/'tools/run_offline_scorer_v096.py'),
                  str(Path(__file__).resolve()),'--child',str(folder)]
            completed=subprocess.run(argv,cwd=scope.ROOT,env=grading.clean_environment(),
                capture_output=True,text=True,timeout=120)
            if completed.returncode:
                raise AssertionError(completed.stdout[-2000:]+completed.stderr[-4000:])
            cases.append(json.loads(completed.stdout))
    return {'version':'v096-cold-scorer-validation-CPU-r1','passed':True,'cases':cases,
        'actual_child_validate_request':True,'manifest':manifest,'production_records_written':False,
        'model_calls':0,'Docker_operations':0,'GPU_operations':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child',type=Path)
    args=parser.parse_args()
    if args.child:
        print(json.dumps(child(args.child)))
    else:
        value=run()
        out=ROOT/'artifacts/software-benchmark-v096/scorer-isolation-control-r1/summary.json'
        out.parent.mkdir(parents=True,exist_ok=True)
        from proworksim.software_benchmark_candidates_v054 import write_new
        write_new(out,value)
        print(json.dumps({'passed':True,'cases':len(value['cases'])}))
