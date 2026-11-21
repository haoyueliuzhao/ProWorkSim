"""Audit the executed validation handoff, locked scores, and physical vs logical costs."""
import json
import sqlite3
from pathlib import Path

R = Path(__file__).resolve().parents[1]
P = R/'artifacts/software-benchmark-v224-3/pair-r1'
RUN = R/'runs/software-benchmark-v224-3/pair-r1/task-01'

def read(path):
    return json.loads(path.read_text())

def analyze():
    result = read(P/'result.json')
    summary = {'branches': {}, 'policy_updates':result['policy']['update'],
               'weights_changed':any(h.get('weights_changed') for h in result['policy']['history'])}
    for label, outcome in result['outcomes'].items():
        ep = RUN/label
        row = dict(outcome)
        if (ep/'boundary.json').exists():
            boundary = read(ep/'boundary.json')
            events = read(ep/'final-world.json')['software_events']
            row['termination'] = boundary.get('termination_class')
            row['handoff_events'] = [
                {k:e.get(k) for k in ('sequence','kind','actor_id','task_id','offer_id')}
                for e in events if e['kind'].endswith((':joint_offered',':joint_accepted',':joint_declined',':work_performed'))
                and e.get('task_id')=='pkg_validation' and e['sequence']>21]
            row['choice'] = read(ep/'progress.json')['lifecycle'].get('choice')
        summary['branches'][label] = row
    with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as db:
        usage = [json.loads(x[0]) for x in db.execute("SELECT body FROM requests WHERE slot GLOB 'v224.3:*' AND status='settled'")]
        summary['physical_cost_by_slot'] = {slot: {'requests': count, 'tokens': tokens, 'CNY': cost}
            for slot,count,tokens,cost in db.execute("SELECT slot,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot GLOB 'v224.3:*' AND status='settled' GROUP BY slot")}
        summary['requests_by_status'] = dict(db.execute("SELECT status,count(*) FROM requests WHERE slot GLOB 'v224.3:*' GROUP BY status"))
        summary['usage'] = {k:sum(u[k] for u in usage) for k in ('input_tokens','output_tokens','total_tokens','peak_cost_nanoyuan')}
        summary['remaining_CNY_after_settlement'] = 1100-db.execute("SELECT sum(cost)/1e9 FROM requests WHERE status='settled'").fetchone()[0]
    return summary

if __name__ == '__main__':
    print(json.dumps(analyze(),ensure_ascii=False,indent=2))
