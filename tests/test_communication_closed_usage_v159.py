import copy,json
import pytest
from proworksim.software_benchmark_closed_usage_v159 import validate_usage
from proworksim.software_communication_finish_v159 import retry_evidence

@pytest.mark.parametrize('purpose',['agent','condenser'])
def test_host_close_rechecks_covered_retry_against_original_rows(purpose):
    common={'logical_id':'same-logical','slot_id':'team','member_id':'member_001','condition':'C2',
        'usage_id':purpose,'request_sha256':'a'*64}
    rows=[{**common,'request_id':'physical-1','attempt_index':1,'status':'http_error_uncertain','reserved_tokens':100},
          {**common,'request_id':'physical-2','attempt_index':2,'status':'settled','reserved_tokens':100,
           'response_id':'actual-returned-response','usage_json':json.dumps({'prompt_tokens':30,'completion_tokens':5,'total_tokens':35})}]
    provider=retry_evidence({'source':'one_shared_physical_provider_sqlite','team_id':'team','attempts':2,
        'known_actual_tokens':35,'uncertain_reserved_tokens':100,'inflight_count':0,
        'available_tokens':4_999_865,'token_limit':5_000_000},rows)
    ledger={'attempts':2,'decisions':1,'known_actual_tokens':35,'complete_actual_tokens':None,
        'uncertain_reserved_tokens':100,'inflight':None,'token_limit':5_000_000,
        'all_model_attempt_limit':512,'agent_decision_limit':512,'authoritative_provider_snapshot':provider}
    physical={'calls':[{'call_id':'physical-2','prompt_tokens':30,'completion_tokens':5}],
        'unresolved_calls':[{'call_id':'physical-1','purpose':purpose,'status':'http_error_uncertain','reserved_tokens':100}],
        'usage_capture_complete':False}
    limits={'input_plus_output_tokens':5_000_000,'all_model_attempts':512,'agent_decisions':512}
    assert validate_usage(ledger,limits,physical,physical_retry_rows=rows) is ledger
    assert ledger['complete_actual_tokens'] is None and ledger['uncertain_reserved_tokens']==100
    forged=copy.deepcopy(rows);forged[1]['request_sha256']='b'*64
    with pytest.raises(ValueError):validate_usage(ledger,limits,physical,physical_retry_rows=forged)
