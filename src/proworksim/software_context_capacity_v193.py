"""Use existing artifact volume and Docker filesystem with separate headroom."""
from . import software_context_resume_v189 as previous
from .software_benchmark_expansion_episode_v069 import clone_function

def capacity_status(policy,*,physical=None,active=None,load1=None):
    active=previous.active_claims(policy) if active is None else active
    physical=policy.physical_capacity() if physical is None else physical
    value=previous.capacity_status(policy,physical=physical,active=active,load1=load1)
    floor=policy.STORAGE_POLICY['Docker_minimum_free_bytes']+policy.CONSTRAINTS['generation_pair_payload_spool_bytes']+sum(r.get('reserved_spool_bytes',0) for r in active)
    value['Docker_disk_floor_bytes']=floor
    if physical['docker_disk_free_bytes']<floor:value['waiting_reasons'].append('Docker_filesystem_reservation')
    value['admit']=not value['waiting_reasons']
    return value

bind_capacity=clone_function(previous.bind_capacity,{**previous.bind_capacity.__globals__,'capacity_status':capacity_status})
