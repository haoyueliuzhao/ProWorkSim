# v201：事实标注规范与逐项证据

对应[实验报告](software-benchmark-v201-frozen-f1-holdout-report.md)，2026-11-12。适用于单个真实输入边界，禁止使用该请求之后的模型回答、未来测试或终局评分反推必要性。

## 1. 八个维度

| 维度 | 核验内容 | 不允许的替代判断 |
| --- | --- | --- |
| Factuality | 值或片段确实存在于当时真实输入 | 模型摘要自我证明、未读源码补全 |
| Provenance | request身份、消息哈希、作用域、JSON路径和字符区间 | 仅文件名相同或关键词出现 |
| Version Validity | 原执行／文件版本，以及当前、历史、未知边界 | 旧通过继承为新版本通过 |
| Task Relevance | 对明确定义的当前决策是否有帮助 | 所在事件Useful就给所有Fact同标签 |
| Necessity | 当前决策所需、可由替代证据满足或未知 | 把有用背景全部升级为必要 |
| Complementarity | 哪些事实应同时考虑，关系证据和范围是什么 | 共现就当因果或效用超加性已成立 |
| Redundancy | 是否被当前窗口／动作／等价同版本证据提供 | 不同执行或不同版本相似文本直接合并 |
| Recoverability | 当前视图有合法引用且可按页恢复原文 | 后台磁盘有记录就认为Agent可取得 |

本轮`necessary`是主AI对所声明决策的开发判断，非全任务所有正确路径的数学必要性。不能以事实匹配程序代替相关性和必要性审阅。`useful`表示相关但未认定不可替代；`irrelevant`对照主要为重复工作台协议版本，不覆盖全部噪声类别。未标注事实保持未知。

后续人工审阅应由两位审阅者分别冻结标注，隐藏方法输出、历史分数与另一人的判断，再由第三方处理分歧。保留初稿与理由，报告一致性和不确定性；没有做到时只能称AI开发参考。既有“自行审阅”安排不等于已经完成人工步骤。

## 2. 本轮逐题结果（主档2048）

| 任务 | 点数 | A必要 | B必要 | C必要 | A输入估计 | B输入估计 | C输入估计 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| astropy__astropy-8872 | 2 | 4/4 | 4/4 | 3/4 | 51571 | 51651 | 49802 |
| django__django-13807 | 2 | 2/2 | 2/2 | 2/2 | 71457 | 71882 | 68052 |
| matplotlib__matplotlib-22719 | 2 | 2/2 | 2/2 | 2/2 | 82958 | 83334 | 79571 |
| psf__requests-1766 | 1 | 2/2 | 2/2 | 2/2 | 57866 | 58099 | 56097 |
| pydata__xarray-3677 | 2 | 3/3 | 3/3 | 3/3 | 69718 | 69870 | 67015 |
| pylint-dev__pylint-4970 | 2 | 3/3 | 3/3 | 3/3 | 76435 | 76969 | 73146 |
| pytest-dev__pytest-7432 | 2 | 3/3 | 3/3 | 3/3 | 82359 | 82803 | 78934 |
| scikit-learn__scikit-learn-25232 | 2 | 2/2 | 2/2 | 2/2 | 111739 | 111866 | 107930 |
| sphinx-doc__sphinx-9698 | 2 | 3/3 | 3/3 | 2/3 | 76044 | 76199 | 72419 |
| sympy__sympy-21930 | 2 | 3/3 | 3/3 | 2/3 | 62792 | 63528 | 59741 |
| pylint-dev__pylint-4604 | 2 | 3/4 | 3/4 | 2/4 | 67077 | 67664 | 63735 |
| sympy__sympy-19954 | 2 | 3/3 | 3/3 | 3/3 | 64983 | 65417 | 61614 |

先按任务聚合事实再算宏平均；23个点没有作为23个独立任务。输入合计因Requests只有1点，不能未经加权作为任务平均成本。

## 3. 62项参考及默认呈现

