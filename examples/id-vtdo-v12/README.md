# ID-VTDO v0.12 冻结实验目录

当前研究目标见[理论设计](../../docs/research/id-vtdo.md)，执行预算与门槛见[计划](../../docs/id-vtdo-v012-plan.md)，事实结果见[实验报告](../../docs/experiments/id-vtdo-v012.md)。这里的 JSON 是已执行批次的冻结输入，不能在原文件中换模型、提示或预算后继续当作同一实验。

| 文件 | 用途与边界 |
| --- | --- |
| `d0-pilot-protocol.json` | 两段开发接入 pilot；与正式分母分离。 |
| `d0-protocol.json` | 16 段固定起点/后端/接口组合比较；两后端工作接口门槛均未通过。 |
| `d1-protocol.json` | 原三角色团队32计划名额。DeepSeek16完整采集；原Qwen中断，闭合2/开放1/未启动13。 |
| `orders_*.json`、`situation-registry.json` | 原D1的四个开发情境；同一手工模拟来源家族，不增加独立公开来源数。 |
| `d1-efficient-protocol.json` | 保留的采集前驱动错误协议。环境步数被误写为元数据，16名额全在场景hash核验处拒绝；0世界/0HTTP。不要当作有效采集入口。 |
| `d1-efficient-r1-protocol.json` | 修正上项的整数环境步数后，独立冻结的本地16联合槽；每角色20决策，显式KV高效float32注意力、`matmul-precision=high`（允许TF32）及公开结构合同。 |
| `*-public-structure.json`、`situation-registry-efficient.json` | 新队列公开表名/列名合同与单独情境指纹；不与原D1合并支持。 |

原语义见证位于 `../decision-team-v12/`，只验证可行性，不提供模型自然支持。所有角色任务未按主动/请求方法标签改写。

每份正式协议已固定目标角色、预算、随机入队顺序、基础奖励合同、Mapper、类内最低计数、源码及服务身份的引用。部分绝对路径/服务端口属于原服务器，原服务 manifest 包含 PID 与资源快照。复现需建立新的只读模型服务、检查实际 profile/权重和路径、重新冻结一个新协议与新输出目录；不能盲目复用旧 manifest SHA。共有 RNG 和运行顺序留在原记录，不声称跨机器逐token确定性。

采样驱动：`scripts/id_vtdo_model_batch_v012.py --protocol 新冻结协议 --execution-queue 后端队列 --output 新目录`。D2读取闭合episode、原HTTP与已冻结slot目录，用 `scripts/team_rollout_experiment.py` 另目录物化。D3默认/`--prepare-only` 只做准入；原D0不通过，本轮没有实际参数更新。原始 `runs/` 留在服务器，Git中的紧凑归档保存结果与原始文件hash。
