# v050 学习桥、支持与权重 CPU 控制

日期：2026-10-13。机器回执：[software-learning-v050-learning-controls.json](software-learning-v050-learning-controls.json)。

本部分只验证 v050 必要变化：24 个新联合 episode、每 root 12 次、48 条成员轨迹的固定基础质量，以及昂贵更新前的可靠类别供给门。没有加载模型或张量 checkpoint，没有调用 GPU、tokenizer、optimizer 或 backward；没有生成 `.pt`，也没有重复旧实验与旧测试套件。

## 冻结适配

- S* 直接引用既有 v049 B4/4，包含 actor、critic、两个 Adam 与 RNG；`bind_s_star_checkpoint` 不另写 checkpoint。每个 B/Q 分支必须独立从 4/4 起步，不接受 3/3 或已经更新到 5/5 的 owner。
- 新窗口 ID 为 `v050-o1-learning-window-01`；唯一新清单为 LA/LB 各 r01—r12，seed 202610130501—524。声明、支持与组成物化绑定同一顺序，不将旧八条材料并入。
- 原 H=1 的 `SharedActor.update_window` 和 `prepare_window` 保持相同 code object，只在私有 globals 绑定 v050 reader/组成验证及可选只读观察器。原动态 `len(entries) * len(members)` 在本轮严格成为 48；actor 分母为 48T，critic 为 48K。不同成员输出长度和决定数分别测试，避免误用所有目标 token 统一分母。
- Mapper 两类、每类至少两例、ratio [0.5,2]、TV≤0.2、唯一方向顺序与 epsilon 规则均不变。v050 reader 只将原同源拒绝证明的 runtime 身份精确改为 v0.50，不放宽旧证明的其他条件。
- 完成 record/Mapper 与 CPU admission 后先 `pretraining_support_gate`。没有可靠多类块就收口，本轮不执行 B 或开发；缺失/未闭合库存不能冒称完整24槽后的供给不足。支持存在时才可执行 B，仍须实际 native 概率/反向资格通过后按原算法选择第一个非零混合方向。
- 可信 R0、unmapped 和未过可靠类别门的残余仍保留单位基础权重；缺失质量不转给其他条目。可选 Q 只改变 actor 经验组成，critic 始终用原目标和固定分母。

## 控制结果与边界

20 个不同 pytest 案例全部通过，累计执行 21 次：初版18项通过；加入“准入成员不得只删一条决定、分母必须精确等于48T/48K”接缝检查后，两项新增反例通过，并针对变化路径补跑一个合法完整成员正例。没有 pytest 失败。

首次 Ruff 出现6条 F401：相关导入仅经 `globals()` 私有命名空间消费，静态工具未识别。改为显式依赖字典后最终 Ruff 通过。原检查结果没有隐去。

控制使用明确标识的 CPU 合成元数据与同源拒绝 fixture，只证明这些合同和绑定实现的行为。它们不证明本轮新模型采集会出现多类支持，不证明 B/Q 的实际数值更新或学习收益。真实采集、实际模型概率复核、反向、完整状态与开发效用必须另行记录。原 v049 数值配方和 Mapper 源文件的 SHA 在机器回执中列出，旧记录未改写。
