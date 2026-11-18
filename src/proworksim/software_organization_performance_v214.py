"""Opt-in execution acceleration with unchanged v213 tools and business semantics.

Private per-world caches only. Canonical bytes, SHA256 receipts, explicit durability,
permission checks, rollback/recovery and mutable caller isolation remain intact.
Existing worlds/processes are not patched by importing this module.
"""
from __future__ import annotations
import copy,hashlib,json,os,sys
from collections import OrderedDict
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import FunctionType,MethodType,SimpleNamespace
from . import software_benchmark_state_storage_v141 as memory
from .software_benchmark_state_cache_v054 import _identity
from . import software_organization_world_v213 as semantic
from .core import transitions,runner
from .adapters.capabilities import read
VERSION='v214-byte-equivalent-hot-path-cache-r1'
MIB=1024**2

def private(fn,**overrides):
 g={**fn.__globals__,**overrides};v=FunctionType(fn.__code__,g,fn.__name__,fn.__defaults__,fn.__closure__);v.__kwdefaults__=fn.__kwdefaults__;return v

class EncoderCache:
 def __init__(self,limit=384*MIB):
  self.limit=limit;self.size=0;self.items=OrderedDict();self.hits=self.misses=0
  self.pretty=json.JSONEncoder(ensure_ascii=False,indent=2,allow_nan=False)
  self.canonical=json.JSONEncoder(ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
  method=private(json.JSONEncoder.iterencode,encode_basestring=self.escape)
  self.pretty.iterencode=MethodType(method,self.pretty);self.canonical.iterencode=MethodType(method,self.canonical)
 def escape(self,value):
  if type(value)is not str or len(value)<1024:return json.encoder.encode_basestring(value)
  old=self.items.get(value)
  if old is not None:self.hits+=1;self.items.move_to_end(value);return old[0]
  self.misses+=1;encoded=json.encoder.encode_basestring(value);size=sys.getsizeof(value)+sys.getsizeof(encoded)
  if size<=self.limit:
   while self.items and self.size+size>self.limit:
    _,(_,n)=self.items.popitem(last=False);self.size-=n
   self.items[value]=(encoded,size);self.size+=size
  return encoded
 def digest(self,value):
  h=hashlib.sha256()
  for part in self.canonical.iterencode(value):h.update(part.encode('utf-8'))
  return h.hexdigest()
 def validate(self,value):
  for _ in self.pretty.iterencode(value):pass

class CachedStore(memory.StreamCachedStore):
 """Keep a detached normalized committed snapshot, bound to our own atomic inode."""
 def __init__(self,root,encoder=None):
  super().__init__(root);self.encoder=encoder or EncoderCache();self.metrics={'load_hit':0,'load_miss':0,'saved_cache':0,'save':0}
 def load(self):
  path=self.control/'state.json'
  try:
   before=_identity(path);old=self._state_cache
   if old is not None and old[0]==before:
    result=copy.deepcopy(old[1])
    if _identity(path)==before:self.metrics['load_hit']+=1;return result
    del result;before=_identity(path)
   self._state_cache=None;self.metrics['load_miss']+=1
   # Larger cold states retain the old bounded-memory reader.
   state=json.loads(path.read_bytes()) if before[2]<=512*MIB else memory.read_json(path)
   if _identity(path)==before:self._state_cache=(before,state);return copy.deepcopy(state)
   return state
  except BaseException:self._state_cache=None;raise
 def save(self,state):
  self._state_cache=None;self.metrics['save']+=1;path=self.control/'state.json';path.parent.mkdir(parents=True,exist_ok=True);tmp=None
  try:
   with NamedTemporaryFile(dir=path.parent,prefix='.tmp-v214-',delete=False) as f:
    tmp=Path(f.name)
    for part in self.encoder.pretty.iterencode(state):f.write(part.encode('utf-8'))
    f.write(b'\n');f.flush();os.fsync(f.fileno());ours=os.fstat(f.fileno())
   os.replace(tmp,path);stamp=_identity(path)
   # Match the actual inode we wrote, not whichever file a foreign replacer installed.
   if stamp[:4]==(ours.st_dev,ours.st_ino,ours.st_size,ours.st_mtime_ns):
    try:snapshot=memory.clone_json(state)
    except (MemoryError,ValueError,TypeError):return
    if _identity(path)==stamp:self._state_cache=(stamp,snapshot);self.metrics['saved_cache']+=1
  finally:
   if tmp is not None:tmp.unlink(missing_ok=True)

class BundleCache:
 def __init__(self,limit=256*MIB):self.limit=limit;self.size=0;self.items=OrderedDict();self.hits=self.misses=0
 def get(self,path):
  path=Path(path);stamp=_identity(path);key=str(path);old=self.items.get(key)
  if old and old[0]==stamp:
   result=copy.deepcopy(old[1])
   if _identity(path)==stamp:self.hits+=1;self.items.move_to_end(key);return result
  if old:self.size-=old[2];del self.items[key]
  self.misses+=1;value=read('json',path.read_bytes())
  # Conservative estimate includes decoded strings/containers, not merely disk bytes.
  seen=set()
  def size(x):
   if id(x) in seen:return 0
   seen.add(id(x));n=sys.getsizeof(x)
   if isinstance(x,dict):n+=sum(size(k)+size(v) for k,v in x.items())
   elif isinstance(x,(tuple,list)):n+=sum(size(v) for v in x)
   return n
  n=size(value)
  if _identity(path)==stamp and n<=self.limit:
   while self.items and self.size+n>self.limit:
    _,(_,_,bytes_used)=self.items.popitem(last=False);self.size-=bytes_used
   self.items[key]=(stamp,value,n);self.size+=n;return copy.deepcopy(value)
  return value

class World(semantic.SoftwareCollaborationWorld):
 def _bundle(self,actor,*,patch_id=None,reference=None,write=False,baseline=False):
  focus=getattr(self,'_read_only_review_focus',None)
  if focus and actor==focus['actor'] and patch_id is None and reference is None and not baseline:
   if write:raise ValueError('Immutable review test cannot edit main workspace')
   patch_id=focus['patch_id']
  if patch_id is not None:reference=self._patch(patch_id)['source_reference']
  # Resolve permission/current version on every lookup, BEFORE touching the cache.
  if reference is not None:
   artifact,version=self._object(actor,semantic.PROJECT,object_id=reference['object_id'],version_id=reference['version_id'],write=write)
  else:artifact,version=self._object(actor,semantic.PROJECT,alias='baseline' if baseline else actor,write=write)
  return artifact,version,self.bundle_cache.get(self.store.version_path(artifact,version))

def enable(world):
 """Only call while preparing a new private world, before starting its model loop."""
 if isinstance(world,World):raise ValueError('Performance binding already installed')
 if not isinstance(world,semantic.SoftwareCollaborationWorld):raise TypeError('Frozen v213 semantic world required')
 old=world.store;enc=EncoderCache();world.__class__=World;world.store=CachedStore(old.root,enc);world.store.fault_hook=old.fault_hook;world.bundle_cache=BundleCache()
 # Bind only this world's runner. No module globals or live-world methods change.
 j=SimpleNamespace(**{**vars(memory._journal),'canonical_digest':enc.digest})
 transition=private(transitions.execute_transition,canonical_digest=enc.digest)
 world.act=MethodType(private(memory.LowMemoryWorldCore.act,journal=j,execute_transition=transition,validate_finite_json=enc.validate),world)
 world._drain_events=MethodType(private(runner.WorldRunner._drain_events,journal=j,execute_transition=transition),world)
 world.performance_revision=VERSION
 return world

def attach(prepared):enable(prepared.world);return prepared

def metrics(world):
 return {'version':VERSION,'state':world.store.metrics,'encoded_string_hits':world.store.encoder.hits,'encoded_string_misses':world.store.encoder.misses,'encoded_cache_bytes':world.store.encoder.size,'bundle_hits':world.bundle_cache.hits,'bundle_misses':world.bundle_cache.misses,'bundle_cache_bytes':world.bundle_cache.size,'business_version':semantic.VERSION}
