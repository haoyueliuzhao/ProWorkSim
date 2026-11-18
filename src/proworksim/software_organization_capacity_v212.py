"""Idempotent finalization of this coordinator's private resource leases."""
from .software_organization_capacity_v206 import Capacity as Previous,Probe,PROFILE
class Capacity(Previous):
 def release(self,key):
  with self.lock:return self.leases.pop(key,None) is not None
