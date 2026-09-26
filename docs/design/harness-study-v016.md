# v0.16 H1 独立开发比较协议生成说明

本补充定义 H1 的固定比较预算与协议生成方式。生成器只写新协议，不选主训练模型、不启动观察器或模型，也不更改 v0.15 筛选及 N0/N1。H0 实际结果核对后，仍需单独固定最终源码、SDK 和运行环境身份；生成文件不代表实验已执行或已获能力认证。

## 固定比较

每个候选使用同一 fresh 公共基础权重、同一初始化种子 `2026093041`，单个 resident actor 连续执行四个**纯评价**窗口：

| 顺序 | harness | 重复 | 情境数 |
|---|---|---:|---:|
| 1 | `native_v15` | 0 | 6 |
| 2 | `openhands_v16` | 0 | 6 |
| 3 | `openhands_v16` | 1 | 6 |
| 4 | `native_v15` | 1 | 6 |

因此每模型为 **24 episode**，两模型共 **48 episode**。两个条件不会分别更新参数；预期 actor/critic optimizer step 均为 0，每窗口使用既有评价 guard 保存学习状态及 RNG 还原证据。不能恢复 N0/N1 或其桥接检查点，也不能把不同初态的结果称为共享起点比较。不同模型各自初始化，不声称不同架构之间权重相同。

六情境为 `retail_harness.registry()` 的固定顺序：实现 2、复核 2、pair 1、chain 1。每 slot 种子严格为 `2026093100 + case_index * 10 + repeat`，两个 harness 和两个模型使用相同情境/重复种子。每 slot 显式保存 task、fact_position、pool=`harness_development`、family=`uci-online-retail-352` 和相同角色预算；不依赖旧报告器猜测新 case 名称。

每个六例窗口最多 89 次角色决策机会，每模型四窗口最多 **356 次**。笔记、检索、等待、完成和实际业务动作共用这些有限机会；不会为 SDK 额外免费提供模型决策。每次生成上限、上下文上限、精度、LoRA 范围及其他 recipe/profile 条件从对应修正 EOS 的原 S1 协议原样继承，只有初始化种子按上述规则改变。总耗时和实际 token 数仍须测量，不能由机会预算直接断言成本相同。

本轮比较是 harness 支持的**组合效果**：当前原生运行使用 latest observation，SDK 使用最新观察与最近 4 轮工具交互，以及声明的私有笔记、局部历史和编辑支持。不能将所有变化单独归于记忆、计划或任何一个功能。两组业务目标、权限、实际工具效果、准备状态及奖励合同相同；不得加入 H0 的公开校准任务提示、正确 SQL、结果值、隐藏反馈或成功重采。

## 候选与解释

审计原文要求“等原S1完成后，再按明确规则确定两个可用候选”。本轮正式启动门禁要求原三条 S1 全部收口，两新候选各 36 个测量闭合已知，才能启动任一 H1 条件。不能在仅 9B 完成、27B 仍运行时临时称只有一个可用。生成器可构造两模型 48 例，或作为将来修订草案构造 24 例 `single_model_harness_diagnostic`；当前正式门禁只支持前者，单模型执行须另行明确修订，不能自动降级。旧 7B 不自动加入，新候选也不因训练数值准入与否被混同为业务能力强弱。

生成器没有新的业务分数门槛，没有回溯重排原 S1。即使原完整责任为零，只要所声明原始完成/绑定证据成立，它也会保留该测量；这表示可进入有界 harness 开发诊断，不代表能力足够。原岗位、事实、重复、成本与短板保存在 manifest 的 `original_S1` 中，不能只展示一个 selected 名称。

主要观察量是完整责任、依据实际使用、正确修改、有据复核、具体错误恢复及总成本。H1 没有参数学习；组合效果不能称为训练收益，也不能称为 ID-VTDO 配置增量。六情境是同一 UCI 来源内的新开发实体，不是独立来源测试。Marshmallow 锁定需求不参与本生成器、提示调试或 H1 选型。

## 生成方式

仅生成计划时，可使用以下命令；它不会验证原 S1 是否已完成，也不会产生可用性认证：

```bash
.venv/bin/python -m scripts.build_harness_study_v016 \
  --screen-protocol examples/learning-v15/screen-chatstop-qwen35-9b.json \
  --screen-protocol examples/learning-v15/screen-chatstop-qwen38-27b.json \
  --profile-root /data1/zhuxinrui/projects/ProWorkSim \
  --output runs/harness-v016-h1-plan
```

正式生成前，如已有 `scripts.learning_report_v015` 产生的原 S1 只读报告，可追加：

```text
--s1-report <已保存的原S1报告/report.json> --require-s1-complete
```

此生成期选项只校验每个显式输入候选，**不会开放正式启动门禁**：原 run 完成、36 个原测量全部闭合且已知、原协议/launch 协议与输入内容一致、runner 指纹一致、原 resident owner/profile/recipe 一致、没有未知 optimizer steps/集成问题，原评价学习/RNG guard 成立。报告中的业务成绩原样保留，不重新评分。校验不加载权重，不重放模型、不运行 SQL，也不重新认证训练数值门槛。它只核验明确输入候选；其他候选的停跑原因、资源可用性和 H0 结论仍由执行方依据独立事实确认。

