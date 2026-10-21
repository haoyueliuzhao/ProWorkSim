# v054：异常清单与主流程结束后一次补评分

本修订增加独立宿主侧异常清单和末尾评分入口。主流程按冻结的 1,500 个槽位继续执行；生成故障、用量未知和评分故障保留原证据。只有主流程全部达到终态、生成和评分活动计数均为零之后，才允许对评分故障的原锁定候选进行最多一次补评分。该入口不调用模型，不重选补丁，不将技术未知填成模型失败，也不改变既有 r5 官方评分器、容器资源或 1,800 秒超时。

## 已观察到的异常

槽位 93 为 REF、`scikit-learn__scikit-learn-14710`。原官方评分目录为：

`runs/software-benchmark-v054/official-output/v054-REF-code-b6435f5902aff80193beb74f9d12d239e8862dc3/`

已有日志显示 editable 安装和评测补丁应用完成，pytest 收集到 80 项后开始执行，但在 1,800 秒限额到达时没有完整测试终结标记和 `report.json`。官方 harness 在超时分支先抛出异常，未执行完整评分报告生成；容器随后正常停止并删除。包装进程退出码为 0 表示成功记录了技术未知，不能解释为该候选通过或失败。

原回执的 `status=technical_unknown`、`resolved=null` 和原评分输出全部保留。现有日志不足以恢复完整官方判定，也没有当时的线程和 CPU 时间细分，不能把超时确定归因为候选、线程过量或宿主争用。该例只支持“一次评分未在原资源限额内闭合”的结论。

## 固定处理边界

| 异常 | 主流程行为 | 末尾行为 |
| --- | --- | --- |
| 生成或执行技术未知 | 保留原候选、调用、种子、账单与故障；不重跑模型 | 保留异常，不增加模型请求 |
| 用量或账单未知 | 分列已知实际用量和不确定预扣，不能把未知填零 | 即使评分补齐也不抹去账单未知 |
| 评分技术未知 | 保留原锁定候选和原评分身份，继续其他槽位 | 先恢复已经存在且身份完整匹配的确定报告；否则对同一候选最多补评分一次 |

补评分只将原请求的 `attempt` 增加 1。任务、组别、端点、模型配置身份、补丁、候选树、初态树、数据集、Docker 镜像、评分器、基线映射和 `limits` 均必须逐字段相同。原评分器已经将 `attempt` 纳入完整身份，因此无需新评分适配器即可获得独立 `run_id`，不会命中原超时缓存。

对槽位 93 进行的纯身份计算得到：

- 原身份：`v054-REF-code-b6435f5902aff80193beb74f9d12d239e8862dc3`。
- 预测补评分身份：`v054-REF-code-f40a183a0c6ed6afa79ea6af50c4bc5cbd216b83`。

这里只计算并核对了身份，尚未提交补评分。一次补评分若仍未知，即写入最终异常清单；不延长超时，不增加资源，不循环重试。

## 主流程终态与异常清单

入口消费 `formal-queue-r1/deferred-fault-overlay-r1/primary-completion.json`。它必须是 `v054-deferred-primary-completion-v1`，包含不可变的完整队列快照、原执行 bindings 和显式末尾处理策略。验证要求：

- 计划仍为原 1,500 个槽位，任务和 seed 与冻结槽表完全一致。
- 生成状态只能为 `closed` 或 `technical_unknown`；已登记评分状态只能为 `official_report` 或 `technical_unknown`。
- `active_generation=0`、`active_graders=0`，并明确 `primary_only=true`、`no_generation_retry=true`。
- 策略为主流程之后、每端点最多追加一次、资源与原请求相同、禁止模型重跑和补丁重选。

异常按快照中的槽位和端点收集，而非按事件条数执行。因此，历史行内事件和后补不可变事件同时描述槽位 93 时，不会触发两次补评分。清单保留任务身份、组别、种子、生成尝试、模型配置、claim、种子回执、候选锁、账单快照、原评分请求、原 attempt、run ID、资源、补丁和全部身份引用。原事件另行保留以便审计。

PROJECT 账单中的不确定预扣是用量上界，不等于已知实际消耗。本入口只把已明确报告的 `reported_actual_trace` 汇总为已知用量；不确定预扣单列，完整实际用量保持未知。

## 一次执行与恢复

每端点使用独立目录、排他锁和永久 `started.json`。一旦写入启动意向，后续恢复不能再次启动该尝试。已有确定报告必须同时匹配完整 identity、run ID、identity SHA、正式运行属性和布尔 resolved 值；匹配后可直接恢复，不再调用评分器。

原评分进程未明确退出、候选或引用失配、输出目录已存在但无授权启动意向等情况保留为未解决异常。进程中断后没有确定报告的尝试也不自动重演。独立驱动一次串行启动一个评分进程，同时复用原两把 grader 全局锁；子进程继承端点和 grader 锁，避免驱动退出后立即失去容量约束。它不触碰模型常驻服务或 Actor 的反馈通道。