| 编号 | 标签 | 版本 | 原值／片段（显示截短） | A | B | C | 判断理由 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H01-1-R01 | necessary | current |                 if not (np.can_cast(np.float32, value.dtype) or                         value.dtype.fields):                     dtype = float  | 是 | 是 | 否 | Quantity复制快路径也含dtype提升条件；只检查后一个数组分支不足以限定修改范围。 |
| H01-1-R02 | necessary | current |         if dtype is None and (not (np.can_cast(np.float32, value.dtype)                                    or value.dtype.fields)                               or value.dtype.kind == 'O'):             value = value.astype(float)  | 是 | 是 | 是 | 第二个dtype默认转换分支与float16现象直接相关，需与快路径对照。 |
| H01-2-R01 | necessary | current | +                if not (np.can_cast(value.dtype, np.float32) or  | 是 | 是 | 是 | 当前实际diff中的转换方向是核对是否改变高精度行为的证据。 |
| H01-2-R02 | necessary | current | False | 是 | 是 | 是 | 修改后的v3是否已有实际执行证明，不能由修改意图推断。 |
| H02-1-R01 | necessary | current | {'collected': 69, 'errors': 1, 'failed': 1, 'passed': 56, 'skipped': 11, 'xfailed': 0, 'xpassed': 0, 'tests_run': 57} | 是 | 是 | 是 | 同版本公开运行有失败和错误，决定下一步定位而非交付。 |
| H02-1-R02 | useful | historical |                         'PRAGMA foreign_key_list(%s)' % table_name                     ).fetchall()\[foreign_key_index\]  | 否 | 是 | 否 | 历史另一处PRAGMA插值提示检查表名引用范围；当前动作已经给出修订，不能视为唯一必要旧事实。 |
| H02-1-R03 | irrelevant | historical | role-workbench-v0.16 | 否 | 否 | 否 | 固定工作台协议版本重复，不是当前故障的任务证据；权限边界仍由共同协议保留。 |
| H02-2-R01 | necessary | current | {'collected': 50, 'errors': 0, 'failed': 0, 'passed': 41, 'skipped': 9, 'xfailed': 0, 'xpassed': 0, 'tests_run': 41} | 是 | 是 | 是 | 41通过9跳过只限定当前选择范围，不是全库无错。 |
| H02-2-R02 | useful | historical | {'collected': 68, 'errors': 20, 'failed': 0, 'passed': 37, 'skipped': 11, 'xfailed': 0, 'xpassed': 0, 'tests_run': 37} | 是 | 是 | 否 | 旧v5有20个错误，可作诊断历史；不能用于声称当前v7仍有20错误。 |
| H02-2-R03 | irrelevant | historical | role-workbench-v0.16 | 否 | 否 | 否 | 重复工作台协议版本不构成当前任务证据，来源权限由共同协议维护。 |
| H03-1-R01 | necessary | current | False | 是 | 是 | 是 | 修改后的版本是否已有执行证据决定是否可以闭合；只承认harness状态。 |
| H03-1-R02 | useful | historical |             is_numlike = all(units.ConversionInterface.is_numlike(v)                              and not isinstance(v, (str, bytes))                              for v in values)  | 是 | 是 | 否 | 旧all(generator)条件说明空输入触发数值分支；新修订已在动作链中可见，不把旧片段单列必需。 |
| H03-2-R01 | necessary | current | False | 是 | 是 | 是 | 当前v4的执行状态决定能否闭合。 |
| H03-2-R02 | useful | historical |             is_numlike = all(units.ConversionInterface.is_numlike(v)                              and not isinstance(v, (str, bytes))                              for v in values)  | 是 | 是 | 是 | 历史v3转换条件用于审阅空输入分支，不把其读取当v4测试结果。 |
| H03-2-R03 | irrelevant | historical | role-workbench-v0.16 | 否 | 否 | 否 | 重复工作台协议版本不构成当前任务证据，来源权限由共同协议维护。 |
| H04-1-R01 | necessary | current | {'collected': 90, 'errors': 0, 'failed': 45, 'passed': 45, 'skipped': 0, 'xfailed': 0, 'xpassed': 0, 'tests_run': 90} | 是 | 是 | 是 | 公开运行45失败45通过，不能按Agent声明推成完整公测通过。 |
| H04-1-R02 | necessary | current | gaierror | 是 | 是 | 是 | 失败输出中网络错误的原文是区分环境限制与代码失败的证据；不据此认定全部45失败同因。 |
| H04-1-R03 | irrelevant | current | role-workbench-v0.16 | 否 | 否 | 否 | 固定工作台协议版本重复，不是当前故障的任务证据；权限边界仍由共同协议保留。 |
| H05-1-R01 | necessary | current | False | 是 | 是 | 是 | 当前v3的验证执行状态应与已编辑代码区分。 |
| H05-1-R02 | useful | historical |     overwrite_vars: Union\[Hashable, Iterable\[Hashable\]\],     compat: str,     join: str,     fill_value: Any,  | 否 | 否 | 否 | 既有覆写选择器属于修改约束，历史签名不是当前行为验证。 |
| H05-2-R01 | necessary | current | {'collected': 21, 'errors': 0, 'failed': 0, 'passed': 21, 'skipped': 0, 'xfailed': 0, 'xpassed': 0, 'tests_run': 21} | 是 | 是 | 是 | 21通过属于test_merge子集；是交付声明可核对的执行事实。 |
| H05-2-R02 | necessary | current | delivery-1 | 是 | 是 | 是 | 当前版本合法交付身份由harness记录而非Agent自述决定。 |
| H05-2-R03 | irrelevant | current | role-workbench-v0.16 | 否 | 否 | 否 | 重复工作台协议版本不构成当前任务证据，来源权限由共同协议维护。 |
| H06-1-R01 | necessary | current | False | 是 | 是 | 是 | 当前版本未获执行证明时不能将写入等同通过。 |
| H06-1-R02 | useful | historical |             self.min_lines = self.config.min_similarity_lines  | 否 | 是 | 否 | 配置项到内部阈值的赋值解释检查入口；不是独立测试结果。 |
| H06-2-R01 | necessary | historical | {'collected': 18, 'errors': 0, 'failed': 1, 'passed': 17, 'skipped': 0, 'xfailed': 0, 'xpassed': 0, 'tests_run': 18} | 是 | 是 | 是 | 旧版1失败的实测记录构成返修背景，未重验不能抹去。 |
| H06-2-R02 | necessary | current | False | 是 | 是 | 是 | 新v5的验证状态必须与v4失败分开。 |
| H07-1-R01 | necessary | current | False | 是 | 是 | 是 | 新v5尚需精确版本的测试证据。 |
| H07-1-R02 | useful | historical |     if not item.config.option.runxfail:         if xfailed and not xfailed.run:  | 否 | 否 | 否 | 旧控制条件为定位背景；本轮修改动作已保留相关内容，不称唯一必要旧证据。 |
| H07-1-R03 | irrelevant | historical | role-workbench-v0.16 | 否 | 否 | 否 | 固定工作台协议版本重复，不是当前故障的任务证据；权限边界仍由共同协议保留。 |
| H07-2-R01 | necessary | current | delivery-1 | 是 | 是 | 是 | 同版本合法交付回执是结束判断的证据，不等于官方评分通过。 |
| H07-2-R02 | necessary | current | True | 是 | 是 | 是 | harness的同版本公开状态仅限定其选择测试，不能替代完整未读报告。 |
| H07-2-R03 | irrelevant | historical | role-workbench-v0.16 | 否 | 否 | 否 | 重复工作台协议版本不构成当前任务证据，来源权限由共同协议维护。 |
| H08-1-R01 | necessary | current | +                fill_value=self.fill_value,  | 是 | 是 | 是 | 已见实际diff体现参数转交，限定本次候选改动的事实。 |
| H08-1-R02 | useful | historical |             self.initial_imputer_ = SimpleImputer(                 missing_values=self.missing_values,                 strategy=self.initial_strategy,                 keep_empty_features=self.keep_empty_features,             )  | 否 | 是 | 否 | 旧构造调用与本次参数转交互补，不能据旧文本认定当前实现仍缺参。 |
| H08-1-R03 | irrelevant | historical | role-workbench-v0.16 | 否 | 否 | 否 | 固定工作台协议版本重复，不是当前故障的任务证据；权限边界仍由共同协议保留。 |
| H08-2-R01 | necessary | current | {'collected': 78, 'errors': 0, 'failed': 0, 'passed': 78, 'skipped': 0, 'xfailed': 0, 'xpassed': 0, 'tests_run': 78} | 是 | 是 | 是 | 78通过是当前选择器的实测覆盖。 |
| H08-2-R02 | useful | historical | {'collected': 78, 'errors': 0, 'failed': 1, 'passed': 77, 'skipped': 0, 'xfailed': 0, 'xpassed': 0, 'tests_run': 78} | 否 | 否 | 否 | v6的1失败是历史返修依据，不能与v8通过混成同一执行。 |
| H08-2-R03 | irrelevant | historical | role-workbench-v0.16 | 否 | 否 | 否 | 重复工作台协议版本不构成当前任务证据，来源权限由共同协议维护。 |
| H09-1-R01 | necessary | historical | {'collected': 46, 'errors': 0, 'failed': 1, 'passed': 45, 'skipped': 0, 'xfailed': 0, 'xpassed': 0, 'tests_run': 46} | 是 | 是 | 是 | 已执行报告仍有一失败，后续测试修改不能自动消除此结果。 |
| H09-1-R02 | useful | historical |         if 'property' in self.options:             return False         else:  | 是 | 是 | 否 | 历史property分支提供结构背景，不是当前测试通过证明。 |
| H09-1-R03 | irrelevant | historical | role-workbench-v0.16 | 否 | 否 | 否 | 固定工作台协议版本重复，不是当前故障的任务证据；权限边界仍由共同协议保留。 |
| H09-2-R01 | necessary | current | {'collected': 46, 'errors': 0, 'failed': 0, 'passed': 46, 'skipped': 0, 'xfailed': 0, 'xpassed': 0, 'tests_run': 46} | 是 | 是 | 否 | 当前v3的46通过来自历史实际运行，区别此前v2的1失败。 |
| H09-2-R02 | necessary | current | delivery-1 | 是 | 是 | 是 | 确认当前交付身份以防把重新阅读当新交付。 |
| H09-2-R03 | irrelevant | current | role-workbench-v0.16 | 否 | 否 | 否 | 重复工作台协议版本不构成当前任务证据，来源权限由共同协议维护。 |
| H10-1-R01 | necessary | current | False | 是 | 是 | 是 | 当前v7的执行状态比Agent的修复意图更能限定交付判断。 |
| H10-1-R02 | useful | historical |         return "b^\\dagger_{%s}" % self.state.name  | 是 | 是 | 否 | 原创建算符格式化文本为历史缺陷背景；新修改可在动作链核对。 |
| H10-1-R03 | irrelevant | historical | role-workbench-v0.16 | 否 | 否 | 否 | 固定工作台协议版本重复，不是当前故障的任务证据；权限边界仍由共同协议保留。 |
| H10-2-R01 | necessary | historical | {'collected': None, 'errors': 0, 'failed': 6, 'passed': 60, 'skipped': 1, 'xfailed': 1, 'xpassed': 0, 'tests_run': 66} | 是 | 是 | 否 | 原v7的六失败尚有历史诊断价值，不能因改写预言自动宣称消除。 |
| H10-2-R02 | necessary | current | False | 是 | 是 | 是 | 新v10没有同版本执行证明时，应保持待验证。 |
| H10-2-R03 | irrelevant | historical | role-workbench-v0.16 | 否 | 否 | 否 | 重复工作台协议版本不构成当前任务证据，来源权限由共同协议维护。 |
| H11-1-R01 | necessary | historical |         if not isinstance(type_annotation, astroid.Subscript):             return  | 是 | 是 | 否 | 旧被调函数会在非Subscript处返回，影响新增转发是否真正收集abc.ABC的名称。 |
| H11-1-R02 | necessary | historical |                     imported_name in self._type_annotation_names                     or as_name in self._type_annotation_names  | 否 | 否 | 否 | 名称集合如何决定unused-import抑制，与类型注释解析组成当前诊断链。 |
| H11-2-R01 | necessary | current | {'collected': 7, 'errors': 0, 'failed': 1, 'passed': 6, 'skipped': 0, 'xfailed': 0, 'xpassed': 0, 'tests_run': 7} | 是 | 是 | 是 | unused_import选择仍有1失败；另一小子集2通过不能覆盖它。 |
| H11-2-R02 | necessary | unknown | Path is absent from this source version. Copy an exact path from list_files or search_repository. To create a new file, explicitly use create_file; write_file only replaces an existing file. | 是 | 是 | 是 | 真实拒绝表明路径不存在，决定下一步重新定位而非继续同一错误入口。 |
| H11-2-R03 | irrelevant | historical | role-workbench-v0.16 | 否 | 否 | 否 | 重复工作台协议版本不构成当前任务证据，来源权限由共同协议维护。 |
| H12-1-R01 | necessary | current | {'collected': None, 'errors': 0, 'failed': 0, 'passed': 64, 'skipped': 1, 'xfailed': 2, 'xpassed': 0, 'tests_run': 64} | 是 | 是 | 是 | 当前v2公开套件64通过及跳过范围是继续加测试或交付判断的证据。 |
| H12-1-R02 | useful | historical |                         del num_blocks\[i\], blocks\[i\]                         to_remove.append(rep_blocks\[i\])  | 否 | 否 | 否 | 旧删除和rep_blocks引用顺序解释IndexError；当前diff已保留修改，旧源不当新版验证。 |
| H12-1-R03 | irrelevant | historical | role-workbench-v0.16 | 否 | 否 | 否 | 固定工作台协议版本重复，不是当前故障的任务证据；权限边界仍由共同协议保留。 |
| H12-2-R01 | necessary | historical | {'collected': None, 'errors': 0, 'failed': 1, 'passed': 63, 'skipped': 1, 'xfailed': 2, 'xpassed': 0, 'tests_run': 64} | 是 | 是 | 是 | v4全套1失败属于实际执行记录，新预言v5尚不能替代。 |
| H12-2-R02 | necessary | current | False | 是 | 是 | 是 | 当前v5必须使用新版本执行证据。 |
| H12-2-R03 | irrelevant | historical | role-workbench-v0.16 | 否 | 否 | 否 | 重复工作台协议版本不构成当前任务证据，来源权限由共同协议维护。 |

