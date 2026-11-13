# v203.2.2 公共测试部署接线修订

冻结 v203.2.1 选择了 v141 execution/evidence。其 sitecustomize 预加载 observer 后，又通过 PYTEST_PLUGINS 加载同模块；filterwarnings=error 将 PytestAssertRewriteWarning 升级为启动错误。已有 v175 修复将 pytest 插件导入延后，并给无测试断言的 observer 标记 PYTEST_DONT_REWRITE。此次显式继承 v175 launcher/library/execution/evidence 与原 v130 dependency helper，未改旧源文件。

新 manifest 固定所有五文件的 SHA-256、部署版本及 managed adapter；新 runtime inputs 以独立函数命名空间引用这些文件，保留原结果 schema，但要求新部署 manifest 与真实加载文件哈希一致。v141 回退即使具有相同结果 schema 也被拒绝。managed actor 独立绑定到受 manifest 检查的 v175 entry。

| 本地实际 pytest 控制 | 通过字段 | validation_status | exit |
| --- | --- | --- | ---: |
| old-v141-strict-warning | False | failed | 1 |
| pinned-v175-strict-warning | True | verified | 0 |
| real-assertion-failure | False | failed | 1 |
| real-project-warning | False | failed | 1 |
| nested-same-nodeid | True | verified | 0 |

旧入口：原本会通过的简单测试因 observer 重写警告启动失败。新入口：同一测试 verified；真正 assert 失败和项目警告仍失败。嵌套同名节点 test_local.py::test_collision 的外层通过、子会话失败分别保留，没有混加。旧 runtime 哈希被拒绝，旧命名空间未改变。

原始 stdout 与完整 result.json 位于各控制目录；staged-public-bundle 是此次实际加载的五文件副本，非运行中的部署。summary.json 保留源码散列、结果和限制。

## 适用范围

- Local synthetic pytest controls only; no original Astropy/pytest task reexecution or historical result rewrite.
- No real deployment, Docker, API, GPU, root, dependency installation or shared-host configuration changes.
- The v175 repair prevents observer assertion-rewrite warnings; project warnings and true failures remain failures.
- Same-nodeid nested sessions are distinguished in this fixture; this does not repair unexplained incomplete journals.
- pytest-5262 test-0004 remains unknown_collection: raw temporary journal was not retained, so missing session boundaries cannot be identified here.
- This is future-deployment source/manifest admission; a future full SDK bundle must explicitly include the new runtime inputs/helper, the pinned manifest and managed v175 adapter and aliases, then pass full deployment admission.
- No changes to test assertions, expected outcomes, framework warning policy or benchmark scoring semantics.

## 下一阶段接入

未来完整 SDK 打包需显式采用 software_benchmark_runtime_inputs_v203_2_2、software_benchmark_public_test_binding_v203_2_2.managed_actor()、config/v203-2-2-public-test-bundle.json 及该 manifest 列明的 v175 adapter/五文件别名。当前只是新目录中的部署材料及准入门；没有启动或改写既有部署。

复现需指定新的空目录：

```bash
.venv/bin/python tools/check_public_test_revision_v203_2_2.py --output artifacts/software-benchmark-v203-2-2/public-test-revision-r2
```
