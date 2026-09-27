# v0.21 E 线：冻结参数工作记录专项复核

六个预定开发案例全部结束，原评分依次为 **1、0.4、0、0.25、0.2、0**；均为独立可评的已知结果，1 例完成其全部职责。实现、独立复核、联合 A/B 的断点不同，不能只用一个均分描述本轮工作能力。没有追加样本、替换案例、修改原分数或进行参数更新。

本专项只读核对已关闭 episode 的实际模型动作、版本、准备记录、已有评分和 Mapper；**没有重新调用评分器、执行 SQL、运行程序见证或重跑模型**。全轮机器记录见 [domain-v021.json](domain-v021.json)，D 线 CPU 控制另见 [retail-collaboration-v021.md](retail-collaboration-v021.md)，两类证据不混计。

## 1. 固定执行条件与真实调用

执行来源为 `7d71b1ff33e54e37590b09c96151bc667f840401`。同一个 Qwen3.5-9B resident 模型依次承担各角色，各角色保留自己的历史；本地物理 GPU 4，BF16 冻结 backbone、实际 FP32 LM head、FP32 LoRA，`highest` matmul，原生工具协议、non-thinking 请求。精确运行配置在 `runs/domain-v021-ne/E/resident/owner.json`，不是依据模型名称推测。

上下文上限固定 **16,384 token**，单次输出上限 **2,048 token**，temperature 0.7；六例决策上限沿冻结目录。固定预算的触发后果原样保留，没有因低分重采。59 条实际记录的请求及 token trace 温度均为 0.7；HF generation options 的 temperature=1.0 是中性设置，唯一温度缩放由原 `SamplingTrace` 经 FP32 processor 执行，并非又用 1.0 采样或重复缩放。

| slot | 任务 | resident 请求尝试 | 实际生成 | 本地上下文 400 | 实际 world 工具调用 | 输出达到上限的生成 |
|---|---|---:|---:|---:|---:|---:|
| 0 | f0 实现 | 10 | 9 | 1 | 9 | 0 |
| 1 | f1 实现 | 10 | 9 | 1 | 8 | 1 |
| 2 | f0 正确初稿复核 | 6 | 6 | 0 | 4 | 2 |
| 3 | f0 错计数初稿复核 | 8 | 7 | 1 | 6 | 1 |
| 4 | 联合 A | 14 | 13 | 1 | 12 | 0 |
| 5 | 联合 B | 17 | 15 | 2 | 14 | 1 |
| 合计 | 6 例 | **65** | **59** | **6** | **53** | **5** |

这里的 400 是同步 resident 适配器返回的 `context_length_exceeded` 协议状态，发生在真实模型生成前，**不是远程 HTTP 服务故障**。59 条实际生成有原始 output IDs、概率及响应记录；6 次本地上下文拒绝不能计作生成。5 条达到输出上限的生成保留原文并消耗决策机会，未执行其拟议动作。53 次 world 调用中 4 次被真实工具拒绝，分别为 A 的无效 alias 和 B 的权限／route／输出 alias 约束。

实际生成的累计输入 549,217 token、输出 23,031 token；累计输入包含每次实际请求重复携带的历史，不是独立材料大小。E 进程占用的计费设备时段为 **1,174.1141 秒**（约 19.57 分钟），exit code 0；该时段包括加载及执行开销，未冒充纯生成耗时。上述数值来自原 resident 记录与监督记录，没有发出新的模型请求。

## 2. 六例的实际工作与停止位置

