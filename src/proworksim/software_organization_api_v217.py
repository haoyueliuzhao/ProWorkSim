"""Audit-authorized 28-state experiment in the existing ledger amended to 1100 CNY ledger.

Protect 392 CNY confirmation planning, preserve all old costs and started slots.
Whole candidate blocks only; global remaining-token worst price guard unchanged.
"""
from .software_organization_api_v211 import Ledger as Prior,Backend,DirectHTTPS,AdmissionStopped
from pathlib import Path
CAP=1_100_000_000_000
START_COST=313_707_097_680
REMAINING=CAP-START_COST
CONFIRM_PLAN=392_000_000_000
DEV_LIMIT=REMAINING-CONFIRM_PLAN
VERSION='v217-shared1100-confirmation-reserved-r1'
def estimate(slot,n):return min(n*8000,1_800_000_000 if slot.endswith(':PREFIX') else 200_000_000 if slot.endswith(':GENERATOR') else 7_500_000_000)
class Ledger(Prior):
 def __init__(self,path):
  self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
  with self.db() as c:
   c.executescript('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS slots(id TEXT PRIMARY KEY,token_limit INTEGER NOT NULL,status TEXT NOT NULL,hold INTEGER NOT NULL); CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,slot TEXT NOT NULL,status TEXT NOT NULL,cost INTEGER NOT NULL,tokens INTEGER NOT NULL,body TEXT,provider_id TEXT UNIQUE); CREATE TABLE IF NOT EXISTS block_slots(slot TEXT PRIMARY KEY,block_id TEXT,token_limit INTEGER,status TEXT); CREATE TABLE IF NOT EXISTS v217_phase_slots(slot TEXT PRIMARY KEY, phase TEXT NOT NULL, estimate INTEGER NOT NULL);')
   c.execute('BEGIN IMMEDIATE')
   cap=c.execute('SELECT value FROM meta WHERE key="cap"').fetchone()
   if cap is None:c.execute('INSERT INTO meta VALUES("cap",?)',(str(CAP),))
   elif cap[0]=='700000000000':
    if c.execute('SELECT 1 FROM slots WHERE status!="closed" LIMIT 1').fetchone() or c.execute('SELECT 1 FROM requests WHERE status="reserved" LIMIT 1').fetchone():raise ValueError('Prior work must settle before authorized amendment')
    c.execute('UPDATE meta SET value=? WHERE key="cap"',(str(CAP),));c.execute('INSERT OR REPLACE INTO meta VALUES("v217_cash_authorization",?)',('User approved +400 CNY and cumulative1100 on 2026-11-19; preserve all costs',))
   elif cap[0]!=str(CAP):raise ValueError('Unexpected cash authority')
 def phase_exposure(self,c,phase):
  phases=('dev1','dev2') if phase=='development' else (phase,)
  total=0
  for p in phases:
   rows=c.execute('SELECT s.status,p.estimate,COALESCE(SUM(r.cost),0) FROM v217_phase_slots p JOIN slots s ON p.slot=s.id LEFT JOIN requests r ON r.slot=s.id WHERE p.phase=? GROUP BY s.id',(p,)).fetchall()
   total+=sum(cost if status=='closed' else max(est,cost) for status,est,cost in rows)
   total+=sum(r[0] for r in c.execute('SELECT p.estimate FROM block_slots b JOIN v217_phase_slots p ON p.slot=b.slot WHERE p.phase=? AND b.status="pending"',(p,)))
  return total
 def reserve_block(self,block,slots,phase):
  if phase not in ('dev1','dev2','confirm') or not slots or any(not s.startswith('v217:') or type(n)!=int or not 0<n<=5_000_000 for s,n in slots.items()):raise ValueError('New bounded complete experiment block required')
  with self.db() as c:
   if any(c.execute('SELECT 1 FROM block_slots WHERE slot=?',(s,)).fetchone() for s in slots):raise ValueError('Identity consumed; no automatic replay')
   est=sum(estimate(s,n) for s,n in slots.items())
   if phase!='confirm' and self.phase_exposure(c,'development')+est>DEV_LIMIT:raise AdmissionStopped('Keep 392 CNY confirmation planning; development buffer exhausted')
   if self.exposure(c)[1]+sum(n*8000 for n in slots.values())>CAP:raise AdmissionStopped('Global worst-price exposure; wait or stop whole block')
   c.executemany('INSERT INTO block_slots VALUES(?,?,?,?)',[(s,block,n,'pending') for s,n in slots.items()]);c.executemany('INSERT INTO v217_phase_slots VALUES(?,?,?)',[(s,phase,estimate(s,n)) for s,n in slots.items()])
 def admit(self,slot,limit):
  super().admit(slot,limit)
  with self.db() as c:c.execute('UPDATE slots SET hold=? WHERE id=?',(estimate(slot,limit),slot))
 def snapshot(self):
  with self.db() as c:
   statuses=[dict(zip(('status','requests','tokens','cost_CNY_upper'),r)) for r in c.execute("SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE 'v217:%' GROUP BY status")]
   spent=c.execute("SELECT COALESCE(sum(cost),0)/1e9 FROM requests WHERE status='settled'").fetchone()[0];e,w=self.exposure(c)
   phases={p:self.phase_exposure(c,p)/1e9 for p in ('development','confirm')}
  return {'version':VERSION,'cap_CNY':1100,'settled_total_CNY_upper':spent,'remaining_CNY':1100-spent,'requests':statuses,'phase_estimated_exposure_CNY':phases,'confirmation_plan_reserved_CNY':392,'estimated_exposure_CNY':e/1e9,'worst_exposure_CNY':w/1e9}
