"""Native REVIEW2 accounting views over the single physical provider authority.

No auxiliary wallet is created. The host SQLite is authoritative for all API
purposes and retries; the native state retains agent decisions and pending local
admission holds. Source annotations cross the key-free broker as typed JSON.
"""
from __future__ import annotations

import copy
from dataclasses import asdict
import json
from types import MethodType

from .software_input_provenance_v156 import SourceFragment, AnnotatedText, TextSegment
from .software_benchmark_deepseek_contract_v105 import slot_user_id, PreDispatchBudgetStopped
from .storage import digest, json_bytes

VERSION='v157-native-authoritative-shared-pool-r1'


def encode_annotations(value):
    """Encode only data, never executable objects, for the controller/host RPC."""
    if isinstance(value, SourceFragment):
        return {'__source_fragment_v157__': asdict(value)}
    if isinstance(value, AnnotatedText):
        return {'__annotated_text_v157__': [
            {'text':s.text,'source':encode_annotations(s.source)} for s in value.segments]}
    if isinstance(value, dict):
        if any(not isinstance(k,str) for k in value):
            raise ValueError('Annotation object keys must be text')
        return {k:encode_annotations(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [encode_annotations(v) for v in value]
    if value is None or type(value) in {str,int,float,bool}:
        return value
    raise ValueError('Unknown annotation value type')


def decode_annotations(value):
    if isinstance(value, dict):
        if '__source_fragment_v157__' in value:
            if set(value)!={'__source_fragment_v157__'} or not isinstance(value['__source_fragment_v157__'],dict):
                raise ValueError('Malformed source fragment encoding')
            fields=copy.deepcopy(value['__source_fragment_v157__'])
            fields['parent_source_ids']=tuple(fields.get('parent_source_ids',()))
            return SourceFragment(**fields)
        if '__annotated_text_v157__' in value:
            if set(value)!={'__annotated_text_v157__'} or not isinstance(value['__annotated_text_v157__'],list):
                raise ValueError('Malformed text annotation encoding')
            segments=[]
            for item in value['__annotated_text_v157__']:
                if not isinstance(item,dict) or set(item)!={'text','source'}:
                    raise ValueError('Malformed text segment encoding')
                segments.append(TextSegment(item['text'],decode_annotations(item['source'])))
            return AnnotatedText(tuple(segments))
        return {k:decode_annotations(v) for k,v in value.items()}
    if isinstance(value,list):
        return [decode_annotations(v) for v in value]
    if value is None or type(value) in {str,int,float,bool}:
        return value
    raise ValueError('Unknown serialized annotation type')


class MemberLedgerView:
    """Member actual totals stay attributable; admission sees the team's remainder."""
    def __init__(self, delegate, authority):
        object.__setattr__(self,'delegate',delegate)
        object.__setattr__(self,'authority',authority)

    def __getattr__(self,name):
        return getattr(self.delegate,name)

    def __setattr__(self,name,value):
        setattr(self.delegate,name,value)

    @property
    def token_budget(self):
        return self.delegate.actual+self.authority()['available_tokens']

    def snapshot(self):
        value=self.delegate.snapshot()
        value.update(token_limit=5_000_000,token_limit_scope='shared_team_not_individual',
            shared_available_tokens=self.authority()['available_tokens'])
        return value


class TeamLedgerView:
    def __init__(self, delegate, authority, compressor_calls):
        self.delegate,self.authority,self.compressor_calls=delegate,authority,compressor_calls
        self.token_budget=5_000_000

    def __getattr__(self,name):
        return getattr(self.delegate,name)

    @property
    def calls(self):
        return self.delegate.calls+copy.deepcopy(self.compressor_calls)

    @property
    def actual(self):
        return self.authority()['known_actual_tokens']

    @property
    def attempts(self):
        return self.authority()['attempts']

    @property
    def decisions(self):
        return self.delegate.decisions

    def snapshot(self):
        # Read the authority once: no double addition of compressor subaccounts.
        value=self.delegate.snapshot()
        current=self.authority()
        value.update(version=VERSION,attempts=current['attempts'],decisions=self.delegate.decisions,
            known_actual_tokens=current['known_actual_tokens'],
            complete_actual_tokens=current['known_actual_tokens'] if current['actual_usage_complete'] else None,
            uncertain_reserved_tokens=current['uncertain_reserved_tokens'],
            available_tokens=current['available_tokens'],per_usage_id=current['per_usage_id'],
            per_member=current['per_member'],calls=self.calls,authoritative_provider_snapshot=current,
            physical_retries_included=True,compressor_is_autonomous_member=False,
            accounting_source='one_shared_physical_provider_sqlite',automatic_retry='bounded_transient_http_only')
        return value


def bind_owner_budget(owner,post):
    """Install before runtime creation; broker remains key-free in the controller."""
    if hasattr(owner,'shared_provider_budget'):
        raise ValueError('The owner may bind only one shared provider authority')
    team=owner.window_id
    members=list(owner.adapters)
    if members!=['member_001','member_002']:
        raise ValueError('Communication keeps exactly the original REVIEW2 members')
    condition=next(iter(owner.adapters.values())).condition_id
    counters={member:0 for member in members}
    calls=[]

    def authority():
        value=post('/team-budget',{'team_slot_id':team})
        if (value.get('team_id')!=team or value.get('token_limit')!=5_000_000
                or value.get('attempt_limit')!=512 or value.get('source')!='one_shared_physical_provider_sqlite'):
            raise ValueError('The shared budget authority changed')
        return value

    owner.shared_provider_budget=authority
    owner.compressor_calls=calls
    owner.compressor_failures=[]
    original=owner.adapter.ledger
    for adapter in owner.adapters.values():
        adapter.ledger=MemberLedgerView(adapter.ledger,authority)
    owner.adapter.ledger=TeamLedgerView(original,authority,calls)

    def compress(payload,identity):
        member=identity.get('member_id',identity.get('recipient'))
        if member not in members or identity.get('episode_id',team)!=team:
            raise ValueError('Compression is bound to the original receiving member')
        if any(adapter.ledger.inflight is not None for adapter in owner.adapters.values()):
            raise ValueError('Compression runs between original member requests, not concurrently with one')
        if any(not identity.get(key) for key in ('source_id','version_hash','request_id')):
            raise ValueError('Compression requires immutable source, version and delivery identity')
        wire=copy.deepcopy(payload)
        wire['user_id']=slot_user_id(team+':'+member,condition)
        source=decode_annotations(encode_annotations(identity['source_annotations']))
        source['payload']['user_id']=AnnotatedText((TextSegment(wire['user_id'],source['template_source']),))
        # The host capture verifies byte-for-byte equivalence with this final wire.
        packet=encode_annotations(source)
        base={'wire':wire,'member_id':member,'team_slot_id':team}
        measurement=post('/compressor-tokenize',base)
        if measurement.get('request_sha256')!=digest(json_bytes(wire)):
            raise ValueError('Compressor input reservation lost its exact wire')
        current=authority()
        amount=measurement['prompt_tokens']+512
        if current['remaining_attempts']<=0 or amount>current['available_tokens']:
            raise PreDispatchBudgetStopped('compression_budget_unavailable')
        counters[member]+=1
        if counters[member]>512:
            raise PreDispatchBudgetStopped('compression_attempt_identity_exhausted')
        request_id=team+':'+member+f':compressor:{counters[member]:04d}'
        envelope={**base,'request_id':request_id,'slot_id':team,'condition':condition,
            'usage_id':'compressor','prompt_upper_bound':measurement['prompt_tokens'],'source_annotations':packet}
        try:
            body=post('/chat/completions',envelope)
        except BaseException as error:
            owner.compressor_failures.append({'request_id':request_id,'usage_id':'compressor',
                'member_id':member,'team_slot_id':team,'error_type':type(error).__name__,
                'logical_source_identity':copy.deepcopy({k:v for k,v in identity.items() if k!='source_annotations'}),
                'authority_after_failure':authority(),'reservation_is_actual_usage':False,
                'new_agent_decisions':0})
            raise
        # Authoritative settlement already happened in the host, including if
        # observational persistence subsequently fails. No fallback requests here.
        calls.append({'request_id':request_id,'usage_id':'compressor','member_id':member,'team_slot_id':team,
            'usage':copy.deepcopy(body['usage']),'response_id':body.get('id'),
            'logical_source_identity':copy.deepcopy({k:v for k,v in identity.items() if k!='source_annotations'}),
            'new_agent_decisions':0})
        return body

    owner.compress=compress
    return owner


def bind_runtime_budget(owner,runtime):
    """Overlay native admission with the same live authority, preserving decisions.

    Local pending reservations remain necessary before a request reaches the
    host. With the serial team writer, they cannot race an auxiliary compressor.
    Once a response settles, native records retain provenance but their token
    totals are not added to the provider totals a second time.
    """
    budget=runtime.team_budget
    if hasattr(budget,'_v157_authority_bound'):
        raise ValueError('The runtime budget cannot bind twice')
    original_snapshot=budget.snapshot

    def snapshot(self):
        local=original_snapshot()
        provider=owner.shared_provider_budget()
        pending=local['held_tokens']
        # A live physical attempt already owns the same local reservation. Calls
        # are serial; subtract that host hold once rather than doubling it.
        if provider['inflight_count']:
            pending=max(0,pending-provider.get('live_reserved_tokens',0))
        accounted=provider['known_actual_tokens']+provider['uncertain_reserved_tokens']
        local.update(version=VERSION,charged_tokens=accounted,held_tokens=pending,
            available_tokens=max(0,5_000_000-accounted-pending),
            attempts=max(local['attempts'],provider['attempts']),
            remaining_attempts=512-max(local['attempts'],provider['attempts']),
            known_actual_tokens=provider['known_actual_tokens'],
            uncertain_reserved_tokens=provider['uncertain_reserved_tokens'],
            native_records_do_not_add_to_provider_usage=True,
            authoritative_provider_snapshot=provider)
        local.pop('state_sha256',None)
        local['state_sha256']=digest(json_bytes(local))
        return local

    budget.snapshot=MethodType(snapshot,budget)
    budget._v157_authority_bound=True
    # The original World stores a bound method at construction, not a dynamic
    # attribute lookup; replace that owned callback so visible remaining budget
    # includes compression and retry reservations too.
    prepared=getattr(runtime,'prepared',None)
    if prepared is not None:
        prepared.world.model_budget_snapshot=budget.snapshot
    return runtime
