"""Four fixed project evaluations using exactly the completed H1 selection.

No model is loaded before saved selection/profile/base bindings pass. No retry,
checkpoint restore, parameter update or automatic work completion is supported.
"""
import argparse
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from proworksim.audit import code_identity
from proworksim.storage import atomic_write, json_bytes, read_json
from scripts.harness_report_v017 import CANDIDATES, HARNESSES, VERSION as H1_REPORT_VERSION, select_combination

VERSION = 'retail-project-resident-evaluation-v0.18'
PLAN = Path(__file__).resolve().parents[1] / 'examples/retail-projects-v17/model-evaluation-plan.json'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def reference(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def checked(reference_, *, label):
    require(isinstance(reference_, dict) and reference_.get('path') and reference_.get('sha256'), label + ' reference absent')
    path = Path(reference_['path']).resolve()
    require(reference(path)['sha256'] == reference_['sha256'], label + ' bytes changed')
    return path


def validate_binding(selection_path, *, model, weight_manifest, harness, candidate=None,
                     protocol_path=None, runtime_profile=None, placement_reason=None):
    """Metadata only: never instantiate Torch, a model, a world or an evaluator."""
    selection_path = Path(selection_path).resolve()
    document = read_json(selection_path)
    wrapper = None
    if 'models' not in document:
        wrapper = copy.deepcopy(document)
        report_path = checked(document.get('report_ref'), label='Selection source report')
        document = read_json(report_path)
        require({k: v for k, v in wrapper.items() if k != 'report_ref'} == document.get('selection'),
                'Selection wrapper differs from its source report')
    else:
        report_path = selection_path
    require(document.get('version') == H1_REPORT_VERSION, 'Final report must use the explicitly installed H1 reporter version')
    models = document.get('models', [])
    require(len(models) == 2 and {m.get('candidate_id') for m in models} == set(CANDIDATES)
            and all(m.get('ended') is True for m in models), 'Both actual H1 model processes must end before project evaluation')
    actual_selection = select_combination(models)
    require(document.get('selection') == actual_selection and actual_selection.get('status') == 'selected',
            'H1 has no matching final selected combination')
    selected = actual_selection['selected']
    require(selected.get('eligible') is True and harness in HARNESSES and harness == selected['harness'],
            'Requested harness is not the final H1 selected harness')
    require(candidate is None or candidate == selected['candidate_id'], 'Requested candidate is not selected')
    # Ended is checked against original launch files, not a caller-edited name.
    for entry in models:
        refs = entry.get('references', {})
        launch = read_json(checked(refs.get('launch'), label='H1 actual launch'))
        require(type(launch.get('exit_code')) is int and type(launch.get('end')) in (int, float),
                'Original H1 launch has not ended')
        original_files = {label: checked(refs.get(label), label='H1 ' + label) for label in ('protocol', 'runner', 'owner')}
        command = launch.get('command', [])
        require('--output' in command and Path(command[command.index('--output') + 1]).resolve() == original_files['protocol'].parent,
                'Original H1 launch command does not bind its reported run')
    measured = next(m for m in models if m['candidate_id'] == selected['candidate_id'])
    original_protocol_path = checked(measured['references']['protocol'], label='Selected H1 protocol')
    original = read_json(original_protocol_path)
    require(protocol_path is None or read_json(Path(protocol_path)) == original, 'Explicit protocol differs from the selected H1 launch')
    require(original.get('candidate_id') == selected['candidate_id'] and original.get('version') == 'harness-study-v0.17'
            and original.get('runtime', {}).get('kind') == 'qwen_hybrid_diagnostics', 'Selected protocol/runtime identity differs')
    owner = read_json(checked(measured['references']['owner'], label='Selected H1 owner'))
    require(owner.get('recipe') == original.get('recipe') and measured.get('fresh_shared_owner') is True,
            'Selected actual H1 owner is not bound to the declared fresh recipe')
    require(measured.get('actor_steps_total') == measured.get('critic_steps_total') == 0
            and measured.get('actual_initial_actor_identity') == measured.get('actual_final_actor_identity') == owner.get('initial_actor_identity'),
            'Selected H1 actor is not unchanged across its evaluation')
    runner = read_json(checked(measured['references']['runner'], label='Selected actual H1 runner'))
    require(runner.get('actor_steps_total') == runner.get('critic_steps_total') == 0
            and runner.get('final_actor_identity') == owner['initial_actor_identity'],
            'Actual selected runner counters/identity differ from the report')
    profile = original['runtime']['profile']
    require(all(owner.get('inference_profile', {}).get(k) == v for k, v in profile.items()), 'Actual H1 inference profile differs')
    base = owner.get('base_identity', {})
    manifest_ref = reference(weight_manifest)
    require(base.get('manifest') == manifest_ref and Path(base.get('path', '')).resolve() == Path(model).resolve()
            and Path(model).is_dir(), 'Model path or exact weight manifest is not the selected H1 base')
    require(owner['initial_actor_identity'].get('base_manifest_sha256') == manifest_ref['sha256'], 'Selected actor/base manifest fingerprint differs')
    require(measured.get('source_before') == measured.get('source_after')
            and measured.get('source_before', {}).get('code_dirty') is False, 'H1 selected source is not unchanged and clean')
    effective = copy.deepcopy(profile)
    placement = None
    if runtime_profile is not None:
        require(isinstance(placement_reason, str) and placement_reason.strip(), 'Placement override needs an explicit reason')
        effective = read_json(Path(runtime_profile))
        require({k: v for k, v in effective.items() if k != 'devices'} == {k: v for k, v in profile.items() if k != 'devices'}
                and type(effective.get('devices')) is int and effective['devices'] > 0,
                'Only explicitly declared device-count placement may change; other profile fields remain fixed')
        placement = {'reason': placement_reason, 'profile': reference(runtime_profile),
                     'original_devices': profile['devices'], 'effective_devices': effective['devices'],
                     'scope': 'Explicit new evaluation placement; actual fresh adapter identity comparison is reported, never assumed identical.'}
    else:
        require(placement_reason is None, 'Placement reason without an explicit profile is ambiguous')
    return {'version': VERSION, 'passed': True, 'selected_candidate': selected['candidate_id'], 'selected_harness': harness,
            'selection_input': reference(selection_path), 'source_report': reference(report_path), 'selected': selected,
            'original_protocol': reference(original_protocol_path), 'original_protocol_body': original,
            'H1_initial_actor_identity': owner['initial_actor_identity'], 'H1_source_identity': measured['source_before'],
            'model_path': str(Path(model).resolve()), 'weight_manifest': manifest_ref,
            'recipe': copy.deepcopy(original['recipe']), 'profile': effective, 'placement_revision': placement,
            'model_loads_during_validation': 0, 'selection_is_capability_certification': False}


def execute(owner, binding, output, plan):
    """A single fresh selected owner, four predeclared independent worlds."""
    from proworksim.retail_project_collection import collect_project_episode

    report = {'version': VERSION, 'status': 'running', 'episodes': [], 'planned_episodes': len(plan['slots']),
              'model_identity': owner.freeze_identity(), 'selected_candidate': binding['selected_candidate'],
              'harness': binding['selected_harness'], 'training_happened': False}
    atomic_write(output / 'report.json', json_bytes(report))
    try:
        for slot in plan['slots']:
            snapshot = owner.capture_evaluation_state()
            folder = output / slot['slot_id']
            owner.begin_window(slot['slot_id'])
            owner.reseed(slot['sampling_seed'], label=slot['slot_id'])
            row = {**slot, 'status': 'collecting', 'assessment': {'eligible': False, 'reward': None, 'completed': None},
                   'before_actor_identity': owner.freeze_identity()}
            report['episodes'].append(row)
            atomic_write(output / 'report.json', json_bytes(report))
            failure = None
            try:
                result = collect_project_episode(owner, slot['case_id'], folder, harness=binding['selected_harness'])
                row.update(status='closed', assessment=result['assessment'], termination=result['termination'],
                           opportunities=result['opportunities'], actions=result['actions'],
                           independent_assessment=result.get('independent_assessment'),
                           independent_assessability=result.get('independent_assessability'),
                           record_trust=result.get('record_trust'), diagnostics=result.get('diagnostics'))
                row['evaluation_close'] = owner.finish_evaluation([], folder / 'evaluation-close')
            except (Exception, KeyboardInterrupt) as error:
                failure = error
                row.update(status='interrupted', error={'type': type(error).__name__, 'message': str(error)},
                           assessment={'eligible': False, 'reward': None, 'completed': None, 'reason': 'collection_interrupted'})
            finally:
                guard = owner.finish_evaluation_guard(snapshot)
                folder.mkdir(parents=True, exist_ok=True)
                atomic_write(folder / 'evaluation-guard.json', json_bytes(guard))
                row['evaluation_guard'] = guard
                row['after_actor_identity'] = owner.freeze_identity()
                if not guard['learning_unchanged'] or not guard['rng_restored_exactly']:
                    row.update(status='guard_failed', assessment={'eligible': False, 'reward': None, 'completed': None, 'reason': 'evaluation_guard_failed'})
                    failure = failure or ValueError('Four-project evaluation changed learning state or failed RNG restoration')
                atomic_write(output / 'report.json', json_bytes(report))
            if failure is not None:
                raise failure
            if row['assessment'].get('eligible') is not True:
                report.update(status='stopped_unknown_execution', unstarted_slots=[s['slot_id'] for s in plan['slots'][len(report['episodes']):]])
                break
        else:
            report['status'] = 'complete'
    except (Exception, KeyboardInterrupt) as error:
        report.update(status='interrupted', error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        report.update(actor_steps_total=owner.actor_steps, critic_steps_total=owner.critic_steps,
                      final_actor_identity=owner.freeze_identity())
        atomic_write(output / 'report.json', json_bytes(report))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', required=True, help='Final H1 report.json or selection.json containing its hash-bound report_ref')
    parser.add_argument('--candidate', choices=CANDIDATES, help='Optional explicit cross-check; never substitutes for final selection')
    parser.add_argument('--protocol', help='Optional exact selected H1 launch protocol cross-check')
    parser.add_argument('--model', required=True)
    parser.add_argument('--weight-manifest', required=True)
    parser.add_argument('--harness', choices=HARNESSES, required=True)
    parser.add_argument('--runtime-profile', help='Optional explicit profile changing only device-count placement')
    parser.add_argument('--placement-reason')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = code_identity()
    atomic_write(output / 'source-before.json', json_bytes(source))
    plan = read_json(PLAN)
    atomic_write(output / 'plan.json', json_bytes(plan))
    atomic_write(output / 'launch-arguments.json', json_bytes(vars(args) | {'output': str(args.output)}))
    owner = None
    status = 'validating_binding'
    try:
        require(source.get('code_dirty') is False, 'Freeze a clean source commit before real project evaluation')
        binding = validate_binding(args.selection, model=args.model, weight_manifest=args.weight_manifest,
            harness=args.harness, candidate=args.candidate, protocol_path=args.protocol,
            runtime_profile=args.runtime_profile, placement_reason=args.placement_reason)
        atomic_write(output / 'binding-validation.json', json_bytes(binding))
        atomic_write(output / 'effective-profile.json', json_bytes(binding['profile']))
        status = 'loading'
        from proworksim.candidate_runtime_v017 import CandidateActor
        dependencies = {name: importlib.metadata.version(name) for name in ('duckdb', 'openpyxl', 'torch', 'transformers', 'peft')}
        if args.harness == 'openhands_v16':
            dependencies['openhands-sdk'] = importlib.metadata.version('openhands-sdk')
        require(dependencies['duckdb'] == '1.5.5', 'Declared SQL executor version differs')
        atomic_write(output / 'runtime-dependencies.json', json_bytes(dependencies))
        owner = CandidateActor.from_candidate(args.model, manifest=args.weight_manifest, profile=binding['profile'],
                                               recipe=binding['recipe'], output=output / 'resident')
        identity = owner.freeze_identity()
        actor_same = identity.get('adapter_sha256') == binding['H1_initial_actor_identity'].get('adapter_sha256')
        require(binding['placement_revision'] is not None or actor_same, 'Fresh adapter differs from selected H1 initial actor under identical placement')
        atomic_write(output / 'initial-identity-comparison.json', json_bytes({'same_adapter_parameters_as_H1': actor_same,
            'H1_initial': binding['H1_initial_actor_identity'], 'actual_initial': identity,
            'explicit_placement_revision': binding['placement_revision']}))
        atomic_write(output / 'adapter-scope.json', json_bytes({'trainable_parameters': sum(p.numel() for p in owner.actor_parameters.values()),
            'total_loaded_parameters': sum(p.numel() for p in owner.model.parameters()),
            'modules': owner.inference_profile.get('actual_lora_modules'),
            'tensors': {name: {'shape': list(p.shape), 'numel': p.numel(), 'dtype': str(p.dtype), 'device': str(p.device)} for name, p in owner.actor_parameters.items()},
            'updated_in_this_run': False}))
        status = 'collecting'
        report = execute(owner, binding, output, plan)
        status = report['status']
        print(json.dumps({'status': status, 'episodes': len(report['episodes']), 'actor_steps': owner.actor_steps, 'critic_steps': owner.critic_steps}))
    except (Exception, KeyboardInterrupt) as error:
        atomic_write(output / 'interruption.json', json_bytes({'stage': status, 'type': type(error).__name__, 'message': str(error),
            'actor_steps': owner.actor_steps if owner else None, 'critic_steps': owner.critic_steps if owner else None,
            'scope': 'Unknown remains unknown; no retry, replacement, restored actor or imputed unstarted episode.'}))
        raise
    finally:
        after = code_identity()
        atomic_write(output / 'source-after.json', json_bytes(after))
        atomic_write(output / 'source-comparison.json', json_bytes({'unchanged': source == after}))


if __name__ == '__main__':
    main()
