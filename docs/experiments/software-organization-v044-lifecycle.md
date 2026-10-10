# v0.44：原始成员结束控制与退休事件的只读关联

本修订仅完善工作使用测量器。它不改变模型输入、世界行为、业务验收、原始轨迹或正式 R。原 v0.43 `work-use.json` 保留原结果；最终新测量文件另存于 `runs/v044-controls/work-use-remeasurement-final/`。

## 原缺口

v0.43 PT 的原工作链指标为 `has_evidenced_cross_member_chain=null`。唯一测量缺口是 `member_001` 的 `member_retired` 事件（世界事件 35、`action-35`）没有直接匹配到原测量器登记的模型世界工具输出。

真实执行分为两个连续阶段：成员先通过 `staff_done` 产生正常结束控制，控制返回 `worker_state=done`、`world_effect=false`；组织运行器看到本次机会的 `completed` 结果后，再以该成员身份执行并记录 `retire_member`。原测量器只关联自带世界 `action_id` 的工具输出，因此遗漏了这一桥接。这个测量缺口没有改变 PT 的原验收结果 R=1。

## 新测量规则

新入口是 `scripts.measure_organization_work_v044.measure_episode(episode_dir)`。它复用未修改的 v040 工作使用测量，仅在完整证据成立时补充退休事件的模型归属：

1. 原团队账本中的调用已经开始生成并结算，原成功尝试、selected 请求、输入 ID 哈希、原响应 ID、响应正文哈希、用量、冻结 actor 身份及执行窗口一致。窗口同时属于该槽。
2. 原输出确实是单个 `staff_done` 调用，或者运行器原本接受的精确 JSON `done` 控制。后者还须有原 `harness_explicit_json_control` 转换回执及原 SDK 的 `control-<call_id>` 标识；不冒称 native tool call。只读取旧输出；不重新运行 native parser，不补造或修正控制。
3. 原 policy decision、harness 调用、控制工具返回和 `model_control` 绑定同一成员、call、tool call、decision、opportunity，顺序一致；实际返回须为该原因的成功 `done`，不能仅凭模型自述。
4. 对应调度机会及正式边界均记录该成员 `completed`，而非系统超时、权限错误、管理员操作或调度停止。该控制自身没有世界动作。
5. 原 selected 输入的成员、世界实例、分支、项目与逻辑时点对应退休事件；世界 interaction、operation commit 和成员 registry 进一步确认同一成员实际提交了该 `retire_member` 动作，原因及真实退休输出完全一致。

只有以上关联成立，才移除对应的单个 `member_events_without_actual_output_binding` 缺口，并增加该成员已归属退休事件计数。其他缺口、语义候选、未支持关系及已经成立的跨成员工作链都保留。跨成员指标仍按原完整证据规则计算：退休本身不产生合作、业务成功或因果贡献信用。

仅有 `staff_done:` 原因文本、终止状态或相近时序均不足以关联。来源不明、记录缺失、身份或窗口矛盾、多个候选控制、非模型来源等情况保持未解决，不把原 `null` 自动改为 `false`。

## 必要控制

执行 `.venv/bin/python -m pytest -q tests/test_measure_organization_work_v044.py`：最终 18 项通过，0.20 秒。控制使用有限合成 JSON/AST 记录，不运行世界任务、模型、tokenizer 或验收。

正例覆盖原 native `staff_done` 与精确 JSON `done`；反例覆盖系统超时、管理员和调度来源，以及缺失或重复控制、actor/call/action/window 不匹配、未提交世界动作、调度超时、控制输出矛盾和输入时点不符。JSON 控制另覆盖缺失原转换回执及伪造 SDK 控制标识。另验证补齐生命周期不能消除其他独立缺口，也不能抹去已成立的跨成员链。测量前后原文件字节保持不变。

对新测量器及其测试的 Ruff 检查通过。未扩大到无关平台或模型资格检查。

## v0.43 四槽只读重测

四槽通过 CPU 并行读取原件重测；没有新模型调用、tokenization、公开测试、private/public 验收或参数更新。首次使用标准输入启动多进程时，Python 3.14 的 forkserver 无法导入该入口，在任何测量开始前失败；改用明确的 CPU fork 上下文后完成读取。此启动器问题不属于模型经历或新的实验样本。

| 原槽 | 原 R | 原跨成员链指标 | 新测量指标 | 新生命周期归属 |
|---|---:|---|---|---|
| org43-r1-s0-PT | 1 | null | false | 1 个原 `staff_done` → 退休事件，完整关联 |
| org43-r1-s0-SB | 0 | false | false | 无新增关联 |
| org43-r1-s0-ST | 0 | false | false | 无新增关联 |
| org43-r1-s0-PB | 1 | false | false | 无新增关联 |

PT 的原控制调用为 `model-27baf98da3c9058e8dbf1883`，原窗口为 `organization-v042:org43-r1-s0-PT`，原 native tool call 为 `call_1278fe82bb27eec241dd47f20082d271`；对应第 35 个调度机会及世界 `action-35`。原记录顺序为成功尝试 623、响应 624、policy decision 627、harness 输出 628、工具返回 629、done 控制 632。原世界提交与 registry 对应退休事件 35。修订文件保留这些原件定位和原测量缺口。

重测后的有限结论为：四条已执行经历均没有达到原机械标准的跨成员工作使用链。它不证明不存在任何语义帮助，也不将个人交付成功解释为协作收益。原两条业务成功和两条已知未提交结果保持不变；原后 12 槽继续未测。

最终汇总：`runs/v044-controls/work-use-remeasurement-final/summary.json`，SHA256 `684922c1b93657dad16bc80cd7b63c60f89591ab914bd17aee2b3cedbd1ee212`。四份修订指标、测量源码哈希及原 `work-use.json` / `slot-result.json` 哈希均由汇总引用；原八份文件在重测前后哈希一致。

较早开发测量保留在 `runs/v044-controls/work-use-remeasurement/summary.json`，SHA256 `7e0774756ac8aa2bcf52b699172bb4fdc135785f9a865f4412c114f968093e3e`。之后按原 SDK 源码补齐 JSON 控制的真实标识与转换回执要求，并以最终源码另存四槽读取结果。PT 原件使用 native `staff_done`，所以两次读取所得四槽指标、R 及未解决项完全相同；没有新增任何模型经历。
