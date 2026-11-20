"""Cache exact immutable-version identities in newly prepared private worlds.

Permission and version resolution still happen on every access. Hashes use the
original pretty JSON bytes, including newline; no new state format or digest.
No module globals, running worlds, shared services or experiment settings change.
"""
import copy,time
from collections import OrderedDict
from types import MethodType
from . import software_runtime_performance_v217_2 as prior
from .software_benchmark_state_cache_v054 import _identity
from .storage import digest,json_bytes

VERSION='v222.1-exact-version-identity-cache-r1'

def _current_identity(self,actor):
 started=time.perf_counter()
 try:
  # Original authority/focus resolution must precede cache lookup, every time.
  artifact,version,bundle=self._bundle(actor)
  path=self.store.version_path(artifact,version);stamp=_identity(path)
  # The detached bundle was decoded under this stamp. If a foreign atomic
  # replacement intervened, or the bundle exceeded the decode-cache bound,
  # return the original freshly computed identity without caching it.
  decoded=self.bundle_cache.items.get(str(path))
  coherent=decoded is not None and decoded[0]==stamp
  key=(actor,artifact['artifact_id'],version,artifact['versions'][version]['sha256'],stamp)
  cached=self._version_identity_cache.get(key)
  if coherent and cached is not None and _identity(path)==stamp:
   self._version_identity_metrics['hits']+=1
   self._version_identity_cache.move_to_end(key)
   return copy.deepcopy(cached)
  self._version_identity_metrics['misses']+=1
  value={'source_reference':{'object_id':artifact['artifact_id'],'version_id':version},
         'files_sha256':digest(json_bytes(bundle['files'])),
         'entry_metadata_sha256':digest(json_bytes(bundle['entry_metadata']))}
  if coherent and _identity(path)==stamp:
   self._version_identity_cache[key]=copy.deepcopy(value)
   while len(self._version_identity_cache)>256:self._version_identity_cache.popitem(last=False)
  return value
 finally:self._version_identity_metrics['seconds']+=time.perf_counter()-started

def install(world):
 """Call only for a new, never-dispatched private world or controlled test copy."""
 if hasattr(world,'_version_identity_cache'):raise ValueError('Already installed')
 prior.install(world)
 world._version_identity_cache=OrderedDict()
 world._version_identity_metrics={'hits':0,'misses':0,'seconds':0.}
 world.org_current_identity=MethodType(_current_identity,world)
 world.performance_revision=VERSION
 return world

def metrics(world):
 return {**prior.metrics(world),'version':VERSION,
         'version_identity_cache':dict(world._version_identity_metrics),
         'version_identity_cache_entries':len(world._version_identity_cache),
         'version_identity_cache_limit':256}

def attach(prepared):install(prepared.world);return prepared
