"""Independent r2 for the original three, after zero-model r1 binding failure.

The original worker code object and resource supervisor algorithm are reused in
private namespaces. Model-visible source is copied byte-for-byte from the old
snapshot. Four interrupted episodes remain unknown and are never replayed.
"""
from __future__ import annotations

import argparse
import ast
import copy
from functools import cache
import inspect
import json
from pathlib import Path
import shutil
import time
from types import FunctionType

from proworksim.audit import code_identity
from proworksim.online_training import sha_file
from proworksim.storage import digest, read_json
from scripts import software_bridge_v052 as bridge
from scripts.software_calibration_v051 import checked, ref, sealed, unseal, write

VERSION = 'software-openhands-bridge-resume-r2-v0.52'
MODULE = 'scripts.software_bridge_v052_resume_r2'
MODULE_FILE = 'scripts/software_bridge_v052_resume_r2.py'
STAGE = 'v052-OH-BRIDGE-resume-r2'
ORIGINAL_COMMIT = '7d95912b4ce9ae3130b01b4ce87bc26f9e2e5b9d'
PENDING = (
    'v052-cal2-xmltodict-1-PS1',
    'v052-cal2-xmltodict-2-PS1',
    'v052-cal2-xmltodict-2-OH_ref',
)
INTERRUPTED = (
    'v052-cal2-boltons-2-PS1', 'v052-cal2-parse-1-PS1',
    'v052-cal2-parse-2-PS1', 'v052-cal2-xmltodict-1-OH_ref',
)
CONTRACT = copy.deepcopy(bridge.CONTRACT)
LIMITS = copy.deepcopy(bridge.LIMITS)
GPU_PREFERENCE = list(range(8))
BOUND = {'maximum_slots': 3, 'maximum_actual_tokens': 1500000,
         'maximum_decisions': 384, 'maximum_attempts': 384,
         'maximum_public_project_tests': 64}
RELEASE_CHECKS = {
    'predecessor_terminal_no_inflight', 'only_three_never_entered',
    'all_nine_entered_excluded', 'four_interrupted_unknown_preserved',
    'original_scientific_sources_unchanged', 'original_qualifications_reused',
    'resume_host_controls', 'old_budget_and_costs_not_transferred',
    'r1_zero_model_entry_failure_preserved',
}
PREDECESSOR_KEYS = ('predecessor_plan', 'predecessor_supervisor', 'predecessor_pause', 'predecessor_stage_report')
PRESERVED_KEYS = (
    'purpose', 'source_commit', 'source_files', 'model_admission', 'admission_references',
    'repository_source_root', 'adapter_manifest', 'test_runtime', 'reference_runtime',
    'model_path', 'model_manifest', 'native_python', 'runtime_dependency_path', 'resource_modules',
    'contract', 'limits', 'gpu_preference', 'idle_only_admission', 'fresh_resident_per_slot',
    'maximum_parameter_updates', 'maximum_backward_calls', 'new_qualification_calls',
    'model_retries', 'pre_model_resource_only_retries', 'old_costs_transferred',
    'old_budget_transferred', 'automatic_successors',
)


def select_rows(original_rows, supervisor):
    """Pure inventory selection: a stopped or entered slot never becomes eligible."""
    validated = bridge.inventory({'rows': original_rows, 'contract': CONTRACT, 'purpose': bridge.PURPOSE})
    states = supervisor.get('states', {})
    if (supervisor.get('status') != 'paused' or supervisor.get('ended_at') is None
            or supervisor.get('active') or supervisor.get('active_workers')
            or set(states) != {row['slot_id'] for row in validated}):
        raise ValueError('The original twelve-slot host must be terminal paused without in-flight work')
    unopened, stopped, completed = [], [], []
    for row in validated:
        name, state = row['slot_id'], states[row['slot_id']]
        attempts = state.get('attempts')
        if state.get('status') == 'not_started' and attempts == []:
            unopened.append(name)
            continue
        if (state.get('status') not in ('complete', 'stopped') or not attempts
                or any(attempt.get('ended_at') is None or type(attempt.get('exit_code')) is not int
                       for attempt in attempts)):
            raise ValueError('An old entered or incompletely closed attempt cannot be resumed as a fresh slot')
        (stopped if state['status'] == 'stopped' else completed).append(name)
    if tuple(unopened) != PENDING or tuple(stopped) != INTERRUPTED or len(completed) != 5:
        raise ValueError('Only the exact original three never-entered slots may resume; four interrupted stay unknown')
    selected = [copy.deepcopy(row) for row in validated if row['slot_id'] in PENDING]
    if (len(selected) != 3 or sum(row['condition'] == 'PS1' for row in selected) != 2
            or sum(row['generation_tokens'] for row in selected) != BOUND['maximum_actual_tokens']
            or sum(row['decisions'] for row in selected) != BOUND['maximum_decisions']
            or sum(row['attempts'] for row in selected) != BOUND['maximum_attempts']
            or sum(row['project_public_tests'] or 0 for row in selected) != BOUND['maximum_public_project_tests']):
        raise ValueError('Retain every original row budget, role, seed and order without transfer')
    return selected


