"""Six fixed coding organizations for the existing managed OpenHands harness.

This catalog grants no model, Docker, GPU or evaluation authority. Roles and
turn windows are experimental treatments, not claims of paper reproduction.
"""
from __future__ import annotations

import copy
import hashlib
import json

VERSION = 'v065-fixed-coding-organizations-r2'
MEMBER_POOL = tuple(f'member_{number:03d}' for number in range(1, 5))
DELIVERY_MEMBER = MEMBER_POOL[0]
ORGANIZATION_IDS = ('CHIEF', 'SOP', 'DIALOGUE', 'REVIEW', 'PEER', 'COUNCIL')
MEMBER_COUNTS = {'CHIEF': 4, 'SOP': 3, 'DIALOGUE': 2, 'REVIEW': 2, 'PEER': 4, 'COUNCIL': 3}

COMMON = {
    'base_framework': 'OpenHands SDK through ProWorkSim HarnessPort and WorldCore',
    'members_per_team': 'fixed per organization, from two to four',
    'member_counts': MEMBER_COUNTS,
    'comparison_scope': 'representative combinations of team size, roles, direct routes and schedule',
    'team_size_ablation_automatically_authorized': False,
    'dynamic_membership': False,
    'context_limit': 131072,
    'maximum_input_tokens': 98304,
    'maximum_output_tokens': 32768,
    'team_token_budget': None,
    'budget_scope': 'one shared cumulative input plus output pool, not per-member copies',
    'team_decisions': 512,
    'team_attempts': 512,
    'team_public_tests': 512,
    'soft_seconds': 21600,
    'hard_seconds': 23400,
    'same_base_model_for_all_members': True,
    'training': False,
    'public_task_board': 'unchanged shared managed task metadata; not a private edge channel',
    'private_workspaces_and_histories': True,
    'direct_edges_cover': ['send_message', 'handoff_patch', 'responsibility_transfer'],
    'patch_use': 'fixed versions remain public under the existing harness; direct handoffs '
                 'follow declared routes and incorporation always requires explicit managed merge',
    'automatic_broadcast_or_merge': False,
    'public_tests': 'same confined repository public entrypoint and same-version evidence',
    'code_endpoint': 'unique final workspace of member_001 at the frozen closure boundary',
    'delivery_endpoint': 'last legal submission by member_001, separately evidenced and scored',
    'other_member_final_trees_are_candidates': False,
    'hidden_grading_feedback': False,
    'real_evaluation_enabled': False,
    'new_model_calls_authorized': 0,
    'new_api_cash_authorized_CNY': 0,
}

COMMON_INSTRUCTION = (
    'Work on the original coding issue using the managed project tools. '
    'All configured members share one total token, model-attempt, decision and public-test budget. '
    'A message, rejected call, history read or coordination step uses an ordinary opportunity. '
    'Each member owns a private versioned workspace and private observed history. '
    'Publishing a fixed patch exposes that exact version to the team under the existing harness; '
    'later private changes do not propagate. Explicitly merge a published patch to use it. '
    'Directed handoffs follow the declared routes, but publication remains a common information channel. '
    'Messages do not transfer ownership or copy code. Use offer/accept for responsibility changes. '
    'The task board also remains shared under the existing harness rules. '
    'Only member_001 can submit the final integration; this common export address grants no '
    'extra reading permissions and is not a manager in organizations without a manager. '
    'Do not create, remove, impersonate or change the roles of team members. '
    'Phase labels describe fixed action windows, not proof that a stage or task succeeded. '
    'staff_done does not merge, test, fix or submit your code automatically.'
)


def _role(title, instruction):
    return {'title': title, 'instruction': instruction}


def _edges(pairs):
    return sorted([a, b] for left, right in pairs
                  for a, b in ((MEMBER_POOL[left-1], MEMBER_POOL[right-1]),
                               (MEMBER_POOL[right-1], MEMBER_POOL[left-1])))


def _phase(name, active, opportunities):
    return {'name': name, 'active_members': [MEMBER_POOL[index-1] for index in active],
            'opportunities': opportunities}


