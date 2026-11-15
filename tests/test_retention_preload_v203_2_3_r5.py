import os
import shutil
import sys
from pathlib import Path
import pytest
from proworksim import software_public_test_retention_v203_2_3 as old
from proworksim import software_public_test_retention_v203_2_3_r5 as new


def prepared(tmp_path, monkeypatch, module):
    root = tmp_path/'private-project'
    (root/'tools').mkdir(parents=True)
    source = Path(__file__).resolve().parents[1]/'tools'
    for name in ('public_test_execution_v175.py','public_test_evidence_v175.py'):
        shutil.copyfile(source/name, root/'tools'/name)
    monkeypatch.setattr(module,'__file__',str(root/'src/proworksim/retention.py'))
    binding={'source_reference':{'object_id':'fixture','version_id':'v1'},'candidate_tree_sha256':'a'*64}
    return root,binding


def test_original_implicit_explicit_none_cache_miss(tmp_path, monkeypatch):
    old.load_base.cache_clear()
    root,binding=prepared(tmp_path,monkeypatch,old)
    old.load_base()
    shutil.rmtree(root/'tools')
    with pytest.raises(FileNotFoundError):
        old.retaining_executor(tmp_path/'journals',binding=binding)
    old.load_base.cache_clear()


def test_repaired_executor_after_source_removal(tmp_path, monkeypatch):
    new._load_base_cached.cache_clear()

    root,binding=prepared(tmp_path,monkeypatch,new)
    preloaded=new.load_base()
    shutil.rmtree(root/'tools')
    assert new.load_base(None) is preloaded
    assert new.load_base(root) is preloaded
    project=tmp_path/'testbed';project.mkdir()
    (project/'pytest.ini').write_text('[pytest]\nfilterwarnings = error\n')
    (project/'test_probe.py').write_text('def test_probe():\n    assert True\n')
    execute=new.retaining_executor(tmp_path/'journals',binding=binding)
    result=execute({'argv':[sys.executable,'-m','pytest','-q','test_probe.py']},root=project,environment=dict(os.environ),timeout_seconds=30)
    assert result['passed'] and result['validation_status']=='verified'
    assert len(list((tmp_path/'journals').glob('*/framework-journal.jsonl')))==1
    new._load_base_cached.cache_clear()


def test_dead_actor_transfer_stops_before_next_model_opportunity():
    import ast
    from types import SimpleNamespace
    source=Path(__file__).resolve().parents[1]/'tools/run_role_context_controller_v203_2_3_r5.py'
    tree=ast.parse(source.read_text())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='guard_actor_transfer')
    namespace={}
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),namespace)
    guard=namespace['guard_actor_transfer']
    guard(SimpleNamespace(failed=False,closed=False))
    for state in ((True,False),(False,True)):
        with pytest.raises(RuntimeError,match='before another model call'):
            guard(SimpleNamespace(failed=state[0],closed=state[1]))
