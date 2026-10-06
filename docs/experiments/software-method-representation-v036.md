# v0.36：带实际呈现与恢复时序的生产单元关系

本次只修订方法表示及其 CPU 控制，旧 v0.35 的完整评分、Mapper 输出、支持门和停止决定不变。新表示保留两个粗粒度类别：`local_lineage_delivery`、`evidenced_peer_product_delivery`。它们描述受评版本的可核对形成路径，不是“单人／合作”、作者归属、语义等价、因果贡献或学习价值标签。

方法 CPU 控制和影子分析的主回执为 `runs/v036-controls/methods/checks.json`。独立原件在 `world-final/`、`shadow-v035/`、`shadow-v035-local-import-fix/`、`shadow-v035-final/`。本阶段没有目标模型调用、GPU 使用、分词或参数更新；真实 World 控制确实执行了脚本指定的工具、公开测试与独立验收，但这些显式 CPU 程序不是模型经历或正式支持。

## 1. 独立接口与冻结边界

新增文件：

- `src/proworksim/software_method_evidence_v036.py`
- `src/proworksim/software_mapper_v036.py`
- `tests/test_software_mapper_v036.py`
- `scripts/shadow_software_methods_v036.py`

接口保持 `build_software_evidence(slot_dir, rollout=..., assessment=..., expected_window=...)`、`map_software_method(rollout, evidence, spec=...)`、`mapping_spec()`。证据版本为 `software-method-evidence-v0.36`，Mapper 版本为 `software-evidenced-product-route-v0.36`。

冻结 spec 摘要为 `ff574f7be89f4e3bbf859289c72bcd8cb6c86c3c0052ff26380cff6f0b3a668e`。新采集必须在 `rollout.online_scope.method_mapper_spec_sha256` 绑定该值；原用途允许训练且具备这一新采集绑定时，映射才可能具备组成支持资格。旧窗口缺少此绑定，因此即使影子映射成功，`composition_support_eligible` 和每个成员的 `support_eligible` 仍为 false。

只读档案基础复用 v0.35 的实际 selected request／native input IDs／原本人目标、World commit receipt、不可变版本、完整评分和祖先链绑定。旧文件没有修改。v0.36 在这些已核对事实之上独立构造生产关系，不通过后台源码补写模型历史，也不把模型声明当作已执行事实。

两个成员仍投影同一条联合经历的类别。本人原 output IDs、行为概率、labels、loss masks、原始槽和分母保持，不按最终代码作者剔除另一成员。影子标签不能进入新 P3；本说明也不宣称已取得新窗口支持或实际学习后果。

## 2. 两类与拒绝边界

`local_lineage_delivery` 要求完整有效、实际输入和当前固定交付链可信，有保留的本人公开生产改动，且最终链没有伙伴导入，也没有无法解释的伙伴固定源码取得。另一成员可以有实际编辑、测试、任务活动或支线导入；这些行为不会被删除或被解释为“不合作”。

`evidenced_peer_product_delivery` 要求所有相关导入均能解释，至少一条导入有合格消费关系，且不存在未解释的关键依赖。每次导入的状态分别记录为 `consumed`、`discarded`、`nonproductive` 或 `unexplained`。检查不再采用 `all(consumed)`；也没有放宽为不加条件的 `any(import)`。

只存在弃用／非生产性导入、完全覆盖但无法追踪的改写、仅手工读取伙伴代码而无最终链导入、输入或时序不足、未知传递依赖等，保守保持 unmapped。失败／unmapped 的原始基础材料不因此删除。

## 3. 合格生产关系的具体证据

生产单元暂限公开契约中声明的顶层 Python 函数或类。规范 AST 忽略格式、注释、docstring；无关 helper 添加本身不能产生伙伴类别。对每个候选单元，分别保存：

1. incoming 相对伙伴 patch starter 是否有公开定义变化；
2. incoming 相对收件人导入前的同一定义是否有新结构；
3. 导入版本、恢复／修改版本、最终版本的定义摘要与真实动作；
4. 模块和函数内静态 import、helper 闭包及相关生产依赖的解释。

