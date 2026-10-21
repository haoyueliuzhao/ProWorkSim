# v054 r3：保留合法Git祖先与官方运行时版本

r2虽然保持了500题的tracked tree，却通过新建单根commit删除了合法祖先及tag。随后真实公开入口观察发现运行时语义变化：若干Django开发版从Git读取新根的2000年时间，Matplotlib版本计算退回`0.post1`或`0.1.0.dev1`。这不是可以忽略的日志差异，因此r2索引仅保留为准备历史，不作为正式三组实验的最终共同环境。

本修订不修改源码版本字符串、不伪造tag，也不将仓库重置回dataset base。它只重建受影响的Git层，复用r2已核对的公开工作树、构建依赖及目标包副本隔离结果；原官方评分镜像始终不变。

## 允许的Git对象范围

策略为`config/v054-actor-ancestry-r3.json`，执行程序为`tools/verified_actor_ancestry_v054.py`。首次冻结的策略SHA为`a67d9030ecfc6a698d83f490606cb7e9823432a5cd330fa08e8829c5d607c3aa`，覆盖配置及实际donor/restore程序。

对父仓库，以已经核实的官方setup HEAD为允许端点，保留其完整祖先闭包。HEAD为dataset base的直接官方setup子提交这一关系已经由r2逐题确认。只保留原HEAD所在分支；tag必须解引用到dataset base的祖先commit。其他分支、远端、坏origin/HEAD指针、旧reflog、hooks和不相关对象不复制。

对子模块，允许端点为父树中的原始gitlink commit，保留它的完整祖先闭包及解引用到其祖先的合法tag。不会再用shallow截断破坏子模块的Git版本计算；父树160000条目和gitlink OID保持原值。

官方镜像只负责提供显式允许heads/tag对象的pack；Actor目标以r2环境为基础，删除其现有Git控制库，将该闭包导入新库，再repack/prune。实际核对包括：

- HEAD及tree等于原始官方端点。
- refs精确等于允许的HEAD分支和tag集合，所有refs均在HEAD祖先范围内。
- 可达commit数量与官方允许闭包一致，整个新对象库中的commit总数也一致。
- 完整Git fsck成功，没有不可达对象，工作树干净。
- 实际公开Python导入的目标模块版本与原官方镜像逐题相同。

这里按祖先关系决定允许范围，不把提交时间简单当成代码可见性的替代；merge带来的合法祖先仍保留。每题拒绝的tag及保留的tag均进入回执。

## 先完成的实际代表对照

正式扩到500之前，固定检验了已观察版本漂移的Django和两类Matplotlib代表。三个对照均在无网络CPU容器中进行，只导入公开模块、读取Git身份，没有运行任务suite或模型。

| 任务 | 原官方镜像版本 | r3 Actor版本 | 原/Actor git describe |
| --- | --- | --- | --- |
| django__django-10097 | `2.2.dev20260813003907` | 完全相同 | `1.7a2-8776-ga51eeca211` |
| matplotlib__matplotlib-13989 | `3.0.2.post2267+gdff5d85a8` | 完全相同 | `v3.0.2-2267-gdff5d85a8` |
| matplotlib__matplotlib-22719 | `3.6.0.dev1932+g3cd319a26d` | 完全相同 | `v3.5.0-1932-g3cd319a26d` |

Django代表保留25,827个commit及8个tag；两个Matplotlib代表分别保留29,316/42,482个commit及71/100个tag，各拒绝1个不符合base祖先条件的tag。三个控制的版本和git describe均保持一致。

这说明“只需要完整文件树相同”不足以保证运行语义相同。此前r2的Git结构控制没有覆盖动态版本计算，本次真实入口观察暴露了这个不足；旧结果、失败与r2镜像均保留，不把它们改写为r3成功。

## 调度、映射与范围

逐题回执位于`runs/software-benchmark-v054/images/actor-admission-r3/instances/`，原始config字节位于同目录体系下的`configs/`。r3 schema为`proworksim.v054.actor-admission-r3`，成功状态为`actor_baseline_admitted`。保留原有任务/官方镜像/Actor镜像/基准tree/Python映射接口，新增`git_ancestry`、`submodule_ancestry`及`runtime_version`；`actor_head == official_head`在这一协议下是必须条件，不再沿用r2“单根commit数为1”或“原HEAD不可读取”的条件。

全量准备使用最多8个worker。每个worker按官方donor容器退出、再启动Actor目标容器的顺序执行，因此同时存活的准备容器不超过8个；每容器4 CPU、16 GiB，无网络、无GPU。临时pack只在本项目`/data0`缓存目录及容器临时区，完成后删除自己产生的临时文件。没有重新下载镜像层或重hash整套镜像资产。

三个先行成功回执在全量阶段复用。其余每题仅修订受影响Git层，原r2的源码/副本检查不重跑。候选内容差分仍对应原官方setup工作树；Gitlink完整内容与工作树补丁的既有控制继续有效。

公开测试入口观察与此阶段分开记录于`runs/software-benchmark-v054/public-entry-family-r1/final-summary.json`：21个仓库×Python major.minor代表的入口help均可启动；它不是500次suite执行。最初只读探测中Astropy的Hypothesis缓存不可写导致help失败，随后仅在实际Actor可写临时层下校正该代表，原失败保留。它没有被误记为模型错误。

全500任务的最终r3数量以收尾索引为准。模型容量、原生工具、PROJECT公开测试接缝、官方评分及正式运行授权继续分别计量；单个准备阶段成功不替代这些条件。

