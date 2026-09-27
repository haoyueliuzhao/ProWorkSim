# v0.19 优化运行协议与启动约束

本接入保留 v0.18 的真实世界、每个 slot、seed、角色预算、奖励及任务权重；改变的是显式运行协议 Γ。`build_harness_learning_v019.py` 从旧构造函数生成相同的 8 例迁移、118 例主 pilot（64 训练＋27 初始＋27 最终）和独立 16 例密度计划。没有新增成功重采、改变训练次数或借吞吐优化合并支持。四任务主要效用仍各 1/4，主 pilot 仍 Q=B，无自动 O4。

## 数值与实际优化报告门

新 runtime kind 为 `qwen_hybrid_optimized`，profile 由 `candidate_runtime_v019.candidate_profile` 精确生成：目前为 FP32 / 显式 matmul high / 显式 KV 的受限 SDPA 路径 / 前 2048 个精确 token 缓存 / 最多 8 项。high 是新数值路径，不能称为维持旧 highest；逐决策完整原输入重算、原 logprob 最大绝对误差 0.02 / 平均 0.002 的门保留。小请求研发结果或实现存在本身不构成正式启动准入。

协议顶层 `optimization_admission` 保存实际报告的绝对路径和 SHA256。正式报告格式为：

```json
{
  "version": "harness-optimization-admission-v0.19",
  "execution_source_commit": "实际冻结源码提交",
  "sampling_replicas": 2,
  "candidates": {
    "qwen35-9b": {
      "passed": true,
      "weight_manifest_sha256": "实际基座清单SHA256",
      "initial_actor_identity": {"adapter_sha256": "实际fresh初态SHA256", "base_manifest_sha256": "同一基座清单SHA256"},
      "runtime_profile": {"说明": "完整、精确的candidate_profile输出"},
      "checks": {
        "prefix_probability": {"passed": true, "evidence": {"path": "绝对路径", "sha256": "SHA256"}},
        "full_recompute_probability": {"passed": true, "evidence": {"path": "绝对路径", "sha256": "SHA256"}},
        "backward": {"passed": true, "evidence": {"path": "绝对路径", "sha256": "SHA256"}},
        "two_replica": {"passed": true, "evidence": {"path": "绝对路径", "sha256": "SHA256"}},
        "throughput": {"passed": true, "evidence": {"path": "绝对路径", "sha256": "SHA256"}}
      }
    }
  }
}
```

上述示例只有结构说明，不是实际通过报告。候选外键使用原 H1 的 `qwen35-9b` / `qwen38-27b`，profile 内部保持正式 `qwen3.5-9b` / `qwen3.8-27b`。只准入原 H1 完整选择的候选；该候选若未通过所声明配置必需的任何一项，则停止，不因另一候选有通过报告而替换选择或静默退回旧 profile。

模型或 Torch 依赖加载前，门禁核对当前源码干净、当前 commit 等于报告的 `execution_source_commit`，profile 与当前 factory 全字典一致，benchmark manifest 与所选 H1 实际权重清单 SHA 相同，声明 `replicas=2` 时五项判定均须明确 true；声明 `replicas=1` 时不要求 `two_replica`，其余四项仍须通过，且报告顶层 `sampling_replicas` 必须匹配。原始证据文件字节必须匹配。报告门不读取业务成绩。真实 benchmark 负责给出每项判定及事实：两副本实际 actor tensor 身份、无 optimizer、原输入/输出/概率记录和 slot seed 绑定、真实并发与吞吐变化；启动门核验这些判定的精确引用，不重新运行 GPU benchmark。冷加载与热执行应分别留存，不用只报告 warm 延迟隐去启动成本。

新 builder CLI 必填 `--optimization-admission`，在写任何正式计划前还执行原 H1 双进程完整结束、最终选择、权重及 fresh 基座检查。未通过实际门时，不生成可以执行的替代计划。主 pilot 继续等待真实迁移的一次更新、新策略实际工作和原评价 guard；从公共基座 fresh 开始，不恢复迁移权重。优化后 fresh adapter 按实际 benchmark 的 `initial_actor_identity` 核对；与旧 H1 adapter 是否一致另列事实，改变 device count 时不假设原初态必然逐位相同。

## 两副本采集与四项目串联