两项变化判断不可合并。伙伴相对 starter 做了实质改动，并不说明收件人此前没有完全相同的单元。后者相同的 no-op 不构成合格消费。

直接合并路线允许工具将单元实际物化后持续保留，不强制再全文读取源码；需要导入时已取得 patch 元数据，且真实导入回执在当前版本测试前进入实际输入。

冲突恢复路线需要先在实际输入取得固定来源元数据、导入回执及相关冲突诊断或 incoming 生产文本，再有同一最终祖先链上的真实同路径修改。恢复出的规范公开单元必须从该恢复节点持续保留到最终版本。其他单元或文件可以重写，因此并不要求整个 incoming 文件从冲突导入节点开始永久不变。

若单元已经被一个可解析的新实现替换，之后再次恢复成 incoming，仅凭最终相似和早期导入记录还不够；规则另要求在那次替换之后出现新的相关源码呈现。先编辑、后见元数据或回执，不能反过来为早先修改建立合格关系。

弃用解释同样有明确限制：要在真实回执之后实际将相关单元重置为收件人导入前或 starter 的定义，并证明其后 incoming 单元没有再次出现。这样可接受“早期弃用＋后期充分消费”的多导入路径。没有这种明确重置的任意改写，不被自动叫作“已解释弃用”。

最终交付仍须绑定同版本测试、实际测试反馈取得、固定 patch 与主动提交，并且最终声明的生产单元可解析、没有生产冲突标记。未知 included patch、取得却没有最终链导入的伙伴固定源码，以及其他无法解释的关键导入，都会阻止伙伴类，即便另一次导入有正向保留。

`direct_merge`、`conflict_resolved`、`partial_rewrite`、`discarded_import`、`nonproductive_import` 和 `source_text_presented` 单独记录为过程属性。源码片段呈现计数会包括同一回执／代码在多个实际输入中的重复出现，不能解释成额外行动数或独立信息样本。

## 4. 依赖解释与明确局限

规范 AST 相同只是结构证据。检查还跟踪模块静态名称、字面常量、被引用 helper 的传递闭包，以及声明生产模块中的被调用公开单元。未知／改变的关键 helper 绑定、动态查找、未解析生产符号会阻断相关见证。跨生产单元的实现变化单独记录已验证版本转换，不宣称其与 incoming 语义相同。

函数内显式 import 使用 Python 词法符号表区分，不能因文件顶部少一个冗余 import 就误判为未绑定。反向控制也覆盖了“嵌套函数里的局部 import 不能掩盖外层函数真实使用的模块全局绑定变化”。

首版仍不追踪任意语义重构或任意函数内部片段组合。完整公开单元被改写成另一规范 AST、无法确定静态依赖、动态别名或无法解释的手工借用，可能保持 unmapped。映射率不是本规则的优化目标；本规则也不是通用因果代码归因器。

## 5. 有限 CPU 控制及实际结果

最终 World 路线使用 v0.36 World、同一训练 root。每条都执行真实工具、三方合并（适用时）、公开测试、固定 patch、主动提交和独立验收。实际输入边界由控制程序明确构造，没有生成模型回复或伪称 native 模型采样。

| CPU 路线 | 原完整R | 映射结果 | 主要核对点 |
|---|---:|---|---|
| local | 1 | local | 本人生产链 |
| off_branch | 1 | local | 另一成员导入不进入受评祖先链 |
| direct | 1 | peer | 实际物化＋回执；没有强制源码重读 |
| conflict | 1 | peer | 先见冲突、后恢复并验证 |
| partial | 1 | peer | 只保留 report.summarize，reader 另行实现 |
| discard_then_consume | 1 | peer | 第一导入明确弃用，第二导入充分消费 |
| overwrite | 1 | unmapped | 正确交付不等于可靠保留伙伴单元 |
| comment | 1 | unmapped | 注释变化不能产生伙伴类别 |
| helper | 1 | unmapped | 无关 helper 不能产生伙伴类别 |
| noop | 1 | unmapped | 收件人此前已具有相同生产单元 |

