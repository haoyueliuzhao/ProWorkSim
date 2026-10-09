# v0.39 新组织开发根目标与CPU任务控制

四个新业务根目标已实现，15项任务控制通过，Ruff通过。控制使用20个程序变体、40次真实CPU隔离执行；没有调用9B或其他模型、没有使用GPU、没有反向或参数更新。此记录说明任务的有限实现/验收合同可运行，不能作为模型组织能力或增员收益。

## 来源与用途

四个任务均为本项目新编写的业务合同，基于已经固定的 pristine `schema@24a3045773eac497c659f24b32f24a281be9f286` 环境。该库环境具有SWE-smith来源谱系，新合同不是上游issue改名，也不是旧v0.38四个业务合同的换名版本。原任务、旧源manifest、历史结果和参数状态没有改写。

全部新root用途为 `organization_development`，训练、Contribution与独立确认资格均为false。复用了schema库环境，不声称独立来源泛化或未接触环境；没有读取TextFSM确认池。F2、A3、X3使用完全相同的业务根、初始文件、公开/私有质量规则，条件差由另行冻结的人员制度控制。

| 顺序 | 新root | 层次 | 生产模块 | 主要功能义务 |
|---|---|---|---|---|
| 0 | sc-label-index-v039 | 轻任务控制 | labels.py、consumer.py | 用真实schema得到归一化标签，再给出稳定名称序列与每项索引 |
| 1 | sc-row-projection-v039 | 轻任务控制 | columns.py、consumer.py | 验证选择列的合法性/不重复，按指定顺序投影每行，区分缺失与原标量 |
| 2 | sc-record-views-v039 | 交叉依赖 | records.py、report.py、query.py | 同一规范记录表示支持分组报告及筛选视图；名称、顺序、重复与原始位置一致 |
| 3 | sc-record-catalog-v039 | 交叉依赖 | records.py、report.py、query.py | 同一catalog保留首出现key顺序与末出现value，支持表格和批量lookup |

层次用于面板和报告，不添加“应该招募”的角色指令。合同列的是功能与公共API，不预生成接口开发、报告开发、验证等任务卡；任何成员都能读相同公共代码并编辑全部应用模块。空任务板、无初始负责人；允许一人集中完成，也允许自行分工。没有强迫多人、通信次数、任务数量或固定岗位。

## 简明输入边界与真实依赖

合同明确规定形状域外不验收；只处理以下有限业务拒绝，不让成员额外猜测广泛错误恢复策略。

| root | 保证的输入形状 | 合同内必须处理的拒绝 | 核心一致性/空输入规则 |
|---|---|---|---|
| label-index | ASCII字符串列表 | 去外空白/小写后不是非空a–z名称，整表返回拒绝 | 名称按首次出现稳定去重；positions保重复，空表有效 |
| row-projection | 列名ASCII字符串列表；rows是约定名字到字符串/整数/布尔/null的字典列表 | 非小写a–z列名或重复列，整个选择拒绝 | 列序与行序保留，缺失为null；空选择保留每行空列表，空rows仍保留选择 |
| record-views | rows字典恰含name/group两个ASCII字符串；query group是规范小写名 | 任一规范化name/group无效，整表拒绝 | shared product保原始位置和重复；报告组序与筛选位置均来自同一表示；空表有效 |
| record-catalog | rows字典恰含key及字符串/整数/布尔/null value；查询key是规范名列表 | 任一记录key无效，整表拒绝，即使查询列表为空 | 首key顺序、末value、false/0/null区别；查不到与存在null分别有found=false/true |

两个交叉依赖root的两个消费者必须调用并消费同一共享产品；它们同时通过才是完整合同。依赖来自代码/API与数据表示，不来自成员专有工具、秘密文件或研究者安排的岗位。没有金额换算、日期规则、持久服务或网络系统。

## 公开/私有材料与冻结绑定

