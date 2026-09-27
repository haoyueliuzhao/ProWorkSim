"""X1: actual unprivileged OS role controls for one explicit D2 grading variant.

CPU program fixtures only. No Docker, sudo, model adapter, API or GPU work.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from proworksim.teambench_isolation_v022 import VERSION, facility_probe, run_role
from scripts.teambench_admission_v021 import (
    D2_WITNESS, REVIEWED, decompose_score, digest, dump, validate_d2_expected,
    verify_assets, write_d2_variant,
)

D2_GRADE_SHA = "8b0a417ea3f810cfa07e376b80b869d479bf574305aef67c62903a738a9a096b"
GENERATOR = """
import sys
sys.path.insert(0,sys.argv[1])
from generators.gen_d2_data_quality import Generator
from pathlib import Path
for seed in (0,1,2):
    root=Path(sys.argv[2])/('seed'+str(seed))
    g=Generator();t=g.generate(seed)
    g.write_to_disk(t,str(root/'workspace'),str(root/'reports'),str(root/'task'))
"""


def hash_tree(root):
    return {str(p.relative_to(root)): digest(p) for p in sorted(Path(root).rglob('*')) if p.is_file()}


def layout(original, target, native_grader):
    target.mkdir(parents=True)
    shutil.copytree(original / 'workspace', target / 'workspace')
    (target / 'workspace/data/output').mkdir(parents=True)
    (target / 'public').mkdir()
    (target / 'trusted').mkdir()
    for role in ('planner', 'executor', 'verifier'):
        for subdir in ('private', 'inbox', 'outbox', 'scratch'):
            (target / 'roles' / role / subdir).mkdir(parents=True)
    shutil.copyfile(original / 'task/brief.md', target / 'public/brief.md')
    for role in ('planner', 'verifier'):
        shutil.copyfile(original / 'task/spec.md', target / 'roles' / role / 'private/spec.md')
    shutil.copyfile(original / 'reports/expected.json', target / 'trusted/expected.json')
    variant = write_d2_variant(native_grader, target / 'trusted/grade.sh')
    if variant['variant_sha256'] != D2_GRADE_SHA:
        raise ValueError('D2 grader differs from the already named v0.21 variant')
    return variant


PROBES = r'''
import json,os,subprocess,socket,sys
from pathlib import Path
root=Path(sys.argv[1]);role=sys.argv[2];own=root/'roles'/role
rows=[]
def attempt(name,operation,allowed):
    try:
        operation();success=True;error=None
    except OSError as e:
        success=False;error={'type':type(e).__name__,'errno':e.errno,'message':str(e)}
    rows.append({'id':name,'expected_allowed':allowed,'actual_allowed':success,'matches':success is allowed,'error':error})
def shell(command):
    result=subprocess.run(['/usr/bin/bash','-c',command],capture_output=True,text=True,timeout=3)
    if result.returncode: raise PermissionError(result.stderr)
    return result.stdout
expected=root/'trusted/expected.json';grader=root/'trusted/grade.sh'
link=own/'scratch/expected-link';link.symlink_to(expected)
attempt('public_brief_read',lambda:(root/'public/brief.md').read_text(),True)
attempt('grader_expected_absolute_read',lambda:expected.read_text(),False)
attempt('grader_program_read',lambda:grader.read_text(),False)
attempt('grader_expected_traversal',lambda:(own/'scratch/../../../trusted/expected.json').read_text(),False)
attempt('grader_expected_symlink',lambda:link.read_text(),False)
attempt('grader_expected_hardlink',lambda:os.link(expected,own/'scratch/expected-hardlink'),False)
attempt('grader_expected_shell',lambda:shell('cat '+str(expected)),False)
attempt('other_role_outbox_write',lambda:(root/'roles'/('executor' if role!='executor' else 'verifier')/'outbox/forged.json').write_text('forged'),False)
attempt('own_scratch_write',lambda:(own/'scratch/allowed.txt').write_text('owned'),True)
attempt('own_scratch_shell_write',lambda:shell('printf fixture > '+str(own/'scratch/shell.txt')),True)
attempt('socket_create',lambda:socket.socket(),False)
attempt('chmod_workspace',lambda:os.chmod(root/'workspace/clean.py',0o777),False)
if role=='executor':
    attempt('input_read',lambda:(root/'workspace/data/input/records.csv').read_text(),True)
    attempt('input_write',lambda:(root/'workspace/data/input/records.csv').write_text('tampered'),False)
    attempt('private_spec_read',lambda:(root/'roles/planner/private/spec.md').read_text(),False)
    attempt('private_spec_shell',lambda:shell('cat '+str(root/'roles/verifier/private/spec.md')),False)
    path=root/'workspace/clean.py';source=path.read_text()
    attempt('pipeline_write',lambda:path.write_text(source),True)
elif role=='verifier':
    attempt('private_spec_read',lambda:(own/'private/spec.md').read_text(),True)
    attempt('workspace_read',lambda:(root/'workspace/clean.py').read_text(),True)
    attempt('workspace_direct_write',lambda:(root/'workspace/clean.py').write_text('tampered'),False)
    attempt('workspace_shell_write',lambda:shell('printf tampered > '+str(root/'workspace/clean.py')),False)
    write_link=own/'scratch/workspace-link';write_link.symlink_to(root/'workspace/clean.py')
    attempt('workspace_symlink_write',lambda:write_link.write_text('tampered'),False)
    attempt('workspace_traversal_write',lambda:(own/'scratch/../../../workspace/clean.py').write_text('tampered'),False)
    attempt('workspace_unlink',lambda:(root/'workspace/clean.py').unlink(),False)
    attempt('workspace_rename',lambda:os.rename(root/'workspace/clean.py',own/'scratch/stolen.py'),False)
    attempt('attestation_write',lambda:(own/'outbox/attestation.json').write_text('{"verdict":"fail","fixture":true}'),True)
else:
    attempt('private_spec_read',lambda:(own/'private/spec.md').read_text(),True)
    attempt('workspace_read',lambda:(root/'workspace/clean.py').read_text(),False)
    attempt('workspace_write',lambda:(root/'workspace/clean.py').write_text('tampered'),False)
    attempt('handoff_write',lambda:(own/'outbox/instructions.md').write_text('Check the complete public rules.'),True)
print(json.dumps({'probes':rows}))
'''

VERIFY_COPY = r'''
import csv,json,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]);scratch=root/'roles/verifier/scratch/copy';scratch.mkdir()
workspace=root/'workspace'
for original in workspace.rglob('*'):
    target=scratch/original.relative_to(workspace)
    if original.is_dir():target.mkdir(parents=True,exist_ok=True)
    elif original.is_file():target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original.read_bytes())
result=subprocess.run(['/usr/bin/python3','-I','-B','-S','clean.py'],cwd=scratch,capture_output=True,text=True)
if result.returncode:raise RuntimeError(result.stderr)
with (scratch/'data/output/clean.csv').open() as f:rows=list(csv.DictReader(f))
(root/'roles/verifier/outbox/attestation.json').write_text(json.dumps({'verdict':'pass','producer':'program_fixture','checked_rows':len(rows),'verification':'independent execution in verifier scratch, no expected access'}))
print(json.dumps({'temporary_execution_returncode':result.returncode,'row_count':len(rows)}))
'''


def checked_role(root, role, command, log):
    result = run_role(root, role, command, log=log)
    if not result['isolation'] or result['timeout'] or result['returncode']:
        raise RuntimeError(f'Role fixture did not complete under isolation: {log}')
    return result


def grade_case(root, frozen_expected_sha, output):
    """Keep native predicates and v0.21 patch; constrain untrusted re-execution."""
    try:
        validate_d2_expected(root / 'trusted/expected.json', frozen_expected_sha)
    except (OSError, ValueError) as error:
        return {'status': 'preflight_rejected', 'score': None, 'reason': str(error)}
    if digest(root / 'trusted/grade.sh') != D2_GRADE_SHA:
        raise ValueError('grader bytes changed')
    import proworksim.teambench_isolation_v022 as isolation
    dispatch = root / 'trusted/bin/python3'
    dispatch.parent.mkdir()
    # The fixed native grader calls python3 clean.py once, then fixed -c
    # predicates. Its PATH must never resolve into the submitted workspace.
    argv = ['/usr/bin/python3', '-I', '-S', str(Path(isolation.__file__).resolve()),
            'grader-dispatch', str(root), str(output / 'grader-clean-isolation.json')]
    dispatch.write_text('#!/usr/bin/bash\nexec ' + shlex.join(argv) + ' "$@"\n')
    dispatch.chmod(0o755)
    reports = root / 'trusted/reports'
    reports.mkdir()
    command = ['/usr/bin/bash', str(root / 'trusted/grade.sh'), str(root / 'workspace'), str(reports),
               str(root / 'roles/verifier/outbox'), str(root / 'public'), str(root / 'trusted/expected.json')]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=30,
                            env={'PATH': str(dispatch.parent) + ':/usr/bin:/bin', 'LANG': 'C.UTF-8'}, check=False)
    dump(output / 'grader-execution.json', {'command': command, 'returncode': result.returncode,
                                         'stdout': result.stdout, 'stderr': result.stderr})
    if result.returncode:
        raise RuntimeError('trusted native grader failed to execute')
    score = json.loads((reports / 'score.json').read_text())
    clean = json.loads((output / 'grader-clean-isolation.json').read_text())
    if not clean['isolation']:
        raise RuntimeError('submitted pipeline was not isolated during grading')
    return {'status': 'graded', 'score': score, 'decomposed': decompose_score(score),
            'grader_sha256': digest(root / 'trusted/grade.sh'),
            'pipeline_rerun_isolated': True, 'pipeline_returncode': clean['returncode']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, default=Path('runs/assets/domain-v021/TeamBench'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assets, out = args.assets.resolve(), args.output.resolve()
    if not re.fullmatch(r'[/A-Za-z0-9_.-]+', str(out)):
        raise ValueError('native eval grader requires a shell-safe output path')
    manifest = verify_assets(assets)
    out.mkdir(parents=True, exist_ok=False)
    facility = facility_probe()
    dump(out / 'declaration.json', {'version': VERSION, 'task': 'D2_data_quality', 'seeds': [0, 1, 2],
        'grading_variants': ['correct', 'wrong_department_forged_pass', 'bad_attestation', 'missing_expected', 'tampered_expected'],
        'additional_guard': 'malicious clean.py attempts expected read during native grader rerun',
        'model_calls': 0, 'api_calls': 0, 'gpu_seconds': 0, 'original_grader_modified': False})
    if not facility['available']:
        dump(out / 'report.json', {'version': VERSION, 'facility': facility, 'status': 'pending_os_facility',
                                  'model_benchmark_launchable': False})
        return
    reviewed = out / 'reviewed-source'
    for name in REVIEWED:
        target = reviewed / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(assets / 'files' / name, target)
    generated = out / 'generated'
    process = subprocess.run(['/usr/bin/python3', '-I', '-B', '-S', '-c', GENERATOR,
                              str(reviewed), str(generated)], cwd=out, env={'LANG': 'C.UTF-8'},
                             capture_output=True, text=True, timeout=15)
    if process.returncode:
        raise RuntimeError(process.stderr)
    root = out / 'role-fixture'
    variant = layout(generated / 'seed0', root, reviewed / 'tasks/D2_data_quality/grade.sh')
    (root / 'workspace/clean.py').write_text(D2_WITNESS)
    original_input = digest(root / 'workspace/data/input/records.csv')
    roles = {}
    for role in ('planner', 'executor', 'verifier'):
        result = checked_role(root, role, ['/usr/bin/python3', '-I', '-B', '-S', '-c', PROBES, str(root), role],
                              out / f'{role}-permission-probes.json')
        roles[role] = json.loads(result['output'])['probes']
    producer = checked_role(root, 'executor', ['/usr/bin/python3', '-I', '-B', '-S', 'clean.py'],
                            out / 'executor-real-build.json')
    before = hash_tree(root / 'workspace')
    verifier = checked_role(root, 'verifier', ['/usr/bin/python3', '-I', '-B', '-S', '-c', VERIFY_COPY, str(root)],
                            out / 'verifier-independent-execution.json')
    unchanged = before == hash_tree(root / 'workspace') and original_input == digest(root / 'workspace/data/input/records.csv')
    controls = []
    for seed in (0, 1, 2):
        source = generated / f'seed{seed}'
        expected_sha = digest(source / 'reports/expected.json')
        for name in ('correct', 'wrong_department_forged_pass', 'bad_attestation', 'missing_expected', 'tampered_expected'):
            case = out / 'grading-controls' / f'seed{seed}' / name
            layout(source, case, reviewed / 'tasks/D2_data_quality/grade.sh')
            code = D2_WITNESS
            if name == 'wrong_department_forged_pass':
                code = code.replace("row[department] = 'review_needed'", 'pass')
            (case / 'workspace/clean.py').write_text(code)
            dump(case / 'roles/verifier/outbox/attestation.json', {'verdict': 'fail' if name == 'bad_attestation' else 'pass',
                  'producer': 'programmatic_grading_fixture_not_model_verifier'})
            if name == 'missing_expected':
                (case / 'trusted/expected.json').unlink()
            elif name == 'tampered_expected':
                expected = json.loads((case / 'trusted/expected.json').read_text())
                expected['row_count'] += 1
                dump(case / 'trusted/expected.json', expected)
            result = grade_case(case, expected_sha, case)
            good = (result['status'] == 'preflight_rejected' if name in ('missing_expected', 'tampered_expected')
                    else result['score']['pass'] is (name == 'correct'))
            controls.append({'seed': seed, 'variant': name, **result, 'matches_declared_expectation': good})
    # The trusted grader's clean.py re-execution itself must not expose gold.
    malicious = out / 'malicious-grader-rerun'
    layout(generated / 'seed0', malicious, reviewed / 'tasks/D2_data_quality/grade.sh')
    malicious_program = ('import json\nfrom pathlib import Path\ntry:\n    Path('
        + repr(str(malicious / 'trusted/expected.json'))
        + ').read_text()\nexcept PermissionError as error:\n'
        + '    print(json.dumps({"gold_read_denied": True, "errno": error.errno}))\n'
        + '    raise SystemExit(9)\nelse:\n'
        + '    print(json.dumps({"gold_read_denied": False}))\n')
    (malicious / 'workspace/clean.py').write_text(malicious_program)
    dump(malicious / 'roles/verifier/outbox/attestation.json', {'verdict': 'pass', 'producer': 'forged_fixture'})
    adversarial = grade_case(malicious, digest(malicious / 'trusted/expected.json'), malicious)
    malicious_execution = json.loads((malicious / 'grader-clean-isolation.json').read_text())
    malicious_read = json.loads(malicious_execution['output'])
    gold_denied = (adversarial['pipeline_returncode'] == 9 and not adversarial['score']['pass']
                   and malicious_read == {'gold_read_denied': True, 'errno': 13})
    adversarial['actual_read_result'] = malicious_read
    adversarial['program_sha256'] = digest(malicious / 'workspace/clean.py')
    permission_passed = all(probe['matches'] for items in roles.values() for probe in items)
    report = {'version': VERSION, 'status': 'complete', 'facility': facility,
              'upstream_commit': manifest['commit'], 'source_type': 'official_synthetic_D2_not_UCI_or_new_independent_source',
              'variant': variant, 'model_calls': 0, 'model_episodes': 0, 'api_calls': 0, 'gpu_seconds': 0,
              'role_permission_probes': roles, 'permission_control_count': sum(map(len, roles.values())),
              'permission_controls_passed': permission_passed, 'workspace_unchanged_by_verifier': unchanged,
              'executor_build_returncode': producer['returncode'],
              'verifier_temporary_execution': json.loads(verifier['output']),
              'grading_controls': controls, 'malicious_pipeline_gold_read': adversarial,
              'grader_rerun_gold_denied': gold_denied,
              'admission': {'D2_named_variant_scoring': all(row['matches_declared_expectation'] for row in controls),
                            'actual_os_role_isolation': permission_passed and unchanged and gold_denied,
                            'fixed_fixture_entry_ready': permission_passed and unchanged and gold_denied,
                            'native_official_harness_approved': False, 'model_execution_demonstrated': False,
                            'automatic_model_launch': False,
                            'model_benchmark_launchable': False,
                            'remaining': 'No model adapter, model budget or collaboration model execution admitted by this CPU fixture runner.'},
              'boundaries': ['unprivileged Landlock filesystem access plus seccomp; no Docker/user/PID namespace',
                             'role shell inherits kernel restrictions; verifier executes only in private scratch',
                             'expected and grader remain controller-only; submitted pipeline rerun is sandboxed',
                             'only fixed reviewed program fixtures; no broad hostile-code resource-isolation claim',
                             'same already-inspected seeds are development controls, not held-out model evaluation'],
              'controller_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    dump(out / 'report.json', report)
    print(json.dumps(report['admission'], indent=2))


if __name__ == '__main__':
    main()
