"""Independent assessment, feasibility and action axes; old labels stay frozen."""
from __future__ import annotations

VERSION = 'v203.3.1-organization-decision-r1'
STATES = {'PRESENT', 'ABSENT', 'UNKNOWN'}
KEEP_REASONS = {'organization_suitable', 'insufficient_expected_gain', 'switch_cost',
                'remaining_budget', 'no_legal_alternative', 'experimental_control'}


def validate_decision(row):
    if row.get('version') != VERSION:
        raise ValueError('New decision schema required; do not reinterpret old labels')
    for axis in ('constraint_gap', 'efficiency_opportunity'):
        if row.get(axis) not in STATES:
            raise ValueError('Declare constraint gap and potential efficiency separately')
    feasible=row.get('feasibility')
    if feasible not in {'FEASIBLE','INFEASIBLE','UNKNOWN'}:
        raise ValueError('Explicit feasibility required')
    action=row.get('action')
    if action=='NO_CHANGE':
        if row.get('reason') not in KEEP_REASONS:
            raise ValueError('Keeping an organization needs a decision reason')
        if row['reason']=='no_legal_alternative' and feasible!='INFEASIBLE':
            raise ValueError('No legal alternative must match feasibility')
    elif action=='ABSTAIN':
        if row.get('reason')!='insufficient_evidence':
            raise ValueError('Abstain describes epistemic uncertainty, not budget refusal')
    elif action=='INTERVENE':
        if feasible!='FEASIBLE' or not row.get('legal_action_evidence'):
            raise ValueError('Intervention needs a legal executable alternative')
        if row.get('reason') not in {'constraint_remedy','efficiency_hypothesis','preregistered_probe'}:
            raise ValueError('Declare why intervention is being considered')
        # An experimental probe does not need a pre-labelled positive effect.
        if row.get('predicted_effect_is_established') is not False:
            raise ValueError('Do not predeclare the experimental effect as established')
    else:
        raise ValueError('Action must be NO_CHANGE, ABSTAIN or INTERVENE')
    if row.get('constraint_gap')=='PRESENT' and not row.get('state_evidence'):
        raise ValueError('Retain evidence for a claimed gap even when keeping the organization')
    return {'valid':True,'gap_implies_intervention':False,'effect_verified':False}


def validate_work_package(package):
    """First intervention is diagnostic work reassignment, never code authorship laundering."""
    if package.get('kind')!='public_diagnosis':
        raise ValueError('First action supports public diagnostic work only')
    if {package.get('old_owner'),package.get('new_owner')}!={'member_001','member_002'}:
        raise ValueError('Use the same two actual members')
    if package.get('delivery_member')!='member_001' or package.get('final_reviewer')!='member_002':
        raise ValueError('Frozen final delivery/review responsibilities do not move')
    if package.get('implementation_author')!='member_001':
        raise ValueError('Do not make the implementer its own nominally independent reviewer')
    if not package.get('task_id') or not package.get('source_reference') or not package.get('next_work'):
        raise ValueError('Bind task, source version and actual remaining work')
    if any(step.get('tool') not in {'read_file','search_repository','run_tests','send_message'}
           for step in package['next_work']):
        raise ValueError('Diagnostic package cannot silently assign code mutation or formal acceptance')
    if not package.get('other_member_work'):
        raise ValueError('Describe the counterpart work and dependency wait')
    return package
