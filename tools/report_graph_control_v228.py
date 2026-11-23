"""Reconcile the eight planned tasks, matching official receipts to their own arm."""
import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'runs/software-benchmark-v228/control-r1'
PLAN = ROOT / 'artifacts/software-benchmark-v228/control-r2/panel.json'
DB = ROOT / 'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'


def read(path):
    return json.loads(path.read_bytes())


def ref(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def usage():
    with sqlite3.connect(f'file:{DB}?mode=ro', uri=True) as db:
        rows = db.execute("""
            SELECT slot,status,count(*),sum(json_extract(body,'$.input_tokens')),
                   sum(json_extract(body,'$.output_tokens')),sum(tokens),sum(cost)
            FROM requests WHERE slot GLOB 'v228:*' GROUP BY slot,status ORDER BY slot,status
        """).fetchall()
    return [dict(zip(('slot','status','requests','input','output','tokens','nanoyuan'), row)) for row in rows]


def arm_receipts(folder, arm, arm_result):
    episode = folder / arm
    keys = ('status','termination','logical_tokens','mechanism','metrics','osa_tokens',
            'control_attempts','controller_wall_seconds','public_test_cost','official','error')
    data = {k:arm_result[k] for k in keys if k in arm_result}
    references = [ref(episode/'result.json')] if (episode/'result.json').is_file() else []
    for kind, expected in data.get('official',{}).items():
        path = folder/f'{arm}-{kind}'/'receipt.json'
        receipt = read(path)
        if (receipt['instance_id'] != arm_result['instance_id'] or receipt['kind'] != kind
                or any(receipt.get(k) != v for k,v in expected.items()) or receipt.get('cleanup_errors')):
            raise ValueError(f'Endpoint receipt mismatch at {path}')
        references.append(ref(path))
    state = episode / 'common-state.json'
    if state.is_file():
        common = read(state)
        data['checkpoint'] = common['checkpoint']
        data['decision_remaining_tokens'] = common['remaining']
        data['regression_targets'] = common['regression_targets']
        references.append(ref(state))
    if arm == 'W1':
        data['decisions'] = []
        for activation in sorted(episode.glob('control-*/activation.json')):
            record = read(activation)
            options = read(activation.parent/'options.json')
            decision = record['decision']
            data['decisions'].append({'version':record['version'], 'target':options['options'][decision['option']],
                                      'changed':record['changed'],'evidence':decision['evidence']})
            references.extend([ref(activation),ref(activation.parent/'options.json')])
        final = episode/'final-organization.json'
        if final.is_file():
            graph = read(final)
            data['final_duties'] = graph['graph']['duties']
            data['blockers'] = (graph.get('control') or {}).get('blockers',[])
            references.append(ref(final))
    data['sources'] = references
    return data


def collect():
    cases = []
    stopped = False
    for row in read(PLAN)['rows']:
        i = row['index']
        item = {'index':i,'instance_id':row['instance_id'],'scene':row['target_scene'],
                'revision':'r1' if i==0 else 'r2'}
        end = RUN/f'result-{i}.json'
        if not end.exists():
            item['status'] = 'not_admitted_after_cash_gate' if stopped else 'pending'
        else:
            result = read(end); item['status'] = result['status']; item['result_source'] = ref(end)
            if 'error' in result:item['error'] = result['error']
            folder = RUN/f'task-{i:02d}'
            if result['status']=='complete_pair_cash_not_admitted':stopped = True
            if 'result' in result:item['natural_episode'] = arm_receipts(folder,'PREFIX',result['result'])
            if 'arms' in result:
                item['arms'] = {k:arm_receipts(folder,k,v) for k,v in result['arms'].items()}
                if result['status']=='scored_pair':
                    a,b = item['arms']['W0'],item['arms']['W1']
                    if a['checkpoint']!=b['checkpoint'] or a['decision_remaining_tokens']!=b['decision_remaining_tokens']:
                        raise ValueError(f'Unpaired decision state in {folder}')
        cases.append(item)
    costs = usage()
    settled = [r for r in costs if r['status']=='settled']
    totals = {k:sum(r[k] for r in settled) for k in ('requests','input','output','tokens','nanoyuan')}
    if totals['tokens']!=totals['input']+totals['output']:raise ValueError('Provider usage mismatch')
    return {'planned_cases':len(cases),'queue_ended':(RUN/'ended-1.json').exists(),
            'status_counts':dict(Counter(c['status'] for c in cases)),'cases':cases,
            'actual_settled':totals,'ledger':costs,'stage_cap_nanoyuan':135_000_000_000,
            'open_reservations_are_not_spend':True,'fit_updates':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=collect()
    if args.output:
        if not result['queue_ended']:parser.error('Queue still active; only live readout is available')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    else:
        print(json.dumps({k:result[k] for k in ('planned_cases','queue_ended','status_counts','actual_settled')},indent=2))
