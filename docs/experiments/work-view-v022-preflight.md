# v0.22 W1：公开复核合同、新材料和确定性工作视图

本记录覆盖 W1 的来源与 CPU 准备，不报告真实模型收益。六个新开发情境及两臂的 12 个槽已固定；另四个训练候选和两个桥接开发候选只保留材料，未运行、未置为可训练。机器归档为 [work-view-v022-preflight.json](work-view-v022-preflight.json)。真实 W1 模型执行应由其独立冻结报告记录，不能把本轮 CPU 假传输控制计进去。

## 1. 新材料的行谱系与用途

新材料来自同一份 UCI Online Retail 原始 XLSX，SHA-256 仍为 `43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16ae4c3936424676d`，许可、DOI 和归属沿原始来源保留。实际扫描完整原文件，排除 v0.15 的所有 train/development/locked 切片，以及 v0.16 harness 切片中的 **30 位客户、90 张发票、438 个原始 SourceRow**；v0.21 材料属于其中已有开发切片。

剩余候选客户须至少有两张非取消、2–10 行的完整发票和一张 1–10 行的完整取消发票，每张票只有一个非空客户，价格精度不超过两位。客户按 `SHA256('collaboration-v022:'+CustomerID)` 排序，固定取前 24 位并顺次配对；每位客户取字典序最前两张常规票及最前一张取消票。此规则使用来源结构，未读取目标模型成绩，也没有按预计答案或容易完成程度补采。

实际获得 **12 个新切片、24 位新客户、72 张完整发票、339 条原始行**。客户、InvoiceNo 与 SourceRow 在新切片间以及与上述旧材料间均不重叠。每条保留行含原 XLSX 行号，完整发票行数、SourceRow 清单／SHA、切片内容 SHA 均写入 [source-manifest.json](../../examples/retail-collaboration-v22/source-manifest.json)。这保证同源实体和行层面的隔离，不声称新增独立来源或完成语义模板去污染。

| 材料编号 | 用途及职责 | 客户 | 原始行数 |
|---|---|---|---:|
| 00 | W1 实现 | 13549、16013 | 24 |
| 01 | W1 实现 | 12647、15754 | 29 |
| 02 | W1 正确初稿复核 | 12727、15874 | 28 |
| 03 | W1 错计数初稿复核 | 12678、16235 | 34 |
| 04 | W1 联合 A | 15140、17381 | 23 |
| 05 | W1 联合 B | 15251、15841 | 29 |
| 06 | 保留训练：实现 | 15144、16473 | 20 |
| 07 | 保留训练：复核 | 13534、16996 | 27 |
| 08 | 保留训练：A | 12778、14341 | 33 |
| 09 | 保留训练：B | 13658、17730 | 33 |
| 10 | 保留桥接开发：A | 15602、18030 | 21 |
| 11 | 保留桥接开发：B | 14198、16330 | 38 |

每个切片均为两位客户、六张完整发票。上述质量词是 host 目录字段，不放入模型任务或公开工作状态；模型仍须检查真实提交内容。保留用途的 `model_training_eligible`、`source_admission` 均为 false，材料存在不能替代真实训练投影、当前策略身份、学习概率及反向资格。

固定 manifest SHA 为 `5e5e225c32ea9fa05d4c53985d5b86bf5c905904400e12157f0153feaea0808e`。运行素材在 `runs/assets/uci-collaboration-v022/`；加载器逐项核验 source-controlled manifest、切片 SHA、原文件身份及实体／行排除。冻结 worktree 应显式传入实际 assets_root，不能依靠另一个 worktree 的相对 runs 路径。

## 2. 两臂共同使用的新公开合同

职责仍是**当前固定材料的结果表**，没有增加任意未来输入的通用查询／管线测试，也没有事后否定 v0.21 固定实例成功。

两臂同时公开 `public-result-review-contract-v0.22`，在实际 work requirements 和角色任务中说明：

- 合格 blocking issue 的 target 必须是 `inspect_submission` 得到的准确固定 **result** 对象与版本；通用工具能存储代码问题，但代码定位本身不完成本结果表复核职责。
- 行级 locator 为 `['tables','metrics','rows',i]`，单元格级为再加 `j`；i、j 均是对应固定表实际数组的**零基整数索引**，不是客户 ID 或 SQL 偏移。
- 行级问题主张该实际行至少一个业务单元格错误；单元格级问题主张指定列错误。
- evidence 必须显式包含**该提交采用的 data**和**复核者已读且适用的 audit_basis**准确对象／版本，两者都须在判断前读取；正文提到数据或只引用代码不能替代 data reference。
- 正确初稿可以直接有据批准，不要求制造问题或返工。

结构示例只含 `<fixed_result_object_id>`、`<zero_based_row_i>` 等占位符，没有错误行位置、正确数字或参考 SQL。实现者也明确知道 `requirements.online_scope` 是观察字段，不是一个文件 alias。这些公开说明两臂相同，不能把 W1 与旧 E 的成绩差直接归因于上下文呈现。

新世界与准备沿用 WorldCore、原真实交接／采用／build／固定提交生命周期和独立 Decimal 评价。A 的交接与实际使用、B 的正确无修复／自检修复／有据反馈修复责任不变。v0.21 评分器仅抽取内部 resolver、reward、report version 和 Mapper 参数；旧公开入口仍绑定原目录与合同，旧 E 记录和分数没有重算。

## 3. 比较条件和顺序

[固定目录](../../examples/retail-collaboration-v22/catalog.json)含 W1 六例以及全部 12 个预定槽。每一情境两臂共享采样种子 `202609290100 + case_index`；偶数情境先 `original_history`，奇数情境先 `compact_work`，不从多次中选优。

