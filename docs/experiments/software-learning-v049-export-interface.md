# v049 实际经验导出接口与有限 CPU 集成控制

本记录覆盖 `software_training_v049.py` 的新窗口绑定，不是模型成绩或训练收益报告。导出沿用原 `TeamRollout`、`MemberView`、record/permission 验证和基础学习 mask/分母；只增加 v049 的真实 world/runtime/source 身份接缝。

## 新窗口与实际输入

`declare_window/expected_window/bind_rollout` 在私有 globals 中执行原 `online_support` 对应函数代码。唯一变化是 policy gate 严格接受真实 `proworksim.software_organization_runtime_v049.worker_type.<locals>.StableO1Worker`，共同 actor、两稳定成员、full-history 和既有格式反馈配置仍绑定；旧模块本身不变，也不伪装为旧 `HarnessWorker`。纯声明用固定真实类名检查，不导入可选 SDK；原生 `policy_spec(owner, prepared)` 另外核对实际类本体及规范化 config。

`situation_fingerprint` 在原 `initial_business_state` 规范化上，只去掉两项控制端环境准备元数据：`environment_preparation_provenance` 和 `environment_preparation_cost`。它们包含宿主回执路径、缓存标记和计时，不是成员可见业务。实际公共诊断、排序、角色、授权、初始任务、所有业务状态与 immutable bytes 均保留。事前声明读取准备初态；结束后导出从原 episode/start 重算，不以已经改变的工作区重算，也不含随机 instance/branch 身份。

Exporter 要求实际 runtime 结果、持久化 `slot-result.json`、原 `assessment.json`、原 public capture、episode 两端 case、Γ1、window、S0 actor、SDK schedule 及声明一致。提交必须绑定原最终固定文件版本和唯一提交事件。所有软件事件逐条匹配原 WorldCore operation/actor/action receipt，提供实际任务/责任/文件成果链给 Mapper。

`MemberView.actual_input` 保留上游 SDK 请求作原始出处；真正训练目标仍直接读取该生成的 `actual_response.token_trace`，input mask 全 0、本人 output mask 全 1。v049 learning bridge 在优化前对实际 selected Γ1 请求、其 token IDs 和原生输出另作一致性绑定。导出器不把归档展开文本重新分词或换成训练上下文，不裁剪生成后缀。

## 资格分离

新 LA/LB 窗口来源允许基础学习，开发来源不能通过删标签或改用途进入训练。正式共同制度评估已知的 R=0 与 R=1 都保留基础 reward 资格，包括安全行政闭合；record/原本人 token 资格照旧控制实际学习材料。完整 work Validity 的 delivery=false/unknown 使 Mapper 不映射，但不删除可信失败材料。未知结果或没有材料的原槽保留原两成员位置和原槽分母；`unavailable_slot_entry` 不补造 reward、输出或缺席成员质量。行政删失保留 R_joint 作为原共同制度 terminal MC reward，另保留 R_token=null，不把 token-only estimand 的未知额外用于筛掉已知共同制度基础材料。实现初版曾多加行政筛选，模型前根据审计和冻结 F=R_joint 口径移除；未改变本人 mask 或原分母。

## 有限 CPU 集成结果

使用既有 `runs/v016-sdk/resident-venv/bin/python` 和 `runs/v030-runtime-deps`，显式 `CUDA_VISIBLE_DEVICES=''`。真实 SDK、WorldCore、权限/原件记录、Γ1 归档、固定树公开与私有验收运行；completion 和 token IDs 为事前人工程序 fixture（64 字符哈希块），没有调用真实模型或 GPU。

只采集两条 CPU 路线：未提交失败 2 个 synthetic completions；本地完整修复 8 个 synthetic completions。失败路线正式 R=0、record=true、delivery=false、Mapper unmapped，但两名成员的本人输出均可进入基础材料。在八个原槽、每槽两名成员下，另七槽缺材料不归一化，actor 与 critic 分母均为 16。成功路线真实执行写完整生产文件、分页 run_tests、fix_patch、submit_integration，正式 R=1，完整 Validity=true，Mapper 为 `local_lineage_delivery`。这验证新页反馈、固定交付和整文件/helper 路径能够接入新 Mapper；不把程序参考修复算作模型工作或方法性能。

首次 pytest 为 7 passed / 1 failed。唯一失败发生在测试自己试图直接把新坐标传给只接受原默认坐标的 `recipe_config`，尚未进入分母断言；生产 exporter、两条 CPU 路线及其它检查已通过。测试改为原 recipe 加显式成员坐标 metadata（与实际迁移方式一致），随后仅加载首次已存原件、执行该同一失败断言，检查通过；没有重新采集两条 SDK 路线。最终 8 个不同必要检查均有通过凭据，不能表述为第二次完整 8/8 pytest。新模块和测试 Ruff 通过。

完整首轮证据为 `artifacts/software-learning-v049/export-controls-attempt1/`；窄离线复核为 `artifacts/software-learning-v049/export-controls-failed-assertion-recheck.json`。另一个 allocation 纯 CPU 控制曾因声明 gate 导入 SDK 时缺可选依赖而在 gate 阶段失败；改为上文固定真实类名验证后消除这一非模型接缝，未修改原支持算法。