## r3.1：官方历史对象的精确格式诊断

全量r3首次结束为459题通过、41题技术未定。失败来自官方允许祖先闭包中已有的历史Git元数据格式，并非当前工作树修复内容：Flask1题包含5个`zeroPaddedFilemode`树对象，scikit-learn32题共享1个同类树对象，Requests8题共享1个`badTimezone` commit对象。旧r3失败回执保留，459题成功结果没有重做。

先在三个固定官方代表镜像中按相同OID检查原始对象，重新计算Git对象OID及原始内容SHA256，并确认对象可从官方HEAD到达、原始fsck包含完全相同的诊断行。七个对象全部满足这些条件。公开审计原件保存在`artifacts/software-benchmark-v054/actor/historical-format-audits-r31/`；没有把整个`zeroPaddedFilemode`或`badTimezone`类别设为忽略。

| 仓库 | 明确允许的历史对象 |
| --- | --- |
| Flask | tree `0b404df8c030cdeaca7b373956c3a697efd32f78`、`6a37da079f3bed362608b2558b162617c0c3af5c`、`51ea366fd4253b3a618289dc1c0c4bb16a3c2a22`、`679afdb340e9e1011927b52d2cd48bd221159131`、`77c7430020693d35500ca4fc292cff63fc3e672b` |
| scikit-learn | tree `5475d108765c5591003210e70fc01bf2a77fca55` |
| Requests | commit `5e6ecdad9f69b1ff789a17733b8edc6fd7091bd8` |

规则位于`config/v054-historical-git-format-exceptions-r31.json`，原始文件SHA256为`43f5dd872f7b6b3eb6ebb48441758daef2c590e40e62f971a5983ad05e9c992c`。每项同时固定仓库、对象类型、OID、raw SHA256、大小、诊断代码及完整诊断行。r3.1执行程序为`tools/verified_actor_historical_formats_v054.py`，在每个实际官方镜像中再次核对该对象和诊断，派生侧也核对同一原始对象；不会重写历史对象或改变其OID。

派生侧完整fsck的输出只能包含当前仓库白名单中的这些精确行，不能夹带其他错误、warning或不可达对象。实际返回码如实记录：格式warning-only为0，Requests的历史对象格式错误位为4；不会伪写成0。另行执行connectivity-only检查，必须返回0且输出为空。refs精确白名单、完整祖先闭包数量、无额外commit/不可达对象、工作树和实际运行时版本等价的所有门均保留。

schema独立标为`proworksim.v054.actor-admission-r3.1`。`git_ancestry`新增`fsck_structural_validation_passed`、`fsck_connectivity_returncode`及`historical_format_exceptions`；后者包含逐对象官方来源与目标hash证据，验证方必须精确匹配上述固定policy。原始`fsck_returncode`仍在回执中。所有例外在任何模型回合之前基于环境证据确定，同一道题三组使用相同策略与派生镜像。

准备器先对三个受影响代表闭合，再按授权将其余受影响项提高到16个并发worker；每个worker仍顺序完成donor和target，最大同时16个容器。该资源调整仅属于准备阶段，没有改变正式Actor的4 CPU/16 GiB约束。

## 最终500题共同CPU初态

2026-10-21 10:27:33 CST固定的 [收尾简报](../../artifacts/software-benchmark-v054/actor/actor-baseline-completion-r3.json) 和 [完整500题索引](../../artifacts/software-benchmark-v054/actor/actor-baseline-index-r3.json) 给出以下实际结果。索引SHA256为`96e20137f03fe3a868bfb4eba1c3570276269d69dcfc09a4236cb65011db705c`，6,753,901 bytes；每题另外绑定canonical映射JSON的path、SHA和字节数。

| 条件 | 实际结果 |
| --- | --- |
| 官方镜像加载 | 500/500 |
| 最终共同Actor CPU初态准入 | 500/500 |
| 原r3／精确格式例外r3.1 | 459／41 |
| 当前技术未定 | 0 |
| Actor HEAD及tracked tree与官方相同 | 500/500 |
| 实际目标模块导入版本与官方相同 | 500/500 |
| allowed祖先、refs及无不可达对象准入 | 500/500 |
| 原始full fsck返回码 | 492题为0；8个Requests为4 |
| 8个返回4的Requests | 同一历史对象精确例外，connectivity-only均0 |
| 此轮新增模型调用、镜像下载、整层重hash | 均为0 |

r3主策略SHA为`a67d9030ecfc6a698d83f490606cb7e9823432a5cd330fa08e8829c5d607c3aa`；r3.1综合执行策略为`7c3206938a850f1446aac627a44d2d87d99c15d742ac046bdebb0b1e00b520ed`。41项完整fsck输出的规范行数组存入`fsck_diagnostic_lines`：执行时已经要求stdout为空、stderr行集合与固定例外精确相等；最终汇总按该已执行等值门重建排序后的同值数组，明确记录这一依据，没有谎称另行保存过原始输出顺序，也没有重跑fsck。逐题实际返回码保持原值。

原r2、首次r3格式失败、三个代表修订和剩余38项修订的回执均保留。成功的459题没有再次构建；先行通过的3项r3.1也没有在38项阶段重跑。必要Ruff检查通过，没有新增无关测试。

这一结果解决共同镜像初态、合法Git上下文及已观察到的运行时版本漂移。它仍不声称完成500次任务suite、模型推理或正式评测，也不将定向已知包路径隔离表述为全文件系统无泄露证明。原生工具、PROJECT入口、官方评分接缝、模型容量和正式授权由各自最终准备状态单列。
