"""Observe exact HTTP/80 framing; exempt only proved completed idle exchanges.

Forwarded bytes, endpoint, transport limits, close timing and TLS handling stay
in the frozen relay. A bounded raw HTTP journal allows independent replay of
every new idle classification. HTTPS is opaque and never receives an exemption.
"""
from __future__ import annotations
import base64
import copy
import hashlib
import inspect
import json
import math
from pathlib import Path
import sys

from . import software_benchmark_tcp_transport_v066 as frozen
from . import software_benchmark_http_framing_v203_2_3_r4 as framing
from .software_benchmark_candidates_v054 import checked, reference

VERSION='v203.2.3-proven-http-idle-transport-r4'
MAX_RAW_BYTES=64*1024**2
MAX_JOURNAL_BYTES=128*1024**2
MAX_RECORDS=200000


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)


def portable_parser():
    descriptor=framing.parser_descriptor()
    return {**{key:value for key,value in descriptor.items() if key!='sources'},
            'sources':[{key:row[key] for key in ('name','sha256','bytes')} for row in descriptor['sources']]}


def idle_allowed(proof,*,port,upstream_pending,docker_pending,audit_usable=True):
    return (audit_usable is True and type(port) is int and port==80
            and type(upstream_pending) is int and upstream_pending==0
            and type(docker_pending) is int and docker_pending==0
            and proof.get('eligible') is True and proof.get('complete_framing') is True
            and proof.get('pending_responses')==0
            and proof.get('buffered_client_bytes')==0 and proof.get('buffered_server_bytes')==0
            and proof.get('requests_completed',0)>0
            and proof.get('requests_completed')==proof.get('responses_completed'))


class HTTPAudit:
    def __init__(self,path):
        self.path=Path(path) if path is not None else None
        self.stream=None;self.failure=None;self.events=0;self.raw_bytes=0;self.file_bytes=0
        self.digest=hashlib.sha256();self.trackers={};self.ports={};self.exemptions=[]
        try:
            if self.path is None:raise ValueError('No owned HTTP capture path was bound')
            self.path.parent.mkdir(parents=True,exist_ok=True)
            self.stream=self.path.open('xb')
        except Exception as error:self.failure=type(error).__name__+': '+str(error)[:256]
        self.record({'event':'header','version':VERSION,'parser':framing.parser_descriptor(),
                     'tracker_source':reference(framing.__file__),'TLS_payloads_retained':False})

    def record(self,row):
        if self.failure:return None
        sequence=self.events
        body=(canonical({'sequence':sequence,**row})+'\n').encode()
        if self.events>=MAX_RECORDS or self.file_bytes+len(body)>MAX_JOURNAL_BYTES:
            self.failure='HTTP audit record/file bound exceeded';return None
        try:
            if self.stream.write(body)!=len(body):raise OSError('Incomplete HTTP audit write')
            self.digest.update(body);self.events+=1;self.file_bytes+=len(body)
            return sequence
        except Exception as error:
            self.failure=type(error).__name__+': '+str(error)[:256]
            return None

    def opened(self,identity,port,opened_since_start):
        if identity in self.trackers:
            self.failure='Duplicate HTTP audit connection';return
        self.ports[identity]=port
        self.trackers[identity]=framing.HTTPKeepaliveTracker(port=port)
        self.record({'event':'open','connection_id':identity,'port':port,
                     'opened_since_start':opened_since_start})

    def feed(self,identity,direction,data):
        if self.ports.get(identity)!=80:return
        self.raw_bytes+=len(data)
        if self.raw_bytes>MAX_RAW_BYTES:
            self.failure='HTTP raw payload bound exceeded';return
        self.record({'event':'data','connection_id':identity,'direction':direction,
                     'data_base64':base64.b64encode(data).decode(),'bytes':len(data)})
        try:
            tracker=self.trackers[identity]
            (tracker.feed_client if direction=='client' else tracker.feed_server)(data)
        except Exception as error:self.failure='HTTP observer failed: '+type(error).__name__

    def server_eof(self,identity):
        self.record({'event':'server_eof','connection_id':identity})
        try:self.trackers[identity].server_eof()
        except Exception as error:self.failure='HTTP observer EOF failed: '+type(error).__name__

    def proof(self,identity):
        try:return self.trackers[identity].proof()
        except Exception as error:return {'eligible':False,'reason':'HTTP observer proof failed: '+type(error).__name__}

    def idle(self,identity,*,upstream_pending,docker_pending,elapsed,idle_seconds,idle_limit):
        proof=self.proof(identity);port=self.ports.get(identity)
        allowed=idle_allowed(proof,port=port,upstream_pending=upstream_pending,
                             docker_pending=docker_pending,audit_usable=self.failure is None)
        row={'event':'idle','connection_id':identity,'port':port,'framing':proof,
             'upstream_pending':upstream_pending,'docker_pending':docker_pending,
             'elapsed':elapsed,'idle_seconds':idle_seconds,'idle_limit':idle_limit,
             'benign_completed_keepalive':allowed,'test_success_claimed':False}
        sequence=self.record(row)
        if self.failure or sequence is None:return False
        if allowed:
            self.exemptions.append({'connection_id':identity,'audit_sequence':sequence,
                'framing_sha256':hashlib.sha256(canonical(proof).encode()).hexdigest(),
                'upstream_pending':upstream_pending,'docker_pending':docker_pending})
        return allowed

    def closed(self,identity,**state):
        proof=self.proof(identity)
        self.record({'event':'close','connection_id':identity,'framing':proof,**state})
        return {'framing':proof,**state}

    def finish(self):
        self.record({'event':'end','raw_http_bytes':self.raw_bytes,'records_before_end':self.events})
        if self.stream is not None:
            try:self.stream.flush();self.stream.close()
            except Exception as error:self.failure='HTTP audit close failed: '+type(error).__name__
        return {'version':VERSION,'usable':self.failure is None,'error':self.failure,
                'raw_http_bytes':self.raw_bytes,'records':self.events,
                'capture':({'path':str(self.path),'sha256':self.digest.hexdigest(),'bytes':self.file_bytes}
                           if self.path and self.path.exists() else None),
                'maximum_raw_bytes':MAX_RAW_BYTES,'maximum_capture_bytes':MAX_JOURNAL_BYTES,
                'TLS_payloads_retained':False,'idle_exemptions':copy.deepcopy(self.exemptions)}


