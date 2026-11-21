"""Prospectively frozen OA-only replay over two complete archived development panels."""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_benchmark_deepseek_api_v105 import load_api_key
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_natural_checkpoint_v224_2 import effective_alternative, effect_signature
from proworksim.software_organization_api_v204 import Backend, DirectHTTPS, Ledger
from proworksim.software_organization_generator_v217 import compile_target
from proworksim.software_organization_planning_v223 import parse, tool
from proworksim.software_organization_proposal_budget_v223_2 import prepare_dispatch
from proworksim.work_interface import _schema_errors

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'runs/software-benchmark-v224-4/oa-r1'
PUBLIC = ROOT / 'artifacts/software-benchmark-v224-4/oa-r1'
PLAN = PUBLIC / 'plan.json'
LIMIT = 200_000
EXPLICIT_FORMAT = (' For keep or defer return candidates: []. A KEEP entry is already supplied '
                   'by the evaluator. For propose, include only grounded alternatives. '
                   'The assessment has exactly decision, demand_types and reason.')

def read(path):
    return json.loads(path.read_text())

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

def prepare():
    early = ROOT / 'runs/software-benchmark-v224-2/development4-r1'
    archive = ROOT / 'runs/software-benchmark-v223-1/paired4-r1'
    original = min((early/'task-00/GENERATOR/physical-api').glob('*/request.json'),
                   key=lambda path: read(path)['time'])
    rows = []
    for index in (2, 3):
        task = archive / f'task-{index:02d}'
        rows.append({'slot': f'v224.4:oa:dev2-{index}', 'index':index,
                     'instance':read(task/'PREFIX/result.json')['instance_id'],
                     'checkpoint':read(task/'PREFIX/result.json')['checkpoint'],
                     'graph':reference(task/'GRAPH/result.json'),
                     'input':reference(task/'GEN-W1/generator-visible-input.json')})
    PUBLIC.mkdir(parents=True, exist_ok=False)
    save(PLAN, {'rows': rows, 'template': reference(original), 'runner': reference(Path(__file__)),
                'additional_instruction': EXPLICIT_FORMAT, 'tokens_per_slot': LIMIT,
                'maximum_total_CNY': len(rows)*LIMIT*8000/1e9,
                'endpoint': 'unique compiled non-KEEP with legal action schema',
                'denominator': 'both available v223.1 developer checkpoints, including KEEP and unknown',
                'policy_input': reference(ROOT/'artifacts/software-benchmark-v224-3/pair-r1/result.json'),
                'max_logical_requests_per_state': 2, 'no_solver_or_hidden_scores': True})

def classify(body, state):
    calls = body['choices'][0]['message'].get('tool_calls') or []
    if len(calls) != 1 or calls[0]['function']['name'] != 'propose_organization':
        raise ValueError('Return one propose_organization tool call')
    args, _ = parse(calls[0]['function']['arguments'], state)
    candidates, errors = {}, []
    for proposal in args['candidates']:
        try:
            candidate = compile_target(state, proposal)
            if not effective_alternative(state, candidate):
                raise ValueError('Equivalent to KEEP')
            for action in candidate['actions']:
                params = action.get('arguments', {'offer_id': 'actual-offer-receipt'})
                issues = _schema_errors(state['proposal_tool_schemas'][action['tool']], params)
                if issues:
                    raise ValueError(str(issues))
            candidates[effect_signature(candidate)] = candidate
        except (KeyError, TypeError, ValueError) as error:
            errors.append(str(error))
    if args['assessment']['decision'] == 'propose' and not candidates:
        raise ValueError(str(errors or ['No alternative provided']))
    return {'result': args['assessment']['decision'], 'assessment': args['assessment'],
            'alternatives': list(candidates.values()), 'rejections': errors}

def run():
    plan = read(PLAN)
    checked(plan['runner'])
    template = read(checked(plan['template']))['payload']['wire']
    inputs = {r['slot']: read(checked(r['input'])) for r in plan['rows']}
    ledger = object.__new__(Ledger)  # reuse transactions, keep existing shared cap metadata
    ledger.path = ROOT / 'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'
    tok = ROOT / 'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
    key = load_api_key(ROOT/'.env')
    RUN.mkdir(parents=True, exist_ok=False)
    with ledger.db() as db:
        assert db.execute("SELECT value FROM meta WHERE key='cap'").fetchone()==('1100000000000',)
        assert not db.execute("SELECT 1 FROM slots WHERE status!='closed'").fetchone()
        assert not db.execute("SELECT 1 FROM block_slots WHERE status='pending'").fetchone()
        exposure = db.execute('SELECT COALESCE(sum(cost),0) FROM requests').fetchone()[0]
        assert exposure + len(inputs)*LIMIT*8000 <= 1000*10**9
        db.executemany("INSERT INTO block_slots VALUES(?, 'v224.4:oa', ?, 'pending')",
                       [(slot,LIMIT) for slot in inputs])
    def replay(row):
        slot = row['slot']
        out = RUN / slot.split(':')[-1]
        out.mkdir()
        ledger.admit(slot,LIMIT)
        result = {'result':'technical_unknown','alternatives':[]}
        try:
            counter = OfficialDeepSeekCounter(tok,manifest_sha256=reference(tok)['sha256'])
            backend = Backend(out/'api',ledger,slot,counter,DirectHTTPS(key,timeout_seconds=180),
                              {'propose_organization'})
            state = inputs[slot]['actual_decision_state']
            wire = {**template,'tools':[tool(state)],'messages':[
                {'role':'system','content':template['messages'][0]['content']+plan['additional_instruction']},
                {'role':'user','content':json.dumps(inputs[slot],ensure_ascii=False)}]}
            errors = []
            for attempt in range(2):
                with ledger.db() as db:
                    used = db.execute('SELECT COALESCE(sum(tokens),0) FROM requests WHERE slot=?',(slot,)).fetchone()[0]
                wire, allocation = prepare_dispatch(wire,counter,LIMIT-used)
                if not allocation['dispatch']:
                    result = {'result':'allocation_boundary','alternatives':[]}
                    break
                body = backend.post('/chat/completions',{'wire':wire,'team_slot_id':slot,'member_id':'member_001','usage_id':'agent'})
                try:
                    result = classify(body,state)
                    break
                except (KeyError,TypeError,ValueError) as err:
                    errors.append(str(err))
                    result = {'result':'invalid','alternatives':[]}
                    message = body['choices'][0]['message']
                    wire['messages'].append(message)
                    for call in message.get('tool_calls') or []:
                        wire['messages'].append({'role':'tool','tool_call_id':call['id'],'content':str(err)})
                    wire['messages'].append({'role':'user','content':'Correct the format or legality once. '+EXPLICIT_FORMAT})
            result['response_errors'] = errors
        except Exception as err:
            result['error'] = f'{type(err).__name__}: {err}'
        finally:
            ledger.close(slot)
        save(out/'result.json',result)
        return {**row,'decision':result['result'],'alternative_count':len(result['alternatives']),
                'receipt':reference(out/'result.json')}
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(replay,plan['rows']))
    with ledger.db() as db:
        usage = db.execute("SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot GLOB 'v224.4:oa:*' GROUP BY status").fetchall()
        spent = db.execute("SELECT sum(cost)/1e9 FROM requests WHERE status='settled'").fetchone()[0]
    save(PUBLIC/'results.json',{'rows':rows,'usage':usage,'cumulative_paid':spent})

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['prepare','run'])
    (prepare if parser.parse_args().mode=='prepare' else run)()
