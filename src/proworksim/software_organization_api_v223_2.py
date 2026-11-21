"""One bounded correction plus a previously unused native W0 continuation."""
from pathlib import Path
from .software_organization_api_v211 import Ledger as Prior
from .software_organization_api_v204 import Backend,DirectHTTPS,AdmissionStopped
CAP=1_100_000_000_000
OLD='v223.1:task-03:';NEW='v223.2:task-03:'
class Ledger(Prior):
 def __init__(self,path):
  self.path=Path(path)
  with self.db() as c:
   if c.execute('SELECT value FROM meta WHERE key="cap"').fetchone()!=(str(CAP),):raise ValueError('Existing authorized 1100 ledger required')
   c.execute('CREATE TABLE IF NOT EXISTS v223_2_recovery(id TEXT PRIMARY KEY,status TEXT,token_limit INTEGER,hold INTEGER)')
 def used(self,c,slot):
  if c.execute('SELECT status FROM slots WHERE id=?',(slot,)).fetchone()!=('closed',):raise ValueError('Predecessor not fully settled')
  return c.execute('SELECT COALESCE(sum(tokens),0) FROM requests WHERE slot=?',(slot,)).fetchone()[0]
 def reserve_recovery(self):
  with self.db() as c:
   if c.execute('SELECT 1 FROM v223_2_recovery').fetchone():raise ValueError('Recovery identity already consumed')
   if c.execute('SELECT 1 FROM slots WHERE status!="closed"').fetchone() or c.execute('SELECT 1 FROM block_slots WHERE status="pending"').fetchone():raise AdmissionStopped('Prior work must be settled')
   if c.execute('SELECT 1 FROM slots WHERE id=?',(OLD+'W0',)).fetchone():raise ValueError('Native W0 has already started; do not resample')
   p,h,g=[self.used(c,OLD+s) for s in ('PREFIX','GRAPH','GEN-W0')];remaining=5_000_000-p-h-g
   if not 0<g<200_000 or remaining<=0:raise ValueError('Invalid old stage allowance')
   hold=remaining*8000
   if Prior.exposure(self,c)[1]+hold>CAP:raise AdmissionStopped('Insufficient complete remaining-branch cash')
   c.execute('INSERT INTO v223_2_recovery VALUES("task-03-W0","active",?,?)',(remaining,hold));return remaining
 def reserve_stage(self,slot):
  if slot not in (NEW+'REPAIR-W0',NEW+'W0'):raise ValueError('Only one fixed recovery branch')
  with self.db() as c:
   row=c.execute('SELECT status,token_limit FROM v223_2_recovery').fetchone()
   if row is None or row[0]!='active':raise AdmissionStopped('Recovery not admitted')
   if c.execute('SELECT 1 FROM block_slots WHERE slot=?',(slot,)).fetchone():raise ValueError('No stage replay')
   limit=200_000-self.used(c,OLD+'GEN-W0') if slot.endswith('REPAIR-W0') else row[1]-self.used(c,NEW+'REPAIR-W0')
   if not 0<limit<=5_000_000:raise ValueError('No remaining logical allowance')
   c.execute('INSERT INTO block_slots VALUES(?,?,?,"pending")',(slot,'v223.2-one-recovery',limit));return limit
 def stage_remaining(self,slot):
  with self.db() as c:
   row=c.execute('SELECT token_limit,status FROM slots WHERE id=?',(slot,)).fetchone()
   if row is None or row[1]!='active':raise ValueError('Stage not active')
   if c.execute('SELECT 1 FROM requests WHERE slot=? AND status NOT IN ("settled","http_error")',(slot,)).fetchone():raise ValueError('Uncertain request: no fresh model call')
   return row[0]-c.execute('SELECT COALESCE(sum(tokens),0) FROM requests WHERE slot=?',(slot,)).fetchone()[0]
 def exposure(self,c):
  old=c.execute('SELECT s.status,s.token_limit,COALESCE(sum(r.cost),0),COALESCE(sum(r.tokens),0) FROM slots s LEFT JOIN requests r ON r.slot=s.id WHERE s.id NOT LIKE "v223.2:%" GROUP BY s.id').fetchall()
  worst=sum(cost if status=='closed' else cost+max(0,n-t)*8000 for status,n,cost,t in old)
  worst+=c.execute('SELECT COALESCE(sum(token_limit),0)*8000 FROM block_slots WHERE status="pending" AND slot NOT LIKE "v223.2:%"').fetchone()[0]
  newcost=c.execute('SELECT COALESCE(sum(cost),0) FROM requests WHERE slot LIKE "v223.2:%"').fetchone()[0];rec=c.execute('SELECT status,hold FROM v223_2_recovery').fetchone()
  worst+=max(rec[1],newcost) if rec and rec[0]=='active' else newcost;return worst,worst
 def finish(self):
  with self.db() as c:
   if c.execute('SELECT 1 FROM slots WHERE id LIKE "v223.2:%" AND status!="closed"').fetchone() or c.execute('SELECT 1 FROM block_slots WHERE slot LIKE "v223.2:%" AND status="pending"').fetchone():return False
   c.execute('UPDATE v223_2_recovery SET status="closed"');return True
 def snapshot(self):
  with self.db() as c:
   spent=c.execute('SELECT COALESCE(sum(cost),0) FROM requests WHERE status="settled"').fetchone()[0]
   rows=[dict(zip(('status','requests','tokens','cost_CNY_upper'),r)) for r in c.execute('SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE "v223.2:%" GROUP BY status')]
   worst=self.exposure(c)[1];recovery=c.execute('SELECT status,token_limit,hold/1e9 FROM v223_2_recovery').fetchone()
  return {'version':'v223.2-existing-task-recovery-r1','cap_CNY':1100,'settled_total_CNY_upper':spent/1e9,'remaining_CNY':(CAP-spent)/1e9,'new_requests':rows,'worst_exposure_CNY':worst/1e9,'recovery':recovery}
