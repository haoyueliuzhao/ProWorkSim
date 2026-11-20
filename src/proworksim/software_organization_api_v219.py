"""Fresh v219 identities in the authorized 1100 CNY shared ledger; no cap raise."""
from .software_organization_api_v217 import Ledger as Prior,Backend,DirectHTTPS,AdmissionStopped,estimate,CAP
PLANNING=270_000_000_000
class Ledger(Prior):
 def reserve_block(self,block,slots,phase=None):
  if not slots or any(not s.startswith('v219:') or type(n)!=int or not 0<n<=5_000_000 for s,n in slots.items()):raise ValueError('Fresh complete v219 block required')
  with self.db() as c:
   if any(c.execute('SELECT 1 FROM block_slots WHERE slot=?',(s,)).fetchone() for s in slots):raise ValueError('No replay of consumed identity')
   rows=c.execute("SELECT s.status,s.hold,COALESCE(sum(r.cost),0) FROM slots s LEFT JOIN requests r ON s.id=r.slot WHERE s.id LIKE 'v219:%' GROUP BY s.id").fetchall()
   paid=sum(cost if status=='closed' else max(hold,cost) for status,hold,cost in rows)
   pending=c.execute("SELECT token_limit FROM block_slots WHERE slot LIKE 'v219:%' AND status='pending'").fetchall()
   if paid+sum(min(n*8000,7_500_000_000) for (n,) in pending)+sum(estimate(s,n) for s,n in slots.items())>PLANNING:raise AdmissionStopped('v219 planning admission line 270 CNY; started slots continue')
   if self.exposure(c)[1]+sum(slots.values())*8000>CAP:raise AdmissionStopped('Shared 1100 worst-price exposure; wait for live slots')
   c.executemany('INSERT INTO block_slots VALUES(?,?,?,?)',[(s,block,n,'pending') for s,n in slots.items()])
 def snapshot(self):
  v=super().snapshot()
  with self.db() as c:v['v219_requests']=[dict(zip(('status','requests','tokens','cost_CNY_upper'),r)) for r in c.execute("SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE 'v219:%' GROUP BY status")]
  return {**v,'version':'v219-shared1100-no-increase','v219_planning_admission_CNY':270}
