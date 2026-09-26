# v0.15：UCI Online Retail 有限工作责任

这一模板把真实交易记录接入现有 `WorldCore`，保留实际读取、引用、采用、SQL 执行、固定提交与独立复核。真实数据来源与模拟组织流程分别记录；它不把既有六行构造世界更名为真实公司。

## 来源与加工

来源为 [UCI Online Retail 官方页](https://archive.ics.uci.edu/dataset/352/online+retail)，[原始下载包](https://archive.ics.uci.edu/static/public/352/online+retail.zip)。官方以 CC BY 4.0 提供，归属：Chen, D. (2015). *Online Retail* [Dataset]. UCI Machine Learning Repository. [DOI:10.24432/C5BW33](https://doi.org/10.24432/C5BW33)，[许可](https://creativecommons.org/licenses/by/4.0/)。本项目进行了字段类型表示转换和完整发票筛选，并新增了模拟工作合同；不暗示原作者认可这些模拟合同。

原始 ZIP 和 XLSX 保存在 ignored `runs/assets/uci-online-retail-v015/`。官方未给不可变发布修订号，因此以 SHA-256 固定实际字节；下载时间、文件大小、来源、许可、加工与每个片段哈希在 `docs/experiments/retail-v015-source-manifest.json`。模板源码另固定 XLSX 与九个片段的哈希，运行时不能靠修改 ignored manifest 替换素材。

原字段 `InvoiceNo/StockCode/Description/Quantity/InvoiceDate/UnitPrice/CustomerID/Country` 保留。增加 `SourceRow` 表示原 XLSX 行号。发票号 C/c 前缀指取消，`UnitPrice` 是英镑单价，金额是 `Quantity × UnitPrice`；没有 `completed/pending`、金额倍数或旧构造 `order_id`。原日期作为无时区本地时间；不编造时区。原 XLSX 不修改。

用途划分按 `SHA256(CustomerID) mod 3`，分别指定 train/development/locked。各桶选择符合约束的前六个客户，两个客户一片段；每客户选两个 2–10 行普通发票与一个 1–10 行取消发票，保留这些发票的全部原始行。选中发票只有一个非空客户且单价最多两位小数，故 `DECIMAL(18,2)` 无损。其他客户历史不进入指标，不被放入另一用途。这个有意有界的子集不是源分布的随机代表，也没有涵盖源数据全部异常。

这是一种客户实体隔离的**同来源内部用途划分**。同片段的实现、复核、双人协作、整链派生任务始终留在相同用途。locked 不等于未见数据家族；不能据此声称独立来源泛化或预训练污染为零。

## 公开合同与可见性

每个工作仍使用项目 `TEAM`、工作 `TEAM::build`，角色为 provider/implementer/reviewer。`data` 是实际 26–36 行完整发票明细及两个客户清单，正文 7,860–10,187 bytes。模型可通过 `read_alias` 取得全表、字段定义和来源；不会用预览替换不可检索的正文。实际 `sql_query` 可以对公开可读/所采用输入运行受限 SELECT/CTE；`sql_build` 执行模型写入的实际程序。底层既有 DuckDB 隔离、函数限制及资源边界保持有效。

独立 `basis` 包含公开模拟合同：半开日期区间、`sales_only` 或 `net_signed`、GBP、保留所有原行、排除缺客户与非正单价。`sales_only` 还排除 C 发票和非正数量；`net_signed` 保留签名数量及取消。汇总保留客户清单的零行，金额输出整数 `revenue_pence`，发票数按 DISTINCT InvoiceNo，不能把行数当发票数。f2 截至 2011-07-01，其余截至 2012-01-01。合同没有给数值答案或可执行 SQL。

输出恰为 `metrics(CustomerID,revenue_pence,invoice_count)`。数据源与合同都要真实采用，SQL 结果的执行来源、代码版本、提交快照和源依赖进入评价。可编辑测试仅提供反馈；独立 evaluator 用 Python Decimal 从固定数据和已采用合同计算，不运行模型 SQL 当真值，也不作为 actor 工具开放。

## 四种责任

| 责任 | 初始状态与当前 actor 必须完成的事 | 活跃角色/机会预算 |
|---|---|---|
| implement | 依据已通过真实路由送达、data/basis 已合法采用。模型本轮仍须读取实际输入、修改 SQL、执行并提交成果。 | implementer 10 |
| review | 原环境已经实际构建并固定提交正确或错误代码/结果。模型读取其精确版本、数据及独立依据，作出有据批准或位于真实错误行/格的阻断问题。 | reviewer 9 |
| pair | 依据只在 provider 可见；双方自主请求/提供、读取、采用、实现和固定交付。无后台补采用、改代码或替模型提交。 | provider 6、implementer 12 |
| chain | 同一工作还要由 reviewer 独立复核实际交付。 | provider 6、implementer 12、reviewer 15 |

每个用途三片段，合计 36 个情境。review f0 是正确提交；f1 是发票数错误；f2 是最终金额错误（含零客户行），位置不在模型提示中揭示。标签留在 host registry，不作为正确性证据。review 原始代码本身是合法工作对象；没有为实现者预先写好本轮答案。

准备动作、原始固定提交和真实历史回执全部保存在 `preparation.json`，在 episode 开始前完成，明确不给当前 actor 信用。所有 active role 仍共用选定策略，轮转、世界钟和角色独立预算沿用实际 collector；规则可行性脚本与模型采样严格区分。

## 奖励与支持边界

`retail-work-reward-v0.15` 使用同一个终局合同：实现为读输入0.2/正确实际构建0.3/正确固定提交0.5；复核为完整独立读取0.25/正确有据判断0.75；双人为真实送达0.2/正确构建0.3/读取后正确固定提交0.5；整链为送达0.2/正确固定提交0.3/有据独立接受0.5。

送达只有在实际路由事件 applied 后提前结算；其余依赖终局的内容结果在终点结算。终点补差保持相同终局回报，可为负。MC/RTG 只改变时间信用，没有工具次数奖。回执与模型实际输入绑定继续核验；模型没有真正获得的证据不当作已读。服务/评价不可测留 unknown，业务失败可评为零。

`work_components.basis/delivery` 是独立工作谓词，不直接由 scalar reward 推导。pair 不冒称三人整链完成；当前方法支持仍只能按确切情境、同 θ 和当前窗口内实际频数计算。原生双成员协作存在，不代表已经形成多个方法类别；未达支持不启动 ID-VTDO。

## 接口与复现

```bash
curl -L --fail -o runs/assets/uci-online-retail-v015/online-retail.zip \
  https://archive.ics.uci.edu/static/public/352/online+retail.zip
.venv/bin/python scripts/import_retail_v015.py --root runs/assets/uci-online-retail-v015
.venv/bin/python -m scripts.retail_work_experiment_v015 --output runs/retail-v015-cpu-new
```

Python：`templates.retail_work.registry()/case_spec(id)/build_retail_case(case, root, assets_root=...)` 返回 `PreparedOnlineCase`；评价：`retail_rewards.assess_retail_reward(episode, spec)`。冻结 checkout 应设置 `PROWORKSIM_RETAIL_ASSETS` 指向已导入固定资产的绝对路径，不能假定 ignored 文件随 Git checkout 搬运。

首版完成这些短责任；P0→P1/P2→P3 四项目之间客户、期间与粒度的真实交叉反馈**尚未实现**。当前 chain 是单项目多成员链，不把同表读取包装为跨项目并行。来源接入、可执行性、模型表现和在线学习收益必须分别报告。
