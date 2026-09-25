# D1：三角色信息不对称 SQL 团队

本模块提供一个有限、可实际执行的团队任务，并用程序见证检查两种合法资料交接路径。它不证明当前模型已自然产生这两类路径，也不证明训练收益。

## 任务与资料来源

项目为 `TEAM`，工作节点为 `TEAM::build`，决策成员固定为 `provider`、`implementer`、`reviewer`。`operator` 只负责初始安装及预声明材料配置，不是第四个学习成员。实现者有真实 SQL 编辑、DuckDB build、来源采用、提交能力；复核者可以实际读取固定提交、提出定位问题、裁定处理及批准；资料提供者必须实际读取并选择其持有的证据版本，然后决定交接或回复不可得。

两组实例各含 6 条交易记录和 3 名客户，是研究构造的合成事实。它们复用上一阶段的 Jaffle 式数据接口与受管 SQL 执行基础，**不是固定上游 Jaffle seeds 的切片，也不新增独立公开来源**。这不是完整 dbt 工程、企业运行流程或任意终端环境。

公开任务要求：每个客户一行，保留零值；按公共期间及批准口径的状态集合筛选交易；金额以整数分累计；多条支付记录累加金额，但相同订单只计一次。`orders_a` 与 `orders_b` 改变实际金额及状态口径。当前的 8 条基础程序见证不是 8 个独立任务家族。

## 信息布局与工具合同

| 布局 | `basis` 持有者 → 接收者 | `audit_basis` 持有者 → 接收者 |
|---|---|---|
| `split_a` | provider → implementer | reviewer 自持 |
| `split_b` | reviewer → implementer | provider → reviewer |

`data` 是公开输入表。`basis` 是可执行的类型化表，包含期间、批准版本、金额倍率及允许状态，**没有预计算的数值答案**。`audit_basis` 是复核者的独立口径与检查说明。它不作为实现者无法访问的额外隐藏数值要求；独立内容评价使用公开声明的 `data` 与实际采用的 `basis`。

资料对象由 operator 持有写权。信息持有成员只有读权及按对象、工作节点、用途限定的 `provide` 权力，不能通过改写资料来改变客户事实或验收要求。全部角色使用相同公开工具合同。

- `request_information` 在 manual route 上只建立真实请求和等待条件，不选择版本，不排入自动 provider 回答。
- `handoff_information` 要求声明的资料提供者已实际读过所选对象的精确版本。传入 `request_id` 是请求后回复；不传是主动交接。`handoff_key` 标识相同成员、路线及工作下的幂等动作。
- 交接经环境运输事件按声明延迟送达，只给指定接收者开放所选精确版本。它不自动采用、提交、批准或发布。
- `status="unavailable"` 必须针对一个实际请求且不附带证据引用；它是一条真实成员决定。没有适用材料的本轮控制保留 `V=unknown`，不进入正向重配池。
- 被新工作版本替代的迟到交接留在历史中，不能满足新的等待义务或授予新工作所需资料。
- 通用 `request(provider, reference, ...)` 对该工作节点中已声明为 manual route 的对象拒绝自动回复旁路。旧 automatic route 保留用于旧机制回归，其回复标识为 `automatic_service`，不能当作学习成员动作。

交接条件的 resolved 仅表示当前等待收到了适用范围内的回复，不代表资料的业务内容正确。例如，提供者可以真实选择已经退休的旧版本；系统不会代其换成新版。业务适用性须由成员判断，并由独立内容评价另行检查。

## 来源、执行与复核

实现者实际读 `data` 和已交接的 `basis`，为 `TEAM::build` 分别明确采用精确引用，然后编辑 `code`。`sql_build(input_aliases=["data", "basis"])` 把实际代码及类型化输入投影到有限 DuckDB 执行，真实结果新版本包含执行来源。`read`、`adopt`、文件依赖与 SQL 实际执行输入分别记录，不能互相冒充。

