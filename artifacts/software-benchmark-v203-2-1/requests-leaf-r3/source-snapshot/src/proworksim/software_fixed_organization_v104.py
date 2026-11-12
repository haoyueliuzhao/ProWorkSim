"""Five organization contracts on one managed coding harness; evaluation disabled."""
from __future__ import annotations

import copy
import hashlib
import json

from . import software_fixed_organization_v065 as previous

VERSION = 'v104-five-fixed-organizations-r1'
MEMBER_POOL = previous.MEMBER_POOL
DELIVERY_MEMBER = MEMBER_POOL[0]
ORGANIZATION_IDS = ('CHIEF', 'PIPELINE', 'REVIEW', 'SPRINT', 'MATRIX')
MEMBER_COUNTS = {'CHIEF': 4, 'PIPELINE': 3, 'REVIEW': 2, 'SPRINT': 4, 'MATRIX': 4}
SPRINT_OPPORTUNITIES = 24
COMMON = {**copy.deepcopy(previous.COMMON), 'member_counts': MEMBER_COUNTS,
    'organization_contracts_enforced': True,
    'comparison_scope': 'fixed sizes, decision rights and evidence-bound organization protocols',
    'schedule': 'fair round-robin filtered by persisted organization eligibility',
    'phase_progress': 'explicit accepted evidence, never a repeating clock alone',
    'sprint_control_opportunities': SPRINT_OPPORTUNITIES,
    'sprint_formal_quota_frozen': False,
    'real_evaluation_enabled': False, 'new_model_calls_authorized': 0}

COMMON_INSTRUCTION = (
    previous.COMMON_INSTRUCTION.replace(
        'Phase labels describe fixed action windows, not proof that a stage or task succeeded. ',
        'Organization state and accepted evidence determine eligible actions; a turn never '
        'advances a handoff or declares success by itself. ')
    + ' Organization decisions are real budgeted tools, not informal text authority. '
      'Inspect the public organization state for the exact task revisions and candidate versions. '
      'Missing or stale organization evidence blocks only that action; correct it through the '
      'documented tools. The original same-version test, fixed patch and explicit submission '
      'requirements still apply. No role obtains another member\'s private workspace or history.'
)


def _role(title, instruction):
    return {'title': title, 'instruction': instruction}


def _spec(key, name, roles, mechanism, instruction, sources):
    members = list(MEMBER_POOL[:MEMBER_COUNTS[key]])
    edges = ([[a, b] for a in members for b in members if a != b]
             if key != 'CHIEF' else [[a, b] for a in members for b in members
                                    if a != b and DELIVERY_MEMBER in (a, b)])
    return {'version': VERSION, 'id': key, 'name': name,
        'fixed_members': members, 'member_count': len(members),
        'roles': dict(zip(members, roles, strict=True)),
        'communication_edges': sorted(edges), 'delivery_member': DELIVERY_MEMBER,
        'phases': [{'name': '组织状态约束下的公平轮转', 'active_members': members,
                    'opportunities': len(members)}],
        'mechanism': mechanism, 'organization_instruction': instruction,
        'sprint_opportunities': SPRINT_OPPORTUNITIES if key == 'SPRINT' else None,
        'sprint_quota_status': 'CPU implementation control; formal evaluation not frozen' if key == 'SPRINT' else None,
        'schedule_semantics': 'round-robin over eligible runnable members; no automatic handoff, '
                              'test, merge, decision, submission or next sprint',
        'role_descriptions_are_instructions_not_new_tool_powers': False,
        'role_file_ACLs_unchanged': True, 'public_task_board_is_shared': True,
        'inspiration': sources, 'notes': ['Project adaptation, not a complete source-method reproduction.'],
        'automatic_evaluation_enabled': False}


