"""New 700-CNY ledger; mechanism phase 220 estimated admission, global worst-price guard.

Existing 200-CNY ledger cannot be opened here. Started slots are never cash-killed;
remaining token worst-price exposure protects the total ceiling at block admission.
"""
import sqlite3
from pathlib import Path
from .software_organization_api_v204 import Ledger as Base, Backend, DirectHTTPS, AdmissionStopped, PrefixComplete
CAP=700_000_000_000;PHASE=220_000_000_000;ESTIMATE=10_500_000_000
class Ledger(Base):
 def __init__(self,path):
  self.path=Path(path)
  if self.path.exists():
   with sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True) as prior:
    if prior.execute('SELECT value FROM meta WHERE key="cap"').fetchone()!=(str(CAP),):raise ValueError('Wrong independent batch cash authority; not modified')
  self.path.parent.mkdir(parents=True,exist_ok=True)
  with self.db() as c:
   c.executescript('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS slots(id TEXT PRIMARY KEY,token_limit INTEGER NOT NULL,status TEXT NOT NULL,hold INTEGER NOT NULL); CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,slot TEXT NOT NULL,status TEXT NOT NULL,cost INTEGER NOT NULL,tokens INTEGER NOT NULL,body TEXT,provider_id TEXT UNIQUE); CREATE TABLE IF NOT EXISTS block_slots(slot TEXT PRIMARY KEY,block_id TEXT,token_limit INTEGER,status TEXT);')
   c.execute('INSERT OR IGNORE INTO meta VALUES (?,?)',('cap',str(CAP)))
   c.execute('INSERT OR IGNORE INTO meta VALUES (?,?)',('mechanism_phase_estimated_start_line',str(PHASE)))
   if c.execute('SELECT value FROM meta WHERE key="cap"').fetchone()[0]!=str(CAP):raise ValueError('Wrong independent batch cash authority')
 def exposure(self,c):
  rows=c.execute('SELECT s.status,s.token_limit,s.hold,COALESCE(SUM(r.cost),0),COALESCE(SUM(r.tokens),0) FROM slots s LEFT JOIN requests r ON s.id=r.slot GROUP BY s.id').fetchall()
  estimated=sum(cost if status=='closed' else max(hold,cost) for status,limit,hold,cost,tokens in rows)
  worst=sum(cost if status=='closed' else cost+max(0,limit-tokens)*8000 for status,limit,hold,cost,tokens in rows)
  pending=c.execute('SELECT token_limit FROM block_slots WHERE status="pending"').fetchall()
  estimated+=sum(min(ESTIMATE,limit*8000) for (limit,) in pending);worst+=sum(limit*8000 for (limit,) in pending)
  return estimated,worst
 def reserve_block(self,block,slots):
  if not slots or any(type(n)!=int or not 0<n<=5_000_000 for n in slots.values()):raise ValueError('Whole complete block required')
  with self.db() as c:
   if any(c.execute('SELECT 1 FROM block_slots WHERE slot=?',(s,)).fetchone() for s in slots):raise ValueError('Identity already used')
   estimated,worst=self.exposure(c)
   if estimated+sum(min(ESTIMATE,n*8000) for n in slots.values())>PHASE:raise AdmissionStopped('Mechanism phase estimated new-block line reached')
   if worst+sum(n*8000 for n in slots.values())>CAP:raise AdmissionStopped('Global worst-price bound; wait for active blocks to release')
   c.executemany('INSERT INTO block_slots VALUES (?,?,?,?)',[(s,block,n,'pending') for s,n in slots.items()])
 def admit(self,slot,limit):
  with self.db() as c:
   if c.execute('SELECT 1 FROM slots WHERE id=?',(slot,)).fetchone():raise ValueError('No replay')
   if c.execute('SELECT token_limit,status FROM block_slots WHERE slot=?',(slot,)).fetchone()!=(limit,'pending'):raise AdmissionStopped('No complete block allocation')
   c.execute('UPDATE block_slots SET status="active" WHERE slot=?',(slot,));c.execute('INSERT INTO slots VALUES (?,?,?,?)',(slot,limit,'active',min(ESTIMATE,limit*8000)))
 def snapshot(self):
  v=super().snapshot()
  with self.db() as c:e,w=self.exposure(c)
  return {**v,'version':'v211-independent-700-mechanism-220-r1','cap_CNY':700,'phase_estimated_start_line_CNY':220,'estimated_exposure_CNY':e/1e9,'worst_exposure_CNY':w/1e9,'old_balance_transferred':False}
