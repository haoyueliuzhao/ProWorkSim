# v0.25 恢复运行：目标显卡遥测与有界故障宽限

本修订只改变新恢复 supervisor 的资源观察策略。旧冻结脚本、旧资源日志、原中断与其已经消耗的成本保持；不改变模型、模板、训练器、更新算法或参数更新预算。模块本身只读取信息并返回停止原因，不发送进程信号。

原运行在全机 `nvidia-smi --query-gpu` 一次 10 秒超时时，由旧 supervisor 的单次查询失败规则停止。另一个 process 查询成功，仍不足以使旧规则继续。本修订不能把原丢失的中途梯度或失败回溯改为成功；新的恢复与资源授权由独立方案绑定。

## 查询与绑定

入场继续要求 supervisor 取得完整且成功的全机资源快照；失败只保持等待并计入 wall 时间，不发起 worker。运行后不再以别卡查询失败作为杀停本 worker 的直接条件。

`target_resources(gpu_index_or_uuid, worker_pid=...)` 的两条只读命令均带 `--id=目标`：

- `--query-gpu=index,uuid,name,memory.free,memory.total,utilization.gpu`；
- `--query-compute-apps=gpu_uuid,pid,used_gpu_memory,process_name`。

默认每条查询超时为 5 秒，两条顺序查询；接口仅接受明确的 5 或 10 秒查询上限，不使用无界查询或重试循环。本机已安装工具的 `nvidia-smi --help` 明确列出选择查询支持 `--id`，未为本次开发运行模型或读取真实 GPU 使用量来冒充故障实验。

原 `time/gpus/processes` 以及各自 `returncode/stdout/stderr` 字段保留。增加目标 scope、每条命令及起止时间、超时参数、原异常类型／文本／部分 stdout／stderr。`sample.time` 在两条查询之前记录。`TimeoutExpired` 的原输出即使为 bytes 也保留为文本，不将未知内存写作零。

`TelemetryGuard` 绑定入场显卡物理 index、UUID，以及当前 worker 的 `/proc/PID/stat` start ticks。每次查询后单独读取实际 OS worker 身份；显卡 compute process 列表尚未出现 CUDA context 不等于 OS worker 消失。启动加载期若成功完整的 process 列表为空、而该 OS worker 仍存活且身份一致，则其当前被测显存为 0。这与查询失败导致的 `None` 明确区分。

## 120 秒连续不完整遥测宽限

完整、可验证的新 GPU 与 process 样本才能清空连续失败计时。单次失败不直接停止 worker；失败累计次数、连续次数、首次失败时间和原样本均记录。

首次失败计时取 **该次查询开始的 `sample.time`**，不是返回异常之后的时刻。当前观察时间减去该起点达到 120 秒时，若完整遥测仍不可用，返回 `telemetry_unavailable_budget`。首次查询本身所耗 5/10 秒算在 120 秒内。恢复成功时记录中断持续时间，清空连续失败计时，但不清除累计失败数量及已有日志。

当前失败样本的字段语义：

| 字段 | 含义 |
|---|---|
| `fresh` | 此次完整样本新鲜且身份、GPU、process 行全部有效 |
| `stale` | 此次非完整新样本，但已有旧成功参考 |
| `last_success_reference_only` | 旧成功条目仅供参考，不替代此次测量 |
| `own_gpu_memory_mib` / `own_memory_mib` | 此次有效 process 测量所得本 worker 显存；未知为 `None` |
| `own_memory_fresh` | 当前显存确由此次有效 process 查询得出 |
| `failure_since` / `failure_seconds` | 连续完整遥测失败的起点与经过时间 |
| `stop_reason` | 无需停止时为 `None`；否则给出精确原因 |

process 查询完整成功、UUID 仍与绑定一致时，即使 GPU 汇总查询失败，也可以得到当前本 worker 显存；若这个新鲜读数已经达到原显存上限，立即返回 `own_gpu_memory_limit`，不等 120 秒。即使另一个无关 PID 的行不完整，已成功观察的唯一且有效本 worker 越限行仍记为 `own_memory_observed_lower_bound_mib` 并立即停止；精确总值仍为 `None`，不伪装完整测量。相反，process 超时、不完整行、N/A、非有限数值、重复 PID 等不会被当作 0，也不会以旧显存填充当前值。旧成功样本重放或超过 120 秒的旧输出不能重置宽限。

OS worker 已消失或已僵死、PID/start ticks 改变、身份无法读取、显卡 UUID/index 与入场绑定不同分别返回 `worker_lost`、`worker_identity_changed`、`worker_identity_unavailable`、`gpu_identity_changed`。这些身份异常不享受遥测宽限。

**所有 wall、stage、task、RSS 和 artifact 检查仍由 supervisor 独立执行。**它们不受 `own_gpu_memory_mib=None` 或遥测宽限抑制；任一新鲜成功测量已经证明越限时仍应立即停止。模块不增加任何任务时间、资源或实验授权。

## 接入

```python
identity = worker_identity(process.pid)
guard = TelemetryGuard(
    target_gpu_index=gpu_index,
    target_gpu_uuid=admitted_uuid,
    expected_worker_start_ticks=identity['start_ticks'],
    worker_pid=process.pid,
)
sample = target_resources(admitted_uuid, worker_pid=process.pid)
observation = guard.observe(
    sample, now=time.time(), worker_pid=process.pid,
    gpu_index=gpu_index, own_memory_limit_mib=57344,
)
```

训练显存门维持 57344 MiB，评价／后继维持 32768 MiB。具体 supervisor 仍检查 worker handle 的退出状态，并保留自己的独立时限与全局资源核算。资源 JSONL 可保留原外层 `sample` 和 `own_gpu_memory_mib`，增加完整 `telemetry` 观察对象；不要把 `last_success` 拷贝成一个新的成功样本。

## 有限验证

`.venv/bin/python -m pytest -q tests/test_resource_monitor_v025.py`：**17 项合成测试通过**。范围包括一次 timeout 后恢复、部分 process 新测量、连续故障精确 120 秒边界、新鲜显存越限、未知不为 0、process 行不完整／重复、加载期真实空列表、worker/显卡身份异常、旧样本重放、过期成功输出，以及两条命令均只查询目标显卡并保留原超时输出。

Ruff 定向检查通过。未杀停真实进程、未运行 GPU 模型、未模拟新的训练收益，未重跑学习路径验收。这里只证明新的资源观察状态机按声明工作；不能保证驱动、硬件或其他项目永远不再发生资源故障。
