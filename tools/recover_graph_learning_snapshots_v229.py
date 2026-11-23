"""Resume two saved prefixes at the first unpaid operation. Keep the original attempt records."""
import argparse
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_graph_learning_balance_v229 as batch
from run_graph_learning_episode_v229 import draft_graph,explain,menu,support,ControlledWorld
from run_graph_learning_episode_v229_1 import main as frozen_episode
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_benchmark_candidates_v054 import checked,reference
from proworksim.software_graph_budget_v229 import LIMIT,PRICE,AdmissionStopped
from proworksim.storage import read_json,json_bytes,atomic_write

SOURCE=batch.OUT
OUT=SOURCE.parent/'dev1-balance90-recovery-r1'
PLAN=batch.ROOT/'artifacts/software-benchmark-v229/dev1-balance90-recovery-r1'
INDICES=(20,21)


def reserve(meter,key,used):
    remaining=LIMIT-used
    with meter.db() as db:
        if db.execute("SELECT value FROM meta WHERE key='cap'").fetchone()!=(str(meter.cap),):
            raise ValueError('Account cap changed')
        if db.execute("SELECT 1 FROM slots WHERE status!='closed'").fetchone() or db.execute("SELECT 1 FROM block_slots WHERE status='pending'").fetchone():
            raise ValueError('Unexpected open reservation')
        if db.execute("SELECT 1 FROM requests WHERE status='reserved'").fetchone():raise ValueError('Unsettled provider request')
        old=key+':PREFIX'
        if db.execute("SELECT status FROM slots WHERE id=?",(old,)).fetchone()!=('closed',):
            raise ValueError('Expected a closed archived prefix')
        charged=db.execute("SELECT sum(tokens) FROM requests WHERE slot=? AND status='settled'",(old,)).fetchone()[0]
        if charged!=used or not 0<remaining<LIMIT:raise ValueError('Checkpoint differs from provider usage')
        paid=db.execute("SELECT coalesce(sum(cost),0) FROM requests WHERE status='settled'").fetchone()[0]
        if paid+2*remaining*PRICE>meter.cap:raise AdmissionStopped('Complete remaining pair exceeds balance')
        db.executemany("INSERT INTO block_slots VALUES(?,?,?,'pending')",[(key+':'+n,key,remaining) for n in ('DRAFT','RECOVERY_HOLD')])


def allocate_arms(meter,key,remaining,bank):
    arms=list(bank['decision']['q'])
    if arms not in (['KEEP'],['KEEP','CHANGE']):raise ValueError('Invalid candidate support')
    with meter.db() as db:
        slot=key+':DRAFT'
        if db.execute('SELECT status FROM slots WHERE id=?',(slot,)).fetchone()!=('closed',):
            raise ValueError('Proposal usage is unsettled')
        used=db.execute("SELECT coalesce(sum(tokens),0) FROM requests WHERE slot=? AND status='settled'",(slot,)).fetchone()[0]
        if used!=bank['osa_tokens'] or remaining-used!=bank['remaining']:raise ValueError('Proposal fee mismatch')
        for name in arms:
            db.execute("INSERT INTO block_slots VALUES(?,?,?,'pending')",(key+':'+name,key,remaining-used))
        if db.execute("UPDATE block_slots SET status='released' WHERE slot=? AND status='pending'",(key+':RECOVERY_HOLD',)).rowcount!=1:
            raise ValueError('Missing complete-pair reservation')


def draft(index,dest):
    from proworksim import software_sdk_resume_v203_3_4 as resume,software_role_baseline_world_v141 as base,software_natural_organization_world_v224_2 as natural
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    from proworksim.software_organization_api_v204 import DirectHTTPS
    from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
    from proworksim.software_benchmark_deepseek_api_v105 import load_api_key
    old=SOURCE/f'task-{index:02d}'/'PREFIX';dest.mkdir()
    cp=old/'checkpoint';previous=read_json(old/'result.json')
    if previous['status']!='technical_unknown' or previous.get('error')!="name 'explain' is not defined" or (old/'draft').exists():
        raise ValueError('Not a preproposal interruption')
    state,proof=resume.read(cp)
    if proof!=read_json(old/'checkpoint-proof.json'):raise ValueError('Unverified snapshot')
    for name in ('checkpoint','observations.json'):
        (dest/name).symlink_to(old/name,target_is_directory=name=='checkpoint')
    row=read_json(batch.PLAN/'panel.json')['rows'][index]
    control=state['control_state'];observer=control['observer'];node=explain(control['node'],read_json(old/'observations.json'),observer)
    tok=batch.ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
    counter=OfficialDeepSeekCounter(tok,manifest_sha256=reference(tok)['sha256'])
    meter=batch.ExactLedger(read_json(batch.AUTH));slot=f'v229:{dest.parent.name}:DRAFT';remaining=LIMIT-proof['prefix_tokens']
    def forbidden_test(**kwargs):raise ValueError('Proposal has no test access')
    with TemporaryDirectory(dir=dest,prefix='world-') as tmp:
        prepared=base.prepare_case(old/'actor/source-manifest.json',Path(tmp)/'prepared',organization_id='FREE2',
            public_test_callback=forbidden_test,public_test_entry=read_json(old/'prepared/role-public-test-selection.json')['entry'],
            deadline=DispatchDeadline(soft_seconds=21600,hard_seconds=23400))
        natural.attach(prepared,[x['id'] for x in row['requirements']],condition='G')
        resume.restore_world(prepared,cp);world=prepared.world;world.__class__=ControlledWorld
        frozen=menu(world,node,observer)
        if len(frozen['options'])<2:raise ValueError('Recovered state no longer has a legal alternative')
        meter.admit(slot,remaining)
        try:
            start=time.monotonic()
            cost,choice=draft_graph(world,node,observer,counter,DirectHTTPS(load_api_key(batch.ROOT/'.env'),timeout_seconds=1800),
                                    meter,slot,dest/'draft',remaining)
            elapsed=time.monotonic()-start
        finally:meter.close(slot)
    valid=choice is not None
    if not valid:choice={'option':'K','evidence':[next(iter(frozen['evidence']))],'reason':'No valid alternative; continue under original graph'}
    bank=support(frozen,choice,proof['identity'],remaining-cost,read_json(SOURCE/'Q0.json'))
    bank.update(osa_tokens=cost,valid_nomination=valid,osa_seconds=elapsed,osa_calls=len(list((dest/'draft/api').glob('*/usage.json'))),
                primary_arm=max(bank['decision']['q'],key=bank['decision']['q'].get))
    atomic_write(dest/'candidate-bank.json',json_bytes(bank))
    atomic_write(dest/'result.json',json_bytes({'status':'point_ready','prefix_tokens':proof['prefix_tokens'],'osa_tokens':cost}))


