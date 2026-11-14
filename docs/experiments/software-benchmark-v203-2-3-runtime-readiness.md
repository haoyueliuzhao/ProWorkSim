# K0/K1/K2 固定 REVIEW2 运行接线准备

本次只做源码定位、独立准备程序及真实 CPU pytest 命令控制。没有调用模型/API、Docker、队列或旧现金账本，没有启动真实试验。`readiness.json` 明确写入 `real_runtime_admitted=false`；生成 manifest 不代表实验准入。用户随后明确新增现金上限 130 元；新面板为 4 题 × K0/K1/K2 共 12 回合。旧 12 题与旧 150 元账本没有续用。本文件中的早期 readiness 是当时的准备证据，不能替代最终封存和实际题目解释器资格。

## 真实模型请求链与插入位置

当前 `tools/run_passive_controller_v203_2_1.py` 调用 `software_role_baseline_runtime_v203_2_1.build_team_owner/build_runtime`。后者保留 v141 双成员 REVIEW2 实现：每位成员有独立 `DeepSeekEpisodeAdapter`、worker、SDK conversation，公共软件世界按既有权限共享。

v141 `build_runtime` 为每位成员创建 `software_benchmark_history_v117.SummarizingManagedContextTransport`。真实 SDK `ManagedCountingLLM.get_token_count` 与请求预算准备 `prepare_for_budget` 都调用同一 `transport.select_for_member(request, member)`。这里先运行原有格式反馈投影和 v117 可逆历史引用，再由后续角色 presentation adapter 改变允许调整的选择/排序，才可能保持计数、预算及实际请求一致。不能只在最终 `post('/chat/completions')` 或 host HTTP transport 改写请求。

后续链路为 member adapter → controller `FifoModelTransport` → host broker → `software_benchmark_deepseek_api_v203_2_1.DeepSeekClient.complete` → physical transport `/chat/completions`。模型请求及回包由 v203 Sidecar 捕获，但 Sidecar/global observer graph 不是角色 selector 的授权输入。

摘要由原 worker 的 `ManagedSummaryAdapter` 和 SDK condenser 单独生成。K0/K1/K2 均须保留原摘要算法、参数、历史原件、摘要来源和摘要计费；角色排序仅在 agent 呈现层生效。完整输入、重复输入、回读、输出和摘要费用仍进入既有全队账本，不能用卡片估算长度替代真实请求总成本。

### 从离线接口到真实 SDK 插入

初版离线 selector 要求 `ctx:` 私有 reader 占位，而真实 v117 只提供 `anchor_message_index/anchor_content_sha256/original_content_sha256/omitted_equal_paths` 同请求静态字段引用。因此没有伪造 `ctx:` 或新增 `context_read`，而是让新 selector 验证真实 v117 原件、marker、anchor 散列及重建后的原始 JSON。

`software_role_context_runtime_v203_2_3.install` 在创建实际成员 runtime 后、第一条模型请求前，给每位成员自己的 transport 安装实例方法。它仅从实际 worker `_observation_texts` 注册表与本次 v117 已重写历史槽产生候选，不读取 World/global observer graph。候选是 messages、handoffs、patches、all_fixed_patches、current_version_test_coverage、delivery_status、organization_protocol 七类完整 JSON 字段。原文跨度必须完整等于原字段，结构 kind 由固定字段映射派生。版本只绑定当前版本测试覆盖的 workspace_reference 或 delivery_status 自己的 source_reference，聚合 patch/message 列表不冒充当前 workspace 版本。

K0 完全保留原 v117 request。正式 K1/K2 设计采用同一候选池与 4096 内容 token 上限，先从可选历史槽删除候选字段，再呈现排序后选中的完整字段卡一次；latest、任务、system、assistant action 和 tool result 原件保持。K2 使用真实开发/复核/交付角色及已绑定版本排序，不能把全零 role score 的退化实现准入。

