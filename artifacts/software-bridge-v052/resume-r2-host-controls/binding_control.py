"""One added cross-interpreter AST binding control; no old tests or model entry."""
import ast
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys

PROJECT = Path('/data1/zhuxinrui/projects/ProWorkSim')
FROZEN = PROJECT / 'runs/software-bridge-v052-resume-r1/source'
sys.path[:0] = [str(FROZEN / 'src'), str(FROZEN)]
PATH = PROJECT / 'scripts/software_bridge_v052_resume_r2.py'
spec = importlib.util.spec_from_file_location('scripts.software_bridge_v052_resume_r2', PATH)
resume = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resume)

def reference(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

def encoded(tree):
    return json.dumps(resume.canonical_ast(tree), sort_keys=True, separators=(',', ':')).encode()

metadata = resume.algorithm_binding()[2]
source = inspect.getsource(resume.bridge.original_host.supervise)
tree = ast.parse(source)
replacements = 0
for node in ast.walk(tree):
    if isinstance(node, ast.Constant) and node.value == 'scripts.software_calibration_v051_cal2':
        node.value = resume.MODULE
        replacements += 1
# Nonempty content changes must still change the structural digest.
left, right = ast.parse('worker = 1'), ast.parse('worker = 2')
checks = {
    'exact_original_supervisor_source': metadata['supervisor_source_sha256'] == 'c1b480fe0b0d8c91fd942f917682d8db442610c34ad54ce8b6af81f4e0b467f7',
    'canonical_encoding_version_bound': metadata['supervisor_AST_encoding'] == 'nonempty-fields-json-v1',
    'binding_matches_canonical_tree': metadata['supervisor_AST_sha256'] == hashlib.sha256(encoded(tree)).hexdigest(),
    'one_worker_module_replacement': replacements == metadata['changed_worker_module_literals'] == 1,
    'nonempty_change_detected': encoded(left) != encoded(right),
    'cuda_disabled': os.environ.get('CUDA_VISIBLE_DEVICES') == '',
    'no_sdk_or_torch_imported': not any(name == 'torch' or name.startswith('openhands') for name in sys.modules),
}
record = {'version': 'v052-r2-cross-interpreter-binding-control-v1', 'passed': all(checks.values()),
    'python': sys.version, 'executable': sys.executable, 'checks': checks,
    'host_source': reference(PATH), 'original_supervisor': reference(resume.bridge.original_host.__file__),
    'binding': metadata, 'canonical_AST_sha256': hashlib.sha256(encoded(tree)).hexdigest(),
    'worker_or_frozen_called': False, 'new_model_calls': 0, 'new_tokenizer_calls': 0,
    'old_control_reruns': 0, 'source_or_initial_input_requalifications': 0}
print(json.dumps(record, sort_keys=True))
if not record['passed']:
    raise SystemExit(1)
