# v090 REF 控制器接入：CPU 验证完成，生产入口未安装

新增独立 [控制器会话工厂](../../src/proworksim/software_benchmark_ref_controller_v090.py)，已将简化提示、公开执行反馈和无动作截断处理接到**真实 OpenHands SDK 调用链**，不再只是未使用的辅助函数。现有 v064—v089 运行文件没有改动。本入口仅接受带有明确脚本化标识的 CPU 依赖，不提供真实评测启动参数。

真实路径为：v090 公开提示 → v090 反馈 RPC → 原期限门及模型账本 → v090 截断守卫 → 原 v057 投影与 SDK 会话 → 控制器终态。反馈 RPC 仍先保存原始观察，不拦命令或增加执行；同一 Agent 和摘要器共用原账本。

## 已验证的调用链

3项必要测试通过，耗时10.97秒，Ruff通过，见[验证记录](../../artifacts/software-benchmark-v090/ref-controller-CPU-validation-r1/validation.json)。其中一项在现有冻结 SDK 上执行以下4种完整会话；全部响应与工具结果均由脚本提供，真实模型、API、GPU、容器、仓库命令和评分调用为0。

| 场景 | 实际验证 | 控制器终态 |
| --- | --- | --- |
| 公开反馈后纯思考截断 | 首次输入包含新提示；ImportError 说明进入第二次输入；重复公开测试摘要说明进入第四次输入；第四次响应完整结算后停止，没有通用空动作纠正 | `closed`，`settled_output_truncation`；`native_finished=false` |
| 原生正常完成 | 原生 `finish` 后仅有一次 v090 完成自检，第二次输入包含新自检提示；再次 `finish` 后结束 | `closed`，`normal_completion=true` |
| 技术异常 | 预制传输异常留下未知预约，没有把费用或状态填为零，没有启动后继请求 | `technical_unknown` |
| 原有资源边界 | 原 `BeforeQwenDispatch` 路径仍按已知预算边界闭合，没有伪造新调用 | `closed`，`original_resource_boundary` |

所有场景的 `code_resolved` 均为 `null`。**控制器闭合、原生 finish、代码通过官方评分是三个不同状态。** 特别是首次纯思考截断终止只是保守止损，可能丢失本可在下一次恢复的任务，不是已证实的能力修复，详见[截断策略](software-benchmark-v090-qwen-truncation-policy-r1.md)。

测试使用原 `validate_closed_usage` 校验已闭合用量。会话关闭后请求 RPC 清理，但明确保留 `process_tree_quiescence_proven=false`；本工厂没有导出候选、调用评分或声称宿主工作进程已经静止。保存原始 RPC、追加反馈、执行策略、截断证据、完整账本和 SDK 终态，异常也保留已知原件。

验证入口为 [check_ref_controller_v090.py](../../tools/check_ref_controller_v090.py)，[测试](../../tests/test_ref_controller_v090.py)自动使用已有冻结 SDK。执行中审计阻断网络、权重、GPU、子进程和命令执行。可重复的本地检查命令为：

```sh
.venv/bin/python -m pytest -q tests/test_ref_controller_v090.py
```

## 生产部署还缺什么

**没有接入生产 PID1 控制器，也没有恢复实验。** 将来部署至少需要单独完成以下步骤，不能仅将此次 CPU 工厂当成可直接运行的生产入口：

1. 新建并封存明确版本的 PID1 启动器和私有 SDK 包，显式接入这些模块；保留原配置身份校验、公开环境准入、解释器初始化、截止时间和 IPC 限制。当前 CPU 标签不构成生产授权。
2. 在新生产入口中包装真实 Qwen REF 的 `GuardedModelAdapter`，确保截断证据及完整新执行版本进入结果；DeepSeek 和 PROJECT 不安装这一 REF 策略。不得更换原 frozen 模块的全局函数。
3. 控制器结束后继续原宿主流程：停止并证明写入者静止、确认原模型／RPC 通道闭合、核验完整账本，最后只锁定一个最终工作树，按原补丁导出和官方评分路径处理。不能从 CPU 的 `closed` 直接跳到候选或成功结论。
4. 新旧提示、反馈和截断策略分别标识。后续生成与评分仍必须保留原预算和真实用量，不把新策略结果混作原 REF 配置，不重采旧回合充当原结果。

本轮只完成这条受限 CPU 接入和必要验证；不涉及共享服务器配置或生产服务。
