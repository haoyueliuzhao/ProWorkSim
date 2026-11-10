"""Bound repeated test-evidence headers; keep exact private report pages intact."""
import copy,json,re
from types import MethodType
from .storage import digest,json_bytes
from .software_collaboration_runtime_observer_v167 import root_sessions

VERSION='v193-bounded-public-test-evidence-header-r1'


def evidence_cursor(report,evidence):
    """Locate an existing page, without inventing a cursor or changing its body."""
    decoder=json.JSONDecoder();wanted=digest(json_bytes(evidence))
    for match in re.finditer(r'"test_evidence":\s*',report['body']):
        try:value,_=decoder.raw_decode(report['body'],match.end())
        except ValueError:continue
        if digest(json_bytes(value))!=wanted:continue
        page=next(p for p in report['pages'] if p['start']<=match.end()<p['end'])
        return page['cursor']
    raise ValueError('Complete framework evidence is not recoverable from the original report body')


def project_test_page(page,report,actor,*,cursor=None):
    if report.get('actor_id')!=actor or report.get('report_id')!=page.get('report_id'):
        raise PermissionError('Only the same member private report can be projected')
    visible=report['visible_result'];execution=visible.get('public_execution',{}).get('execution',{})
    full=execution.get('test_evidence')
    if not isinstance(full,dict) or 'test_evidence' not in page:return page
    if page.get('source_reference')!=visible.get('source_reference') or page['test_evidence']!=full:
        raise ValueError('Projected header must bind the exact recorded test source and report')
    cursor=cursor or evidence_cursor(report,full)
    if not any(p['cursor']==cursor for p in report['pages']):raise ValueError('Unknown original evidence page')
    header={'version':VERSION,'full_evidence_version':full.get('version'),
        'framework':full.get('framework'),'report_count':full.get('report_count'),
        'nested_report_count':full.get('nested_report_count'),'partial':full.get('partial'),
        'parse_error_present':full.get('error') is not None,
        'root_sessions':root_sessions(full),'total_sessions':len(full.get('sessions',[])),
        'root_counts_only':True,'full_evidence_sha256':digest(json_bytes(full)),
        'full_details':{'tool':'read_test_result','report_id':report['report_id'],'cursor':cursor,
            'body_sha256':report['body_sha256'],'same_immutable_report':True,
            'instruction':'Read this exact page and follow next_cursor for the complete framework evidence; no test reruns.'},
        'full_test_records_omitted_from_repeated_header':True,
        'full_test_records_remain_in_exact_body_pages':True}
    if len(json_bytes(header))>4096:raise ValueError('Bounded test header exceeds4KiB')
    value=dict(page);value['test_evidence']=header
    return value


def bind_world_test_view(world):
    if getattr(world,'public_test_view_revision',None)==VERSION:return world
    original=world._validation_status_page;cache={}
    def bounded(self,actor,page):
        raw=original(actor,page)
        if 'test_evidence' not in raw:return raw
        report=self._software()['test_reports'][raw['report_id']]
        key=(raw['report_id'],report['body_sha256'])
        if key not in cache:cache[key]=evidence_cursor(report,raw['test_evidence'])
        return project_test_page(raw,report,actor,cursor=cache[key])
    world._validation_status_page=MethodType(bounded,world)
    world.public_test_view_revision=VERSION
    return world


def full_observer_result(world,member,result):
    """Restore full evidence to the passive observer, never to the model wire."""
    header=result.get('test_evidence',{})
    if not isinstance(header,dict) or header.get('version')!=VERSION:return result
    report=world._software()['test_reports'].get(result.get('report_id'))
    if not report or report['actor_id']!=member or report['visible_result']['source_reference']!=result.get('source_reference'):
        raise ValueError('Observer report identity differs from the bounded member return')
    full=report['visible_result']['public_execution']['execution']['test_evidence']
    if digest(json_bytes(full))!=header['full_evidence_sha256']:raise ValueError('Observer original evidence hash differs')
    return {**result,'test_evidence':copy.deepcopy(full)}
