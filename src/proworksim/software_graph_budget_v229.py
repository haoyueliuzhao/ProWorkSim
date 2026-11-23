"""Keep a complete-pair reservation until prefix usage and the frozen candidate are known."""
import sqlite3
from pathlib import Path
from .software_organization_api_v204 import Ledger,AdmissionStopped

LIMIT=5_000_000
PRICE=8000
NANO=10**9


class WindowLedger(Ledger):
    def __init__(self, authority):
        self.path=Path(authority['ledger'])
        self.cap=authority['account_cap_CNY']*NANO
        self.stage=authority['stage_cap_CNY']*NANO
        if not self.path.is_file() or min(self.cap,self.stage)<=0 or self.stage>self.cap:
            raise ValueError('Funded account required')

    @classmethod
    def create_independent(cls,authority):
        path=Path(authority['ledger'])
        if authority['scope']!='independent' or path.exists():raise ValueError('Fresh independent account required')
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb'):pass
        with sqlite3.connect(path) as c:
            c.executescript('''
            CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE slots(id TEXT PRIMARY KEY,token_limit INTEGER NOT NULL,status TEXT NOT NULL,hold INTEGER NOT NULL);
            CREATE TABLE requests(id TEXT PRIMARY KEY,slot TEXT NOT NULL,status TEXT NOT NULL,cost INTEGER NOT NULL,tokens INTEGER NOT NULL,body TEXT,provider_id TEXT UNIQUE);
            CREATE TABLE block_slots(slot TEXT PRIMARY KEY,block_id TEXT,token_limit INTEGER,status TEXT);
            ''')
            c.execute('INSERT INTO meta VALUES(?,?)',('cap',str(authority['account_cap_CNY']*NANO)))
        return cls(authority)

    def reserve_case(self,key):
        if not key.startswith('v229:'):raise ValueError('Unexpected namespace')
        def worst(c,pattern):
            rows=c.execute("""SELECT s.status,s.token_limit,coalesce(sum(r.cost),0),
                coalesce(sum(CASE WHEN r.status='settled' THEN r.tokens ELSE 0 END),0),
                coalesce(sum(CASE WHEN r.status='settled' THEN r.cost ELSE 0 END),0)
                FROM slots s LEFT JOIN requests r ON r.slot=s.id WHERE s.id GLOB ? GROUP BY s.id""",(pattern,))
            existing=sum(cost if status=='closed' else max(cost,paid+max(0,limit-used)*PRICE)
                         for status,limit,cost,used,paid in rows)
            held=c.execute("SELECT coalesce(sum(token_limit),0) FROM block_slots WHERE status='pending' AND slot GLOB ?",(pattern,)).fetchone()[0]
            return existing+held*PRICE
        with self.db() as c:
            if c.execute("SELECT value FROM meta WHERE key='cap'").fetchone()!=(str(self.cap),):raise ValueError('Account cap differs')
            if worst(c,'*')+2*LIMIT*PRICE>self.cap or worst(c,'v229:*')+2*LIMIT*PRICE>self.stage:
                raise AdmissionStopped('Complete pair would exceed approved allowance')
            c.executemany("INSERT INTO block_slots VALUES(?,?,?,'pending')",[(key+':'+s,key,LIMIT) for s in ('PREFIX','HOLD')])

    def close(self,slot):
        if not slot.endswith(':PREFIX'):return super().close(slot)
        # Still reserves its unused capacity. Coordinator converts it within one transaction.
        with self.db() as c:
            uncertain=c.execute("SELECT 1 FROM requests WHERE slot=? AND status='reserved'",(slot,)).fetchone()
            c.execute("UPDATE slots SET status=? WHERE id=?",('uncertain' if uncertain else 'awaiting_split',slot))

    def split(self,key,arms,expected_tokens):
        if tuple(arms) not in ((),('KEEP',),('KEEP','CHANGE')):raise ValueError('Invalid support')
        prefix=key+':PREFIX'
        with self.db() as c:
            status=c.execute('SELECT status FROM slots WHERE id=?',(prefix,)).fetchone()
            if c.execute("SELECT status FROM block_slots WHERE slot=?",(key+':HOLD',)).fetchone()!=('pending',):
                raise ValueError('Pair allocation already consumed')
            if status not in (('awaiting_split',),None) and arms:raise ValueError('Unsettled prefix')
            used=c.execute("SELECT coalesce(sum(tokens),0) FROM requests WHERE slot=? AND status='settled'",(prefix,)).fetchone()[0]
            if arms and (not status or used!=expected_tokens or used>=LIMIT):raise ValueError('Native prefix/OSA accounting mismatch')
            c.execute("UPDATE slots SET status='closed' WHERE id=? AND status='awaiting_split'",(prefix,))
            c.execute("UPDATE block_slots SET status='released' WHERE slot IN (?,?) AND status='pending'",(prefix,key+':HOLD'))
            c.executemany("INSERT INTO block_slots VALUES(?,?,?,'pending')",[(key+':'+s,key,LIMIT-used) for s in arms])
        return LIMIT-used
