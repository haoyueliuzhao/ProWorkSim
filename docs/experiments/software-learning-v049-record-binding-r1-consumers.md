# v049r1 原记录消费者与只读重物化

本修订在独立工作树 `/tmp/ProWorkSim-v049-record-binding-r1` 实施。原执行源码 `e2221fc`、原采集目录、原 entries/exports、unknown 解释、正式 R、费用与全部实际输入输出保持不动。本记录不是新采样、模型更新或私有验收结果。

## 隔离消费者

`software_member_views_v049r1` 对原共享预约拒绝规则只替换一个缺失世界身份字段的判定，改用同一已闭 episode 的原 manifest/start/end/账单/结果证明；其余请求、身份、执行前拒绝与无生成条件继续走原验证器。

本子模块新增三层隔离适配：

- `software_training_v049r1` 的 TeamValidity 使用原函数 code object 和每次调用独立 globals。原 TeamValidity 的临时视图没有档案路径；只在内存中绑定实际 episode 路径和 manifest SHA，再调用新 reader。旧模块 globals 未修改。
- 新窗口 binding 使用原 `declare_window/_declaration/expected_window/bind_rollout` 代码，只将私有 `member_view` 绑定到新 reader。导出函数的 AST 只有 Mapper 导入模块名改变；source admission、原工作证据、reward、mask 和分母代码保持原函数。
- `software_mapper_v049r1.Evidence.__init__` 使用原 Archive 构造器 code object 和新 reader；Γ1 输入读取、版本链、整文件采用、测试反馈可见性和类别判定方法保持原对象。`mapping_spec` 与其哈希未改。
- `software_allocation_v049r1.build_support_report` 只替换一个内部相对导入，绑定新的 rollout reader。原 `support_weights.build_support` 只读传入的成员视图，不再重读旧 MemberView；该 kernel 不改。`feasible_radius` 与 `select_direction` 直接复用原函数对象，类别顺序、质量、权重比例界、TV 界与原分母均未改。

四项不同纯 CPU 消费者控制通过，Ruff 通过；没有新模型、tokenizer、GPU、反向或 optimizer 工作。

## 只读入口

`reexport_closed_slot(folder, declaration, destination)`，别名 `rematerialize_closed_episode`，返回 `(entry, details)`。它只接受声明绑定的已闭 v049 O1 训练源。`prepared` 只由原 case、scenario、active roles 与冻结 reward metadata 组成，情境指纹从原 episode/start 的 Store 读取；不重建世界、不再次运行公开或私有验收。

输出必须是原槽之外的新目录。原 `training-entry.json`、`training-export.json` 若存在只作对照，不覆盖。每份新回执核对原事件、actual native request/response、所有真实 completion 行（含 token IDs、labels、mask 和概率记录）、原 reward、费用与源文件哈希不变。只有源证明支持的无生成拒绝解释、相应 record Validity 和其后 Mapper/支持结果可以改变。

## 五个原闭槽重物化结果

| 原槽 | 实际调用 | 旧 record | 新 record | 新 entry 与旧 entry 完全同值 | 修订后类别 |
|---|---:|---|---|---|---|
| LA r1 | 14 | true | true | 是 | local_lineage_delivery |
| LA r2 | 38 | unknown | true | 否，原件与实际完成行全部相同 | local_lineage_delivery |
| LA r3 | 15 | true | true | 是 | local_lineage_delivery |
| LB r1 | 34 | unknown | true | 否，原件与实际完成行全部相同 | local_lineage_delivery |
| LB r2 | 18 | true | true | 是 | local_lineage_delivery |

五槽正式 R 均为原来的 1；119 次实际调用、1,617,987 输入加输出 token 不变。LA r2 的 member_002 有29条真实 completion，其后一条共享预约拒绝原来缺少可识别身份；LB r1 两成员各17条真实 completion，其后各一条共享预约拒绝有同一问题。新 reader 从完整原档案证明这三条请求在生成前被拒绝，保持无生成，不把它们补成训练动作。

旧基础准备先按整槽 record 门筛选，因此 LA r2 整槽38条（含另一成员9条）和 LB r1 整槽34条共72条原 completion 被连带排除。只读新准备恢复这72条原材料，基础决策数47→119；旧47条已准入 decision 逐字段完全不变。全部31,747个原本人输出 token 保留，没有重建或追加目标。

同一原八槽库存用于有限支持贯通控制，其余原 LA r4、LB r3/r4 仍为 unavailable。全局成员分母因子仍为16；每 root/成员块 M=4。LA 两成员实际准入 decision 为24/43，LB 为26/26；原件目前均属于同一 local 类，部分库存的 b=1。这里没有据此选方向、追加样本、更新策略或将三条未执行槽填为0；完整窗口仍待原库存合法接续。

## 证据位置与边界

完整只读物化保存在 `artifacts/v049r1-reexport-controls-attempt1/`，包含每槽新 entry/export、源文件与数据不变回执，以及 `summary.json`、`admission-support-control.json` 和部分库存支持门控制。原数据始终指向 `/data1/zhuxinrui/projects/ProWorkSim/runs/software-learning-v049/`。

这些结果确认原记录可以充分绑定，并确认新旧消费者不会把同一已证明无生成的拒绝重新当作丢失模型输出。它们不等于概率复算、完整反向资格或学习收益；没有重新运行任何模型生成或业务验收。
