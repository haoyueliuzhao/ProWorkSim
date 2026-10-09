# v0.39 新组织开发任务

这里保存四个**项目自建业务合同**，用途仅为 `organization_development`。源码环境复用已固定的 pristine `schema@24a3045773eac497c659f24b32f24a281be9f286`，其来源谱系为 SWE-smith；新业务根目标不是原封不动的上游 issue，不属于训练或独立确认池。旧 manifest、环境用途记录和历史结果保持原样。

| 新 root | 层次 | 生产模块 | 根要求 |
|---|---|---|---|
| sc-label-index-v039 | 轻任务 | labels.py、consumer.py | 全列表标签归一化、稳定去重名称及索引 |
| sc-row-projection-v039 | 轻任务 | columns.py、consumer.py | 验证有序列选择，按同序投影记录并保留缺失/标量类型 |
| sc-record-views-v039 | 交叉依赖 | records.py、report.py、query.py | 同一规范记录表示供分组报告和筛选视图共同使用 |
| sc-record-catalog-v039 | 交叉依赖 | records.py、report.py、query.py | 同一稳定catalog表示供表格和批量查询共同使用 |

这些是功能/API要求，不是执行任务卡。各成员具有相同可读材料和可编辑路径；允许单人集中完成、直接工作、空任务绑定固定交付，也允许模型自行拆分和协商。没有指定谁编写哪一模块，没有强制增员、交流次数、任务数量或测试员岗位。层次字段用于事前面板与报告分析，不向模型附加“应当招募”的提示。

每个 root 的 `contract.md` 明确输入形状保证、需处理的业务拒绝和输出义务；域外形状不验收。没有引入业务金额、时间计算、网络或持久状态。`public-checks.json` 为公开有限示例，`acceptance.json` 为控制器持有的同合同其他请求；同一 root 的公开与私有完整 request 不重合。

`starter/` 和公共合同经源适配器进入初始私有副本。公开 `test_visible.py` 由固定 driver、公开请求和一个原始 `schema` 回归函数组成；可选 `test_member.py` 初始仅有注释。`reference/`、`controls/` 和 `acceptance.json` 均不进入初始文件集、成员观察或模型提示。

`reference/` 是CPU完整正控制；`controls/library_bypass/` 产生正确业务值但不调用真实 `Schema.validate`；`controls/product_bypass/` 仍真实使用 `schema`，却将生产逻辑复制进消费者而不调用合同规定的共享产品函数。后两者应内容正确、规定API关系不合格。两个交叉依赖root还检查仅完成共享产品、仅完成两个消费者均不足以满足完整合同。

验收使用有限的实际函数调用观察和精确JSON比较。通过可证明固定输入上调用了规定API并满足行为，不证明任意防绕过能力、唯一因果贡献或特定团队分工。特别地，这些正反控制不要求三名成员分别实现三个模块。

源适配器为 `src/proworksim/software_organization_tasks_v039.py`。`source-manifest.json` 绑定每份合同、starter、reference、控制程序、公开/私有fixture以及生成driver；`source-partition.json` 绑定四个新root的用途。两个manifest中的 `sha256` 是 `json_bytes` 序列化时排除自身 `sha256` 字段的payload摘要。原库文件按已有哈希逐字读取，未修改旧环境或确认材料。

CPU测试与详细测量见 `tests/test_software_organization_tasks_v039.py` 和 `docs/experiments/software-organization-v039-tasks.md`。CPU通过只说明有限任务合同可运行，不代表模型会组织工作或新成员有收益。
