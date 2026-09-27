"""Real CPU tool paths for A/B contracts; never target-model demonstrations."""
import argparse
import copy
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from proworksim.episode import begin_episode, finish_episode
from proworksim.experience import ExperienceRecorder, capture_port
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.templates import retail_collaboration_v021 as contract
from proworksim.templates.retail_work import witness_code
from proworksim.work_interface import WorkInterface


def rows(table):
    return [dict(zip([c['name'] for c in table['columns']], r)) for r in table['rows']]


def public_disagreements(data, product, rules):
    """Program worker calculation from its own public returns, not host grader."""
    transactions = rows(data['tables']['retail'])
    errors = []
    for index, row in enumerate(rows(product['tables']['metrics'])):
        eligible = [t for t in transactions if t['CustomerID'] == row['CustomerID']
                    and rules['start_inclusive'] <= t['InvoiceDate'] < rules['end_exclusive']
                    and Decimal(str(t['UnitPrice'])) > 0
                    and (rules['invoice_mode'] == 'net_signed' or (not t['InvoiceNo'].upper().startswith('C') and t['Quantity'] > 0))]
        amount = int((sum((Decimal(str(t['UnitPrice'])) * t['Quantity'] for t in eligible), Decimal(0)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        expected = {'revenue_pence': amount, 'invoice_count': len({t['InvoiceNo'] for t in eligible})}
        for column, cell in enumerate(product['tables']['metrics']['columns']):
            key = cell['name']
            if key in expected and row[key] != expected[key]:
                errors.append([index, column])
    return errors


class Witness:
    def __init__(self, prepared, output):
        self.prepared, self.output = prepared, Path(output)
        self.recorder = ExperienceRecorder()
        self.captures = {r: [] for r in prepared.active_roles}
        self.ports = {r: capture_port(prepared.world.session(r, 'TEAM'), self.captures[r]) for r in prepared.active_roles}
        self.environment_offset = len(prepared.world.state['event_history'])
        self.policies = {r: {'implementation': 'ExplicitCPUProgramWitness', 'model': False} for r in prepared.active_roles}
        self.episode = self.output / 'episode'
        begin_episode(prepared.world, self.episode, experience=self.recorder.snapshot(), work_ids=[contract.WORK], scenario=prepared.scenario, policies=self.policies)

    def observe(self, role):
        result = self.ports[role].observe()
        self.recorder.record('public_observation', result, role)
        return result

    def call(self, role, action, **arguments):
        response = self.ports[role].call(action, request_key='v21-cpu-' + str(len(self.recorder.events)), **arguments)
        self.recorder.record('tool_call', self.captures[role][-1]['payload'], role)
        for event in self.prepared.world.state['event_history'][self.environment_offset:]:
            self.recorder.record('environment_event', event)
        self.environment_offset = len(self.prepared.world.state['event_history'])
        if not response['ok']:
            raise ValueError({'role': role, 'action': action, 'response': response})
        return response['result']

    def read(self, role, alias):
        return self.call(role, 'read_alias', alias=alias, work_id=contract.WORK)

    def inspect(self, role, sid):
        fixed = self.call(role, 'inspect_submission', work_id=contract.WORK, submission_id=sid)
        aliases = self.observe(role)['workspaces']['TEAM']
        return {alias: self.call(role, 'read_version', reference={'object_id': aliases[alias], 'version_id': fixed['artifact_versions'][aliases[alias]]}, work_id=contract.WORK)
                for alias in ('code', 'result')}

    def build_submit(self, refs, defect=None):
        self.call('implementer', 'write_object', alias='code', data=witness_code(defect=defect), dependencies=refs, work_id=contract.WORK)
        built = self.call('implementer', 'sql_build', code_alias='code', output_alias='result', input_aliases=['data', 'basis'], work_id=contract.WORK)
        if built['execution_status'] != 'success':
            raise ValueError(built)
        return self.call('implementer', 'submit', work_id=contract.WORK, artifacts=['code', 'result'])['submission_id']

    def finish(self, status='cpu_witness_done'):
        finish_episode(self.prepared.world, self.episode, experience=self.recorder.snapshot(), termination={'status': status, 'origin': 'cpu_program_not_model'})
        score = contract.assess_episode(self.episode, self.prepared.reward_spec)
        atomic_write(self.output / 'capture.json', json_bytes(self.captures))
        atomic_write(self.output / 'experience.json', json_bytes(self.recorder.snapshot()))
        atomic_write(self.output / 'score.json', json_bytes(score))
        return score


def a_path(w, control):
    request = None
    if control == 'requested':
        request = w.call('implementer', 'request_information', route_id='basis', work_id=contract.WORK)
    ref = w.read('provider', 'basis')['reference']
    args = {'route_id': 'basis', 'work_id': contract.WORK, 'handoff_key': 'actual-policy', 'reference': ref, 'body': 'Applicable exact reporting policy for your declared work.'}
    if request:
        args['request_id'] = request['request_id']
    w.call('provider', 'handoff_information', **args)
    w.call('implementer', 'read_messages')
    if control == 'delivered_unused':
        return
    finish_a(w)


def finish_a(w):
    refs = []
    for alias in ('data', 'basis'):
        ref = w.read('implementer', alias)['reference']
        w.call('implementer', 'adopt', alias=alias, **ref, policy='fixed', work_ids=[contract.WORK])
        refs.append(ref)
    w.build_submit(refs)


def b_path(w, control):
    initial = w.observe('implementer')['work_items'][contract.WORK]['pending_submission_id']
    if control == 'no_actions':
        return
    if control == 'approval_without_evidence':
        w.call('reviewer', 'approve', work_id=contract.WORK, submission_id=initial)
        return
    # Implementer sees only the exact fixed work, actual data and delivered policy.
    impl = w.inspect('implementer', initial)
    source = {a: w.read('implementer', a) for a in ('data', 'basis')}
    own_errors = public_disagreements(source['data']['data'], impl['result']['data'], rows(source['basis']['data']['tables']['basis_meta'])[0])
    issue = None
    reviewer_source = None
    if control != 'self_check' or not own_errors:
        reviewer_source = {a: w.read('reviewer', a) for a in ('data', 'audit_basis')}
        inspected = w.inspect('reviewer', initial)
        errors = public_disagreements(reviewer_source['data']['data'], inspected['result']['data'], reviewer_source['audit_basis']['data'])
        if not errors or control == 'wrong_approval':
            w.call('reviewer', 'approve', work_id=contract.WORK, submission_id=initial)
            return
        loc = [0, 0] if control == 'wrong_location' else errors[0]
        issue = w.call('reviewer', 'raise_issue', work_id=contract.WORK, submission_id=initial,
                       issue_key='actual-disagreement', **inspected['result']['reference'],
                       locator=['tables', 'metrics', 'rows', *loc],
                       description='This exact cell disagrees with the independently read reporting policy and original invoice rows.',
                       evidence=[] if control == 'issue_without_evidence' else [v['reference'] for v in reviewer_source.values()])
        if control in {'wrong_location', 'issue_without_evidence'}:
            return
    if not own_errors:
        raise ValueError('Repair would manufacture a defect')
    w.call('implementer', 'read_messages')
    w.call('implementer', 'withdraw', work_id=contract.WORK, submission_id=initial, reason='Replace the actual erroneous fixed result after checking exact source facts.')
    final = w.build_submit([v['reference'] for v in source.values()], defect='wrong_count' if control == 'wrong_repair' else None)
    produced = w.read('implementer', 'result')
    response = None
    if issue:
        response = w.call('implementer', 'respond_issue', issue_id=issue['issue_id'], response_key='real-new-build',
                          submission_id=final, body='A new actual SQL build and fixed submission address the located metric defect.', evidence=[produced['reference']])
    if reviewer_source is None:
        reviewer_source = {a: w.read('reviewer', a) for a in ('data', 'audit_basis')}
    fixed = w.inspect('reviewer', final)
    errors = public_disagreements(reviewer_source['data']['data'], fixed['result']['data'], reviewer_source['audit_basis']['data'])
    if errors and control != 'wrong_repair':
        raise ValueError('CPU repair does not satisfy public business facts')
    if issue:
        w.call('reviewer', 'decide_issue', issue_id=issue['issue_id'], response_id=response['response_id'],
               decision_key='fixed-result-checked', decision='accept_fix', reason='Actual new fixed code/result inspected against independently read data/audit facts.')
    w.call('reviewer', 'approve', work_id=contract.WORK, submission_id=final)


def run_control(case, output, control):
    output = Path(output)
    prepared = contract.build_case(case, output)
    w = Witness(prepared, output)
    if case['task'] == 'joint_a':
        a_path(w, control)
    else:
        b_path(w, control)
    score = w.finish()
    return w, score


def main(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    a = next(c for c in contract.registry()['situations'] if c['task'] == 'joint_a')
    declarations = [
        ('A_proactive', a, 'proactive', True), ('A_requested', a, 'requested', True),
        ('A_delivered_unused', a, 'delivered_unused', False),
        ('B_correct_direct', contract.cpu_variant('correct'), 'feedback', True),
        ('B_correct_no_actions', contract.cpu_variant('correct'), 'no_actions', False),
        ('B_count_feedback', contract.cpu_variant('wrong_count'), 'feedback', True),
        ('B_amount_feedback', contract.cpu_variant('wrong_amount'), 'feedback', True),
        ('B_amount_self_check', contract.cpu_variant('wrong_amount'), 'self_check', True),
        ('B_wrong_approval', contract.cpu_variant('wrong_count'), 'wrong_approval', False),
        ('B_missing_evidence', contract.cpu_variant('correct'), 'approval_without_evidence', False),
        ('B_wrong_location', contract.cpu_variant('wrong_count'), 'wrong_location', False),
        ('B_issue_missing_evidence', contract.cpu_variant('wrong_count'), 'issue_without_evidence', False),
        ('B_wrong_repair', contract.cpu_variant('wrong_amount'), 'wrong_repair', False),
    ]
    result = {'version': contract.VERSION, 'scope': 'CPU real-world program controls only, not model trajectories, method support, training data or independent sources.',
              'model_calls': 0, 'gpu_calls': 0, 'training_updates': 0, 'controls': []}
    for name, case, mode, expected in declarations:
        w, score = run_control(case, output / name, mode)
        entry = {'name': name, 'case_id': case['case_id'], 'expected_complete': expected,
                 'score': score, 'passed': score['eligible'] and score['completed'] == expected,
                 'episode_ref': {'path': str((w.episode / 'manifest.json').resolve()), 'sha256': digest((w.episode / 'manifest.json').read_bytes())}}
        if name == 'A_delivered_unused':
            prior = copy.deepcopy(score)
            finish_a(w)  # Continue the LIVE world after the old episode already closed.
            entry['historical_no_backfill'] = contract.assess_episode(w.episode) == prior
            entry['passed'] &= entry['historical_no_backfill']
        if name == 'B_correct_no_actions':
            entry['prefix_not_credited'] = score['reward'] == 0
            entry['passed'] &= entry['prefix_not_credited']
        result['controls'].append(entry)
        atomic_write(output / 'report.json', json_bytes(result))
        print(name, score['eligible'], score['reward'], score['completed'], score['exclusions'], flush=True)
    # All three preparations differ only in real submitted code/result quality.
    prepared_cross = []
    for quality in contract.retail_balanced.QUALITIES:
        p = contract.build_case(contract.cpu_variant(quality), output / ('cross-' + quality))
        state, products = p.world.state, {}
        for alias in ('data', 'basis', 'audit_basis'):
            art = state['artifacts'][state['workspaces']['TEAM'][alias]]
            products[alias] = digest(p.world.store.version_path(art, 'v1').read_bytes())
        public = [WorkInterface(p.world.session(role, 'TEAM'), role, variant='v14').observe() for role in p.active_roles]
        no_labels = all(x not in json_bytes(public).decode() for x in ('wrong_count', 'wrong_amount', 'prepared_submission'))
        prepared_cross.append({'host_quality': quality, 'source_hashes': products, 'reward_spec': p.reward_spec,
                               'role_tasks': [r['config']['task'] for r in p.scenario['roles']], 'no_quality_labels': no_labels})
    result['crossed_quality_controls'] = prepared_cross
    result['same_policy_all_qualities'] = all(len({json_bytes(row[key]) for row in prepared_cross}) == 1 for key in ('source_hashes', 'reward_spec', 'role_tasks'))
    result['passed'] = all(c['passed'] for c in result['controls']) and result['same_policy_all_qualities'] and all(c['no_quality_labels'] for c in prepared_cross)
    atomic_write(output / 'report.json', json_bytes(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    raise SystemExit(0 if main(args.output)['passed'] else 1)
