"""Read-only r1 metadata once per interpreter; no worker/SDK/tokenizer/model calls."""
import ast
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys

PROJECT = Path('/data1/zhuxinrui/projects/ProWorkSim')
ROOT = PROJECT / 'runs/software-bridge-v052-resume-r1'
SOURCE = ROOT / 'source'
sys.path[:0] = [str(SOURCE / 'src'), str(SOURCE)]
from scripts import software_bridge_v052_resume as resume

def reference(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

def canonical(node):
    if isinstance(node, ast.AST):
        return [type(node).__name__, {name: canonical(value) for name, value in ast.iter_fields(node)
                                    if value is not None and value != []}]
    if isinstance(node, list):
        return [canonical(value) for value in node]
    return node

plan = json.loads((ROOT / 'plan.json').read_text())
actual = resume.algorithm_binding()[2]
source = inspect.getsource(resume.bridge.original_host.supervise)
tree = ast.parse(source)
for node in ast.walk(tree):
    if isinstance(node, ast.Constant) and node.value == 'scripts.software_calibration_v051_cal2':
        node.value = resume.MODULE
ast.fix_missing_locations(tree)
serialized = json.dumps(canonical(tree), sort_keys=True, separators=(',', ':'))
record = {'version': 'v052-r1-binding-readonly-probe-v1', 'executable': sys.executable,
    'python': sys.version, 'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
    'plan': reference(ROOT / 'plan.json'), 'frozen_host': reference(resume.__file__),
    'frozen_supervisor': reference(resume.bridge.original_host.__file__),
    'expected': plan['supervisor_adaptation'], 'actual': actual,
    'different_fields': {key: {'plan': plan['supervisor_adaptation'].get(key), 'actual': actual.get(key)}
                         for key in sorted(set(actual) | set(plan['supervisor_adaptation']))
                         if actual.get(key) != plan['supervisor_adaptation'].get(key)},
    'ast_dump': ast.dump(tree, include_attributes=False),
    'ast_dump_show_empty_signature_supported': 'show_empty' in inspect.signature(ast.dump).parameters,
    'canonical_ast': canonical(tree), 'canonical_sha256': hashlib.sha256(serialized.encode()).hexdigest(),
    'sdk_or_torch_imported': [name for name in sys.modules if name == 'torch' or name.startswith('openhands')],
    'worker_or_frozen_called': False, 'model_calls': 0, 'tokenizer_calls': 0}
print(json.dumps(record, sort_keys=True))
