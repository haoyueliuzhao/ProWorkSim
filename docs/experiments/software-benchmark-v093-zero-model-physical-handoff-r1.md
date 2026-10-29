**v092 零模型初始化失败与 v093 物理身份交接审阅**

44 个已授权恢复回合尚未调用模型。v092 为每题取得 actor 的宿主容量预约后，检查执行计划中的 `host_cpu_pool` 时失败；计划漏了该字段。失败发生在导入 Docker、创建客户端和创建容器之前。不能把调度器的 `entered=true` 解释为模型已运行，也不能把这 44 项初始化错误统计成模型修复失败。

逐题只读核验结果一致：`model_calls=0`、`model_dispatch_started=false`；没有 `entered.json`、`model-dispatch-intent.json` 或 `host-api-counts`；每题仅有 execution-intent、public-context-provenance、quiescence、result 四个文件。三张 API 账表中，对应 44 个逻辑身份的 requests、response_observations、provider_protocol_events 记录均为 0。44 份 actor 容量预约已释放，无 controller/volume claim，quiescent 全为 true，未知创建结果、清理错误及残留对象均为空。此检查无需调用 Docker 管理接口。

**模型尝试未消费，旧物理预约身份已经消费。** 因此可以继续用户已经授权的同一批 44 个恢复回合，但不能覆盖 6000–6043 的失败记录或重用其已消费 claim。

| 项目 | 必须保留 | 新部署允许改变 |
| --- | --- | --- |
| 模型尝试 | 同 44 个完整 slot_id，后缀 `:recovery-v089-r1`，`recovery_attempt=1` | 不新增第二次模型采样 |
| 模型条件 | 原任务、seed、REF/PROJECT、思考模式、5M 上限、模型及工具配置 | 不改变评测设置 |
| 物理身份 | 原 6000–6043 失败记录及释放凭据 | 一一映射到 6044–6087，规则为原 index＋44 |
| API 费用 | 原人民币 1,700 元总账及所有历史费用/未知预约 | 不重置、退款或增加 token 额度 |
| CPU 池 | 原 v066 固定只读 CPU 清单及 SHA | 新执行计划补入该既有引用，不重新配置服务器 |

完整的 44 项映射、源文件 SHA、零用量与资源释放证据已封存：[交接摘要](../../artifacts/software-benchmark-v093/zero-generation-physical-handoff-r1/summary.json)；逐题文件布局见[只读审计](../../artifacts/software-benchmark-v093/zero-model-rebind-audit-r1/audit.json)。6044–6087 在取样时均无已有 episode 或 resource claim；新 manager 启动前仍须核对未占用，不能把历史快照当成永久空闲保证。

推荐将**逻辑账本注册表与物理执行映射分开**：预算端继续使用 v089 原 6000–6043 canonical registry 和原 inventory。`validate_retry_registry()` 明确绑定这个范围，不应直接扩大范围来绕过身份检查。新物理执行计划只改 index 与相应 config 引用；新 config 的内容须严格等于原 config，仅 `slot_index` 变为映射的新值。原 slot_id、original_slot_id、original_slot_index 与 recovery_attempt 均保持。

另一个必须处理的边界是 `DeepSeekRuntime.transport_factory()`：它同时比较 slot_id、slot_index、configuration 等字段，直接传 6044 的行给原 canonical broker 会被拒绝。新包装层应先用封存映射完整核验物理行/config，然后把对应 canonical 行传给原 factory，输出目录仍使用新物理目录。原 factory 的同 slot_id 已有请求禁止重采、`:0001` 起的请求 ID 格式、512 次上限、费用和工具检查都保留。不能删除 index/config 检查后任意放行新行。

新 scope 还应单独绑定：v092 已结束且无在途任务/评分、旧 manager 已退出和租约释放、新物理映射及新源码、同一个原44回合授权、同父资源组生命周期。不能沿用“44 物理身份从未消费”的旧交接断言；本轮只有模型尝试和 Docker 创建未消费，actor 容量 claim 已经消费并释放。新资源表按原角色数量重建（44 actor、44 controller、44卷、44代码评分及23交付评分）；这是原范围的首次实际 Docker 执行，不应被记成额外 44 个模型回合。

本审阅没有修改旧源码、原失败记录或账本，没有启动服务、容器、网络请求或模型。零请求证据只对应取样时刻；新部署初始化前再核对每个未消费逻辑 ID，此后由既有逐槽反重采检查保护，不能要求开始正常运行后的整批账表仍永远为零。宿主旧 manager 退出证明由新部署交接另行核验，本文件不把已生成最终 summary 等同于直接观测 PID 已退出。
