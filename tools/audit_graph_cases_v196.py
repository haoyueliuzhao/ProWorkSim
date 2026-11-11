"""Separate retrospective outcome/cost audit; never imported by graph selection."""
from __future__ import annotations
import json,hashlib
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'artifacts/software-benchmark-v195/context-report-r1'
OUT=ROOT/'artifacts/software-benchmark-v196/retrospective-cases-r1'


def load(name):return json.loads((SOURCE/name).read_bytes())
def ref(p):
    raw=p.read_bytes();return {'path':str(p),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
def main():
    primary=load('primary-tasks.json');episodes=load('episodes.json');actions=load('actions.json');cards=load('critical-cards.json')
    audit=load('mechanism-audit.json');rows=[]
    for task in primary:
        left,right=task['M1-5'],task['M1-5K']
        category=('both_pass' if left and right else 'M15_only' if left else 'K_only' if right else 'both_fail')
        row={'instance_id':task['instance_id'],'repo':task['repo'],'outcome_class':category,'groups':{}}
        for method in ('M1-5','M1-5K'):
            e=next(e for e in episodes if e['instance_id']==task['instance_id'] and e['group_id']==method and e['primary_panel'])
            selected=[a for a in actions if a['slot_index']==e['slot_index']];counts=Counter(a['tool'] for a in selected)
            c=[c for c in cards if c['slot_index']==e['slot_index']];first_presentations=[]
            for card in c:
                following=next((a for a in selected if a['request_id']==card['first_observed_request']),None)
                report_ids=[f['value'] for f in card['fields'] if f['pointer']=='/result/report_id']
                first_presentations.append({'reference':card['reference'],'category':card['category'],'payload':card['payload'],
                    'first_request':card['first_observed_request'],'next_actual_tool':following['tool'] if following else None,
                    'immediate_read_of_same_report':bool(following and following['tool']=='read_test_result' and following['arguments'].get('report_id') in report_ids),
                    'this_is_temporal_association_not_proof_of_adoption':True})
            row['groups'][method]={'slot_index':e['slot_index'],'code':e['code'],'delivery':e['delivery'],
                'tokens':e['usage']['total_tokens'],'requests':e['usage_by_purpose']['agent']['requests'],
                'stop':e['end_class'],'masked_observation_exposures':e['critical_numeric'].get('masked_observation_exposures'),
                'card_exposures':e['critical_numeric'].get('card_exposures',0),'source_cards':len(c),
                'exact_duplicate_card_exposures':audit['duplicates_by_episode'].get(str(e['slot_index']),{}).get('extra_cards',0),
                'tools':dict(counts),'new_context_read':counts.get('context_read',0),'official_failures':e['official_failures'],
                'changed_patch_headers':e['changed_patch_headers'],'first_card_followups':first_presentations,
                'evidence':e['evidence']}
        rows.append(row)
    results={'version':'v196-retrospective-outcome-classes-r1','classes':dict(Counter(r['outcome_class'] for r in rows)),
        'rows':rows,'all12_included_not_selected_by_favorable_results':True,
        'outcomes_and_final_patch_information_not_passed_to_graph_or_selector':True,
        'no_counterfactual_causal_effect_claimed':True,'new_model_calls':0,
        'sources':[ref(SOURCE/n) for n in ['primary-tasks.json','episodes.json','actions.json','critical-cards.json','mechanism-audit.json']]}
    OUT.mkdir(parents=True,exist_ok=True);p=OUT/'cases.json'
    if p.exists():raise ValueError('Preserve prior audit')
    p.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(results['classes']))


if __name__=='__main__':main()