`--screen-protocol` 必须显式提供，最多两份且候选不能重复。`--profile-root` 指向所用源树，生成器核对 profile 源文件 SHA 及嵌入内容，并拒绝旧错误 EOS runtime、跨候选 profile、被改写的 profile 或不是 36 槽原 S1 的来源协议。输出目录必须不存在；任何原协议、运行结果或已生成协议都不会被覆盖。

输出为 `study.json` 和每候选一份 `h1-<candidate>.json`，collector 固定为 `proworksim.harness_collection:collect_window`。协议从最小字段重新构造，旧 S1 的 experiment_id、paired_original_protocol、budget_scope 或 change_scope 文案不继承。生成器不接收 checkpoint 参数、不写调度器，也不替执行方决定资源分配。默认协议带 `launch_gate.state=planning_only`，公共 runner 在依赖查询、learner 导入和模型加载之前直接拒绝，并写入拒绝记录。

## 本次生成器核验

单个有界 fixture 测试通过，验证 48/24 预算与解释名称、四窗口配对顺序、共享种子及角色预算、runtime/recipe 保留、new-only 输出、profile 篡改拒绝、显式报告要求及“人工全零业务成绩仍保留原测量、不认证能力”。这个 fixture 的原完成记录是人工输入，不是实际 S1 结果。Ruff 通过。

此处仅交付生成器和固定计划；尚未据此启动 H1，也未将 H0 或原 S1 部分成功算作 H1 样本。


## 正式启动门禁与身份绑定

实际 enforce 位于 `scripts/online_learning_v015.py` 调用 `proworksim.harness_admission.validate_h1_launch`，发生在新 `online_training` 导入、依赖版本查询与模型加载前。原 H0/S1/N0/N1 协议返回 `not_H1`，仍按其原合同执行；在跑冻结源树没有被修改。H1 的 restore checkpoint 始终禁止。

只有显式提供外部正式 admission JSON，且 `--admission <path>` 把该文件 SHA 绑定进两份 H1 协议后，runner 才会核验以下条件。这不是新队列，也不自动创建准入结论：

1. admission 为 `h1-launch-admission-v0.16/admitted`，同时包含两候选协议主体 SHA（仅排除自身 `launch_gate`，避免哈希自引用）；每个启动的实际协议与其 SHA 相等。
2. 当前 clean commit/source identity 与 admission 完全一致；7 个 runner/builder/gateway/SDK/collector 文件字节也与显式清单一致。最终 SDK/context/adapter 版本与协议一致。不是只在结束后记录源码是否变动。
3. 原全 S1 报告和两候选 supervisor 由文件 SHA 绑定。三条原 S1 均为完成、各 36 闭合已知；复用原选择器的 saved-record binding validator 核对两新候选的实际 S0/S1 源、启动命令、退出、owner、profile 和权重清单，再核对真实评价 guard 与原槽数。训练准入可以为 false；本门禁没有业务成绩阈值，也不把相对 selected 当能力认证。
4. 启动的 `--model` 路径与 `--weight-manifest` 路径/SHA 必须与原完整筛选候选相同。门禁只读取小型清单；各权重文件的字节检查仍由实际 CandidateActor 加载器执行，不新增权重遍历。
5. 初始化必须为 fresh public base、固定 seed `2026093041`，四窗口协议须与生成器从原 S1 runtime/recipe 重建的主体完全一致、全为 evaluate、预期 actor/critic 步数为 0。同一 resident 执行四窗口，实际学习/RNG不变检查仍由已有 runner 执行。
6. H0 的真实全 3 槽总结、原 run、原 source、闭合 episode、零更新及评价 guard 被实际读取核对；`accepted_for_h1` 只是一项明确的兼容性审阅结论，不是 H0 业务成功。若已测试 adapter 为 v0.16，而最终目标为 v0.16.1，admission 必须显式列出没有重跑真实模型的变更及带 SHA 的定向 CPU 证据，不能把新版本追认为原真实运行。

正式清单的必要顶层字段为 `version/status`、`protocol_body_sha256`（两候选）、`source_identity`、`source_files`（模块常量 `SOURCE_FILES` 列出的七文件）、`harness_identity`、`original_s1_report`、`original_s1_supervisor`、`weight_manifests`（两候选）及 `H0`。文件引用形如 `{path, sha256}`，可以另带 bytes。`H0` 包含 `review_status=accepted_for_h1`、`scope=compatibility_only_not_business_success`、实际总结的 `report` 引用、相对证据的 `evidence_root`、`reviewed_source_identity`、`target_harness_identity`、`tested_adapter_version`；有版本差异时另需 `untested_model_changes` 和 `targeted_cpu_evidence`。该清单应在最终源冻结及真实原 S1 收口后生成，存放在不使冻结源码变脏的独立运行目录。

门禁不是通用权限或不可伪造证明系统；它针对本轮误启动与身份混用，信任本地原始记录及明确审阅结论，不重新计算业务评分、概率或梯度，不检查显卡容量，也不自动判定每个 CPU 报告的语义。资源安排仍须在实际启动前确认。若需单模型、变预算、不同源码/权重或新的 H0 变更范围，必须另行修订并重新绑定，不能沿用旧 admission。

新增针对测试使用完整人工保存记录夹具，通过正式分支，并验证 planning-only、只完成9B、错权重、错源、checkpoint restore 和 H0 原始证据变动均拒绝。完整分支目前**只在夹具上通过**；实际 S1 尚未全收口，未生成正式 admission，现归档 H1 仍为不可执行的 planning-only。
