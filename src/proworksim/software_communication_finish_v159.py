"""Finish after bounded HTTP recovery without refunding uncertain attempts.

A fully received transient error followed by a matching settled response to the
same logical request is different from a terminal lost response. Both retain
cash/token uncertainty; only the former permits normal action completion.
"""
from __future__ import annotations
import copy
from types import FunctionType
from . import software_communication_finish_v157 as original
from .software_benchmark_finish_review_v117 import FinishReviewPolicy as OriginalPolicy
from .software_benchmark_finish_review_v117 import require_known_usage as base_require_known

VERSION='v159-finish-with-covered-physical-retry-uncertainty-r1'


def retry_evidence(snapshot,records):
    """Host-only projection of original SQLite rows; never writes/refunds them."""
    settled={}
    for row in records:
        if row['status']=='settled':settled.setdefault(row['logical_id'],[]).append(row)
    covered=[];compressor=[];unresolved=[];live=[]
    for row in records:
        if row['status']=='settled':continue
        item={k:row[k] for k in ('request_id','logical_id','attempt_index','slot_id','member_id','condition','usage_id','status','request_sha256','reserved_tokens')}
        if row['status']=='reserved':live.append(item);continue
        if row['usage_id']=='compressor':compressor.append(item);continue
        matches=[s for s in settled.get(row['logical_id'],[]) if s['attempt_index']>row['attempt_index']
            and all(s[k]==row[k] for k in ('slot_id','member_id','condition','usage_id','request_sha256'))
            and s.get('response_id') and s.get('usage_json')]
        if row['status']=='http_error_uncertain' and len(matches)==1:
            item.update(settled_success_request_id=matches[0]['request_id'],settled_response_id=matches[0]['response_id'],
                successful_exact_logical_response_returned=True)
            covered.append(item)
        else:unresolved.append(item)
    proof={'version':VERSION,'covered_retry_unknowns':covered,'compressor_unknowns':compressor,
        'terminal_uncovered_unknowns':unresolved,'inflight':live,
        'covered_retry_token_upper':sum(r['reserved_tokens'] for r in covered),
        'compressor_unknown_token_upper':sum(r['reserved_tokens'] for r in compressor),
        'uncovered_unknown_token_upper':sum(r['reserved_tokens'] for r in unresolved),
        'inflight_token_upper':sum(r['reserved_tokens'] for r in live),
        'physical_usage_unknown_remains':bool(covered or compressor or unresolved or live),
        'unknown_reservations_refunded':False,'original_ledger_records_changed':False}
    total=sum(proof[k] for k in ('covered_retry_token_upper','compressor_unknown_token_upper','uncovered_unknown_token_upper','inflight_token_upper'))
    if total!=snapshot['uncertain_reserved_tokens']:
        raise ValueError('The retry-recovery projection differs from the same physical account snapshot')
    return {**snapshot,'retry_recovery_evidence':proof}


def require_known_usage(snapshot):
    held=snapshot.get('uncertain_reserved_tokens',0)
    if not held:return base_require_known(snapshot)
    provider=snapshot.get('authoritative_provider_snapshot') or {}
    proof=provider.get('retry_recovery_evidence') or {}
    if (provider.get('source')!='one_shared_physical_provider_sqlite'
        or provider.get('inflight_count')!=0 or snapshot.get('inflight') is not None
        or type(held) is not int or held<=0 or provider.get('uncertain_reserved_tokens')!=held
        or provider.get('known_actual_tokens')!=snapshot.get('known_actual_tokens')
        or provider.get('available_tokens')!=max(0,5_000_000-held-provider['known_actual_tokens'])
        or provider.get('token_limit')!=5_000_000 or proof.get('version')!=VERSION
        or proof.get('terminal_uncovered_unknowns') or proof.get('inflight')
        or proof.get('unknown_reservations_refunded') is not False
        or proof.get('original_ledger_records_changed') is not False
        or proof.get('covered_retry_token_upper',0)+proof.get('compressor_unknown_token_upper',0)!=held):
        raise RuntimeError('Unsettled terminal/inflight responses cannot be concealed by recovered HTTP retries')
    covered=proof.get('covered_retry_unknowns',[]);compressors=proof.get('compressor_unknowns',[])
    ids=[r.get('request_id') for r in [*covered,*compressors]]
    if (len(ids)!=len(set(ids)) or None in ids
        or sum(r.get('reserved_tokens',0) for r in covered)!=proof['covered_retry_token_upper']
        or sum(r.get('reserved_tokens',0) for r in compressors)!=proof['compressor_unknown_token_upper']
        or any(r.get('usage_id') not in {'agent','condenser'} or r.get('status')!='http_error_uncertain'
            or r.get('successful_exact_logical_response_returned') is not True
            or not r.get('settled_success_request_id') or not r.get('settled_response_id') for r in covered)
        or any(r.get('usage_id')!='compressor' or r.get('status')=='reserved' for r in compressors)):
        raise RuntimeError('The frozen same-logical-request retry proof is incomplete')


class FinishReviewPolicy(OriginalPolicy):
    def offer(self,snapshot,*,intent_id,reason):
        require_known_usage(snapshot)
        held=snapshot.get('uncertain_reserved_tokens',0)
        if not held:return super().offer(snapshot,intent_id=intent_id,reason=reason)
        admission=copy.deepcopy(snapshot);upper=snapshot['known_actual_tokens']+held
        admission.update(known_actual_tokens=upper,complete_actual_tokens=upper,uncertain_reserved_tokens=0)
        self._emit('covered_physical_unknown_finish_admission',intent_id=intent_id,
            known_actual_tokens=snapshot['known_actual_tokens'],uncertain_reserved_tokens=held,
            conservative_admission_upper=upper,actual_usage_complete=False,reservation_released=False)
        return super().offer(admission,intent_id=intent_id,reason=reason)


# Same runtime finish scheduling, proof and one-review limit; only its explicit
# usage predicate/accounting view are replaced in a private function namespace.
_ns={**original.decorate_reviews.__globals__,'VERSION':VERSION,
    'FinishReviewPolicy':FinishReviewPolicy,'require_known_usage':require_known_usage}
decorate_reviews=FunctionType(original.decorate_reviews.__code__,_ns,original.decorate_reviews.__name__,
    original.decorate_reviews.__defaults__,original.decorate_reviews.__closure__)
decorate_reviews.__kwdefaults__=original.decorate_reviews.__kwdefaults__
