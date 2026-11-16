import pytest
from proworksim.software_organization_demand_v203_3 import observed_interval,validate_mismatch

def test_fault_censor_does_not_invent_resolution_or_duration():
    a={'sequence':5,'capture_time':100};b={'sequence':11,'capture_time':130}
    assert observed_interval(a,b)['seconds']==30
    assert observed_interval(a,b,cutoff=11)['status']=='right_censored'
    assert observed_interval(a,None)['seconds'] is None
    assert observed_interval(a,b,cutoff=5)['status']=='excluded_by_fault'
    assert observed_interval(b,a)['status']=='invalid_event_order'

def test_dependency_failure_and_unknown_cannot_authorize_reorganization():
    row={'demand':'PRESENT','capability_gap':'UNKNOWN','mismatch':'UNKNOWN','decision':'ABSTAIN'}
    assert validate_mismatch(row)
    for patch in ({'decision':'INTERVENE'},{'decision':'NO_CHANGE'},
                  {'mismatch':'PRESENT'},{'mismatch_seconds':5}):
        with pytest.raises(ValueError):validate_mismatch({**row,**patch})
    assert validate_mismatch({**row,'capability_gap':'PRESENT','mismatch':'PRESENT',
        'decision':'INTERVENE','why_normal_coordination_insufficient':'supported rights conflict',
        'evidence':['source-event-id']})
