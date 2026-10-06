# v0.35 新来源支持窗口启动记录

**固定16槽P2监督队列已启动。** 北京时间 **2026-10-06 17:11:53** 启动；本快照9B为`not_started`，等待满足原稳定空闲门的GPU，新增9B调用与已分配worker成本均为0。监督／自动发布进程已验证存活、身份匹配、状态新鲜。动态结果见[运行报告](software-support-v035.md)及[机器汇总](software-support-v035.json)，本启动快照不回改。

执行提交：`ccf756459d09e769235b25300477f5f98172be56`，已推送`haoyueliuzhao/ProWorkSim`。本记录[机器数据](software-support-v035-launch.json)绑定计划、资格、PID和快照；详细修订与边界见[协议](software-support-v035-protocol.md)、[准备证据](software-support-v035-preparation.md)及[一次P1方法复核](software-method-review-v035.md)。

## 1. 已冻结内容

| 阶段 | 冻结材料 | 数量／当前状态 |
|---|---|---|
| P2正式训练用途采集 | 新sqlparse `sp-script-inventory-v035`，9B完整原3／3 common，member_a先手，同一ξ／Γ | 16槽，已交监督队列；零更新 |
| 贡献开发 | 新schema job-policy、command-set两root，各seed `202610060901`／`202610060902` | 每候选4条；P2不执行 |
| 独立确认 | 新TextFSM port-status、batch-totals两root，各seed `202610061001`／`202610061002` | 每方法4条；P2不执行 |

支持seed固定`202610060801`至`202610060816`。单owner保持一个真实参数窗口，不将两个较小窗口后验合池；CPU准备并行完成，后继独立候选的并行度另在采后清单中确定。没有S条件、模型替换、当前开发题重采或成功池改标。

每episode两成员共享128决定、128实际attempt上限、500000实际token、32次run_tests；16K上下文、2048单次输出及原采样／数值profile不变。已有3／3更新的common不是fresh base，P2期间不执行参数更新。

## 2. 资格与必要核验

新源世界8项控制涵盖五root×四程序变体，以及一条真实SDK合法来源路线；Mapper21项控制及一次191原调用只读复核；learner一次tiny CPU实际采样／概率／完整反传；runner的三用途collector导出与报告准入控制；分配桥5项不同增量控制及一个独立freezer编排fixture均通过。最终全项目Ruff通过，未重复全仓pytest或旧数值求解器控制。

这些检查分阶段完成，不能相加冒称一次同源整套pytest。tiny CPU的32次生成与actor／critic各1步单列，不是9B调用或训练收益；该较早控制未采CUDA初始化／资源遥测，null事实保留，不伪写实测零GPU。

同一新训练来源的9个脚本请求以原9B tokenizer作一次CPU条件成本核对，峰值输入10282，最小上下文余量4054，完整输出预留后的路线总量91222／500000；没有加载模型权重或重做近16K资格。程序见证不进入训练材料。

干净工作树资格SHA256：`14a7eab032bc041c36eae4ac77b02d3d796f39941a20c52e65ec7710cc1dca55`。计划SHA256：`b950c2e6b33b42446e6b62b7c8e5faba5c27f8d5d6e26970fbfa1eb2e12ff617`。原10份数值文件中9份逐字节保持，唯一差异是online_training中新组成验证分派的4行；完整common、原native与当前呈现证据继承。新源与Mapper、输入／原始目标绑定、完整方向和分母检查分别保留。

## 3. 实际部署

| 项目 | 实际绑定 |
|---|---|
| 冻结执行工作树 | `runs/v035-frozen-source` |
| 计划 | `runs/v035-plan.json` |
| 原件目录 | `runs/software-support-v035` |
| finish PID／start ticks | `4064711`／`370230827` |
| supervisor PID／start ticks | `4064777`／`370230878` |
| 日志 | `runs/software-support-v035-finish.log` |
| 实际入口 | `software_support_v035 finish ... --publish` |

只在原空闲显存、利用率及无其他compute进程条件连续稳定60秒后分配单张A100 80GB，GPU优先顺序4、6、5、0、1、2、3、7。不提前预约显存，不停止其他作业；单加载900秒、episode2400秒、边界600秒、RSS64GiB、原件128GiB及卷预留20GiB保护保留，累计GPU／worker／统一墙钟／队列截止继续为空。

本快照所有GPU均不满足准入，未加载9B。排队时间不计GPU占用；后续仅按本P2逐卡worker区间计算，旧P1的1.395206 GPU小时不叠入。结束后仅自动提交并推送两份约定运行报告，完整请求、token、世界事件、版本、固定交付、独立验收、方法与预算原件流式保留。

## 4. 完成窗口后做什么

分别报告M、n、n+、v、b、门前频数、可信基础mask与真实训练序列规模。分类不靠工具次数或后台真值推断已见信息；失败、unmapped、低频和未选成员保持原始分母。无支持、单类、多类频数不足、形式自由度有而梯度尚未验证、技术未知分别处理，不补采凑数。

若有配置自由度，先用`freeze_software_allocation_v035`绑定实际支持、完整common／RNG、类内核、全部方向、步长及唯一试训清单；该脚本不启动训练、不读取独立结果。第一窗h=b、logN和双锚沿用现有v030规则，G-raw不接收专用类别／图。后继最多33次唯一试训、132条贡献开发、3次正式更新和12条独立确认，实际数量由n+／K确定，不能删方向压缩G。

真实共享B试训须完成原始行为概率／目标消费及完整更新，再产生更新后开发工作；正式B／G-raw／I-P各回同一完整起点。P2队列不自动启动未冻结P3，也不把静态支持或CPU数值结果说成分配收益。
