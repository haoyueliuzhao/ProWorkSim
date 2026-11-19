"""Byte-equivalent large-state acceleration for newly created private worlds.

No tool/observation/model/budget changes and no live process monkeypatching.
"""
import copy,hashlib,json
from types import SimpleNamespace,MethodType
from . import software_organization_performance_v214 as prior
from .software_benchmark_state_cache_v054 import _identity
from . import software_benchmark_state_storage_v141 as memory
from .core import transitions,runner
VERSION='v217.2-large-state-cached-canonical-and-bounded-cache-r2'
MIB=1024**2
class EncoderCache(prior.EncoderCache):
 def __init__(self):super().__init__(limit=1536*MIB)
class CachedStore(prior.CachedStore):
 def __init__(self,root,encoder=None):super().__init__(root,encoder or EncoderCache())
 def load(self):
  path=self.control/'state.json'
  try:
   before=_identity(path);old=self._state_cache
   if old is not None and old[0]==before:
    result=copy.deepcopy(old[1])
    if _identity(path)==before:self.metrics['load_hit']+=1;return result
    del result;before=_identity(path)
   self._state_cache=None;self.metrics['load_miss']+=1
   state=json.loads(path.read_bytes()) if before[2]<=2048*MIB else memory.read_json(path)
   if _identity(path)==before:self._state_cache=(before,state);return copy.deepcopy(state)
   return state
  except BaseException:self._state_cache=None;raise

def install(world):
 if not isinstance(world,prior.World):raise TypeError('Expected existing private v214/v216 business world')
 old=world.store;enc=EncoderCache();world.store=CachedStore(old.root,enc);world.store.fault_hook=old.fault_hook;world.bundle_cache=prior.BundleCache(limit=768*MIB)
 j=SimpleNamespace(**{**vars(memory._journal),'canonical_digest':enc.digest})
 transition=prior.private(transitions.execute_transition,canonical_digest=enc.digest)
 world.act=MethodType(prior.private(memory.LowMemoryWorldCore.act,journal=j,execute_transition=transition,validate_finite_json=enc.validate),world)
 world._drain_events=MethodType(prior.private(runner.WorldRunner._drain_events,journal=j,execute_transition=transition),world)
 world.performance_revision=VERSION
 return world

def metrics(world):return {**prior.metrics(world),'version':VERSION,'canonical_encoder':'unchanged_cached_stream','encoded_cache_limit':world.store.encoder.limit,'bundle_cache_limit':world.bundle_cache.limit,'fast_cold_read_max_bytes':2048*MIB}

semantic=prior.semantic
class BundleCache(prior.BundleCache):
 def __init__(self,limit=768*MIB):super().__init__(limit)
def attach(prepared):
 if not isinstance(prepared.world,prior.World):prior.attach(prepared)
 install(prepared.world);return prepared
