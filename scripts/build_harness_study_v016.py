"""Create an independent, fixed-weight H1 development protocol; never launch it.

Explicit input S1 protocols bind native runtime/recipe. Optional original S1
report validation checks completed measurements without ranking business scores.
H0 review and the final source/runtime freeze remain separate execution gates.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from proworksim.storage import digest, json_bytes
from proworksim.templates.retail_harness import PIN_PATH, registry

VERSION = 'harness-study-v0.16'
CANDIDATES = {'qwen35-9b': 'qwen3.5-9b', 'qwen38-27b': 'qwen3.8-27b'}
ORDER = (('native_v15', 0), ('openhands_v16', 0), ('openhands_v16', 1), ('native_v15', 1))
INITIALIZATION_SEED = 2026093041
SLOT_SEED = 2026093100
COLLECTOR = 'proworksim.harness_collection:collect_window'


def read(path):
    return json.loads(Path(path).read_text())


def ref(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_screen(screen, *, profile_root):
    candidate = screen.get('candidate_id')
    require(candidate in CANDIDATES and screen.get('stage') == 'screen', 'Only explicitly registered new-candidate S1 protocols are accepted')
    runtime = screen.get('runtime', {})
    require(runtime.get('kind') == 'qwen_hybrid_chatstop', 'H1 requires the corrected native chat-stop runtime')
    profile = runtime.get('profile', {})
    require(profile.get('candidate_id') == CANDIDATES[candidate]
            and profile.get('version') == 'candidate-runtime-v0.15.1', 'Candidate/profile identity mismatch')
    root = Path(profile_root).resolve()
    declared = Path(runtime.get('profile_source', ''))
    require(not declared.is_absolute() and bool(str(declared)), 'Profile source must name the frozen relative file')
    source = (root / declared).resolve()
    require(source.is_relative_to(root), 'Profile source escapes its declared source root')
    identity = ref(source)
    require(identity['sha256'] == runtime.get('profile_sha256') and read(source) == profile,
            'Source profile bytes or embedded profile differ from frozen S1 binding')
    require(screen.get('mode') == 'evaluate' and screen.get('windows')
            and all(w.get('mode') == 'evaluate' for w in screen['windows']), 'Original screening protocol must be pure evaluation')
    require(sum(len(w.get('slots', [])) for w in screen['windows']) == 36,
            'Expected the unchanged 36-slot original S1 protocol')
    return identity


def build_protocol(screen):
    """Pure construction after validate_screen; excludes old descriptive fields."""
    candidate = screen['candidate_id']
    cases = registry()['situations']
    require(len(cases) == 6, 'The six declared development situations must remain fixed')
    recipe = copy.deepcopy(screen['recipe'])
    recipe['seed'] = INITIALIZATION_SEED
    protocol = {'version': VERSION, 'experiment_id': 'h1-' + candidate,
                'stage': 'H1_development', 'candidate_id': candidate,
                'condition': 'paired_native_and_openhands', 'mode': 'evaluate',
                'launch_gate': {'version': 'h1-launch-admission-v0.16', 'state': 'planning_only'},
                'collector': COLLECTOR, 'runtime': copy.deepcopy(screen['runtime']), 'recipe': recipe,
                'initialization': {'kind': 'fresh_public_base', 'seed': INITIALIZATION_SEED,
                                   'same_resident_actor_for_all_four_windows': True,
                                   'restore_checkpoint_permitted': False,
                                   'N0_N1_weights_or_trajectories_used': False},
                'expected_optimizer_steps': {'actor': 0, 'critic': 0},
                'budget_scope': '6 new UCI development situations x 2 repeats x 2 harnesses = 24 episodes for this model; no success resampling or outcome-dependent extension.',
                'harness_identity': {
                    'native_v15': {'context_selection': 'latest_observation'},
                    'openhands_v16': {'adapter_version': 'openhands-managed-worker-v0.16.1', 'sdk_version': '1.49.6', 'upstream_commit': 'fcc102a697874d54a357e36004e02c95040dbdc0',
                                      'context_selection': 'latest_observation_last4_tool_rounds'},
                    'effect_scope': 'Combined interface, private memory, local history and editing support; no attribution to one feature. Exact source/runtime identity must be frozen after H0 review.'},
                'reward_scope': 'Unchanged retail-work-reward-v0.15 with actual world evidence and Decimal evaluation; no hidden answer or software task feedback.',
                'learning_scope': 'No parameter update; H1 combination effects cannot be called learning or ID-VTDO gains.',
                'windows': []}
    for index, (harness, repeat) in enumerate(ORDER):
        label = f'h1-{candidate}-{index}-{harness}-r{repeat}'
        slots = []
        for case_index, case in enumerate(cases):
            slots.append({'slot_id': f'{label}-c{case_index}', 'case_id': case['case_id'],
                          'task': case['task'], 'fact_position': case['fact_position'],
                          'pool': 'harness_development', 'family': 'uci-online-retail-352',
                          'repeat': repeat, 'sampling_seed': SLOT_SEED + case_index * 10 + repeat,
                          'role_decision_limits': copy.deepcopy(case['role_decision_limits']),
                          'purpose': 'paired_harness_development_work'})
        protocol['windows'].append({'window_id': label, 'mode': 'evaluate', 'stage': 'H1_development',
                                    'phase': 'harness_development', 'node': f'repeat-{repeat}',
                                    'template': 'retail_harness', 'harness': harness,
                                    'interface': 'v14', 'presentation': 'compact_v14',
                                    'external_tick_per_sweep': 1, 'min_class_count': 2, 'slots': slots})
    return protocol


def validate_original_s1(screen, screen_path, study_report):
    """Read-only, bounded validation of original saved completion/profile evidence.

    This is not a new candidate ranking or a minimum business-score threshold.
    It deliberately does not certify H0, trainability or current GPU capacity.
    """
    from scripts.select_candidate_v015 import validate_guard

    matches = [r for r in study_report.get('runs', []) if r.get('candidate_id') == screen['candidate_id']]
    require(len(matches) == 1, 'Original S1 report must contain one matching candidate')
    run = matches[0]
    source_ref = ref(screen_path)
    root = Path(run['root'])
    require(run.get('runner_status') == 'complete' and run.get('saved_protocol_equals_declared') is True,
            'Original S1 condition has not completed; do not infer a failure or zero score')
    require(run.get('protocol_ref', {}).get('sha256') == source_ref['sha256'],
            'Original S1 report does not bind these source protocol bytes')
    saved = read(root / 'online/protocol.json')
    launch = read(root / 'launch-protocol.json')
    runner = read(root / 'online/report.json')
    owner = read(root / 'resident/owner.json')
    require(saved == launch == screen and runner.get('status') == 'complete',
            'Original S1 saved/launch protocol or completed runner differs')
    require(runner.get('protocol_sha256') == digest(json_bytes(screen)), 'Original S1 runner protocol fingerprint differs')
    require(owner == run.get('owner') and owner.get('recipe') == screen['recipe']
            and all(owner.get('inference_profile', {}).get(k) == v for k, v in screen['runtime']['profile'].items()),
            'Original owner/profile/recipe differs from registered source protocol')
    counts = run.get('progress', {}).get('counts', {})
    require(counts.get('planned') == counts.get('distinct_planned_or_measured') == counts.get('closed_known') == 36
            and all(counts.get(k) == 0 for k in ('closed_unknown', 'open', 'interrupted_open', 'not_started')),
            'All 36 original S1 measurements must be closed and known; missing is not zero')
    require(not run.get('unknown_step_windows') and not run.get('issues')
            and run.get('observed_optimizer_step_increments') == {'actor': 0, 'critic': 0},
            'Original S1 has unknown steps, integration issues or actual updates')
    require(len(run.get('windows', [])) == len(screen['windows']), 'Original S1 window count differs')
    for window, spec in zip(run['windows'], screen['windows']):
        require(window['window_id'] == spec['window_id'], 'Original S1 window binding differs')
        validate_guard(window)
    # Preserve measured weaknesses rather than use any score as an entry gate.
    return {'status': 'original_completed_S1_profile_bound',
            'protocol_ref': source_ref, 'run_root': str(root.resolve()),
            'original_progress': copy.deepcopy(run['progress']),
            'original_task_fact_summaries': copy.deepcopy(run.get('task_fact_summaries', [])),
            'original_sampling': copy.deepcopy(run.get('sampling', {})),
            'original_runtime_sources': {k: copy.deepcopy(run.get(k)) for k in ('source_before', 'source_after', 'source_comparison')},
            'original_runner_ref': ref(root / 'online/report.json'),
            'inference_entry_evidence': 'A completed corrected-native S1 run with actual owner/profile binding; no added score threshold.',
            'trainability_recertified': False,
            'capability_certified': False}


def build_study(protocol_paths, output, *, profile_root, s1_report_path=None, require_s1_complete=False, admission_path=None):
    require(1 <= len(protocol_paths) <= 2, 'Declare one or two new candidate source protocols explicitly')
    output = Path(output)
    require(not output.exists(), 'Output must be a new directory; original or previous protocols cannot be overwritten')
    report = read(s1_report_path) if s1_report_path else None
    require(not require_s1_complete or report is not None, '--require-s1-complete needs the explicit original --s1-report')
    require(admission_path is None or len(protocol_paths) == 2, 'Formal H1 supports both candidates only; single-model execution requires a separate revision')
    rows, protocols = [], {}
    for path in protocol_paths:
        screen = read(path)
        profile_ref = validate_screen(screen, profile_root=profile_root)
        candidate = screen['candidate_id']
        require(candidate not in protocols, 'Candidate protocols must be distinct')
        protocol = build_protocol(screen)
        eligibility = validate_original_s1(screen, path, report) if report is not None else {
            'status': 'not_checked_planning_only', 'capability_certified': False,
            'original_measurements': None, 'missing_results_are_not_zero': True}
        if admission_path is not None:
            from proworksim.harness_admission import body_hash
            admission = read(admission_path)
            require(admission.get('version') == 'h1-launch-admission-v0.16' and admission.get('status') == 'admitted'
                    and set(admission.get('protocol_body_sha256', {})) == set(CANDIDATES)
                    and admission['protocol_body_sha256'][candidate] == body_hash(protocol),
                    'Formal admission does not bind both fixed H1 protocols')
            protocol['launch_gate'] = {'version': 'h1-launch-admission-v0.16', 'state': 'admitted', 'admission': ref(admission_path)}
        protocols[candidate] = protocol
        rows.append({'candidate_id': candidate, 'protocol': f'h1-{candidate}.json',
                     'source_screen_protocol': ref(path), 'source_profile': profile_ref,
                     'original_S1': eligibility, 'episodes': 24,
                     'entry_basis': 'Caller declares an available corrected-native inference entry; generator applies no business-score ranking.',
                     'known_limitations': 'Read original task/fact/repeat measurements above or their source report; selected/usable is not sufficient-work-capability certification.'})
    manifest = {'version': VERSION, 'stage': 'H1_development', 'status': 'generated_not_started',
                'model_count': len(rows), 'episodes': 24 * len(rows), 'train_episodes': 0,
                'scope': 'two_model_harness_development_comparison' if len(rows) == 2 else 'single_model_harness_diagnostic',
                'candidate_availability_rule': 'After original S1 closure, use both registered new candidates when both have usable corrected-native inference entries. With only one available candidate, declare 24 episodes and no two-model comparison. Runtime execution eligibility is decided separately; this generator does not launch or observe jobs.',
                'selected_is_capability_certification': False,
                'H0_review_and_final_source_freeze_required': True,
                'launch_gate': 'runner_revalidates_formal_global_admission' if admission_path else 'planning_only_not_executable',
                'formal_admission': ref(admission_path) if admission_path else None,
                'original_s1_report': ref(s1_report_path) if s1_report_path else None,
                'source_asset_manifest': ref(PIN_PATH),
                'sampling': {'initialization_seed': INITIALIZATION_SEED,
                             'slot_seed_formula': '2026093100 + case_index * 10 + repeat',
                             'paired_across_harnesses_and_models': True},
                'window_order': [{'harness': h, 'repeat': r} for h, r in ORDER],
                'fixed_case_count': 6, 'repeats_per_case_per_harness': 2,
                'max_role_decisions_per_model': 4 * sum(sum(c['role_decision_limits'].values()) for c in registry()['situations']),
                'primary_measures': ['complete_responsibility', 'actual_basis_use', 'correct_modification', 'evidenced_review', 'specific_error_recovery', 'total_cost'],
                'unchanged_dimensions': ['business_contract', 'role_permissions', 'tool_effects', 'prepared_start', 'role_decision_limits', 'native_model_profile', 'LoRA_scope', 'precision', 'reward'],
                'interpretation': 'Bundled harness effect at a fresh shared initial actor; no parameter learning, ID-VTDO gain or independent-source generalization claim.',
                'Marshmallow_used': False, 'N0_N1_resumed_or_modified': False,
                'candidates': rows}
    output.mkdir(parents=True, exist_ok=False)
    for candidate, protocol in protocols.items():
        (output / f'h1-{candidate}.json').write_text(json.dumps(protocol, ensure_ascii=False, indent=2) + '\n')
    (output / 'study.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screen-protocol', type=Path, required=True, action='append', help='Explicit source S1 protocol; repeat for the second available candidate')
    parser.add_argument('--profile-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--s1-report', type=Path, help='Existing learning_report_v015 report.json; if supplied, validate original selected S1 runs and retain all original task/fact results')
    parser.add_argument('--require-s1-complete', action='store_true')
    parser.add_argument('--admission', type=Path, help='Explicit formal global H1 admission; the runner revalidates it before loading dependencies/models')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = build_study(args.screen_protocol, args.output, profile_root=args.profile_root,
                           s1_report_path=args.s1_report, require_s1_complete=args.require_s1_complete, admission_path=args.admission)
    print(json.dumps({k: manifest[k] for k in ('status', 'model_count', 'episodes', 'train_episodes', 'scope')}))


if __name__ == '__main__':
    main()
