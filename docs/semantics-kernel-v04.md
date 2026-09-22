# v0.4：工作世界语义内核构建

本轮依据 [内核化审计](reference/semantics-kernel-audit.md)，先写清 [对象语义](../CORE_SEMANTICS.md)、[状态归属](../STATE_OWNERSHIP.md) 与 [行动合同](../ACTION_CONTRACTS.md)，再迁移共用规则。经营世界仍是主模板；文稿微模板只检验复用边界。本轮不进行训练、GPU 使用或新的模型效果研究。

## 实际分层与调用路径

| 实现 | 责任及实际使用者 |
| --- | --- |
| `core/types.py` | Fact、Claim、Assumption、Credential 与四态 CheckResult；事实类型表示来源记载，不自动担保现实真值 |
| `core/references.py` | 确切对象版本与 ApplicabilityContext |
| `core/visibility.py` | 版本访问、幂等授权、嵌套观察投影；经营与文稿共用 |
| `core/rules.py` | confirm_credential / registered_applicability；basis 签发与 editorial_policy 签发共用 |
| `core/conditions.py` | Reply 的证据满足判断、四态结果、局部状态后果与明确恢复机会；两模板共用 |
| `core/work.py` | Submit / Withdraw / Approve / ReviseRequirement / 当前义务与阻塞终态；两模板共用 |
| `core/transitions.py` | Apply/Derive 的实际影响范围、历史保持检查与确定事件顺序；两模板经 World.act 使用 |
| `policies/organization.py` | 权力和职位由配置解释；经营默认机构只是其中一个配置 |
| `domains/operating_toy.py` | 经营分析阶段、growth_delta、scope 和批准依据更新；从 lifecycle 抽出 |
| `domains/publication.py` | 文稿微模板、有限审阅和独立内容检查；没有给 core 添加文稿分支 |
| `adapters/communication.py` | 请求主题的证据取得、消息和授权效果；环境恢复行动 |
| `adapters/action_scopes.py` | 当前工具／事件可修改对象的声明 |
| 原 `kernel.py` | 经营工具门面与事件集成，已调用共享核心；其名字不表示该文件全部成为领域无关代码 |

`basis.py`、`blockers.py`、`lifecycle.py` 保留为适配接口，已有文件工具和不可变存储继续使用。旧经营编译、表格计算和业务审阅仍有领域知识，本轮没有将所有代码强塞进 core。

## 制度效力与内容区分

正式凭据元数据位于指定不可变版本的 `credential`，对应签发事实以 `attestations` 为唯一正式登记。旧 `basis_approvals` 只是历史格式投影；新世界不通过修改它改变效力。确认者按组织授予的主题／工作范围权力检查，角色名称没有制度特权。

读取、可见、声明采用和独立验证支持分别存在。正文自写“经理已批准”或元数据声明新版依据都不自动证明正式效力或实际数值正确。新适用性关系精确指定需求维度、版本、工作节点、用途、期间和时间，不读取全局 latest 来替代判断。

同一产物服务多个当前工作时，`basis_applicability_by_work` 保存每项结论；不同结果的全局摘要为 unknown。该查询明确针对产物当前版本。历史提交按其固定版本评价，因此“当前文件不适用旧工作”不会改写“旧提交曾正确”的事实。

## 行动效果与保持

运行器在提交前比较允许修改的路径和实际差异。`transition` 收据分开记录业务直接变化、派生变化、历史保持以及回滚；Reply 的范围限定到请求、相关条件、工作和确切版本授权。新建字典也按叶路径检查，不能以新增容器绕过范围判断。

已有文件版本的身份、哈希、来源、既有凭据，以及提交内容、完成的审阅和旧消息不允许重写。首次对已有版本正式签发可附加凭据登记，其后的内容不得覆盖。失败动作回滚直接效果，但会记录尝试并推进时间，随后到期事件仍能送达；不能把这称为“失败动作没有任何状态变化”。相同时刻事件按入队顺序执行。

保持检查是有限 JSON 状态事务检查，沿用文件适配器的崩溃恢复；它不是通用并发数据库。部分经营事件仍由专用适配过程驱动。显式路径范围与程序属性共同提供证据，不宣称任意外部插件都已正确声明作用域。

## 条件与信息恢复

消息送达不等于满足条件。条件检查要求真实请求、匹配身份与工作版本、用途、所需证据和正式适用性。重复处理同一已完成回复只返回原结果，不重复发信或授权。

当前 provider 的 unavailable 保留为事实。可恢复性由其他配置提供者和明确 `future_opportunities` 判断。`information_arrival` 事件可通过有权的 `restore_information` 提供真实、同需求适用的凭据，并发出不泄露私有内容的通知。它只恢复选中工作／条件的取得路线；条件仍需新的真实请求和匹配回复才能满足。

提交、批准、回复重开和公开 `dependency_readiness` 使用相同的 current predecessor 解析，防止旧 accepted 前驱与新未完成前驱混用。此就绪关系是派生视图；本轮尚未把所有 activity status 都替换成统一重建器，不能据此宣称所有状态都已经事件溯源。

新 v0.4 即使缺少整个 attestations 或 organization 容器，也不降级获取历史确认／权限。旧格式回读限定在显式历史 schema；不完整的新快照无法从旧投影取得正式效力。

## 微模板与使用

主模板仍使用原 CLI，例如：

```bash
.venv/bin/proworksim build runs/kernel-operating --scenario waiting_reply
.venv/bin/proworksim run runs/kernel-operating --provider baseline
.venv/bin/proworksim evaluate runs/kernel-operating
```

文稿微模板通过 Python 接口或独立实验脚本使用，不扩展为第二个 benchmark，也不接入经营专用课程或训练导出：

```python
from proworksim.domains.publication import compile_publication, PublicationWorld
path = compile_publication("runs/publication-demo", {"author": "writer-7", "editor": "approver-2"})
world = PublicationWorld(path)
print(world.session().observe())
print(world.session().call("read_file", artifact_id="source_note"))
```

三个验收入口：

```bash
.venv/bin/python scripts/world_mechanism_suite.py --output runs/world-regression-new --workers 4
.venv/bin/python scripts/core_semantics_experiment.py --output runs/core-properties-new --workers 4
.venv/bin/python scripts/publication_kernel_experiment.py --output runs/publication-kernel-new --workers 4
```

原十情境保留为回归；新增属性实验关注局部性、历史保持、观察与采用、适用关系、越权、错误执行与授权批准、以及动作组合。文稿实验只检查字段、精确引用和指定短语，不评价专业表达。详细结果见 [实验报告](experiments/semantics-kernel-v04.md)。
