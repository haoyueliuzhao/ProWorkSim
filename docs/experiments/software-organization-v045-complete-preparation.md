# v0.45原14槽接续准备记录

**必要准入已通过；本文件记录源码冻结和模型启动之前的CPU/只读状态，新增模型调用为0。**

用户随新审计授权修订成员固定预算归因，并继续原14未启动槽。完整原24槽仍有10已执行；本轮不重跑旧槽，不改变模型可见条件，不分配旧未用预算。

## 必要修订与核验

新增共享原准备解析器、反馈r2和工作r2测量，以及独立接续准入与宿主入口；原src、旧模块和旧测试均未改。成员固定预算证明绑定原start/stop/boundary、meter、调用/机会/输入身份、共享账单前后守恒与无副作用/后续生成。若原成员meter先拒且同时硬容量不足，按真实先拒原因归因并单列并发超限，不能把普通context或服务异常笼统归为固定预算。

最终必要CPU控制为27项测量反例加41项宿主库存/准入/合并控制，共68项；全项目Ruff通过。早期宿主36项通过属于同套件开发阶段，不另算36项独立控制。测量首次收集时有测试代码括号错误，修复后27项通过；失败日志和来源均保留。旧业务、分页、tokenizer资格和191次模型调用不重做。

HA/452/S1反馈重物化仅改变feedback698的派生无后续原因：原unknown保留，新版为member_fixed_budget。35个反馈/34次呈现、原R0/498562token及原实际输入输出均不变；组合原10槽仍191反馈=175呈现+16无后续，派生原因9正常结束+4context+2共享预算+1成员固定预算。原停止算法在新版回执上返回continue，原measurement_pending未覆盖。

工作机会视图补回已准备但未生成的末次机会，报告资源元数据的后续机会由25增为26，实际后续生成仍25。S1无伙伴聚合由旧null派生为False只表示不适用；三条snapshot produced未知和所有成果内容、正式R保持。准入只允许这些精确元数据变化，不放宽程序指纹。

## 失败与修复原件

根代理第一次工作物化误用项目Python3.14.6；AST序列化导致程序指纹与原worker的Python3.12.3不同，程序及行为证据并未变化。两解释器对同一初始apply_batch函数的窄CPU比较证明3.12指纹精确复现旧件。3.14候选、失败日志与helper存档；反馈归因复用已通过输出，只在原3.12解释器重物化工作测量，全部程序指纹和三个结构未知随后精确一致。

首次准入命令缺create子命令，在argparse阶段退出，未开始准入读取或执行；修正调用后准入通过。该命令日志同样保留。以上均为宿主准备过程，不是模型采样或业务验收。

## 原库存、预算与后续

14槽的case/完整seed/先手/块内顺序取自原plan并排除已执行10槽。新上限1792决定/attempt、7000000token、448测试；加旧实际费用的上界为1990决定、1983调用、9563352token、467测试。原未用2436648token不转移。最多3驻留且只物理GPU3/4/5/7，原资源与局部/全局停止规则不变。

只读HA业务义务与LA公开后接收机会补充见[解释修订](software-organization-v045-audit-original14-transition.md)，内容不会进入新模型输入。原C/A仅在原24闭合后评估触发证据，本轮未增加模型预算；旧训练/Contribution/确认/缓存队列保持暂停。

| 证据 | SHA-256 |
|---|---|
| audit | `2e76f31e4b605c8581810c62a9f4b9b8a4ed45e36a71c3b145c20819d25283f6` |
| admission | `d60d9ebe7a06b0844c43cca338e9e555951455a6240cb31cda8855d33278b77b` |
| qualification | `efc009196464e7383833b82ae5490dcc52b9dab4a20922e338586eba0c33fa63` |
| measurement_controls | `3b8df5f1c1e9a69c4d15243250ee61e61a1f1d327c78e42735b0da29fc89bc77` |
| retained_review | `de191468724f0b3b1609a6b90c3afd83e3034d2327354e03e7ffde5d2ccacbf7` |
| python_ast_review | `8d731c1791abdb8089fd73e29f8b1aed3eaebc90b5628ff690c8a4d96de76889` |
| business_publication_review | `d0221760438327ab91bf4c0edf03ea0f4652f406a6981842d14a030969e7b9f6` |
| initial_host_tests | `de32e54b6594c82d14980e45cff4b25f92262ffee0c60d21bc798afcf5bd0f95` |
| missing_mode_cli_log | `ed49b2aed79806b5241c78b8f639e4e0750a25484ce6280680258e922e718943` |
| successful_admission_log | `eb23664be5642797b0f1e5b4c76b495bd9e6fdfb45887b71856727e270771a4a` |

[冻结协议](software-organization-v045-complete-protocol.md) · [准备机器记录](software-organization-v045-complete-preparation.json) · [原10槽报告](software-organization-v045-final.md)
