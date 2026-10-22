# Qwen REF 完成后的生成接管：独立队列与 worker 接线 r5

本修订只接线资源池退休规则，不修改原始任务、模型或评分协议。REF 的 500 个预定生成槽全部终态并且原生成资源静止后，GPU7 才可按照独立 pool overlay 的规则转换为 MATCH／PROJECT 资源。技术未知保留为未知；它们不被改写为已评分，也不新增正式回合。

## 队列入口

新入口 `tools/run_qwen_ref_handoff_v054_r5.py` 继承当前 `run_qwen_disk_volumes_v054_r4.VolumeCoordinator`。它先验证独立 overlay 和本次源码封存，并在新进程内安装 canonical pool reader。原双卷磁盘门、共享预约锁、原资源恢复凭据、预热调度及 GPU6 kernel 路由均沿用。

原 `resource_planning_revision` 保持 r4，另存 `ref_handoff_host` 凭据。采用时只追加宿主采用记录，逐题 `rows` 必须同值，不创建模型调用或正式 claim，不向既有 worker、评分器或驻留模型发送信号。启动前拒绝与旧 r4 协调器同时活动，随后仍由原队列排他锁防止重复控制。

## 新 worker 路由

仅当任务类型恰好为 `generation`，且 argv 前两项恰好为当前 `HOST_PYTHON` 与项目原入口 `tools/run_benchmark_episode_v054.py` 时，入口替换为 `tools/run_benchmark_episode_ref_handoff_v054_r1.py`。原 `--config`、`--output` 及其余参数逐项原样转交；正式配置中的任务身份、seed、条件、预算、工具、claim 和导出逻辑不改。

新 wrapper 验证 host revision 的 SHA、source seal 与 overlay 引用一致后，先安装 reader，再调用原 `software_benchmark_runner_v054.main`。原源码 generation record 追加 host revision 与 overlay 引用，实际不可变 `job.json` 保存完整新入口。已启动 worker 不替换。GPU6 使用 `/usr/bin/env PYTHONPATH=...` 的独立源码快照路径，评分路径及其他不精确匹配的 argv 均逐项透传。

## 必要控制

`tests/test_qwen_ref_handoff_routing_v054_r1.py` 的七项 CPU 控制已通过（0.11 秒）。覆盖原 generation 参数无损转交、GPU6 独立快照透传、评分透传、不同 Python／脚本不误匹配、worker 安装 reader 在原 runner 调用之前，以及仅匹配的新 generation 追加审计字段。三个新增入口／控制文件的 Ruff 检查通过。

这些是零模型的路由控制，不是 GPU7 转换成功或正式任务性能证据。实际退休资格、live quiescence、一次转换及新 MP 六请求两会话资格由独立 pool overlay 负责；相关旧失败、费用和准备凭据另存。本修订本身没有停止任何服务、启动模型、修改正式队列状态或账本。实际采用／部署回执须以宿主执行时另存的凭据为准。

## 封存与采用

先封存 pool overlay，再执行 `freeze --predecessor <当前 r4 revision> --overlay <overlay.json> --output <新宿主 revision.json>`。host seal 包含两个新入口、overlay 模块／boundary／monitor、overlay 本身和所有沿用的 r4 源码依赖。

正式启动使用 `run --revision <新宿主 revision.json> --sha256 <精确 SHA>`。仅在根协作者确认停止旧协调器、保留在途 worker 后执行。后续重启验证同一采用记录，不能借本入口清除全局故障、重置退休状态或重跑已进入回合。

已完成封存：

| 凭据 | SHA-256 |
| --- | --- |
| pool overlay：`runs/software-benchmark-v054/ref-generation-handoff-r1/overlay.json` | `a0b5a1e69d1343a2df2247acc208b5e71265dba45f5b80100d8379567dcae3ae` |
| host：`runs/software-benchmark-v054/ref-handoff-host-r5/revision.json` | `b579c732e93c642d8213d09d60a052180774f45e85ba9b2c154d7ca6a5ed81dd` |
| 七项路由控制：`runs/software-benchmark-v054/ref-handoff-routing-cpu-control-r1/control.json` | `427bf8745a9d54e17b689ffae4d487f24430b51295c40b490bdd58b83fef15ad` |

小型 host／路由凭据副本位于 `artifacts/software-benchmark-v054/ref-handoff-host-r5/`。上述封存只绑定代码和规则，不表示 REF 已完成或 GPU7 已转组。

根协作者已于 2026-10-22 14:17（北京时间）部署新 queue／pool 管理器；14:19 的只读观察确认两者 active、队列与 provisioner 持续更新、host seal 正确、conversion 仍为 null，REF 为 305 闭合／4 技术未知／191 pending，当前受既有共享磁盘预约门等待，尚未出现采用后的新 canonical job，GPU6 在途 snapshot 路径与四个旧失败设备的 attempt-1 记录保持；具体凭据为 `artifacts/software-benchmark-v054/ref-handoff-host-r5/post-deploy-observation.json`，因此此刻只确认管理器采用成功，不声称 GPU7 已转组或实际新 wrapper 回合已执行。
