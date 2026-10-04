# SWE v0.31-r2 终止原因只读审计

审计时间：2026-10-05T00:15:38.377848+08:00。原运行：`runs/software-path-recovery-v031r2`。
被审计执行源码：`2456572481b01a8b6bde9cfd5fd168c35024a830`。本记录只解释原件，不修改旧调用、旧结果、分数、门槛或失败归属；下述修订方向尚未实测。

## 结论与范围

SWE worker 正常退出：supervisor与worker均为`complete`，`exit_code=0`，`stop_reason=null`，无worker异常字段。分配时间为2026-10-04T23:42:49.605282+08:00至2026-10-05T00:06:20.068668+08:00，本次完整worker成本1410.463386 GPU秒；连同旧失败和旧探针累计4491.283063 GPU秒。
路径补验以3次新调用完成，推理／训练准入及完整common恢复均通过，新optimizer step为0。随后原六合同×两seed全部12槽闭合；完整交付0/12、R=1为0/12。12份assessment均为`submitted=false`、`reason="No fixed integrated delivery"`。这不是尚未结束槽位补零，也不是GPU停止后补算失败。
顶层正常完成并不表示任务完成。episode内部包括原生输出违反格式／公开schema、保守token预约阻止下一调用、成员主动wait后无可达事件，以及实际业务动作未形成固定集成交付。现有证据不支持把全部停止归因于软件bug，也不支持把全部失败直接归因于模型业务能力。

## 资源与控制器排查

- 共269条资源观测，guard.stop_reason全部为null。
- RSS峰值15.147385 GiB，限额64 GiB。
- 旧新产物合计峰值11.011148 GiB，限额128 GiB。
- 卷剩余最低291.254803 GiB，要求至少20 GiB。
- worker.log未发现Traceback、CUDA out of memory、MemoryError或ERROR标记；末尾明确记录complete。日志中的“Agent execution pause requested”是SDK运行过程日志，不能当作外部杀停证据。
- 最后task为`close-screen-1-5`／`boundary`，是最后一个筛选槽的正常关闭边界。未观察到900秒loading/inference、600秒boundary或2400秒episode上限触发。
原件：`runs/software-path-recovery-v031r2/supervisor.json`、`runs/software-path-recovery-v031r2/swe-next-14b/state.json`、`runs/software-path-recovery-v031r2/swe-next-14b/worker.log`、`runs/software-path-recovery-v031r2/swe-next-14b/resources.jsonl`、`runs/software-path-recovery-v031r2/swe-next-14b/actual/task.json`。资源结论仅限已记录观测及终态，没有声称连续硬件测量可排除任意瞬时事件。

## 12槽原始终态

表中保留原runtime标签；`finite_task_deadline`不等于实际墙钟超时。`software_runtime_v030.py:240–241`在不存在waiting且未全部completed时使用该总括标签，真正的终止细分要看role_stops。原件统计为5槽finite_task_deadline、7槽blocked_no_reachable_events；role_stops含6次model_format_error和2次model_budget_exhausted，O1槽可能同时有另一个成员等待。

| 槽 | 案例／seed | 原episode标签 | role_stops | waiting成员 | 格式错误数 | 验收 |
|---|---|---|---|---|---:|---|
| screen-0-0 | mm-nested-order-import / 202610040701 | finite_task_deadline | member_a: model_budget_exhausted | 无 | 2 | 未提交，R=0 |
| screen-0-1 | mm-event-projection / 202610040701 | blocked_no_reachable_events | 无 | member_a | 1 | 未提交，R=0 |
| screen-0-2 | mm-envelope-hook-repair / 202610040701 | finite_task_deadline | member_a: model_format_error | 无 | 3 | 未提交，R=0 |
| screen-0-3 | mm-nested-error-repair / 202610040701 | blocked_no_reachable_events | 无 | member_a | 0 | 未提交，R=0 |
| screen-0-4 | mm-ledger-rootgoal / 202610040701 | blocked_no_reachable_events | member_a: model_format_error | member_b | 2 | 未提交，R=0 |
| screen-0-5 | mm-settings-rootgoal / 202610040701 | blocked_no_reachable_events | 无 | member_b, member_a | 1 | 未提交，R=0 |
| screen-1-0 | mm-nested-order-import / 202610040702 | finite_task_deadline | member_a: model_format_error | 无 | 2 | 未提交，R=0 |
| screen-1-1 | mm-event-projection / 202610040702 | finite_task_deadline | member_a: model_format_error | 无 | 2 | 未提交，R=0 |
| screen-1-2 | mm-envelope-hook-repair / 202610040702 | finite_task_deadline | member_a: model_format_error | 无 | 2 | 未提交，R=0 |
| screen-1-3 | mm-nested-error-repair / 202610040702 | blocked_no_reachable_events | 无 | member_a | 2 | 未提交，R=0 |
| screen-1-4 | mm-ledger-rootgoal / 202610040702 | blocked_no_reachable_events | member_b: model_format_error | member_a | 5 | 未提交，R=0 |
| screen-1-5 | mm-settings-rootgoal / 202610040702 | blocked_no_reachable_events | member_b: model_budget_exhausted | member_a | 3 | 未提交，R=0 |

