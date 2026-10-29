# v088：有完整证据的单题通信初始化故障隔离

本修订解决的是停止范围，不把技术未知改成模型失败或成功，也不重跑任何已消费任务。旧 v086 的停止、取消、候选和费用记录保持原样。只在新建的私有 episode namespace 中替换 `classify_failure_scope`，不修改冻结的 v066 episode 或 v082 队列文件，不操作运行中的 Qwen、Docker 或服务。

## 触发问题

原 slot 5552 在模型派发前失败。宿主 `model-transport.json` 记录 `ValueError: filedescriptor out of range in select()`，ready 为 false，所有请求计数为零。episode 记录 model_calls=0、model_dispatch_started=false，随后停止自己的写入进程并完成 actor／controller／volume 清理。然而旧分类仅因 `trusted_model_bridge_initialization_failed` 标签存在就升级为共享完整性故障，主队列随即取消其他在途任务。

高 FD 等待器本身由独立 IO 修订解决。这里补上分类边界：已经证实只发生于一个尚未派发模型的通信初始化过程，并且其资源已完整清理，不足以证明所有其他任务也受到共享完整性破坏。

## 放行条件和保留的拒绝

只有全部条件同时成立，才把新 episode 的停止范围记为 local：

- 原已知 v066／DeepSeek 初始化结果形状；恰为 trusted_model_bridge_initialization_failed，model_calls 是整数 0、dispatch=false、桥接线程已退出、没有生命周期截止，没有候选、ledger 或 controller 终态等后续阶段证据。
- 从宿主不可变文件读取原通信回执，要求 ready=false、请求／生成／计数／预检回复／重试全部为零，API key 没有进入容器、没有宿主监听；只允许明确列出的本地描述符错误、已知通信截止和 EOF 错误。任意协议帧、来源、身份或 JSON 完整性错误不在允许集合。
- cleanup 回执与传入的实际清理对象完全一致；quiescent=true、cleanup_errors=[]、create_result_unknown=false、无遗留对象，三个原角色均已删除。
- 三份原 claim 必须位于该 episode 的原 resource-claims 目录，角色、key、父 actor、slot_id 和 instance_id 一致。
- 两个原 writer 必须绑定这些同值 claim，container ID 合法、PID0、非 running／paused／restarting，并有明确退出状态。

缺少任一原件、hash 改变、新增未知故障字段、非零模型请求、身份不同、写入未结束或清理不明，均回到原严格全局停止规则。错误文本本身不构成放行依据；它只是在结构、阶段、身份和清理证据已经全部成立后的受信宿主异常类型限制。

新结果保留原 shared_integrity_fault 标签，并增加 `local_failure_classification`，明确原回执、claim、零派发观察、禁止重试、没有更改账本、没有推断现金费用为零。原 episode 根据 local 分类写出 batch_stop_required=false；原 v082 队列沿用其技术未知隔离路径，其他任务继续。真正的 shared fault、response projection fault、清理不可信，以及 API shared_halted 现金状态仍执行原停止逻辑。

接入顺序：先完成高 FD IO 的私有 episode 适配，最后调用 `software_benchmark_failure_scope_v088.bind_episode(delegate)`。该函数会检查实际 `_run` 的 globals 绑定，拒绝修改原始模块，也不会仅修改一个无效的 module 属性。

## 必要 CPU 验证

12 项有限检查通过，限定 Ruff 通过：

- 完整原形状变为 local，原标记、现金权威、禁止重试和原函数不变。
- 已派发、非零请求、writer 存活、清理缺失、任务身份不同、协议错误、额外共享故障、回执 hash 改变均不能降级。
- 实际 v082 队列中，首题本地初始化失败保留技术未知，另一个已在途 future 没有收到停止，余下七题各执行一次并完成；真正共享身份故障的反例仍触发停止，后六题保持未进入。
- 验证实际 private episode 调用链变化，而原模块 globals 不变。

另对原 5552 已保存文件做一次纯只读形状核验，新规则判为符合 local 条件；原 result 的 SHA 保持 `6635d9d01fd63d570c4a452dc4b7569953947002888df590d423b1f6c8f7c6bd`，并没有回写或重新解释旧正式结果。所有检查均无模型、API、Docker、评分或服务操作。

CPU 命令：`.venv/bin/python -m pytest -q tests/test_failure_scope_v088.py`。运行上线与库存恢复由主协调者完成，本文不将 CPU 控制通过写成真实实验已经恢复。
