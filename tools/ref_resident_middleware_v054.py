"""Load the stdlib-only REF ASGI gate without importing the project package."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

_source = Path(__file__).resolve().parents[1] / "src/proworksim/software_benchmark_ref_resident_v054.py"
_name = "pws_v054_ref_resident_asgi"
_spec = importlib.util.spec_from_file_location(_name, _source)
if _spec is None or _spec.loader is None:
    raise ImportError("The pinned REF session gate is unavailable")
_module = importlib.util.module_from_spec(_spec)
sys.modules[_name] = _module
_spec.loader.exec_module(_module)
RefSessionGate = _module.RefSessionGate

__all__ = ["RefSessionGate"]
