# v0.35：用途隔离的新 O1 来源

本目录是新合同与新应用程序，不是旧题改标。只复用已经固定的 pristine 源库环境，不施加旧 SWE-smith defect.patch，不复用旧 consumer、私有验收或 Marshmallow 开发经历。训练只有一个精确根目标；贡献开发和独立确认各两个不同根目标。

| 用途 | 新根目标 | 固定环境 | 编辑接口 |
|---|---|---|---|
| policy_training | sp-script-inventory-v035 | sqlparse e57923b3 | reader.statement_records → report.summarize |
| contribution_development | sc-job-policy-v035 | schema 24a30457 | policy.validate_job → consumer.review_jobs |
| contribution_development | sc-command-set-v035 | schema 24a30457 | rules.validate_commands → consumer.apply_commands |
| independent_confirmation | tf-port-status-v035 | TextFSM c31b6007 | adapter.port_records → consumer.port_report |
| independent_confirmation | tf-batch-totals-v035 | TextFSM c31b6007 | adapter.batch_values → consumer.batch_totals |

五个根目标不等于五个独立仓库。三个环境保持原来的仓库用途边界；`source-partition.json` 在编写 fixtures/reference 文件前固定了新 root 分配。每个根目标只有两个生产编辑模块，另允许 `test_member.py`。公开合同中的接口名称不是成员责任、执行任务卡或方法标签；初始任务表为空，两名成员有真实私有副本，可以集中完成或自主协作。

训练 SQL 合同只含公开声明的平面单表 SELECT／UPDATE／DELETE 常量操作。真实 split／parse／Statement.get_type 的产物被报告消费，不要求修复旧 Comparison.right。两个 schema 合同只校验明确的队列／优先级规则或 put／drop 批次，没有默认值、secret 或复杂异常树。两个确认合同使用不同、只读的合法 TextFSM 语法资产，分别是平面状态记录和 Filldown 批次值；消费者没有未声明的异常输入义务。各 `contract.md` 明确顺序、重复、空输入、确切输出类型和输入保持。

公共检查覆盖这些语义，私有检查使用不同输入。相关原库小回归仅为 sqlparse 的 `test_statement_get_type`、schema 的 `test_callable_error`、TextFSM 的 `testParseNullText`／`testReset`；不再把旧缺陷修复或旧消费者验收带入新目标。原库 unit 对只读库本身的输入不是新增的消费者输入范围。完整私有验收是一道任务内评分，与独立确认材料池的用途不同。

API 探针观察实际 Python code object 调用，包含真实库 API 和共享应用产物入口，因此 `from module import function` 的别名不会因临时 monkeypatch 缓存而漏记。探针不替换函数行为。API 是否满足、观测是否完整、业务内容分别记录；profile return 的 None 可能来自异常展开，不冒充成功返回。类型比较和输入保持、公开通过项摘要／完整失败业务反馈、成员自测输出、合同去重均沿用 v0.34 已冻结语义，不开展新的呈现搜优。

`source_contract.contract_symbols` 只列公开合同已经要求的顶层入口。它不包含答案、角色、路线或类别；用于排除与合同无关的新 helper、注释和排版变化，不能证明作者或因果贡献。确认合同不参与 Mapper 开发或配置选择。

## 暴露时间与旧用途

旧 `software-sources-v028/source-partition.json` 中的 `previously_used=false` 是 2026-10-02 冻结时的值，不是当前未暴露证明。v0.28 来源资格记录有 42 次 CPU 隔离执行、0 模型 episode、0 参数更新；当时实际模型开发工作使用 Marshmallow。v0.29 的 sqlparse 旧训练题随后实际运行了 8 条当前策略经历，完整有效为 0/8，无可配置支持，新增更新为 0；该批 schema 贡献开发和 TextFSM 独立确认阶段未启动。旧题的失败不能推断新合同适合或不适合现模型。

上述是本项目已归档阶段的用途／暴露证据，不是预训练语料无重合证明。旧 sqlparse／schema／TextFSM 合同及所有历史和当前 Marshmallow 开发题，均不进入这五个新根目标；旧开发题不能改为训练或独立确认。机器出处及 SHA 见 `exposure-audit.json`。

## CPU 资格边界

每根目标只做原始、共享 API 侧、consumer 侧和联合参考四种实际程序控制；20 个变体中前三类失败、联合参考通过完整验收，并保留实际 API／产物返回观察。一条训练来源的真实 SDK／WorldCore 参考路线执行任务创建、编辑、测试、固定发布和提交，R=1；没有重复全套四路线、模型筛选或 16K 训练资格。参考选择与合成 token 明确标为 offline_fixture，不生成可训练 entry，不进入 P2 提示或原始训练分母。

P2 的 M=16、member_a 先手、共同参数与 Γ、seed 清单由外部冻结协议绑定；source case 不含采样 seed。两次独立初始化验证相同业务指纹。新增公开入口元数据后只复核文件不变与指纹，不重复程序或 SDK 验收。

单条参考路线另以已选 Qwen 原生 tokenizer 离线核对 9 个请求及构造输出，零模型／权重加载／GPU：峰值输入 10,282；预留每步 2,048 输出后最小上下文余量 4,054；整条保守 token 上界 91,222，距 500,000 尚余 408,778；构造输出峰值 113 且原解析器往返一致。这是合法参考路径的条件成本见证，不是模型成功、支持频率或训练耗时保证。完整回执在 `runs/v035-controls/world/`。