def instrumented_source():
    source=inspect.getsource(frozen.relay_many)
    replacements=[
      ('    start = clock()\n','    start = clock()\n    audit = _HTTPAudit(_capture_context["path"])\n'),
      ('        item.record.update(outcome=outcome, duration_seconds=max(0.0, clock() - item.record.pop("started_at")))',
       '        closed_at = clock()\n        opened_at = item.record.pop("started_at")\n'
       '        item.record.update(outcome=outcome, duration_seconds=max(0.0, closed_at - opened_at))\n'
       '        item.record["http_observation"] = audit.closed(identity, outcome=outcome,\n'
       '            opened_since_start=opened_at-start, closed_since_start=closed_at-start,\n'
       '            last_progress_since_start=item.last_progress-start, client_eof=item.client_eof,\n'
       '            remote_eof=item.remote_eof, upstream_pending=len(item.outgoing), docker_pending=len(outgoing))'),
      ('                    finish_connection(identity, "upstream_idle_timeout", network_error="Connection idle deadline exceeded")',
       '                    benign = audit.idle(identity, upstream_pending=len(item.outgoing), docker_pending=len(outgoing),\n'
       '                        elapsed=now-start, idle_seconds=now-item.last_progress, idle_limit=limits.idle_seconds)\n'
       '                    if benign:\n                        finish_connection(identity, "completed_http_keepalive_idle_close")\n'
       '                    else:\n                        finish_connection(identity, "upstream_idle_timeout", network_error="Connection idle deadline exceeded")'),
      ('                                connections[identity] = _Connection(identity, peer, record, clock())',
       '                                connections[identity] = _Connection(identity, peer, record, clock())\n'
       '                                audit.opened(identity, port, record["started_at"]-start)'),
      ('                        consume(count, "bytes_to_upstream", item.record)',
       '                        consume(count, "bytes_to_upstream", item.record)\n'
       '                        audit.feed(identity, "client", bytes(item.outgoing[:count]))'),
      ('                            consume(len(data), "bytes_from_upstream", item.record)',
       '                            consume(len(data), "bytes_from_upstream", item.record)\n'
       '                            audit.feed(identity, "server", data)'),
      ('                            item.remote_eof = True',
       '                            item.remote_eof = True\n                            audit.server_eof(identity)'),
      ('    return result\n',
       '    result["http_frame_audit"] = audit.finish()\n'
       '    if not result["http_frame_audit"]["usable"]:\n'
       '        result.update(ok=False, status="failed", error={"type":"HTTPAuditFailure", "message":result["http_frame_audit"]["error"]})\n'
       '    return result\n')]
    original=source
    for before,after in replacements:
        if source.count(before)!=1:raise ValueError('Frozen relay observation seam changed')
        source=source.replace(before,after)
    restored=source
    for before,after in reversed(replacements):restored=restored.replace(after,before)
    if restored!=original:raise ValueError('A relay statement outside the declared observation seams changed')
    return source