每个root将公共合同、starter、pinned schema及公开driver装入初始副本；`test_member.py`初始只有注释。starter明确留下待实现公共函数，没有预置正确业务实现或任务组织轨迹。`reference/`、`controls/`、`acceptance.json`不进入初始文件集、成员观察或模型提示。

| root | 公开业务检查 | 每次公开执行另含原库回归 | 私有同合同检查 |
|---|---:|---:|---:|
| label-index | 6 | 1 | 7 |
| row-projection | 6 | 1 | 7 |
| record-views | 7 | 1 | 9 |
| record-catalog | 7 | 1 | 9 |
| 合计 | 26 | 每root 1 | 32 |

公开/私有完整request集合在同一root内不重合；私有检查只使用公共合同允许的输入，并非保留TextFSM独立确认材料。私有worker仅接收输入请求，预期答案由控制器比较，不发送给被执行程序。私有验收仍只由终态固定交付路径触发，源控制中的reference执行是明确分离的CPU资格。

新[source manifest](../../examples/software-organization-v039/source-manifest.json)绑定合同、starter、公开/私有fixture、reference、反控制及公开/私有driver摘要；[source partition](../../examples/software-organization-v039/source-partition.json)绑定新用途。原库文件按原哈希读取，未施加旧缺陷patch。manifest的`sha256`是排除自身字段后的规范payload摘要，实际文件字节摘要另存[任务机器记录](software-organization-v039-tasks.json)。

源适配器提供`build_case`、`run_public_tests`、`assess_files`、`reference_solution`、`source_manifest`和`source_partition`；全部root初始`task_definitions={}`、`initial_owners={}`。公共检查、完整内容结果、规定API关系及观察完整性分别保留；成员脚本反馈继续由世界层处理。

## 必要CPU正反控制

最终定向命令运行结果为 **15通过，0失败，0跳过，4.56秒**。Ruff检查新源适配器与测试通过。具体路径、代码/资产绑定和每个程序变体结果见[机器记录](software-organization-v039-tasks.json)。

| root | starter基线 | 完整reference | 绕过真实schema | 绕过共享产品但仍调用schema | 仅完成shared | 仅完成消费者 |
|---|---|---|---|---|---|---|
| label-index | 不合格 | 合格 | 内容正确，过程不合格 | 内容正确，过程不合格 | 不适用 | 不适用 |
| row-projection | 不合格 | 合格 | 内容正确，过程不合格 | 内容正确，过程不合格 | 不适用 | 不适用 |
| record-views | 不合格 | 合格 | 内容正确，过程不合格 | 内容正确，过程不合格 | 不合格 | 不合格 |
| record-catalog | 不合格 | 合格 | 内容正确，过程不合格 | 内容正确，过程不合格 | 不合格 | 不合格 |

全部20变体的公开与私有程序都真实执行，合计40次隔离执行。基线负控制保留原库通过但业务函数未实现；完整reference验证空输入、顺序、重复、精确类型、全局拒绝和调用者输入不变。`library_bypass`由手写等价业务实现跳过真实`Schema.validate`，`product_bypass`则在消费者内部复制同样的schema实现，省略规定共享应用函数调用。后者仍有真实schema调用，因此反控制能具体识别共享产品边缺失。

这些是固定输入上的函数调用与输出观察，不是任意防绕过、完整数据流等价或唯一因果贡献证明。尤其不能从两个消费者都通过推导出必须由不同成员完成，也不能从CPU控制推导模型会自然创建成员、使用伙伴成果或取得更好质量。

冻结前检查移除了一条与公开request完全相同的轻任务私有空输入例，将它换为另一组重复归一化输入；四root的公私完整request均不再重合。该调整发生在模型工作和主库存冻结之前，未产生或替换任何真实模型槽。上述最终15项控制基于修订后的唯一资产版本。

后续主运行的模型、成员条件、seed和库存由主协议冻结；本文件不启动运行，不恢复旧26次试训、正式更新、独立确认或缓存生产验证。
