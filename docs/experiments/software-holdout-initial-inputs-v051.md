# v051 HOLD 初态 SDK / tokenizer 资格

本文件记录内容访问前完成的公共实现，不是 HOLD 来源准入、模型放行或容量通过凭据。实现为 `scripts/software_holdout_inputs_v051.py`，输出版本 `v051-holdout-initial-input-qualification-v1`。实际 HOLD 题目、初态仓库和测试内容尚未由本实现读取；本次未执行真实初态资格。

## 门控与执行顺序

脚本先验证独立 `v051-holdout-source-access-release-v1`、其 `common_implementation_freeze` 与静态 `inventory` 的绝对 path / SHA256 / bytes 引用。复用来源脚本的 release gate，核对整个共同源码快照，并要求输入脚本自身也从该快照执行。来源资格必须 `fixture_only=false`、`completed=true`，其来源访问放行和共同冻结引用必须完全一致；固定八题由 `qualified_case_ids` / `blocked_case_ids` 原序完整分区。`passed=false` 不等于盘点未完成，不要求八题全部合格。

来源全部 blocked 时，输出合法 completed 盘点，SDK 请求和 tokenizer 调用均为 0。存在来源合格题时，才构造 provider 并读取对应初态。tokenizer 的 model_path、tokenizer.json、tokenizer_config.json 及存在时的 chat_template.jinja 由共同冻结记录绑定，严格核对文件后仅加载原 tokenizer；不加载 actor / critic / optimizer 权重。

## 请求范围及计数

原先“16 个逻辑角色形状只编码一次”的草案不足以覆盖独立世界的 opaque 标识。内容访问和共同冻结之前已明确修订为最多 8 题 × 2 角色 × 4 条件 = 64 个实际初态身份请求。每题仍只有两类角色逻辑形状。Γ1 内部为 original / selected / protected 等请求执行的渲染和编码次数另列，64 不是底层 tokenizer 函数调用次数上界。

每个身份请求复用正式 HOLD 的 `build_runtime`，创建两个原稳定 SDK 会话、同一共享预算和原工具合同。为得到两个角色各自的未工作初态，每个角色使用独立新世界；保留清单指定的 first_member，仅将资格采集游标移到目标角色。这不模拟另一角色已经工作后的实际第二回合。SDK 到达首次 `prepare_for_budget` 时保存原始请求和真实 runner association，使用资格专用停止信号退出，早于预约 / attempt / 模型派发；响应数为 0，仓库执行数为 0，没有程序化业务动作。

对捕获请求调用原 `project_software_request` 和原 `prepare_native_input`，C18432 / O2048 / Γ1 及原模板完全保持。只按 selected P + 2048 ≤ 18432 判断硬容量；不添加工程余量，不改变页长或候选。缓存仅允许相同角色且原请求完整 JSON 字节相同的投影，底层渲染 / 编码缓存要求完整输入及参数精确相同；审计归一化后的请求绝不用于缓存或实际编码。

四条件的完整业务输入和工具合同须相同。只在比较副本中屏蔽明确字段：world instance_id、workspace object_id、两成员 initial_source_reference.object_id、team_model_budget.state_sha256。逐项记录屏蔽前原值及位置，实际输入原件不改。未知字段差异或任一实际初态容量失败将保留原题并标为 input_blocked，不换题、不调共同实现。host 的状态授权、会话 / window / call 等宿主元数据另存在 capture.json；资格 owner 明确为 checkpoint 元数据装配，没有声称实际加载权重或通过参数 / RNG guard。

资格只证明这些实际初态身份实例；不声称所有未来随机会话标识数学上均 fit。正式运行每次仍执行原硬容量门，局部 context 终止依原规则保留。

## 新增控制与证据

`tests/test_software_holdout_inputs_v051.py` 的三个纯 CPU 控制一次全部通过（3 passed，0.14s）：完整 / 部分 / 全 blocked 来源分区及 gate 拒绝后不得读源；精确缓存与 opaque 比较不混淆真实业务差异；捕获边界绑定角色、只接受一次请求、禁止派发。这里没有重放旧 SDK 双会话情境、真实 tokenizer、来源测试、GPU 或模型。

首次 Ruff 发现一个 unused CONDITIONS import；原日志和首次源码已保留，删除该未使用 import 后只重新执行 Ruff，没有重跑已通过 pytest。证据目录为 `artifacts/software-calibration-v051/hold-input-controls/`，摘要 `summary.json` 将绑定最终源码和原执行源码。

已有实际 SDK 双会话 / 休眠 / 真实伙伴唤醒装配证据精确复用 `hold-interface-controls/summary.json`，保留其首轮 4 passed / 1 failed、字段断言修正后仅只读完成的事实。本轮按根代理要求仅将 world.observe 中 `full original pytest executor` 改为 `full original repository test engine`，适用于原生 unittest 和 pytest；这是共同冻结前的公共文案修正，不重放旧 SDK 控制，也不声称旧 fixture 已含新文案。

## 后续实际命令

由根代理单独确认来源访问和资格后，从共同快照执行：

```bash
PYTHONPATH=<common-source>/src:<common-source> <pinned-sdk-python> -m scripts.software_holdout_inputs_v051 \
  --project-root <original-project> --release <source-access-release.json> \
  --source-qualification <source-summary.json> --inventory <repository-inventory.json> \
  --model <original-common-tokenizer-directory> --output <new-initial-qualification-directory>
```

输出保留每个原始 SDK 请求、capture.json、projection.json（含原 native 渲染和 token IDs）、opaque-identities.json、逐题进度及最终 summary.json。执行中出现非容量的基础设施异常会保留已有原件并停止，不伪造 completed 资格。最终合格列表只是输入资格，仍需独立模型准入将其与来源资格取交集，不能自行派发模型。