最终这组 10 条路线合计 132 个真实 World 动作、10 次公开 `run_tests`；每条均有独立验收。它们是控制脚本，不是当前9B的成功率。其他 CPU 反控制从这些实际 World 事实中移除／推迟呈现边界，验证缺元数据、缺回执、未见最终测试反馈、先编辑后见信息，以及“有一次正向消费但较早导入未解释”都保持 unmapped。另验证未知依赖、原有效性 false／unknown、新旧窗口与用途隔离、本人目标不变和证据 seal。

执行记录：

- 初次 25 项通过（15.40秒）；随后增加传递 helper 检查，对受改动影响的方法控制再运行 25 项，通过（15.47秒）。两次 World 执行原件分别保留在 `world-attempt-1/`、`world-final/`，不将二者算成更多独立控制路线。
- 影子诊断定位函数内 import 解析漏项后，只运行三项相关纯 CPU 检查（包括两个新词法作用域反／正例），3项通过、24项未选中（0.09秒），没有再次执行 World。测试文件合计27项；这里不将“25＋3”说成28个不同控制。
- 新增方法、测试、影子脚本的 Ruff 通过。每次实际命令及源码摘要见 `checks.json`；后续根级全仓检查另由根回执记录。

## 6. 原16槽的影子结果与一次解析修复

首次只读影子诊断为 10 local、4 peer、2 unmapped。槽9被静态绑定器拒绝后，读取其原 incoming 和最终 `report.py` 发现：incoming 的 `summarize` 内已有显式 `from reader import statement_records`，最终文件还增加了一个冗余模块级 import。旧的模块级扫描将合法函数内 import 误报为未绑定，而不是原程序确实缺少依赖。这是表示实现错误，不能当作轨迹的缺证据结论。

修复使用通用词法作用域规则，没有修改 spec、任务、原程序、评分或类别目标。首次影子报告及其七份确切源码快照保留在 `shadow-v035/initial-source/`。只重建受影响槽9；其余15槽复用已绑定输入／版本证据，并对先前接纳的7个生产单元执行新依赖检查。一个汇总阶段 `read_json(str)` 错误发生在槽9完整证据已产出之后；修为 Path 后复用那份证据，没有再次扫描槽9的原模型输入。中间文件与恢复依据也保留，未覆盖首次诊断。

最终影子结果：

| 原槽 | v0.36影子结果 | 可核对关系 |
|---|---|---|
| 0—8、14 | local，共10条 | 原受评树无伙伴导入；旁支活动仍保留 |
| 9、12 | peer，共2条 | 冲突恢复后保留 report.summarize，生产文件仍有部分重写 |
| 10、11、13 | peer，共3条 | 冲突恢复后两公开生产单元保留 |
| 15 | unmapped，共1条 | 原未提交／完整有效性不成立，不改变原R |

最终机器报告为 `runs/v036-controls/methods/shadow-v035-final/report.json`。原完整成功仍为15/16。五条旧成功 unmapped 在最终影子规则下均获得伙伴标签，是具体证据检查的结果；不能据此预承诺新窗口10:5、推断新类有效产出率，或补记旧支持。所有影子支持资格为false，`new_support_contribution=0`。

## 7. 可复现命令

新控制通常由根最终检查统一执行；单独执行时必须使用新的控制输出目录，避免覆盖原实验见证：

```bash
PROWORKSIM_V036_METHOD_CONTROL_RUN=/tmp/v036-method-control-new \
  .venv/bin/python -m pytest -q tests/test_software_mapper_v036.py
.venv/bin/python -m ruff check src/proworksim/software_mapper_v036.py \
  src/proworksim/software_method_evidence_v036.py \
  tests/test_software_mapper_v036.py scripts/shadow_software_methods_v036.py
.venv/bin/python -m scripts.shadow_software_methods_v036 \
  --output /tmp/v036-old-window-shadow-new --workers 4
```

完整影子入口始终只读原16槽且拒绝覆盖输出。增量入口 `--baseline-report ... --rebuild-slots 9` 只用于同一 spec 的词法依赖检查变动，明确记录复用范围；恢复已完成单槽要求其方法源字节和证据摘要仍一致。以上入口均不会运行新采集、训练或P3。新窗口及其条件后继由独立冻结协议和监督器负责。