表中长文字为了阅读截短，完整值、source_id、消息哈希、派生索引、pointer和span在`artifacts/software-benchmark-v201/annotations-r1/Hxx-x.json`。这些标签在207个视图生成前已封存，运行器只读取其文件哈希，不读取标注值。

## 4. 可复现来源与运行

来源映射使用真实tool call ID及原已见观察的内容哈希。对`_v117_same_input_static_fields`只从同次真实输入锚点复核，再与此前完整输入的严格JSON结构比对；未将重建内容伪装成新的模型观察。派生索引可跨SDK摘要保持身份，实际source_id仍包含每次真实消息哈希。

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/python tools/run_offline_scorer_v096.py tools/prepare_fact_holdout_v201.py
LITELLM_LOCAL_MODEL_COST_MAP=True OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/python tools/run_offline_scorer_v096.py tools/run_fact_holdout_v201.py
.venv/bin/python tools/score_fact_holdout_v201.py
.venv/bin/python -m pytest -q tests/test_history_source_v201.py
```

完成目录拒绝覆盖；不应为刷新分数重新运行或改标签。实际raw wire、common frame、source witness与静态锚点链在`runs/software-benchmark-v201/source-prefix-r1/`，counterfactual视图与reader entries在`runs/software-benchmark-v201/offline-r1/`。同题两个决策点不是两次独立运行；全部来自封存历史。

首批人工录入配方中H10-1的来源索引10没有result字段，写入前被拒绝，改为实际代码来源11后才封存；已封存的其他前缀未重写。原配方与后续补齐配方均保留，这不是模型失败或重采。

源适配器：[software_history_source_v201.py](../../src/proworksim/software_history_source_v201.py)；准备／标注／对照／统计：[准备](../../tools/prepare_fact_holdout_v201.py)、[标注封存](../../tools/annotate_fact_holdout_v201.py)、[运行](../../tools/run_fact_holdout_v201.py)、[统计](../../tools/score_fact_holdout_v201.py)。

## 5. 尚未启动的阶段

F1-T需要由真实harness状态与动作确定工作阶段，不能把模型一句“已修好”当验证状态。F1-G只能使用已确认依赖，不为获益提升Inferred。两者的启动条件仍是本轮主档推进门通过，本轮未满足。

真实单Agent比较应保留M1-5与冻结F1-2048，同题、独立工作区和相同总预算；统计模型实际读回、版本／片段正确性、工具行动与事实的可核查关联、代码与交付双端点和完整费用。关键词提及或时间先后都不能单独证明事实因果作用。

24题×两条件、每回合5M以及重复诊断仅为后续设计上限，没有本轮模型调用或预算授权。本轮不自动申请旧余额、不启动训练或REVIEW2。组织—通信—上下文协同仍需经真实成员、职责、交接、采用和测试回执逐层验证。