引用是审计定位符，不是模型可调用的全文 reader。原 v117 静态引用依赖同一请求中的完整 anchor；它不保证被摘要的任意旧历史可恢复。新增选择删除了未选历史动态字段后，不能再称这些字段“lossless 可回读”，也不新增工具绕过选择预算。后续效果应包含信息省略及真实全请求 token 成本。

最终真实 SDK 控制见 `artifacts/software-benchmark-v203-2-3/sdk-role-controls-r7/summary.json`。使用固定 OpenHands SDK、真实软件世界、独立成员 conversation、脚本化 provider 和 v175 真实 CPU pytest；网络调用由 audit hook 拒绝。原 condenser 参数保持不变，没有用缩小阈值强迫摘要。三个 group 的新 closure 分别保留 K0/K1/K2，组织始终为 REVIEW2，均完成同一独立复核与合法交付脚本。

| 条件 | 实际 SDK agent dispatch | selector 调用／应用 | 具有非零角色分数的调用 | 实际请求中逐项确认已删的历史字段 | 单请求序列化内容 token 减少范围 |
|---|---:|---:|---:|---:|---:|
| K0 | 25 | 50／0 | 0 | 0 | 0 |
| K1 | 25 | 50／46 | 0 | 593 | −2811 至 8332 |
| K2 | 25 | 50／46 | 46 | 593 | −2779 至 8059 |

每条实际 dispatch 都有相同字节的计数请求；`prompt_upper_bound` 与官方本地 DeepSeek recipe（含固定工程 margin）的渲染计数相等，mock usage 按此计数加 25 输出 token 形成，团队账本同步核对。它是可核验的 CPU 预算路径控制，**不是 provider 实测计费或模型质量结果**。每条投影请求只有一个选中卡片 envelope，原 eligible 字段已从旧槽删除。K1/K2 的实际字段序列不同。负数说明短历史时卡片溯源开销可能使输入增加，没有声称每次请求都省 token。

初期 `sdk-role-controls-r2` 仅追加卡片，不能作为正式选择的效果证据。后续构建控制暴露并修复了 fixture 的重复锁定/过早读取 summary，以及新 closure 把 K 条件误当组织检查的问题；r7 是这些修订与真字段选择共同通过的版本。旧控制目录保留，不合并为正式任务样本。

## public-test bundle 的真实缺口

`config/v203-2-2-public-test-bundle.json` 钉住 v175 launcher、library、execution、observer，以及 v130 dependency helper 和 v175 managed entry。准备程序逐文件核对这份清单中的 SHA256；三组必须使用同一修复 bundle。

冻结的 v203.2.1 `runtime_inputs.PUBLIC_FILES` 仍绑定 v141 的四个测试文件；`software_benchmark_sdk_bundle_v203_2_1` 继承的 v141 aliases 仍指向 v141 public-test 文件。现有 managed actor 的历史链也导入 v141 managed public-test entry。因此在磁盘上存在 v175 文件、或者生成一份 v175 manifest，都不会自动改变 actor 实际执行路径。

本次新 v203.2.3 bundle、actor managed entry、五个文件 aliases、runtime inputs/controller-ready 和新 episode 已独立接线；actor managed entry 使用相同 v175 parser 与留存 adapter。新 source snapshot 与真实解释器资格仍由执行准备独立核验。三组 K0/K1/K2 必须完全共用这条修复接线，不能让 K0 继续使用损坏历史测试协议。所有旧文件和旧结果保持冻结。

## 框架原始 journal 留存

v175 `execute_public_entry` 仍把 `counts.jsonl` 放在 `TemporaryDirectory`，原函数返回时目录被删除。它保留的会话摘要与散列不能复原原始 JSONL。历史“401 passed 但框架核验不完整”的缺失会话无法据此补判，本次不改写那条旧结果。

