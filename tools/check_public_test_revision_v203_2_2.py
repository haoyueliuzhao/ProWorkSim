"""Actual local pytest controls for the pinned v203.2.2/v175 public-test binding.

No Docker, model, network, system installation or active deployment is used.
The inherited execution helper only terminates its own newly created group.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from proworksim import software_benchmark_public_test_binding_v203_2_2 as binding
from proworksim import software_benchmark_runtime_inputs_v203_2_2 as runtime


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def main(output):
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    output.mkdir(parents=True, exist_ok=False)
    staged = output / "staged-public-bundle"
    staged_proof = binding.stage_bundle(staged)
    repaired = binding.staged_execution(staged)
    old_path = ROOT / "artifacts/software-benchmark-v203-2-1/continuation-r4/source-snapshot/tools/public_test_execution_v141.py"
    spec = importlib.util.spec_from_file_location("frozen_v203_2_1_public_execution", old_path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTEST_PLUGINS": "",
           "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
           "MKL_NUM_THREADS": "1", "CUDA_VISIBLE_DEVICES": "", "PYTHONPATH": ""}
    controls = {}

    def case(name, code, execute):
        folder = output / name
        folder.mkdir()
        (folder / "pytest.ini").write_text("[pytest]\nfilterwarnings = error\n")
        (folder / "test_local.py").write_text(code)
        result = execute({"argv": [sys.executable, "-m", "pytest", "-q", "test_local.py"]},
                         root=folder, environment=env, timeout_seconds=15)
        save(folder / "result.json", result)
        (folder / "stdout.txt").write_text(result["output"])
        controls[name] = {key: result[key] for key in
                          ("passed", "validation_status", "returncode", "counts", "wall_seconds")}
        return result

    passing = "def test_real(): assert 1 + 1 == 2\n"
    before = case("old-v141-strict-warning", passing, old.execute_public_entry)
    assert not before["passed"] and "PytestAssertRewriteWarning" in before["output"]
    assert before["returncode"] != 0
    after = case("pinned-v175-strict-warning", passing, repaired.execute_public_entry)
    assert after["passed"] and after["validation_status"] == "verified" and after["counts"]["passed"] == 1
    assert after["deployment_revision"] == binding.manifest()["deployment_revision"]
    failed = case("real-assertion-failure", "def test_real(): assert False, 'real assertion failure'\n", repaired.execute_public_entry)
    assert not failed["passed"] and failed["counts"]["failed"] == 1 and failed["returncode"] == 1
    warned = case("real-project-warning", "import warnings\ndef test_real(): warnings.warn('actual project warning')\n", repaired.execute_public_entry)
    assert not warned["passed"] and warned["counts"]["failed"] == 1 and "actual project warning" in warned["output"]
    nested = case("nested-same-nodeid", '''import os
import pytest
def test_collision(monkeypatch):
    if os.environ.get("PWS_SYNTHETIC_CHILD") == "1":
        assert False, "expected child failure"
    monkeypatch.setenv("PWS_SYNTHETIC_CHILD", "1")
    assert pytest.main(["-q", __file__]) == 1
''', repaired.execute_public_entry)
    assert nested["passed"] and nested["counts"]["passed"] == 1 and nested["counts"]["failed"] == 0
    sessions = nested["test_evidence"]["sessions"]
    roots = [s for s in sessions if s["root"]]
    children = [s for s in sessions if not s["root"]]
    assert len(roots) == len(children) == 1 and children[0]["counts"]["failed"] == 1
    root_nodes = {r["nodeid"] for r in roots[0]["test_reports"]}
    child_nodes = {r["nodeid"] for r in children[0]["test_reports"]}
    assert root_nodes == child_nodes == {"test_local.py::test_collision"}
    controls["nested-same-nodeid"]["same_nodeid_different_sessions"] = True
    controls["nested-same-nodeid"]["child_counts"] = children[0]["counts"]

    old_hashes = {key: hashlib.sha256(path.read_bytes()).hexdigest()
                  for key, path in runtime.original.PUBLIC_FILES.items()}
    try:
        binding.admit_loaded_hashes(old_hashes)
    except ValueError as error:
        controls["old-runtime-hashes-rejected"] = {"passed": True, "reason": str(error)}
    else:
        raise AssertionError("Old v141 files were admitted")
    current_hashes = {key: hashlib.sha256(path.read_bytes()).hexdigest()
                      for key, path in runtime.PUBLIC_FILES.items()}
    assert binding.admit_loaded_hashes(current_hashes)["manifest_sha256"] == binding.MANIFEST_SHA256
    assert runtime.original.PUBLIC_FILES["public_test_execution_sha256"].name == "public_test_execution_v141.py"
    actor = binding.managed_actor()
    assert actor.ManagedOperationSession.execute.__globals__["run_public_entry"] is binding.run_public_entry
    assert runtime.original.RESULT_REVISION == runtime.RESULT_REVISION
    # A schema label is intentionally insufficient; exact implementation hashes
    # reject a v141 rollback even though both retain the same result schema.
    controls["isolated-managed-and-runtime-binding"] = {"passed": True,
        "original_runtime_still_v141": True, "new_managed_entry_guarded": True,
        "result_schema_unchanged": True, "public_bundle_sha256": binding.MANIFEST_SHA256}
    inputs = [Path(__file__), binding.MANIFEST, Path(binding.__file__), Path(runtime.__file__),
              old_path, old.helper_path()]
    summary = {"version": binding.VERSION, "status": "local_pytest_controls_passed",
               "python": sys.version, "pytest_version": __import__("pytest").__version__,
               "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
               "bundle_admission": staged_proof, "controls": controls,
               "limitations": [
                   "Local synthetic pytest controls only; no original Astropy/pytest task reexecution or historical result rewrite.",
                   "No real deployment, Docker, API, GPU, root, dependency installation or shared-host configuration changes.",
                   "The v175 repair prevents observer assertion-rewrite warnings; project warnings and true failures remain failures.",
                   "Same-nodeid nested sessions are distinguished in this fixture; this does not repair unexplained incomplete journals.",
                   "pytest-5262 test-0004 remains unknown_collection: raw temporary journal was not retained, so missing session boundaries cannot be identified here.",
                   "This is future-deployment source/manifest admission; a future full SDK bundle must explicitly include the new runtime inputs/helper, the pinned manifest and managed v175 adapter and aliases, then pass full deployment admission.",
                   "No changes to test assertions, expected outcomes, framework warning policy or benchmark scoring semantics.",
               ]}
    save(output / "summary.json", summary)
    lines = ["# v203.2.2 公共测试部署接线修订", "",
             "冻结 v203.2.1 选择了 v141 execution/evidence。其 sitecustomize 预加载 observer 后，又通过 PYTEST_PLUGINS 加载同模块；filterwarnings=error 将 PytestAssertRewriteWarning 升级为启动错误。已有 v175 修复将 pytest 插件导入延后，并给无测试断言的 observer 标记 PYTEST_DONT_REWRITE。此次显式继承 v175 launcher/library/execution/evidence 与原 v130 dependency helper，未改旧源文件。", "",
             "新 manifest 固定所有五文件的 SHA-256、部署版本及 managed adapter；新 runtime inputs 以独立函数命名空间引用这些文件，保留原结果 schema，但要求新部署 manifest 与真实加载文件哈希一致。v141 回退即使具有相同结果 schema 也被拒绝。managed actor 独立绑定到受 manifest 检查的 v175 entry。", "",
             "| 本地实际 pytest 控制 | 通过字段 | validation_status | exit |", "| --- | --- | --- | ---: |"]
    for name, result in controls.items():
        if "validation_status" in result:
            lines.append(f"| {name} | {result['passed']} | {result['validation_status']} | {result['returncode']} |")
    lines.extend(["", "旧入口：原本会通过的简单测试因 observer 重写警告启动失败。新入口：同一测试 verified；真正 assert 失败和项目警告仍失败。嵌套同名节点 test_local.py::test_collision 的外层通过、子会话失败分别保留，没有混加。旧 runtime 哈希被拒绝，旧命名空间未改变。", "",
                  "原始 stdout 与完整 result.json 位于各控制目录；staged-public-bundle 是此次实际加载的五文件副本，非运行中的部署。summary.json 保留源码散列、结果和限制。", "", "## 适用范围", ""])
    lines.extend("- " + item for item in summary["limitations"])
    lines.extend(["", "## 下一阶段接入", "", "未来完整 SDK 打包需显式采用 software_benchmark_runtime_inputs_v203_2_2、software_benchmark_public_test_binding_v203_2_2.managed_actor()、config/v203-2-2-public-test-bundle.json 及该 manifest 列明的 v175 adapter/五文件别名。当前只是新目录中的部署材料及准入门；没有启动或改写既有部署。", "",
                  "复现需指定新的空目录：", "", "```bash", ".venv/bin/python tools/check_public_test_revision_v203_2_2.py --output artifacts/software-benchmark-v203-2-2/public-test-revision-r2", "```", ""])
    (output / "README.md").write_text("\n".join(lines))
    print(json.dumps({"status": summary["status"], "output": str(output), "controls": len(controls)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/software-benchmark-v203-2-2/public-test-revision-r1")
    args = parser.parse_args()
    main(args.output.resolve())
