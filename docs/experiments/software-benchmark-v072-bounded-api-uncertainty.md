# v072：完整费用预约下隔离 API 未知结果

本次修订只改变宿主对“结果未知但最大费用仍被完整保留”的准入判定。原两笔请求、实际已知 token、未知 token 和费用记录均不改写，不补发旧请求、不恢复旧已消费任务，也不新增 1500 元额度。候选源码和恢复库存已经准备；真实启动需使用这份新源码的独立授权，不能假称旧 v069 source index 覆盖了新实现。

## 已核对的停止原因

v069 在北京时间 2026-10-28 21:16:41.149413 记录 `provider_stopped: api_shared_halted`，21:17:53 左右完成自身收口。首先变为 uncertain 的请求是原 episode1165、`django-13401/REF/B5000K` 的 condenser 第25次请求，账本记录 `TimeoutError`。其预约时间为21:14:40.554404。

另一笔为 episode1144、`django-16255/PROJECT/B5000K` 的 agent 第10次请求，21:16:40.100718 预约，之后记录 `AttributeError`。第一次 provider-stop 的观测中，该笔仍为 reserved；最终账本为 uncertain。旧 runtime 的 provider stop 会取消全部在途 API socket，因此第二笔与取消时序相符；但是原始底层异常堆栈没有保存，不能把 socket 关闭竞态断言为已证实根因。

两笔都没有 `response_observations` 或 `provider_protocol_events`；`usage_json`、response ID/model/hash、settled 金额等字段均为空。对应 controller 只保留 `request-0025.json` / `request-0010.json`，没有同号 response。两项清理证明均为 `quiescent=true`、无 cleanup errors，actor/controller/volume 已移除。没有可用的权威响应可真实补结算；当前不能把未知使用量改成0。

当前账本快照如下（保守记账上界，不冒称供应商发票金额）：

| 字段 | 值 |
|---|---:|
| 已结算请求 | 13,198 |
| uncertain 请求 | 2 |
| reserved / inflight | 0 |
| settled upper | ¥416.27869316 |
| uncertain 原预约合计 | ¥10.48576 |
| committed upper | ¥426.76445316 |
| 原 ¥1500 内剩余可预约金额 | ¥1073.23554684 |

metadata 没有 `halted` 或 cooldown，连续系统失败计数为2。真正导致全 API provider 停止的是 v067 wrapper 的“存在任意 uncertain 就 shared_halted”规则；原底层金额账本仍把 uncertain 计入 committed，并未判断它们无费用上界。

## 完整上界证明及停止边界

原 policy 的单笔绝对预约为 `1,048,576×2,000 + 393,216×8,000 = 5,242,880,000` 纳元，即 ¥5.24288。它按原 provider 绝对输入/输出上限和峰时单价计算，覆盖本次实际请求的 prompt 上界4,658/65,970与输出上限32,768。两笔原预约均完整保留，合计 ¥10.48576。

`software_benchmark_deepseek_budget_v072` 在同一只读事务中复用原预算判断，并逐笔校验 uncertain：

- 原完整 policy、模型/价格/额度/并发身份必须一致；status 只能是 settled/reserved/uncertain。
- uncertain 必须属于合法原5M slot/condition/request序号，prompt/output 边界合法，完整绝对预约一分不减，所有真实结算/usage/response字段仍为空。
- 只接纳原 client 留下的明确 transport/本地响应处理失败记录；存在未处理的 response observation、protocol event、部分预约或身份矛盾仍阻止准入。
- metadata.halted、401/402/403 等原硬停、现金不足、账本不可读及原 cooldown 保持有效。连续失败达到原阈值时仍退避；不借此自动重发旧请求。

原 `BudgetLedger.reserve` 的事务和总额检查未变。新请求仍要求“全部已结算 + 全部未知完整预约 + 在途完整预约 + 新最大预约”不超过1500元。若以后出现同合同下可完整定价的普通未知结果，只关闭该任务并保留其预约；真正无价格上界或账本/身份完整性异常仍会停止 provider。

## 新恢复范围与源码边界

新根为 `runs/software-benchmark-v072/api-5m-bounded-uncertain-r1`。不可变库存保留原两个500任务分母，目前新允许779个身份（REF390 / PROJECT389），明确排除全部旧 entered/scheduled、actor/controller/volume claim、API request、候选或部分 episode 目录。旧 provider 暂停生成的纯未开始占位记录不冒充已消费任务；但任何曾 scheduled 的身份即使0请求也不自动重放。

新 runtime 同时替换预检与 transport authorization 闭包内的预算函数，只替换外层 runtime 会让旧闭包再次全停。替换发生在私有函数命名空间，冻结 v064/v067/v068/v069 源与 globals 保持原样。任务执行仍用已批准的 v069 18-lane 资源实现，新的 source seal 另外约束 v072 预算策略、runtime、runner、库存与 launcher，并交叉绑定 v069 授权。

新普通用户 unit 为 `proworksim-v072-api-5m.service`，CPU168–171、4 CPU/16 GiB、0 swap；自己的 auxiliary claim 计入原152 CPU/832 GiB共用池。Qwen 实际模型/actor 预约、评分余量与物理门继续实时扣除，不重启或操作 Qwen，也不承诺固定 API 实际并发。

## 必要 CPU 与文件准备结果

预算模块14项 CPU 控制通过（0.28秒），覆盖完整未知费用继续扣款且不能重放、部分预约/身份/usage/响应矛盾拒绝、原硬停/cooldown/现金上限。runtime、库存过滤及独立输出路径3项控制通过（0.15秒）；新增完整队列集成控制另1项通过（0.21秒），证明保留两笔未知预约时仍可调度独立任务，某个任务正常清理后的 technical_unknown 不阻停其他任务。上述新代码限定 Ruff 均通过；没有重复运行无关旧测试。

实际只读 preflight 已验证779个新允许身份，旧两次中性资格合计799 token（747输入+52输出）原样复用；client与token counter均未初始化，新增API调用0。只执行了文件准备：库存 SHA256=`63d753c6c4e980c9f1ef79f77214245ace82109851656e7feb56a5f6af72bfdf`，费用证明及逐槽排除理由位于 `preparation-snapshot-r1/`，新 unit 规格已生成。尚未调用真实 launch、停止服务、改账或消耗新任务。

可审阅启动流程为先运行 `tools/prepare_api_continuation_v072.py --authorize` 封存最终源与规格，再运行 `tools/launch_api_continuation_v072.py --launch`；后者只启动这一个新 API unit。此文档中的准备状态不替代后续真实运行结果。
