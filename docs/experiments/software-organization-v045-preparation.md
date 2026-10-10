# v0.45组织诊断准备与有限CPU准入

**最终准入通过。65项不同的必要pytest控制均有通过证据，最终Ruff通过；12个新材料条件单元已闭合。此处真实9B调用、权重加载、GPU worker及参数更新均为0。**

## 1. 修订范围

新增四个人工业务root、S1/F2/O3初始化和collector，以及五阶段成果使用测量。S1只有一个真实成员；F2退休不补员；O3同actor、共享预算出生，新会话没有私史免费继承。旧工具、分页、v044反馈投影、正常退役证明和局部context停止语义保留，仅新运行身份绑定为v045。

此前786份Python源码保持原字节。最终准入绑定950份证据，模型前冻结完整src/scripts/tests与新业务assets。没有重跑旧112请求、旧模型槽或恢复训练。

## 2. 首次失败与必要修复均保留

首次CPU组为56通过、1失败、1 deselected；真实SDK出生单独使用原resident Python运行，1通过，没有skip。失败来自一个成果往返测试的两次read_file遗漏start_line/max_lines；修复仅补参数并按既有逐行读取语义处理尾换行。只重跑失败测试一次，1通过（pytest0.80秒、宿主墙钟1.206841秒），未改运行器、任务或模型输入。

HA/HB在模型前补齐已声明的私验边界：HA12→15条、HB11→15条；LA12/LB10条保持。旧private表是新表逐项不变的前缀，public、初态、合同、参考实现、负控和任务源码保持。首次表与manifest按原SHA精确保全；归档记录披露了先写扩展、后按原生成内容恢复旧快照的时序，不冒称事前归档。

原4root业务控制已验证参考解、初态公开失败与7个负控；该组件26个sandbox driver（15公开/11私有）及8个初诊断。扩展后只对HA/HB原参考解各运行一次新private driver，共2进程/30观察全部符合，公开/负控不重复；7负控依据原失败用例前缀保留继续成立。新增私验墙钟0.153859秒，sandbox相加0.229716秒；子时间不再加到外层检查墙钟。

首次新材料路线已完成36个实际CPU程序请求（每条件单元3步）：初态读文件、run_tests、后继读文件。所有selected均硬容量fit，但第三步后读取检查文件误传字符串给要求Path的read_json，12条记录因此为failed。这是宿主检查错误，原failed原样保留。

只修宿主Path包装。原36请求通过原experience、输出、费用和selected输入只读核对，首页确已进入第三步；没有重分词或重放。原路线已经关闭，8个未测伙伴初态用独立fresh world/runtime各补1请求，不恢复原runtime，不称12条完整连续四步路线均被执行。

最后新增7项宿主准入控制通过（pytest0.05秒），最终全局Ruff通过。65项不同控制=56原通过+1夹具修复+1真实SDK出生+7宿主准入。开发阶段另曾运行同一测量文件的21项控制（会话回执0.24秒）；它们已包含在65项内，不重复当独立证据。

## 3. 新材料容量与程序费用

| 条件单元 | 原连续请求 | 最小selected硬余量 | protected1024不足次数 |
|---|---:|---:|---:|
| LA-S1 | 3 | 1614 | 0 |
| LA-F2 | 3 | 1239 | 0 |
| LA-O3 | 3 | 1246 | 0 |
| HA-O3 | 3 | 46 | 1 |
| HA-S1 | 3 | 400 | 0 |
| HA-F2 | 3 | 22 | 1 |
| LB-O3 | 3 | 1210 | 0 |
| LB-F2 | 3 | 1181 | 0 |
| LB-S1 | 3 | 1562 | 0 |
| HB-S1 | 3 | 944 | 0 |
| HB-F2 | 3 | 584 | 1 |
| HB-O3 | 3 | 586 | 0 |

新增8个独立伙伴初态的最小selected余量3889 token、protected工程余量全部为正。合44请求最小硬余量22，工程余量不足3处均保留为诊断。有限初态/合法反馈可容纳不保证任意探索、全部未来反馈或其它长度状态都可继续；正式运行仍保留真实局部context中断。

| CPU程序材料 | 请求/程序响应 | 实tokenizer调用 | 原生render调用 | 程序记账token |
|---|---:|---:|---:|---:|
| 原12单元的连续三步 | 36 | 89 | 84 | 412335 |
| 未测伙伴独立初态 | 8 | 20 | 16 | 77233 |
| 合计 | 44 | 109 | 100 | 489568 |

程序原生输出是预先指定的CPU夹具，不是模型采样，489568不是正式9B花费。原36含12次公开run_tests；新增8含0次run_tests、8个初诊断driver及4次初诊断缓存复用。其它初始化/生命周期测试的准备成本各保留在原receipt，业务组件的26+8不能冒称所有CPU操作总数。

原native路线耗时30.616861秒；补核与补形native阶段16.0034秒、进程墙钟17.9058秒，其中旧36只读核对0.617883秒。原CPU组/Ruff/native SDK命令墙钟分别为3.162054/0.058881/8.746105秒。子时间、并行sandbox时间与外层墙钟不直接相加。

## 4. 准入与启动边界

最终准入显式保存初次两份false，只接受四项业务/夹具路径变化、Path修复、driver准入薄接入及声明的新宿主控制文件。未变CPU与SDK证据复用；新私验、原36只读证明、8个补形、当前源码与最终检查完整绑定。

下一阶段仅[协议](software-organization-v045-protocol.md)中的24槽：四root×两seed×S1/F2/O3，总上限12000000实际token，不转旧余额。仅GPU3/4/5/7、最多3驻留、原资源门保持。训练、Contribution、独立确认资格均false，额外C/A四探针未启用。

| 证据 | SHA-256 |
|---|---|
| admission | `fa1ddf1c8a73ac336b57e624f61376df9012cc50f309967258cf754bc0f03155` |
| original_failed_qualification | `fdf2561bbe7394af5ddae189e79dffdb3cbcfbfc7ff2a9196ab25a25157ec3b5` |
| original_failed_native_material_check | `0a46e7121831a8763eb763f44d47473475607a5acbf9c665bb206c66d926cf78` |
| repaired_native_materials | `def73a55d597c3c6289d332a95ee8e1d2f1166951c3eb0af088131afbc8dcb69` |
| fixture_repair | `e9148cc386aa64ed8f1c80aeca11008dd97096488cf20737e8285dc6e47c35bb` |
| private_extension_check | `03047fa7c1bc8b79fe3f3aa462260c005a2203a5e722e4e3de42f2b183e5fd42` |
| final_host_checks | `fcff50c415c1c81f447987c6ba350749bda1e3090d3944c637c8ccbb84fa17c5` |
| private_extension_history | `594b6dba85d66b588430e4e01b81513e25383137e3a5ff76e57b63f65a17195f` |
| business_controls | `4ece7010d56b8885a46f258f74f1a71f6e78f5a19949ac3ed8a0ffdb28873605` |

[机器准备记录](software-organization-v045-preparation.json) · [协议](software-organization-v045-protocol.md) · [审计](../reference/audit-v044-complete-next-v045.md)
