"""Join official endpoints to actual changes of responsibility and measured usage."""
import json
import sqlite3
from pathlib import Path

from run_window2_v224_4 import PUBLIC, OUT, DATABASE, ROOT, read, save
from proworksim.software_mapping_selector_v224 import evaluate, initialize

def report():
    result=read(PUBLIC/'result.json')
    inputs=read(PUBLIC.parent/'oa-r1/results.json')['rows']
    q1=read(PUBLIC/'q1.json')
    q2=result['policy']
    summaries=[]
    for record in result['records']:
        idx=record['index']
        key=f'task-{idx:02d}'
        source=next(row for row in inputs if row['index']==idx)
        state=read(Path(source['input']['path']))['actual_decision_state']
        bank=read(PUBLIC/key/'bank.json')
        seed=record['decision']['seed']
        decisions={name:evaluate(state,bank,policy,seed) for name,policy in [('Q0',initialize()),('Q1',q1),('Q2',q2)]}
        arms={}
        for label,value in record['outcomes'].items():
            ep=OUT/key/label
            arm=dict(value)
            if (ep/'boundary.json').exists():
                boundary=read(ep/'boundary.json')
                actions=[]
                for item in boundary['outcomes']:
                    decision=item.get('decision',{})
                    if item.get('response',{}).get('ok') and decision.get('action') in ('offer_joint_arrangement','accept_joint_arrangement','decline_joint_arrangement','change_dependency','complete_work','fix_patch','submit_integration'):
                        actions.append({'member':item['worker_id'],'tool':decision['action'],
                                        'task':decision.get('arguments',{}).get('task_id')})
                arm.update(termination=boundary.get('termination_class'),actions=actions)
            arms[label]=arm
        summaries.append({'instance':record['instance'],'q':{k:v['probabilities'] for k,v in decisions.items()},
                          'draw':{k:v['selected'] for k,v in decisions.items()},'arms':arms})
    with sqlite3.connect('file:'+str(DATABASE)+'?mode=ro',uri=True) as db:
        usage=[json.loads(r[0]) for r in db.execute("SELECT body FROM requests WHERE slot GLOB 'v224.4:*' AND status='settled'")]
    summary={'tasks':summaries,'actual_tokens':{k:sum(u[k] for u in usage) for k in ('input_tokens','output_tokens','total_tokens','peak_cost_nanoyuan')},
             'learning_history':q2['history'][-1],'remaining_CNY':result['remaining_CNY'],'confirmation_started':False}
    save(PUBLIC/'summary.json',summary)
    return summary

if __name__=='__main__':
    report()