def _organization(key, name, roles, edges, phases, inspiration, notes):
    members = MEMBER_POOL[:MEMBER_COUNTS[key]]
    return {'version': VERSION, 'id': key, 'name': name,
            'fixed_members': list(members), 'member_count': len(members),
            'roles': dict(zip(members, roles, strict=True)),
            'communication_edges': _edges(edges), 'phases': phases,
            'delivery_member': DELIVERY_MEMBER,
            'inspiration': inspiration, 'notes': notes,
            'schedule_semantics': 'repeat fixed windows; round-robin within each window; '
                'skip non-runnable members without a world action; consume actual attempts only',
            'role_descriptions_are_instructions_not_new_tool_powers': True,
            'public_task_board_is_shared': True,
            'automatic_evaluation_enabled': False}


_CATALOG = [
    _organization('CHIEF', '集中负责人', [
        _role('负责人兼集成者', 'Plan the repair, assign work through legal managed operations, '
              'coordinate findings, integrate received fixed patches and close delivery.'),
        _role('仓库定位员', 'Locate relevant code and explain the suspected mechanism to the lead. '
              'Provide concrete paths and observations without accessing hidden materials.'),
        _role('实现者', 'Implement the requested repair in your private workspace, validate it '
              'with permitted public tests and hand a fixed patch to the lead.'),
        _role('质量复核者', 'Review the fixed candidate received from the lead, check the issue '
              'and public test evidence, then report concrete concerns to the lead.')],
        [(1, 2), (1, 3), (1, 4)],
        [_phase('负责人规划', [1], 2), _phase('仓库定位', [2], 4),
         _phase('负责人分派', [1], 1), _phase('实现', [3], 8),
         _phase('负责人集成', [1], 3), _phase('质量复核', [4], 4),
         _phase('负责人闭合', [1], 2)],
        ['chief-programmer team', 'MAGIS'],
        ['Four fixed agents, not MAGIS dynamic per-task developer creation.',
         'Direct coordination between spokes must pass through the lead.']),
    _organization('SOP', '职能流水线', [
        _role('需求设计与集成', 'Clarify public issue requirements and repository design, then '
              'hand an implementation plan to member_002. Later integrate the validated fixed patch '
              'and close the same-version delivery.'),
        _role('实现', 'Implement the agreed repair in your private workspace, publish an '
              'immutable patch and describe changes and assumptions for member_003 to validate.'),
        _role('验证', 'Inspect the published candidate, explicitly integrate when needed, '
              'run permitted public tests and send precise evidence or revision requests.')],
        [(1, 2), (2, 3), (3, 1)],
        [_phase('需求与设计', [1], 4), _phase('实现', [2], 8),
         _phase('验证', [3], 6), _phase('集成交付', [1], 6)],
        ['functional specialization', 'MetaGPT SOP'],
        ['Three fixed members; requirements/design/integration share one role.',
         'Single-role windows use explicit artifacts; a stage label is not evidence of success.']),
    _organization('DIALOGUE', '阶段对话链', [
        _role('需求设计与集成', 'Discuss issue requirements and design with member_002, clarify '
              'ambiguous observations, then integrate the explicit returned patch and close delivery.'),
        _role('实现与自测', 'Discuss the proposed design with member_001, implement the repair '
              'and run permitted self-checks. Publish the actual fixed patch and report evidence.')],
        [(1, 2)],
        [_phase('需求设计对话', [1, 2], 8), _phase('实现自测对话', [2, 1], 8),
         _phase('交付确认对话', [1, 2], 8)],
        ['ChatDev phase and role dialogue chain'],
        ['Two fixed roles alternate in staged dialogue; this is an adaptation, not full ChatDev reproduction.',
         'Published versions stay team-public; all reads, merges and communication cost real opportunities.']),
    _organization('REVIEW', '开发复核返修', [
        _role('开发兼交付', 'Develop a repair, publish its fixed candidate for member_002 to '
              'review, address concrete feedback and perform the explicit same-version delivery.'),
        _role('独立复核', 'Independently inspect the developer candidate and issue coverage. '
              'Use actual public tests and source evidence, then return actionable revision feedback.')],
        [(1, 2)],
        [_phase('开发', [1], 8), _phase('独立复核', [2], 4),
         _phase('返修与集成', [1], 8), _phase('复核反馈', [2], 4)],
        ['modern code review development-review-revision loop'],
        ['Two fixed members separate implementation from independent review.',
         'Review remains an instructed responsibility, not a new read-only ACL or hidden-score oracle.']),
    _organization('PEER', '扁平同伴协作', [
        _role('同伴甲兼交付出口', 'Self-organize with your peers using the task board and explicit '
              'messages. You have no managerial or extra visibility powers; integrate the agreed final code.'),
        *[_role(f'同伴{label}', 'Self-organize with the other peers, choose useful work from '
                'public information, and explicitly coordinate responsibilities and fixed patches.')
          for label in ('乙', '丙', '丁')]],
        [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)],
        [_phase('同伴轮转', [1, 2, 3, 4], 4)],
        ['self-managing team'],
        ['Fixed membership and turn order; only work allocation is self-organized.',
         'member_001 is the common export address, not an elected or privileged manager.']),
    _organization('COUNCIL', '专家会诊', [
        _role('需求与集成专家', 'Analyze issue semantics and repository constraints in the joint '
              'discussion. Later integrate the chosen published implementation with explicit evidence.'),
        _role('实现专家', 'Contribute implementation hypotheses in the joint discussion, then '
              'build the discussed repair and publish an immutable candidate for verification.'),
        _role('验证专家', 'Contribute failure hypotheses and edge cases in the joint discussion, '
              'then inspect the candidate and report actual public validation evidence.')],
        [(1, 2), (1, 3), (2, 3)],
        [_phase('专家会诊', [1, 2, 3], 6), _phase('集中实现', [2], 8),
         _phase('验证反馈', [3], 4), _phase('集成闭合', [1], 4)],
        ['AgentVerse expert collaboration and feedback'],
        ['Three fixed experts; no recruitment, replacement or hidden-score voting.',
         'Unlike four-member PEER, this baseline changes team size as well as roles and staged activation.']),

]


