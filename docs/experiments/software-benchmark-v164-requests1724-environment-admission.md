# Requests1724 环境修复及专属准入说明

Requests1724 的参考补丁现已通过官方评分；空白补丁未通过。两次控制均完成有界真实 httpbin 通道和容器清理，原任务 Python2、官方测试、候选补丁和官方 `resolved` 计算未改变。生效的是评分侧环境修订，以及仅针对这道题的额外准入门解释。

| 独立修订 | 实际新容器 | 观察及处理 |
| --- | ---: | --- |
| v158 | 2 | 新探针错误地用 `/sys/class/net` 挂载视图判断网络命名空间；控制在官方测试前停止，两容器清理完成，relay 未开始出网。 |
| v160 | 1 | 改用 `socket.if_nameindex` 与 `/proc/self/net/route` 后真实网络恢复；gold 的六个 FAIL_TO_PASS 全通过，只剩旧 CA 的 HTTPS 校验失败。官方 cleanup 使用 Docker CLI，绕过 wrapper 方法，导致晚于删除的 CA 读回失败；保留原错误，并通过精确容器 ID 的404证明补充清理。未运行该版 empty。 |
| v162 | 2 | 评分侧追加冻结的当前可信公共 CA，保留源与安装位置的原 CA 文件、证书要求和主机名校验；采用实际 evaluator 私有 namespace 的清理钩子，在官方 CLI 删除前完成 relay 和 CA 读回。gold `resolved=true`，empty `resolved=false`，两容器均正常清理。 |
| v164 | 0 | 只读验证原控制证据，对本题“empty 必须有 F2P 失败”的额外准入条件作明确例外；没有重新评分。 |

上述独立修复链合计五个实际容器，已全部物理清理。v160 原 `quiescent=false` 记录没有被覆盖，其404补充证据单独保留。未使用模型 API 或 GPU，未修改共享主机配置。更早的 v157 环境尝试不包含在此五个容器中。

## 为什么还需要专属准入解释

原官方数据将新增回归测试 `test_requests.py::RequestsTestCase::test_unicode_method_name` 归在 `PASS_TO_PASS`。在当前可信环境中：

- gold 的 F2P、P2P 全部通过，官方 `resolved=true`。
- empty 的六个 F2P 也全部通过，但新增 Unicode 方法测试发生原 Python2.7 `httplib` 的 `UnicodeDecodeError`，官方 `resolved=false`。

旧项目准入器另外要求“empty 必须至少有一个 F2P 失败”，因此拒绝这一对已经能区分正确修复与空白补丁的实际控制。现在只对1724取消这个额外假设，要求差异精确来自官方 `test_patch` 新增的上述回归测试，同时继续核验相同镜像、基线、测试、网络、CA及清理。

**没有改写 F2P/P2P 列表，没有重分类任何测试，没有修改官方测试或官方评分，也没有放宽模型通过条件。** 当前证据说明该官方分组与这次实际回归差异不一致；造成这种分组的历史原因未进一步验证，不据此作更广泛推断。

完整原列表及各自SHA、完整 `test_patch` SHA、新增定义所在行、gold/empty原报告、输出、身份、transport及清理引用见：

- `artifacts/software-benchmark-v164/requests1724-qualification-r1/discrepancy-evidence.json`
- `artifacts/software-benchmark-v164/requests1724-qualification-r1/qualified-overlay.json`
- `artifacts/software-benchmark-v164/requests1724-final-r1/summary.json`

## 接入后续候选评分

`software_benchmark_requests1724_qualification_v164.py` 提供只读 `validate_qualification(ref, config, plan_ref)`，严格绑定同一任务、镜像、数据集、基线和评分输入。它不授予 Docker 或出网权限，不覆盖旧 v162 准入拒绝记录。

`software_benchmark_requests1724_binding_v165.py` 为新候选 scope 提供行政绑定桥：

```python
environment = environment_for(
    candidate_policy,
    scope_ref=reference(candidate_policy.__file__),
    directory=candidate_binding_directory,
)
fields = environment.request_fields("psf__requests-1724")
proof = verify_qualified_reuse(fields["environment_revision"], candidate_config)
```

桥明确复用 v162 原 scope 下已经执行的端点探测，不伪装成新 DNS 或新网络探测。新环境 manifest 只允许 `scope`、`network_resolution`、`resolution_source` 三个行政引用不同，其余 provider、CA、权限、测试和单容器限额必须完全一致。新实际 relay 授权调用传入的候选 policy，不重开已消费的 v162 控制授权。

候选 policy 必须显式限定仅1724最多六个评分 session（3个code及最多3个不同树delivery），每 session 512连接／64MiB，合计3072连接／384MiB。两个控制报告只是环境资格，不能复用为候选分数；候选仍使用自己的补丁、run ID及官方评分。

新私有 scorer 的 `_score`、`Containers.create`、`validate_attrs` 必须引用同一个新 router，随后可调用 `bind_qualification(existing_private_scorer)` 绑定 v164 overlay。该函数会拒绝未一致接线的 namespace，不修改任何已运行模块或旧源码。`environment.__file__` 记录新 v165 router，`environment.tls.__file__` 仍记录实际通过控制的 v162 provider，两者在正式 manifest 中分别保留。

验证包含：v162 九项 CPU 控制与实际 gold/empty；v164 七项准入反例检查；v165 四项复用桥检查，并对 router/provider 来源标识作一项定向复核。v164/v165 均无新网络、容器或模型调用。
