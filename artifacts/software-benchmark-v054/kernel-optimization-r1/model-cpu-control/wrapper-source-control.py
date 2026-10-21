"""One CPU fixture with real files and functools.wraps; no GPU imports."""
import ast
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import tempfile


def reference(path):
    data = path.read_bytes()
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    # A real module filename becomes the code object's co_filename; no forged
    # __module__ or synthetic return from inspect is used.
    exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
    return module


source = Path('/tmp/v054-kernel-model-r1/src/proworksim/software_benchmark_kernel_diagnostic_v054.py')
assert reference(source)["sha256"] == "743759aea313b95310cf20d32d62e8d6645068037bd90b7691c689d963299294"
function = next(node for node in ast.parse(source.read_text()).body
                if isinstance(node, ast.FunctionDef) and node.name == "implementation")
namespace = {"inspect": inspect, "Path": Path}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
with tempfile.TemporaryDirectory(prefix='v054-real-wrapper-cpu-') as temporary:
    root = Path(temporary)
    overlay = root / 'overlay'
    overlay.mkdir()
    inner = overlay / 'kernel.py'
    outside = root / 'compiler_wrapper.py'
    inner.write_text('def kernel(value):\n    return value + 1\n')
    outside.write_text('''from functools import wraps

def wrap(target):
    @wraps(target)
    def compiler_wrapper(value):
        return target(value)
    return compiler_wrapper

def select(target):
    implementation, is_new_implementation = target, True
    @wraps(target)
    def dispatch(value):
        assert is_new_implementation
        return implementation(value)
    return dispatch
''')
    kernel = load('v054_fixture_kernel', inner)
    compiler = load('v054_fixture_compiler', outside)
    wrapped = compiler.wrap(kernel.kernel)
    assert wrapped.__module__ == kernel.kernel.__module__  # wraps copies metadata.
    assert inspect.getfile(wrapped) == str(outside)  # code still belongs outside.
    assert inspect.getsourcefile(inspect.unwrap(wrapped)) == str(inner)
    actual = namespace['implementation'](compiler.select(wrapped))
    assert actual['source'] == str(inner.resolve())
    assert actual['wrapper_source'] == str(outside.resolve())
    assert Path(actual['source']).is_relative_to(overlay)
    assert not Path(actual['wrapper_source']).is_relative_to(overlay)
    assert actual['optimized'] is True
    assert compiler.select(wrapped)(4) == 5
    evidence = {"real_inner_file": reference(inner), "real_wrapper_file": reference(outside),
                "inspection": actual, "copied_module_metadata_did_not_determine_source": True,
                "manual_module_spoofing": False}
receipt = {"version": "v054-kernel-wrapper-source-cpu-control-r1", "passed": True,
           "source": reference(source), "fixture": evidence, "fixture_count": 1,
           "GPU_operations": 0, "model_calls": 0, "mathematical_controls_repeated": 0,
           "operator_controls_repeated": 0,
           "scope": "Real functools.wraps wrapper outside overlay, unwrapped implementation inside overlay; tests source attribution only."}
Path(__file__).with_name('wrapper-source-control.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
