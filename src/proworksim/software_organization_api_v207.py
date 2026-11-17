"""User-approved empirical whole-block admission after healthy v204/v205 feedback.

The nominal 200 CNY line gates new complete blocks. Started slots retain token
and wall limits, not a cash interruption. Prior prices/records are immutable.
"""
from .software_organization_api_v204 import Ledger as Previous,Backend,DirectHTTPS,AdmissionStopped,CAP
ESTIMATE=10_500_000_000
VERSION='v207-healthy-cost-complete-block-1050-r1'
class Ledger(Previous):
 def _tables(self,c):
  c.execute('CREATE TABLE IF NOT EXISTS block_slots (slot TEXT PRIMARY KEY,block_id TEXT,token_limit INTEGER,status TEXT)')
  c.execute('CREATE TABLE IF NOT EXISTS block_cash_estimates (slot TEXT PRIMARY KEY,estimate INTEGER,version TEXT)')
 def exposure(self,c):
  self._tables(c)
  live=c.execute('SELECT s.status,s.hold,COALESCE(SUM(r.cost),0) FROM slots s LEFT JOIN requests r ON r.slot=s.id GROUP BY s.id').fetchall()
  paid_and_held=sum(cost if status=='closed' else max(hold,cost) for status,hold,cost in live)
  pending=c.execute('SELECT COALESCE(SUM(COALESCE(e.estimate,b.token_limit*8000)),0) FROM block_slots b LEFT JOIN block_cash_estimates e ON e.slot=b.slot WHERE b.status="pending"').fetchone()[0]
  return paid_and_held+pending
 def reserve_block(self,block,slots):
  if not slots or any(type(n)!=int or not 0<n<=5000000 for n in slots.values()):raise ValueError('Invalid complete comparison block')
  with self.db() as c:
   self._tables(c)
   if any(c.execute('SELECT 1 FROM block_slots WHERE slot=?',(s,)).fetchone() for s in slots):raise ValueError('No duplicate block or identity')
   if self.exposure(c)+len(slots)*ESTIMATE>CAP:raise AdmissionStopped('Insufficient estimated cash for whole new block')
   c.executemany('INSERT INTO block_slots VALUES (?,?,?,?)',[(s,block,n,'pending') for s,n in slots.items()])
   c.executemany('INSERT INTO block_cash_estimates VALUES (?,?,?)',[(s,ESTIMATE,VERSION) for s in slots])
 def admit(self,slot,limit):
  with self.db() as c:
   self._tables(c)
   if c.execute('SELECT 1 FROM slots WHERE id=?',(slot,)).fetchone():raise ValueError('No replay')
   row=c.execute('SELECT b.token_limit,b.status,e.estimate FROM block_slots b JOIN block_cash_estimates e ON e.slot=b.slot WHERE b.slot=?',(slot,)).fetchone()
   if row!=(limit,'pending',ESTIMATE):raise AdmissionStopped('Complete empirical block reservation required')
   c.execute('UPDATE block_slots SET status="active" WHERE slot=?',(slot,))
   c.execute('INSERT INTO slots VALUES (?,?,?,?)',(slot,limit,'active',ESTIMATE))
 def snapshot(self):
  result=super().snapshot()
  with self.db() as c:amount=self.exposure(c)
  return {**result,'cash_policy_version':VERSION,'nominal_new_block_line_CNY':200,'slot_estimate_CNY':10.5,
   'admission_exposure_CNY':amount/1e9,'started_cash_interruption':False,'estimate_is_guarantee':False,
   'over_nominal_CNY':max(0,result['peak_cost_upper_CNY']-200)}
