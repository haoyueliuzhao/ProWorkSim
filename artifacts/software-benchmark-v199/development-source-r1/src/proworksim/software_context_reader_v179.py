"""Read-only, source-labeled view of an unchanged private history archive.

Metadata is structural, task-independent and never adds another member's data.
Source identities are returned only for complete messages in the actual page.
"""
import json
import re

from .software_context_recovery_v176 import HistoryEvidenceStore

VERSION='v179-source-labeled-recoverable-reader-r1'
REFERENCE_PATTERN=re.compile(r'^ctx:[0-9a-f]{24}$')


class SourceLabeledHistoryReader(HistoryEvidenceStore):
    def read(self,arguments,*,point_id,slot_id,member_id):
        value=super().read(arguments,point_id=point_id,slot_id=slot_id,member_id=member_id)
        entry=self.entries[arguments['reference']];start=value['start'];end=start+len(value['text'])
        citable=[]
        if entry.get('kind')=='original_closed_private_history':
            archived=json.loads(entry['text']);messages=dict(zip(
                (r['message_index'] for r in entry['message_offsets']),archived['messages']))
            actions={call['id']:index for index,m in messages.items() for call in m.get('tool_calls',[])}
            if start==0:
                value['message_offsets']=[{**row,
                    'tool_call_ids':[c['id'] for c in messages[row['message_index']].get('tool_calls',[])],
                    'paired_action_message_index':actions.get(messages[row['message_index']].get('tool_call_id'))}
                    for row in entry['message_offsets']]
            for row in entry['message_offsets']:
                if start<row['end'] and end>row['start']:
                    index=row['message_index'];m=messages[index]
                    item={'citation':{'reference':arguments['reference'],'message_index':index},
                        'message_complete_in_this_page':start<=row['start'] and end>=row['end'],
                        'paired_action_message_index':actions.get(m.get('tool_call_id'))}
                    if item['message_complete_in_this_page']:item.update(self.source_header(m))
                    citable.append(item)
        else:
            item={'citation':{'reference':arguments['reference'],'message_index':entry.get('message_index')},
                  'message_complete_in_this_page':start==0 and end==len(entry['text'])}
            if item['message_complete_in_this_page']:item.update(self.source_header({'role':'tool','content':entry['text']}))
            citable.append(item)
        value.update(reader_revision=VERSION,citable_messages=citable,
            citation_guidance='Copy citation objects exactly. Explanations belong in rationale, never in reference. Index entries alone do not mean message contents were read.')
        return value

    @staticmethod
    def source_header(message):
        if message.get('role')!='tool':return {}
        try:body=json.loads(message['content'])
        except (ValueError,TypeError,KeyError):return {}
        if not isinstance(body,dict):return {}
        result=body.get('result')
        if not isinstance(result,dict):return {}
        source=result.get('source_reference') or {}
        return {'source_identity':{'report_schema_version':result.get('version'),
            'workspace_object_id':source.get('object_id'),'workspace_version_id':source.get('version_id'),
            'workspace_files_sha256':result.get('files_sha256')},
            'source_identity_scope':'exact historical message; not validation of current workspace'}


def citation_format_feedback(answer,reads):
    """Format/read-receipt feedback only: no expected facts or answer oracle."""
    available={(x['citation']['reference'],x['citation']['message_index'])
        for r in reads if r.get('ok') for x in r['result'].get('citable_messages',[])}
    bad=[]
    for n,c in enumerate(answer.get('evidence',[])):
        if not isinstance(c,dict):bad.append({'item':n,'reason':'citation must be an object'});continue
        ref,index=c.get('reference'),c.get('message_index')
        if not isinstance(ref,str) or not REFERENCE_PATTERN.fullmatch(ref):
            bad.append({'item':n,'reason':'reference must be only the exact ctx identifier, without commentary'})
        elif type(index)is not int or (ref,index)not in available:
            bad.append({'item':n,'reason':'this message/reference has no actual read receipt; read it or omit the citation'})
    if not bad:return None
    return {'kind':'citation_format_or_read_receipt','problems':bad,
        'available_read_citations':[{'reference':r,'message_index':i} for r,i in sorted(available)],
        'facts_or_decisions_graded':False,'expected_answer_revealed':False,
        'instruction':'Correct reference formatting or unread citations. Facts are not evaluated here. You may make another permitted read or give corrected final JSON.'}
