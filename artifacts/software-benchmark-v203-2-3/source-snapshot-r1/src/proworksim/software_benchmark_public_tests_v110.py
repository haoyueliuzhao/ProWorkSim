"""Load the single public stdlib selection library in the source tree or bundle."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

_here = Path(__file__).resolve()
if _here.is_relative_to(Path('/opt/pws-runtime')):
    _source = Path('/opt/pws-runtime/public-test-library.py')
else:
    _source = _here.parents[2] / 'tools/public_test_library_v110.py'
_name = '_proworksim_public_tests_v110'
_module = sys.modules.get(_name)
if _module is None:
    _spec = importlib.util.spec_from_file_location(_name, _source)
    if _spec is None or _spec.loader is None:
        raise ImportError('The exact public test library has not been installed')
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _module
    _spec.loader.exec_module(_module)
for _key, _value in vars(_module).items():
    if not _key.startswith('_'):
        globals()[_key] = _value
