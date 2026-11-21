"""Proposal-only predispatch allocation; preserve context and stage allowance."""
import copy,json
from .software_organization_planning_v223 import parse
from .software_organization_generator_v219 import mutable_tasks
VERSION='v223.2-proposal-repair-with-remaining-output-r1'

def output_allocation(prompt_upper,remaining,requested_output=8192,input_bound=98304):
 if any(type(x) is not int or x<0 for x in (prompt_upper,remaining,requested_output,input_bound)):raise ValueError('Nonnegative integer bounds required')
 if requested_output<1:raise ValueError('Positive output cap required')
 available=max(0,remaining-prompt_upper)
 dispatch=prompt_upper<=input_bound and available>0
 return {'version':VERSION,'dispatch':dispatch,'prompt_upper_including_existing_margin':prompt_upper,'remaining_stage_tokens':remaining,'requested_output_cap':requested_output,'max_tokens':min(requested_output,available) if dispatch else 0,'reason':'within_remaining_allowance' if dispatch else 'input_limit' if prompt_upper>input_bound else 'no_output_allowance','context_truncated':False,'stage_limit_increased':False}

def correction_request(first_request,first_response,state):
 """Exact one permitted format correction after a saved invalid first response."""
 calls=first_response['choices'][0]['message'].get('tool_calls') or []
 try:
  if len(calls)!=1 or calls[0]['function']['name']!='propose_organization':raise ValueError('Exactly one proposal tool payload required')
  parse(calls[0]['function']['arguments'],state)
 except (ValueError,TypeError,KeyError) as e:errors=[{'response_error':str(e)}]
 else:raise ValueError('An already valid response must not be resampled by this recovery')
 wire=copy.deepcopy(first_request['payload']['wire']);wire['messages'].append(copy.deepcopy(first_response['choices'][0]['message']))
 for call in calls:wire['messages'].append({'role':'tool','tool_call_id':call['id'],'content':json.dumps({'errors':errors,'exact_mutable_ids':sorted(mutable_tasks(state))})})
 wire['messages'].append({'role':'user','content':'One permitted format/legality correction only. Errors: '+json.dumps(errors,ensure_ascii=False)+'. Return up to two valid alternatives, or fewer if none other can be grounded. Do not invent transfers, relations or outcomes.'})
 return wire,errors

def prepare_dispatch(wire,counter,remaining):
 proposed=copy.deepcopy(wire);quote=output_allocation(counter.measure(proposed)['prompt_tokens'],remaining,proposed['max_tokens'])
 if quote['dispatch']:proposed['max_tokens']=quote['max_tokens']
 return proposed,quote

def fallback_assessment(reason):
 return {'decision':'keep','demand_types':[],'reason':'System fallback preserves current structure because the bounded proposal correction was unavailable or invalid: '+str(reason)[:1200]+'. This is not a valid model endorsement; ordinary repair and missing setup remain allowed.'}
