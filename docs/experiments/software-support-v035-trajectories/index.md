# v0.35真实轨迹审计包：16条逐槽分工与交互

本包抽取本轮全部16条预登记轨迹。每条都有逐项核对的分工／协作摘要、完整决定时间线和可移植原文。原R、冻结Mapper与原停止决定保持。

共710个账本决定：701次真实模型生成与9次生成前预算拒绝，实际7286778 token。抽取新增模型调用、验收执行和Mapper执行均为0。

## 共同任务与初始组织

16条都是同一新sqlparse根目标的不同预登记seed：reader.statement_records(script)使用真实sqlparse.split、sqlparse.parse和Statement.get_type()生成有序记录；report.summarize(script)消费reader结果，返回原记录、SELECT／UPDATE／DELETE三类整数计数及total。输入限合同声明的合法平面单表语句，包括空白、重复、引号内分号与可选末尾分号。完整原合同在每次实际selected输入中保留。

两名等权成员共享同一固定9B参数与团队预算，但各有私有会话和文件副本，A固定先手，初始任务板为空。任务、认领、发布、导入及提交均由实际动作产生。下表的‘先各自实现’描述写文件事实，不意味着两个早期版本均已正确。

## 阅读方式

先看每槽摘要及双方动作概况，再按原seq核对时间线。需检查具体代码、参数或模型原输出时，用文末命令查看decisions记录；需判断当时实际可见信息时，查看对应selected-inputs。两种压缩文件均为UTF-8 JSONL，可用Python标准库gzip读取，无需原运行目录。

任务创建／描述不等于已认领；认领不等于独占代码作者；固定发布不等于验收通过；导入成功受理不等于没有冲突。最终R仅来自原独立验收。原模型在message或reason中声称完成、分工或采纳，不自动成为事实。

## 逐槽入口

| 槽 | seed尾号 | 任务分工与交互摘要 | R | 原方法标签 |
|---:|---:|---|---:|---|
| [00](slot-00/trajectory.md) | 801 | 双方各写两模块；A补建并认领两项任务后提交，B在支线导入、修订并测试通过，但未发布自己的当前版本。 | 1 | own_tree_delivery |
| [01](slot-01/trajectory.md) | 802 | 双方先各自实现并公开通过；A创建的总任务被B认领，B提交原树，A导入后完成另一副本但未成功发布或提交。 | 1 | own_tree_delivery |
| [02](slot-02/trajectory.md) | 803 | B先实现并创建发布任务，A认领先提交；B导入后公开检查持续通过，但成员执行组仍判失败，最终因共享预算耗尽而结束。 | 1 | own_tree_delivery |
| [03](slot-03/trajectory.md) | 804 | B先写完并测试，A认领B创建的reader任务后提交两模块；B在支线解决导入冲突并终于另建任务发布，但未赶上提交。 | 1 | own_tree_delivery |
| [04](slot-04/trajectory.md) | 805 | A独立双模块实现后提交；B支线导入并在公开契约与自己的列表输入测试之间反复改report，最终测试通过但发布受阻、预算耗尽。 | 1 | own_tree_delivery |
| [05](slot-05/trajectory.md) | 806 | 双方先各自双模块实现并公开通过；A认领B创建的任务并提交，B导入解决冲突后测试通过，但改任务与提交均被拒后主动结束。 | 1 | own_tree_delivery |
| [06](slot-06/trajectory.md) | 807 | 双方各自实现双文件；B 发布并交付，A 导入冲突后改写通过公开测试，但未形成第二份有效交付 | 1 | own_tree_delivery |
| [07](slot-07/trajectory.md) | 808 | A 自行发布交付；B 实际读取 A 的固定补丁并修复自己的冲突树，但新发布任务来不及认领便预算停止 | 1 | own_tree_delivery |
| [08](slot-08/trajectory.md) | 809 | A 创建任务却由 B 先认领；B 独立交付，A 导入修复后仍无法发布，最后等待一个已发生的提交 | 1 | own_tree_delivery |
| [09](slot-09/trajectory.md) | 810 | 先各自实现，后由 B 导入 A 的冲突补丁并改写；B 另建“验证”任务完成最终交付，但其成员测试仍失败 | 1 | unmapped |
| [10](slot-10/trajectory.md) | 811 | B 先独立交付，A 导入冲突并改写双文件及测试，再创建自己的收尾任务形成最终 delivery-2 | 1 | unmapped |
| [11](slot-11/trajectory.md) | 812 | 双方各写两模块；B先交付，A导入后修复冲突并另建发布任务，最终交付来自A | 1 | unmapped |
| [12](slot-12/trajectory.md) | 813 | 双方先各自实现并通过公开检查；B创建的任务被A先认领，B导入A产物后修复并成为最后交付者 | 1 | unmapped |
| [13](slot-13/trajectory.md) | 814 | 双方各自实现两模块；A先认领并提交，B从冲突导入修复后另建发布任务完成第二份提交 | 1 | unmapped |
| [14](slot-14/trajectory.md) | 815 | B完成唯一固定交付；A也实现并修复三文件导入冲突，但其通过测试的支线未能再次固定提交 | 1 | own_tree_delivery |
| [15](slot-15/trajectory.md) | 816 | 双方各自重复实现却共同误设report接口；公开失败持续，反复改reader后预算停止，无任务、固定产物或提交 | 0 | unmapped |

## 本次逐轨迹抽取发现的统计勘误

上一详细报告提交9662d65将10条own轨迹中‘另一成员至少一次公开业务通过’写成9/10。原脚本实际数的是run_tests整体passed：正确口径是**公开业务与上游组均通过10/10，工具整体至少一次通过9/10**。差异来自槽02的B：原seq 300、606、657、756四次公开两组均通过，但成员自测失败，整体为false。

本包按原groups逐项统计并提供全部证据；旧派生分析文件保留以追踪勘误，详细报告同步修正。不改变任何原测试记录、R、Mapper、15/16成功率或10条单类支持结论。

## 提取范围与核验

压缩的decisions保留完整动作参数、原生成文本、assistant消息、世界工具返回及反馈；只省去重复的SDK日志、累计观测副本、累计预算账和大体积token IDs／概率数组，这些仍可按原日志路径、行号和SHA定位。selected-inputs保留701次真实调用的原请求文件文本（包含完整消息与工具定义），并保存投影和input IDs hash；没有重分词。9个被拒请求仅保有预算准备hash，未归档selected-request全文；该全文明确为null，actually_generated=false，不重建输入或补造输出。

必要核验包括每槽账本决定／实际生成／测试／token计数与封存账一致、所有tool_call和harness_tool_call完整抽取、摘要seq存在、输入准备hash对应。没有重跑模型、世界、验收、分类或全仓测试。

[独立原文核验](extraction-validation.json)逐项确认701份原输出、673个实际工具／控制动作payload与原日志相等，701份selected输入的UTF-8原字节和hash相等；9次拒绝无输出。所有原调用和动作完整、唯一对应，原seq／行号／行hash与16份源日志hash匹配。

完整selected输入包含历史多轮消息，不能把同一历史动作在不同输入中的重复出现算作多次执行；实际执行次数以decisions动作事件为准。

[机器索引与勘误证据](index.json) · [本轮详细报告](../software-support-v035-final.md)

重新抽取与合并摘要（需原归档及runs/v035-trajectory-analysis中的摘要）：

```bash
.venv/bin/python -m scripts.extract_software_trajectories_v035
```