提交合同公开要求两份文件：`code` 与 `result`。`preflight_submission` 只检查公开格式、引用、依赖和执行来源事实，返回 `structurally_ready`；它不评价业务数值，也不填入缺失依据。工作批准采用真实 reviewer 的明确动作。独立领域评价使用 Python 从精确采用的事实重算有限口径，并检查实际 SQL 执行 provenance；不把员工可编辑测试、SQL 文本相似度或制度批准当作业务真值。

程序复核者另从其真正读到的 `audit_basis` 和 `data` 构造检查。修订控制先真实提交将 `COUNT(DISTINCT order_id)` 改成 `COUNT(order_id)` 的 SQL 结果，随后走 `raise_issue → withdraw → 编辑及重新build → submit → respond_issue → decide_issue(accept_fix) → approve`。初次错误提交和后续正确提交均保留，未以最终成功覆盖历史。

## 配置与复验

模板位于 `src/proworksim/templates/decision_team.py`，场景 recipe 为 `decision_team`。`examples/decision-team-v12/` 有四个基础实例/布局配置及迟到、旧版并存、不可得、全信息控制。角色任务不指定主动交接或请求后交接，也不按实例或布局标签改变；精确环境条件在场景 manifest 的 `variation.xi` 中固定。

只运行 CPU 程序见证，不触发场景内 model policies：

```bash
.venv/bin/python scripts/decision_team_experiment.py --output runs/decision-team-v12-new --jobs 4
```

输出目录必须尚不存在。基础矩阵为 `2 数据实例 × 2 信息布局 × 2 私有程序交接调度`，加 4 个机制控制及 1 条复核修订控制，共 13 条。程序调度仅在规则见证配置中选择路径，不能用于声称同一模型提示下的实测类支持。用于模型运行的场景文件不含此调度选择。

每条见证在动作前 `begin_episode`，通过成员各自真实 public port 记录 tools、observations、actions 和 returns，并有独立捕获对照；环境事件另记。执行后 `finish_episode` 固定起止世界、全部精确提交及经验区间，再运行独立内容和有效性评估。所调用的有效性入口从实际捕获、世界提交、sender read → handoff → delivery、实现者读/采用/提交、复核者读取固定交付及复核依据推导结果，不手填四个 true。

同一 ξ 的两种路径比较使用 `initial_business_state`，只规范掉实例/分支标识、墙钟耗时及 receipt/transition 诊断摘要；逻辑时间、工作义务、调用、版本、权限、消息、顺序与材料字节均保留。另比较完整场景和全部角色任务的摘要。

## 已完成的开发验证与限制

`runs/decision-team-v12-dev2/report.json` 记录 **13 条开发见证、73/73 项检查**：8 条基础见证、迟到、旧版并存、全信息及修订共 12 条 completed；不可得 1 条真实停止，`V=unknown`。四组同 ξ 对照的初始业务状态、场景及角色任务摘要均一致。该批为 commit `17b5698542afe28790ac16290ee9647d4dd28da3` 上的 dirty 开发稿，起止 source tree 摘要一致；不冒称干净正式冻结。

开发期保留了以下修正证据：manual unavailable 的对象限定授权需要在条件凭据中保留对象身份；generic request 曾可排入自动 provider 回复（没有证明私有文件读取越权），后增加真实拒绝回归；首版见证驱动误用 `decide_issue="resolved"` 得到真实拒绝，dev2 使用公开合法值 `accept_fix`。旧开发世界与原结果未覆盖。

本模块的程序见证、正式模型执行和训练收益必须分别报告。程序路径可行性、结构合法、独立内容正确、有效性准入、模型分布的类支持以及重配资格均不是同一个判断。特别地，全信息控制改变了 ξ；旧版并存、迟到或不可得也各是独立条件，不能把它们与基础 ξ 的样本合并增加同起点类支持数。
