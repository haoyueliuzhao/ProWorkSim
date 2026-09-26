# v0.16 独立 harness 开发情境与有限项目关系

本设计保持 v0.15 的筛选、N0/N1 和 Marshmallow 锁定需求不变。它新增六个 UCI 开发情境，供原生工作人员接口与 SDK harness 使用同一业务起点。奖励、角色权限与 SQL 效果沿用既有有限零售合同；harness 负责的笔记、局部历史、调度和模型事件应在另一层实现。

## 独立素材边界

新资产使用同一份已固定字节的 [UCI Online Retail](https://archive.ics.uci.edu/dataset/352/online+retail)，SHA-256 为 `43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16ae4c3936424676d`。本次再扫描 541,909 行，先排除 v0.15 train/development/locked 的全部 18 客户和 54 发票，再按固定规则选取 12 个新客户、36 张完整发票、164 条原始记录。六片段之间客户与发票也互斥。

这里的“新”指来源内部的实体与开发情境；没有增加独立公开来源，也没有生成新的锁定测试集。公开资料可能已进入模型预训练，这个实体划分没有排除这种可能。

选取规则固定为：单张发票 1–10 行、全部属于同一个非空客户、单价可无损表示为两位小数；客户至少有两张普通多行发票及一张 C 取消发票。客户按 `SHA256(harness-v016:CustomerID)` 排序，取前 12 位，相邻两个一片段；每客户保留字典序最早两张普通发票及最早一张取消发票的**全部原始行**。没有行级切分或重复删除。片段不是客户完整历史，也不是总体的无偏样本。

源文件保存在旧来源资产目录，但新 worker 只得到自己的有界 JSON；原始 XLSX、旧 train/development/locked 文件及 Marshmallow 目录不通过世界工具暴露。固定清单位于 `examples/retail-harness-v16/source-manifest.json`，运行时逐个核对片段 SHA 与排除实体。manifest 或 case 合同变化会拒绝加载。

## 六个业务起点

| case | 职责 | 行数 | 模拟政策 | 准备阶段 |
|---|---|---:|---|---|
| `uci-harness-f0-implement` | 单人实现 | 32 | 全期、仅销售 | 已实际交接、采用数据及依据 |
| `uci-harness-f1-implement` | 单人实现 | 27 | 截至 2011-07-01、带符号净额 | 已实际交接、采用数据及依据 |
| `uci-harness-f2-review` | 单人复核 | 29 | 全期、带符号净额 | 已实际构建并固定正确提交 |
| `uci-harness-f3-review` | 单人复核 | 26 | 全期、仅销售 | 已实际构建并固定错发票数提交 |
| `uci-harness-f4-pair` | 资料提供＋实现 | 27 | 全期、带符号净额 | 无业务动作前缀 |
| `uci-harness-f5-chain` | 提供＋实现＋复核 | 23 | 截至 2011-07-01、仅销售 | 无业务动作前缀 |

所有起始时间为 2010-12-01，日期合同左闭右开；全期截止为 2012-01-01。金额为实际 Quantity × GBP UnitPrice，输出整数便士；发票数按 DISTINCT InvoiceNo，保留全部原行与零客户。政策、人员、交接和错误提交是模拟，原始交易行不是模拟。正确/错误准备标签只属于宿主 case manifest，角色必须从实际资料和固定成果判断。

接口 `proworksim.templates.retail_harness.build_harness_case(case_id, new_root)` 返回现有 `PreparedOnlineCase`。使用独立环境变量 `PROWORKSIM_RETAIL_HARNESS_ASSETS`，默认资产目录 `runs/assets/uci-retail-harness-v016`。项目仍为 `TEAM`、工作为 `TEAM::build`，以便 SDK 与原生接口保持同一业务合同。`assess_retail_reward` 直接复用 v0.15 的 Decimal 与真实证据条件，reward version 不因换 harness 更名或放宽。准备工作发生在当前 episode 之前，不给新 actor 信用。

角色决策预算保持实现 10、复核 9；pair 为 6＋12；chain 为 6＋12＋15。等待和 done 计入有限责任预算。CPU 可行性程序不是模型提示、演示或训练轨迹。

## 单独的四项目关系

`retail_projects.py` 使用 f0 **开发**片段，另外声明 P0 资料、P1 指标、P2 分析、P3 集成世界。它不是六情境中的追加样本，不影响 H1 分母，也不进入旧学习线。

P0 读取并发布实际发票、字段和边界说明。P2 在开始时已经拥有可发布的客户粒度合同；P1 与 P2 都只需 P0 资料和 P2 合同即可开始，彼此不等待对方结果。P1 执行 metrics SQL，P2 独立执行 customer_analysis SQL，P3 对两条真正发布的结果做 FULL OUTER JOIN，比较每个客户的金额和发票数，避免总额相同掩盖局部不一致。

第二版合同由 P2 的显式 write/publish 提出，改为上半年带符号净额。已有内核的 publication/maintenance 只产生发布事实与有限工作义务修订；它不替下游采用、改 SQL、构建或提交。程序见证随后显式读取、采用和执行新结果，保留旧版本。初版成果先作为已发布产物供集成使用，第二版完成后固定提交；本见证不声称覆盖已验收项目的无限维护后继。

P1 复用已注册的零售内容评估；P2/P3 的本轮有界内容检查由独立 CPU 报告执行，还没有注册成新训练奖励。机构提交通过不等于内容正确；报告必须分别给出实际来源、Decimal 对照与集成结果，不能仅报告 accepted。
