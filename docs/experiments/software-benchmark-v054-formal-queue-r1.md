# v054 三组固定 1500 槽的持久执行与评分

## 授权、预算与尚未启动的边界

用户于 2026-10-21 明确要求“尽快完成环境准备进行实验”。本修订将该执行授权单独记录在 `config/v054-formal-authorization-r1.json`，不覆盖旧准备阶段的 `formal_execution_authorized=false`。授权范围为 SWE-bench Verified 固定 500 题在 REF、MATCH、PROJECT 三组各执行一次，仍用同一个原始 Qwen3.5-9B、单 Agent、无项目 LoRA、无训练。每槽 500,000 输入与输出 token，上限合计 750,000,000；上限不代表预计消耗量，不含环境准备、评分和 GPU 驻留。

`config/v054-formal-execution-plan-r1.json` 固定队列规则。写出授权和计划不会启动模型；必须另有 REF 与 MATCH 两种数值模式的真实 `capacity_and_synthetic_accounting_passed` 回执、最终源清单和 r5 评分安装清单，才能物化运行绑定。PROJECT 使用 MATCH 的数值容量证据。已有 GPU holder 的交接由根协调器执行；队列不会终止 holder 或其他进程。

## 顺序、资源与独立初态

原 `slots.json` 的 SHA-256 为 `55899d0b83a5bab1082bccb50496fb6c1d7111ecb951fc4d61c222be19d88676`。1500 个槽、三个条件、原任务身份和 seed 全部保持。调度按原 `slot_index` 顺序领取；前一槽尚无原子 claim 时，不跳到后面的任务。当前所需 GPU 忙会阻塞后续顺序，避免依运行结果或短任务优先改变任务选择。

最多两个生成槽：REF 仅物理 GPU 7；MATCH、PROJECT 共用物理 GPU 6。REF 只有一个 18054 端口 resident。队列只做显存只读观察，真实 GPU/global resident 锁和 REF 端口锁由 runner 在原子领取任务之前取得。明确资源等待必须同时满足退出码 75、`resource_not_ready`、未 claim、未 entered、0 model calls、0 GPU loads；只有这类零执行等待可以保留同一槽并在 30 秒后再次准备。其他依赖或初态故障按技术未知暂停，不将准备失败改成模型失败。

每个槽调用正式 service factory 建立新的 owner/service、私有通信与账本，不复用容量验证的 resident。历史补丁、测试反馈、模型 KV 缓存和评分结果不能进入另一槽。仅可复用按源身份绑定的不可变本地环境缓存。每槽保持 128 attempts、128 decisions、5400/6000 秒边界；未知账单保留预约量、暂停新生成，不把未知当成 0。完整 controller 账本以引用保存，不在调度摘要中将预约量冒充实际 token。

## 持久性与故障语义

入口为 `tools/run_formal_queue_v054.py`，主实现为 `software_benchmark_queue_v054.py`。固定运行目录为 `runs/software-benchmark-v054/formal-queue-r1`，包含不可变绑定、队列状态、独立 slot 准备目录、systemd worker intent、stdout/stderr、进程退出回执及逐端点评分引用。

协调器持唯一文件锁。每个 worker 启动前先原子落盘 intent，再启动由 intent 路径确定的唯一 user systemd transient unit，`Restart=no`。协调器重启只观察已有 unit、持久 completion 和全局 episode claim；不会重新提交一个启动结果不明的 intent。unit 消失且无退出回执、已有 claim 却未完成、导出失败、评分异常或冻结源码变化都暂停新生成，保留原身份，不重采、不自动重新评分。对已经在途的正常槽，允许其由原 watchdog 完成闭合；原锁定候选可继续在可信端评分。源码变化时不再启动任何新 worker。

worker 属于各自 systemd control group；停止协调器不会把仍在途 worker 当成未执行任务。实际 once-only claim 仍由 runner 在 `episode-claims` 全局目录原子创建。队列状态不取代该原始证据。暂停后重新启动协调器不会清除暂停或自动重试；公共故障若需修订，必须另外记录恢复协议。

## 评分也是完成条件

runner 返回 `closed_candidate_and_official_requests_ready` 只表示生成已闭合和候选已锁定，不表示实验完成。队列随后在可信 CPU runtime 调用冻结的官方 r5 wrapper，最多两个评分 worker；各 worker 还持两把全局评分锁之一，协调器重启后仍不能超额。

REF、MATCH 评分唯一 terminal code。PROJECT 分别评分 terminal code 和存在的最后合法提交；即使两个树相同，也不共享缓存结果。r5 的 run ID 包含组、端点和完整身份摘要，不使用跨组相同 run ID。PROJECT 无合法提交时记录 `no_legal_submission`、`R_delivery=0`，且明确没有为不存在的提交制造评分；REF、MATCH 的 delivery 为不适用。候选、初态、模型配置、官方镜像和评分清单均由请求与原始 r5 identity 绑定。没有评分结果返回 Actor。

只有官方 receipt 可确定的 true/false 才是代码结果。非零退出、无 receipt、身份不符或 `technical_unknown` 暂停新生成并保留完整日志；不将它们填成模型错误，不补跑或换题。所有 1500 槽的生成及必须的评分端点闭合才标记完整完成。状态摘要一直保留每组 500 的分母；未定时主完成率为 null，另报成功下界和未知上界。

## 根协调器的启动步骤

先完成并冻结数据、共同 Actor、公开测试 registry、实际模型容量、最终 `artifacts/software-benchmark-v054/runner/source-manifest.json`。源清单必须包含队列、runner、两 factory、r5 和 CLI。队列初次验证这些小文件的摘要，后续调度核对已绑定的 inode/size/mtime/ctime；不重新 hash 大模型或 Docker 层。

在仓库根目录以项目 `.venv/bin/python` 运行以下命令，路径应替换成实际成功回执。宿主 `/usr/bin/python3` 缺项目导入依赖，不能用于队列或 runner；这里不改变 GPU 子进程或官方 scorer 的固定解释器。

```bash
PYTHONPATH="$PWD/src:$PWD" "$PWD/.venv/bin/python" tools/run_formal_queue_v054.py freeze \
  --ref-capacity /absolute/path/to/passed-ref-capacity.json \
  --match-capacity /absolute/path/to/passed-match-capacity.json \
  --scorer-manifest "$PWD/artifacts/software-benchmark-v054/scorer/installation-manifest-r5.json" \
  --output "$PWD/runs/software-benchmark-v054/formal-bindings-r1.json"
```

使用输出 reference 中的实际 SHA 启动唯一持久协调器：

```bash
systemd-run --user --unit=proworksim-v054-formal-queue-r1 \
  --property=Restart=no --property="WorkingDirectory=$PWD" \
  --setenv="PYTHONPATH=$PWD/src:$PWD" \
  "$PWD/.venv/bin/python" "$PWD/tools/run_formal_queue_v054.py" run \
  --bindings "$PWD/runs/software-benchmark-v054/formal-bindings-r1.json" \
  --bindings-sha256 ACTUAL_BINDINGS_SHA256
```

此文只描述执行机制，不预报三组成绩或将容量诊断计入正式回合。CPU 控制仅覆盖必要的新风险：持久 intent 的断连与无回执恢复、原顺序和资源等待边界、两评分锁阻止第三个实际子进程、已完成 worker 拒绝重放、评分 false 正常闭合及候选错配暂停。没有重跑既有环境、500 个 Docker 镜像或正式模型题目。
