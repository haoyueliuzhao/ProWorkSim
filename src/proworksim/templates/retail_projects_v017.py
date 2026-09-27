"""Formal static and one-change four-project cases, independent from H1/H2."""
import copy
from pathlib import Path

from ..scenarios import build_scenario, initial_business_state, save_deployment
from ..storage import atomic_write, digest, json_bytes
from .online_work import PreparedOnlineCase
from .retail_projects import ACTORS, GOALS, SOURCES, package as old_package, request, scenario_spec as old_scenario

VERSION = 'retail-projects-v0.17'
REWARD_VERSION = 'retail-project-utility-v0.17'


def case_spec(case_id):
    if case_id not in {'retail-projects-v17-static', 'retail-projects-v17-change'}:
        raise ValueError('Unknown fixed four-project case')
    changed = case_id.endswith('-change')
    return {'version': VERSION, 'case_id': case_id, 'changed': changed, 'pool': 'project_development',
            'family': 'uci-online-retail-352', 'target_policy_edition': 2 if changed else 1,
            'role_decision_limits': {'P0': 14, 'P1': 44 if changed else 24,
                                     'P2': 44 if changed else 24, 'P3': 44 if changed else 24},
            'active_roles': list(ACTORS)}


def package(project):
    pkg = old_package(project)
    work = pkg['works'][0]
    if project == 'P2':
        client = next(o for o in pkg['objects'] if o['alias'] == 'request')
        client.update(owner='operator', writers=['operator'])
        pkg['grants'] += [{'actor_id': 'operator', 'power': p, 'subject': 'artifact', 'object_ids': ['request']} for p in ('share', 'publish')]
    if project != 'P0':
        work['deliverable_contract']['content_checks'] = [{
            'kind': 'retail_project_product', 'project_kind': project, 'role': 'sql_result',
            'path': ['tables'], 'period': 'UCI-harness-f0',
            'policy_sha256s': [digest(json_bytes(request(i))) for i in (1, 2)],
            'sources': [{'alias': a, 'reference_path': ['sources', a]} for a in SOURCES[project]]}]
    recipients = {'P0': ['P1', 'P2'], 'P1': ['P3'], 'P2': ['P3'], 'P3': []}[project]
    work['requirements']['public_delivery'] = {
        'publish': bool(recipients), 'recipients': [{'project_id': p, 'actor_ids': [ACTORS[p]]} for p in recipients]}
    work['goal'] = GOALS[project] + ' Make a fixed submission before publishing each output for downstream consumption. Never infer business correctness from delivery acceptance or zero differences alone.'
    if project == 'P2':
        work['goal'] = work['goal'].replace('Publish the initial usable customer-grain reporting contract.', 'Use the already published client-owned reporting contract; only the declared client event may change it.')
    # A single declared change can follow already accepted first deliveries.
    for rule in list(pkg['maintenance_rules']):
        pkg['maintenance_rules'].append({**copy.deepcopy(rule), 'rule_id': rule['rule_id'] + '-accepted',
                                         'when': ['accepted'], 'effect': 'successor'})
    return pkg


def scenario(case):
    case = case_spec(case) if isinstance(case, str) else copy.deepcopy(case)
    if case != case_spec(case['case_id']):
        raise ValueError('Four-project case differs from fixed declaration')
    spec = old_scenario()
    spec['scenario_id'] = case['case_id']
    spec['world']['world_id'] = VERSION
    spec['projects'] = [{'package': package(p)} for p in ('P0', 'P2', 'P1', 'P3')]
    spec['roles'] = [{'role_id': p, 'actor': ACTORS[p], 'project': p, 'policy': 'model',
                      'config': {'task': package(p)['works'][0]['goal']}} for p in ACTORS]
    # Delegated subscriptions are installation facts, not a selected downstream
    # result or automatic provider response. Publication remains actor work.
    for source, alias, targets in [('P0', 'data', ['P1', 'P2']), ('P0', 'release_note', ['P1', 'P2']),
                                   ('P1', 'code', ['P3']), ('P1', 'result', ['P3']), ('P2', 'code', ['P3']), ('P2', 'result', ['P3']), ('P2', 'request', ['P1', 'P3'])]:
        from ..core.world import object_identity
        for target in targets:
            spec['setup'].append({'actor': 'operator' if alias == 'request' else ACTORS[source], 'project': source, 'tool': 'share',
                                  'arguments': {'object_id': object_identity(source, alias), 'version_id': 'v1',
                                                'target_project': target, 'actor_ids': [ACTORS[target]], 'follow_updates': True}})
    spec['setup'].append({'actor': 'operator', 'project': 'P2', 'tool': 'publish',
                          'arguments': {'alias': 'request', 'version_id': 'v1', 'target_projects': ['P1', 'P2', 'P3']}})
    if case['changed']:
        spec['events'] = [{'event_id': 'declared-half-year-net-contract', 'fire_once': True,
                           'when': {'all': [{'work': {'project': p, 'node': 'build', 'phase': 'accepted'}} for p in ACTORS]},
                           'effects': [{'actor': 'operator', 'project': 'P2', 'tool': 'write_object',
                                        'arguments': {'alias': 'request', 'data': request(2)}},
                                       {'actor': 'operator', 'project': 'P2', 'tool': 'publish',
                                        'arguments': {'alias': 'request', 'version_id': 'v2', 'target_projects': ['P1', 'P2', 'P3']}}]}]
    spec['boundary'] = {'max_opportunities': sum(case['role_decision_limits'].values()) + 4}
    spec['variation'] = {'kind': 'structure', 'project_case': case,
                         'project_reward': {'version': REWARD_VERSION, 'target_policy_edition': case['target_policy_edition'],
                                            'R': 'one iff all fixed branches, actual integration fidelity and global contract/source/version coherence hold',
                                            'partial_dimensions_reported_separately': True},
                         'usage': 'Four-project development evaluation; neither H1 samples nor H2 short-responsibility training.'}
    return spec


def build_project_case(case, root):
    case = case_spec(case) if isinstance(case, str) else copy.deepcopy(case)
    spec = scenario(case)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(spec, root / 'world')
    if deployment.status != 'ready':
        raise ValueError(deployment.diagnostics)
    prefix = {'version': VERSION, 'preparation_credit': False,
              'prepared_business_state_sha256': digest(json_bytes(initial_business_state(deployment.world))),
              'scope': 'Initial subscriptions and usable reporting contract only; no edit/build/submit of downstream work.'}
    atomic_write(root / 'preparation.json', json_bytes(prefix))
    save_deployment(deployment)
    return PreparedOnlineCase(deployment, case, spec['variation']['project_reward'], prefix)