def run(index,meter):
    row=read_json(batch.PLAN/'panel.json')['rows'][index]
    root=OUT/f'task-{index:02d}';root.mkdir()
    key='v229:'+root.name
    manifest=read_json(SOURCE/root.name/'PREFIX/checkpoint/manifest.json');used=manifest['prefix_tokens']
    reserve(meter,key,used)
    try:
        pre=batch.window.invoke(Path(__file__).name,['--draft','--index',index],root/'PREFIX','result.json')
        if pre['status']!='point_ready':raise ValueError(str(pre))
        bank=read_json(root/'PREFIX/candidate-bank.json')
        allocate_arms(meter,key,LIMIT-used,bank)
        def branch(name):
            args=['--index',index,'--condition',name,'--policy',SOURCE/'Q0.json','--prefix',root/'PREFIX']
            result=batch.window.invoke(Path(__file__).name,args,root/name,'result.json')
            return batch.window.grade(row,root,name,result)
        arms={}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures={arm:pool.submit(branch,arm) for arm in bank['decision']['q']}
            for arm,future in futures.items():
                try:arms[arm]=future.result()
                except Exception as exc:arms[arm]={'status':'technical_unknown','error':repr(exc)}
        known=all(a['status']=='closed' and all(type(a['official'][k]['resolved']) is bool for k in ('code','delivery')) for a in arms.values())
        return {'instance_id':row['instance_id'],'phase':'dev1','status':('paired' if len(arms)==2 else 'single_response') if known else 'incomplete',
                'bank':bank,'arms':arms,'reused_prefix_tokens':used}
    finally:
        with meter.db() as db:
            for n in ('RECOVERY_HOLD','DRAFT','KEEP','CHANGE'):
                db.execute("UPDATE block_slots SET status='released' WHERE slot=? AND status='pending'",(key+':'+n,))


def coordinator():
    freeze=read_json(PLAN/'freeze.json')
    for r in freeze['files']:checked(r)
    meter=batch.ExactLedger(read_json(batch.AUTH))
    OUT.mkdir(parents=True,exist_ok=False)
    records={}
    for i in INDICES:
        try:records[i]=run(i,meter)
        except AdmissionStopped as exc:records[i]={'status':'cash_not_admitted','error':str(exc)}
        except Exception as exc:records[i]={'status':'technical_unknown','error':repr(exc)}
        atomic_write(OUT/f'result-{i}.json',json_bytes(records[i]))
    rows=read_json(batch.PLAN/'panel.json')['rows'][20:24]
    for i in (22,23):records[i]=read_json(SOURCE/f'result-{i}.json')
    update=batch.update_window(batch.Q0,[r for r in records.values() if r['status']=='paired'],[r['instance_id'] for r in rows])
    atomic_write(OUT/'window-result.json',json_bytes({'tasks':{i:r['status'] for i,r in records.items()},'update':update,'Q1_produced':update['fitted']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');parser.add_argument('--draft',action='store_true')
    parser.add_argument('--index',type=int,choices=INDICES);parser.add_argument('--condition',choices=['KEEP','CHANGE'])
    for name in ('output','prefix','policy'):parser.add_argument('--'+name,type=Path)
    args=parser.parse_args()
    if args.run:coordinator()
    elif args.draft:draft(args.index,args.output)
    else:
        expected=OUT/f'task-{args.index:02d}'
        if args.output!=expected/args.condition or args.prefix!=expected/'PREFIX' or args.policy!=SOURCE/'Q0.json':parser.error('Invalid branch identity')
        clone_function(frozen_episode,{**frozen_episode.__globals__,'explain':explain,'PLAN':batch.PLAN,'AUTH':batch.AUTH,'WindowLedger':batch.ExactLedger})(args)
