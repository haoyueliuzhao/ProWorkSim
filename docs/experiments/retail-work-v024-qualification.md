# v0.24 新材料、完整工作机会与可见标识资格

本记录只支持工作路线存在、公开合同保持和可控宿主标识可重复。全部 CPU 程序见证均不属于模型成绩、教师数据、训练标签或 ID-VTDO 方法支持。没有模型推理、GPU、API 或参数更新。

## 材料与固定采样设计

原 UCI Online Retail XLSX 身份与既有许可、来源合同保持。先排除 v0.15、v0.16、v0.22、v0.23 的 110 个客户、330 张发票、1143 个原始行，再按 `SHA256(collaboration-v024:CustomerID)` 顺序选择 28 个新客户，组成 14 对材料。每对保留两名客户各自字典序前两张完整普通发票和首张完整冲销发票；普通发票为 2–3 行，冲销发票为 1–3 行，金额原值至多两位小数。总计 84 张完整发票、172 个原始行。没有根据模型输出筛选材料，仍为一个来源家族，不能称独立来源泛化或语义去污染。

前六对用于评价，后八对按两组各四对用于训练。每组固定 A、B、独立实现、独立复核四情境，以 `A,B,实现,复核,A,B` 形成六槽。共同首窗 B 为正确初稿、复核为错金额；第二窗 B 为错计数、复核为正确初稿。MC 与 Handoff-RTG 第二窗共用情境及采样 seed 声明，各自生成独立实际经历、各自消费自己的第二窗。

评价六情境为 2A、2B、2维护。B 分别为正确初稿与错计数；维护分别实际触发需要改变数值的 policy v2 和数值保持不变的 policy v2。每情境两个固定重复，每个重复内按 `A,B,维护,A,B,维护` 交错。共有 12 个评价槽，每个 checkpoint 使用同一声明。任何一个重复均不是新独立情境。

源码合同：`examples/retail-collaboration-v24/catalog.json`、`source-manifest.json`；实际素材目录为 `runs/assets/uci-collaboration-v024`。`training_windows` 保留两阶段规范；`sampling_windows` 分别为 `v024-window-1`、`v024-window-2-mc`、`v024-window-2-handoff_rtg`，后两者真实运行和存储身份独立。

## 工具、任务、预算与评价

v0.23 的角色职责、加性终局项、固定材料数值谓词、工具与权限、compact 选择算法保持。维护实现者仍使用原 `v23_maintenance` 权限配置，其他角色为原 v14；没有额外工具。角色生成机会维持实现 12、复核 12、A 的提供者 6／实现者 16、B/维护的实现者 24／复核者 28；上下文 16384、预留输出 2048。

`retail_collaboration_v024` 具有独立新目录身份与评价版本；不改写或重新评分 v0.23。维护仍以当前实际行为独立核准，准备正确交付和外部 policy 事件不记作当前工作。

## 确定性标识的范围

仅新协议安装以下规则：

- `StaffRuntime.run_id` 由 case 与同 seed 的 `episode_key` 确定，进而固定 request_key、model decision ID、机会 ID 和其派生 command ID。单独存储随机 `actual_run_id`，真实 world instance、branch、episode UUID 和存储目录保持独立。
- Runtime 先依据真实 observation 执行身份绑定并保存原观察，模型输入才将根层 instance/branch 标识投影为可见稳定名。actor、project、object、version、权限及内容均保持，映射键按确定次序序列化。
- 原 Qwen native parser 的接受规则不变。解析后仅宿主 `tool_call.id` 由实际 role-local messages/tools、调用序号和解析后的动作/参数生成；同一动作的 JSON 键顺序或自由文字前缀不会生成新的宿主身份。原始输出、输出 token、行为概率不变。
- 没有 request_key 的环境时钟操作按当前实际 state revision、actor、action、arguments 和公开 namespace 确定命名。该规则不代替或合并任何业务动作。
- compact 的读回内容、提交与 inspect 的保留字段不变。新响应仅规范映射键顺序。`public_presentation` 采用 `work-presentation-v0.24-canonical`，其 raw hash 为完整原响应的 canonical digest。旧 v14 分支保留；新分支仍从实际 commit、actor/project、真实 action/arguments、profile 和原响应精确重算，不接受任意子集，也不删除 hash。

不同实验的局部命令名可以相同，查询和验证始终绑定各自真实世界及 episode。对象和版本不合并；本设计不承诺 GPU 生成或不同硬件逐位确定。

## 实际资格与已保留开发记录

最终明细、原报告路径及 SHA256 见 `retail-work-v024-qualification.json`。14 个新情境均通过真实 WorldCore、WorkInterface、ModelPolicy、compact、官方 tokenizer 和固定上下文拒绝规则下的 CPU 程序路径，使用生产 native parser 和生产长度的确定 tool-call IDs。每条均在原角色预算内完成完整职责。 最终所需业务动作最大 prompt 为 13875 token，连同固定 2048 输出预留共 15923，低于 16384；7 次额外 staff_done 在工作已完成后被真实上下文门拒绝。

两条代表路线（A 与实际数值变化维护）另由独立进程以 `PYTHONHASHSEED=17` 和 `29` 完整执行。比较实际 requests 的 messages、tools、官方 tokenizer 的完整 input ID 序列、真实世界 tool call/command/receipt、准备状态 canonical hash，全相等；实际 run、instance、branch、episode、存储目录各不相同。A 每过程 12 次请求，维护每过程 26 次请求，其中保留真实终止阶段 context 拒绝。这是指定路线的有限复验，不是全部可能历史的穷尽证明。

开发过程没有掩盖失败：初次 identity CPU fixture 误将 parser 的成功返回 `None` 当作诊断字典，导致程序 transport failure；修正的是 fixture 对既有接口的调用。随后跨 hashseed 的完整运行暴露了旧 compact receipt hash 受字典插入顺序影响，已用上述独立 v24 canonical marker 修复。两类原记录保留。初版短 CPU tool ID 路线和中间 canonical 路线亦保留，最终资格使用真实 native 宿主 ID 长度重新核验。

定向测试含 4 项 v24 测试：完整目录与来源边界、真实世界可见重复／真实身份分离、native 标识的精确动作与权限区别、canonical receipt 的篡改 hash／对象／权限范围／参数反例。原 presentation 5 项回归亦通过。没有重跑模型数值诊断或反向验收。

复现：

```bash
CUDA_VISIBLE_DEVICES='' PYTHONPATH=src runs/v016-sdk/resident-venv/bin/python \
  -m scripts.retail_work_controls_v024 --output NEW_DIRECTORY \
  --tokenizer runs/assets/models/Qwen3.5-9B-c20223623576

PYTHONHASHSEED=17 CUDA_VISIBLE_DEVICES='' PYTHONPATH=src \
  runs/v016-sdk/resident-venv/bin/python -m scripts.retail_identity_v024 \
  --output NEW_ID_DIRECTORY --tokenizer runs/assets/models/Qwen3.5-9B-c20223623576
```

上下文只证明这些实际程序路径的必需动作可执行。模型可以走更长的历史、产生更长输出、错用工具或停在中途；资格不保证其采样路径可完成。完成后额外 `staff_done` 的真实 context 拒绝保留且不执行，不补为模型动作，不作为业务成功训练数据。