| slot | 原分数 | 已发生的工作 | 尚未成立的责任与终止 |
|---|---:|---|---|
| 0 | 1 | 模型读 data/basis，编辑 code v2，真实构建 result v2，再固定提交 code/result v2 | 实现职责完成后，后续请求遇到本地上下文上限；这不抹去此前成果 |
| 1 | 0.4 | 先执行原 SQL；随后改为 distinct 发票计数，重新构建正确 result v3 | 没有任何固定提交；之后一次输出截断，再到上下文上限 |
| 2 | 0 | 读正确初稿的 result v2、data v1、audit v1、code v2 | 未 inspect 固定提交、未批准或提出问题；连续两次输出截断触发格式终止 |
| 3 | 0.25 | 检查固定提交并读足 code/result/data/audit；正确指出 `COUNT(DISTINCT InvoiceNo)+1` 缺陷，实际提出 issue | issue 选择代码位置，且引用中缺 data；未满足冻结评分器的完整定位／证据条件；随后上下文上限 |
| 4 | 0.2 | provider 本轮实际读私有 basis 并合法送达；implementer 读入、准确采用、build 并固定提交 | 没有编辑初始 SQL，执行结果业务错误；只完成交接分项，之后上下文上限 |
| 5 | 0 | 实现者检查旧固定提交、发现金额 `+1` 并撤回；两角色继续读取及尝试核验 | 没有编辑代码、新 build、新固定提交或最终复核；两角色分别遇到上下文上限 |

### slot 0：分数对应本轮真实实现，泛化范围仍有限

episode 开始时没有提交。准备阶段只有六次实际交接／读取／采用操作，不含代码构建。当前模型在原经验序列 44 写 code v2，68 真实 build result v2，80 固定提交。结果为客户 12352 的 98,465 pence／2 张发票、客户 12395 的 49,040 pence／2 张发票；已有独立评价认定该固定输入的产品正确。

实际 SQL 没有显式日期过滤、零活动客户补齐，也没有动态查询 `basis_meta`。它在当前 f0 固定材料上满足结果合同，**不能扩大为任意日期、客户或政策变化下的通用正确程序**。版本谱系说明构建使用了准确声明的 data/basis，不说明模型内部如何推理，也不构成信息因果贡献测量。

### slot 1：真实修正了计数，仍缺交付

初次 build 的客户计数为 15／18；模型把 `COUNT(*)` 改为 `COUNT(DISTINCT InvoiceNo)` 后，新的 result v3 为 3／3，独立构建分项成立。关闭时 `submissions=[]`，因此 0.6 的固定交付项不成立。输出截断及后续上下文拒绝被保留，但没有将已知 0.4 清成 null，也没有把正确草稿称为完整交付。

### slot 2：没有作出判断，不等于作出了错误判断

正确 code/result 是 host 在准备阶段真实构建并固定的。评分记录明确 `current_actor_build=False`；模型读取了材料，但没有 inspect_submission，也没有 approve/raise_issue。原 0 分表示复核职责未完成，不能解释为它把正确工作判断成错误，更不能把继承的正确成果计作本轮模型能力。

## 3. slot 3：正确业务诊断与评分合同缺口分开

实际 issue 指出计数多加 1，并举出客户 12352 有两张合格发票、结果却为 3。该诊断与实际提交代码相符；world 接受了 issue 操作。模型选择的目标是 **code v2**，locator 为 `['models',0,'sql']`，evidence 列表只有 code 和 audit，没有 data 版本。

已有冻结评分器仅接受指向 result 固定版本的 `['tables','metrics','rows',i]` 或额外列索引路径，并要求 data 和 audit 两个准确引用。因此原评分为读证据 0.25、正式复核判断 0；本轮不回改。

本专项进一步读取了这次真实消费请求（`model-b5623879956658334ce1b1c5`，world 动作 sequence 78），而不只检查 host 模板。其 `model_attempt.request.messages[13]` 的当前观察，以及 `messages[2]` 的早先 inspect 返回，确实包含公共要求 **“real wrong row/cell with exact data/audit evidence”**；role task 和 review_contract 也明示 data/audit evidence。模型遗漏 data 引用有公开语义依据。

但公共工具说明只要求准确的已提交 object/version 与非空 locator，公开合同没有明确说明 **result-only**，也没有列出评分器唯一接受的结果行路径。因此存在公开测量合同表达不足，不能把 0.25 简化为“模型不会识别计数错误”或全归于模型复核能力不足。应同时保留正确诊断、漏数据引用和定位合同缺口三项事实。

