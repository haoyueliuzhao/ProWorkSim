# v0.32 实测终态：接口修订完成，第三条工具选择未过准入

记录时间：2026-10-05T00:36:00.231617+08:00。源码`b9af2331caea930eb420ce29cac95504766e47ac`。本页解释本次实际终态；完整计划和引用见[自动运行报告](software-harness-recovery-v032.md)、[修订协议](software-harness-recovery-v032-protocol.md)及[旧12槽终止审计](software-termination-audit-v031r2.md)。

## 已完成的修复

补齐按公开schema生成的无参／可选参数说明；SDK主反馈优先呈现真实原生parser错误，保留二次adapter诊断；resident预算使用选中prompt的实测token加原输出上限，绑定实际请求与actor，保留500000总帽；终态增加具体role停止原因。原parser、概率门、格式错误2／4限额、64决定、业务验收和模型权重保持。CPU必要控制已通过，命令与分支范围见协议。

## GPU4预约、交接与本次成本

按用户要求先预约GPU4，连续持有1201.250108秒后于2026-10-05T00:28:31.410917+08:00交接。预约未调用模型；即时容量检查通过，无额外空卡稳定等待。新worker PID `3283503` 从2026-10-05T00:28:36.110470+08:00至2026-10-05T00:29:54.877165+08:00占用GPU4，完整worker成本78.766694 GPU秒。继承全部旧SWE成本后累计4570.049757 GPU秒；不把预约时间混入worker成本。

worker正常退出码0，stop_reason=null，终态qualification_failed。GPU4已由实验进程正常释放，没有继续循环采样或新业务worker。自动归档与推送成功，报告提交`a6fd4ade5857b7f7d19f452c0ef85c6f9cbf4642`。

## 三次新调用和概率／反向检查

| 调用 | 输入／输出token | 实际工具与参数 | 指定操作通过 |
|---|---:|---|---|
| read_initial | 626 / 10 | `read_public_note({})` | True |
| record_fact_8k | 8185 / 38 | `record_fact({"code": "NATIVE-DIAGNOSTIC-AMBER", "revision": 17})` | True |
| missing_file_feedback_10k | 10229 / 10 | `read_public_note({})` | False |

首次真实零参数读取成功，没有空名称parameter，也没有使用一次纠正机会；第二条正确记录已读事实。第三条公开请求明确要求在实际missing-file异常后调用record_fact记录已读code/revision，模型输出却为read_public_note({})。该输出格式和schema合法，但工具选择不满足本次操作要求；没有parser异常或模型调用错误。此处的失败是指定操作门不通过，不能误写为数值或无参语法失败，也不能把它改为通过。

三条trace均完整保留，no-grad和grad-mode重算max／mean误差全部0，全部原输出完成3/3反传，有限actor梯度的非零元素为2359296。零step检查耗时50.374437秒，整体短补验58.894274秒；actor／critic新增optimizer step均0。受保护状态、原common、RNG与optimizer对象检查通过，诊断梯度已清空。峰值allocated为39412199424字节，reserved为41632661504字节。

`training_integration_ready=true`只表示本次完整数值路径通过；`inference_ready=false`、`training_ready=false`保留第三条指定操作失败。近16K、诊断更新、重载和新身份回流是原v0.31继承证据，本轮未重新进行，不能把它们列为本次新增成功。

## 旧预算停止点的真实tokenizer重算

另以冻结`b9af233`的新手册／预算链路及同一本地SWE tokenizer，在CPU上重算两次旧预算停止请求。旧停止发生在model_attempt之前，没有该次完整raw-transport请求文件；从既存真实消息和SDK事件逐条按SHA恢复，整条request SHA与原started事件完全匹配后才计算。不存在补造或猜测消息。记录包括原始引用、tokenizer文件哈希、完整恢复验证、选中请求和新预约，见[预算重算JSON](software-harness-recovery-v032-budget-replay.json)。

| 旧停止点 | 已记账token | 原字节预约 | 原合计 | 新实际输入＋2048 | 新合计 | 原500000门 |
|---|---:|---:|---:|---:|---:|---|
| screen-0-0 / member_a | 449303 | 55698 | 505001 | 10200＋2048＝12248 | 461551 | 通过 |
| screen-1-5 / member_b | 437655 | 63191 | 500846 | 11714＋2048＝13762 | 451417 | 通过 |

两条均在原16K容量内，不需要删除历史工具轮次；旧UTF8公式也精确复现。模型对象构造0、生成0、GPU使用0、optimizer step 0，CUDA未初始化。此结果证明新预算算法会允许这两条SHA绑定请求继续调用；并未真正续跑旧机会，不能说明随后模型会交付成功，也不覆盖旧结果。

## 没有启动的部分与其他进程

本轮新正式业务经历为0，12个预定槽均未启动，不能补为0/12成绩。旧r2真实闭合12槽的0/12保持。新精确预算链路已通过CPU控制；由于未进入正式SDK业务采集，本次GPU验证没有产生新业务预约／完成配对证据，不能宣称已改善实际工作完成率。

Devstral读取时为`screening`，闭合11 / 12、完整成功4，当前task为`screen-1-5`。其原GPU6进程与冻结源码不受本轮控制；此为时间点状态，最终结果由原批次报告记录。

没有三模型最终选择、参数训练收益或分配算法收益结论。接口修订的实际作用需后续独立明确的实验验证；不能从一次技术调用成功、此次失败或CPU控制推出整轮业务的因果结论。
