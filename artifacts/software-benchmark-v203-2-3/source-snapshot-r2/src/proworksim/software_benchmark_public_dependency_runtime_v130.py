"""Load the identical stdlib dependency helper before actor package sealing."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys

_source = (Path('/opt/pws-runtime/public-test-dependencies.py')
           if Path(__file__).resolve().is_relative_to('/opt/pws-runtime')
           else Path(__file__).resolve().parents[2]/'tools/public_test_dependencies_v130.py')
_spec = importlib.util.spec_from_file_location('_pws_public_dependency_runtime_v130', _source)
if _spec is None or _spec.loader is None:
    raise ImportError('The exact public dependency helper is unavailable')
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
VERSION = _module.VERSION
TASK = _module.TASK
validate_descriptor = _module.validate_descriptor
effective_test_environment = _module.effective_test_environment