def never_entered(root, selected):
    root = Path(root).resolve()
    for row in selected:
        for kind in ('slots', 'workers'):
            if (root / kind / row['slot_id']).exists():
                raise ValueError('A selected old not_started slot has execution artifacts: ' + row['slot_id'])


def gates(release, references):
    if (release.get('version') != 'v052-bridge-resume-r2-release-v1'
            or release.get('stage') != STAGE or release.get('released') is not True
            or release.get('user_resume_authorized') is not True
            or release.get('unresolved_blockers') != []
            or set(release.get('checks', {})) != RELEASE_CHECKS
            or any(value is not True for value in release['checks'].values())
            or any(release.get(key) != references[key] for key in PREDECESSOR_KEYS)
            or release.get('selected_slot_ids') != list(PENDING)
            or release.get('original_interrupted_remain_unknown') is not True
            or release.get('exact_resume_state_available_for_interrupted') is not False
            or release.get('old_remaining_budget_transfer') != 0):
        raise ValueError('An independent explicit user-resume release for only the original three is required')
    if release.get('resources') != {'allowed_gpu_indices': GPU_PREFERENCE,
                                    'max_residents': 4, 'idle_only_admission': False}:
        raise ValueError('Keep original all-GPU capacity sharing and maximum four residents')
    observation = release.get('signal_observation', {})
    if (observation.get('scope') != 'supervisor_only' or observation.get('follow_forks') is not False
            or observation.get('worker_wrapped') is not False or observation.get('restart') != 'no'):
        raise ValueError('Signal observation is external, supervisor-only, no-fork-follow and no worker wrapper')
    supporting = release.get('supporting_references', {})
    if not {'signal_observation_control', 'interruption_audit', 'partial_accounting_audit',
            'resume_r1_zero_model_failure', 'cross_interpreter_binding_diagnostic'} <= set(supporting):
        raise ValueError('Bind signal/interruption/accounting and zero-model r1/AST-difference evidence')


