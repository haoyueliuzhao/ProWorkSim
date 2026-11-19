"""Isolate task faults; only repeated typed infrastructure faults trip admission."""
import re,threading,copy
INFRA_TYPES={'FatalTransport','TransportFailure','ConnectionError','TimeoutError','TimeoutExpired','ReadTimeout','ConnectTimeout','ImageNotFound','NotFound','APIError','MemoryError','BrokenPipeError','OSError','FileNotFoundError'}
class FaultRegistry:
 def __init__(self):self.lock=threading.RLock();self.rows=[];self.groups={}
 def record(self,index,reason):
  with self.lock:
   detail=reason
   if reason.get('scoring'):
    detail=next((v for v in reason['scoring'].values() if isinstance(v,dict) and v.get('error_type') in INFRA_TYPES),reason)
   error=detail.get('error');errdict=error if isinstance(error,dict) else {}
   typ=detail.get('type') or detail.get('error_type') or errdict.get('type')
   message=str(detail.get('message') or errdict.get('message') or error or '')
   signature=None
   if typ in INFRA_TYPES:
    message=re.sub(r'/[^\s,:]+','<path>',message);message=re.sub(r'[0-9a-f]{16,}|\d+','<id>',message)
    signature=typ+':'+message[:240];self.groups.setdefault(signature,set()).add(str(index))
   shared=signature is not None and len(self.groups[signature])>=3
   row={'index':index,'reason':copy.deepcopy(reason),'infrastructure_signature':signature,'independent_tasks_same_signature':len(self.groups.get(signature,set())),'pause_new_admissions':shared,'isolated_until_shared_evidence':not shared,'automatic_model_retry':False}
   self.rows.append(row);return row
