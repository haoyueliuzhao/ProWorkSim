# v053 数据准备完成与 GPU 调度监控

准备完成时间：2026-10-20 18:10:00 CST。监控器开始时间：18:10:01 CST。本文的资源与执行状态快照截至 18:47:07 CST，后续以实际运行状态文件为准。

## 正式题单已经冻结

32 个候选仓库已形成环境准入结论：23 个仓库合格，9 个来源未准入。依照预先固定的顺序取前 20 个合格仓库，每个仓库 10 题，形成 200 个不同任务；不是从 23 个合格仓库中另作模型成绩筛选。全部来源核验发生在正式模型运行前。

固定题单见 [software-panel-v053-panel.json](software-panel-v053-panel.json)，包含 200 个主测任务、预选 40 个重复任务、280 个独立 slot 与全部生成 seed。40 题各追加两次，不改变主结果只采用首轮 200 题的定义。正式生成预算仍为每回合输入加输出 500,000 token、全批最多 140,000,000 token；原始 Qwen3.5-9B、原生 OpenHands 单 Agent、无训练适配器的配置保持不变。

所选仓库按固定顺序为：

| 顺序 | 仓库 |
| --- | --- |
| 1 | joke2k/faker |
| 2 | arrow-py/arrow |
| 3 | pallets/jinja |
| 4 | burnash/gspread |
| 5 | mahmoud/boltons |
| 6 | andialbrecht/sqlparse |
| 7 | django/channels |
| 8 | r1chardj0n3s/parse |
| 9 | keleshev/schema |
| 10 | graphql-python/graphene |
| 11 | seatgeek/thefuzz |
| 12 | django/daphne |
| 13 | kennethreitz/records |
| 14 | iterative/dvc |
| 15 | pyasn1/pyasn1 |
| 16 | john-kurkowski/tldextract |
| 17 | hukkin/tomli |
| 18 | msiemens/tinydb |
| 19 | paramiko/paramiko |
| 20 | Knio/dominate |

具体实例、来源版本、环境资格引用、重复子集及 seed 以固定 JSON 为准。环境总表保存在 `artifacts/software-panel-v053/environment-admission-v5.json`。此前公共故障、旧回执及 v4 到 v5 的复用链仍保留，不能将这些准备故障计为模型失败。

## 已实际完成的运行前检查

流水线以源码提交 `06b5895ce04b08aa5dd14c94bcd27beb272619bd` 接续。环境阶段复用已完成证据后继续未完成任务，没有重跑全部旧资格验证。

| 阶段 | 实际结果 | 本阶段墙钟秒数 |
| --- | --- | ---: |
| v5 环境准入接续 | 23 个合格仓库，准许冻结 | 2811.153 |
| 固定题单与全部 seed | 200 主题／40 重复题／280 回合 | 0.320 |
| 完整候选导出及原始评分控制 | 通过，零模型调用 | 42.450 |
| 源码快照 | 完成 | 0.342 |
| 200 个真实 SDK 初始请求捕获与容量检查 | 全部通过，零模型生成 | 20.979 |
| 正式运行计划封存 | 完成 | 0.338 |

这些是各步骤实际进程起止时间，不是整个准备工作的总成本：早先版本执行过的测试、下载、缓存修复和人工间隔另有原始记录，复用的旧执行不能重复累计。正式准入凭据见 [software-panel-v053-model-admission-v5.json](software-panel-v053-model-admission-v5.json)。

## 监控器与派发条件

现有系统服务 `proworksim-v053-panel-v5.service` 已进入 `supervise` 阶段，无需再创建第二个监督器。服务观察时为 active/running，主 PID 为 2219792。执行状态为 `waiting_resources`，280 个 slot 均待运行，活动 worker 和历史派发尝试均为 0，暂停原因列表为空。

- 无运行任务时，每 60 秒观察一次物理 GPU 0–7 的真实容量。
- A100／A800 80 GiB 卡实际空闲显存达到 46,080 MiB（45 GiB）后，按固定 slot 顺序派发。
- 最多四个 worker 并行，同一张卡不重复分配本实验 worker。
- 运行中每 5 秒检查 worker；模型进入前若资源竞争导致未能预约，仅按既有零模型重试规则处理。
- 公共故障仍暂停并保留证据，不自动重跑已进入模型的回合，不按分数选择任务。

18:47:07 的观察中，没有 GPU 达到上述容量门槛，因此没有正式模型加载或生成。GPU2／GPU5 的临时占位已按用户要求取消，未重启占位服务；监控器等待实际可用容量。

主要持续记录：

```text
runs/software-panel-v053/pipeline-v5/pipeline-state.json
runs/software-panel-v053/pipeline-v5/execution/state.json
runs/software-panel-v053/pipeline-v5/execution/gpu-observations.jsonl
runs/software-panel-v053/pipeline-v5/preparation/plan.json
runs/software-panel-v053/pipeline-v5/06-supervise.log
```

数据准备完成与正式能力测量完成是两个阶段。本文不报告完成率或稳定性结论；最终分析仍须使用实际回合记录，按原 200 题首轮、40 题重复诊断、任务／仓库层级和技术未知规则报告。
