"""The real controller must use the tested finalizer, not an unused helper."""
import ast
from pathlib import Path

def test_actual_main_finally_uses_only_the_budget_safe_finalizer():
    source=Path(__file__).resolve().parents[1]/'tools/run_communication_controller_v159.py'
    main=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='main')
    blocks=[n for n in ast.walk(main) if isinstance(n,ast.Try) and n.finalbody]
    final=next(n.finalbody for n in blocks if any(isinstance(s,ast.ImportFrom) and s.module=='proworksim.software_benchmark_finalization_v159' for s in n.finalbody))
    calls=[n for s in final for n in ast.walk(s) if isinstance(n,ast.Call)]
    assert len(calls)==1 and isinstance(calls[0].func,ast.Name) and calls[0].func.id=='finalize_controller'
    assert {k.arg for k in calls[0].keywords}=={'runtime','close_runtime','owner','transport'}
