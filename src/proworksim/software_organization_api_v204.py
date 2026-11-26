"""Independent 80 CNY trial ledger; whole-slot reservations protect started work.

Peak tariff upper accounting, authoritative provider token usage. No old ledger
imports, implicit network access, server tools, or ambiguous request replay.
"""
from __future__ import annotations
import json, sqlite3, time, uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from .storage import json_bytes, digest
from .software_benchmark_deepseek_api_v203_2_3 import DirectHTTPS, validate_payload, TransportFailure
from .software_benchmark_deepseek_contract_v105 import normalize_usage

VERSION='v204-independent-200-complete-block-r1'
CAP=200_000_000_000
class AdmissionStopped(RuntimeError): pass
class PrefixComplete(RuntimeError): pass

class Ledger:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS slots(id TEXT PRIMARY KEY,token_limit INTEGER NOT NULL,status TEXT NOT NULL,hold INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,slot TEXT NOT NULL,status TEXT NOT NULL,cost INTEGER NOT NULL,tokens INTEGER NOT NULL,body TEXT,provider_id TEXT UNIQUE);''')
            c.execute('INSERT OR IGNORE INTO meta VALUES (?,?)',('cap',str(CAP)))
            if c.execute('SELECT value FROM meta WHERE key="cap"').fetchone()[0]!=str(CAP):raise ValueError('Cash authority mismatch')
    @contextmanager
    def db(self):
        c=sqlite3.connect(self.path,timeout=60,isolation_level=None)
        try:
            c.execute('BEGIN IMMEDIATE');yield c;c.commit()
        except BaseException:c.rollback();raise
        finally:c.close()
    def reserve_block(self,block,slots):
        if not slots or any(type(n)!=int or not 0<n<=5_000_000 for n in slots.values()):raise ValueError('Invalid complete comparison block')
        with self.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS block_slots (slot TEXT PRIMARY KEY,block_id TEXT,token_limit INTEGER,status TEXT)')
            if any(c.execute('SELECT 1 FROM block_slots WHERE slot=?',(slot,)).fetchone() for slot in slots):raise ValueError('Block identities already consumed')
            closed=c.execute('SELECT COALESCE(SUM(cost),0) FROM requests WHERE slot IN (SELECT id FROM slots WHERE status="closed")').fetchone()[0]
            held=c.execute('SELECT COALESCE(SUM(hold),0) FROM slots WHERE status!="closed"').fetchone()[0]
            pending=c.execute('SELECT COALESCE(SUM(token_limit),0)*8000 FROM block_slots WHERE status="pending"').fetchone()[0]
            if closed+held+pending+sum(slots.values())*8000>CAP:raise AdmissionStopped('Cannot guarantee the entire paired block within independent 200')
            c.executemany('INSERT INTO block_slots VALUES (?,?,?,?)',[(slot,block,n,'pending') for slot,n in slots.items()])
    def admit(self,slot,limit):
        with self.db() as c:
            if c.execute('SELECT 1 FROM slots WHERE id=?',(slot,)).fetchone():raise ValueError('No replay')
            row=c.execute('SELECT token_limit,status FROM block_slots WHERE slot=?',(slot,)).fetchone()
            if row!=(limit,'pending'):raise AdmissionStopped('No complete-block cash authorization for this slot')
            c.execute('UPDATE block_slots SET status="active" WHERE slot=?',(slot,))
            c.execute('INSERT INTO slots VALUES (?,?,?,?)',(slot,limit,'active',limit*8000))
    def reserve(self,slot,request_id,upper):
        with self.db() as c:
            row=c.execute('SELECT token_limit,status,hold FROM slots WHERE id=?',(slot,)).fetchone()
            if not row or row[1]!='active':raise ValueError('Unadmitted slot')
            used=c.execute('SELECT COALESCE(SUM(tokens),0) FROM requests WHERE slot=?',(slot,)).fetchone()[0]
            if used+upper>row[0]:raise PrefixComplete('Stage token reservation ceiling reached before dispatch')
            if c.execute('SELECT 1 FROM requests WHERE slot=? AND status!="settled" AND status!="http_error"',(slot,)).fetchone():raise ValueError('Unsettled request; no replay')
            c.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?)',(request_id,slot,'reserved',upper*8000,upper,None,None))
    def settle(self,rid,body):
        u=normalize_usage(body)
        with self.db() as c:
            row=c.execute('SELECT tokens,status FROM requests WHERE id=?',(rid,)).fetchone()
            if not row or row[1]!='reserved':raise ValueError('Duplicate settlement')
            c.execute('UPDATE requests SET status="settled",cost=?,tokens=?,body=?,provider_id=? WHERE id=?',
                (u['peak_cost_nanoyuan'],u['total_tokens'],json.dumps(u),u['provider_response_id'],rid))
            if u['total_tokens']>row[0]:
                # Persist actual usage before reporting a broken reservation contract.
                c.commit();raise ValueError('Provider actual exceeds frozen request token reservation')
        return u
    def http_error(self,rid):
        with self.db() as c:c.execute('UPDATE requests SET status="http_error",cost=0,tokens=0 WHERE id=? AND status="reserved"',(rid,))
    def close(self,slot):
        with self.db() as c:
            uncertain=c.execute('SELECT COUNT(*) FROM requests WHERE slot=? AND status="reserved"',(slot,)).fetchone()[0]
            c.execute('UPDATE slots SET status=? WHERE id=?',('uncertain' if uncertain else 'closed',slot))
    def snapshot(self):
        with self.db() as c:
            rows=[dict(zip(('id','slot','status','cost_nanoyuan','tokens','usage'),r)) for r in c.execute('SELECT id,slot,status,cost,tokens,body FROM requests')]
            slots=[dict(zip(('id','token_limit','status','cash_hold_nanoyuan'),r)) for r in c.execute('SELECT * FROM slots')]
        return {'version':VERSION,'cap_CNY':200,'peak_cost_upper_CNY':sum(r['cost_nanoyuan'] for r in rows if r['status']=='settled')/1e9,
            'actual_tokens':sum(r['tokens'] for r in rows if r['status']=='settled'),'requests':rows,'slots':slots,'unknown_reservations_are_actual_cost':False}

class Backend:
    def __init__(self,folder,ledger,slot,counter,transport,allowed_tools, *, members=("member_001","member_002")):
        self.members=frozenset(members)
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.ledger,self.slot,self.counter,self.transport,self.allowed_tools=ledger,slot,counter,transport,set(allowed_tools)
        self.requests=0
    def post(self,route,payload):
        wire=payload['wire']
        if route=='/tokenize-prefix':
            from .software_benchmark_deepseek_prefix_v055_r2 import count_incomplete_prefix
            n=count_incomplete_prefix(SimpleNamespace(counter=self.counter,folder=self.folder),wire,tuple(payload['pending_ids']))
            return {'prompt_tokens':n,'request_sha256':digest(json_bytes(wire)),'method':'official_original_member_incomplete_prefix','count_only_not_dispatchable':True}
        if route=='/tokenize':return self.counter.measure(wire)
        if route!='/chat/completions':raise ValueError('Unknown endpoint')
        if payload.get('team_slot_id')!=self.slot or payload.get('member_id') not in self.members:raise ValueError('Foreign slot/member')
        validate_payload(wire,self.allowed_tools,payload['usage_id'])
        estimate=self.counter.measure(wire)
        if estimate['prompt_tokens']>98304:raise ValueError('Experimental full-input bound')
        upper=estimate['prompt_tokens']+wire['max_tokens']
        for attempt in range(3):
            rid=self.slot+':'+str(uuid.uuid4());self.ledger.reserve(self.slot,rid,upper)
            d=self.folder/rid.rsplit(':',1)[-1];d.mkdir()
            (d/'request.json').write_bytes(json_bytes({'physical_id':rid,'payload':payload,'count':estimate,'time':time.time()}))
            def capture(kind,raw,context,metadata):
                (d/(kind.lower()+'.raw')).write_bytes(raw)
                (d/(kind.lower()+'.json')).write_bytes(json_bytes(metadata))
            self.transport.physical_capture=capture
            self.requests+=1
            try:body=self.transport.request('POST','/chat/completions',wire)
            except TransportFailure as error:
                (d/'error.json').write_bytes(json_bytes(error.evidence))
                if error.evidence['error_code']=='complete_http_error_response':self.ledger.http_error(rid)
                if error.retryable and attempt<2:
                    time.sleep(min(30,error.evidence.get('retry_after_seconds') or 2**attempt));continue
                raise
            (d/'response.json').write_bytes(json_bytes(body))
            usage=self.ledger.settle(rid,body)
            (d/'usage.json').write_bytes(json_bytes(usage))
            if getattr(self.transport,'capture_faults',0):raise ValueError('Request raw capture failed')
            return body
        raise AssertionError('retry loop')
