"""Run the clarified12 independent diagnostic attempts; preserve v177 results."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import copy
import fcntl
import json
import os
from pathlib import Path
import time

from proworksim.software_benchmark_candidates_v054 import reference,write_new,checked
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_context_api_v175 import ReplayAPI,load_api_key,AdmissionBusy,CashClosed
from proworksim.software_context_probe_v178 import ProbeLedger,restore_store,evaluate,load,RUN,ROOT,MAX_DECISIONS


def retain(path,value):
    if path.exists():
        if json.loads(path.read_bytes())!=value:raise ValueError('A resumed diagnostic changed its original result')
        return reference(path)
    return write_new(path,value)


def parse_answer(text):
    if not isinstance(text,str):raise ValueError('Missing final JSON')
    text=text.strip()
    if text.startswith('```') and text.endswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0]
    value=json.loads(text)
    if not isinstance(value,dict) or not isinstance(value.get('facts'),dict) or not isinstance(value.get('evidence'),list):
        raise ValueError('Final facts/evidence structure missing')
    return value


class Probe:
    def __init__(self):
        self.plan=load(reference(RUN/'plan.json'))
        freeze=load(reference(RUN/'sources.json'))
        for ref in freeze['files']:checked(ref)
        if freeze['plan']!=reference(RUN/'plan.json'):raise ValueError('Frozen cases changed')
        self.ledger=ProbeLedger(phase_plan=reference(RUN/'plan.json'),authority=self.plan['authority'])
        manifest=ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
        self.api=ReplayAPI(self.ledger,counter=OfficialDeepSeekCounter(manifest,manifest_sha256=reference(manifest)['sha256']),
            api_key=load_api_key(ROOT/'.env'),concurrency=self.plan['maximum_concurrency'])

    def one(self,case):
        job='v178:'+case['case_id'];folder=RUN/'cases'/case['case_id'];folder.mkdir(parents=True,exist_ok=True)
        if (folder/'result.json').exists():return load(reference(folder/'result.json'))
        result={'case_id':case['case_id'],'kind':case['kind'],'status':'running','reads':[],'calls':[],
            'new_world_actions':0,'diagnostic_decision_not_executed':True}
        try:
            while True:
                try:self.ledger.admit(job,'v178-recovery-probe');break
                except AdmissionBusy:time.sleep(.25)
            store=restore_store(case['store']);payload=load(case['actual_initial_payload']);started=time.monotonic()
            answer=None
            for step in range(MAX_DECISIONS):
                body,rid=self.api.call(job,payload,purpose='recovery',step=step,folder=folder/'physical')
                result['calls'].append(rid);message=body['choices'][0]['message'];calls=message.get('tool_calls') or []
                if not calls:
                    try:answer=parse_answer(message.get('content'))
                    except (ValueError,TypeError) as error:
                        # A format-only correction consumes a real opportunity; no answer oracle.
                        if step==MAX_DECISIONS-1:raise
                        payload['messages'].append({'role':'assistant','content':message.get('content','')})
                        payload['messages'].append({'role':'user','content':'Please provide the requested final JSON fields. No factual correctness feedback is supplied.'})
                        continue
                    break
                if len(calls)!=1 or calls[0]['function']['name']!='context_read':
                    raise ValueError('Only a single read-only context tool is available')
                if step==MAX_DECISIONS-1:break
                call=calls[0]
                try:
                    arguments=json.loads(call['function']['arguments'])
                    feedback={'ok':True,'result':store.read(arguments,point_id=store.point_id,slot_id=store.slot_id,member_id=store.member_id)}
                    # Expose only identity already bound by the private store.
                    entry=store.entries[arguments['reference']]
                    if 'message_index' in entry:feedback['result']['original_message_index']=entry['message_index']
                except (ValueError,TypeError,PermissionError) as error:
                    feedback={'ok':False,'error':{'type':type(error).__name__,'message':str(error)}}
                result['reads'].append(feedback)
                payload['messages'].append({k:message[k] for k in ('role','content','tool_calls') if k in message})
                payload['messages'].append({'role':'tool','tool_call_id':call['id'],'name':'context_read',
                    'content':json.dumps(feedback,ensure_ascii=False,separators=(',',':'))})
            result.update(status='closed',answer=answer,wall_seconds=time.monotonic()-started,
                assessment=evaluate(case,answer or {},result['reads']))
            self.ledger.finish(job,'closed')
        except CashClosed:
            result['status']='not_started_cash_admission'
        except Exception as error:
            result.update(status='technical_unknown',error={'type':type(error).__name__,'message':str(error)[:500]})
            self.ledger.finish(job,'technical_unknown')
        retain(folder/'result.json',result)
        print(json.dumps({'case':case['case_id'],'status':result['status'],
            'passed':result.get('assessment',{}).get('passed'),'reads':len(result['reads'])}),flush=True)
        return result

    def run(self):
        start=time.monotonic();before=self.ledger.snapshot();results=[]
        with ThreadPoolExecutor(max_workers=self.plan['maximum_concurrency']) as pool:
            futures={pool.submit(self.one,c):c for c in self.plan['cases']}
            for future in as_completed(futures):
                try:results.append(future.result())
                except Exception as error:
                    c=futures[future];self.ledger.finish('v178:'+c['case_id'],'technical_unknown')
                    results.append({'case_id':c['case_id'],'status':'technical_unknown','error':{'type':type(error).__name__}})
        result={'plan':reference(RUN/'plan.json'),'before_cumulative':before,'after_cumulative':self.ledger.snapshot(),
            'rows':sorted(results,key=lambda r:r['case_id']),'gate_passed':all(r.get('assessment',{}).get('passed') for r in results),
            'world_actions':0,'wall_seconds':time.monotonic()-start}
        retain(RUN/'summary.json',result);print(json.dumps({k:v for k,v in result.items() if k!='rows'}),flush=True)


if __name__=='__main__':
    os.nice(10);os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[-4:])
    lock=(RUN/'owner.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    Probe().run()
