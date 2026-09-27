"""Actual native/compact WorldCore feasibility paths; explicit CPU programs only."""
import argparse
import copy
import json
from collections import Counter
from pathlib import Path

from proworksim.episode import begin_episode, finish_episode
from proworksim.online_collection import run_fragment
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.templates import retail_collaboration_v023 as contract
from proworksim.templates.retail_work import witness_code
from proworksim.templates.retail_collaboration_v023 import runtime
from scripts.retail_collaboration_experiment_v021 import public_disagreements, rows


class ProgramOwner:
    """Uses only each role's actual public request/returns; no world handle."""
    recipe = {'temperature': .7, 'max_output_tokens': 2048, 'max_length': 16384}

    def __init__(self, task, tokenizer=None, control='complete'):
        self.task, self.tokenizer, self.control = task, tokenizer, control
        self.transport = self
        self.states, self.requests, self.actions = {}, [], []
        self.tokens = []

    def freeze_identity(self):
        return {'policy_version': 'explicit-cpu-program-v023-not-a-model'}

    def ingest(self, role, request):
        s = self.states.setdefault(role, {'step': 0, 'materials': {}, 'inspects': {}, 'seen': set()})
        associations = {}
        for m in request['messages']:
            if m.get('role') == 'assistant':
                associations.update({c['id']: c['function'] for c in m.get('tool_calls', [])})
            if m.get('role') != 'tool' or m['tool_call_id'] in s['seen']:
                continue
            s['seen'].add(m['tool_call_id'])
            body = json.loads(m['content'])
            if body.get('ok') is False:
                raise ValueError({'program_world_tool_failed': body})
            if not body.get('ok'):
                continue
            f = associations[m['tool_call_id']]
            name, result = f['name'], body['result']
            s['last'] = result
            if name in {'read_alias', 'read_version'}:
                s['materials'][result['reference']['object_id']] = result
            if name == 'inspect_submission':
                s['inspects'][result['submission_id']] = result
        return s

    def choose(self, role, obs, s):
        wid, aliases = contract.WORK, obs['workspaces']['TEAM']
        step = s['step']
        pending = obs['work_items'][wid]['pending_submission_id']
        work = {'work_id': wid}
        done = ('staff_done', {'reason': 'Explicit CPU feasibility program finished; not model evidence.'})
        if self.control == 'no_actions':
            return done
        if role == 'provider':
            if step == 0:
                return 'read_alias', {**work, 'alias': 'basis'}
            if step == 1:
                return 'handoff_information', {**work, 'route_id': 'basis', 'handoff_key': 'cpu-actual-policy',
                       'reference': s['materials'][aliases['basis']]['reference'], 'body': 'Actual applicable policy delivery.'}
            return done
        if role == 'implementer':
            if self.task in {'joint_b', 'maintenance'}:
                if step == 0:
                    s['initial'] = pending
                    return 'inspect_submission', {**work, 'submission_id': pending}
                if step in (1, 2):
                    alias = 'code' if step == 1 else 'result'
                    return 'read_version', {**work, 'reference': {'object_id': aliases[alias], 'version_id': s['inspects'][s['initial']]['artifact_versions'][aliases[alias]]}}
                if step in (3, 4):
                    return 'read_alias', {**work, 'alias': 'data' if step == 3 else 'basis'}
                source = s['materials']
                errors = public_disagreements(source[aliases['data']]['data'], source[aliases['result']]['data'], rows(source[aliases['basis']]['data']['tables']['basis_meta'])[0])
                if not errors and self.control != 'unnecessary_rebuild':
                    return done
                if self.control == 'stale_retention':
                    return done
                if step == 5:
                    return 'withdraw', {**work, 'submission_id': s['initial'], 'reason': 'Actual fixed cells disagree with the applicable current policy.'}
                phase = step - 6
                if self.task == 'maintenance':
                    if phase == 0:
                        return 'adopt_version', {**work, 'alias': 'basis', 'version_id': source[aliases['basis']]['reference']['version_id']}
                    phase -= 1
                if phase == 0:
                    return 'write_object', {**work, 'alias': 'code', 'data': witness_code(), 'dependencies': [source[aliases[a]]['reference'] for a in ('data', 'basis')]}
                if phase == 1:
                    return 'sql_build', {**work, 'code_alias': 'code', 'output_alias': 'result', 'input_aliases': ['data', 'basis']}
                if phase == 2:
                    return 'submit', {**work, 'artifacts': ['code', 'result']}
                return done
            if self.task == 'implement':
                if step in (0, 1):
                    return 'read_alias', {**work, 'alias': 'data' if step == 0 else 'basis'}
                step += 2
            elif self.task == 'joint_a':
                if step == 0:
                    return 'read_messages', {}
                step -= 1
                if self.control == 'delivered_unused':
                    return done
            if step in (0, 2):
                return 'read_alias', {**work, 'alias': 'data' if step == 0 else 'basis'}
            if step in (1, 3):
                alias = 'data' if step == 1 else 'basis'
                return 'adopt', {'alias': alias, **s['materials'][aliases[alias]]['reference'], 'policy': 'fixed', 'work_ids': [wid]}
            if step == 4:
                return 'write_object', {**work, 'alias': 'code', 'data': witness_code(), 'dependencies': [s['materials'][aliases[a]]['reference'] for a in ('data', 'basis')]}
            if step == 5:
                return 'sql_build', {**work, 'code_alias': 'code', 'output_alias': 'result', 'input_aliases': ['data', 'basis']}
            if step == 6:
                return 'submit', {**work, 'artifacts': ['code', 'result']}
            return done
        if self.control == 'approval_without_evidence':
            return ('approve', {**work, 'submission_id': pending}) if step == 0 else done
        if step in (0, 1):
            return 'read_alias', {**work, 'alias': 'data' if step == 0 else 'audit_basis'}
        if self.task in {'joint_b', 'maintenance'} and self.control not in {'stale_retention', 'wrong_approval'} and step < 10:
            return 'staff_wait', {'reason': 'Reserve independent final review until the implementer has had the fixed initial self-check opportunities.'}
        phase = s.get('review_phase', 0)
        if phase == 0:
            if pending is None:
                return 'staff_wait', {'reason': 'Await an actual fixed submission.'}
            s['review_sid'] = pending
            s['review_phase'] = 1
            return 'inspect_submission', {**work, 'submission_id': pending}
        if phase in (1, 2):
            alias = 'code' if phase == 1 else 'result'
            s['review_phase'] = phase + 1
            return 'read_version', {**work, 'reference': {'object_id': aliases[alias], 'version_id': s['inspects'][s['review_sid']]['artifact_versions'][aliases[alias]]}}
        if phase == 3:
            source = s['materials']
            errors = public_disagreements(source[aliases['data']]['data'], source[aliases['result']]['data'], source[aliases['audit_basis']]['data'])
            if self.control in {'wrong_approval', 'stale_retention'}:
                s['review_phase'] = 4
                return 'approve', {**work, 'submission_id': s['review_sid']}
            if not errors:
                s['review_phase'] = 4
                return 'approve', {**work, 'submission_id': s['review_sid']}
            if self.task == 'review':
                s['review_phase'] = 4
                return 'raise_issue', {**work, 'submission_id': s['review_sid'], 'issue_key': 'cpu-actual-wrong-cell',
                       **source[aliases['result']]['reference'], 'locator': ['tables', 'metrics', 'rows', *errors[0]],
                       'description': 'The fixed cell disagrees with the independently read source data and audit policy.',
                       'evidence': [source[aliases[a]]['reference'] for a in ('data', 'audit_basis')]}
            if pending and pending != s['review_sid']:
                s['review_sid'] = pending
                s['review_phase'] = 1
                return 'inspect_submission', {**work, 'submission_id': pending}
            return 'staff_wait', {'reason': 'The observed product is incorrect; await the implementer actual fixed replacement before judgment.'}
        return done

    def complete(self, request, *, timeout_seconds):
        self.requests.append(copy.deepcopy(request))
        body = json.loads(request['messages'][-1]['content'])
        obs = body['observation']
        role = obs['actor_id']
        state = self.ingest(role, request)
        name, args = self.choose(role, obs, state)
        state['step'] += 1
        call = {'id': f'cpu-{role}-{state["step"]}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}
        response = {'role': 'assistant', 'content': None, 'tool_calls': [call]}
        prompt_n, output_n = 1, 1
        if self.tokenizer is not None:
            from proworksim.candidate_runtime_v015 import prepare_candidate_prompt
            rendered, _, projection = prepare_candidate_prompt(request, self.tokenizer, {'chat_template_kwargs': {'enable_thinking': False, 'preserve_thinking': False}})
            prompt_n = len(self.tokenizer(rendered, add_special_tokens=False)['input_ids'])
            wire = '<tool_call>\n<function=' + name + '>\n' + '\n'.join('<parameter=' + k + '>' + (v if isinstance(v, str) else json.dumps(v)) + '</parameter>' for k, v in args.items()) + '\n</function>\n</tool_call><|im_end|>'
            output_n = len(self.tokenizer(wire, add_special_tokens=False)['input_ids'])
            self.tokens.append({'role': role, 'decision': state['step'], 'action': name, 'prompt_tokens': prompt_n, 'program_output_tokens': output_n,
                                'fits_prompt_and_reserved_output': prompt_n + 2048 <= 16384,
                                'program_output_within_limit': output_n <= 2048, 'projection': projection})
        if prompt_n + 2048 > 16384:
            result = {'error': {'code': 'context_length_exceeded', 'message': 'Actual official tokenizer prompt plus fixed2048 output exceeds16384; explicit CPU transport enforces the real local service gate.'}}
            return {'http_status': 400, 'body': result, 'raw_body': json.dumps(result), 'headers': {}}
        self.actions.append({'role': role, 'action': name})
        result = {'choices': [{'message': response, 'finish_reason': 'tool_calls'}],
                  'usage': {'prompt_tokens': prompt_n, 'completion_tokens': output_n, 'total_tokens': prompt_n + output_n}}
        return {'http_status': 200, 'body': result, 'raw_body': json.dumps(result), 'headers': {}}


def run_control(case, output, tokenizer=None, control='complete'):
    output = Path(output)
    prepared = contract.build_case(case, output)
    owner = ProgramOwner(case['task'], tokenizer, control)
    runner, capture, _ = runtime(owner, prepared, output, 'compact_work')
    episode = output / 'episode'
    begin_episode(prepared.world, episode, experience=runner.recorder.snapshot(), work_ids=[contract.WORK], scenario=prepared.scenario, policies=runner.policy_identities)
    stop = run_fragment(prepared, runner)
    finish_episode(prepared.world, episode, experience=runner.recorder.snapshot(), termination=stop)
    score = contract.assess_episode(episode)
    counts = dict(Counter(r['role'] for r in owner.actions))
    attempts = dict(Counter(json.loads(r['messages'][-1]['content'])['observation']['actor_id'] for r in owner.requests))
    result = {'case_id': case['case_id'], 'task': case['task'], 'control': control,
              'scope': 'Explicit CPU programs through actual native ModelPolicy, compact presentation, WorkInterface and WorldCore. No model generation, teacher/context transfer or parameter training.',
              'model_calls': 0, 'program_decisions': counts, 'program_request_attempts': attempts, 'role_limits': case['role_decision_limits'],
              'within_role_budgets': all(attempts[r] <= case['role_decision_limits'][r] for r in attempts),
              'tokenizer_checked': tokenizer is not None, 'token_lengths': owner.tokens,
              'maximum_prompt_tokens': max((r['prompt_tokens'] for r in owner.tokens), default=None),
              'fits_context': all(r['program_output_within_limit'] for r in owner.tokens) and bool(score['eligible'] and score['completed']) if tokenizer else None,
              'context_rejected_requests': [r for r in owner.tokens if not r['fits_prompt_and_reserved_output']],
              'context_check_scope': 'Every actual world action passed the real tokenizer prompt+2048 gate. A later nonessential stop can receive the genuine local400 after full responsibility is already achieved; no rejected request executes.',
              'prepared_business_state_sha256': prepared.prefix['prepared_business_state_sha256'],
              'policy_identities_sha256': digest(json_bytes(runner.policy_identities)),
              'score': score, 'termination': stop,
              'episode_reference': {'path': str((episode / 'manifest.json').resolve()), 'sha256': digest((episode / 'manifest.json').read_bytes())}}
    atomic_write(output / 'control.json', json_bytes(result))
    atomic_write(output / 'requests.json', json_bytes(owner.requests))
    atomic_write(output / 'capture.json', json_bytes(capture))
    return result


def main(output, tokenizer_path=None, case_indices=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    tokenizer = None
    if tokenizer_path:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True)
    catalog = contract.registry()
    cases = catalog['all_cases']
    selected = list(range(len(cases))) if case_indices is None else case_indices
    report = {'version': 'retail-work-cpu-feasibility-v0.23', 'model_calls': 0, 'gpu_calls': 0, 'training_updates': 0,
              'source_manifest_sha256': digest(contract.PIN_PATH.read_bytes()), 'controls': [],
              'scope': 'Existence of one legal finite route under actual presentation/tokenizer; not the global shortest route, likelihood under the model, teacher data or a model score.'}
    for i in selected:
        row = run_control(cases[i], output / f'case-{i:02d}', tokenizer)
        row['passed'] = bool(row['score']['eligible'] and row['score']['completed'] and row['within_role_budgets'] and (row['fits_context'] is not False))
        report['controls'].append(row)
        atomic_write(output / 'report.json', json_bytes(report))
        print(i, row['task'], row['score']['reward'], row['program_decisions'], row['maximum_prompt_tokens'], row['score']['exclusions'], flush=True)
    report['passed'] = all(r['passed'] for r in report['controls'])
    atomic_write(output / 'report.json', json_bytes(report))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    p.add_argument('--tokenizer')
    p.add_argument('--case-indices', type=int, nargs='+')
    a = p.parse_args()
    raise SystemExit(0 if main(a.output, a.tokenizer, a.case_indices)['passed'] else 1)
