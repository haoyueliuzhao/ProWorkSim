"""Actual-request context corpus, with source estimates kept separate from usage.

All text originates in retained provider payloads. Outcomes are analysis labels,
never replay input. No source inferred by text equality; original provenance
offsets remain the authoritative link for every exposure.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from . import software_input_provenance_v156 as provenance
from .software_benchmark_candidates_v054 import checked,reference
from .software_collaboration_observation_v141 import load_official_content_counter

ROOT=Path(__file__).resolve().parents[2]
VERSION='v175-actual-context-source-corpus-r1'
COUNTER=None
TOKENIZER=None
PATH_RE=re.compile(r'(?<!\w)(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+|\b[A-Za-z_][\w.-]*\.(?:py|js|ts|json|yaml|yml|toml|cfg|ini|md|rst)\b')
VERSION_RE=re.compile(r'\b(?:[a-f0-9]{40}|[a-f0-9]{64}|patch-\d+|delivery-\d+|v\d+)\b')


def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(text):return hashlib.sha256(text.encode()).hexdigest()
def load(ref):return json.loads(checked(ref).read_bytes())


def initialize():
    global COUNTER,TOKENIZER
    manifest=ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
    counter,TOKENIZER=load_official_content_counter(manifest,manifest_sha256=reference(manifest)['sha256'])
    COUNTER=lru_cache(maxsize=65536)(counter)


def annotate(text,*,role,tool_name):
    kinds=[]
    if re.search(r'(?m)^(?:diff --git|@@ |\+\+\+ |--- a/)',text):kinds.append('code_diff')
    if tool_name in {'run_tests','read_test_result'} or re.search(r'\b(?:FAILED|Traceback|pytest|test_evidence)\b',text):kinds.append('test_report')
    if tool_name in {'read_file','search_file','search_repository','diff_workspace'}:kinds.append('code_or_file')
    if tool_name in {'org_status','read_task','delivery_status','org_review_patch'}:kinds.append('task_state')
    if re.search(r'"(?:source_reference|version_id|files_sha256|patch_id)"',text):kinds.append('version_information')
    if role in {'user','tool'} and not kinds:kinds.append('natural_language_or_mixed')
    paths=sorted(set(PATH_RE.findall(text)))
    versions=sorted(set(VERSION_RE.findall(text)))
    lines=text.splitlines()
    risks=[{'line':i,'text':line[:2048]} for i,line in enumerate(lines)
        if re.search(r'\b(?:fail(?:ed|ure)?|error|risk|unknown|unresolved|blocked|unverified)\b|失败|错误|风险|未解决|未知',line,re.I)]
    return {'content_kinds':kinds,'path_literals':paths[:256],'version_literals':versions[:256],
        'risk_or_unresolved_lines':risks[:64],'annotation_method':'structural_tool_name_and_literal_regex_not_gold_semantics',
        'literal_caps':{'paths':256,'versions':256,'risk_lines':64},
        'literal_caps_reached':len(paths)>256 or len(versions)>256 or len(risks)>64,
        'sender_claims_independently_verified':False}


def process_request(job):
    if COUNTER is None:initialize()
    receipt=load(job['receipt']);capture=receipt['request_capture']
    built=provenance.load_persisted_request(capture)  # One exact span validation.
    payload=json.loads(built.payload_bytes);identity=built.manifest['identity']
    if identity['episode_id']!=job['slot_id'] or identity['request_id']!=job['request_id']:
        raise ValueError('Frozen canonical episode/capture identity changed')
    categories=Counter({k:0 for k in provenance.PRIMARY_CATEGORIES});unknown=0
    units_sources=defaultdict(dict);unit_categories=defaultdict(Counter)
    # Each text/key/scalar occurs once; API totals are never proportionally split.
    for span in built.manifest['spans']:
        if not span['semantic_input'] or span['kind']=='json_syntax':continue
        raw=built.payload_bytes[span['payload_start']:span['payload_end']]
        if span['kind'] in {'text_fragment','unannotated_text'}:text=json.loads('"'+raw.decode()+'"')
        elif span['kind']=='json_key':text=json.loads(raw)
        else:text=raw.decode()
        n=COUNTER(text);source=span['source'];category=source['category'] if source else 'Unattributed'
        if source:categories[category]+=n
        else:unknown+=n
        parts=span['json_pointer'].split('/')
        if len(parts)>=4 and parts[1]=='messages' and parts[2].isdigit():
            m=int(parts[2]);unit_categories[m][category]+=n
            if source:
                key=(source['category'],source['origin_event_id'],source['origin_member_id'],
                    source.get('version_sha256'),source.get('artifact_sha256'),source['transformation'])
                units_sources[m][key]={'category':source['category'],'origin_event_id':source['origin_event_id'],
                    'origin_member_id':source['origin_member_id'],'version_sha256':source.get('version_sha256'),
                    'artifact_sha256':source.get('artifact_sha256'),'transformation':source['transformation']}
    units=[]
    for i,message in enumerate(payload['messages']):
        content=message.get('content')
        if not isinstance(content,str):continue
        sources=list(units_sources[i].values());tool=message.get('name')
        units.append({'unit_id':sha(canonical({'role':message['role'],'name':tool,'content':content})),
            'text':content,'role':message['role'],'tool_name':tool,'characters':len(content),
            'estimated_content_tokens':COUNTER(content),'annotations':annotate(content,role=message['role'],tool_name=tool),
            'message_index':i,'tool_call_id':message.get('tool_call_id'),
            'json_pointer':'/messages/'+str(i)+'/content','sources':sources,
            'primary_estimated_tokens':dict(unit_categories[i]),
            'recipient':identity['member_id'],'request_time':identity['request_time'],
            'task_state_pointer':'/messages/'+str(len(payload['messages'])-1)+'/content',
            'model_input_before_this_response':True,'later_behavioral_use':None,
            'later_behavioral_use_reason':'not_inferred_from_presentation_or_final_score'})
    total=sum(categories.values())+unknown
    return {'request_id':identity['request_id'],'slot_id':identity['episode_id'],
        'member_id':identity['member_id'],'purpose':identity.get('usage_id'),
        'request_time':identity['request_time'],'physical_receipt':job['receipt'],
        'capture':capture,'provider_usage':receipt['response_metadata']['usage'],
        'source_estimates':dict(categories),'unknown_estimated_tokens':unknown,
        'estimated_fragment_total':total,'unknown_fraction':unknown/total if total else 0,
        'whole_messages_tools_estimated_tokens':COUNTER(canonical({k:v for k,v in payload.items() if k in {'messages','tools'}})),
        'source_estimates_are_not_provider_decomposition':True,'tokenizer':TOKENIZER,
        'units':units}


SCHEMA='''
CREATE TABLE IF NOT EXISTS episodes(slot_id TEXT PRIMARY KEY, metadata TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS requests(request_id TEXT PRIMARY KEY, slot_id TEXT NOT NULL, member_id TEXT,
  purpose TEXT, request_time TEXT, metadata TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS units(unit_id TEXT PRIMARY KEY, role TEXT, tool_name TEXT, text TEXT NOT NULL,
  characters INTEGER, local_tokens INTEGER, annotations TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS exposures(request_id TEXT, message_index INTEGER, unit_id TEXT,
  source_binding TEXT NOT NULL, PRIMARY KEY(request_id,message_index));
CREATE INDEX IF NOT EXISTS exposures_unit ON exposures(unit_id);
CREATE INDEX IF NOT EXISTS requests_slot ON requests(slot_id);
'''


def open_dataset(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path);db.executescript(SCHEMA)
    return db


def retain_request(db,value):
    units=value.pop('units')
    with db:
        db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?)',(value['request_id'],value['slot_id'],
            value['member_id'],value['purpose'],value['request_time'],canonical(value)))
        for unit in units:
            db.execute('INSERT OR IGNORE INTO units VALUES(?,?,?,?,?,?,?)',(unit['unit_id'],unit['role'],
                unit['tool_name'],unit['text'],unit['characters'],unit['estimated_content_tokens'],canonical(unit['annotations'])))
            binding={k:v for k,v in unit.items() if k not in {'text','annotations'}}
            db.execute('INSERT INTO exposures VALUES(?,?,?,?)',(value['request_id'],unit['message_index'],
                unit['unit_id'],canonical(binding)))


def restore_unit(db,request_id,message_index,*,slot_id,member_id):
    row=db.execute('SELECT r.slot_id,r.member_id,u.text,e.source_binding FROM exposures e '
        'JOIN requests r ON r.request_id=e.request_id JOIN units u ON u.unit_id=e.unit_id '
        'WHERE e.request_id=? AND e.message_index=?',(request_id,message_index)).fetchone()
    if not row or row[0]!=slot_id or row[1]!=member_id:
        raise PermissionError('Only content actually presented to this same episode/member is recoverable')
    return row[2],json.loads(row[3])