def get_organization(organization_id):
    if organization_id not in ORGANIZATION_IDS:
        raise ValueError('Unknown fixed organization: ' + str(organization_id))
    return copy.deepcopy(next(row for row in _CATALOG if row['id'] == organization_id))


def catalog():
    return [get_organization(key) for key in ORGANIZATION_IDS]


def validate_organization(spec):
    if not isinstance(spec, dict) or spec != get_organization(spec.get('id')):
        raise ValueError('Organization roles, identities, topology or schedule changed')
    ordered_members = MEMBER_POOL[:MEMBER_COUNTS[spec['id']]]
    members = set(ordered_members)
    edges = {tuple(edge) for edge in spec['communication_edges']}
    if (set(spec['roles']) != members or spec['fixed_members'] != list(ordered_members)
            or spec['member_count'] != len(ordered_members)
            or spec['delivery_member'] != DELIVERY_MEMBER
            or len(edges) != len(spec['communication_edges'])
            or any(a == b or a not in members or b not in members or (b, a) not in edges for a, b in edges)):
        raise ValueError('Fixed organizations need their declared two-to-four identities and explicit bidirectional routes')
    covered = set()
    for phase in spec['phases']:
        active, count = phase['active_members'], phase['opportunities']
        if (not active or len(set(active)) != len(active) or not set(active) <= members
                or type(count) is not int or count < len(active) or count % len(active)):
            raise ValueError('Each phase has complete deterministic turns for its active members')
        covered.update(active)
    if covered != members:
        raise ValueError('Every configured member must have real scheduled opportunities')
    return copy.deepcopy(spec)


def catalog_sha256():
    raw = json.dumps({'version': VERSION, 'common': COMMON, 'organizations': catalog()},
                     sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def role_instruction(organization_id, member_id):
    spec = get_organization(organization_id)
    if member_id not in spec['fixed_members']:
        raise ValueError('Only this organization’s configured members have an organizational role')
    partners = [target for source, target in spec['communication_edges'] if source == member_id]
    return (COMMON_INSTRUCTION + '\nYour fixed role: ' + spec['roles'][member_id]['instruction'] +
            '\nYour direct collaboration partners: ' + ', '.join(partners) +
            '.\nFixed repeating action windows: ' +
            '; '.join(phase['name'] + ' [' + ','.join(phase['active_members']) + '], ' +
                      str(phase['opportunities']) + ' opportunities' for phase in spec['phases']))


def require_evaluation_disabled():
    """Explicit preparation boundary; no reuse of v064 launch authorization."""
    raise PermissionError('v065 is implementation-only. Wait for the single-model token study '
                          'and a separately frozen, reviewed evaluation plan before any real model call.')
