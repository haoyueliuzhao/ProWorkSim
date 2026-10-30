**历史异常清单：只读分类，不修改原成绩（v095）**

范围为 v088 原 1,000 个 DeepSeek 5M 首次回合中的 205 项历史生成未知和 29 项未开始；正在执行的 44 项预算截止独立恢复另列。原面板记录仍为 722 closed、249 technical_unknown、29 not_started。此次没有生成、评分、容器、GPU、root 操作，也没有修改账本或旧原件。

| 当前证据 | 数量 | 应如何处理 |
| --- | ---: | --- |
| controller 内已有终态候选锁 | 27 | 全为 PROJECT；已有 project-candidates/lock 和 terminal-code/lock，API费用已结算且环境静止。先核原 close_claim、绑定、补丁及归档，再考虑原候选补评；不能因 host candidate_lock 为 null 就重新采样 |
| 三张 API 账表均无请求证据 | 78 | 原物理环境已消费并清理，可准备同一原模型尝试的接续；不能覆盖旧结果或复用已消费 claim |
| 有实际 API 调用，但当前小文件未确认终态锁 | 100 | 其中27项仍有 OOM 完整归档，交独立闭合审计进一步核验；其余73项也不能只靠字段缺失就断言所有归档中无候选。若最终无可信原候选，新增模型采样须单独授权 |
| 原 not_started | 29 | 28槽对应14个环境问题；另1槽 SymPy-15599 PROJECT 已有有效资格，仅因当时 API 全局暂停未开始 |

前三行合计205；最后一行另为29。27个小锁是“进入候选恢复审计”的数量，不是本次已恢复评分的数量。所有新统计按原逻辑任务身份保留，不将部署失败、独立恢复或评分重试加进基准分母。

78项零API的 requests、response_observations、provider_protocol_events 均为0；全部有静止、无清理错误、无未知创建结果和无残留对象证据。68项有 actor/controller/volume 历史容量 claim，10项有 actor/volume；原清理记录实际移除了76个actor、68个controller、78个volume，不能误称从未创建过环境。72项原 model_dispatch_started=false、5项因 OOM 无该字段，另1项为true；该标记是框架阶段，不能替代真实API账本。完整名单和释放证据见 [zero-api-78.json](zero-api-78.json)。

29项未开始逐题核验均无生成 episode、actor/controller/volume claim 和API请求，不是仅依赖状态标签。SymPy-15599 的 PROJECT1188 原因明确为 `api_shared_halted`，其 gold=true、empty=false，v064资格和v066复用资格均passed；它不属于需要重修环境的28槽，也不需要为此重新运行gold/empty。其余问题如下。

| 原任务 | 槽数 | 已观察原因 |
| --- | ---: | --- |
| Sphinx 10435/7985/8269/8475、Requests2317、Matplotlib20488 | 12 | 评分测试需要外部网络资源；现有离线环境出现DNS/连接失败，gold不能通过全部指定测试。部分日志还有其他套件错误，不能承诺联网后必然全过 |
| Pylint4661 | 2 | 缺少appdirs，离线pip无法获取依赖，测试导入失败 |
| Requests1142 | 2 | 容器初始基线不等于冻结的干净树，测试前被身份门拒绝 |
| Requests1724 | 2 | 容器旧解释器没有os.sched_getaffinity，私有评分边界探针失败 |
| Pylint8898 | 2 | 边界探针结果无法解析为JSON；现有日志不足以确认原stdout是空还是其他非JSON内容 |
| Requests1921 | 2 | 官方测试gold通过、empty失败，但容器删除后CA最终身份读取404，导致完整性/清理资格未通过 |
| Django10097 | 2 | 7个目标报缺少registration模板；日志混合使用/testbed与安装的Django egg。模板缺失已确证，是否加载非预期安装副本需进一步环境身份核验 |
| Django10554 | 2 | Gold通过；empty在unittest错误输出阶段再次触发ORDER BY数据库异常，没有形成有效的测试状态报告 |
| Django7530 | 2 | 空基线也通过指定FAIL_TO_PASS目标；其他测试虽然报错，不能替代目标应失败的鉴别要求 |

这些28槽需要相应环境修复及可信控制后才能启动模型；不修改参考补丁、官方验收测试或把错误控制重标为通过。各gold/empty的原结果、具体失败行及日志入口见 [environment-inventory.json](environment-inventory.json)。分析区分原v064与后续v066控制，保留二者原件。

另有已生成候选的评分异常1675、3536、5530，不属于以上205生成未知或29未开始，不重复计数。1675日志确认离线构建缺 `flit_core>=3.7`，并伴随官方测试文件复位/补丁应用错误；5530确认新测试文件复位路径不匹配，之后官方测试补丁应用失败。两项的失败行见 [additional-scoring-environment-failures.json](additional-scoring-environment-failures.json)，3536由独立评分恢复流程处理。此次不下载依赖、不改测试补丁、不重评。

费用是交叉限制，不能作为额外任务再计一次：原29条未决API预约均落在上述100项中，合计 **152.04352元**；没有释放或退款，也没有当成0消耗。全批人民币上限仍 **1,700元**。有可信候选时可以独立审查评分，但不能借补评抹掉这笔未定费用；无可信候选时，已有模型调用也不能伪装成“零生成接续”。

机器入口为 [summary.json](summary.json)，原始结构索引为 [inventory.json.gz](inventory.json.gz)（无损压缩，原件保留本地；可用 `gzip -dk inventory.json.gz` 恢复）。27个候选和33个OOM来源已交接 [candidate-review-handoff.json](candidate-review-handoff.json)；该交接与本清单不宣称已完成闭合恢复。大归档未重复批量解压，后续小锁闭合审计可能进一步收窄100项的未定范围。时间、请求身份、资源消费与原件SHA都保留，文本片段中的测试Authorization值和无关内存地址已脱敏。
