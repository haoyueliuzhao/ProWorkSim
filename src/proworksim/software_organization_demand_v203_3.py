"""Demand/capability evidence without converting dependencies into mismatch.

An observed time interval is not a causal effect or a mismatch duration. Missing
ends are censored, never imputed with the last available timestamp.
"""
from __future__ import annotations


def observed_interval(start, end, *, cutoff=None):
    if not start or start.get('capture_time') is None:
        return {'status':'unknown_start','seconds':None}
    if cutoff is not None and start['sequence'] >= cutoff:
        return {'status':'excluded_by_fault','seconds':None}
    if not end or (cutoff is not None and end['sequence'] >= cutoff):
        return {'status':'right_censored','seconds':None,'start':start}
    if end['sequence'] < start['sequence']:
        return {'status':'invalid_event_order','seconds':None}
    if end.get('capture_time') is None:
        return {'status':'unknown_end_time','seconds':None}
    seconds=end['capture_time']-start['capture_time']
    if seconds<0:return {'status':'clock_inconsistent','seconds':None}
    return {'status':'observed','seconds':seconds,'start':start,'end':end,
            'measurement':'controller_capture_wall_clock_not_active_work'}


def validate_mismatch(row):
    """Require evidence of unmet demand AND incapacity, not just a work edge."""
    statuses={'PRESENT','ABSENT','UNKNOWN'}
    if any(row.get(k) not in statuses for k in ('demand','capability_gap','mismatch')):
        raise ValueError('Three-state demand, capability gap and mismatch are separate')
    if row['mismatch']=='PRESENT':
        if (row['demand']!='PRESENT' or row['capability_gap']!='PRESENT'
                or not row.get('why_normal_coordination_insufficient')
                or not row.get('evidence')):
            raise ValueError('Dependency or failure alone cannot justify mismatch')
    if row.get('decision')=='INTERVENE' and row['mismatch']!='PRESENT':
        raise ValueError('Unknown cannot authorize an intervention')
    if row.get('decision')=='NO_CHANGE' and row['mismatch']!='ABSENT':
        raise ValueError('Abstention is not a negative label')
    if row.get('mismatch_seconds') is not None and row['mismatch']!='PRESENT':
        raise ValueError('No mismatch duration without a supported mismatch')
    return True