_CATALOG = [
    _spec('CHIEF', '集中负责人', [
        _role('负责人兼集成者', 'Authorize task assignments and integration choices. Preserve current '
              'ownership until its owner and recipient execute the ordinary accepted transfer.'),
        _role('仓库定位员', 'Locate code and report concrete evidence to the lead. Accept only '
              'assignments authorized by the lead; do not acquire managerial rights.'),
        _role('实现者', 'Implement assigned work in your own workspace, test and publish a fixed '
              'patch for the lead to select and explicitly integrate.'),
        _role('质量复核者', 'Inspect published candidates and send evidence-based advice to the lead; '
              'you do not replace its organization decision authority.')],
        'centralized_assignment_and_integration',
        'Only member_001 authorizes assignments and candidate choices. Ordinary messages do not '
        'grant these rights or transfer task ownership.', ['chief-programmer team', 'MAGIS']),
    _spec('PIPELINE', '产物交接流水线', [
        _role('需求设计与最终集成', 'Create and hand off a task-bound design. Later integrate '
              'the verified fixed candidate; do not skip the evidence-gated stages.'),
        _role('实现', 'Implement the accepted design, own the relevant task through its normal '
              'claim or accepted transfer, and hand off an immutable candidate.'),
        _role('验证', 'Explicitly adopt the candidate, execute public tests on that exact tree, '
              'and hand back evidence or return the work for a named reason.')],
        'artifact_gated_pipeline',
        'Design, implementation and verification handoffs must bind exact task revisions, patch '
        'identities and executed test evidence. Exhausting turns is not stage completion.',
        ['functional standardization', 'MetaGPT SOP']),
    _spec('REVIEW', '开发复核返修', [
        _role('开发兼交付', 'Develop and publish your candidate. Obtain an independent review '
              'of that precise version and satisfy the normal delivery evidence.'),
        _role('独立复核', 'Review member_001\'s published candidate and record acceptance or '
              'requested changes bound to its exact version. You may inspect and test privately.')],
        'candidate_version_review',
        'Only member_002 may accept or request changes to the author candidate. Editing after '
        'acceptance invalidates use of that review for the new working version.',
        ['Bacchelli and Bird modern code review']),
    _spec('SPRINT', '短周期自管理', [
        _role('开发兼交付', 'As a developer, co-select the sprint work and plan implementation '
              'with member_002. Explicitly integrate and deliver without waiting for a ceremony.'),
        _role('开发', 'Co-select sprint work and self-organize implementation. PO orders goals '
              'and SM facilitates; neither assigns your individual coding decisions.'),
        _role('Product Owner', 'Order work within the unchanged original issue, propose the '
              'sprint goal, and negotiate scope changes with both developers.'),
        _role('Scrum Master', 'Facilitate planning and actual-evidence review. Do not allocate '
              'implementation tasks for the developers or automatically declare success.')],
        'timeboxed_goal_and_developer_plan',
        'The two developers accept a public goal and select a plan; PO orders the backlog, SM '
        'facilitates review. The fixed opportunity clock can request review but never opens '
        'another sprint or changes the original issue automatically.', ['Scrum Guide 2020 adaptation']),
    _spec('MATRIX', '项目与技术双权责', [
        _role('项目协调兼集成', 'Confirm task scope and priorities and integrate only candidates '
              'with matching project and technical confirmations. Do not override technical refusal.'),
        _role('技术负责人', 'Confirm technical requirements and review exact fixed candidates. '
              'Resolve disagreement explicitly with the project coordinator.'),
        _role('实现者甲', 'Own accepted implementation work and publish its task-bound candidate '
              'for independent project-scope and technical confirmation.'),
        _role('实现者乙', 'Own accepted implementation work and publish its task-bound candidate '
              'for independent project-scope and technical confirmation.')],
        'separate_scope_and_technical_confirmation',
        'Tasks keep one actual owner. Scope and technical confirmations are distinct records; '
        'neither authority may forge, replace or bypass the other confirmation.',
        ['Galbraith matrix organization; one-issue dual-authority adaptation']),
]


def get_organization(organization_id):
    if organization_id not in ORGANIZATION_IDS:
        raise ValueError('Unknown v104 organization: ' + str(organization_id))
    return copy.deepcopy(next(row for row in _CATALOG if row['id'] == organization_id))


def catalog():
    return [get_organization(key) for key in ORGANIZATION_IDS]


def validate_organization(spec):
    if not isinstance(spec, dict) or spec != get_organization(spec.get('id')):
        raise ValueError('The fixed v104 roster, decision contract or control schedule changed')
    return copy.deepcopy(spec)


def catalog_sha256():
    value = {'version': VERSION, 'common': COMMON, 'organizations': catalog()}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def role_instruction(organization_id, member_id):
    spec = get_organization(organization_id)
    if member_id not in spec['fixed_members']:
        raise ValueError('Only a configured member may receive its private session instructions')
    return COMMON_INSTRUCTION + '\n' + spec['organization_instruction'] + '\n' + spec['roles'][member_id]['instruction']


def require_evaluation_disabled():
    raise PermissionError('v104 implements organization contracts only. Real model, API, GPU, '
                          'container and official evaluation execution remain disabled.')