H2 迁移和主 pilot 必须在采样前用 `--replicas 1|2` 固定进程数。`2` 使用 `proworksim.harness_parallel_v019:collect_window`；`1` 使用原 serial collector，只检查 parent 资源、不创建只读副本、不设置 `PROWORKSIM_REPLICA_GPUS`。数值、真实更新与新策略工作门不因此放松。以下双副本规则仅适用于 `replicas=2`。一个 parent 保有唯一 actor/critic/optimizer，另一个进程只接收当前策略只读快照；两者按固定 slot 分配执行当前同一窗口，收齐可信记录后才允许 parent 更新。分配公式为 `rank=(global_index+1-slot_count)%2`，最后一个逻辑 slot 留在 parent；按原 slot 顺序归并，不按完成顺序改采样。每个窗口保存相同的 `parallel_collection` 合同。独立密度仍使用 serial collector，一窗 16 例、固定完成后最终策略、零更新，不启动副本或 O4。

| 原 H1 选中模型 | parent 可见 GPU | 只读副本物理 GPU | 四项目 GPU及顺序 |
|---|---|---|---|
| 9B | 0,1 | 2,3 | 0,1；迁移与主 pilot 均终态后 |
| 27B | 0,1,2,3 | 4,5,6,7 | 0,1,2,3；迁移与主 pilot 均终态后 |

表中为未覆盖时的默认卡组。`--devices` 显式指定已经过实际 gate 的每个进程卡数；省略时保留旧 H1 的 2/4 卡数。`--learning-gpus` 与 `--replica-gpus` 可声明物理卡组，例如四卡 serial 使用 `2,3,4,5`，或双进程各两卡使用 `2,3` / `4,5`；名单长度必须等于 devices，双进程两组必须无交叉。单进程拒绝无用途的第二组。启动双进程前资源门检查两组并集，child 通过 `PROWORKSIM_REPLICA_GPUS` 取得明确物理卡组，collector 再核对组宽和无交叉。采样开始后资源变化只能等待或失败，不能自动换 replicas、devices 或 collector。仍只记录其他项目竞争，不发信号停止他人进程。

四项目不与两组采集抢卡。新 `continue_harness_v017.py`（文件名保留，运行版本 v0.19）复用原单用途三个 job 的图：migration → 已通过实际迁移门的 pilot → projects。迁移或 pilot 失败时，四项目仍可单独测量，但必须等学习两个 job 确实终态，再到 parent 组执行。9B 与 27B 采用同一顺序。四项目 CLI 同样接受实际 `--optimization-admission`，精确绑定原 H1 选择和新的 profile；该分支只接受精确 gate 绑定的显式 devices；不能用未测 placement override 绕过门。

```bash
PYTHONPATH=<冻结source>/src <resident-python> <冻结source>/scripts/continue_harness_v017.py \
  --project <项目目录> --source <冻结source> --output <全新目录> \
  --optimization-admission <实际最终优化准入报告.json> --replicas <1或2> \
  --devices <每进程明确卡数> --learning-gpus <物理卡列表>
```

该命令格式仅说明入口，本文没有启动观察器、模型或学习。旧 H1、旧等待观察器的停止状态和旧样本分母不改变。

## 本次 CPU 核验

新增 `tests/test_harness_optimization_admission_v019.py` 使用明确人工元数据，检查：所有 v0.18 slot/seed/recipe 精确保留；16 例密度保持 serial；逐项门未通过、证据变化、source 不同/脏、清单不同、profile 不同均拒绝；新 runtime 不能靠改 stage 绕过门；迁移禁止 restore，未测 pilot/density 不能启动；四项目严格使用同一优化绑定；两候选 GPU 资源取两组并集，四项目在学习运行时不释放。

连同现有 H2 admission、四项目选型与 continuation 控制，**15 passed in 1.36s**，改动文件 Ruff 通过。此结果验证元数据门、预算和调度合同，不能冒充真实概率、反向或吞吐通过。实际优化准入须由冻结源码下的独立 GPU 控制报告给出。


## 第二次源码边界中的必要修订

首个 b370 冻结源及其正式冷启动失败保留。随后 main 明确新增 `replicas`、`devices` 和物理卡组参数、实际优化初态身份，并由 profile factory 绑定显式 KV attention；没有热改 b370 或原 H1。原冷启动 OOM 属于该次具体路径的失败记录，不能直接归因为 high 数值精度失效。

新增单进程控制确认：没有 two-replica 证据仍可按已预声明的单进程配置通过其余实际门；声明两进程、换 devices 或改物理组约束时必须重新匹配，不自动降级。变更后针对四个已有小测试文件共 **16 passed in 1.56s**，相应 Ruff 通过；此前全库结果保持自己的源时点，未重跑或回填为覆盖后续全部变更。