新增 `software_public_test_retention_v203_2_3.py` 是独立、显式启用的 adapter。它首先核对原 v175 execution SHA256，再在函数的明确位置插入留存：自己启动的进程组退出后、输出尺寸校验和框架解析前，将完整 journal 和 stdout 分块写入调用方指定目录，并保存原始命令、cwd、进程组、observer token、退出状态、timeout、候选树/源引用以及每份原件的字节数与 SHA256。原命令、超时、进程清理、parser 和 pass 判定保持 v175 原规则。

这也保留了 unknown/failed 结果需要诊断的原始记录，不把缺失 finish 自动补成通过。留存写失败会使调用失败；它不是同 UID 防伪边界，也不证明整机崩溃/断电后的恢复。进程启动失败或进程清理自身异常尚未完成时，不承诺生成完整命令证据。actor 在 `/pws/output/framework-journals` 留原件，新 episode 在写者静止后、cleanup 前导出 actor `/pws/output`；导出失败保留 actor 并记录 technical_unknown。既有受限 actor 文件系统仍约束存储；真实容器资格须验证导出路径，不能仅凭源码声称通过。

执行验证使用当前 `.venv/bin/python`，实际运行 1 个 pytest 测试，通过 v175 原 observer 取得 `verified` 与 `passed=1`；临时框架目录结束后，从留存 JSONL 按原 token/进程组重新解析，counts 与 validation_status 相同。它证明新增 adapter 能保留并重放这条真实 CPU 命令的原始证据。它没有使用未来题目的解释器，不覆盖历史缺失会话、嵌套框架、实际容器、真实 SDK agent 请求或模型收益。

## 可重复运行

```bash
PYTHONPATH=src .venv/bin/python -B tools/prepare_role_context_v203_2_3.py \
  --output artifacts/software-benchmark-v203-2-3/runtime-readiness-r3 \
  --run-cpu-control
```

输出目录必须不存在，避免覆盖旧控制。只生成静态 readiness 时省略 `--run-cpu-control`。留存控制证据在 `artifacts/software-benchmark-v203-2-3/runtime-readiness-r3/readiness.json`，原件保留于同目录 `retained-framework/`；r3 还先预载 source/observer，再删除隔离副本中的私有源码，验证 actor seal 后无需重开这些文件仍可执行并留存。r1/r2 保留为之前修订的证据。准备程序没有 launcher 子命令，不创建预算授权。

完整 SDK 控制命令（指定新的输出目录，避免覆盖 r7）：

```bash
.venv/bin/python -B tools/run_offline_scorer_v096.py \
  tools/check_role_context_sdk_v203_2_3.py --output /tmp/pws-role-sdk-new-control
```

最终新 bundle 目标为 `runs/software-benchmark-v203-2-3/sdk-bundle-r5`。其离线 probe 加载复制后的 SDK、实际 controller/worker 五个入口、context adapter 和 runtime inputs，并对三组真实生成的合成公开配置做 controller config/ready 往返及 actor 实际五个文件散列核验。bundle probe 与真实题目解释器资格是两个不同检查，不能互相替代。

## 为什么不能直接复用旧 snapshot/launcher

旧 `software_benchmark_scope_v203_2_1` 固定了旧 12 题、v203.2.1 slot/condition 身份、150 元 cash ledger、API unit、source index、容器索引和 manifest 散列。r4 continuation 更明确地继承原题/seed/slot、剩余 10 题及原有测试与模型 bundle；Requests leaf launcher 也绑定旧 group、execution plan 和 admission。现有 source snapshot 封存的是这些旧源码与身份，不会因当前工作树增加新文件而自动包含 selector 或留存 adapter。

新实验需要新 scope、source snapshot、manifest、只读部署 bundle、现金与模型账本、新 panel/seed/条件映射以及新 launch admission。不能直接换旧配置里的 condition 名称、重用旧 unit 或覆盖旧 snapshot。已明确 130 元额度，仍应先完成真实题目解释器下的零模型 actor/controller 准入及真实 SDK count/dispatch 一致性验证，再启动 K0/K1/K2；当前 readiness 中的阻塞项没有被标成已通过。