def bind_transport(transport):
    if sys.modules.get(getattr(transport,'__name__','')) is transport:
        raise ValueError('Only a private per-scorer transport namespace may be bound')
    context={'path':None}
    namespace={**transport.relay_many.__globals__,'_HTTPAudit':HTTPAudit,
               '_capture_context':context,'VERSION':VERSION}
    compiled={}
    exec(compile(instrumented_source(),__file__+':observed-relay','exec'),namespace,compiled)
    transport.relay_many=compiled['relay_many']
    transport.__file__=__file__
    transport.http_capture_context=context
    return transport


def validate_capture(audit,*,expected_path):
    if audit.get('version')!=VERSION or audit.get('usable') is not True:
        raise ValueError('A complete raw HTTP capture is required')
    ref=audit['capture']
    if Path(ref['path']).resolve()!=Path(expected_path).resolve() or ref['bytes']>MAX_JOURNAL_BYTES:
        raise ValueError('HTTP capture is outside its owned scorer or size bound')
    data=checked(ref).read_bytes();rows=[json.loads(line) for line in data.splitlines()]
    if not rows or len(rows)>MAX_RECORDS or len(rows)!=audit['records']:
        raise ValueError('HTTP capture record count differs')
    if [row.get('sequence') for row in rows]!=list(range(len(rows))):raise ValueError('HTTP capture ordering changed')
    header=rows[0]
    if header.get('event')!='header' or header.get('version')!=VERSION:raise ValueError('HTTP capture header missing')
    descriptor=header['parser']
    portable={**{k:v for k,v in descriptor.items() if k!='sources'},
              'sources':[{k:r[k] for k in ('name','sha256','bytes')} for r in descriptor['sources']]}
    if portable!=portable_parser() or header['tracker_source']!=reference(framing.__file__):
        raise ValueError('HTTP parser bytes/version differ from the observed code')
    for source in descriptor['sources']:checked({key:source[key] for key in ('path','sha256','bytes')})
    trackers={};ports={};exemptions=[];raw_bytes=0;closed=set()
    for row in rows[1:-1]:
        identity=row.get('connection_id');event=row.get('event')
        if event=='open':
            if identity in trackers or type(identity) is not int or not 1<=identity<=512:
                raise ValueError('Duplicate/invalid HTTP connection')
            ports[identity]=row['port'];trackers[identity]=framing.HTTPKeepaliveTracker(port=row['port']);continue
        if identity not in trackers or identity in closed:raise ValueError('HTTP event outside its live connection')
        tracker=trackers[identity]
        if event=='data':
            if ports[identity]!=80:raise ValueError('TLS bytes may not be interpreted or retained')
            body=base64.b64decode(row['data_base64'],validate=True);raw_bytes+=len(body)
            if len(body)!=row['bytes'] or raw_bytes>MAX_RAW_BYTES:raise ValueError('HTTP data length/budget differs')
            if row['direction']=='client':tracker.feed_client(body)
            elif row['direction']=='server':tracker.feed_server(body)
            else:raise ValueError('Unknown HTTP direction')
        elif event=='server_eof':tracker.server_eof()
        elif event=='idle':
            proof=tracker.proof()
            if proof!=row['framing'] or row.get('port')!=ports[identity]:raise ValueError('HTTP idle proof differs from raw stream')
            allowed=idle_allowed(proof,port=ports[identity],upstream_pending=row['upstream_pending'],docker_pending=row['docker_pending'])
            if (any(type(row[key]) not in (int,float) or not math.isfinite(row[key])
                    for key in ('elapsed','idle_seconds','idle_limit'))
                    or row['benign_completed_keepalive'] is not allowed or row['idle_seconds']<row['idle_limit']
                    or not 0<row['idle_limit']<=60):raise ValueError('HTTP idle decision violates the frozen proof gate')
            if allowed:exemptions.append({'connection_id':identity,'audit_sequence':row['sequence'],
                'framing_sha256':hashlib.sha256(canonical(proof).encode()).hexdigest(),
                'upstream_pending':row['upstream_pending'],'docker_pending':row['docker_pending']})
        elif event=='close':
            if row['framing']!=tracker.proof():raise ValueError('Final HTTP framing proof differs')
            closed.add(identity)
        else:raise ValueError('Unknown HTTP capture event')
    if (rows[-1].get('event')!='end' or rows[-1]['raw_http_bytes']!=raw_bytes
            or rows[-1]['records_before_end']!=len(rows)-1
            or raw_bytes!=audit['raw_http_bytes'] or set(trackers)!=closed
            or audit['idle_exemptions']!=exemptions):raise ValueError('Incomplete HTTP audit or mismatched exemption list')
    return {'raw_capture_replayed':True,'connections':len(trackers),'raw_http_bytes':raw_bytes,
            'proved_completed_idle_closures':len(exemptions),'capture':ref}
