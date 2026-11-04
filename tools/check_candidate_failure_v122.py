"""Verify preserved patch application and parser classification without Docker."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
    HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')


def main():
    from proworksim import software_benchmark_candidate_failure_v122 as repair
    from proworksim.software_benchmark_candidates_v054 import _git, checked, reference, write_new
    from proworksim.software_benchmark_native_artifact_v054 import decode_native_entry
    from proworksim.storage import digest
    from swebench.harness import grading as official
    from swebench.harness.log_parsers.python import MAP_REPO_TO_PARSER_PY
    root = Path(__file__).resolve().parents[1]
    output = root/'artifacts/software-benchmark-v122/pylint-patch-repair-r1'
    output.mkdir(parents=True, exist_ok=False)
    forbidden, git_calls = [], []
    with tempfile.TemporaryDirectory(prefix='pws-v122-locked-patch-') as temporary:
        scratch = Path(temporary).resolve()
        def audit(event, args):
            if event in {'socket.connect', 'socket.bind', 'socket.sendto', 'socket.getaddrinfo',
                         'os.system', 'os.fork', 'os.posix_spawn'}:
                forbidden.append(event)
                raise AssertionError('No network, Docker or unrestricted process in CPU adjudication')
            if event == 'subprocess.Popen':
                executable, argv, cwd, env = args
                if (executable not in ('/bin/git', '/usr/bin/git') or Path(cwd).resolve() != scratch
                        or argv[1:9] != ['-c', 'core.hooksPath=/dev/null', '-c', 'core.attributesFile=/dev/null',
                            '-c', 'core.autocrlf=false', '-c', 'core.filemode=true']
                        or argv[9] not in ('init', 'apply') or env.get('GIT_CONFIG_GLOBAL') != '/dev/null'):
                    forbidden.append(event)
                    raise AssertionError('Only this isolated scratch git init/apply is permitted')
                git_calls.append(argv[9])
        sys.addaudithook(audit)
        folder = root/'runs/software-benchmark-v118/project-repaired-r1/grading-v120/score-8039'
        request_ref = reference(folder/'request.json')
        request = repair.load(request_ref)
        receipt = repair.load(reference(folder/'receipt.json'))
        lock = repair.load(request['candidate_lock'])
        baseline, candidate = repair.load(lock['baseline']), repair.load(lock['candidate'])
        before = decode_native_entry(repair.PATH, baseline['files'][repair.PATH], baseline['entry_metadata'][repair.PATH])
        after = decode_native_entry(repair.PATH, candidate['files'][repair.PATH], candidate['entry_metadata'][repair.PATH])
        patch = checked(lock['patch_receipt']['patch'])
        assert digest(patch.read_bytes()) == repair.PATCH_SHA256
        target = scratch/repair.PATH
        target.parent.mkdir(parents=True)
        target.write_bytes(before)
        target.chmod(0o644)
        _git(scratch, ['init', '--quiet', '--template='])
        _git(scratch, ['apply', '--binary', '--', str(patch)])
        applied = target.read_bytes()
        # Git 100644 describes a non-executable blob; local umask may remove
        # group/other read bits without changing the versioned file mode.
        assert applied == after and target.stat().st_mode & 0o111 == 0
        missing = repair.missing_binding_evidence(before.decode('utf-8'), after.decode('utf-8'))
        logs = folder/'official-output/logs/run_evaluation'/receipt['run_id']/request['resource_key']/repair.TASK
        assert (logs/'patch.diff').read_bytes() == patch.read_bytes()
        # Use the installed public repository parser registry. No test patch,
        # reference repair or F2P/P2P labels are read to construct this object.
        parser = MAP_REPO_TO_PARSER_PY['pylint-dev/pylint']
        parser_name = parser.__name__
        assert official.PARSER_REGISTRY[parser_name] is parser
        status_map, found = official.get_logs_eval(SimpleNamespace(log_parser=parser_name), str(logs/'test_output.txt'))
        assert status_map == {} and found is False
        def blob_id(data):
            return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        before_blob, after_blob = blob_id(before), blob_id(after)
        assert ('index '+before_blob+'..'+after_blob+' 100644').encode() in patch.read_bytes()
        proof = {'version': repair.VERSION, 'passed': True, 'request': request_ref,
            'candidate_lock': request['candidate_lock'], 'original_patch': lock['patch_receipt']['patch'],
            'baseline_snapshot': lock['baseline'], 'candidate_snapshot': lock['candidate'],
            'exact_patch_application_verified': True, 'candidate_bytes_changed': False,
            'baseline_file_sha256': digest(before), 'candidate_file_sha256': digest(after),
            'applied_file_sha256': digest(applied), 'baseline_git_blob': before_blob, 'candidate_git_blob': after_blob,
            'applied_versioned_file_mode': '100644', 'scratch_permissions_octal': oct(target.stat().st_mode & 0o777),
            'same_grader_patch_bytes': True, 'git_commands': git_calls,
            'missing_binding': missing, 'official_no_parseable_tests_reproduced': True,
            'official_log': reference(logs/'test_output.txt'), 'official_parser_name': parser_name,
            'official_parser_source': reference(official.__file__),
            'official_parser_status_map': status_map, 'official_parser_found': found,
            'trusted_test_patch_or_gold_read': False, 'model_calls': 0, 'Docker_operations': 0,
            'official_tests_executed': 0, 'network_connections': 0, 'forbidden_attempts': forbidden,
            'source': reference(__file__), 'adjudicator_source': reference(repair.__file__)}
        proof_ref = write_new(output/'cpu-proof.json', proof)
        derived = repair.derive_resolution(request_ref, proof_ref)
        resolution_ref = write_new(output/'derived-resolution.json', derived)
        assert not forbidden and git_calls == ['init', 'apply']
    (output/'explanation.md').write_text('''# Pylint4604 未定原因修订

原解释“补丁应用失败”不正确。官方日志记录补丁干净应用，传入 patch.diff 与锁定候选完全相同；离线将同一补丁应用到原文件，结果也逐字等于锁定候选。

模型把 pylint/checkers/variables.py 从 2,152 行改成 32 行，删除 import re，却保留第 30 行 re.compile。正式 pytest 加载 conftest 时因此出现 NameError，测试未能收集。CPU 仅对同一字面量表达式复现缺少 re 绑定的错误，没有在宿主执行任务模块或测试。

官方评分器把“没有可解析测试输出”也编码为 patch_successfully_applied=false；原报告本身已经 resolved=false、infra_failure=false。旧外层因此误把确定的候选代码错误列为技术未知。

新 derived-resolution.json 仅修订测量分类为候选代码失败（resolved=false）；原 receipt、官方 report 和补丁均不改。无需修补模型答案、无需新 gold/empty 环境控制，也无需重新运行候选评分或模型。这是单独留档的证据裁定，不冒称新增官方评分。
''')
    print(json.dumps({'passed': True, 'derived_resolution': resolution_ref,
        'new_candidate_scoring_needed': False, 'Docker_operations': 0}))


if __name__ == '__main__':
    main()
