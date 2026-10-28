# v066：保留 v064 实验身份的 API 续跑与旧证据复用

本次修订只调整宿主派发和故障范围。模型可见的 v064 SDK bundle、DeepSeek Flash 思考模式参数、REF／PROJECT 工具、上下文、输出和每题预算保持原值。v064／v065 原源码和结果不覆盖。本说明记录代码与只读准备，不能作为真实续跑已完成的证明。

## 原预算与资格

唯一费用账本仍为 `runs/software-benchmark-v064/full-verified-r1/api-budget/ledger.sqlite3`，现金上限仍为人民币 1500 元，包含原准备、生成、摘要及未知预约。v066 不新开预算、不清空旧请求、不解除已有未知预约。原两次中性资格调用共 799 个实际输入加输出 token，直接复用原资格和账单；不重复中性调用、模型元数据或余额 API 请求。官方离线 tokenizer、计数余量及真实 SDK 工具 schema 仍引用原冻结文件。

新 `software_benchmark_deepseek_runtime_v066.py` 只在正式 `initialize_for_run()` 通过 v066 权限和原资格核验后加载 API key。普通构造、预算查询和统计不加载 key、不请求网络。容器继续只见 key-free adapter；18219 仍是私有 FIFO 逻辑身份，不创建宿主监听。

## 不重放已经入模的任务

只读核查的旧 30 个 episode 中，27 个已经有实际宿主 usage、API 请求或 controller 调用记录，不能重新生成。旧 25、27、29 三项尚未进入模型且完成清理，可以按原任务、条件、seed 和配置重新排队：

| 原索引 | 模型／条件 | 判断依据 |
| --- | --- | --- |
| 25 | DeepSeek／PROJECT／500 万 | FIFO 的总请求、计数、生成、失败请求均为 0，原 API 账本无该槽请求；controller 在模型前 OOM 退出，全部对象已删除 |
| 27 | Qwen／PROJECT／750 万 | 同样无 FIFO 请求与宿主模型 usage，controller 在模型前 OOM 退出，全部对象已删除 |
| 29 | DeepSeek／PROJECT／750 万 | 入模前取消，FIFO 请求均为 0、无 API 请求，全部对象已删除 |

25 和 27 的旧 `model_dispatch_started=true` 是启动意图标记，不能独自证明已经调用模型。判定同时保留原标记、宿主通道计数、实际账本、controller／actor readiness 和清理证据；没有修改原技术未知状态。新的派发 inventory 必须明确列入可续跑身份，API transport 在建立前还检查该槽没有任何旧请求，且一个运行器只允许创建一次该槽 broker。

原 109 项通过的环境资格、17 项代码评分、7 项交付端点均保留原文件引用；3 项未通过的环境资格也保留，不悄悄换题或视为模型错误。证据汇总位于 `artifacts/software-benchmark-v066/recovery-preparation-r1/predecessor-evidence.json`。代码评分继续绑定原候选锁和独立 request／receipt，不重用不同补丁的评分缓存。

## API 故障与并行队列

新状态查询区分实际在途现金预约与结果未知。`reserved` 是尚在执行的请求；`uncertain` 是没有可信完整账单的已尝试请求。后者触发 API 侧停止，保留现金预约和未知 token 记录。预算不足、鉴权或 provider／账单异常也只停止 API 派发；Qwen 和独立评分的生命周期由 coordinator 分开管理。

`cancel_all()` 只中止本 API runtime 已创建的私有 socket。它不操作 GPU、模型服务、Docker 对象或共享主机，不释放未知费用预约。取消后新调用在 HTTP 前拒绝并带有明确的未发送证明；已经发送的调用仍按旧权威账本结算或保留未知，不能伪装成零费用。

## 必要验证及边界

本次 6 项 CPU 测试通过：唯一旧预算与资格、构造无网络／key、未知费用的 API 独立停止、失败资格不重试、原身份／schema 与单 broker 限制、已有 API 请求禁止重放、取消的未发送证明和私有范围；部分边界在同一测试中覆盖。相关三个新文件 Ruff 检查通过。只读审计没有真实 API、Docker 或 GPU 操作，也没有共享服务器配置修改。

DeepSeek 模型别名依旧不能固定为可验证权重哈希；本次没有新增远端元数据请求，也不据此宣称 provider 后端从未变化。此限制沿用原协议并在逻辑 resident 身份中保留。完整实验的最终平均 token 必须合并旧权威 usage 与新续跑 usage，并保持旧 6000 个计划分母；未知、未开始及费用预约均不能填成零实际消耗。