每槽原件目录为`runs/software-path-recovery-v031r2/swe-next-14b/actual/<slot_id>/slot-0/`：`experience.jsonl`末条run_boundary、`runtime-state.json`和`assessment.json`共同支持表内结果。配套JSON逐槽保存路径、SHA256、run_boundary行号、剩余decision、显式wait理由及事件计数。

## 25次格式错误：原输出确实违反现有要求

| 原因类别 | 次数 |
|---|---:|
| XML参数内容异常／不完整 | 10 |
| search_file.text为空 | 6 |
| read_file.max_lines=200超过180 | 7 |
| 缺少recipient | 1 |
| 重复source_reference参数 | 1 |

25次事件的顶层reason均是`Expecting value: line 1 column 1 (char 0)`。具体原生拒绝原因仍保留在`parse_diagnostics.native_parser.failure.reason`；因此不是完全丢失诊断。发生链为原生codec拒绝XML或参数schema后不产生tool_calls，SDK再把无tool_calls内容尝试解析为显式JSON wait/done控制，第二层JSON错误成为主reason。
这会使摘要和主要反馈显得像JSON问题，但不意味着原始XML本来合法。原错误不能通过忽略空参数、裁剪值、补齐缺失参数或放宽schema改判成功。root在工具说明中发现尚未给出无参数function的完整示例；补充公开示例是拟议修订，而非本审计已证明的成功原因。

以下是实际raw assistant content，不是重新生成的示例；`<|im_end|>`如出现，是原记录内容。

### XML参数内容异常／不完整

原件：`runs/software-path-recovery-v031r2/swe-next-14b/actual/screen-0-0/slot-0/raw-transport/call-00008.finished.json`。
原生拒绝：`invalid_swe_xml_v031: Unexpected or incomplete XML parameter content`。

```text
<function=run_tests>
<parameter=></parameter>
</function><|im_end|>
```

### search_file.text为空

原件：`runs/software-path-recovery-v031r2/swe-next-14b/actual/screen-1-0/slot-0/raw-transport/call-00001.finished.json`。
原生拒绝：`invalid_swe_xml_v031: Public argument schema violation at text: '' should be non-empty`。

```text
<function=search_file>
  <parameter=path>consumer.py</parameter>
  <parameter=text></parameter>
</function><|im_end|>
```

### read_file.max_lines=200超过180

原件：`runs/software-path-recovery-v031r2/swe-next-14b/actual/screen-1-2/slot-0/raw-transport/call-00002.finished.json`。
原生拒绝：`invalid_swe_xml_v031: Public argument schema violation at max_lines: 200 is greater than the maximum of 180`。

```text
<function=read_file>
  <parameter=path>consumer.py</parameter>
  <parameter=start_line>1</parameter>
  <parameter=max_lines>200</parameter>
</function><|im_end|>
```

### 缺少recipient

原件：`runs/software-path-recovery-v031r2/swe-next-14b/actual/screen-1-4/slot-0/raw-transport/call-00001.finished.json`。
原生拒绝：`invalid_swe_xml_v031: Public argument schema violation at <arguments>: 'recipient' is a required property`。

```text
<function=send_message>
<parameter=body>Starting work on root goal. Will create tasks, implement models and consumer, run tests, and submit.</parameter>
<parameter=task_id>root_goal</parameter>
</function><|im_end|>
```

### 重复source_reference参数

原件：`runs/software-path-recovery-v031r2/swe-next-14b/actual/screen-1-5/slot-0/raw-transport/call-00039.finished.json`。
原生拒绝：`invalid_swe_xml_v031: Duplicate XML parameter: source_reference`。

