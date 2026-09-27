"""Formal utility on an immutable four-project episode end boundary only."""
from pathlib import Path

from .episode import _read_boundary, assess_historical_episode
from .storage import digest, json_bytes, read_json
from .templates.retail_projects import request
from .templates.retail_projects_v017 import REWARD_VERSION, case_spec


def assess_project_episode(episode):
    root = Path(episode)
    result = {'version': REWARD_VERSION, 'eligible': False, 'reward': None, 'completed': None,
              'dimensions': {'P1_quality': None, 'P2_quality': None, 'P3_fixed_input_fidelity': None, 'overall_business_goal': None},
              'scope': 'Closed episode fixed submissions and immutable versions only; no live-world lookup or score feedback to workers.'}
    historical = assess_historical_episode(root)
    result['historical_assessment'] = historical
    if historical.get('assessment_execution', {}).get('status') != 'complete':
        result['reason'] = 'historical_evidence_or_evaluator_unavailable'
        return result
    if any(event.get('status') in {'model_service_error', 'environment_error'}
           or event.get('kind') in {'interface_error', 'interface_exception', 'model_service_error'}
           for event in historical.get('runtime_problems', {}).get('events', [])):
        result['reason'] = 'model_or_environment_evidence_incomplete'
        return result
    try:
        manifest = read_json(root / 'manifest.json')
        spec = manifest['scenario']['variation']['project_case']
        if spec != case_spec(spec['case_id']):
            raise ValueError('Episode case differs from frozen four-project declaration')
        store, state = _read_boundary(root, manifest['end'])
        start_store, start = _read_boundary(root, manifest['start'])
        selected = {state['work_items'][wid]['project_id']: state['work_items'][wid] for wid in manifest['selected_work_ids']}
        if set(selected) != {'P0', 'P1', 'P2', 'P3'}:
            raise ValueError('Episode must declare all four exact project nodes')
        evaluations = {r['project_id']: r['evaluation'] for r in historical['content_quality']['submissions']}
        if any(evaluations[p].get('status') in {'source_unavailable', 'evaluator_error'} for p in ('P1', 'P2', 'P3')):
            result['reason'] = 'required_fixed_product_evidence_unknown'
            return result
        dims = result['dimensions']
        for project, dimension in [('P1', 'P1_quality'), ('P2', 'P2_quality'), ('P3', 'P3_fixed_input_fidelity')]:
            dims[dimension] = evaluations[project].get('passed') is True
        subs = {p: item.get('submissions', [])[-1] if item.get('submissions') else None for p, item in selected.items()}
        valid = {p: bool(s and not s.get('invalidated') and s.get('current_applicability') != 'withdrawn') for p, s in subs.items()}
        refs, data = {}, {}
        for p, sub in subs.items():
            if not sub:
                continue
            alias = 'data' if p == 'P0' else 'result'
            oid = state['workspaces'][p][alias]
            vid = sub['artifact_versions'].get(oid)
            if vid:
                refs[p] = {'object_id': oid, 'version_id': vid}
                data[p] = read_json(store.version_path(state['artifacts'][oid], vid))
        coherent = False
        original_preserved = False
        if set(data) == {'P0', 'P1', 'P2', 'P3'}:
            original_oid = start['workspaces']['P0']['data']
            original = read_json(start_store.version_path(start['artifacts'][original_oid], 'v1'))
            original_preserved = data['P0'] == original
            s1, s2, s3 = [data[p]['sources'] for p in ('P1', 'P2', 'P3')]
            policy_ref = s3['basis']
            policy = read_json(store.version_path(state['artifacts'][policy_ref['object_id']], policy_ref['version_id']))
            coherent = (s1['data'] == s2['data'] == refs['P0'] and s1['basis'] == s2['basis'] == policy_ref
                        and s3['metrics'] == refs['P1'] and s3['analysis'] == refs['P2']
                        and policy == request(spec['target_policy_edition']))
        institutional = {r['project_id']: r for r in historical['institutional_progress']['works']}
        all_delivered = all(institutional[p]['status'] == 'accepted' and valid[p] for p in selected)
        published = True
        for project, item in selected.items():
            delivery = item['requirements'].get('public_delivery', {})
            if not delivery.get('publish'):
                continue
            targets = {project} | {r['project_id'] for r in delivery.get('recipients', [])}
            sub = subs[project]
            published &= bool(sub) and all(
                any(release['object_id'] == oid and release['version_id'] == vid
                    and target in release['scope']['target_projects'] for release in state['releases'])
                for oid, vid in (sub['artifact_versions'].items() if sub else []) for target in targets)
        # P3 arithmetic can be faithful while both branches share the same error.
        goal = (all(dims[k] for k in ('P1_quality', 'P2_quality', 'P3_fixed_input_fidelity'))
                and coherent and original_preserved and all_delivered and published)
        dims['overall_business_goal'] = bool(goal)
        result.update(eligible=True, reward=int(goal), completed=bool(goal),
                      exact_final_branch_versions=refs, source_preserved=original_preserved,
                      fixed_contract_and_version_coherence=coherent, all_projects_fixed_and_delivered=all_delivered,
                      declared_publication_obligations_complete=published,
                      episode_id=manifest['episode_id'], episode_manifest_sha256=digest((root / 'manifest.json').read_bytes()),
                      component_measurement='Independent branch quality and exact-input fidelity are diagnostic dimensions; scalar R is the conjunction, not a zero-difference shortcut.',
                      end_boundary_sha256=digest(json_bytes(state)))
    except (KeyError, ValueError, OSError, TypeError) as error:
        result['reason'] = 'invalid_or_unavailable_joint_evidence'
        result['diagnostic'] = str(error)
    return result