输出写入独立目录：`binding.json`、`inventory.json`、逐端点 `request.json`、`started.json`、`child.json`、stdout/stderr、`completion.json`、`result.json`，以及总 `progress.json`、`summary.json`。原主队列状态和原评分目录不改写。最终汇总同时保留已补齐结果与仍未知的唯一槽位数量。

## 运行入口

只生成清单可随时执行，输出必须使用新目录：

```bash
.venv/bin/python tools/run_deferred_scoring_v054.py inventory \
  --queue-state runs/software-benchmark-v054/formal-queue-r1/state.json \
  --output runs/software-benchmark-v054/deferred-inventory-r1
```

主流程终态后的一次补处理：

```bash
.venv/bin/python tools/run_deferred_scoring_v054.py run \
  --primary-completion runs/software-benchmark-v054/formal-queue-r1/deferred-fault-overlay-r1/primary-completion.json \
  --output runs/software-benchmark-v054/deferred-scoring-r1
```

同一补处理可恢复读取相同输出目录，但不会对已经消耗的补评分尝试再次执行。自动触发应由宿主在收到终态标记后启动此独立入口；主流程继续执行无需等待补处理进程。

### 耐久等待器

`tools/watch_deferred_scoring_v054.py` 使用标准库先验证启动封存文件，再导入补处理模块。封存固定 driver、CLI、等待器自身、候选读取、存储、基线验证、原评分适配器、评分安装清单和私有 CPU runtime 启动源码，并固定已经上线的原异常策略。它每 30 秒检查终态标记；未出现标记时不创建补评分请求、不调用评分器。真正触发前再次检查所有固定源和策略。

部署后先创建独立封存文件：

```bash
.venv/bin/python tools/watch_deferred_scoring_v054.py seal \
  --fault-policy runs/software-benchmark-v054/deferred-fault-policy-r1.json \
  --primary-completion runs/software-benchmark-v054/formal-queue-r1/deferred-fault-overlay-r1/primary-completion.json \
  --output runs/software-benchmark-v054/deferred-scoring-r1 \
  --seal runs/software-benchmark-v054/deferred-scoring-watch-seal-r1.json
```

然后将返回的 SHA-256 明确放入 systemd 启动 argv（下列 `SEAL_SHA256` 为该返回值，不能保持占位符）：

```bash
systemd-run --user --unit=proworksim-v054-deferred-scoring-r1.service \
  --property=Restart=on-failure --property=RestartSec=30 \
  --property=KillMode=control-group --property=TimeoutStopSec=60 \
  --property=WorkingDirectory=/data0/zhuxinrui/projects/ProWorkSim \
  /data0/zhuxinrui/projects/ProWorkSim/.venv/bin/python -B \
  /data0/zhuxinrui/projects/ProWorkSim/tools/watch_deferred_scoring_v054.py watch \
  --seal /data0/zhuxinrui/projects/ProWorkSim/runs/software-benchmark-v054/deferred-scoring-watch-seal-r1.json \
  --seal-sha256 SEAL_SHA256
```

`watch-waiting.json` 表示仅在等待；`watch-trigger.json` 是永久一次触发记录；`watch-completion.json` 指向独立末尾汇总。触发后进程中断时不会重新调度 driver 或再运行模型。已触发但未完成的现场应根据现有逐端点报告核对；不能自动删除意向文件后重试。systemd 重启也遵守这一边界。

20 项驱动 CPU 控制已经通过宿主 `.venv/bin/python` 实际加载本地数据并调用原 r5 纯身份函数，确认宿主依赖可用；真正评分仍使用原私有 scorer runtime，不下载依赖。

## 本次必要控制

一次 CPU 控制共 20 项通过。它使用槽位 93 已保存请求及原 r5 的纯身份函数，确认原身份复现、新 attempt 身份独立、只有 attempt 可变、1800 秒及资源不变、重复启动拒绝、原有效报告可恢复、错误身份拒绝、完整 1500 槽终态门有效、待执行或活动任务不能绕过、变更 seed 拒绝、账单未知不被改为已知、重复事件不造成重复处理。补丁、候选树或超时任一变化均拒绝。

控制回执：`/tmp/v054-deferred-scoring-r1/control/receipt.json`，SHA-256 为 `54ab5f4ac94329c5dd8aeefe1d640996576420f317b31d23f73a1a83e03d965a`。控制中模型请求、正式评分调用、GPU 查询和正式槽位领取均为 0，未改生产文件。它证明的是新驱动的身份和恢复分支，不能替代尚未执行的真实末尾评分。

新增等待器后仅执行 8 项窄 CPU 控制：无终态不触发、源 SHA 变化拒绝、原策略不匹配拒绝、合格终态一次触发、正常重启不重复、已有中断触发不重复、等待间隔固定 30 秒、systemd argv 中的 seal SHA 不匹配拒绝。控制通过内存中的合成 driver 记录调用，真实模型/评分/GPU 调用仍均为 0；原 20 项未重跑。回执 `control/watch-receipt.json` 的 SHA-256 为 `a368e5e130721f434d627c408225a3f1ce9d38e26a66d0f0a0609c438b9cd96b`。
