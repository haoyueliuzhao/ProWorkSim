"""Bounded deterministic feedback from the same private immutable test report."""
import copy,re
VERSION='v223.1-failure-first-private-test-feedback-r1'
def compact(report,page,actor):
 if report['actor_id']!=actor or page['report_id']!=report['report_id']:raise ValueError('Same actor-owned report required')
 if page['source_reference']!=report['visible_result']['source_reference']:raise ValueError('Exact test version required')
 out=copy.deepcopy(page);evidence=out.pop('test_evidence',None) or report['visible_result'].get('public_execution',{}).get('execution',{}).get('test_evidence',{})
 failures=[]
 for session in evidence.get('sessions',[]):
  for t in session.get('test_reports',[]):
   if t.get('outcome') in ('failed','error'):
    key=(t.get('nodeid'),t.get('phase'))
    if key not in [(v['nodeid'],v['phase']) for v in failures]:failures.append({'nodeid':key[0],'phase':key[1],'outcome':t['outcome']})
 excerpts=[];locators=[];remaining=3200
 if page.get('passed') is not True:
  for group in report['visible_result'].get('groups',{}).values():
   raw=group.get('output','')
   if not isinstance(raw,str) or not raw:continue
   start=next((raw.index(k) for k in ('FAILURES','ERRORS','Traceback','FAILED') if k in raw),0)
   text=re.sub(r'\x1b\[[0-9;]*m','',raw[start:]);text=text[:remaining];remaining-=len(text)
   if text:excerpts.append({'source':'saved_visible_result.groups.output','text':text,'truncated':start+len(text)<len(raw),'ansi_color_removed':True})
   for needle in ('FAILURES','ERRORS','Traceback','FAILED'):
    pos=report['body'].find(needle)
    if pos>=0:
     found=next((p for p in report['pages'] if p['start']<=pos<p['end']),None)
     if found and found['cursor'] not in [x['cursor'] for x in locators]:locators.append({'cursor':found['cursor'],'page_index':found['index'],'tool':'read_test_result','report_id':report['report_id']})
   if remaining<=0:break
 out['diagnostic_summary']={'version':VERSION,'failed_tests':failures[:8],'omitted_failure_records':max(0,len(failures)-8),'excerpts':excerpts,'detail_pages':locators[:3],'full_evidence_remains_in_saved_body':True,'raw_report_body_sha256':report['body_sha256'],'not_additional_test_or_semantic_coverage':True}
 out['evidence_overview']={k:copy.deepcopy(evidence[k]) for k in ('framework','report_count','nested_report_count','partial','error') if k in evidence}
 return out