证据均在 `slot-3/episode/experience.json`、`assessment.json` 与固定代码版本中；核对过程没有重新评分。

## 4. A/B 的真实协作断点

**联合 A 的交接不是准备功劳。**本例 preparation experience 为空；provider 先读适用 basis v1，再在 sequence 30 合法 handoff。实现者随后实际读取该版本和数据并采用它们。这比“只有消息出现”更进一步。

但实现者没有 write_object，固定提交的仍是初始 code v1，SQL 使用 `COUNT(*)` 且未实施政策过滤；result v2 为客户 12471 的 76,945 pence／10、12481 的 38,340 pence／21，业务正确性分项不成立。A 的 0.2 仅代表已验证交接，不能称完整信息使用成功。它先尝试读取不存在的 `online_scope` alias 被拒绝，随后继续合法动作；这次工具拒绝没有被误写为服务故障。

**联合 B 的错误固定初稿来自真实、排除计功的准备。**本轮实现者真实 inspect 原提交、读取 code/result/data/basis，随后 withdraw 原提交（sequence 145）。撤回理由识别了金额 `+1`，同时包含对 invoice_mode 的额外判断；后者不能仅凭该文本当作正确诊断。撤回之后仅又读取 code v1，没有写入修复代码或执行新构建。

复核者读到了 result/data/audit，也 inspect 了原提交；它额外尝试读取未授权 basis、向自己并非收件人的 route 发请求，均被真实拒绝。实现者尝试 sql_query 写入未声明的 `temp_data`，也被拒绝。全例无 raise_issue、respond_issue、decide_issue 或 approve，没有实际反馈—修复闭环。两角色的上下文停止都被记录，未取消或伪造另一角色的后续行动。

B 的 Mapper 返回 `class_id=null, eligible=false`。其中 `features.repair_path` 字符串是评分器检查的自检分支名，**不表示新修复或独立最终复核已经发生**；不能用该字符串宣称发现了一种已成功联合方法。

## 5. 固定参数与证据保全

六例的 actor identity 均与初始一致；原报告的初末 actor identity 比较、source 一致性均通过。每例记录的 actor/critic/optimizer 状态未变化，RNG 按既定评价流程恢复；最终 actor、critic、optimizer steps 均为 0。模型概率的学习资格、反向容量和更新收益不由 E 判定，旧 P1 停止结果没有被补跑或重写。

所有六例均保留，未开始数为 0，评分 unknown 数为 0。只有 slot 0 的完整职责 Mapper 可用，标签为 `independent_implement`；其他案例的 class_id 均为 null。六个不同情境的各一次运行不是同一 xi 的重复支持，不支持 ID-VTDO 类别密度或因果贡献结论。

主要原始证据：

- [E 原始终态报告](../../runs/domain-v021-ne/E/report.json)，SHA-256 `b602e07c674f1fcbd390b29379103ffda03644d400b6913fb87df49cc3e86799`。
- [逐例进度及守卫](../../runs/domain-v021-ne/E/progress.json)，SHA-256 `dc618c4023ec99dfbf263ae0355061c0a8c12b07fce2f700ef5a5e571b794eb7`。
- [实际 owner/config 身份](../../runs/domain-v021-ne/E/resident/owner.json)，SHA-256 `02927f762403997e4dece7feefca1ec17a86b3fd9803a6c1dd6c7261eae858cc`。
- `runs/domain-v021-ne/E/slot-0` 至 `slot-5` 的 `preparation.json`、`episode/manifest.json`、`episode/experience.json`、固定版本及 `assessment.json`；逐项路径和 SHA 亦见全轮机器归档。

下一轮可先明确公开复核定位与证据合同，再检查观察呈现、历史增长和输出预算，另行冻结新的 Γ 后评价。改变这些条件会改变测量环境，不能在本轮原记录上追改或将补跑并入本轮。当前结果支持“已取得有限实际实现、诊断与交接行为，并定位了交付、政策落实和修复闭环的断点”；它不证明普遍协作成功或学习收益。
