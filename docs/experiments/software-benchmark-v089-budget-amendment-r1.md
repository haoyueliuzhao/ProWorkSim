# v089：原 DeepSeek 账本追加 200 元

用户明确要求“deepseek组增补两百预算，完成后对技术未知进行处理”。本修订将原唯一 API 总账的限额由 **1500 元提高到 1700 元**，追加量仅为 200 元。不新建一个从零计费的实验账本，不清除旧支出、不退款、不释放没有用量证据的不确定预约，也不通过修改旧请求身份取得重放机会。Qwen 不使用此现金预算，本工具不操作其服务或显卡。

本文记录已实现的代码与 CPU 验证；代理阶段没有执行实际 `--prepare`／`--execute`、没有更改真实账本或运行 API。实际执行与结果应由主协调者的 proposal／intent／completed 回执确认。

## 精确修改范围

原 SQLite 文件仍为 `runs/software-benchmark-v064/full-verified-r1/api-budget/ledger.sqlite3`。原 policy 中只修改两项：`cap_nanoyuan` 从 1500000000000 到 1700000000000，`version` 改为 v089 的明确追加版本。价格、每请求最大预约、上下文、输出上限、思考模式、并发限制、冷却与硬停止规则全部保持。另在 metadata 插入一次 `budget_amendment_v089` 审计标记。

以下内容必须逐项保持：requests、response_observations、provider_protocol_events 三张表的全部行；其他 metadata（包括冷却和失败计数）；SQLite schema；已结算、已承诺、不确定预约、峰值计费、请求总数和状态数量。每张表按主键顺序流式计算完整内容指纹，记录行数和 SHA256，修改前后指纹必须一致。原不确定请求仍按完整原预约计费；追加金额不能被表述为原未知费用已经查明。

## 操作流程和拒绝条件

`tools/amend_api_budget_v089.py --prepare` 仅核验和写项目内提案：确认精确 v088 管理服务已停止、无在途 API 对象或管理预约、官方正常预算终态及已释放管理租约；原 policy 必须精确等于冻结的 1500 元 policy，reserved 必须为零，原有不确定费用仍通过 v072 的严格证据校验。已有账单 hard halt 或身份异常不得借增加预算绕过。

`--execute` 重新核对前置条件，先通过 SQLite backup API 保存一个包含 WAL 已提交数据的一致备份，路径为 `runs/software-benchmark-v089/budget-amendment-r1/ledger-before.sqlite3`。备份逻辑指纹须等于提案中的原快照，并完成数据和目录同步；随后保存不可变 intent。

真正修改只发生在一个 `BEGIN IMMEDIATE` 事务中：再次核对原快照和零在途状态，按精确旧 policy 字节条件更新一行，并写入唯一追加标记，比较前后全部保留指纹和费用合计，再提交。失败回滚；已经存在 intent／backup 的 mutation 身份不自动重试，更不会再次加 200 元。

若事务已提交但完成回执写入中断，`--finalize` 只读核验现有追加标记、备份、原快照和保留指纹后补写回执，不再执行 UPDATE。新运行器初始化要求 completed 回执与真实账本中的追加标记一致，禁止在该证据缺失时启动真实请求。

提案与回执位于 `artifacts/software-benchmark-v089/budget-amendment-r1/`。SQLite 备份留在 runs 目录，避免将大体积真实数据库纳入 Git。整个工具只使用普通用户的已有文件、SQLite 和只读用户服务状态，不请求 API、不操作 Docker、不修改共享服务器配置。

## 私有运行器适配

`software_benchmark_deepseek_budget_v089` 不修改旧模块的全局变量。新 BudgetLedger 的构造、reserve、snapshot 明确使用 1700 元 policy，保留 v085 的 SQLite 显式关闭；settle 和 uncertain 沿用原计费与保留规则。新客户端及每题 fork 都使用同一追加账本，旧客户端会拒绝新 policy，而不是悄悄用旧 1500 上限读新实验。

运行器接口：

```python
from proworksim import software_benchmark_deepseek_budget_v089 as budget

raw = budget.build_runtime(
    scope_guard=scope.require_allowed,
    retry_rows=rows,                   # 封存的新恢复身份，不是旧 slot 的重放
    inventory_ref=inventory_reference, # JSON 必须包含 rows 列表
    identity_file=api_root / "api-runtime/identity.json",
)
api = budget.RuntimeView(raw, fd_guard)
api.initialize_for_run()
```

新恢复行必须保留 `original_slot_id`、`original_slot_index`、原题目、condition、model、arm、seed 和 5M token 限制；`recovery_attempt=1`。操作身份是 `original_slot_id + ':recovery-v089-r1'`，物理索引只允许 6000–6043。模型控制器继续满足冻结的 v064 前缀要求，但每个新请求的完整前缀均与原请求不同。原6000行和新增精准白名单共同参与未知费用校验；没有在白名单中的新未知请求会拒绝准入，不能仅凭字符串前缀通行。

`build_runtime` 重新核对封存 inventory.rows、原两条 neutral 资格和工具 schema，并禁止任何已经出现过的新恢复 ID 再开 broker。它不恢复中断时的模型状态，也不把新尝试伪称原回合的精确续跑；是否执行这44个恢复尝试由主协调者另行封存任务计划。旧29笔不确定预约继续与新请求共享 1700 元总限额。

## 必要验证

7 项 CPU 检查通过，Ruff 通过。检查覆盖：唯一增加200且所有原行保留；有在途预约或 hard halt 时拒绝；价格／metadata 变化时拒绝；只读 SQLite backup 一致性；新reserve确实使用1700上限且仍禁止请求重放；恢复未知必须精确匹配白名单并保留原足额预约；实际初始化和每题fork不会被旧FD包装器换回1500元客户端。测试仅使用临时 SQLite 数据和无网络客户端，没有读取密钥、调用模型或修改真实总账。

```bash
.venv/bin/python tools/run_offline_scorer_v058.py tools/amend_api_budget_v089.py --prepare
.venv/bin/python tools/run_offline_scorer_v058.py tools/amend_api_budget_v089.py --execute
# 仅在已提交但完成回执缺失时：
.venv/bin/python tools/run_offline_scorer_v058.py tools/amend_api_budget_v089.py --finalize
```

实际追加仅表示多了200元可承诺余额，不保证所有恢复题和后续技术未知都能完成；后续仍须报告实际费用、未定费用以及不同恢复尝试的身份与统计边界。
