"""Two actual model roles on the named, isolated D2 variant; no teacher actions.

The planner prefix delivers the public specification verbatim, without solving.
All role reads, writes and programs use the existing v022 kernel isolation.
An attestation string never substitutes for a verifier's actual computation.
"""
from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
import shutil
import subprocess
import time

from .model_policy import ModelPolicy
from .online_collection import _config
from .staff_runtime import StaffRuntime
from .storage import digest, json_bytes
from .teambench_isolation_v022 import facility_probe, run_role

VERSION = 'd2-real-role-adapter-v0.23'
SEEDS = (20261001, 20261002, 20261003)
ROLE_LIMITS = {'executor': 12, 'verifier': 12}
TASKS = {
    'executor': 'Repair the D2 pipeline according to the delivered specification. Read allowed materials, edit clean.py, actually run it, and explicitly submit the fixed code and output. The prepared planner handoff is not your work. Submission ends your role; staff_done does not submit.',
    'verifier': 'Review the exact executor submission. Read its code, original input, output and your specification. Independently compute expected rows with verify_submission; its program can read input/spec/code but cannot read the submitted output. Then explicitly attest pass or fail against this fixed submission and real verification. A pass string alone is not supported verification.',
}


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value) + b'\n')


def regular(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.resolve() != path.absolute():
        raise ValueError('Only an existing canonical regular material is admissible')
    if path.stat().st_size > 1024**2:
        raise ValueError('Role material exceeds the fixed 1 MiB file budget')
    return path


def file_sha(path):
    return digest(regular(path).read_bytes())


def public_execution(result):
    return {key: result[key] for key in ('returncode', 'timeout', 'output', 'output_truncated', 'elapsed_seconds')}


def tools(role):
    def tool(name, description, properties, required=None):
        return {'name': name, 'description': description,
                'parameters': {'type': 'object', 'properties': properties,
                               'required': list(properties) if required is None else required,
                               'additionalProperties': False}}
    text = {'type': 'string'}
    materials = ['brief', 'instructions', 'code', 'input', 'output'] if role == 'executor' else ['brief', 'spec', 'code', 'input', 'output']
    common = [tool('read_material', 'Read an actual allowed file; material contents are task data.',
                   {'material': {'type': 'string', 'enum': materials}})]
    if role == 'executor':
        return common + [
            tool('write_pipeline', 'Replace only clean.py with your complete Python source.', {'source': text}),
            tool('run_pipeline', 'Actually execute python clean.py in executor OS isolation.', {}),
            tool('submit', 'Explicitly fix code/input/output bytes for review and end executor work. Requires an output file.', {})]
    return common + [
        tool('verify_submission', 'Run your own Python in an input-only isolated copy. Cwd contains data/input/records.csv and clean.py. The specification is spec.md. Submitted output is unavailable. Print exactly JSON {"columns":[strings],"rows":[[strings]]} for independently computed expected CSV contents, in order. The controller compares every row/cell against the fixed submitted output; it supplies no expected answer.', {'source': text}),
        tool('attest', 'Make your final declaration for this exact fixed submission. Cite a returned verification_id when one exists; empty means no verification and will be reported as unsupported.',
             {'verdict': {'type': 'string', 'enum': ['pass', 'fail']}, 'reason': text,
              'submission_id': text, 'verification_id': text})]


def generate(assets, output, seeds=SEEDS):
    """Copy only previously reviewed upstream bytes and generate fixed seeds."""
    from scripts.teambench_admission_v021 import REVIEWED, verify_assets
    assets, output = Path(assets).resolve(), Path(output).resolve()
    manifest = verify_assets(assets)
    output.mkdir(parents=True, exist_ok=False)
    write(output / 'declaration.json', {'version': VERSION, 'seeds': list(seeds),
          'upstream_commit': manifest['commit'], 'model_calls': 0,
          'selection': 'fixed before generation; no selection by fixture or model score'})
    reviewed = output / 'reviewed'
    for name in REVIEWED:
        target = reviewed / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(assets / 'files' / name, target)
    code = """import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from generators.gen_d2_data_quality import Generator
for seed in json.loads(sys.argv[3]):
 root=Path(sys.argv[2])/('seed'+str(seed));g=Generator();t=g.generate(seed)
 g.write_to_disk(t,str(root/'workspace'),str(root/'reports'),str(root/'task'))
"""
    result = subprocess.run(['/usr/bin/python3', '-I', '-B', '-S', '-c', code,
        str(reviewed), str(output / 'generated'), json.dumps(list(seeds))],
        capture_output=True, text=True, timeout=20, env={'LANG': 'C.UTF-8'}, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return output / 'generated', reviewed / 'tasks/D2_data_quality/grade.sh'


class D2Episode:
    def __init__(self, generated, grader, output, *, seed):
        from scripts.teambench_isolation_v022 import layout
        if not facility_probe()['available']:
            raise RuntimeError('Existing Landlock/seccomp facility unavailable')
        self.output = Path(output).resolve()
        self.root = self.output / 'roles-world'
        self.generated, self.grader, self.seed = Path(generated), Path(grader), seed
        self.variant = layout(self.generated, self.root, self.grader)
        # This is an explicitly credited program preparation, not a model planner.
        shutil.copyfile(self.root / 'roles/planner/private/spec.md',
                        self.root / 'roles/executor/inbox/instructions.md')
        self.submission = None
        self.attestation = None
        self.events, self.verifications = [], []
        self.reads = {'executor': {}, 'verifier': {}}
        self.expected_sha = file_sha(self.root / 'trusted/expected.json')
        write(self.output / 'preparation.json', {'version': VERSION, 'seed': seed,
              'planner': 'program_preparation_verbatim_spec_delivery_not_model_work',
              'handoff_sha256': file_sha(self.root / 'roles/executor/inbox/instructions.md'),
              'initial_input_sha256': file_sha(self.root / 'workspace/data/input/records.csv'),
              'initial_code_sha256': file_sha(self.root / 'workspace/clean.py'),
              'trusted_expected_sha256': self.expected_sha,
              'roles': ['executor', 'verifier'], 'limits': ROLE_LIMITS, 'variant': self.variant})

    def material(self, role, name):
        paths = {'brief': 'public/brief.md', 'code': 'workspace/clean.py',
                 'input': 'workspace/data/input/records.csv', 'output': 'workspace/data/output/clean.csv'}
        if role == 'executor':
            paths['instructions'] = 'roles/executor/inbox/instructions.md'
        elif role == 'verifier':
            paths['spec'] = 'roles/verifier/private/spec.md'
        if name not in paths:
            raise ValueError('Material is outside this role contract')
        return self.root / paths[name]

    def snapshot(self):
        return {name: file_sha(self.material('verifier', name)) for name in ('code', 'input', 'output')}

    def isolated(self, role, command, label, root=None):
        row = run_role(root or self.root, role, command,
                       log=self.output / 'os-executions' / f'{len(self.events):03d}-{label}.json')
        if not row['isolation']:
            raise RuntimeError('Role command did not install existing OS isolation')
        return row

    def action(self, role, name, args):
        if role not in ROLE_LIMITS or name not in {x['name'] for x in tools(role)}:
            raise ValueError('Unsupported role action')
        definition = next(item for item in tools(role) if item['name'] == name)
        if set(args) != set(definition['parameters']['required']):
            raise ValueError('Arguments must match the complete declared action schema')
        if (role == 'executor' and self.submission) or (role == 'verifier' and self.attestation):
            raise ValueError('Role has already finalized')
        if role == 'verifier' and not self.submission:
            raise ValueError('Verifier requires an actual fixed submission')
        if self.submission and self.snapshot() != self.submission['files']:
            raise RuntimeError('Fixed submitted workspace changed')
        if name == 'read_material':
            path = self.material(role, args['material'])
            regular(path)
            result = self.isolated(role, ['/usr/bin/cat', str(path)], 'read')
            if result['returncode'] or result['timeout'] or result['output_truncated']:
                return {'ok': False, 'error': {'code': 'read_failed'}, 'result': public_execution(result)}
            self.reads[role][args['material']] = file_sha(path)
            return {'ok': True, 'result': {'material': args['material'], 'sha256': file_sha(path), 'content': result['output']}}
        if name == 'write_pipeline':
            source = args['source']
            if not isinstance(source, str) or len(source.encode()) > 1024**2:
                raise ValueError('Invalid finite pipeline source')
            result = self.isolated(role, ['/usr/bin/python3', '-I', '-B', '-S', '-c',
                'from pathlib import Path;import sys;Path("clean.py").write_text(sys.argv[1])', source], 'write')
            return {'ok': result['returncode'] == 0 and not result['timeout'], 'result': public_execution(result)}
        if name == 'run_pipeline':
            result = self.isolated(role, ['/usr/bin/python3', '-I', '-B', '-S', 'clean.py'], 'build')
            return {'ok': result['returncode'] == 0 and not result['timeout'], 'result': public_execution(result)}
        if name == 'submit':
            files = self.snapshot()
            self.submission = {'submission_id': 'fixed-' + digest(json_bytes(files)), 'files': files,
                               'executor_action_index': len(self.events)}
            write(self.output / 'fixed-submission.json', self.submission)
            return {'ok': True, 'result': self.submission}
        if name == 'verify_submission':
            return self.verify(args['source'])
        if name == 'attest':
            if args['verdict'] not in ('pass', 'fail') or not args['reason'].strip():
                raise ValueError('A nonempty explicit judgment is required')
            if args['submission_id'] != self.submission['submission_id']:
                raise ValueError('Attestation does not bind the fixed submission')
            if args['verification_id'] and args['verification_id'] not in {v['verification_id'] for v in self.verifications}:
                raise ValueError('Unknown verification identifier')
            result = self.isolated(role, ['/usr/bin/python3', '-I', '-B', '-S', '-c',
                'from pathlib import Path;import sys;Path(sys.argv[1]).write_text(sys.argv[2])',
                str(self.root / 'roles/verifier/outbox/attestation.json'), json.dumps(args)], 'attest')
            if result['returncode'] or result['timeout']:
                return {'ok': False, 'error': {'code': 'attestation_write_failed'}, 'result': public_execution(result)}
            self.attestation = copy.deepcopy(args)
            return {'ok': True, 'result': self.attestation}
        raise ValueError('Unhandled action')

    def verify(self, source):
        # Same audited role profile, new finite layout. Its readable workspace
        # has original input/code/spec only; the original result path is denied.
        from scripts.teambench_isolation_v022 import layout
        if not isinstance(source, str) or len(source.encode()) > 1024**2:
            raise ValueError('Invalid finite verification source')
        index = len(self.verifications)
        root = self.output / f'input-only-verification-{index}'
        layout(self.generated, root, self.grader)
        shutil.copyfile(regular(self.root / 'workspace/clean.py'), root / 'workspace/clean.py')
        shutil.copyfile(root / 'roles/verifier/private/spec.md', root / 'workspace/spec.md')
        # Source is passed by the actual verifier action; no oracle program runs.
        result = self.isolated('verifier', ['/usr/bin/python3', '-I', '-B', '-S', '-c', source],
                               f'check-{index}', root=root)
        expected = None
        valid = False
        if result['returncode'] == 0 and not result['timeout'] and not result['output_truncated']:
            try:
                expected = json.loads(result['output'])
                valid = (isinstance(expected, dict) and set(expected) == {'columns', 'rows'}
                    and isinstance(expected['columns'], list) and len(expected['columns']) == 4
                    and all(isinstance(x, str) for x in expected['columns'])
                    and isinstance(expected['rows'], list)
                    and all(isinstance(row, list) and len(row) == 4 and all(isinstance(x, str) for x in row)
                            for row in expected['rows']))
            except ValueError:
                pass
        with regular(self.root / 'workspace/data/output/clean.csv').open(newline='') as stream:
            rows = list(csv.reader(stream))
        submitted = {'columns': rows[0] if rows else [], 'rows': rows[1:]}
        row = {'verification_id': f'check-{index}', 'submission_id': self.submission['submission_id'],
               'source_sha256': digest(source.encode()), 'execution_succeeded': result['returncode'] == 0 and not result['timeout'],
               'input_only_kernel_isolation': True, 'valid_expected_table': bool(valid),
               'submitted_table_equal': expected == submitted if valid else None,
               'expected_table_sha256': digest(json_bytes(expected)) if valid else None,
               'submitted_table_sha256': digest(json_bytes(submitted)), 'stdout': result['output'],
               'returncode': result['returncode'], 'timeout': result['timeout'],
               'scope': 'Actual model-authored input-only program; equality checks this fixed data only, not generalized semantic independence.'}
        self.verifications.append(row)
        write(self.output / f'verification-{index}.json', row)
        return {'ok': bool(valid), 'result': row,
                **({} if valid else {'error': {'code': 'verification_did_not_return_a_table'}})}

    def call(self, role, name, **args):
        key = args.pop('request_key', None)
        try:
            response = self.action(role, name, args)
        except (ValueError, OSError, KeyError, TypeError) as error:
            response = {'ok': False, 'error': {'code': 'role_action_rejected', 'message': str(error)}}
        self.events.append({'role': role, 'action': name, 'arguments': args,
                            'request_key': key, 'response': copy.deepcopy(response)})
        write(self.output / 'actions.json', self.events)
        return response

    def assess(self):
        from scripts.teambench_isolation_v022 import grade_case, layout
        root = self.output / 'grading-copy'
        layout(self.generated, root, self.grader)
        for path in ('clean.py', 'data/input/records.csv', 'data/output/clean.csv'):
            original = self.root / 'workspace' / path
            if original.exists():
                shutil.copyfile(regular(original), root / 'workspace' / path)
        if self.attestation:
            write(root / 'roles/verifier/outbox/attestation.json', self.attestation)
        grade = grade_case(root, self.expected_sha, self.output / 'grading-evidence')
        judgment = self.attestation
        check = next((x for x in self.verifications if judgment and x['verification_id'] == judgment['verification_id']), None)
        reads = self.reads['verifier']
        complete_reads = bool(self.submission and all(reads.get(name) == self.submission['files'][name] for name in ('code', 'input', 'output'))
                              and reads.get('spec') == file_sha(self.root / 'roles/verifier/private/spec.md'))
        executed = bool(check and check['execution_succeeded'] and check['valid_expected_table'])
        supported = bool(complete_reads and executed and judgment and
                         (judgment['verdict'] == 'pass') == check['submitted_table_equal'])
        score = grade.get('score') or {}
        parts = grade.get('decomposed') or {}
        artifact_pass = (parts.get('artifact_checks_passed') == parts.get('artifact_checks_total')) if grade['status'] == 'graded' else None
        rerun_output = root / 'workspace/data/output/clean.csv'
        reproduced = bool(self.submission and rerun_output.exists() and file_sha(rerun_output) == self.submission['files']['output'])
        responsibility = {'explicit_fixed_submission': self.submission is not None,
            'complete_fixed_verifier_reads': complete_reads, 'verifier_computation_executed': executed,
            'formal_attestation': judgment, 'supported_attestation': supported,
            'unsupported_pass': bool(judgment and judgment['verdict'] == 'pass' and not supported),
            'artifact_checks_pass': artifact_pass,
            'grader_rerun_reproduces_fixed_output': reproduced,
            'wrong_approval': bool(judgment and judgment['verdict'] == 'pass' and (artifact_pass is False or not reproduced)),
            'wrong_rejection': bool(judgment and judgment['verdict'] == 'fail' and artifact_pass and reproduced),
            'fixed_workspace_unchanged': self.snapshot() == self.submission['files'] if self.submission else None,
            'full_joint_responsibility': bool(self.submission and grade['status'] == 'graded' and score.get('pass') and supported and reproduced)}
        return {'version': VERSION, 'seed': self.seed, 'grader': grade, 'responsibility': responsibility,
                'case_identity': {'input_sha256': file_sha(self.generated / 'workspace/data/input/records.csv'),
                                  'initial_code_sha256': file_sha(self.generated / 'workspace/clean.py'),
                                  'spec_sha256': file_sha(self.generated / 'task/spec.md'),
                                  'trusted_expected_sha256': self.expected_sha},
                'official_native_score': False, 'source': 'same official synthetic D2 family; new seed is not a new source',
                'preparation_credited_to_models': False}


class D2Port:
    def __init__(self, episode, role):
        self.episode, self.role = episode, role

    def tools(self):
        return tools(self.role)

    def observe(self):
        return {'world_id': f'd2-seed-{self.episode.seed}', 'instance_id': self.episode.output.name,
                'branch_id': 'fixed', 'actor_id': self.role, 'projects': {'D2': {}},
                'contract': TASKS[self.role], 'role_decision_limit': ROLE_LIMITS[self.role],
                'fixed_submission': copy.deepcopy(self.episode.submission),
                'allowed_materials': [x for x in ('brief', 'instructions', 'spec', 'code', 'input', 'output')
                                      if x != ('spec' if self.role == 'executor' else 'instructions')]}

    def call(self, name, **args):
        return self.episode.call(self.role, name, **args)


def run_episode(owner, generated, grader, output, *, seed):
    episode = D2Episode(generated, grader, output, seed=seed)
    boundaries = {}
    for role in ROLE_LIMITS:
        if role == 'verifier' and not episode.submission:
            boundaries[role] = {'status': 'not_activated_no_fixed_submission', 'model_calls': 0}
            continue
        policy = ModelPolicy(_config(owner, role, TASKS[role], ROLE_LIMITS), transport=owner.transport,
                             audit_dir=episode.output / 'model-calls' / role)
        runtime = StaffRuntime({role: D2Port(episode, role)}, {role: policy})
        results = []
        for _ in range(ROLE_LIMITS[role] + 1):
            result = runtime.step()
            results.append(result)
            write(episode.output / f'{role}-runtime.json', runtime.snapshot())
            if (role == 'executor' and episode.submission) or (role == 'verifier' and episode.attestation):
                boundaries[role] = {'status': 'explicit_submission' if role == 'executor' else 'explicit_attestation'}
                break
            if result['status'] in {'completed', 'model_budget_exhausted', 'model_service_error', 'model_format_error',
                                     'binding_mismatch', 'environment_error', 'policy_error'}:
                boundaries[role] = {'status': result['status']}
                break
        boundaries.setdefault(role, {'status': 'finite_role_deadline'})
        boundaries[role].update(opportunities=runtime.opportunities, actions=runtime.actions, outcomes=results)
    report = episode.assess()
    report['boundaries'] = boundaries
    write(episode.output / 'report.json', report)
    return report


def run_checkpoint(owner, *, assets, output, checkpoint_label, on_episode_start=None):
    """Evaluate three fixed seeds using an existing IDLE owner; restore its RNG.

    The caller owns GPU/global wall supervision and initial/final checkpoint
    selection. This adapter neither loads another model nor updates any parameter.
    """
    if checkpoint_label not in ('initial', 'final'):
        raise ValueError('Only the predeclared initial/final endpoints are supported')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    generated, grader = generate(assets, output / 'assets')
    report = {'version': VERSION, 'checkpoint': checkpoint_label, 'status': 'started',
              'seeds': list(SEEDS), 'episodes': [], 'actor_identity': owner.freeze_identity(),
              'started_at': time.time(), 'model_api_calls': 0, 'parameter_updates': 0}
    write(output / 'report.json', report)
    for index, seed in enumerate(SEEDS):
        if on_episode_start is not None:
            on_episode_start(seed)
        before = owner.capture_evaluation_state()
        owner.begin_window(f'v023-d2-{checkpoint_label}-{seed}')
        owner.reseed(202610010000 + index, label=f'd2-{seed}')
        report['current_episode'] = {'seed': seed, 'status': 'started'}
        write(output / 'report.json', report)
        try:
            row = run_episode(owner, Path(generated) / f'seed{seed}', grader, output / f'seed{seed}', seed=seed)
        except BaseException as error:
            report.update(status='interrupted_or_unassessed', error={'type': type(error).__name__, 'message': str(error)})
            write(output / 'report.json', report)
            raise
        owner.finish_evaluation([{'slot_id': f'd2-{seed}', 'active_members': ['executor', 'verifier'], 'reward': row}],
                                output / f'seed{seed}' / 'frozen-evaluation')
        guard = owner.finish_evaluation_guard(before)
        if not guard['learning_unchanged'] or not guard['rng_restored_exactly']:
            raise ValueError('External evaluation changed learning state')
        row['evaluation_guard'] = guard
        row['actor_identity'] = owner.freeze_identity()
        report['episodes'].append(row)
        report['current_episode'] = {'seed': seed, 'status': 'closed'}
        write(output / 'report.json', report)
    report.update(status='complete', ended_at=time.time())
    write(output / 'report.json', report)
    return report


def compare_checkpoints(initial, final):
    """Three seed pairs, never six independent sources; unknown remains unknown."""
    by_stage = {}
    for label, report in [('initial', initial), ('final', final)]:
        if report is None:
            by_stage[label] = {}
            continue
        if report.get('version') != VERSION or report.get('checkpoint') != label or report.get('seeds') != list(SEEDS):
            raise ValueError('External endpoint differs from the fixed three-seed contract')
        by_stage[label] = {row['seed']: row for row in report['episodes']}
        if len(by_stage[label]) != len(report['episodes']) or set(by_stage[label]) - set(SEEDS):
            raise ValueError('External endpoint repeats or changes a seed')
    pairs = []
    for seed in SEEDS:
        before, after = by_stage['initial'].get(seed), by_stage['final'].get(seed)
        if before and after and before['case_identity'] != after['case_identity']:
            raise ValueError('Initial/final external material identities differ')
        values = [r['responsibility']['full_joint_responsibility'] if r else None for r in (before, after)]
        known = all(type(value) is bool for value in values)
        pairs.append({'seed': seed, 'initial': values[0], 'final': values[1],
                      'known_pair': known, 'difference': int(values[1])-int(values[0]) if known else None})
    known_sum = sum(row['difference'] for row in pairs if row['known_pair'])
    missing = sum(not row['known_pair'] for row in pairs)
    return {'version': VERSION, 'planned_pairs': 3, 'pairs': pairs, 'known_pairs': 3-missing,
            'mean_full_responsibility_difference': known_sum/3 if not missing else None,
            'unknown_compatible_bounds': [(known_sum-missing)/3, (known_sum+missing)/3],
            'interpretation': 'Three paired seeds in one synthetic D2 source family, separate from internal pilot; no significance or generalization claim.'}