角色机会沿 v0.21：实现各 12、复核各 12、A 为 provider 6＋implementer 16、B 为 implementer 24＋reviewer 28，每臂共 122 次决策上限。工具、模型、16,384 总长度、2,048 输出上限及终态业务职责保持一致；wait/done、格式失败仍消耗原机会，不扩额、不自动提交或生成问题。

`original_history` 精确继承 v0.21 实际采用的 `latest_observation` 组织：保留最新注册观察，其余真实对话历史继续保留。该臂名称不表示改成字面上的全量旧观察重复。`compact_work` 使用同一原始角色 memory，在请求前做确定性投影。

## 4. 紧凑视图的权限和证据边界

实现为 `proworksim.work_view_v022.CompactWorkModelPolicy`；原臂为 `OriginalHistoryModelPolicy`，类身份明确不同。公共入口 `runtime(owner,prepared,folder,arm)` 返回标准 StaffRuntime、独立 capture 和接口字典；没有修改通用 ModelPolicy、online_training 或 member_views。

投影函数只接收**该角色已保存的实际 messages**，没有 world、store、其他角色 memory 或评分器句柄。它不发工具查询、不读取未见材料、不猜测适用依据，也不把“已读”提升成“理解／采用”。

具体规则固定如下：

- 保留原系统协议；保留当前真实授权观察及公开规则，仅删除逐字重复目标与重复的同一 review contract，保留不重复的 visible requirements。
- 保留每个准确对象／版本的最近一次实际读取结果、各固定提交的实际 inspect 返回、最近实际 read_messages，以及实际 build/query 返回。选中的 tool message **原样保留**，配回真实的 assistant tool call。
- 从选中合法 tool call 中删去自由文本前言，保留真实工具名称和参数；保留最近两次工具反馈及合法 wait/done 的实际控制返回。
- 最新一次格式失败的原 assistant 输出以明确的“被拒输出数据”形式保留，与其真实 public_format_feedback 一并呈现。所有原始失败文本与历史始终留在原 memory 和日志，没有清空错误计数或修复输出。
- 当前视图附本角色动作索引：真实操作、作用域参数、引用、状态与原消息 hash。该索引不携带新业务计算，也不称某动作已经满足隐藏正确性条件。
- 被移出的世界资料仍可用原授权读取工具取得；旧 assistant 自由文本保留在原始记录，本设计没有把它改写成一份“知识摘要”。

每次选择记录原始和实际发送消息 SHA、选择／移除索引及投影种类。选中的真实读返回仍与原消息逐项相等，使固定评分器能够核对证据是否实际出现在消费请求中，而非仅因曾经读过就默认可用。

## 5. CPU 控制、失败和限制

六个 W1 新世界均已实际 CPU 初始化。必要端到端控制使用明确的假传输响应，通过真实 ModelPolicy、StaffRuntime 和 WorldCore 执行同一错计数复核路径。两臂均有 9 次机会、6 次真实 world 动作，包含一次合法 wait、一次达到输出上限的格式反馈、实际固定提交／材料读取、合格 issue 与 done；独立评分均为 1。两臂准备后的业务状态 hash 相等，原始 memory 未被投影修改，选中工具消息原样进入后续请求。

这条控制的最高请求大小由原臂 64,208 bytes 降到紧凑臂 58,576 bytes。**它只是这条 CPU 假响应路径的字节统计，不是 tokenizer 长度测量、GPU 加速或真实模型任务收益，也不保证所有真实请求都能容纳。**

首轮控制因 CPU 夹具返回了过时 tuple 而非要求的原始响应 envelope，两臂均在首请求以 `invalid_transport_response` 正确停止，评分 null、world 动作 0。该现场保留在 `runs/work-view-v022-cpu/`。仅修正假传输夹具，使用新目录 `runs/work-view-v022-cpu-fixed/` 完成上述控制，没有改变生产拒绝规则或掩盖失败。

三项必要定向测试 **3 passed，0.06 秒**：材料与旧来源实体／原行隔离、保留用途与交错配对；纯视图的准确返回、控制和格式原文保留且 memory 不变；异常消息 fail-closed 与公开 target/locator/evidence 结构。涉及的六个 Python 文件 Ruff 通过，未重复全库、旧 E 六例或目标模型。原始报告与 JUnit 的路径、SHA 见机器归档。

## 6. 运行接口与后续边界

```python
from proworksim.templates.retail_collaboration_v022 import registry, build_case, assess_episode
from proworksim.work_view_v022 import runtime

catalog = registry()  # situations6，reserved_training4，reserved_bridge2，ordered_slots12
prepared = build_case(case_id, new_world_directory, assets_root=actual_asset_directory)
runner, captures, interfaces = runtime(owner, prepared, run_directory, arm)
# 由既有 begin_episode/run_fragment/finish_episode 执行固定机会；结束后：
assessment = assess_episode(closed_episode_directory)
```

来源准备可通过 `python -m scripts.import_retail_v022 --output <new-directory>` 重复执行固定选择；已有正式素材不会覆盖。实际目录必须与归档 pin 内容相符。保留训练／桥接素材需要独立准入和真实经历投影，不能把 `model_training_eligible` 改成 true 就启动训练，更不能把这些 CPU 程序响应当教师样本。

W1 的模型记录应报告完整职责、有据复核、A/B 闭合、首次正确 build 与正式提交／判断时点，以及实际生成、格式和上下文终止。改变公开合同和呈现构成新的 Γ；旧 E 的正确诊断、0.25 及其他原结果继续保留。模型学习效果还需要同一冻结 Γ 下的初末评价，不能由本次接口改善推导。