```text
<function=diff_workspace>
<parameter=source_reference>{"object_id":"obj-77afcd671d61457a0df1efc9","version_id":"v2"}</parameter>
<parameter=max_chars>4000</parameter>
<parameter=offset>0</parameter>
<parameter=source_reference>{"object_id":"obj-77afcd671d61457a0df1efc9","version_id":"v2"}</parameter>
</function><|im_end|>
```

例如`screen-1-0`两次都输出`search_file`且text为空，连续格式错误到2次即停止；相应原件是`screen-1-0/slot-0/raw-transport/call-00001.finished.json`与`call-00002.finished.json`，`experience.jsonl:30`为Frozen format-error limit reached，`:31`为原finite_task_deadline标签。公开格式门为总错误4次／连续2次，本审计不修改该门。

## 两次token预算停止：实际使用量与保守预约分开

每成员原声明为64 decisions、64 HTTP attempts、500000累计token。下面两次仅触发`max_total_tokens_conservative_reservation`，未触发GPU／RSS／任务时间帽。预约算法位于`model_policy.py:466–500`：UTF8请求字节数加1024及每message/tool的64开销，再加2048输出token；它明确是保守估算，并非实测token。

| 槽／成员 | 已记账token | 下一次保守预约 | 合计 | 500000上限前实际调用数 |
|---|---:|---:|---:|---:|
| screen-0-0 / member_a | 449303 | 55698 | 505001 | 44 |
| screen-1-5 / member_b | 437655 | 63191 | 500846 | 39 |

这两次实际已报token均未到500000，停止发生在下一次采样前。现有记录不能推断下一调用实际会用多少token，不能把保守预约差额当作已发生超支。后续可评估本地实际上下文投影后的tokenizer计数用于预约，并保留500000等原预算及未知usage的保守处理；能否多完成调用或提高交付仍须实测。

最后一槽`screen-1-5`：member_a在`experience.jsonl:86`明确wait；member_b在`:708`记录上述预算停止，`:710`记录model_budget_exhausted，`:711`记录blocked_no_reachable_events。成员主动挂起且另一成员退休后，没有异步执行者或外部事件产生者，调度器关闭该episode。这个终态不是任务完成。

## 主动等待与业务交付

显式wait并非全部由预算引起。例如`screen-0-3/slot-0/experience.jsonl:188`为“Waiting for task to be claimable.”，`:190`已blocked_no_reachable_events，仍有53个role decisions；`screen-1-3`等待初始测试反馈，但该环境没有未执行的异步测试作业可唤醒成员。O1中也有成员等待伙伴发布patch，而伙伴已因格式或预算退休。
这些是模型真实选择和既定事件唤醒语义共同产生的结果，不应一律包装为调度器异常。相同地，read/search、编辑、消息、创建任务或公共测试记录均不等于固定集成交付；12份独立assessment均没有收到固定提交。新修订需要分别报告格式拒绝、工具参数拒绝、wait理由、预算边界和实际验收，不能仅以减少停止数宣称完成任务。

## Devstral仅作时间点说明

在2026-10-05T00:15:39.960331+08:00读取原v031记录时，Devstral仍为`running`／worker `screening`，GPU6、PID 3107100，已记录9槽，当前task为`screen-1-3`。这是会变化的时间点快照，不是其最终成绩。
来源：`runs/software-model-selection-v031/supervisor.json`、`runs/software-model-selection-v031/devstral-small-2507/actual/report.json`、`runs/software-model-selection-v031/devstral-small-2507/actual/task.json`。本审计未停止／重启／重判Dev，也未执行三模型最终选择。

## 最小修订方向及未验证部分

1. 工具说明明确示范无参数XML调用，强调既有非空搜索文本、max_lines上限和必填字段；不向模型提供业务答案，不修补旧输出。
2. 主反馈优先保留native syntax/schema原因，并将episode总括标签与实际role stop同时展示，避免把格式或预算停止误称墙钟超时。
3. 评估实际上下文投影后的精确本地tokenizer预约，继续保留原累计token、decision、格式与资源门；不通过简单放宽预算得出修复结论。

上述修改在本审计时尚未以新真实运行验证。它们可能改善可理解性或减少保守提前停止，但不能保证模型服从schema、主动完成工作、提交固定版本或通过独立验收。原0/12及全部旧失败保持不变；新运行应以独立修订身份、完整原12槽和独立成本记录报告。

本任务只读既有原件并写入本MD和配套JSON；没有运行测试、查询GPU、发送进程信号、启动worker、改历史文件、git提交或推送。