def original_state(project, references):
    project = Path(project).resolve()
    old_root = project / 'runs/software-bridge-v052'
    for key, name in zip(PREDECESSOR_KEYS[:3], ('plan.json', 'supervisor.json', 'pause.json'), strict=True):
        if checked(references[key]) != old_root / name:
            raise ValueError('Resume lineage must bind the original v052 root')
    old = unseal(read_json(old_root / 'plan.json'))
    supervisor = read_json(old_root / 'supervisor.json')
    pause = read_json(old_root / 'pause.json')
    report = read_json(checked(references['predecessor_stage_report']))
    if (old.get('version') != bridge.VERSION or old.get('purpose') != bridge.PURPOSE
            or old.get('contract') != CONTRACT or old.get('limits') != LIMITS
            or old.get('gpu_preference') != GPU_PREFERENCE or old.get('idle_only_admission') is not False
            or old.get('fresh_resident_per_slot') is not True or old.get('worker_module') != 'scripts.software_bridge_v052'
            or old.get('source_commit', {}).get('code_commit') != ORIGINAL_COMMIT
            or old.get('source_commit', {}).get('code_dirty') is not False
            or Path(old['source_root']).resolve() != old_root / 'source'
            or supervisor.get('plan') != references['predecessor_plan'] or not pause.get('kind')):
        raise ValueError('Original source/host/pause/numerical identity differs')
    admission = read_json(checked(old['model_admission']))
    for item in old['admission_references'].values():
        checked(item)
    refs = old['admission_references']
    original = bridge.gate_records(admission, read_json(checked(refs['design'])),
                                  read_json(checked(refs['source_qualification'])),
                                  read_json(checked(refs['initial_inputs'])))
    if original != old['rows']:
        raise ValueError('The original full twelve-row qualification must be reused exactly')
    selected = select_rows(original, supervisor)
    if (report.get('version') != 'software-bridge-v052-final-v1'
            or Path(report.get('root', '')).resolve() != old_root
            or report.get('host_status') != 'paused' or report.get('plan') != references['predecessor_plan']
            or report.get('supervisor') != references['predecessor_supervisor']
            or [row.get('slot_id') for row in report.get('rows', [])] != [row['slot_id'] for row in original]
            or [row['slot_id'] for row in report['rows'] if row.get('status') == 'not_started'] != list(PENDING)
            or [row['slot_id'] for row in report['rows'] if row.get('status') == 'technical_unknown'] != list(INTERRUPTED)):
        raise ValueError('Bind the immutable first-stage report, including four unknowns and three unopened rows')
    for name, sha in old['source_files'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts or sha_file(Path(old['source_root']) / name) != sha:
            raise ValueError('An original frozen model/source file changed: ' + name)
    for module, name in ((bridge, 'scripts/software_bridge_v052.py'),
                         (bridge.original_host, 'scripts/software_calibration_v051_cal2.py')):
        if sha_file(Path(module.__file__)) != old['source_files'][name]:
            raise ValueError('Imported inherited worker/supervisor code is not the original frozen source')
    for reference in (old['adapter_manifest'], old['model_manifest'], *old['resource_modules'],
                      *[item['frozen_copy'] for item in old['evidence']]):
        checked(reference)
    entered = {}
    for row in original:
        if row['slot_id'] in PENDING:
            continue
        path = old_root / 'slots' / row['slot_id'] / 'started.json'
        value = read_json(path)
        if value.get('row') != row or value.get('source_plan') != references['predecessor_plan']:
            raise ValueError('Every excluded entered slot retains its original started binding')
        expected_attempts = {str(Path(attempt['output']).resolve()) for attempt in supervisor['states'][row['slot_id']]['attempts']}
        if str(Path(value['attempt']).resolve()) not in expected_attempts:
            raise ValueError('An original started record points outside its supervisor attempts')
        entered[row['slot_id']] = ref(path)
    never_entered(old_root, selected)
    return old, selected, entered


def zero_model_predecessor(project, reference):
    """Reuse the immutable r1 receipt, rejecting any changed trace or new entry."""
    root = Path(project).resolve() / 'runs/software-bridge-v052-resume-r1'
    audit = read_json(checked(reference))
    if (audit.get('version') != 'v052-resume-r1-zero-entry-readonly-audit-v1'
            or audit.get('passed') is not True or audit.get('root') != str(root)
            or audit.get('host_status') != 'paused' or audit.get('host_ended_at') is None
            or not audit.get('checks') or any(value is not True for value in audit['checks'].values())
            or [row.get('slot_id') for row in audit.get('rows', [])] != list(PENDING)
            or audit.get('new_model_calls') != 0):
        raise ValueError('r1 must remain a fully bound zero-model entry failure')
    for name in ('plan.json', 'supervisor.json', 'pause.json', 'supervisor-signals.strace'):
        if Path(audit['sources'][name]['path']).resolve() != root / name:
            raise ValueError('r1 predecessor trace identity changed')
    for item in audit['sources'].values():
        checked(item)
    ledger = audit.get('original_ledger', {})
    if (any(ledger.get(key) != 0 for key in ('known_actual_tokens', 'uncertain_reservation_tokens',
            'started_generations', 'complete_generations', 'ledger_tokens', 'complete_actual_tokens'))
            or ledger.get('integrity_errors') != []
            or [row.get('slot_id') for row in ledger.get('outcomes', [])] != list(PENDING)
            or any(row.get('started') is not False or row.get('closed') is not False
                   for row in ledger.get('outcomes', []))):
        raise ValueError('r1 model exposure or cost prevents a fresh entry')
    for row in audit['rows']:
        if (any(row.get(key) is not False for key in ('slot_entered', 'model_loader_entered',
                'generation_started', 'business_sample_exposure_added'))
                or any(row.get(key) != 0 for key in ('new_model_calls', 'known_actual_tokens',
                    'uncertain_reservation_tokens'))
                or row.get('host_state') != 'stopped' or len(row.get('attempts', [])) != 1):
            raise ValueError('r1 entered or charged rows cannot be replayed')
        attempt = row['attempts'][0]
        if (attempt.get('exit_code') != 1 or attempt.get('ended_at') is None
                or attempt.get('failure') != 'ValueError: Resume source/release/lineage binding changed'
                or attempt.get('failure_present_in_log') is not True
                or attempt.get('all_expected_pre_model_paths_absent') is not True):
            raise ValueError('r1 failure is not the recorded pre-entry binding error')
        for key in ('worker_log', 'launch'):
            checked(attempt[key])
        absent = attempt.get('absent_before_model_paths', {})
        if not absent or any(value is not True or not Path(path).is_relative_to(root) or Path(path).exists()
                             for path, value in absent.items()):
            raise ValueError('r1 has new slot/model entry artifacts')
        output = Path(attempt['output'])
        if (not output.is_relative_to(root / 'workers')
                or sorted(path.name for path in output.iterdir()) != attempt['actual_attempt_directory_entries']):
            raise ValueError('r1 attempt contents changed after its zero-entry audit')
    return audit


def scientific_contract(plan, old, selected):
    if any(plan.get(key) != old.get(key) for key in PRESERVED_KEYS):
        raise ValueError('Original scientific, asset, qualification or resource contract changed')
    if (plan.get('rows') != selected or plan.get('original_rows') != old['rows']
            or [row['slot_id'] for row in plan['rows']] != list(PENDING)
            or any(plan.get(key) != value for key, value in BOUND.items())
            or plan.get('old_remaining_budget_transfer') != 0
            or plan.get('first_exposure_or_entered_retry_exceptions') is not False
            or plan.get('interrupted_slots_remain_unknown') != list(INTERRUPTED)
            or plan.get('excluded_entered_slots') != [row['slot_id'] for row in old['rows'] if row['slot_id'] not in PENDING]):
        raise ValueError('The three-slot budget/order or no-replay/unknown policy changed')


def ledger(root, rows):
    if [row['slot_id'] for row in rows] != list(PENDING):
        raise ValueError('Resume accounting accepts only the fixed three new rows')
    function = algorithm_binding()[3]
    result = function(root, rows)
    # Original accounting arithmetic and null endpoints are retained; only panel labels change.
    result.update(logical_inventory=3, new_inventory=3, original_unique_inventory=12,
                  prior_costs_included=False, old_remaining_budget_transfer=0,
                  scope='This independent three-slot root only; first-stage costs are a separate immutable source, never added here.')
    return result


def canonical_ast(node):
    """Versioned structural value, independent of ast.dump empty-field defaults.

    Omit empty optional fields only. Source bytes remain independently hashed;
    the parsed tree used by the supervisor is not changed by this serialization.
    """
    if isinstance(node, ast.AST):
        return [type(node).__name__, {name: canonical_ast(value) for name, value in ast.iter_fields(node)
                                    if value is not None and value != []}]
    if isinstance(node, list):
        return [canonical_ast(value) for value in node]
    return node


@cache
def algorithm_binding():
    worker_namespace = dict(bridge.__dict__)
    worker_namespace.update(VERSION=VERSION, MODULE=MODULE, frozen=frozen,
                            CONTRACT=copy.deepcopy(CONTRACT), LIMITS=copy.deepcopy(LIMITS))
    worker_function = bridge.worker
    worker_bound = FunctionType(worker_function.__code__, worker_namespace, worker_function.__name__,
                                worker_function.__defaults__, worker_function.__closure__)
    worker_bound.__kwdefaults__ = worker_function.__kwdefaults__
    original_ledger = bridge.ledger
    ledger_bound = FunctionType(original_ledger.__code__, worker_namespace, original_ledger.__name__,
                                original_ledger.__defaults__, original_ledger.__closure__)
    ledger_bound.__kwdefaults__ = original_ledger.__kwdefaults__
    base = bridge.original_host
    namespace = dict(base.__dict__)
    namespace.update(VERSION=VERSION, LIMITS=copy.deepcopy(LIMITS), frozen=frozen,
                     ledger=ledger, classify_closed=bridge.classify_closed)
    completion = base.worker_completion
    bound_completion = FunctionType(completion.__code__, namespace, completion.__name__,
                                    completion.__defaults__, completion.__closure__)
    bound_completion.__kwdefaults__ = completion.__kwdefaults__
    namespace['worker_completion'] = bound_completion
    source = inspect.getsource(base.supervise)
    tree, replacements = ast.parse(source), 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == 'scripts.software_calibration_v051_cal2':
            node.value = MODULE
            replacements += 1
    if replacements != 1:
        raise ValueError('The original resource supervisor has exactly one worker-module literal')
    ast.fix_missing_locations(tree)
    exec(compile(tree, '<v052-resume-r2-worker-module-only>', 'exec'), namespace)
    adaptation = {'version': VERSION, 'worker_module': MODULE,
        'worker_code_unchanged': worker_bound.__code__ is bridge.worker.__code__,
        'ledger_code_unchanged': ledger_bound.__code__ is bridge.ledger.__code__,
        'worker_completion_code_unchanged': bound_completion.__code__ is completion.__code__,
        'supervisor_source_sha256': digest(source.encode()),
        'supervisor_AST_encoding': 'nonempty-fields-json-v1',
        'supervisor_AST_sha256': digest(json.dumps(canonical_ast(tree), sort_keys=True, separators=(',', ':')).encode()),
        'changed_worker_module_literals': replacements,
        'worker_global_overrides': ['VERSION', 'MODULE', 'frozen', 'CONTRACT', 'LIMITS'],
        'supervisor_global_overrides': ['VERSION', 'LIMITS', 'frozen', 'ledger', 'classify_closed', 'worker_completion'],
        'old_module_globals_modified': False, 'model_loop_or_tools_or_history_modified': False,
        'resource_process_deadline_algorithms_modified': False}
    return worker_bound, namespace['supervise'], adaptation, ledger_bound


def prepare(root, *, project_root, release_path=None):
    project, root = Path(project_root).resolve(), Path(root).resolve()
    if root != project / 'runs/software-bridge-v052-resume-r2' or root.exists():
        raise ValueError('Use only the predeclared fresh resume-r2 root, never replay or overwrite it')
    release_path = Path(release_path or project / 'docs/experiments/software-bridge-v052-resume-r2-release.json').resolve()
    release = read_json(release_path)
    references = {key: copy.deepcopy(release[key]) for key in PREDECESSOR_KEYS}
    gates(release, references)
    identity = code_identity()
    if identity.get('code_dirty') is not False:
        raise ValueError('Commit the independent resume source, controls and release before prepare')
    old, selected, entered = original_state(project, references)
    zero_model_predecessor(project, release['supporting_references']['resume_r1_zero_model_failure'])
    controls = read_json(checked(release['controls']))
    if controls.get('version') != 'v052-resume-r2-host-controls-v1' or controls.get('passed') is not True:
        raise ValueError('Bind the new finite resume host controls')
    host_source = checked(release['resume_host_source'])
    if host_source != project / MODULE_FILE or ref(Path(__file__)) != release['resume_host_source']:
        raise ValueError('Freeze this committed independent resume host source')
    if controls.get('sources', {}).get(MODULE_FILE) != release['resume_host_source']:
        raise ValueError('The resume host source must be exactly the one bound by controls')
    if MODULE_FILE in old['source_files']:
        raise ValueError('A newly added host cannot overwrite any original source path')
    for item in [release['protocol'], *release['supporting_references'].values()]:
        checked(item)
    root.mkdir(parents=True)
    snapshot = root / 'source'
    for name in old['source_files']:
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(old['source_root']) / name, target)
    target = snapshot / MODULE_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(host_source, target)
    extra_sources = {MODULE_FILE: sha_file(target)}
    evidence = []
    paths = [release_path, *[Path(item['path']) for item in references.values()],
             Path(release['protocol']['path']), Path(release['controls']['path']),
             *[Path(item['path']) for item in release['supporting_references'].values()]]
    for index, path in enumerate(paths):
        destination = root / 'evidence' / f'{index:02d}-{path.name}'
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(path, destination)
        evidence.append({'original': ref(path), 'frozen_copy': ref(destination)})
    plan = copy.deepcopy(old)
    plan.pop('sha256', None)
    plan.update(version=VERSION, created_at=time.time(), project_root=str(project), source_root=str(snapshot),
        rows=selected, original_rows=copy.deepcopy(old['rows']), predecessor_root=str(project / 'runs/software-bridge-v052'),
        predecessor_references=references, excluded_entered_slots=list(entered),
        original_entered_records=entered, interrupted_slots_remain_unknown=list(INTERRUPTED),
        resume_release=ref(release_path), resume_protocol=copy.deepcopy(release['protocol']),
        resume_controls=copy.deepcopy(release['controls']), resume_host_source=copy.deepcopy(release['resume_host_source']),
        resume_host_commit=identity, resume_host_source_files=extra_sources, worker_module=MODULE,
        original_evidence=copy.deepcopy(old['evidence']), evidence=evidence,
        supervisor_adaptation=algorithm_binding()[2], old_remaining_budget_transfer=0,
        first_exposure_or_entered_retry_exceptions=False,
        prior_cost_source=references['predecessor_stage_report'],
        prior_cost_scope='First-stage report is lineage and one future merge cost source only; never charged to this new root.',
        signal_observation=copy.deepcopy(release['signal_observation']),
        supporting_references=copy.deepcopy(release['supporting_references']),
        source_snapshot_scope='Original source_files/source_commit preserved byte-for-byte; independent resume host source/commit bound separately.',
        **BOUND)
    scientific_contract(plan, old, selected)
    write(root / 'plan.json', sealed(plan))
    return plan


