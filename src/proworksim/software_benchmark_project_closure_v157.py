"""Unique member_001 code/delivery endpoints with frozen organization proof."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import FunctionType

from . import software_benchmark_project_closure_v130 as original
from . import software_role_baseline_world_v141 as organization_world
from .software_benchmark_alignment_contract_v157 import GROUP_IDS, condition, organization, validate_plan_identity
from .software_benchmark_candidates_v054 import checked, write_new, read_episode_candidates
from .repository_sources_v054 import tree_manifest
from .storage import digest, json_bytes

VERSION = 'v157-communication-member001-dual-endpoint-closure-r1'


def validate_slot_identity(slot_id, instance_id):
    parts=slot_id.split(':') if isinstance(slot_id,str) else []
    if len(parts)!=4 or parts[0]!='v157' or parts[1]!=instance_id or not parts[3].isdigit():
        raise ValueError('Exact communication pilot identity is required')
    group=parts[2].removeprefix('REVIEW2_')
    expected=condition(group)
    row={'slot_id':slot_id,'instance_id':instance_id,'condition_id':expected['condition_id'],
        'seed':int(parts[3]),'organization_id':'REVIEW2','group_id':group,
        'arm':'PROJECT','execution_arm':'PROJECT','fixed_members':expected['fixed_members'],'member_count':2}
    validate_plan_identity(row)
    return row


_base_validate = FunctionType(original.validate_delivery_evidence.__code__,
    {**original.validate_delivery_evidence.__globals__, 'VERSION': VERSION,
     'validate_slot_identity': validate_slot_identity}, original.validate_delivery_evidence.__name__,
    original.validate_delivery_evidence.__defaults__, original.validate_delivery_evidence.__closure__)


def validate_delivery_evidence(evidence, snapshot, baseline_bundle):
    identity = validate_slot_identity(evidence.get('slot_id'), evidence.get('instance_id'))
    group, spec = identity['organization_id'], organization(identity['organization_id'])
    if (evidence.get('organization_id') != group or evidence.get('group_id') != identity['group_id']
            or snapshot.get('organization_id') != group or snapshot.get('group_id') != identity['group_id']
            or evidence.get('fixed_members') != spec['fixed_members']
            or evidence.get('fixed_organization') != spec
            or evidence.get('designated_delivery_member') != 'member_001'):
        raise ValueError('The delivery belongs to another roster or role contract')
    verdict = _base_validate(evidence, snapshot, baseline_bundle)
    proofs = evidence.get('organization_delivery_inventory')
    if not isinstance(proofs, dict) or set(proofs) != {row['delivery_id'] for row in evidence['delivery_inventory']}:
        raise ValueError('Every submission requires its original role proof')
    if not verdict['submitted']:
        return {**verdict, 'organization_id': group, 'organization_submission_verified': False}
    delivery = evidence['binding']['delivery']
    proof = proofs[delivery['delivery_id']]
    if (proof.get('version') != organization_world.VERSION or proof.get('delivery_id') != delivery['delivery_id']
            or proof.get('delivery_member') != 'member_001' or proof.get('organization_id') != group
            or proof.get('source_reference') != snapshot['source_reference']
            or proof.get('explicit_delivery') is not True or proof.get('automatic_work') is not False):
        raise ValueError('The chosen submission lost its actual role proof')
    context = evidence['organization_evidence_context']
    events = context['events']
    submits = [row for row in events if row['kind'] == 'submit' and row.get('delivery_id') == delivery['delivery_id']]
    if len(submits) != 1 or any(submits[0].get(k) != v for k,v in delivery.items()):
        raise ValueError('Legal submission must bind its unique source event')
    review = proof.get('independent_review')
    if group != 'REVIEW2':
        if review is not None:
            raise ValueError('Single/free execution cannot acquire an implicit review gate')
    else:
        patch = context['patches'].get(review.get('patch_id')) if isinstance(review, dict) else None
        if (not isinstance(patch, dict) or patch['author'] != 'member_001'
                or review.get('actor_id') != 'member_002' or review.get('author') != 'member_001'
                or review.get('decision') != 'accept'
                or review.get('identity') != {key: patch[key] for key in
                    ('source_reference','files_sha256','entry_metadata_sha256')}
                or patch['source_reference'] != snapshot['source_reference']):
            raise ValueError('REVIEW2 requires the exact independent accepted candidate')
        applicable = [row for row in events if row['kind'] == organization_world.EVENT_PREFIX+'candidate_reviewed'
            and row['actor_id'] == 'member_002' and row['identity']['source_reference'] == snapshot['source_reference']
            and row['sequence'] < submits[0]['sequence']]
        if (not applicable or applicable[-1]['sequence'] != review['event_sequence']
                or any(applicable[-1].get(key) != value for key,value in review.items()
                       if key not in {'event_sequence','logical_time'})
                or applicable[-1]['logical_time'] != review['logical_time']):
            raise ValueError('Review must be the latest actual decision before this submission')
        revisions, pending, seen = {}, [patch['patch_id']], set()
        while pending:
            pid = pending.pop()
            if pid in seen:
                continue
            seen.add(pid)
            fixed = context['patches'][pid]
            for tid, task in fixed['task_snapshots'].items():
                revisions[tid] = max(revisions.get(tid,0), task['revision'])
            pending += fixed.get('included_patch_ids',[])
        if review.get('task_revisions') != revisions:
            raise ValueError('Accepted review changed its fixed candidate task revisions')
        test = review.get('test_evidence')
        retained = context['review_tests'].get(str(test.get('sequence'))) if isinstance(test,dict) else None
        if (test != retained or test.get('actor_id') != 'member_002' or test.get('executed') is not True
                or test.get('source_reference') != review.get('adopted_source_reference')
                or test['sequence'] >= review['event_sequence']
                or any(test.get(key) != patch[key] for key in ('files_sha256','entry_metadata_sha256'))):
            raise ValueError('Independent acceptance lost its actual same-version adoption/test chain')
    return {**verdict, 'organization_id': group, 'organization_submission_verified': True,
            'organization_proof_sha256': digest(json_bytes(proof))}


def export_managed_closure(prepared, folder, *, slot_id, sdk_closed):
    if sdk_closed is not True:
        raise ValueError('Every fixed member SDK must close before selecting the unique candidates')
    identity = validate_slot_identity(slot_id, prepared.case['case_id'])
    if prepared.case['fixed_organization'] != organization(identity['organization_id']):
        raise ValueError('The final world is not this team identity')
    from .software_role_baseline_runtime_v157 import lock_fixed_candidates
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    lock_ref = lock_fixed_candidates(prepared, folder/'project-candidates', sdk_closed=True)
    pair = read_episode_candidates(lock_ref)
    terminal, delivery_bundle, lock = pair['terminal_code'], pair['last_legal_delivery'], pair['lock']
    with prepared.world.store.lock():
        state = prepared.world.store.load()
        prepared.world.state = state
        facts = prepared.world._software()
        inventory = copy.deepcopy(facts['deliveries'])
        organization_proofs = copy.deepcopy(facts.get('organization_delivery_proofs_v141', {}))
        _, _, baseline = prepared.world._bundle('member_001', baseline=True)
        review_sequences = {proof['independent_review']['test_evidence']['sequence']
            for proof in organization_proofs.values() if proof.get('independent_review')}
        context = {'patches': copy.deepcopy(facts['patches']),
            'events': [copy.deepcopy(row) for row in state['software_events']
                if row['kind'] in {'submit', organization_world.EVENT_PREFIX+'candidate_reviewed'}],
            'review_tests': {str(row['sequence']): organization_world.SoftwareCollaborationWorld._test_summary(row)
                for row in state['software_events'] if row['kind'] == 'test' and row['sequence'] in review_sequences}}
    terminal_lock = json.loads(checked(lock['terminal_code']).read_bytes())
    terminal_binding = json.loads(checked(terminal_lock['binding']).read_bytes())
    binding = delivery_reference = delivery_tree = None
    if delivery_bundle is not None:
        delivery_lock = json.loads(checked(lock['last_legal_delivery']).read_bytes())
        binding = json.loads(checked(delivery_lock['binding']).read_bytes())
        tests = [row for row in state['software_events']
                 if row.get('kind') == 'test' and row.get('sequence') == binding['public_test_sequence']]
        if len(tests) != 1:
            raise ValueError('Last team submission lost its exact member001 public-test event')
        binding['public_test_event'] = copy.deepcopy(tests[0])
        delivery_reference, delivery_tree = delivery_lock['source_reference'], delivery_lock['tree_sha256']
    common = {'version': VERSION, 'slot_id': slot_id, 'instance_id': prepared.case['case_id'],
        'organization_id': identity['organization_id'], 'group_id': identity['group_id']}
    snapshot = {**common, 'submitted': delivery_bundle is not None, 'candidate': delivery_bundle,
                'source_reference': delivery_reference, 'tree_sha256': delivery_tree}
    evidence = {**common, 'submitted': delivery_bundle is not None, 'binding': binding,
        'delivery_inventory': inventory, 'organization_delivery_inventory': organization_proofs,
        'organization_evidence_context': context,
        'fixed_members': list(prepared.case['active_roles']),
        'fixed_organization': copy.deepcopy(prepared.case['fixed_organization']),
        'designated_delivery_member': 'member_001', 'best_of_members': False,
        'file_policy': copy.deepcopy(prepared.case['file_policy']),
        'baseline_reference': terminal_binding['baseline_reference'],
        'baseline_tree_sha256': tree_manifest(baseline['files'], baseline['entry_metadata'])['tree_sha256'],
        'terminal_source_reference': terminal_lock['source_reference'],
        'terminal_tree_sha256': terminal_lock['tree_sha256'], 'same_tree': lock['same_tree'],
        'locked_before_grading': True, 'model_calls_after_lock': 0, 'controller_candidate_lock': lock_ref}
    verdict = validate_delivery_evidence(evidence, snapshot, baseline)
    observer = getattr(prepared.world, 'collaboration_observer_v141', None)
    observation = None
    if observer is not None:
        path = observer.folder/'summary.json'
        if path.is_file():
            from .software_benchmark_candidates_v054 import reference
            observation = reference(path)
    return {'terminal_bundle': terminal, 'collaboration_observation': observation,
        'terminal_snapshot': write_new(folder/'project-terminal-snapshot.json', terminal),
        'baseline_snapshot': write_new(folder/'project-baseline-snapshot.json', baseline),
        'delivery_snapshot': write_new(folder/'project-delivery-snapshot.json', snapshot),
        'delivery_evidence': write_new(folder/'delivery-evidence.json', evidence),
        'terminal_tree_sha256': terminal_lock['tree_sha256'],
        'terminal_source_reference': terminal_lock['source_reference'], 'same_tree': lock['same_tree'],
        'submitted': delivery_bundle is not None, 'controller_candidate_lock': lock_ref,
        'organization_id': identity['organization_id'], 'group_id': identity['group_id'],
        'fixed_members': list(prepared.case['active_roles']), 'delivery_validation': verdict}
