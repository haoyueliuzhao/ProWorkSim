"""Real OS controls, no models, GPU, daemon changes or network calls."""
import json

import pytest

from proworksim.teambench_isolation_v022 import facility_probe, role_profile, run_role


def fixture_root(tmp_path):
    root = tmp_path.resolve() / 'd2'
    for directory in ['public', 'trusted', 'workspace/data/input', 'workspace/data/output',
                      *[f'roles/{role}/{leaf}' for role in ('planner', 'executor', 'verifier')
                        for leaf in ('private', 'scratch', 'outbox', 'inbox')]]:
        (root / directory).mkdir(parents=True)
    (root / 'public/brief.md').write_text('public fixture')
    (root / 'workspace/clean.py').write_text('print("fixture")\n')
    (root / 'workspace/data/input/records.csv').write_text('id,name,score,department\n1,x,1,x\n')
    (root / 'trusted/expected.json').write_text('{"private":"gold fixture"}')
    for role in ('planner', 'verifier'):
        (root / f'roles/{role}/private/spec.md').write_text('private public-contract fixture')
    return root


def test_actual_role_shell_and_symlink_operations_remain_os_restricted(tmp_path):
    if not facility_probe()['available']:
        pytest.skip('Landlock ABI>=3 plus libseccomp required; no Python-only substitute')
    root = fixture_root(tmp_path)
    code = r'''
import json,os,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]);role=sys.argv[2];scratch=root/'roles'/role/'scratch'
target=root/'trusted/expected.json';link=scratch/'gold-link';link.symlink_to(target)
results={}
for name,path in [('direct',target),('symlink',link),('traversal',scratch/'../../../trusted/expected.json')]:
    try:path.read_text();results[name]=None
    except OSError as error:results[name]=error.errno
results['shell_read']=subprocess.run(['/usr/bin/bash','-c','cat '+str(target)],capture_output=True).returncode
if role=='verifier':
    results['shell_write']=subprocess.run(['/usr/bin/bash','-c','printf bad > '+str(root/'workspace/clean.py')],capture_output=True).returncode
    (scratch/'verify.txt').write_text((root/'workspace/clean.py').read_text())
else:
    results['allowed_pipeline_write']=(root/'workspace/clean.py').write_text('print("fixture")\n')>0
print(json.dumps(results))
'''
    for role in ('executor', 'verifier'):
        result = run_role(root, role, ['/usr/bin/python3', '-I', '-S', '-c', code, str(root), role],
                          log=tmp_path / f'{role}.json')
        assert result['isolation']['filesystem'] == 'kernel_landlock_allowlist'
        assert result['returncode'] == 0 and not result['timeout']
        observed = json.loads(result['output'])
        assert all(observed[name] == 13 for name in ('direct', 'symlink', 'traversal'))
        assert observed['shell_read'] != 0
        if role == 'verifier':
            assert observed['shell_write'] != 0
            assert (root / 'roles/verifier/scratch/verify.txt').read_text() == 'print("fixture")\n'
        else:
            assert observed['allowed_pipeline_write']
    assert (root / 'workspace/clean.py').read_text() == 'print("fixture")\n'
    assert (root / 'trusted/expected.json').read_text() == '{"private":"gold fixture"}'


def test_replaced_grant_file_is_rejected_before_kernel_allowlist(tmp_path):
    root = fixture_root(tmp_path)
    (root / 'workspace/clean.py').unlink()
    (root / 'workspace/clean.py').symlink_to(root / 'trusted/expected.json')
    with pytest.raises(ValueError, match='canonical path'):
        role_profile(root, 'executor')
