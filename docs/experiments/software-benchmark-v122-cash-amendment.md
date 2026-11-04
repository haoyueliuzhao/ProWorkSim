# v122：将原账本可用余额调整为45元

用户明确要求将**剩余可用预算调整为45元**。2026-11-04，已在原v105唯一账本上完成一次原子增补；没有创建新账本，没有启动模型、API请求、容器或实验服务。本次授权只改变现金上限，不构成对已调用回合的额外重采授权。

## 金额口径与实际结果

账本金额采用整数nanoyuan（1元＝1,000,000,000 nanoyuan），不以浮点数修改金额。`committed`包括已结算的保守费用上界和未定请求仍保留的预约；它不是服务商发票金额。

| 项目 | 调整前 | 调整后 |
| --- | ---: | ---: |
| 累计现金上限 | 350元 | **389.7945248元** |
| 已结算费用 | 334.3087648元 | 334.3087648元 |
| 旧未定请求预约 | 10.48576元 | 10.48576元 |
| 已占用金额 `committed` | 344.7945248元 | 344.7945248元 |
| 可用余额 | 5.2054752元 | **45元** |
| 在途请求 | 0 | 0 |

新上限按事务前已冻结、事务内再次核验的`committed＋45元`计算。因此实际新增上限是**39.7945248元**，不是在350元上再加45元，也不是把旧未定预约退回后重新计算。旧未定预约继续占用10.48576元。

原15,311条请求全部保留：15,309条`settled`、2条`uncertain`。所有历史请求、响应观察、协议事件和其他非policy记录在事务前后逐表指纹一致；其他policy字段也完全一致。账本仅修改`metadata.policy.cap_nanoyuan`并追加一个`cash_amendment_v122`审计标记。

## 原子操作及保留证据

操作前确认三个使用过该账本的普通用户API服务均为`inactive`、`MainPID=0`，四个既有batch均无API协调器或生成环境活动租约，最新v121协调器释放回执完整。事务期间持有这四个batch原有的资源分配锁，并在SQLite `BEGIN IMMEDIATE`中再次检查无在途、无API所有者、旧cap恰为350元，以及全部请求仍等于准备时快照。

先保存原policy原始字节及完整SQLite备份，再写一次增补事务。程序拒绝重复执行；若提交后进程在写回执前退出，`--finalize`只能核验并补写完成回执，不能再次增额。未启动或停止任何服务，未修改共享主机配置、权限、挂载、网络或GPU状态。

- [已冻结用户金额grant](../../config/v122-cash-amendment.json)：SHA256 `2b521c0aaa4846a2e3112f61acf9058f645a07520026ce8b521204cee007a724`。
- [完成回执](../../artifacts/software-benchmark-v122/cash-amendment-r1/completed.json)：SHA256 `b5a8d94a0d410eaf4bf28e40873f3ed7fb163ad105efb13dbd56ce8d2d2a2520`，含前后快照、指纹、增额及备份引用。
- [原policy原始字节](../../artifacts/software-benchmark-v122/cash-amendment-r1/old-policy.json)。完整SQLite备份位于`runs/software-benchmark-v122/cash-amendment-r1/ledger-before.sqlite3`，具体hash见完成回执；不将该数据库备份加入Git。
- [CPU控制](../../artifacts/software-benchmark-v122/cash-amendment-r1/cpu-controls.json)：6项通过，覆盖金额语义、请求和预约保留、在途或活动所有者拒绝、旧policy或请求漂移拒绝、重复执行拒绝，以及新API实际现金门。Ruff通过。
- [新API绑定只读核验](../../artifacts/software-benchmark-v122/cash-amendment-r1/runtime-binding-readonly.json)：已读取实际新账本，确认cap及45元余额，无客户端或网络请求。

## 后续运行的明确绑定方式

冻结的v105/v120/v121源码未修改。它们的旧350元policy校验会拒绝新账本，因此后续运行必须另建明确绑定的新入口，不能直接重启旧入口：

```python
from proworksim import software_benchmark_deepseek_api_v122

api = software_benchmark_deepseek_api_v122.bind_api()
# 新host使用该api视图；新scope和身份显示应读取同一值。
cash_cap_cny = api.CASH_CAP_CNY  # "389.7945248"
```

`bind_api()`验证冻结grant、事务回执与账本标记，返回独立API视图。其`BudgetLedger`、`DeepSeekClient`及实际预约检查都使用新cap；原账本路径、并发上限16、模型、非思考模式、上下文、输入输出、单回合token预算、计价及未知处理规则均保持。构造API视图不创建客户端或发送请求，默认也不增加neutral资格调用。

为只改变一个policy字段，账本原policy的`version`字符串保留v105历史标识；不能从该字符串中的`cny350`推断当前金额。当前金额以冻结grant、实际`cap_nanoyuan`及新API视图为准。新入口还需显式绑定本阶段已授权的任务身份和资源范围；本次增额本身不延长时间、扩大容器授权或自动重试旧回合。