def frozen(root):
    root = Path(root).resolve()
    plan = unseal(read_json(root / 'plan.json'))
    project = Path(plan['project_root']).resolve()
    if (root != project / 'runs/software-bridge-v052-resume-r2' or plan.get('version') != VERSION
            or plan.get('worker_module') != MODULE or plan.get('resume_host_commit', {}).get('code_dirty') is not False
            or Path(plan['source_root']).resolve() != root / 'source'):
        raise ValueError('Distinct resume plan, source root and committed host identity are required')
    release = read_json(checked(plan['resume_release']))
    refs = plan['predecessor_references']
    gates(release, refs)
    old, selected, entered = original_state(project, refs)
    zero_model_predecessor(project, release['supporting_references']['resume_r1_zero_model_failure'])
    scientific_contract(plan, old, selected)
    if (plan.get('original_entered_records') != entered
            or plan.get('predecessor_root') != str(project / 'runs/software-bridge-v052')
            or plan.get('resume_protocol') != release['protocol']
            or plan.get('resume_controls') != release['controls']
            or plan.get('resume_host_source') != release['resume_host_source']
            or plan.get('supporting_references') != release['supporting_references']
            or plan.get('signal_observation') != release['signal_observation']
            or plan.get('prior_cost_source') != refs['predecessor_stage_report']
            or plan.get('supervisor_adaptation') != algorithm_binding()[2]):
        raise ValueError('Resume source/release/lineage binding changed')
    extra = plan.get('resume_host_source_files', {})
    if extra != {MODULE_FILE: release['resume_host_source']['sha256']} or set(extra) & set(old['source_files']):
        raise ValueError('Only the separately controlled resume host may supplement the original source map')
    wanted = {**plan['source_files'], **extra}
    actual = {str(path.relative_to(root / 'source')) for path in (root / 'source').rglob('*.py')
              if '__pycache__' not in path.parts}
    if actual != set(wanted):
        raise ValueError('Unexpected or missing Python source in the copied frozen source tree')
    for name, sha in wanted.items():
        if sha_file(root / 'source' / name) != sha:
            raise ValueError('Resume frozen source changed: ' + name)
    if sha_file(Path(__file__)) != extra[MODULE_FILE]:
        raise ValueError('Run the exact controlled resume module')
    for item in [plan['resume_protocol'], plan['resume_controls'], plan['resume_host_source'],
                 *plan['supporting_references'].values(), *[item['frozen_copy'] for item in plan['evidence']]]:
        checked(item)
    controls = read_json(checked(plan['resume_controls']))
    if (controls.get('version') != 'v052-resume-r2-host-controls-v1' or controls.get('passed') is not True
            or controls.get('sources', {}).get(MODULE_FILE) != release['resume_host_source']):
        raise ValueError('Resume control/source evidence changed')
    return plan


def worker(root, slot_id, attempt):
    return algorithm_binding()[0](root, slot_id, attempt)


def supervise(root):
    return algorithm_binding()[1](root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'supervise', 'worker'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--release', type=Path)
    parser.add_argument('--slot')
    parser.add_argument('--attempt', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        if args.project_root is None:
            parser.error('prepare requires --project-root')
        prepare(args.root, project_root=args.project_root, release_path=args.release)
    elif args.command == 'supervise':
        supervise(args.root)
    else:
        raise SystemExit(worker(args.root, args.slot, args.attempt))


if __name__ == '__main__':
    main()
