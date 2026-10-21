"""One explicit retained-terminal export, never a model/episode re-entry."""
import json
from contextlib import contextmanager
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_native_closure_v054 import lock_native_candidate
from proworksim.software_benchmark_queue_v054 import atomic, lock_file
from proworksim.software_benchmark_runner_v054 import score_requests
from proworksim.software_benchmark_supervision_v054 import assert_quiet, assert_outer_launcher_exited

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
QUEUE = ROOT/'runs/software-benchmark-v054/formal-queue-r1'
OUT = ROOT/'runs/software-benchmark-v054/administrative-closure-r1'
EP = QUEUE/'slots/39/preclaim-1/episode'
CLAIM = ROOT/'runs/software-benchmark-v054/episode-claims/ef-invalid'


def read(path):
    return json.loads(Path(path).read_bytes())


def quiet(scopes):
    proofs=[]
    for scope in scopes:
        proofs.append(assert_quiet(scope))
        assert_outer_launcher_exited(scope)
    return proofs


def main():
    with lock_file(QUEUE/'controller.lock'):
        q=read(QUEUE/'state.json')
        assert q['status']=='paused_technical_unknown' and q['active_generation']==q['active_graders']==0
        row=q['rows'][38];g=row['generation'];slot=row['slot']
        assert slot['slot_id']=='v054-REF-pydata__xarray-6461' and g['status']=='technical_unknown'
        assert not row['scores'] and g['claimed'] is True
        original=read(checked(g['result']));child=read(EP/'controller-result.json')
        assert original['error']=={'type':'RuntimeError','message':'No complete bound quiescence evidence'}
        assert original['entered'] is True and child['status']=='closed' and child['hidden_feedback_received'] is False
        ledger=child['ledger']
        assert ledger['attempts']==27 and ledger['complete_actual_tokens']==ledger['known_actual_tokens']==467492
        assert ledger['inflight'] is None and ledger['uncertain_reserved_tokens']==0
        start=read(EP/'start.json');claimroot=Path(start['guard_path']).parent
        claim=read(claimroot/'claim.json');oldquiet=read(claimroot/'quiescence.json')
        assert claim['slot']==slot and claim['claim_id']==start['claim_id']==oldquiet['claim_id']
        assert len(oldquiet['errors'])==1 and oldquiet['errors'][0]['unit'].endswith('-model.service')
        assert 'CalledProcessError(5,' in oldquiet['errors'][0]['error']
        assert all(not x['populated'] for x in oldquiet['stopped'])
        assert not (claimroot/'candidate-claim.json').exists() and not (claimroot/'candidate-result.json').exists()
        assert not (EP/'candidates').exists()
        release=read(checked(original['resident_release']));session=read(checked(release['session']))
        rr=release['result']
        assert rr['claim_id']==claim['claim_id']==session['claim_id']
        assert all(rr[k] is True for k in ['released','quiescent','resident_still_loaded','cache_reset'])
        assert rr['engine_unfinished']==0 and rr['weights_unloaded'] is False
        config=read(checked(g['config']));task=config['public_task']
        assert task['instance_id']==slot['instance_id'] and config['arm']=='REF'
        assert config['seed']==slot['seed'] and config['authorization']==claim['authorization']
        scopes=oldquiet['scopes'];stopped=quiet(scopes)
        OUT.mkdir(parents=True,exist_ok=False)
        before=write_new(OUT/'state-before.json',(QUEUE/'state.json').read_bytes())
        original_claim=write_new(OUT/'original-claim.json',(claimroot/'claim.json').read_bytes())
        intent=write_new(OUT/'intent.json',{'version':'v054-explicit-administrative-candidate-closure-r1',
            'original_result':g['result'],'original_claim':original_claim,
            'original_configuration':g['config'],'original_bindings':q['bindings'],
            'controller_result':reference(EP/'controller-result.json'),
            'original_failed_quiescence':reference(claimroot/'quiescence.json'),
            'normal_resident_release':original['resident_release'],
            'generation_already_closed':True,'new_model_calls':0,'formal_claims_created':0,
            'actor_worktree_modified':False,'candidate_reselection':False,'hidden_score_observed':False})
        proof=write_new(OUT/'quiescence.json',{'version':oldquiet['version'],'claim_id':claim['claim_id'],
            'scopes':scopes,'stopped':stopped,'errors':[],'all_quiet':True,
            'administrative_closure':intent,'outer_launchers_proven_exited':True,
            'model_calls':0,'usage_reconstructed':False,'known_actual_tokens':467492})
        class Boundary:
            root=claimroot
            claim_id=claim['claim_id']
            def __init__(self): self.slot=slot
            @contextmanager
            def candidate_boundary(self):
                with lock_file(claimroot/'administrative-candidate.lock'):
                    quiet(scopes)
                    write_new(claimroot/'candidate-claim.json',{'claim_id':self.claim_id,
                        'quiescence':proof,'administrative_closure':intent,'selection_after_scoring':False})
                    yield proof
                    quiet(scopes)
        candidate=lock_native_candidate(Boundary(),baseline_reference=reference(EP/'public-source/initial-tree.json'),
            public_worktree=EP/'actor/rootfs/testbed',public_task=task,dataset_revision=config['dataset_revision'],
            output=OUT/'candidates')
        requests=score_requests(config,candidate,OUT)
        assert len(requests)==1
        request=read(checked(requests[0]))
        assert request['endpoint']=='code' and request['instance_id']==slot['instance_id']
        assert request['scorer_manifest']==json.loads(checked(q['bindings']).read_text())['scorer_manifest']
        result={**original,'status':'closed_candidate_and_official_requests_ready',
            'candidate':candidate,'official_requests':requests,'controller_result':reference(EP/'controller-result.json'),
            'quiescence':proof,'hidden_feedback_to_actor':False,'public_test_calls':0,
            'administrative_closure':intent,'original_error_result':g['result'],
            'model_calls':27,'actual_tokens':467492,'new_model_calls_from_administrative_closure':0}
        result.pop('error');result.pop('resident_poison')
        rrref=write_new(OUT/'result.json',result)
        g.update(status='closed',result=rrref,controller_result=result['controller_result'],
                 actual_cost_ledger=result['controller_result'],administrative_closure=intent)
        row.setdefault('original_execution_bindings',row.get('next_execution_bindings',q['bindings']))
        row['scores']['code']={'status':'pending','request':requests[0]}
        q['status']='paused_operator_drain'
        q.setdefault('administrative_closures',[]).append(intent)
        q['generation_counts']={kind:sum(r['generation']['status']==kind for r in q['rows']) for kind in ['closed','pending','technical_unknown']}
        assert reference(QUEUE/'state.json')['sha256']==before['sha256']
        atomic(QUEUE/'state.json',q)
        write_new(OUT/'applied.json',{'state_before':before,'state_after':reference(QUEUE/'state.json'),
            'result':rrref,'new_model_calls':0,'original_faults_retained':True,'score_pending':True})
        print(json.dumps({'result':rrref,'code_score_request':requests[0],'model_calls':0}))

if __name__=='__main__': main()
