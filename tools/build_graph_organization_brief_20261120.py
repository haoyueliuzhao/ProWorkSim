"""Verify the direct KEEP/ADAPT reporting comparison; no new experiments or Word."""
import json,datetime,re
from pathlib import Path
from zoneinfo import ZoneInfo
from proworksim.software_benchmark_candidates_v054 import reference
R=Path(__file__).resolve().parents[1];OUT=R/'artifacts/research-brief-20261120';DOC=R/'docs/experiments/software-weekly-research-brief-20261119.md'
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 source=R/'artifacts/software-benchmark-v216/final-report-r1';summary=read(source/'summary.json')
 rows=[r for r in read(source/'episodes.json') if r['revision']=='v216.2']
 assert len(rows)==4 and len({r['instance_id'] for r in rows})==2
 groups={}
 for condition in ('KEEP','ADAPT'):
  rr=[r for r in rows if r['condition']==condition];assert len(rr)==2
  groups[condition]={'runs':len(rr),'code_successes':sum(r['code_pass'] for r in rr),'correct_deliveries':sum(r['legal_delivery_pass'] for r in rr),'average_logical_tokens':sum(r['logical_usage']['total_tokens'] for r in rr)/len(rr),'budget_boundaries':sum(r['budget_boundary'] for r in rr)}
  old=next(g for g in summary['groups'] if g['revision']=='v216.2' and g['condition']==condition)
  assert groups[condition]['code_successes']==old['code_pass'] and groups[condition]['correct_deliveries']==old['legal_delivery_pass'] and groups[condition]['average_logical_tokens']==old['average_logical_tokens']
 assert all(r['actual_post_progress_adaptation'] for r in summary['gate']['facts'])
 assert all(r['scope_owner_dependency_mode_preserved'] for r in summary['gate']['KEEP_integrity'])
 fields=('revision','instance_id','condition','code_pass','legal_delivery_pass','logical_usage','prefix_tokens','generator_tokens','budget_boundary','final_observed_readiness','failed_official_tests','refs','score_refs')
 facts={'updated':datetime.datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),'comparison':'same-task KEEP versus model-proposed ADAPT','revision':'v216.2','tasks':2,'runs':4,'groups':groups,'episodes':[{k:r[k] for k in fields} for r in rows],'actual_adaptation_evidence':summary['gate']['facts'],'KEEP_integrity':summary['gate']['KEEP_integrity'],'relative_token_increase':groups['ADAPT']['average_logical_tokens']/groups['KEEP']['average_logical_tokens']-1,'sources':{'summary':reference(source/'summary.json'),'episodes':reference(source/'episodes.json'),'report':reference(R/'docs/experiments/software-benchmark-v216-final-report.md')},'v222_LG_not_relabelled_or_pooled':True,'new_model_calls':0,'new_scoring_runs':0}
 save(OUT/'keep-adapt-facts.json',facts)
 text=DOC.read_text()
 for g in groups.values():assert f'{g["average_logical_tokens"]/10000:.2f}万' in text
 assert '2/2，100%' in text and '1/2，50%' in text and '0/2' in text and '3/4' in text
 assert 'C/N' not in text and '498.69万' not in text and '497.07万' not in text
 links=re.findall(r'\[[^\]]+\]\(([^)]+)\)',text)
 for link in links:assert (DOC.parent/link).is_file(),link
 result={'format':'Markdown','word_generated':False,'facts':reference(OUT/'keep-adapt-facts.json'),'markdown':reference(DOC),'local_source_links_checked':len(links),'result_tables_recomputed':True,'scope':'direct_midtask_keep_adapt_comparison_v216_2','provider_calls':0}
 save(OUT/'markdown-publication-check.json',result);print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
