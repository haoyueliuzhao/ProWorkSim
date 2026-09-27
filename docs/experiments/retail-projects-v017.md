# v0.17 四项目固定提交与历史效用验证

本记录是 CPU 机制验证，不是模型表现、SDK收益或参数训练结果。新增正式评价分列 P1 独立质量、P2 独立质量、P3 对实际固定输入的忠实性、整体业务目标；标量 R 仅在整体成立时为1。合同与未来模型调用方式见 [设计说明](../design/retail-projects-v017.md)。

## 实际结果

固定 UCI 开发片段与 SQL 程序见证来自 v0.16，不新增解题服务。所有构建、发布、采用和固定提交均通过实际 WorldCore 操作；评价只读闭合 episode。

| 路径 | P1质量 | P2质量 | P3固定输入忠实 | 整体 R |
|---|---|---|---|---:|
| 静态交付 | true | true | true | 1 |
| 一次明确变更后交付 | true | true | true | 1 |
| 两分支共同错误、P3差额0 | false | false | true | 0 |
| 新指标＋旧分析 | true | false | true | 0 |
| 错误结果只改成功标签 | false | false | true | 0 |
| P2提交复制的结果，没有该版本真实build | true | false | true | 0 |
| P3构建后才补上游固定提交 | true | true | false | 0 |
| 先关空episode，再于活世界完成 | 后续为true | 后续为true | 后续为true | 旧0、后续1 |

混版本例中 P2 新维护义务没有固定提交，故当前 P2 责任质量为 false；P3 仍如实消费原先已固定的旧分析，不能将它的算术忠实性混同为整体版本一致。

共同错误例确实执行了双方金额均加 1 的 SQL，P3 实际差额为零；独立 Decimal 检查拒绝两条分支。无真实 build 例复制了之前真实构建的完整 JSON，另用 write_object 产生新结果版本；新版本没有内核构建证明，复制 `execution` 字段不能通过。后补固定提交例发生在同一个世界且最终所有项目都有提交，但上游提交晚于 P3 构建，正式 P3 合同仍拒绝。

后续回填控制先固定一个无提交的早期 episode，再在活世界继续全部实际工作并关闭另一个 episode；旧档案反复读取仍为0，旧 end-state SHA 不变，后续 episode 为1。未修改旧文件或用当前 workspace 替换旧输入。

最终8条路径共 **367次真实工具调用、9个闭合CPU episode**。3项定向 pytest 通过：新增积分语义、模型工具隔离/初始化无自动成果、四角色 native 采集器的明确 fake transport 控制（每角色生成一个 done，4次人工响应，0业务动作，R=0）。这个 fake transport 不计真实模型或 SDK 运行。新增/触及文件 Ruff 通过，未重跑旧全库。

## 失败保留与最终只读核验

首次开发运行 `runs/retail-projects-v017-cpu/` 的8条路径均在第一次 adopt 处停止：CPU脚本将原 `read_object` 的 `artifact_id` 表示直接展开到要求 `object_id` 的参数。修订了见证脚本的规范引用转换，未改变世界规则、奖励或模型响应。首次所有原始记录保留，不解释为模型失败。

修订后 `runs/retail-projects-v017-cpu-r1/` 全部预定结果成立。之后给整体目标补上其已经公开声明的发布义务合取，直接对原不可变快照重新评价，没有重复 SQL 或世界动作；全部结果不变。最终正式核验保存在 `runs/retail-projects-v017-reassessment/`，归档摘要见 [最终控制记录](retail-projects-v017-controls.json)。它保留各 episode manifest SHA、终局维度、发布条件及早期档案不变检查。

复现新路径须用全新输出目录：

```bash
.venv/bin/python -m scripts.retail_projects_experiment_v017 --output <new-output-directory>
.venv/bin/python -m pytest -q tests/test_retail_projects_v017.py
```

## 尚未测量

选定共享模型的四项目运行尚未启动。已准备静态2次和变更2次的固定计划与注入 owner 的采集接口；正式运行需绑定 H1 选定组合，记录实际token、错误、每角色机会、业务分项及资源。不能据 CPU 路径推断模型会自主协调，也不能将同一 UCI 片段的四次计划称为独立来源泛化。

业务标量接口已经正式化，但四项目的成员动作投影和训练更新尚未实现；本次不声称四项目已进入参数训练或 ID-VTDO 支持池。短责任学习线可以独立继续。

## 执行 CLI 与补充 SDK 控制

实际选中模型入口 `scripts/retail_project_model_v017.py` 已完成：只接受 H1 最终选中组合；复用其基础权重、profile/recipe与初始化，固定4槽、0更新，保存所有学习/RNG guard及源码/actor身份。显式资源变化仅允许设备数与理由另录。两个纯元数据/执行控制通过（0.09s）：选择不符或尚未结束拒绝、profile其他参数不可暗改、unknown第一槽后不重试且三后续槽保持未启动。

补充两项真实SDK、人工transport控制，均禁用CUDA，在 `runs/v016-sdk/resident-venv` 执行：

| 控制 | 结果 | 时间 |
|---|---|---:|
| 真实四角色SDK采集，逐角色仅人工done响应 | 1 passed，4请求、0业务动作、R=0 | 12.37s |
| 真实新义务触发同SDK会话重新生成 | 1 passed，私有note和计数保留，meter 2→3 | 9.83s |

两次均有上游Pydantic的ReadOnly类型提示警告，没有测试失败。第二项修复了仅清外层stopped但SDK内部仍保留done锁的问题；修订局限于新四项目派发，不改变H1源树、不重跑H0或H1。

本轮默认环境全库与Ruff最终记录另见 [验证清单](harness-v017-validation.json)，其计数不与上述另一Python环境的SDK控制混合。真实四项目模型结果仍须在H1选择收口后产生，以上控制不替代它。
