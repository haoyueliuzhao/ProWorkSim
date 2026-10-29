# v078：闭合任务遗留于暂停API调度记录的修复

v072队列在暂停新派发后，最后一题已经完成，但调度器进入准入等待循环，继续更新progress而没有刷新cursor。于是progress显示实际生成future为0，cursor仍将slot3083列为在途，阻碍只读交接器确认静止。这是可变调度记录滞后，不是新的模型失败。

只读核验确认：slot3083为 `sympy-20428 / DeepSeek PROJECT / 5M`，原不可变result已closed，共52次调用、4,450,100个已知输入加输出token。原generation_finished事件、actor/controller/volume清理及释放凭据齐全，官方代码评分也已有completion。修复不修改这些原件，也不改变评分结果。

`tools/reconcile_idle_api_cursor_v078.py --apply` 在原分配锁下再次核对：旧API明确暂停、进度新鲜、实际future为0、没有API物理预约或在途计费请求、旧协调器身份及暂停门仍有效。随后完整归档旧cursor、progress、控制文件和events，从原result补入唯一已闭合generation，并清除对应过期active项。新的cursor记录独立修复证据；评分、交付、待派发身份、费用账本和运行源码保持。任何证据不符则拒绝更新。

这是已完成事件对可变checkpoint的一次对账，不是重新生成、重新评分或重新选择候选。原cursor与修复后副本都保留；交接器可以继续导入已有结果和评分。实现通过4项必要CPU控制及Ruff，真实只读检查确认当前唯一条目具备修复条件。验证见 `artifacts/software-benchmark-v078/idle-api-cursor-validation-r1/validation.json`；实际应用凭据由工具写入 `artifacts/software-benchmark-v078/idle-api-cursor-r1/`。
